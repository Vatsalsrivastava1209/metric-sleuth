"""
FastAPI router for triggering and polling RCA analysis jobs.

The upload contract is intentionally two-step:
1. The browser asks for a signed upload URL.
2. The browser uploads directly to Supabase Storage.
3. The browser starts analysis with the resulting storage key.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Form, HTTPException
from pydantic import BaseModel

from api.dependencies import get_current_user
from api.schemas import AnalyzeRequest, AnalyzeResponse, JobStatusResponse
from api.tasks import run_rca_pipeline
from src.db import create_analysis_run, get_analysis_run, update_analysis_run
from utils.config import MAX_UPLOAD_SIZE_BYTES, USE_PROPHET

router = APIRouter(prefix="/api/v1/analyze", tags=["analyze"])
logger = logging.getLogger(__name__)

MAX_REQUESTS_PER_MINUTE = 5
MAX_FILE_SIZE_BYTES = MAX_UPLOAD_SIZE_BYTES
_METRIC_ALLOWLIST = re.compile(r"^[a-zA-Z0-9_\-]{1,100}$")
_DATASET_ID_ALLOWLIST = re.compile(r"^[a-zA-Z0-9_\-]{1,200}$")

_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(_REDIS_URL, decode_responses=True)
    return _redis


async def check_rate_limit(user_id: str) -> None:
    redis = _get_redis()
    key = f"ratelimit:analyze:{user_id}"
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 60)
        if count > MAX_REQUESTS_PER_MINUTE:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Rate limit exceeded. Maximum {MAX_REQUESTS_PER_MINUTE} "
                    "analysis jobs per minute per user."
                ),
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Redis rate-limit check failed for user %s (%s). Allowing request.", user_id, exc)


class SignedUrlResponse(BaseModel):
    upload_url: str
    storage_key: str
    job_id: str


_DIRECT_UPLOAD_EXTENSIONS = {
    ".csv": "csv",
    ".json": "split",
    ".parquet": "parquet",
}


@router.post("/signed-url", response_model=SignedUrlResponse)
async def create_signed_upload_url(
    filename: str = Form(...),
    current_user: Annotated[dict, Depends(get_current_user)] = None,
) -> SignedUrlResponse:
    user_id = current_user["user_id"]
    await check_rate_limit(user_id)

    job_id = str(uuid.uuid4())
    lowered = filename.lower()
    ext = next((suffix for suffix in _DIRECT_UPLOAD_EXTENSIONS if lowered.endswith(suffix)), None)
    if ext is None:
        raise HTTPException(
            status_code=422,
            detail="Unsupported upload type. One-off investigations only accept CSV, JSON, or Parquet files.",
        )

    storage_key = f"{user_id}/{job_id}{ext}"
    bucket = "temp-processing"

    from api.dependencies import get_admin_client

    client = get_admin_client()
    try:
        res = client.storage.from_(bucket).create_signed_upload_url(storage_key)
        if not res or "signedUrl" not in res:
            raise ValueError("No signedUrl returned by Supabase SDK")
        upload_url = res["signedUrl"]
    except Exception as exc:
        logger.error("Failed to generate signed upload URL: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to generate secure upload token.") from exc

    return SignedUrlResponse(upload_url=upload_url, storage_key=storage_key, job_id=job_id)


@router.post("/", response_model=AnalyzeResponse)
async def start_analysis(
    request: Annotated[AnalyzeRequest, Depends(AnalyzeRequest.as_form)],
    current_user: Annotated[dict, Depends(get_current_user)] = None,
) -> AnalyzeResponse:
    user_id = current_user["user_id"]
    access_token = current_user["access_token"]
    await check_rate_limit(user_id)

    dataset_id = request.dataset_id
    metric = request.metric
    storage_key = request.storage_key
    job_id = request.job_id or str(uuid.uuid4())

    if not storage_key and not dataset_id:
        raise HTTPException(
            status_code=422,
            detail="Either 'storage_key' or 'dataset_id' must be provided.",
        )

    if storage_key and not storage_key.startswith(f"{user_id}/"):
        logger.warning("IDOR attempt: User %s attempted to access storage key %s", user_id, storage_key)
        raise HTTPException(status_code=403, detail="You are not authorized to process this storage object.")

    source_type = "direct_upload" if storage_key else "saved_dataset"
    created = await asyncio.to_thread(
        create_analysis_run,
        job_id,
        user_id,
        metric,
        dataset_id,
        storage_key,
        source_type,
        access_token,
    )
    if not created:
        raise HTTPException(status_code=500, detail="Could not persist the analysis run before queueing work.")

    orient = "csv"
    if storage_key:
        suffix = next(
            (candidate for candidate in _DIRECT_UPLOAD_EXTENSIONS if storage_key.endswith(candidate)),
            ".csv",
        )
        orient = _DIRECT_UPLOAD_EXTENSIONS[suffix]

    try:
        run_rca_pipeline.apply_async(
            args=[
                storage_key,
                metric,
                user_id,
                dataset_id,
                orient,
                "",
                "gemini",
                USE_PROPHET,
            ],
            task_id=job_id,
        )
    except Exception as exc:
        logger.error("Failed to enqueue analysis run %s for user %s: %s", job_id, user_id, exc)
        await asyncio.to_thread(
            update_analysis_run,
            job_id,
            user_id,
            "FAILURE",
            "Failed to enqueue the analysis run.",
            {"stage": "queue"},
            str(exc),
            None,
        )
        raise HTTPException(status_code=502, detail="Failed to enqueue the analysis run.") from exc

    return AnalyzeResponse(
        job_id=job_id,
        message="Analysis queued. Poll /api/v1/analyze/jobs/{job_id} for status.",
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    current_user: Annotated[dict, Depends(get_current_user)] = None,
) -> JobStatusResponse:
    user_id = current_user["user_id"]
    access_token = current_user["access_token"]

    run_row = await asyncio.to_thread(get_analysis_run, job_id, user_id, access_token)
    if not run_row:
        raise HTTPException(status_code=404, detail="Analysis run not found.")

    meta = dict(run_row.get("progress_meta") or {})
    if run_row.get("status_message"):
        meta["message"] = run_row["status_message"]
    if run_row.get("error_message"):
        meta["error"] = run_row["error_message"]
    if run_row.get("report_id"):
        meta["report_id"] = run_row["report_id"]

    return JobStatusResponse(
        job_id=job_id,
        state=run_row.get("status", "QUEUED"),
        meta=meta,
    )
