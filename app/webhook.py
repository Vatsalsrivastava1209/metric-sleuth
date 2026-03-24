"""
webhook.py
==========
Stripe webhook handler — a lightweight Flask server that runs alongside
the Streamlit app and processes subscription lifecycle events.

Run standalone:
    python app/webhook.py

Or as a Railway/Render service with:
    Start command: python app/webhook.py

Environment variables required:
    STRIPE_WEBHOOK_SECRET   — from Stripe Dashboard > Webhooks > Signing secret
    SUPABASE_URL            — your Supabase project URL
    SUPABASE_SERVICE_KEY    — service role key (bypasses RLS for tier updates)
"""

from __future__ import annotations

import logging
import os

from flask import Flask, request, jsonify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger("webhook")

app = Flask(__name__)


# ── Stripe → tier mapping ─────────────────────────────────────────────────────
# Keys must match the metadata.tier you set in billing.py create_checkout_session()

_STRIPE_TIER_MAP = {
    "pro":      "pro",
    "business": "business",
}


def _get_stripe():
    import stripe  # type: ignore
    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    return stripe


# ── Webhook endpoint ──────────────────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def stripe_webhook():
    payload    = request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature", "")
    secret     = os.getenv("STRIPE_WEBHOOK_SECRET", "")

    stripe = _get_stripe()

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except stripe.error.SignatureVerificationError:
        logger.warning("Webhook signature verification failed.")
        return jsonify({"error": "Invalid signature"}), 400
    except Exception as exc:
        logger.error("Webhook parse error: %s", exc)
        return jsonify({"error": str(exc)}), 400

    event_type = event["type"]
    logger.info("Received Stripe event: %s", event_type)

    # ── Successful checkout ───────────────────────────────────────────────────
    if event_type == "checkout.session.completed":
        session = event["data"]["object"]
        user_id  = session.get("metadata", {}).get("user_id", "")
        tier     = session.get("metadata", {}).get("tier", "")
        customer = session.get("customer", "")

        if user_id and tier:
            _update_tier(user_id, tier, stripe_customer_id=customer)
        else:
            logger.warning("checkout.session.completed missing metadata: %s", session)

    # ── Subscription cancelled / payment failed ───────────────────────────────
    elif event_type in ("customer.subscription.deleted", "invoice.payment_failed"):
        obj       = event["data"]["object"]
        customer  = obj.get("customer", "")
        if customer:
            user_id = _user_id_from_customer(customer)
            if user_id:
                _update_tier(user_id, "free")

    return jsonify({"status": "ok"}), 200


# ── Helpers ───────────────────────────────────────────────────────────────────

def _update_tier(user_id: str, tier: str, stripe_customer_id: str = "") -> None:
    """Update the user's subscription tier in Supabase."""
    from src.db import set_user_tier
    ok = set_user_tier(user_id, tier, stripe_customer_id)
    if ok:
        logger.info("Updated tier: user=%s → %s", user_id, tier)
    else:
        logger.error("Failed to update tier for user=%s", user_id)


def _user_id_from_customer(stripe_customer_id: str) -> str | None:
    """Look up user_id via stripe_customer_id in Supabase profiles."""
    from src.db import get_admin_client
    try:
        client = get_admin_client()
        result = (
            client.table("profiles")
            .select("id")
            .eq("stripe_customer_id", stripe_customer_id)
            .single()
            .execute()
        )
        profile = result.data
        return profile["id"] if profile else None
    except Exception as exc:
        logger.error("Could not look up customer %s: %s", stripe_customer_id, exc)
        return None


# ── Health check ──────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy"}), 200


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("WEBHOOK_PORT", 5001))
    logger.info("Stripe webhook server listening on port %d", port)
    app.run(host="0.0.0.0", port=port)
