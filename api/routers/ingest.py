"""
M2M ingestion endpoints for automated pipelines.

Large payloads should use the staged workflow:
1. Request a signed upload URL.
2. Upload the object directly to shared storage.
3. Submit a staged manifest referencing the storage key.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, status

from api.dependencies import get_api_key_user
from api.routers.analyze import check_rate_limit
from api.schemas import (
    IngestRequest,
    IngestResponse,
    IngestSignedUrlResponse,
    IngestStagedRequest,
)
from api.tasks import run_rca_pipeline
from src.db import create_analysis_run, update_analysis_run
from utils.config import MAX_INLINE_INGEST_RECORDS

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])
logger = logging.getLogger(__name__)

STORAGE_BUCKET = "temp-processing"


def _stage_bytes_to_storage(storage_key: str, file_bytes: bytes, content_type: str) -> None:
    from src.db import get_admin_client

    client = get_admin_client()
    client.storage.from_(STORAGE_BUCKET).upload(
        path=storage_key,
        file=file_bytes,
        file_options={"content-type": content_type, "upsert": "true"},
    )


@router.post("/signed-url", response_model=IngestSignedUrlResponse)
async def create_ingest_signed_upload_url(
    filename: str = Form(...),
    current_user: Annotated[dict, Depends(get_api_key_user)] = None,
) -> IngestSignedUrlResponse:
    user_id = current_user["user_id"]
    await check_rate_limit(user_id)

    job_id = str(uuid.uuid4())
    lowered = filename.lower()
    if lowered.endswith(".json"):
        ext = ".json"
    elif lowered.endswith(".parquet"):
        ext = ".parquet"
    else:
        ext = ".csv"
    storage_key = f"{user_id}/{job_id}{ext}"

    from api.dependencies import get_admin_client

    client = get_admin_client()
    try:
        res = client.storage.from_(STORAGE_BUCKET).create_signed_upload_url(storage_key)
        upload_url = res["signedUrl"]
    except Exception as exc:
        logger.error("Failed to generate M2M signed upload URL for user=%s: %s", user_id, exc)
        raise HTTPException(status_code=502, detail="Failed to generate secure upload token.") from exc

    return IngestSignedUrlResponse(upload_url=upload_url, storage_key=storage_key, job_id=job_id)


@router.post("/staged", response_model=IngestResponse, status_code=202)
async def staged_ingestion(
    payload: IngestStagedRequest,
    current_user: Annotated[dict, Depends(get_api_key_user)],
) -> IngestResponse:
    user_id = current_user["user_id"]
    await check_rate_limit(user_id)

    if not payload.storage_key.startswith(f"{user_id}/"):
        raise HTTPException(status_code=403, detail="You are not authorized to process this staged object.")

    job_id = payload.job_id or str(uuid.uuid4())
    created = await asyncio.to_thread(
        create_analysis_run,
        job_id,
        user_id,
        payload.metric,
        payload.dataset_name,
        payload.storage_key,
        "m2m_staged",
        None,
    )
    if not created:
        raise HTTPException(status_code=500, detail="Could not persist the staged analysis run.")

    try:
        run_rca_pipeline.apply_async(
            args=[
                payload.storage_key,
                payload.metric,
                user_id,
                payload.dataset_name,
                payload.file_format,
                "",
                "gemini",
                True,
            ],
            task_id=job_id,
        )
    except Exception as exc:
        logger.error("Failed to enqueue staged ingestion run=%s user=%s: %s", job_id, user_id, exc)
        await asyncio.to_thread(
            update_analysis_run,
            job_id,
            user_id,
            "FAILURE",
            "Failed to enqueue the staged ingestion run.",
            {"stage": "queue"},
            str(exc),
            None,
        )
        raise HTTPException(status_code=502, detail="Failed to enqueue the staged ingestion run.") from exc

    return IngestResponse(
        status="Accepted",
        message="Staged payload queued for analysis. Poll /api/v1/analyze/jobs/{job_id} for progress.",
        job_id=job_id,
    )


@router.post("/", response_model=IngestResponse, status_code=202)
async def external_telemetry_ingestion(
    payload: IngestRequest,
    current_user: Annotated[dict, Depends(get_api_key_user)],
) -> IngestResponse:
    user_id = current_user["user_id"]
    await check_rate_limit(user_id)

    if len(payload.records) > MAX_INLINE_INGEST_RECORDS:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"Inline JSON ingestion is capped at {MAX_INLINE_INGEST_RECORDS:,} records. "
                "Use /api/v1/ingest/signed-url plus /api/v1/ingest/staged for larger datasets."
            ),
        )

    job_id = str(uuid.uuid4())
    storage_key = f"{user_id}/{job_id}.json"
    file_bytes = json.dumps([r.model_dump() for r in payload.records], ensure_ascii=False).encode("utf-8")

    try:
        await asyncio.to_thread(_stage_bytes_to_storage, storage_key, file_bytes, "application/json")
    except Exception as exc:
        logger.error("Failed to upload M2M payload to storage for user=%s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to stage payload in cloud storage. Please retry.",
        ) from exc

    created = await asyncio.to_thread(
        create_analysis_run,
        job_id,
        user_id,
        payload.metric,
        payload.dataset_name,
        storage_key,
        "m2m_inline",
        None,
    )
    if not created:
        raise HTTPException(status_code=500, detail="Could not persist the inline analysis run.")

    try:
        run_rca_pipeline.apply_async(
            args=[
                storage_key,
                payload.metric,
                user_id,
                payload.dataset_name,
                "records",
                "",
                "gemini",
                True,
            ],
            task_id=job_id,
        )
    except Exception as exc:
        await asyncio.to_thread(
            update_analysis_run,
            job_id,
            user_id,
            "FAILURE",
            "Failed to enqueue the inline ingestion run.",
            {"stage": "queue"},
            str(exc),
            None,
        )
        raise HTTPException(status_code=502, detail="Failed to enqueue the inline ingestion run.") from exc

    logger.info("Inline M2M job queued: job_id=%s user=%s metric=%s", job_id, user_id, payload.metric)
    return IngestResponse(
        status="Accepted",
        message=(
            "Inline M2M payload staged and queued for analysis. "
            f"Poll /api/v1/analyze/jobs/{job_id} for progress."
        ),
        job_id=job_id,
    )
