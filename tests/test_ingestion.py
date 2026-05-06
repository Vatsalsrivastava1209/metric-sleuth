"""
tests/test_ingestion.py
=======================
Integration tests for the M2M ingestion endpoint.

The current implementation validates the API key through api.dependencies and
stages the payload in shared object storage through src.db.get_admin_client.
These tests patch those exact runtime dependencies instead of stale helper names.
"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def _make_mock_admin_client(user_id: str = "test-user-id-555") -> MagicMock:
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"user_id": user_id}
    ]
    return mock_supabase


def _make_mock_storage_client() -> MagicMock:
    mock_storage_client = MagicMock()
    mock_bucket = MagicMock()
    mock_storage_client.storage.from_.return_value = mock_bucket
    return mock_storage_client


@patch("api.dependencies.get_admin_client")
@patch("src.db.get_admin_client")
@patch("api.routers.ingest.create_analysis_run", return_value=True)
@patch("api.routers.ingest.run_rca_pipeline.apply_async")
def test_successful_m2m_ingestion(
    mock_apply_async,
    mock_create_analysis_run,
    mock_storage_admin_client,
    mock_auth_admin_client,
):
    raw_key = "sk_live_12345securekey"
    mock_auth_admin_client.return_value = _make_mock_admin_client("test-user-id-555")
    storage_client = _make_mock_storage_client()
    mock_storage_admin_client.return_value = storage_client

    payload = {
        "dataset_name": "shopify_prod",
        "metric": "sales",
        "records": [
            {"date": "2024-01-01", "sales": 100},
            {"date": "2024-01-02", "sales": 150},
        ],
    }

    response = client.post(
        "/api/v1/ingest/",
        json=payload,
        headers={"x-api-key": raw_key},
    )

    assert response.status_code == 202, (
        f"Expected 202, got {response.status_code}. Body: {response.json()}"
    )
    body = response.json()
    assert "job_id" in body
    assert body["status"] == "Accepted"
    storage_client.storage.from_.assert_called_once()
    storage_client.storage.from_.return_value.upload.assert_called_once()
    mock_create_analysis_run.assert_called_once()
    mock_apply_async.assert_called_once()
    args = mock_create_analysis_run.call_args.args
    assert args[2] == "sales"
    assert args[3] is None
    assert args[4] == "shopify_prod"


@patch("api.dependencies.get_admin_client")
def test_failed_m2m_ingestion_bad_key(mock_get_admin_client):
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    mock_get_admin_client.return_value = mock_supabase

    response = client.post(
        "/api/v1/ingest/",
        json={"dataset_name": "x", "metric": "y", "records": [{"date": "2024-01-01", "y": 1}]},
        headers={"x-api-key": "fake_bad_key"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or revoked API Key."


@patch("api.dependencies.get_admin_client")
def test_missing_api_key_returns_401(mock_get_admin_client):
    response = client.post(
        "/api/v1/ingest/",
        json={"dataset_name": "x", "metric": "y", "records": [{"date": "2024-01-01", "y": 1}]},
    )
    assert response.status_code == 401


@patch("api.dependencies.get_admin_client")
def test_empty_records_rejected(mock_get_admin_client):
    raw_key = "sk_live_validkey"
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"user_id": "test-user-id-555"}
    ]
    mock_get_admin_client.return_value = mock_supabase

    response = client.post(
        "/api/v1/ingest/",
        json={"dataset_name": "x", "metric": "y", "records": []},
        headers={"x-api-key": raw_key},
    )
    assert response.status_code in (401, 422), (
        f"Expected 401 or 422 for empty records, got {response.status_code}"
    )
