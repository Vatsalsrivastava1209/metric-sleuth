"""
db.py
=====
Supabase data access layer for MetricSleuth SaaS.

All database operations are centralised here. Each function accepts a
user_id so that callers cannot accidentally access another user's data
(RLS provides the second layer of protection).

Usage
-----
    from src.db import get_client, get_user_datasets, save_dataset_meta
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


# ── Client factory ─────────────────────────────────────────────────────────────

def get_client():
    """Return an authenticated Supabase client.

    Uses the ANON key (respects RLS) for all user-facing operations.
    For admin operations (e.g. webhook server), use the SERVICE key.
    """
    try:
        from supabase import create_client  # type: ignore
    except ImportError as exc:
        raise ImportError("Run: pip install supabase") from exc

    import os
    from dotenv import load_dotenv
    load_dotenv()

    url = ""
    key = ""
    try:
        import streamlit as st
        url = st.secrets.get("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_ANON_KEY", "")
    except Exception:
        pass

    url = url or os.getenv("SUPABASE_URL", "")
    key = key or os.getenv("SUPABASE_ANON_KEY", "")

    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be set.")

    return create_client(url, key)


def get_admin_client():
    """Return a Supabase client using the SERVICE_ROLE key (bypasses RLS).
    Only use in the webhook server — never in the Streamlit frontend.
    """
    try:
        from supabase import create_client  # type: ignore
    except ImportError as exc:
        raise ImportError("Run: pip install supabase") from exc

    import os
    from dotenv import load_dotenv
    load_dotenv()

    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set.")
    return create_client(url, key)


# ── Profile ───────────────────────────────────────────────────────────────────

def get_profile(user_id: str) -> dict:
    """Return the profile row for a user."""
    client = get_client()
    result = (
        client.table("profiles")
        .select("*")
        .eq("id", user_id)
        .single()
        .execute()
    )
    return result.data or {}


def update_profile(user_id: str, updates: dict) -> bool:
    """Update profile fields (e.g. llm_api_key, slack_webhook_url)."""
    client = get_client()
    try:
        client.table("profiles").update(updates).eq("id", user_id).execute()
        return True
    except Exception as exc:
        logger.error("Failed to update profile %s: %s", user_id, exc)
        return False


def get_user_tier(user_id: str) -> str:
    """Return the subscription tier ('free'|'pro'|'business')."""
    profile = get_profile(user_id)
    return profile.get("subscription_tier", "free")


def set_user_tier(user_id: str, tier: str, stripe_customer_id: str = "") -> bool:
    """Update subscription tier (called from Stripe webhook)."""
    client = get_admin_client()   # needs service key to bypass RLS
    updates: dict = {"subscription_tier": tier}
    if stripe_customer_id:
        updates["stripe_customer_id"] = stripe_customer_id
    try:
        client.table("profiles").update(updates).eq("id", user_id).execute()
        logger.info("Updated tier for %s → %s", user_id, tier)
        return True
    except Exception as exc:
        logger.error("Failed to set tier: %s", exc)
        return False


# ── Datasets ─────────────────────────────────────────────────────────────────

def get_user_datasets(user_id: str) -> list[dict]:
    """Return all datasets belonging to a user, newest first."""
    client = get_client()
    result = (
        client.table("datasets")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


def get_dataset(dataset_id: str, user_id: str) -> dict | None:
    """Return a single dataset, verifying ownership."""
    client = get_client()
    result = (
        client.table("datasets")
        .select("*")
        .eq("id", dataset_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    return result.data


def save_dataset_meta(
    user_id: str,
    name: str,
    connector_type: str,
    schema_mapping: dict,
    connection_config: dict | None = None,
    row_count: int | None = None,
) -> str | None:
    """
    Insert a new dataset record.

    Returns the new dataset UUID on success, None on failure.
    """
    client = get_client()
    row: dict[str, Any] = {
        "user_id":          user_id,
        "name":             name,
        "connector_type":   connector_type,
        "schema_mapping":   schema_mapping,
        "connection_config": connection_config or {},
        "row_count":        row_count,
        "last_synced_at":   datetime.utcnow().isoformat(),
    }
    try:
        result = client.table("datasets").insert(row).execute()
        inserted = result.data
        if inserted:
            return inserted[0]["id"]
        return None
    except Exception as exc:
        logger.error("Failed to save dataset: %s", exc)
        return None


def update_dataset_meta(dataset_id: str, user_id: str, updates: dict) -> bool:
    """Update fields on an existing user dataset."""
    client = get_client()
    try:
        client.table("datasets").update(updates).eq("id", dataset_id).eq("user_id", user_id).execute()
        return True
    except Exception as exc:
        logger.error("Failed to update dataset %s: %s", dataset_id, exc)
        return False


def delete_dataset(dataset_id: str, user_id: str) -> bool:
    """Delete a dataset record (RLS ensures only owner can delete)."""
    client = get_client()
    try:
        client.table("datasets").delete().eq("id", dataset_id).eq("user_id", user_id).execute()
        return True
    except Exception as exc:
        logger.error("Failed to delete dataset %s: %s", dataset_id, exc)
        return False


def count_user_datasets(user_id: str) -> int:
    """Return the number of datasets a user has."""
    return len(get_user_datasets(user_id))


# ── RCA Reports ──────────────────────────────────────────────────────────────

def save_report_meta(
    user_id: str,
    dataset_id: str | None,
    anomaly_date: str,
    primary_metric: str,
    executive_summary: str,
    n_anomalies: int = 0,
    n_hypotheses: int = 0,
    top_hypothesis: str = "",
    confidence: float = 0.0,
    report_md: str = "",
) -> str | None:
    """Insert an RCA report record. Returns the new report UUID."""
    client = get_client()
    row: dict[str, Any] = {
        "user_id":           user_id,
        "dataset_id":        dataset_id,
        "anomaly_date":      anomaly_date,
        "primary_metric":    primary_metric,
        "executive_summary": executive_summary,
        "n_anomalies":       n_anomalies,
        "n_hypotheses":      n_hypotheses,
        "top_hypothesis":    top_hypothesis,
        "confidence":        round(confidence, 2),
        "report_md":         report_md,
    }
    try:
        result = client.table("rca_reports").insert(row).execute()
        inserted = result.data
        return inserted[0]["id"] if inserted else None
    except Exception as exc:
        logger.error("Failed to save report: %s", exc)
        return None


def get_user_reports(user_id: str, limit: int = 50) -> list[dict]:
    """Return the user's RCA report history, newest first."""
    client = get_client()
    result = (
        client.table("rca_reports")
        .select("id, anomaly_date, primary_metric, executive_summary, n_anomalies, "
                "n_hypotheses, top_hypothesis, confidence, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


def get_report(report_id: str, user_id: str) -> dict | None:
    """Fetch a single report including the full markdown."""
    client = get_client()
    result = (
        client.table("rca_reports")
        .select("*")
        .eq("id", report_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    return result.data
