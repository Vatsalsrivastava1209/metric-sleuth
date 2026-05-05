from unittest.mock import patch

from fastapi.testclient import TestClient

from api.dependencies import require_pro_tier
from api.main import app

client = TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def _pro_user():
    return {
        "user_id": "pro-user-123",
        "email": "analyst@example.com",
        "access_token": "jwt-token",
        "tier": "pro",
    }


def test_memory_stats_returns_index_summary():
    app.dependency_overrides[require_pro_tier] = _pro_user

    with patch(
        "api.routers.memory.get_profile",
        return_value={"llm_api_key": "sk-test", "llm_backend": "openai"},
    ), patch(
        "api.routers.memory.get_index_stats",
        return_value={"total_documents": 4, "index_dir": "pgvector:rca_embeddings", "is_empty": False},
    ):
        response = client.get("/api/v1/memory/stats")

    assert response.status_code == 200
    assert response.json()["total_documents"] == 4


def test_memory_stats_surfaces_embedding_readiness_error_without_hiding_counts():
    app.dependency_overrides[require_pro_tier] = _pro_user

    with patch(
        "api.routers.memory.get_profile",
        return_value={"llm_api_key": "", "llm_backend": ""},
    ), patch(
        "api.routers.memory.get_embedding_runtime_status",
        return_value={"ready": False, "reason": "Embeddings are not configured."},
    ), patch(
        "api.routers.memory.get_index_stats",
        return_value={"total_documents": 2, "index_dir": "pgvector:rca_embeddings", "is_empty": False},
    ):
        response = client.get("/api/v1/memory/stats")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_documents"] == 2
    assert payload["error"]


def test_memory_query_returns_grounded_answer():
    app.dependency_overrides[require_pro_tier] = _pro_user

    class _Result:
        answer = "Yes. A similar revenue drop happened on 2026-01-15."
        sources = [
            {
                "user_id": "pro-user-123",
                "anomaly_date": "2026-01-15",
                "primary_metric": "revenue",
                "generated_at": "2026-01-16",
                "n_hypotheses": 3,
            }
        ]

    with patch(
        "api.routers.memory.get_profile",
        return_value={"llm_api_key": "sk-test", "llm_backend": "openai"},
    ), patch("api.routers.memory.query", return_value=_Result()):
        response = client.post("/api/v1/memory/query", json={"question": "Have we seen this before?"})

    assert response.status_code == 200
    payload = response.json()
    assert "similar revenue drop" in payload["answer"]
    assert payload["sources"][0]["primary_metric"] == "revenue"


def test_memory_clear_deletes_user_index():
    app.dependency_overrides[require_pro_tier] = _pro_user

    with patch(
        "api.routers.memory.get_profile",
        return_value={"llm_api_key": "sk-test", "llm_backend": "openai"},
    ), patch("api.routers.memory.clear_user_index") as mock_clear:
        response = client.delete("/api/v1/memory")

    assert response.status_code == 200
    mock_clear.assert_called_once_with("pro-user-123", "jwt-token")


def test_memory_query_returns_503_when_embeddings_are_unavailable():
    app.dependency_overrides[require_pro_tier] = _pro_user

    with patch(
        "api.routers.memory.get_profile",
        return_value={"llm_api_key": "", "llm_backend": ""},
    ), patch(
        "api.routers.memory.get_embedding_runtime_status",
        return_value={"ready": False, "reason": "Embeddings are not configured."},
    ):
        response = client.post("/api/v1/memory/query", json={"question": "Have we seen this before?"})

    assert response.status_code == 503
