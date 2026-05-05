from unittest.mock import patch

from fastapi.testclient import TestClient

from api.dependencies import get_current_user
from api.main import app

client = TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def _mock_user():
    return {
        "user_id": "user-123",
        "email": "cto@example.com",
        "access_token": "jwt-token",
    }


def test_start_analysis_with_saved_dataset_creates_run_and_enqueues_job():
    app.dependency_overrides[get_current_user] = _mock_user

    with patch("api.routers.analyze.create_analysis_run", return_value=True) as mock_create_run, patch(
        "api.routers.analyze.run_rca_pipeline.apply_async"
    ) as mock_apply_async:
        response = client.post(
            "/api/v1/analyze/",
            data={"metric": "revenue", "dataset_id": "dataset-001"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_id"]
    mock_create_run.assert_called_once()
    mock_apply_async.assert_called_once()


def test_start_analysis_rejects_foreign_storage_key():
    app.dependency_overrides[get_current_user] = _mock_user

    response = client.post(
        "/api/v1/analyze/",
        data={"metric": "revenue", "storage_key": "other-user/run.csv"},
    )

    assert response.status_code == 403


def test_job_status_reads_canonical_run_state():
    app.dependency_overrides[get_current_user] = _mock_user

    with patch(
        "api.routers.analyze.get_analysis_run",
        return_value={
            "id": "job-123",
            "status": "SUCCESS",
            "status_message": "Investigation complete.",
            "progress_meta": {"stage": "complete"},
            "report_id": "report-123",
        },
    ):
        response = client.get("/api/v1/analyze/jobs/job-123")

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "SUCCESS"
    assert payload["meta"]["report_id"] == "report-123"


def test_signed_upload_url_rejects_unsupported_extension():
    app.dependency_overrides[get_current_user] = _mock_user

    response = client.post(
        "/api/v1/analyze/signed-url",
        data={"filename": "client-export.xlsx"},
    )

    assert response.status_code == 422


def test_signed_upload_url_accepts_csv_and_returns_storage_key():
    app.dependency_overrides[get_current_user] = _mock_user

    class _StorageBucket:
        def create_signed_upload_url(self, storage_key: str):
            return {"signedUrl": "https://storage.example/upload", "path": storage_key}

    class _Storage:
        def from_(self, _bucket: str):
            return _StorageBucket()

    class _AdminClient:
        storage = _Storage()

    with patch("api.dependencies.get_admin_client", return_value=_AdminClient()):
        response = client.post(
            "/api/v1/analyze/signed-url",
            data={"filename": "client-export.csv"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["storage_key"].endswith(".csv")
