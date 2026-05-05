"""
scripts/webhook_payloads.py
============================
Realistic Stripe JSON payload factories for every webhook event type handled
by api/routers/webhooks.py.

All payloads are structured to be identical in schema to live Stripe sandbox
events. They can be signed with HMAC-SHA256 and sent directly to your endpoint.

Usage:
    from scripts.webhook_payloads import build_payload, EVENT_TYPES
"""

from __future__ import annotations

import time
import uuid
from typing import Any


# ── Shared fixtures ────────────────────────────────────────────────────────────


def _new_event_id() -> str:
    return "evt_" + uuid.uuid4().hex[:24]


def _new_customer_id() -> str:
    return "cus_" + uuid.uuid4().hex[:14]


def _new_subscription_id() -> str:
    return "sub_" + uuid.uuid4().hex[:14]


def _new_invoice_id() -> str:
    return "in_" + uuid.uuid4().hex[:14]


def _new_session_id() -> str:
    return "cs_" + uuid.uuid4().hex[:14]


def _new_user_id() -> str:
    """Simulate a Supabase UUID (what we'd store in client_reference_id)."""
    return str(uuid.uuid4())


def _now() -> int:
    return int(time.time())


# ── Price IDs ─────────────────────────────────────────────────────────────────
# These mirror the values you'd set in STRIPE_PRICE_PRO / STRIPE_PRICE_BUSINESS.
# The stress tester overrides them from the environment if set.
PRICE_PRO = "price_test_pro_monthly"
PRICE_BUSINESS = "price_test_business_monthly"


def _subscription_item(price_id: str, sub_id: str) -> dict:
    return {
        "id": "si_" + uuid.uuid4().hex[:14],
        "object": "subscription_item",
        "subscription": sub_id,
        "price": {
            "id": price_id,
            "object": "price",
            "currency": "usd",
            "unit_amount": 4900 if "pro" in price_id else 9900,
            "recurring": {"interval": "month"},
        },
        "quantity": 1,
    }


def _subscription(
    customer_id: str,
    sub_id: str,
    price_id: str,
    status: str = "active",
) -> dict:
    return {
        "id": sub_id,
        "object": "subscription",
        "customer": customer_id,
        "status": status,
        "items": {
            "object": "list",
            "data": [_subscription_item(price_id, sub_id)],
        },
        "current_period_end": _now() + 2_592_000,
        "current_period_start": _now(),
        "created": _now(),
        "cancel_at_period_end": False,
    }


# ── Payload Factories ─────────────────────────────────────────────────────────


def checkout_session_completed(
    user_id: str | None = None,
    customer_id: str | None = None,
    tier: str = "pro",
) -> dict[str, Any]:
    """A user just completed a checkout and bought Pro or Business."""
    cid = customer_id or _new_customer_id()
    uid = user_id or _new_user_id()
    sub_id = _new_subscription_id()
    price_id = PRICE_PRO if tier == "pro" else PRICE_BUSINESS
    return {
        "id": _new_event_id(),
        "type": "checkout.session.completed",
        "created": _now(),
        "data": {
            "object": {
                "id": _new_session_id(),
                "object": "checkout.session",
                "customer": cid,
                "client_reference_id": uid,
                "subscription": sub_id,
                "payment_status": "paid",
                "status": "complete",
                "mode": "subscription",
            }
        },
    }


def subscription_updated(
    customer_id: str | None = None,
    tier: str = "business",
    sub_status: str = "active",
) -> dict[str, Any]:
    """A subscriber changed plans — e.g. pro → business upgrade."""
    cid = customer_id or _new_customer_id()
    sub_id = _new_subscription_id()
    price_id = PRICE_PRO if tier == "pro" else PRICE_BUSINESS
    return {
        "id": _new_event_id(),
        "type": "customer.subscription.updated",
        "created": _now(),
        "data": {
            "object": _subscription(cid, sub_id, price_id, status=sub_status),
        },
    }


def subscription_deleted(
    customer_id: str | None = None,
) -> dict[str, Any]:
    """A subscription was cancelled or expired — downgrade to free."""
    cid = customer_id or _new_customer_id()
    sub_id = _new_subscription_id()
    return {
        "id": _new_event_id(),
        "type": "customer.subscription.deleted",
        "created": _now(),
        "data": {
            "object": _subscription(cid, sub_id, PRICE_PRO, status="canceled"),
        },
    }


def invoice_payment_failed(
    customer_id: str | None = None,
) -> dict[str, Any]:
    """A renewal payment failed — we should flag payment_failed_at, NOT downgrade."""
    cid = customer_id or _new_customer_id()
    return {
        "id": _new_event_id(),
        "type": "invoice.payment_failed",
        "created": _now(),
        "data": {
            "object": {
                "id": _new_invoice_id(),
                "object": "invoice",
                "customer": cid,
                "status": "open",
                "amount_due": 4900,
                "attempt_count": 1,
                "next_payment_attempt": _now() + 86_400,
            }
        },
    }


def subscription_paused(
    customer_id: str | None = None,
) -> dict[str, Any]:
    """Stripe paused the subscription (merchant pause_collection feature)."""
    cid = customer_id or _new_customer_id()
    sub_id = _new_subscription_id()
    return {
        "id": _new_event_id(),
        "type": "customer.subscription.paused",
        "created": _now(),
        "data": {
            "object": _subscription(cid, sub_id, PRICE_PRO, status="paused"),
        },
    }


def unknown_event() -> dict[str, Any]:
    """An event type we don't handle — should return 200 and be silently ignored."""
    return {
        "id": _new_event_id(),
        "type": "payment_intent.created",
        "created": _now(),
        "data": {"object": {"id": "pi_" + uuid.uuid4().hex[:14]}},
    }


def invalid_signature_payload() -> bytes:
    """A totally garbled raw body to test our 400 rejection path."""
    return b"this is not a valid stripe payload {malformed JSON"


# ── Registry ──────────────────────────────────────────────────────────────────

EVENT_FACTORIES = {
    "checkout.session.completed": checkout_session_completed,
    "customer.subscription.updated": subscription_updated,
    "customer.subscription.deleted": subscription_deleted,
    "invoice.payment_failed": invoice_payment_failed,
    "customer.subscription.paused": subscription_paused,
    "unknown_event": unknown_event,
}

EVENT_TYPES = list(EVENT_FACTORIES.keys())


def build_payload(event_type: str, **kwargs) -> dict:
    """Return a full Stripe-shaped event dict for the given event_type."""
    factory = EVENT_FACTORIES.get(event_type)
    if not factory:
        raise ValueError(f"Unknown event type: {event_type}. Available: {EVENT_TYPES}")
    return factory(**kwargs)
