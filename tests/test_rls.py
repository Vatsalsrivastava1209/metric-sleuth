"""
tests/test_rls.py
=================
Tests for Row Level Security enforcement in src/db.py.

P0-C Fix: The previous test_save_report_meta_propagates_rls() tested a phantom
API — it passed access_token="test_jwt_123" to save_report_meta(), but that
parameter was removed in the architectural refactor. The function now uses
service-role + session-level _impersonate_user() instead of a user JWT.

The ghost test silently passed because mock.patch("src.db.get_client") intercepted
the call at the wrong level, causing the test to validate a call signature that
no longer existed. This provides false security assurance to auditors.

The rewritten tests verify the ACTUAL current implementation:
1. get_client() correctly applies the JWT to PostgREST (unchanged)
2. save_report_meta() uses the admin (service-role) client + _impersonate_user()
   RPC — NOT get_client() with a JWT. This is the correct pattern for Celery
   background tasks where JWTs would expire.
"""

import os
from unittest.mock import MagicMock, call, patch

import pytest


# ── Test 1: get_client JWT forwarding ────────────────────────────────────────

def test_rls_client_instantiation_forwards_jwt():
    """
    Ensures get_client(access_token) applies the JWT to PostgREST, activating
    RLS policies that use auth.uid().
    """
    mock_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy_token"

    with patch("supabase.create_client") as mock_create_client:
        mock_supabase = MagicMock()
        mock_create_client.return_value = mock_supabase

        with patch.dict(os.environ, {"SUPABASE_URL": "http://mock", "SUPABASE_ANON_KEY": "mock"}):
            from src.db import get_client
            client = get_client(access_token=mock_token)

            mock_create_client.assert_called_once()

            # The critical security check: JWT must be passed to PostgREST
            # so that RLS auth.uid() resolves to the correct tenant.
            mock_supabase.postgrest.auth.assert_called_once_with(mock_token)


def test_rls_client_no_token_skips_auth():
    """
    Ensures get_client() with no token does NOT call postgrest.auth,
    so the anonymous key is used without any user identity claim.
    This is the expected behaviour for public/service-role paths.
    """
    with patch("supabase.create_client") as mock_create_client:
        mock_supabase = MagicMock()
        mock_create_client.return_value = mock_supabase

        with patch.dict(os.environ, {"SUPABASE_URL": "http://mock", "SUPABASE_ANON_KEY": "mock"}):
            from src.db import get_client
            get_client(access_token=None)

            # No JWT — postgrest.auth should NOT be called
            mock_supabase.postgrest.auth.assert_not_called()


# ── Test 2: save_report_meta uses service-role + impersonation ───────────────

def test_save_report_meta_uses_service_role_and_impersonation():
    """
    P0-C Fix: Validates the ACTUAL current API of save_report_meta().

    The function must:
    1. Use get_admin_client() (service role) — NOT get_client(access_token).
       Background workers don't carry JWTs; JWTs expire, service keys don't.
    2. Call _impersonate_user(client, user_id) BEFORE the INSERT, which fires
       an RPC to set the Postgres session variable request.jwt.claim.sub,
       activating RLS as if the user's JWT were present.

    If _impersonate_user is not called, the INSERT succeeds under the service
    role but RLS is NOT applied — any user_id could be inserted for any tenant,
    breaking multi-tenant isolation.
    """
    mock_admin_client = MagicMock()
    # Simulate the INSERT returning a row with an id
    mock_admin_client.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": "report-uuid-123"}
    ]
    # Simulate the impersonation RPC succeeding
    mock_admin_client.rpc.return_value.execute.return_value = MagicMock()

    with patch("src.db.get_admin_client", return_value=mock_admin_client), \
         patch("src.db._impersonate_user") as mock_impersonate:

        from src.db import save_report_meta
        result = save_report_meta(
            user_id="user-uuid-123",
            dataset_id="dataset-uuid-456",
            anomaly_date="2024-01-15",
            primary_metric="revenue",
            executive_summary="Revenue dropped 23% due to a regional outage.",
            n_anomalies=3,
            n_hypotheses=2,
            top_hypothesis="Regional infrastructure outage",
            confidence=0.87,
            report_md="# RCA Report\n...",
        )

        # 1. Must impersonate the user BEFORE inserting
        mock_impersonate.assert_called_once_with(mock_admin_client, "user-uuid-123")

        # 2. Must INSERT into rca_reports
        mock_admin_client.table.assert_called_once_with("rca_reports")
        mock_admin_client.table.return_value.insert.assert_called_once()

        # 3. Must return the new report ID on success
        assert result == "report-uuid-123"


def test_save_report_meta_aborts_if_impersonation_fails():
    """
    If _impersonate_user raises (e.g. service key rejected), save_report_meta
    must NOT proceed with the INSERT. Writing without impersonation would mean
    the INSERT runs under service-role with no RLS, which could allow cross-
    tenant data writes.
    """
    mock_admin_client = MagicMock()

    with patch("src.db.get_admin_client", return_value=mock_admin_client), \
         patch("src.db._impersonate_user", side_effect=RuntimeError("Impersonation RPC failed")):

        from src.db import save_report_meta
        result = save_report_meta(
            user_id="user-uuid-123",
            dataset_id=None,
            anomaly_date="2024-01-15",
            primary_metric="revenue",
            executive_summary="",
        )

        # INSERT must NOT have been called — impersonation failure is fatal
        mock_admin_client.table.return_value.insert.assert_not_called()

        # Must return None (not raise) — the pipeline handles the None gracefully
        assert result is None
