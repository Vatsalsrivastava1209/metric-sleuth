"""
Tenant-scoped investigation history and semantic query endpoints for the Next.js UI.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import require_pro_tier
from api.schemas import (
    IndexedReportListResponse,
    IndexedReportResponse,
    MemoryQueryRequest,
    MemoryQueryResponse,
    MemorySource,
    MemoryStatsResponse,
)
from src.db import get_profile
from src.observability import log_event
from src.rag_indexer import (
    EmbeddingGenerationError,
    EmbeddingUnavailableError,
    clear_user_index,
    get_embedding_runtime_status,
    list_indexed_reports,
)
from src.rag_query import get_index_stats, query

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])
logger = logging.getLogger(__name__)


async def _get_memory_profile(current_user: dict) -> tuple[str, str]:
    user_id = current_user["user_id"]
    access_token = current_user["access_token"]
    profile = await asyncio.to_thread(get_profile, user_id, access_token)
    return profile.get("llm_api_key") or "", profile.get("llm_backend") or ""


@router.get("/stats", response_model=MemoryStatsResponse)
async def memory_stats(
    current_user: Annotated[dict, Depends(require_pro_tier)],
) -> MemoryStatsResponse:
    stats = await asyncio.to_thread(
        get_index_stats,
        current_user["user_id"],
        current_user["access_token"],
    )
    api_key, _ = await _get_memory_profile(current_user)
    status = get_embedding_runtime_status(api_key=api_key)
    if not status["ready"]:
        return MemoryStatsResponse(
            total_documents=stats["total_documents"],
            index_dir=stats["index_dir"],
            is_empty=stats["is_empty"],
            error=str(status["reason"]),
        )
    return MemoryStatsResponse(**stats)


@router.get("/reports", response_model=IndexedReportListResponse)
async def indexed_reports(
    current_user: Annotated[dict, Depends(require_pro_tier)],
) -> IndexedReportListResponse:
    report_rows = await asyncio.to_thread(
        list_indexed_reports,
        current_user["user_id"],
        current_user["access_token"],
    )
    reports = [IndexedReportResponse(**row) for row in report_rows]
    return IndexedReportListResponse(reports=reports)


@router.post("/query", response_model=MemoryQueryResponse)
async def query_memory(
    payload: MemoryQueryRequest,
    current_user: Annotated[dict, Depends(require_pro_tier)],
) -> MemoryQueryResponse:
    user_id = current_user["user_id"]
    api_key, backend = await _get_memory_profile(current_user)
    readiness = get_embedding_runtime_status(api_key=api_key)
    if not readiness["ready"]:
        raise HTTPException(status_code=503, detail=str(readiness["reason"]))

    try:
        result = await asyncio.to_thread(
            query,
            payload.question,
            user_id,
            api_key=api_key,
            backend=backend,
        )
    except EmbeddingUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except EmbeddingGenerationError as exc:
        logger.error("Semantic embedding generation failed for user=%s: %s", user_id, exc)
        raise HTTPException(
            status_code=503,
            detail="Semantic memory is temporarily unavailable because embeddings could not be generated.",
        ) from exc
    except Exception as exc:
        logger.error("Memory query failed for user=%s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail="Historical investigation query failed.") from exc

    log_event(logger, "memory.query", user_id=user_id, source_count=len(result.sources))
    return MemoryQueryResponse(
        answer=result.answer,
        sources=[MemorySource(**source) for source in result.sources],
    )


@router.delete("", response_model=dict)
async def clear_memory(
    current_user: Annotated[dict, Depends(require_pro_tier)],
) -> dict[str, str]:
    deleted = await asyncio.to_thread(
        clear_user_index,
        current_user["user_id"],
        current_user["access_token"],
    )
    log_event(
        logger,
        "memory.cleared",
        user_id=current_user["user_id"],
        documents_deleted=deleted,
    )
    return {"status": "ok", "message": f"Cleared {deleted} indexed investigation document(s) from memory."}
