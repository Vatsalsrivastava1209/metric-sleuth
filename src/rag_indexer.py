"""
rag_indexer.py
==============
Indexes historical investigation reports into Supabase pgvector so they can be
retrieved later by semantic similarity.

The production pgvector schema is pinned to OpenAI ``text-embedding-3-small``
(1536 dims). If embedding infrastructure is unavailable, indexing fails closed
instead of writing placeholder vectors that make semantic search appear healthy
while silently returning junk results.
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Embeddings are stored in a vector(1536) column, so only the OpenAI backend is
# supported by the current production schema.
_EMBED_BACKEND: str = os.getenv("EMBED_BACKEND", "openai").lower()
_EMBED_API_KEY: str = os.getenv("EMBED_API_KEY", "")
_OPENAI_EMBED_MODEL: str = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
EMBED_DIMS: int = 1536
_TABLE = "rca_embeddings"


class EmbeddingUnavailableError(RuntimeError):
    """Raised when semantic memory is not configured or not supported."""


class EmbeddingGenerationError(RuntimeError):
    """Raised when an embedding request fails after readiness checks pass."""


def _resolve_embedding_api_key(api_key: str | None = None) -> str:
    return (
        _EMBED_API_KEY
        or os.getenv("OPENAI_API_KEY", "")
        or api_key
        or os.getenv("LLM_API_KEY", "")
    )


def get_embedding_runtime_status(api_key: str | None = None) -> dict[str, Any]:
    """Return the embedding readiness state used by semantic memory endpoints."""
    resolved_key = _resolve_embedding_api_key(api_key)

    if _EMBED_BACKEND == "none":
        return {
            "ready": False,
            "backend": _EMBED_BACKEND,
            "dimensions": EMBED_DIMS,
            "reason": "Semantic embeddings are disabled via EMBED_BACKEND=none.",
        }

    if _EMBED_BACKEND != "openai":
        return {
            "ready": False,
            "backend": _EMBED_BACKEND,
            "dimensions": EMBED_DIMS,
            "reason": (
                "Semantic memory requires EMBED_BACKEND=openai because the current "
                "pgvector schema is provisioned for 1536-dimensional embeddings."
            ),
        }

    if not resolved_key:
        return {
            "ready": False,
            "backend": _EMBED_BACKEND,
            "dimensions": EMBED_DIMS,
            "reason": (
                "No embedding API key is configured. Set EMBED_API_KEY or OPENAI_API_KEY "
                "to enable semantic memory."
            ),
        }

    return {
        "ready": True,
        "backend": _EMBED_BACKEND,
        "dimensions": EMBED_DIMS,
        "reason": None,
    }


def assert_embedding_ready(api_key: str | None = None) -> str:
    """Return a usable embedding API key or raise a fail-closed runtime error."""
    status = get_embedding_runtime_status(api_key)
    if not status["ready"]:
        raise EmbeddingUnavailableError(str(status["reason"]))
    return _resolve_embedding_api_key(api_key)


def _get_admin_client():
    from src.db import get_admin_client

    return get_admin_client()


def _get_user_client(access_token: str | None = None):
    from src.db import get_client

    return get_client(access_token)


def _embed_text(text: str, api_key: str | None = None) -> list[float]:
    """Generate a semantic embedding for *text* or raise a fail-closed error."""
    resolved_key = assert_embedding_ready(api_key)

    try:
        from openai import OpenAI  # type: ignore
    except ImportError as exc:
        raise EmbeddingUnavailableError(
            "The OpenAI SDK is not installed, so semantic memory cannot generate embeddings."
        ) from exc

    try:
        client = OpenAI(api_key=resolved_key)
        response = client.embeddings.create(
            model=_OPENAI_EMBED_MODEL,
            input=text,
            encoding_format="float",
        )
        embedding = response.data[0].embedding
    except Exception as exc:
        logger.error("Embedding generation failed (%s): %s", _EMBED_BACKEND, exc)
        raise EmbeddingGenerationError("Embedding generation failed.") from exc

    if len(embedding) != EMBED_DIMS:
        raise EmbeddingGenerationError(
            f"Embedding dimension mismatch: expected {EMBED_DIMS}, received {len(embedding)}."
        )

    return embedding


def _report_to_text(report: dict[str, Any]) -> str:
    """Flatten a structured report dict into a single indexable text blob."""
    parts: list[str] = []

    parts.append(f"Anomaly date: {report.get('anomaly_date', 'N/A')}")
    parts.append(f"Primary metric: {report.get('primary_metric', 'N/A')}")

    for a in report.get("anomaly_summary", []):
        parts.append(
            f"Anomaly - {a['metric']} {a['direction']} on {a['date']}: "
            f"observed {a['observed']:.2f} vs expected {a['expected']:.2f} "
            f"(z-score {a['z_score']:.2f})"
        )

    for c in report.get("contribution_breakdown", []):
        parts.append(
            f"Factor {c['factor']} changed {c['pct_change']:.1f}%, "
            f"contributing {c['contribution_pct']:.1f}% of the decline."
        )

    for dim, records in report.get("segment_impact", {}).items():
        if records:
            top = records[0]
            parts.append(
                f"Worst {dim} segment: '{top.get(dim, '?')}' "
                f"({top.get('relative_change_pct', 0):.1f}% vs baseline)"
            )

    for h in report.get("hypotheses", []):
        parts.append(f"Likely driver [{h['id']}]: {h['title']} - {h['description']}")

    for action in report.get("recommended_actions", []):
        parts.append(f"Action: {action}")

    return "\n".join(parts)


def _make_doc_id(user_id: str, report: dict[str, Any]) -> str:
    """Generate a stable, tenant-scoped document ID."""
    key = f"{report.get('anomaly_date', '')}_{report.get('primary_metric', '')}"
    content_hash = hashlib.md5(key.encode()).hexdigest()[:16]
    uid_prefix = user_id.replace("-", "")[:12]
    return f"{uid_prefix}_{content_hash}"


def index_report(
    report: dict[str, Any],
    user_id: str,
    executive_summary: str = "",
    report_id: str | None = None,
    api_key: str | None = None,
) -> str:
    """Add a single report to the pgvector index for a specific tenant."""
    if not user_id:
        raise ValueError("user_id is required for semantic indexing.")

    doc_id = _make_doc_id(user_id, report)
    doc_text = _report_to_text(report)
    if executive_summary:
        doc_text = executive_summary + "\n\n" + doc_text

    metadata = {
        "user_id": user_id,
        "anomaly_date": str(report.get("anomaly_date", "")),
        "primary_metric": str(report.get("primary_metric", "")),
        "generated_at": str(report.get("generated_at", "")),
        "n_hypotheses": len(report.get("hypotheses", [])),
    }

    embedding = _embed_text(doc_text, api_key=api_key)

    from src.db import _impersonate_user

    client = _get_admin_client()
    _impersonate_user(client, user_id)

    row = {
        "user_id": user_id,
        "report_id": report_id,
        "doc_id": doc_id,
        "document": doc_text,
        "metadata": metadata,
        "embedding": embedding,
    }

    client.table(_TABLE).upsert(row, on_conflict="user_id,doc_id").execute()

    logger.info(
        "Indexed report '%s' for user=%s (date=%s) via pgvector.",
        doc_id,
        user_id,
        metadata["anomaly_date"],
    )
    return doc_id


def index_reports_bulk(
    reports: list[tuple[dict[str, Any], str, str]],
    api_key: str | None = None,
) -> list[str]:
    """Index multiple reports at once."""
    return [index_report(r, uid, summary, api_key=api_key) for r, uid, summary in reports]


def list_indexed_reports(
    user_id: str,
    access_token: str | None = None,
) -> list[dict]:
    """Return metadata for all indexed reports belonging to *user_id*."""
    if not user_id:
        raise ValueError("user_id is required to list indexed reports.")

    client = _get_user_client(access_token)
    result = (
        client.table(_TABLE)
        .select("doc_id, metadata, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )

    rows = []
    for row in (result.data or []):
        meta = row.get("metadata") or {}
        rows.append(
            {
                "id": row.get("doc_id", ""),
                "anomaly_date": meta.get("anomaly_date"),
                "primary_metric": meta.get("primary_metric"),
                "generated_at": meta.get("generated_at"),
                "n_hypotheses": meta.get("n_hypotheses"),
                "user_id": meta.get("user_id", user_id),
            }
        )
    return rows


def clear_user_index(
    user_id: str,
    access_token: str | None = None,
) -> int:
    """Delete all embedding documents belonging to *user_id*."""
    if not user_id:
        raise ValueError("user_id is required to clear indexed reports.")

    client = _get_user_client(access_token)
    result = client.table(_TABLE).delete().eq("user_id", user_id).execute()
    deleted = len(result.data or [])
    logger.info("pgvector index cleared for user=%s (%d documents removed).", user_id, deleted)
    return deleted
