"""
tests/test_rls.py
=================
Tests for Row Level Security enforcement in src/db.py.

These tests intentionally validate the current architecture:
1. get_client() applies the caller JWT to the shared anon client so RLS can
   resolve auth.uid() correctly.
2. save_report_meta() uses the service-role client plus _impersonate_user()
   before writing, which is the correct pattern for background jobs.
"""

from unittest.mock import MagicMock, patch


def test_rls_client_instantiation_forwards_jwt():
    """
    Ensures get_client(access_token) applies the JWT to PostgREST, activating
    RLS policies that use auth.uid().
    """
    mock_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy_token"
    mock_supabase = MagicMock()

    with patch("utils.supabase_client.get_anon_singleton", return_value=mock_supabase):
        from src.db import get_client

        client = get_client(access_token=mock_token)

        assert client is mock_supabase
        mock_supabase.postgrest.auth.assert_called_once_with(mock_token)


def test_rls_client_no_token_skips_auth():
    """
    Ensures get_client() with no token does NOT call postgrest.auth, so the
    anonymous key is used without any user identity claim.
    """
    mock_supabase = MagicMock()

    with patch("utils.supabase_client.get_anon_singleton", return_value=mock_supabase):
        from src.db import get_client

        get_client(access_token=None)

        mock_supabase.postgrest.auth.assert_not_called()


def test_save_report_meta_uses_service_role_and_impersonation():
    """
    save_report_meta() must impersonate the user before inserting so tenant
    isolation is preserved for service-role background writes.
    """
    mock_admin_client = MagicMock()
    mock_admin_client.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": "report-uuid-123"}
    ]
    mock_admin_client.rpc.return_value.execute.return_value = MagicMock()

    with (
        patch("src.db.get_admin_client", return_value=mock_admin_client),
        patch("src.db._impersonate_user") as mock_impersonate,
    ):
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

        mock_impersonate.assert_called_once_with(mock_admin_client, "user-uuid-123")
        mock_admin_client.table.assert_called_once_with("rca_reports")
        mock_admin_client.table.return_value.insert.assert_called_once()
        assert result == "report-uuid-123"


def test_save_report_meta_aborts_if_impersonation_fails():
    """
    If user impersonation fails, save_report_meta() must not proceed with an
    insert that would bypass tenant isolation.
    """
    mock_admin_client = MagicMock()

    with (
        patch("src.db.get_admin_client", return_value=mock_admin_client),
        patch("src.db._impersonate_user", side_effect=RuntimeError("Impersonation RPC failed")),
    ):
        from src.db import save_report_meta

        result = save_report_meta(
            user_id="user-uuid-123",
            dataset_id=None,
            anomaly_date="2024-01-15",
            primary_metric="revenue",
            executive_summary="",
        )

        mock_admin_client.table.return_value.insert.assert_not_called()
        assert result is None
