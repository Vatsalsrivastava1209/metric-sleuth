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
        "email": "ops@example.com",
        "access_token": "jwt-token",
    }


def test_update_report_workflow_route_returns_updated_fields():
    app.dependency_overrides[get_current_user] = _mock_user

    with patch(
        "api.routers.reports.update_report_meta",
        return_value={
            "id": "report-123",
            "workflow_status": "investigating",
            "assigned_owner": "alex@agency.com",
            "internal_notes": "Check Meta account history.",
        },
    ):
        response = client.patch(
            "/api/v1/reports/report-123",
            json={
                "workflow_status": "investigating",
                "assigned_owner": "alex@agency.com",
                "internal_notes": "Check Meta account history.",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow_status"] == "investigating"
    assert payload["assigned_owner"] == "alex@agency.com"


def test_create_share_link_returns_public_path():
    app.dependency_overrides[get_current_user] = _mock_user

    with patch(
        "api.routers.reports.create_report_share_token",
        return_value={"id": "report-123", "share_token": "share-abc", "workflow_status": "ready_to_send"},
    ):
        response = client.post("/api/v1/reports/report-123/share-link")

    assert response.status_code == 200
    payload = response.json()
    assert payload["share_token"] == "share-abc"
    assert payload["public_path"] == "/brief/share-abc"


def test_public_brief_returns_client_safe_payload():
    with patch(
        "api.routers.reports.get_shared_report",
        return_value={
            "report": {
                "id": "report-123",
                "anomaly_date": "2026-04-01",
                "primary_metric": "revenue",
                "executive_summary": "Revenue dipped after mobile conversion softened.",
                "top_hypothesis": "Mobile conversion rate weakened.",
                "confidence": 0.81,
                "n_anomalies": 3,
                "n_hypotheses": 4,
                "report_payload": {
                    "hypotheses": [
                        {
                            "title": "Mobile conversion rate weakened.",
                            "supporting_evidence": ["Mobile CVR fell 19% week over week."],
                        }
                    ]
                },
            },
            "workspace_name": "Aurelia Skin",
            "agency_name": "Northstar Growth",
        },
    ):
        response = client.get("/api/v1/public/brief/share-abc")

    assert response.status_code == 200
    payload = response.json()
    assert payload["workspace_name"] == "Aurelia Skin"
    assert payload["agency_name"] == "Northstar Growth"
    assert payload["evidence"]


def test_deliver_to_slack_requires_webhook_configuration():
    app.dependency_overrides[get_current_user] = _mock_user

    with patch("api.routers.reports.get_report", return_value={"id": "report-123", "dataset_id": None}), patch(
        "api.routers.reports.get_profile",
        return_value={"slack_webhook_url": "", "full_name": "Northstar Growth"},
    ):
        response = client.post("/api/v1/reports/report-123/deliver/slack", json={})

    assert response.status_code == 409
