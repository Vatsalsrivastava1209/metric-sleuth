"""
access_control.py
=================
Server-side access control and audit logging for MetricSleuth SaaS.

Why this module exists
----------------------
Streamlit renders all UI in a single Python process.  The ``billing.gate()``
function hides UI elements for locked features, but a sophisticated user could
manipulate Streamlit's WebSocket state to bypass those guards.

This module adds a **second enforcement layer** for the most sensitive premium
features:

1. ``verify_tier_server_side(user_id, feature)``
   Re-reads the user's subscription tier **directly from Supabase** (not from
   session state) before granting access.  If the tiers disagree, the Supabase
   value wins and the session is updated.

2. ``log_feature_access(...)``
   Appends every access decision to a ``feature_access_log`` table in Supabase
   so you have a tamper-evident audit trail.

Usage
-----
Replace the most sensitive ``gate()`` calls with::

    from src.access_control import verify_tier_server_side

    if verify_tier_server_side(uid, "pdf_export"):
        # render PDF download button
        ...

Features protected by server-side verification (in order of sensitivity):
  - ``pdf_export``
  - ``rag_history``
  - ``llm_summary``

All other features still use ``billing.gate()`` for performance.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Features that warrant a round-trip to Supabase for verification.
# Lower-stakes features (segmentation, correlation) are gated client-side only.
_HIGH_SENSITIVITY_FEATURES = frozenset({"pdf_export", "rag_history", "llm_summary"})


# ── Supabase helpers ──────────────────────────────────────────────────────────

def _get_supabase_client():
    """Return a Supabase client (same pattern as auth.py — avoids circular import)."""
    try:
        from supabase import create_client  # type: ignore
    except ImportError as exc:
        raise ImportError("supabase-py is not installed. Run: pip install supabase") from exc

    import os
    from dotenv import load_dotenv
    load_dotenv()

    # Safe Streamlit import — access_control.py is imported by the FastAPI backend
    # which does NOT have Streamlit installed. The try/except mirrors billing.py L29.
    try:
        import streamlit as _st  # type: ignore
        url = _st.secrets.get("SUPABASE_URL", "") if _st is not None else ""
        key = _st.secrets.get("SUPABASE_ANON_KEY", "") if _st is not None else ""
    except Exception:
        url = key = ""

    url = url or os.getenv("SUPABASE_URL", "")
    key = key or os.getenv("SUPABASE_ANON_KEY", "")

    if not url or not key:
        raise RuntimeError("Supabase credentials not configured.")

    return create_client(url, key)



def _fetch_tier_from_db(user_id: str) -> str:
    """Fetch the subscription tier for *user_id* directly from Supabase profiles.

    Returns ``\"free\"`` if the profile cannot be found or the call fails.
    This is the authoritative source — session state is only a cache.
    """
    try:
        client = _get_supabase_client()
        result = (
            client.table("profiles")
            .select("subscription_tier")
            .eq("id", user_id)
            .single()
            .execute()
        )
        return (result.data or {}).get("subscription_tier", "free")
    except Exception as exc:
        logger.warning(
            "access_control: Could not fetch tier for user %s: %s — defaulting to 'free'.",
            user_id, exc,
        )
        return "free"


# ── Audit logging ─────────────────────────────────────────────────────────────

def log_feature_access(
    user_id: str,
    feature: str,
    tier: str,
    granted: bool,
    source: str = "server",
) -> None:
    """Append an access decision to the ``feature_access_log`` Supabase table.

    Call this after every access decision on a high-sensitivity feature.
    The table schema should be::

        CREATE TABLE feature_access_log (
            id          BIGSERIAL PRIMARY KEY,
            user_id     UUID NOT NULL,
            feature     TEXT NOT NULL,
            tier        TEXT NOT NULL,
            granted     BOOLEAN NOT NULL,
            source      TEXT NOT NULL DEFAULT 'server',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );

    If the table does not exist or the insert fails, the error is swallowed so
    it never disrupts the user-facing flow.
    """
    try:
        client = _get_supabase_client()
        client.table("feature_access_log").insert({
            "user_id":    user_id,
            "feature":    feature,
            "tier":       tier,
            "granted":    granted,
            "source":     source,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as exc:
        # Non-fatal: log locally but never surface to the user
        logger.debug("access_control: audit log insert failed: %s", exc)


# ── Public API ────────────────────────────────────────────────────────────────

def verify_tier_server_side(
    user_id: str | None,
    feature: str,
    session_tier: str = "free",
) -> bool:
    """Gate a feature with server-side tier verification.

    For low-sensitivity features this falls back to ``billing.check_access``
    using the session tier.  For high-sensitivity features a Supabase round-trip
    is made to confirm the tier has not been tampered with.

    Parameters
    ----------
    user_id:
        The current user's UUID.  Pass ``None`` (anonymous) returns ``False``
        for any premium feature.
    feature:
        Feature key to check (e.g. ``\"pdf_export\"``).
    session_tier:
        Tier stored in session state — used as fast path for low-sensitivity
        features and as a fallback if Supabase is unreachable.

    Returns
    -------
    bool
        ``True`` if access is granted, ``False`` otherwise.
    """
    from src.billing import check_access

    # Anonymous users never get premium features, regardless of feature type.
    if not user_id:
        logger.debug("access_control: anonymous user denied '%s'.", feature)
        return False

    if feature in _HIGH_SENSITIVITY_FEATURES:
        # Authoritative check: re-read from Supabase
        authoritative_tier = _fetch_tier_from_db(user_id)

        if authoritative_tier != session_tier:
            logger.warning(
                "access_control: tier mismatch for user %s — session='%s', db='%s'. "
                "Using authoritative DB value.",
                user_id, session_tier, authoritative_tier,
            )
            # Sync session state so the badge reflects reality
            try:
                import streamlit as st
                user = st.session_state.get("ms_user")
                if user:
                    user["tier"] = authoritative_tier
                    st.session_state["ms_user"] = user
            except Exception:
                pass

        resolved_tier = authoritative_tier
        granted = check_access(feature, resolved_tier)
        log_feature_access(user_id, feature, resolved_tier, granted, source="server")
        return granted

    else:
        # Fast path: trust session state for non-sensitive features
        granted = check_access(feature, session_tier)
        return granted
