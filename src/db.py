"""
db.py
=====
Supabase data access layer for MetricSleuth SaaS.

All database operations are centralised here. Each function accepts a
user_id so that callers cannot accidentally access another user's data
(RLS provides the second layer of protection).

Security Architecture
---------------------
Background workers (Celery) MUST NOT receive or store the user's JWT. JWTs
expire in ~1 hour; a backed-up task queue will cause silent DB write failures.

Instead, all background writes use the Service Role key (which never expires)
but enforce multi-tenant isolation by calling `_impersonate_user(client, user_id)`
which sets the Postgres session variable `request.jwt.claim.sub` via an RPC call.
All RLS policies that reference `auth.uid()` resolve against this session variable,
giving us durable, non-expiring, per-user row isolation on every worker write.

Usage
-----
    from src.db import get_admin_client, save_report_meta
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from src.crypto import (
    EncryptionUnavailableError,
    decrypt_string,
    encrypt_string,
    require_encryption,
)

load_dotenv()

logger = logging.getLogger(__name__)

_CONNECTION_CONFIG_PLAINTEXT_KEYS = {
    "connector_type",
    "storage_key",
    "storage_bucket",
    "file_type",
    "session_only",
    "query",
    "lookback_days",
    "original_filename",
    "pilot_only",
    "credential_mode",
    "requires_manual_refresh",
    "token_expires_at",
    "source_label",
}
_SENSITIVE_CONNECTION_CONFIG_KEYS = {
    "access_token",
    "developer_token",
    "private_key",
    "password",
    "refresh_token",
    "client_secret",
    "api_key",
}
USER_DATASET_BUCKET = "user-datasets"
DEFAULT_SHARE_TTL_DAYS = int(os.getenv("REPORT_SHARE_TTL_DAYS", "14"))


def _json_default(value: Any) -> Any:
    """Convert pandas / numpy values into JSON-compatible Python primitives."""
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, set):
        return list(value)
    return str(value)


def _json_compatible(payload: Any) -> Any:
    """Round-trip arbitrary nested payloads into JSON-compatible objects."""
    return json.loads(json.dumps(payload, default=_json_default))


# ── Client factory ─────────────────────────────────────────────────────────────

def get_client(access_token: str | None = None):
    """Return a Supabase client authenticated with the ANON key.

    P1-A: Now returns the process-scoped singleton from utils/supabase_client
    rather than creating a new client per call. This eliminates the N\u00d7M TCP
    connection explosion that occurred when every DB function in a multi-stage
    Celery pipeline opened its own connection pool.

    For user-authenticated queries, ``access_token`` is forwarded to the
    PostgREST layer via ``client.postgrest.auth(token)`` so RLS policies fire
    against the caller's JWT. The singleton client object is shared, but the
    auth header is set per-request (not stored globally).

    For background worker writes, use ``get_admin_client() + _impersonate_user``.
    """
    try:
        from utils.supabase_client import get_anon_singleton
    except ImportError:
        # Fallback: direct instantiation (e.g., Streamlit environment without utils/)
        from supabase import create_client  # type: ignore
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_ANON_KEY", "")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be set.")
        client = create_client(url, key)
        if access_token:
            client.postgrest.auth(access_token)
        return client

    client = get_anon_singleton()
    if access_token:
        client.postgrest.auth(access_token)
    return client


def get_admin_client():
    """Return a Supabase client using the SERVICE_ROLE key.

    P1-A: Now returns the process-scoped singleton from utils/supabase_client
    rather than creating a new client per call.

    The service role bypasses Row Level Security by default.  It is ONLY safe
    to use in a trusted server context (FastAPI / Celery).  Never expose to the
    browser or a Streamlit frontend.

    For background writes that must still respect per-user isolation, call
    ``_impersonate_user(admin_client, user_id)`` immediately after obtaining
    the client.  This sets the Postgres ``request.jwt.claim.sub`` session
    variable so that all RLS policies fire correctly for that user's session
    without needing the original JWT.
    """
    try:
        from utils.supabase_client import get_service_singleton
        return get_service_singleton()
    except ImportError:
        # Fallback: direct instantiation
        from supabase import create_client  # type: ignore
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set.")
        return create_client(url, key)


def _serialize_connection_config(connection_config: dict[str, Any] | None) -> dict[str, Any]:
    """Encrypt string fields before persisting connector configuration."""
    if not connection_config:
        return {}

    require_encryption()
    stored: dict[str, Any] = {}
    encrypted_keys: list[str] = []

    for key, value in connection_config.items():
        if (
            isinstance(value, str)
            and value
            and key not in _CONNECTION_CONFIG_PLAINTEXT_KEYS
        ):
            stored[key] = encrypt_string(value)
            encrypted_keys.append(key)
        else:
            stored[key] = value

    if encrypted_keys:
        stored["__encrypted_keys__"] = encrypted_keys

    return stored


def _deserialize_connection_config(connection_config: dict[str, Any] | None) -> dict[str, Any]:
    """Decrypt persisted connector configuration for runtime use."""
    if not connection_config:
        return {}

    runtime = dict(connection_config)
    encrypted_keys = runtime.pop("__encrypted_keys__", [])
    for key in _SENSITIVE_CONNECTION_CONFIG_KEYS:
        value = runtime.get(key)
        if isinstance(value, str) and value and key not in encrypted_keys:
            raise EncryptionUnavailableError(
                f"Connection config field '{key}' is stored as plaintext and must be rotated through secure storage."
            )
    for key in encrypted_keys:
        value = runtime.get(key)
        if isinstance(value, str):
            runtime[key] = decrypt_string(value)
    return runtime


def _slugify_filename(filename: str) -> str:
    """Return a storage-safe filename stem."""
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", filename).strip("-._")
    return normalized or "dataset"


def build_user_dataset_storage_key(user_id: str, original_filename: str) -> str:
    """Generate a private storage path for a durable user dataset upload."""
    suffix = Path(original_filename).suffix.lower() or ".csv"
    safe_name = _slugify_filename(Path(original_filename).stem)
    return f"{user_id}/{datetime.utcnow():%Y%m%dT%H%M%SZ}_{uuid.uuid4().hex}_{safe_name}{suffix}"


def upload_user_dataset_bytes(
    user_id: str,
    file_bytes: bytes,
    original_filename: str,
    content_type: str = "text/csv",
) -> str:
    """Upload a durable dataset object to Supabase Storage and return its key."""
    storage_key = build_user_dataset_storage_key(user_id, original_filename)
    client = get_admin_client()
    client.storage.from_(USER_DATASET_BUCKET).upload(
        path=storage_key,
        file=file_bytes,
        file_options={"content-type": content_type, "upsert": "false"},
    )
    return storage_key


def download_user_dataset_bytes(storage_key: str) -> bytes:
    """Download a durable dataset object from Supabase Storage."""
    client = get_admin_client()
    return client.storage.from_(USER_DATASET_BUCKET).download(storage_key)


def delete_user_dataset_object(storage_key: str) -> None:
    """Delete a durable dataset object from Supabase Storage."""
    client = get_admin_client()
    client.storage.from_(USER_DATASET_BUCKET).remove([storage_key])


def _impersonate_user(admin_client: Any, user_id: str) -> None:
    """Set the Postgres session-level claim so RLS fires as if the user is authenticated.

    This is the enterprise-grade pattern for background jobs: we use the never-
    expiring service role key for connectivity, but restrict each transaction to the
    requesting user's data by injecting their UUID into the Postgres session config.

    Requires the following Postgres function to exist in your Supabase project:

        CREATE OR REPLACE FUNCTION public.set_claim(uid uuid)
        RETURNS void AS $$
        BEGIN
          PERFORM set_config('request.jwt.claim.sub', uid::text, true);
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER;

    Parameters
    ----------
    admin_client:
        A client obtained from get_admin_client().
    user_id:
        The UUID of the user whose context should be active for this session.
    """
    try:
        admin_client.rpc("set_claim", {"uid": user_id}).execute()
        logger.debug("Impersonated user %s via session-level RLS claim.", user_id)
    except Exception as exc:
        # Log and re-raise — a failed impersonation must not silently proceed
        # as a service-role write, which would bypass all tenant isolation.
        logger.error(
            "CRITICAL: Failed to set RLS session claim for user %s: %s — aborting write.",
            user_id, exc
        )
        raise RuntimeError(
            f"RLS impersonation failed for user {user_id}. Aborting to prevent cross-tenant data leakage."
        ) from exc


# ── Profile ───────────────────────────────────────────────────────────────────

def _read_llm_key_from_vault(user_id: str) -> str:
    """Read the user's LLM API key from Supabase Vault.

    Requires Vault to be enabled in the Supabase Dashboard.
    Returns an empty string if not found or if Vault is not available.
    """
    try:
        client = get_admin_client()
        secret_name = f"llm_key_{user_id}"
        result = (
            client.table("vault.decrypted_secrets")
            .select("decrypted_secret")
            .eq("name", secret_name)
            .single()
            .execute()
        )
        return (result.data or {}).get("decrypted_secret", "")
    except Exception as exc:
        logger.debug("Vault read failed for user %s: %s — falling back to encrypted column.", user_id, exc)
        return ""


def _write_llm_key_to_vault(user_id: str, plaintext_key: str) -> str | None:
    """Write the user's LLM API key to Supabase Vault.

    Returns the vault secret name on success, None on failure.
    Requires Vault to be enabled in the Supabase Dashboard.
    """
    try:
        client = get_admin_client()
        secret_name = f"llm_key_{user_id}"
        # create_secret is idempotent: if the secret exists it updates it.
        client.rpc("vault.create_secret", {
            "secret":      plaintext_key,
            "name":        secret_name,
            "description": "MetricSleuth LLM API key",
        }).execute()
        return secret_name
    except Exception as exc:
        logger.warning("Vault write failed for user %s: %s — falling back to Fernet encryption.", user_id, exc)
        return None


def get_profile(user_id: str, access_token: str | None = None) -> dict:
    """Return the profile row for a user.

    LLM API key priority:
    1. Supabase Vault (llm_api_key_vault_id is set) — SOC 2 compliant.
    2. Fernet-encrypted column (llm_api_key) — backwards compatible fallback.
    3. Empty string — key not configured.
    """
    if access_token:
        client = get_client(access_token)
    else:
        client = get_admin_client()
        _impersonate_user(client, user_id)
    result = (
        client.table("profiles")
        .select("*")
        .eq("id", user_id)
        .single()
        .execute()
    )
    profile = result.data or {}

    # P1-B: Prefer Vault if user has been migrated (vault_id column is set).
    if profile.get("llm_api_key_vault_id"):
        vault_key = _read_llm_key_from_vault(user_id)
        profile["llm_api_key"] = vault_key  # surface under the same key for callers
    elif profile.get("llm_api_key"):
        # Legacy path: Fernet-encrypted column. Decrypt for the caller.
        profile["llm_api_key"] = decrypt_string(profile["llm_api_key"])

    return profile


def update_profile(user_id: str, updates: dict, access_token: str | None = None) -> bool:
    """Update profile fields (e.g. llm_api_key, slack_webhook_url).

    P1-B: When llm_api_key is in the updates payload, attempts a Vault write first.
    On success, stores the vault secret name and clears the legacy plaintext column.
    Falls back to Fernet encryption if Vault is unavailable.
    """
    client = get_client(access_token)

    # P1-B: Route LLM API key through Vault (SOC 2 compliant at-rest encryption).
    if "llm_api_key" in updates and updates["llm_api_key"]:
        plaintext_key = updates.pop("llm_api_key")
        vault_name = _write_llm_key_to_vault(user_id, plaintext_key)
        if vault_name:
            # Vault write succeeded — store the secret name, clear legacy column.
            updates["llm_api_key_vault_id"] = vault_name
            updates["llm_api_key"] = ""   # clear plaintext/Fernet column
        else:
            # Vault unavailable — fall back to Fernet application-layer encryption.
            updates["llm_api_key"] = encrypt_string(plaintext_key)

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

def get_user_datasets(user_id: str, access_token: str | None = None) -> list[dict]:
    """Return all datasets belonging to a user, newest first.

    Parameters
    ----------
    user_id:
        The owner's UUID.
    access_token:
        Optional JWT to authenticate the Supabase client for RLS enforcement.
    """
    client = get_client(access_token)
    result = (
        client.table("datasets")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


def get_dataset(dataset_id: str, user_id: str, access_token: str | None = None) -> dict | None:
    """Return a single dataset, verifying ownership via RLS and application filter.

    Parameters
    ----------
    dataset_id:
        The dataset UUID to fetch.
    user_id:
        The expected owner.  Acts as an application-layer guard.
    access_token:
        Optional JWT for authenticated RLS enforcement.
    """
    client = get_client(access_token)
    result = (
        client.table("datasets")
        .select("*")
        .eq("id", dataset_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    return result.data


def get_dataset_runtime_config(
    dataset_id: str,
    user_id: str,
    access_token: str | None = None,
) -> dict | None:
    """Fetch a dataset row and decrypt its connector configuration for runtime use."""
    if access_token:
        dataset = get_dataset(dataset_id, user_id, access_token)
    else:
        client = get_admin_client()
        _impersonate_user(client, user_id)
        result = (
            client.table("datasets")
            .select("*")
            .eq("id", dataset_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        dataset = result.data

    if not dataset:
        return None

    dataset["connection_config"] = _deserialize_connection_config(
        dataset.get("connection_config") or {}
    )
    return dataset


def save_dataset_meta(
    user_id: str,
    name: str,
    connector_type: str,
    schema_mapping: dict,
    connection_config: dict | None = None,
    row_count: int | None = None,
    access_token: str | None = None,
) -> str | None:
    """
    Insert a new dataset record.

    Returns the new dataset UUID on success, None on failure.
    """
    client = get_client(access_token)
    row: dict[str, Any] = {
        "user_id":          user_id,
        "name":             name,
        "connector_type":   connector_type,
        "schema_mapping":   schema_mapping,
        "connection_config": _serialize_connection_config(connection_config),
        "row_count":        row_count,
        "last_synced_at":   datetime.utcnow().isoformat(),
    }
    try:
        result = client.table("datasets").insert(row).execute()
        inserted = result.data
        if inserted:
            return inserted[0]["id"]
        return None
    except EncryptionUnavailableError as exc:
        logger.error("Failed to save dataset securely for user %s: %s", user_id, exc)
        return None
    except Exception as exc:
        logger.error("Failed to save dataset: %s", exc)
        return None


def update_dataset_meta(
    dataset_id: str,
    user_id: str,
    updates: dict,
    access_token: str | None = None,
) -> bool:
    """Update fields on an existing user dataset.

    Parameters
    ----------
    access_token:
        Optional JWT for authenticated RLS enforcement.
    """
    client = get_client(access_token)
    if "connection_config" in updates:
        updates = dict(updates)
        updates["connection_config"] = _serialize_connection_config(
            updates.get("connection_config")
        )
    try:
        client.table("datasets").update(updates).eq("id", dataset_id).eq("user_id", user_id).execute()
        return True
    except EncryptionUnavailableError as exc:
        logger.error("Failed to update dataset %s securely: %s", dataset_id, exc)
        return False
    except Exception as exc:
        logger.error("Failed to update dataset %s: %s", dataset_id, exc)
        return False


def delete_dataset(dataset_id: str, user_id: str, access_token: str | None = None) -> bool:
    """Delete a dataset record (RLS ensures only owner can delete).

    Parameters
    ----------
    access_token:
        Optional JWT for authenticated RLS enforcement.
    """
    try:
        dataset = get_dataset_runtime_config(dataset_id, user_id, access_token)
        if not dataset:
            return False

        config = dataset.get("connection_config") or {}
        storage_key = config.get("storage_key")
        storage_bucket = config.get("storage_bucket")
        if storage_key and storage_bucket == USER_DATASET_BUCKET:
            delete_user_dataset_object(str(storage_key))

        client = get_client(access_token)
        client.table("datasets").delete().eq("id", dataset_id).eq("user_id", user_id).execute()
        return True
    except Exception as exc:
        logger.error("Failed to delete dataset %s: %s", dataset_id, exc)
        return False


def count_user_datasets(user_id: str, access_token: str | None = None) -> int:
    """Return the number of datasets a user has using a single COUNT(*) query.

    P1 Fix: the previous implementation called ``get_user_datasets(user_id)``
    and returned ``len(result)`` — fetching every dataset row (all columns)
    over the network just to produce a count.  On a business-tier user with
    hundreds of datasets, this transferred KBs–MBs of data for a single integer.

    This implementation issues a single ``COUNT(*)`` aggregation (PostgREST sends
    a HEAD request with a ``Prefer: count=exact`` header).  Zero rows are
    transferred; the count is read from the ``Content-Range`` response header.
    """
    client = get_client(access_token)
    try:
        result = (
            client.table("datasets")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .execute()
        )
        return result.count if result.count is not None else 0
    except Exception as exc:
        logger.error("Failed to count datasets for %s: %s", user_id, exc)
        return 0


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
    report_payload: dict[str, Any] | None = None,
    workflow_status: str = "new",
) -> str | None:
    """Insert an RCA report record securely using session-level user impersonation.

    Uses the Service Role for connectivity (never expires), then calls
    `_impersonate_user` to set the Postgres `request.jwt.claim.sub` session
    variable so that all INSERT RLS policies resolve to the correct tenant.

    This pattern is safe for long-running Celery queues where the original
    user JWT would expire, which previously caused silent report data loss.
    """
    client = get_admin_client()
    # Enforce per-user RLS without a live JWT — this must succeed or we abort.
    try:
        _impersonate_user(client, user_id)
    except Exception as exc:
        logger.error("Failed to save report: %s", exc)
        return None
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
        "report_payload":    _json_compatible(report_payload or {}),
        "workflow_status":   workflow_status,
    }
    try:
        result = client.table("rca_reports").insert(row).execute()
        inserted = result.data
        return inserted[0]["id"] if inserted else None
    except Exception as exc:
        logger.error("Failed to save report: %s", exc)
        return None


def get_user_reports(user_id: str, limit: int = 50, access_token: str | None = None) -> list[dict]:
    """Return the user's RCA report history, newest first.

    Parameters
    ----------
    access_token:
        Optional JWT for authenticated RLS enforcement.
    """
    client = get_client(access_token)
    result = (
        client.table("rca_reports")
        .select(
            "id, dataset_id, anomaly_date, primary_metric, executive_summary, n_anomalies, "
            "n_hypotheses, top_hypothesis, confidence, created_at, workflow_status, "
            "assigned_owner, last_client_delivery_at, feedback_rating"
        )
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


def get_report(report_id: str, user_id: str, access_token: str | None = None) -> dict | None:
    """Fetch a single report including the full markdown.

    P1-A Fix: The previous implementation called get_client() with no access_token,
    meaning the Supabase client used the ANON key only. RLS policies using
    auth.uid() did not fire — the only protection was the application-layer
    .eq("user_id") filter. This is acceptable only if the ANON key has no
    SELECT policy, but it violates defense-in-depth.

    With access_token forwarded, both RLS (auth.uid() = user_id) and the
    application-layer filter are active — two independent ownership checks.

    Parameters
    ----------
    access_token:
        The caller's JWT. When provided, RLS policies fire at the DB layer.
        Pass None only in contexts where no JWT is available (service tasks);
        in that case the .eq("user_id") filter is the only protection.
    """
    client = get_client(access_token)
    result = (
        client.table("rca_reports")
        .select("*")
        .eq("id", report_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    return result.data


def update_report_meta(
    report_id: str,
    user_id: str,
    updates: dict[str, Any],
    access_token: str | None = None,
) -> dict[str, Any] | None:
    """Update mutable report workflow fields and return the updated row."""
    if not updates:
        return get_report(report_id, user_id, access_token)

    client = get_client(access_token)
    payload = dict(updates)
    if "report_payload" in payload:
        payload["report_payload"] = _json_compatible(payload.get("report_payload") or {})

    try:
        result = (
            client.table("rca_reports")
            .update(payload)
            .eq("id", report_id)
            .eq("user_id", user_id)
            .execute()
        )
        rows = result.data or []
        return rows[0] if rows else get_report(report_id, user_id, access_token)
    except Exception as exc:
        logger.error("Failed to update report %s: %s", report_id, exc)
        return None


def add_report_comment(
    report_id: str,
    user_id: str,
    author_email: str,
    body: str,
    access_token: str | None = None,
) -> dict[str, Any] | None:
    """Persist an internal collaboration comment for a report."""
    client = get_client(access_token)
    try:
        result = client.table("incident_comments").insert(
            {
                "report_id": report_id,
                "user_id": user_id,
                "author_email": author_email,
                "body": body,
            }
        ).execute()
        rows = result.data or []
        return rows[0] if rows else None
    except Exception as exc:
        logger.error("Failed to add report comment for %s: %s", report_id, exc)
        return None


def get_report_comments(
    report_id: str,
    user_id: str,
    access_token: str | None = None,
) -> list[dict[str, Any]]:
    """Return internal handoff notes for a report."""
    client = get_client(access_token)
    try:
        result = (
            client.table("incident_comments")
            .select("*")
            .eq("report_id", report_id)
            .eq("user_id", user_id)
            .order("created_at", desc=False)
            .execute()
        )
        return result.data or []
    except Exception as exc:
        logger.error("Failed to fetch report comments for %s: %s", report_id, exc)
        return []


def create_report_share_token(
    report_id: str,
    user_id: str,
    access_token: str | None = None,
) -> dict[str, Any] | None:
    """Create or rotate a public client-brief token for a report."""
    share_token = secrets.token_urlsafe(24)
    expires_at = datetime.utcnow() + timedelta(days=DEFAULT_SHARE_TTL_DAYS)
    return update_report_meta(
        report_id,
        user_id,
        {
            "share_token": share_token,
            "share_created_by": user_id,
            "share_created_at": datetime.utcnow().isoformat(),
            "share_expires_at": expires_at.isoformat(),
            "share_last_accessed_at": None,
            "share_revoked_at": None,
            "workflow_status": "ready_to_send",
        },
        access_token,
    )


def revoke_report_share_token(
    report_id: str,
    user_id: str,
    access_token: str | None = None,
) -> dict[str, Any] | None:
    """Revoke a public client-brief token while preserving report history."""
    return update_report_meta(
        report_id,
        user_id,
        {"share_revoked_at": datetime.utcnow().isoformat()},
        access_token,
    )


def record_report_delivery(
    report_id: str,
    user_id: str,
    channel: str,
    access_token: str | None = None,
) -> dict[str, Any] | None:
    """Mark a report as delivered to a client-facing channel."""
    return update_report_meta(
        report_id,
        user_id,
        {
            "workflow_status": "sent",
            "delivery_channel": channel,
            "last_client_delivery_at": datetime.utcnow().isoformat(),
        },
        access_token,
    )


def record_report_feedback(
    report_id: str,
    user_id: str,
    rating: int,
    notes: str = "",
    access_token: str | None = None,
) -> dict[str, Any] | None:
    """Persist usefulness feedback on the ranked likely drivers."""
    return update_report_meta(
        report_id,
        user_id,
        {
            "feedback_rating": rating,
            "feedback_notes": notes,
        },
        access_token,
    )


def get_shared_report(share_token: str) -> dict[str, Any] | None:
    """Fetch a client-safe report view for a shared brief token."""
    client = get_admin_client()
    try:
        report_result = (
            client.table("rca_reports")
            .select("*")
            .eq("share_token", share_token)
            .single()
            .execute()
        )
    except Exception as exc:
        logger.warning("Shared report lookup failed for token %s: %s", share_token[:8], exc)
        return None

    report = report_result.data
    if not report:
        return None

    if report.get("share_revoked_at"):
        return None

    if report.get("share_expires_at"):
        try:
            expires_at = datetime.fromisoformat(str(report["share_expires_at"]).replace("Z", "+00:00"))
            if expires_at < datetime.now(expires_at.tzinfo):
                return None
        except Exception:
            logger.warning("Invalid share expiry for report %s", report.get("id"))

    workspace = None
    if report.get("dataset_id"):
        try:
            workspace = (
                client.table("datasets")
                .select("name")
                .eq("id", report["dataset_id"])
                .single()
                .execute()
            ).data
        except Exception:
            workspace = None

    profile = None
    try:
        profile = (
            client.table("profiles")
            .select("full_name, alert_email")
            .eq("id", report["user_id"])
            .single()
            .execute()
        ).data
    except Exception:
        profile = None

    try:
        client.table("rca_reports").update(
            {"share_last_accessed_at": datetime.utcnow().isoformat()}
        ).eq("id", report["id"]).execute()
    except Exception as exc:
        logger.warning("Failed to audit public brief access for report %s: %s", report.get("id"), exc)

    return {
        "report": report,
        "workspace_name": (workspace or {}).get("name", "Client workspace"),
        "agency_name": (profile or {}).get("full_name", "") or "Your Agency",
        "contact_email": (profile or {}).get("alert_email", "") or "",
    }


# Analysis runs

def create_analysis_run(
    job_id: str,
    user_id: str,
    metric: str,
    dataset_id: str | None = None,
    source_label: str | None = None,
    storage_key: str | None = None,
    source_type: str = "saved_dataset",
    access_token: str | None = None,
) -> bool:
    """Persist a canonical analysis run row before queueing background work."""
    if access_token:
        client = get_client(access_token)
    else:
        client = get_admin_client()
        _impersonate_user(client, user_id)
    row = {
        "id": job_id,
        "user_id": user_id,
        "metric": metric,
        "dataset_id": dataset_id,
        "source_label": source_label or "",
        "storage_key": storage_key,
        "source_type": source_type,
        "status": "QUEUED",
        "status_message": "Analysis queued and waiting for a worker.",
        "progress_meta": {"stage": "queued"},
        "started_at": None,
        "completed_at": None,
        "retry_count": 0,
        "dead_lettered_at": None,
    }
    try:
        client.table("analysis_runs").insert(row).execute()
        return True
    except Exception as exc:
        logger.error("Failed to create analysis run %s for user %s: %s", job_id, user_id, exc)
        return False


def update_analysis_run(
    job_id: str,
    user_id: str,
    status: str,
    status_message: str = "",
    progress_meta: dict[str, Any] | None = None,
    error_message: str | None = None,
    report_id: str | None = None,
    extra_updates: dict[str, Any] | None = None,
) -> bool:
    """Update a run using service-role connectivity plus user impersonation."""
    client = get_admin_client()
    try:
        _impersonate_user(client, user_id)
    except Exception as exc:
        logger.error("Failed to impersonate user for analysis run update %s: %s", job_id, exc)
        return False

    updates: dict[str, Any] = {
        "status": status,
        "status_message": status_message,
        "progress_meta": progress_meta or {},
        "error_message": error_message,
    }
    if report_id is not None:
        updates["report_id"] = report_id
    if extra_updates:
        updates.update(extra_updates)
    if status == "RUNNING":
        updates["started_at"] = datetime.utcnow().isoformat()
        updates["completed_at"] = None
    elif status in {"SUCCESS", "FAILURE"}:
        updates["completed_at"] = datetime.utcnow().isoformat()

    try:
        client.table("analysis_runs").update(updates).eq("id", job_id).eq("user_id", user_id).execute()
        return True
    except Exception as exc:
        logger.error("Failed to update analysis run %s for user %s: %s", job_id, user_id, exc)
        return False


def get_analysis_run(job_id: str, user_id: str, access_token: str | None = None) -> dict | None:
    """Read a single analysis run with RLS and an ownership filter."""
    client = get_client(access_token)
    try:
        result = (
            client.table("analysis_runs")
            .select("*")
            .eq("id", job_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        return result.data
    except Exception as exc:
        logger.warning("Failed to fetch analysis run %s for user %s: %s", job_id, user_id, exc)
        return None
