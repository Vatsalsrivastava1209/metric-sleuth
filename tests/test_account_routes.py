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


def test_request_headers_include_request_id_and_timing():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.headers.get("x-request-id")
    assert response.headers.get("x-process-time-ms")


def test_get_profile_returns_sanitized_profile():
    app.dependency_overrides[get_current_user] = _mock_user

    with patch(
        "api.routers.account.get_profile",
        return_value={
            "full_name": "Northstar Growth",
            "subscription_tier": "business",
            "llm_backend": "openai",
            "llm_api_key_vault_id": "vault-secret",
            "slack_webhook_url": "https://hooks.slack.com/services/test",
            "alert_email": "alerts@example.com",
            "stripe_customer_id": "cus_123",
        },
    ):
        response = client.get("/api/v1/account/profile")

    assert response.status_code == 200
    payload = response.json()
    assert payload["subscription_tier"] == "business"
    assert payload["llm_api_key_configured"] is True
    assert payload["email"] == "cto@example.com"
    assert payload["agency_name"] == "Northstar Growth"


def test_update_profile_forwards_access_token():
    app.dependency_overrides[get_current_user] = _mock_user

    with patch("api.routers.account.update_profile", return_value=True) as mock_update_profile:
        response = client.put(
            "/api/v1/account/profile",
            json={
                "agency_name": "Northstar Growth",
                "llm_backend": "gemini",
                "alert_email": "alerts@example.com",
            },
        )

    assert response.status_code == 200
    mock_update_profile.assert_called_once_with(
        "user-123",
        {"full_name": "Northstar Growth", "llm_backend": "gemini", "alert_email": "alerts@example.com"},
        "jwt-token",
    )


def test_checkout_route_returns_stripe_url():
    app.dependency_overrides[get_current_user] = _mock_user

    with patch(
        "api.routers.account.create_checkout_session",
        return_value="https://checkout.stripe.test/session",
    ):
        response = client.post(
            "/api/v1/account/billing/checkout",
            json={
                "tier": "pro",
                "success_url": "https://app.example.com/dashboard/billing?upgraded=1",
                "cancel_url": "https://app.example.com/dashboard/billing",
            },
        )

    assert response.status_code == 200
    assert response.json()["checkout_url"].startswith("https://checkout.stripe.test/")


def test_portal_route_requires_customer_id():
    app.dependency_overrides[get_current_user] = _mock_user

    with patch("api.routers.account.get_profile", return_value={"stripe_customer_id": ""}):
        response = client.post(
            "/api/v1/account/billing/portal",
            json={"return_url": "https://app.example.com/dashboard/billing"},
        )

    assert response.status_code == 404
