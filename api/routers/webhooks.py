"""
api/routers/webhooks.py
=======================
Stripe Webhook Listener — synchronizes subscription state with Supabase profiles.

Handled Events
--------------
checkout.session.completed
    A user completed a Stripe Checkout session. Upgrades their tier to the
    purchased plan immediately.

customer.subscription.updated
    A subscription was modified (plan upgrade pro→business, downgrade, renewal).
    Resolves the new tier from the Stripe price ID and writes it to the profiles table.

customer.subscription.deleted
    A subscription was cancelled or expired. Immediately downgrades to 'free'.

invoice.payment_failed
    A renewal payment failed. We do NOT immediately downgrade — instead we record a
    `payment_failed_at` timestamp so the UI can show a warning banner. The hard
    downgrade happens only when Stripe sends `customer.subscription.deleted` after
    its retry window exhausts.

customer.subscription.paused
    Stripe paused the subscription. Treated like a payment failure: flag the profile
    timestamp, keep the tier active to avoid mid-period disruption.

Security
--------
All events are cryptographically verified via stripe.Webhook.construct_event()
using the STRIPE_WEBHOOK_SECRET. Requests without a valid signature are rejected
with HTTP 400 before any DB operations are performed.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, Header, HTTPException, Request, status

import asyncio

from api.dependencies import get_admin_client
from api.routers.analyze import check_rate_limit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "sk_test_mock")
_endpoint_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "whsec_mock")

# Maps Stripe price IDs → internal subscription tiers.
# Populated from environment variables so pricing can change without code deploys.
# If a price ID is not in this map we fall back to "pro" (safe — avoids accidental downgrades
# when a new price is added to Stripe before the env var is updated in this service).
_PRICE_TO_TIER: dict[str, str] = {}


def _build_price_tier_map() -> None:
    """Populate _PRICE_TO_TIER from STRIPE_PRICE_PRO / STRIPE_PRICE_BUSINESS env vars."""
    for tier in ("pro", "business"):
        price_id = os.environ.get(f"STRIPE_PRICE_{tier.upper()}", "")
        if price_id:
            _PRICE_TO_TIER[price_id] = tier


_build_price_tier_map()


def _resolve_tier_from_subscription(subscription: dict) -> str:
    """Map a Stripe subscription object to an internal tier string.

    Reads the price ID from the first subscription item and looks it up in
    _PRICE_TO_TIER. Falls back to 'pro' if unrecognised.
    """
    try:
        items = subscription.get("items", {}).get("data", [])
        if items:
            price_id = items[0].get("price", {}).get("id", "")
            if price_id and price_id in _PRICE_TO_TIER:
                return _PRICE_TO_TIER[price_id]
    except (KeyError, IndexError, TypeError):
        pass

    logger.warning(
        "Could not resolve tier from subscription %s — defaulting to 'pro'.",
        subscription.get("id", "unknown"),
    )
    return "pro"


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None),
) -> dict:
    """
    Stripe Webhook Listener.
    Synchronizes Stripe subscription states with the Supabase Profiles table.
    All events are cryptographically verified before any DB writes occur.
    """
    if not stripe_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Stripe-Signature header.",
        )

    payload = await request.body()

    try:
        # Cryptographically verify the event originated from Stripe.
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, _endpoint_secret
        )
    except ValueError as exc:
        logger.error("Stripe webhook: invalid payload — %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook payload.",
        ) from exc
    except stripe.error.SignatureVerificationError as exc:
        logger.error("Stripe webhook: signature verification failed — %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stripe signature verification failed.",
        ) from exc

    client = get_admin_client()
    event_id:   str = event["id"]
    event_type: str = event["type"]
    logger.info("Stripe webhook received: %s (id=%s)", event_type, event_id)

    # ── P0-B: Idempotency guard ───────────────────────────────────────────────
    # Stripe guarantees at-least-once delivery, so the same event may arrive
    # multiple times during retries. We record the event_id in a dedicated table
    # before any DB writes. On conflict (duplicate delivery) we return 200
    # immediately — Stripe will stop retrying on any 2xx response.
    try:
        client.table("stripe_processed_events").insert({
            "event_id":   event_id,
            "event_type": event_type,
        }).execute()
    except Exception as exc:
        # PostgREST returns a 409-equivalent on UNIQUE violation.
        # The error message contains '23505' (the Postgres unique_violation code).
        if "23505" in str(exc) or "duplicate" in str(exc).lower():
            logger.info(
                "Stripe webhook: duplicate event ignored (id=%s type=%s).",
                event_id, event_type,
            )
            return {"status": "already_processed", "event_id": event_id}
        # Any other error (DB down, service key issue) — log and continue.
        # We prefer to process a duplicate event over silently dropping a valid one.
        logger.error(
            "Stripe webhook: could not record event_id=%s: %s — proceeding anyway.",
            event_id, exc,
        )

    # ── checkout.session.completed ────────────────────────────────────────────
    if event_type == "checkout.session.completed":
        session = event["data"]["object"]
        metadata = session.get("metadata") or {}
        # Accept both the new canonical field and older sessions that only
        # populated metadata.user_id so upgrades remain recoverable.
        user_id = session.get("client_reference_id") or metadata.get("user_id")
        customer_id = session.get("customer")

        # Resolve the exact tier purchased from the attached subscription.
        # P1-A Fix: stripe.Subscription.retrieve() is a synchronous blocking HTTP call.
        # Calling it directly inside an async route blocks the entire FastAPI event loop
        # for the network RTT to Stripe (~200-500ms). Under concurrent webhook delivery
        # (guaranteed during subscription lifecycle events) this causes cascading delays
        # across all in-flight requests. asyncio.to_thread() moves it to the thread pool.
        import asyncio
        tier = "pro"
        subscription_id = session.get("subscription")
        if subscription_id:
            try:
                sub = await asyncio.to_thread(stripe.Subscription.retrieve, subscription_id)
                tier = _resolve_tier_from_subscription(sub)
            except Exception as exc:
                logger.warning(
                    "Could not retrieve subscription %s for tier resolution: %s",
                    subscription_id, exc,
                )

        if user_id:
            client.table("profiles").update({
                "subscription_tier": tier,
                "stripe_customer_id": customer_id,
                "payment_failed_at": None,   # clear any prior payment failure flag
            }).eq("id", user_id).execute()
            logger.info(
                "Upgraded user %s to '%s' tier via checkout.session.completed.",
                user_id, tier,
            )
        else:
            logger.error(
                "checkout.session.completed missing user mapping for session=%s",
                session.get("id", "unknown"),
            )

    # ── customer.subscription.updated ────────────────────────────────────────
    # Fires on plan changes (upgrade, downgrade, renewal, trial end).
    # Previously MISSING → pro→business upgrades were silently lost.
    elif event_type == "customer.subscription.updated":
        subscription = event["data"]["object"]
        customer_id = subscription.get("customer")
        sub_status = subscription.get("status", "")

        if customer_id:
            if sub_status in ("active", "trialing"):
                tier = _resolve_tier_from_subscription(subscription)
                client.table("profiles").update({
                    "subscription_tier": tier,
                    "payment_failed_at": None,  # clear prior failure flag on renewal
                }).eq("stripe_customer_id", customer_id).execute()
                logger.info(
                    "Updated subscription for customer %s → tier='%s' (status=%s).",
                    customer_id, tier, sub_status,
                )
            elif sub_status in ("past_due", "unpaid"):
                # Payment is overdue but Stripe hasn't cancelled yet.
                # Do NOT downgrade — Stripe retries for several days before deletion.
                # The invoice.payment_failed event handles the UI warning banner.
                logger.info(
                    "Subscription for customer %s is '%s' — awaiting Stripe retry cycle.",
                    customer_id, sub_status,
                )

    # ── customer.subscription.deleted ────────────────────────────────────────
    elif event_type == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        customer_id = subscription.get("customer")

        if customer_id:
            client.table("profiles").update({
                "subscription_tier": "free",
                "payment_failed_at": None,
            }).eq("stripe_customer_id", customer_id).execute()
            logger.info(
                "Downgraded customer %s to 'free' (subscription deleted).", customer_id,
            )

    # ── invoice.payment_failed ────────────────────────────────────────────────
    # Previously MISSING → payment failures were invisible until subscription deletion.
    # Now we write payment_failed_at so the frontend can show a recovery banner
    # without hard-downgrading the user while Stripe is still retrying.
    elif event_type == "invoice.payment_failed":
        invoice = event["data"]["object"]
        customer_id = invoice.get("customer")

        if customer_id:
            failed_at = datetime.now(timezone.utc).isoformat()
            client.table("profiles").update({
                "payment_failed_at": failed_at,
            }).eq("stripe_customer_id", customer_id).execute()
            logger.warning(
                "Payment failed for customer %s at %s — profile flagged for UI warning.",
                customer_id, failed_at,
            )

    # ── customer.subscription.paused ─────────────────────────────────────────
    # Previously MISSING. Handles merchant-initiated pause (pause_collection feature).
    # We reuse payment_failed_at as a "subscription not active" signal for the UI.
    elif event_type == "customer.subscription.paused":
        subscription = event["data"]["object"]
        customer_id = subscription.get("customer")

        if customer_id:
            paused_at = datetime.now(timezone.utc).isoformat()
            client.table("profiles").update({
                "payment_failed_at": paused_at,
            }).eq("stripe_customer_id", customer_id).execute()
            logger.info(
                "Subscription paused for customer %s at %s.", customer_id, paused_at,
            )

    else:
        # All other event types are safely ignored. Stripe sends many event types
        # (customer.created, payment_intent.*, etc.) that don't affect our state.
        logger.debug("Stripe webhook: unhandled event type '%s' — ignoring.", event_type)

    return {"status": "success", "event_type": event_type}
