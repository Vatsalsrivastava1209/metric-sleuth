from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.dependencies import get_current_user, require_pro_tier
from api.main import app

client = TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_pdf_export_blocks_non_pro_user():
    def _deny_user():
        raise HTTPException(
            status_code=403,
            detail="Active 'Pro' or 'Business' subscription required to access this endpoint.",
        )

    app.dependency_overrides[require_pro_tier] = _deny_user

    response = client.get("/api/v1/export/pdf/report-123")

    assert response.status_code == 403
    assert "Pro" in response.json()["detail"]


def test_pdf_export_returns_pdf_for_pro_user():
    app.dependency_overrides[require_pro_tier] = lambda: {
        "user_id": "user-456",
        "email": "ceo@agency.com",
        "access_token": "jwt-token",
    }

    with patch("src.db.get_report", return_value={"report_md": "# RCA Report"}), patch(
        "api.routers.export._markdown_to_pdf_bytes",
        return_value=b"%PDF-1.4 mock pdf bytes",
    ):
        response = client.get("/api/v1/export/pdf/report-123")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment;" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF-1.4")


def test_markdown_export_supports_client_mode():
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "user-456",
        "email": "ceo@agency.com",
        "access_token": "jwt-token",
    }

    with patch(
        "src.db.get_report",
        return_value={
            "id": "report-123",
            "dataset_id": "dataset-123",
            "anomaly_date": "2026-04-01",
            "primary_metric": "revenue",
            "executive_summary": "Mobile conversion softened after landing-page changes.",
            "top_hypothesis": "Paid social traffic quality dropped on mobile.",
            "n_anomalies": 2,
            "n_hypotheses": 4,
        },
    ), patch(
        "src.db.get_profile",
        return_value={"full_name": "Northstar Growth"},
    ), patch(
        "src.db.get_dataset",
        return_value={"name": "Aurelia Skin"},
    ):
        response = client.get("/api/v1/export/markdown/report-123?audience=client")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert b"Northstar Growth Client Incident Brief" in response.content
    assert b"Aurelia Skin" in response.content
