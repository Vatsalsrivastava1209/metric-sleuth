from unittest.mock import patch

import pandas as pd
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


def test_dataset_templates_return_agency_catalog():
    app.dependency_overrides[get_current_user] = _mock_user

    response = client.get("/api/v1/datasets/templates")

    assert response.status_code == 200
    payload = response.json()
    assert payload["templates"]
    assert payload["integrations"]


def test_demo_dataset_creates_workspace():
    app.dependency_overrides[get_current_user] = _mock_user

    with patch("api.routers.datasets.upload_user_dataset_bytes", return_value="user-123/demo.csv"), patch(
        "api.routers.datasets.save_dataset_meta",
        return_value="dataset-123",
    ):
        response = client.post("/api/v1/datasets/demo")

    assert response.status_code == 201
    payload = response.json()
    assert payload["dataset_id"] == "dataset-123"
    assert payload["row_count"] > 0


class _FakeConnector:
    def connect(self, **kwargs):
        self.kwargs = kwargs
        return True, "connected"

    def test_connection(self):
        return True, "Connected to fake provider."

    def fetch_data(self, _query):
        return pd.DataFrame(
            [
                {
                    "date": "2026-04-01",
                    "revenue": 1000,
                    "traffic": 500,
                    "orders": 20,
                    "conversion_rate": 0.04,
                    "region": "US",
                    "device": "mobile",
                    "traffic_source": "Shopify",
                }
            ]
        )


def test_integration_test_endpoint_validates_provider_credentials():
    app.dependency_overrides[get_current_user] = _mock_user

    with patch("api.routers.datasets.get_connector", return_value=_FakeConnector()):
        response = client.post(
            "/api/v1/datasets/integrations/test",
            json={
                "provider": "shopify",
                "workspace_name": "Aurelia Skin | Shopify",
                "credentials": {"shop_domain": "aurelia.myshopify.com", "access_token": "shpat_test"},
                "lookback_days": 30,
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_integration_workspace_endpoint_persists_native_dataset():
    app.dependency_overrides[get_current_user] = _mock_user

    with patch("api.routers.datasets.get_connector", return_value=_FakeConnector()), patch(
        "api.routers.datasets.save_dataset_meta",
        return_value="dataset-native-123",
    ) as mock_save:
        response = client.post(
            "/api/v1/datasets/integrations/workspace",
            json={
                "provider": "shopify",
                "workspace_name": "Aurelia Skin | Shopify",
                "credentials": {"shop_domain": "aurelia.myshopify.com", "access_token": "shpat_test"},
                "lookback_days": 30,
            },
        )

    assert response.status_code == 201
    payload = response.json()
    assert payload["dataset_id"] == "dataset-native-123"
    assert payload["connector_type"] == "shopify"
    mock_save.assert_called_once()
