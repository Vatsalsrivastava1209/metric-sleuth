"""
billing.py
==========
Tier gating and Stripe billing utilities for MetricSleuth SaaS.

Tier hierarchy:  free < pro < business

Usage
-----
    from src.billing import gate, check_access, PLANS

    # In a Streamlit page:
    if gate("pdf_export"):
        # user has access — render the feature
        ...

    # Or check without rendering:
    if check_access("db_connectors"):
        show_db_connector_ui()
"""

from __future__ import annotations

import logging
import os
from typing import Any

import streamlit as st

logger = logging.getLogger(__name__)


# ── Plan definitions ──────────────────────────────────────────────────────────

PLANS: dict[str, dict[str, Any]] = {
    "free": {
        "label":        "Free",
        "price_monthly": 0,
        "color":        "#3a4a6b",
        "features": {
            "max_datasets":       1,
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
        "label":        "Pro",
        "price_monthly": 29,
        "color":        "#00e5ff",
        "features": {
            "max_datasets":       5,
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
        "label":        "Business",
        "price_monthly": 99,
        "color":        "#7b68ee",
        "features": {
            "max_datasets":       -1,   # unlimited
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
    "pdf_export":           "PDF Report Export",
    "rag_history":          "Historical RCA Query (AI Memory)",
    "prophet_detection":    "Prophet Anomaly Detection",
    "forecast":             "30-Day Forecasting",
    "llm_summary":          "AI Executive Summary",
    "db_connectors":        "Database Connectors (Postgres, MySQL, BigQuery)",
    "slack_alerts":         "Slack Alerts",
    "email_alerts":         "Email Alerts",
    "scheduler":            "Automated Monitoring Schedule",
    "multi_dataset_compare":"Multi-Dataset Comparison",
}

FEATURE_MIN_TIER: dict[str, str] = {
    feature: ("business" if not plans["pro"]["features"].get(feature) else "pro")
    for feature, plans in [("_", PLANS)]
    for feature in PLANS["free"]["features"]
    if not PLANS["free"]["features"].get(feature)
}
# Build it properly
FEATURE_MIN_TIER = {}
for feature in PLANS["free"]["features"]:
    if not PLANS["free"]["features"][feature]:
        if PLANS["pro"]["features"].get(feature):
            FEATURE_MIN_TIER[feature] = "pro"
        else:
            FEATURE_MIN_TIER[feature] = "business"


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


# ── Streamlit gate decorator ──────────────────────────────────────────────────

def gate(feature: str) -> bool:
    """
    Streamlit tier gate.

    Returns True if the current user has access to the feature.
    If not, renders an upgrade prompt in the current Streamlit context
    and returns False.

    Example
    -------
        if gate("pdf_export"):
            st.download_button("Download PDF", ...)
    """
    from src.auth import get_user_tier
    user_tier = get_user_tier()

    if check_access(feature, user_tier):
        return True

    # Feature is locked — show upgrade CTA
    required = FEATURE_MIN_TIER.get(feature, "pro")
    plan     = PLANS[required]
    label    = FEATURE_LABELS.get(feature, feature.replace("_", " ").title())
    color    = plan["color"]

    st.markdown(
        f"""
        <div style="background:#0d1327;border:1px solid {color}40;border-radius:10px;
            padding:1.2rem 1.5rem;margin:.5rem 0;">
          <div style="font-size:.65rem;letter-spacing:2px;color:{color};
              font-family:JetBrains Mono,monospace;margin-bottom:.4rem;">
              🔒 {plan['label'].upper()} FEATURE
          </div>
          <div style="font-size:.9rem;color:#c9d1e3;margin-bottom:.8rem;">
              <strong>{label}</strong> is available on the
              <span style="color:{color};font-weight:700;">{plan['label']}</span> plan
              (${plan['price_monthly']}/mo).
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button(f"Upgrade to {plan['label']} →", key=f"upgrade_{feature}"):
        st.switch_page("pages/4_💳_Billing.py")
    return False


# ── Stripe helpers ────────────────────────────────────────────────────────────

def _get_stripe():
    try:
        import stripe  # type: ignore
        stripe.api_key = (
            st.secrets.get("STRIPE_SECRET_KEY", "")
            or os.getenv("STRIPE_SECRET_KEY", "")
        )
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
    price_id  = (
        st.secrets.get(price_key, "") or os.getenv(price_key, "")
    )
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
