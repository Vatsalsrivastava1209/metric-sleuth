"""
billing.py
==========
Tier gating and Stripe billing utilities for MetricSleuth SaaS.

Tier hierarchy:  free < pro < business

Usage
-----
    from src.billing import check_access, PLANS

    if check_access("pdf_export", user_tier):
        # user has access — render the feature
        ...
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _secret_or_env(name: str, default: str = "") -> str:
    """Read from environment variables."""
    return os.getenv(name, default)


# ── Plan definitions ──────────────────────────────────────────────────────────

PLANS: dict[str, dict[str, Any]] = {
    "free": {
        "label":        "Starter",
        "price_monthly": 0,
        "color":        "#3a4a6b",
        "features": {
            "max_datasets":       3,
            "max_workspaces":     3,
            "date_history_days":  30,
            "csv_upload":         True,
            "z_score_detection":  True,
            "prophet_detection":  False,
            "forecast":           False,
            "segmentation":       True,
            "correlation":        True,
            "pdf_export":         False,
            "markdown_export":    True,
            "rag_history":        False,
            "llm_summary":        False,
            "db_connectors":      False,
            "slack_alerts":       False,
            "email_alerts":       False,
            "scheduler":          False,
            "multi_dataset_compare": False,
        },
    },
    "pro": {
        "label":        "Growth",
        "price_monthly": 499,
        "color":        "#00e5ff",
        "features": {
            "max_datasets":       15,
            "max_workspaces":     15,
            "date_history_days":  365,
            "csv_upload":         True,
            "z_score_detection":  True,
            "prophet_detection":  True,
            "forecast":           True,
            "segmentation":       True,
            "correlation":        True,
            "pdf_export":         True,
            "markdown_export":    True,
            "rag_history":        True,
            "llm_summary":        True,
            "db_connectors":      False,
            "slack_alerts":       False,
            "email_alerts":       False,
            "scheduler":          False,
            "multi_dataset_compare": True,
        },
    },
    "business": {
        "label":        "Portfolio",
        "price_monthly": 1500,
        "color":        "#7b68ee",
        "features": {
            "max_datasets":       50,
            "max_workspaces":     -1,   # unlimited
            "date_history_days":  -1,   # unlimited
            "csv_upload":         True,
            "z_score_detection":  True,
            "prophet_detection":  True,
            "forecast":           True,
            "segmentation":       True,
            "correlation":        True,
            "pdf_export":         True,
            "markdown_export":    True,
            "rag_history":        True,
            "llm_summary":        True,
            "db_connectors":      True,
            "slack_alerts":       True,
            "email_alerts":       True,
            "scheduler":          True,
            "multi_dataset_compare": True,
        },
    },
}

# Human-readable feature labels for the upgrade prompt
FEATURE_LABELS: dict[str, str] = {
    "pdf_export":           "Client-ready PDF Briefs",
    "rag_history":          "Pattern Library Memory",
    "prophet_detection":    "Deeper incident validation",
    "forecast":             "Trend and pacing outlooks",
    "llm_summary":          "Agency brief drafting",
    "db_connectors":        "Managed data connectors",
    "slack_alerts":         "Slack delivery",
    "email_alerts":         "Email delivery",
    "scheduler":            "Scheduled portfolio monitoring",
    "multi_dataset_compare":"Multi-workspace comparison",
    "workspace_slots":      "Client Workspace Slots",
}

FEATURE_MIN_TIER: dict[str, str] = {}
for _feature in PLANS["free"]["features"]:
    if not PLANS["free"]["features"][_feature]:
        if PLANS["pro"]["features"].get(_feature):
            FEATURE_MIN_TIER[_feature] = "pro"
        else:
            FEATURE_MIN_TIER[_feature] = "business"


# ── Tier comparison ───────────────────────────────────────────────────────────

_TIER_ORDER = {"free": 0, "pro": 1, "business": 2}


def tier_gte(user_tier: str, required_tier: str) -> bool:
    """Return True if user_tier is >= required_tier."""
    return _TIER_ORDER.get(user_tier, 0) >= _TIER_ORDER.get(required_tier, 99)


def check_access(feature: str, user_tier: str | None = None) -> bool:
    """
    Return True if the given tier has access to the feature.

    If user_tier is None, reads from the current Streamlit session.
    """
    if user_tier is None:
        from src.auth import get_user_tier
        user_tier = get_user_tier()

    plan = PLANS.get(user_tier, PLANS["free"])
    return bool(plan["features"].get(feature, False))


def get_max_datasets(user_tier: str | None = None) -> int:
    """Return the dataset limit for the tier (-1 = unlimited)."""
    if user_tier is None:
        from src.auth import get_user_tier
        user_tier = get_user_tier()
    return PLANS.get(user_tier, PLANS["free"])["features"]["max_datasets"]


def get_max_workspaces(user_tier: str | None = None) -> int:
    """Return the client workspace limit for the tier (-1 = unlimited)."""
    if user_tier is None:
        from src.auth import get_user_tier
        user_tier = get_user_tier()
    return PLANS.get(user_tier, PLANS["free"])["features"]["max_workspaces"]


# ── Stripe helpers ────────────────────────────────────────────────────────────

def _get_stripe():
    try:
        import stripe  # type: ignore
        stripe.api_key = _secret_or_env("STRIPE_SECRET_KEY", "")
        return stripe
    except ImportError as exc:
        raise ImportError("Run: pip install stripe") from exc


def create_checkout_session(
    user_id: str,
    user_email: str,
    tier: str,            # "pro" | "business"
    success_url: str,
    cancel_url: str,
) -> str | None:
    """
    Create a Stripe Checkout session for a tier upgrade.
    Returns the checkout URL, or None on error.
    """
    stripe = _get_stripe()

    # Read price IDs from secrets / env
    price_key = f"STRIPE_PRICE_{tier.upper()}"
    price_id  = _secret_or_env(price_key, "")
    if not price_id:
        logger.error("No Stripe price ID configured for tier '%s' (set %s).", tier, price_key)
        return None

    try:
        session = stripe.checkout.Session.create(
            customer_email=user_email,
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=success_url + "?upgraded=1",
            cancel_url=cancel_url,
            client_reference_id=user_id,
            metadata={"user_id": user_id, "tier": tier},
        )
        return session.url
    except Exception as exc:
        logger.error("Stripe checkout error: %s", exc)
        return None


def create_portal_session(stripe_customer_id: str, return_url: str) -> str | None:
    """Create a Stripe Customer Portal session for billing management."""
    stripe = _get_stripe()
    try:
        session = stripe.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url=return_url,
        )
        return session.url
    except Exception as exc:
        logger.error("Stripe portal error: %s", exc)
        return None
