"""
api/routers/datasets.py
=======================
Dataset-management API for the Next.js application.

Provides:
  - CSV/Excel preview for schema mapping
  - Durable dataset persistence to Supabase Storage
  - Authenticated dataset listing and deletion
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
from pathlib import Path
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from api.dependencies import get_current_user
from api.schemas import (
    DatasetCreateResponse,
    DatasetDeleteResponse,
    DatasetListResponse,
    DatasetPreviewResponse,
    DatasetSummary,
    DatasetTemplate,
    DatasetTemplateListResponse,
    DemoDatasetResponse,
    IntegrationTestResponse,
    IntegrationWorkspaceRequest,
    IntegrationWorkspaceResponse,
    IntegrationCatalogItem,
)
from src.db import (
    USER_DATASET_BUCKET,
    delete_dataset,
    delete_user_dataset_object,
    get_user_datasets,
    save_dataset_meta,
    upload_user_dataset_bytes,
)
from src.schema_mapper import apply_mapping, suggest_mapping, validate_mapping
from src.connectors import get_connector
from utils.config import MAX_UPLOAD_SIZE_BYTES

router = APIRouter(prefix="/api/v1/datasets", tags=["datasets"])
logger = logging.getLogger(__name__)

MAX_DATASET_FILE_SIZE_BYTES = MAX_UPLOAD_SIZE_BYTES
ALLOWED_SUFFIXES = {".csv", ".xls", ".xlsx"}
REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_DATASET_PATH = REPO_ROOT / "data" / "sample_ecommerce.csv"
DEMO_DATASET_MAPPING = {
    "date": "date",
    "revenue": "revenue",
    "traffic": "traffic",
    "orders": "orders",
    "conversion_rate": "conversion_rate",
    "region": "region",
    "device": "device",
    "traffic_source": "traffic_source",
}
AGENCY_TEMPLATES = [
    DatasetTemplate(
        id="shopify-plus-daily",
        label="Shopify daily health check",
        description="Track storefront revenue, orders, traffic, and conversion for one client workspace.",
        connectors=["Shopify", "GA4"],
        metrics=["revenue", "orders", "traffic", "conversion_rate"],
        recommended_for="DTC brand account managers",
    ),
    DatasetTemplate(
        id="paid-media-recovery",
        label="Paid media pacing triage",
        description="Map spend, sessions, orders, and revenue for fast campaign incident reviews.",
        connectors=["Meta Ads", "Google Ads", "GA4"],
        metrics=["spend", "traffic", "orders", "revenue"],
        recommended_for="Performance marketing teams",
    ),
    DatasetTemplate(
        id="email-retention-watch",
        label="Retention and email signal watch",
        description="Monitor repeat-purchase, campaign revenue, and audience engagement across lifecycle channels.",
        connectors=["Klaviyo", "Shopify"],
        metrics=["revenue", "orders", "conversion_rate", "email_clicks"],
        recommended_for="Lifecycle and CRM operators",
    ),
]
INTEGRATION_CATALOG = [
    IntegrationCatalogItem(
        id="shopify",
        label="Shopify",
        status="Token connection supported",
        summary="Connect with a Shopify custom-app Admin API token. OAuth app installation is still a later hardening step.",
    ),
    IntegrationCatalogItem(
        id="ga4",
        label="GA4",
        status="Token connection supported",
        summary="Connect with a GA4 Data API OAuth access token and property ID for daily KPI pulls.",
    ),
    IntegrationCatalogItem(
        id="meta_ads",
        label="Meta Ads",
        status="Token connection supported",
        summary="Connect with a Meta Ads long-lived/system-user token and ad account ID for daily insights.",
    ),
    IntegrationCatalogItem(
        id="google_ads",
        label="Google Ads",
        status="Token connection supported",
        summary="Connect with an OAuth access token, developer token, and customer ID for Google Ads API reporting.",
    ),
    IntegrationCatalogItem(
        id="klaviyo",
        label="Klaviyo",
        status="Token connection supported",
        summary="Connect with a Klaviyo private key and metric ID for daily lifecycle aggregate pulls.",
    ),
]
INTEGRATION_REQUIRED_FIELDS = {
    "shopify": ["shop_domain", "access_token"],
    "ga4": ["property_id", "access_token"],
    "meta_ads": ["ad_account_id", "access_token"],
    "google_ads": ["customer_id", "access_token", "developer_token"],
    "klaviyo": ["private_key"],
}


def _validate_filename(filename: str | None) -> str:
    if not filename:
        raise HTTPException(status_code=422, detail="A dataset filename is required.")

    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=422,
            detail="Only CSV and Excel files are supported for saved datasets.",
        )
    return suffix


def _read_tabular_bytes(file_bytes: bytes, suffix: str) -> pd.DataFrame:
    if suffix in {".xls", ".xlsx"}:
        return pd.read_excel(io.BytesIO(file_bytes))
    return pd.read_csv(io.BytesIO(file_bytes))


def _serialize_preview_rows(df: pd.DataFrame, limit: int = 5) -> list[dict]:
    preview = df.head(limit).copy()
    preview = preview.where(pd.notnull(preview), None)
    preview = preview.astype(object)
    rows: list[dict] = []
    for row in preview.to_dict(orient="records"):
        normalized: dict[str, object] = {}
        for key, value in row.items():
            if isinstance(value, pd.Timestamp):
                normalized[key] = value.isoformat()
            else:
                normalized[key] = value
        rows.append(normalized)
    return rows


def _integration_config(payload: IntegrationWorkspaceRequest, require_metric_id: bool = False) -> dict:
    credentials = dict(payload.credentials or {})
    missing = [
        field
        for field in INTEGRATION_REQUIRED_FIELDS[payload.provider]
        if not str(credentials.get(field) or "").strip()
    ]
    if payload.provider == "klaviyo" and require_metric_id and not payload.metric_id:
        missing.append("metric_id")
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required {payload.provider} field(s): {', '.join(missing)}.",
        )
    credentials["lookback_days"] = payload.lookback_days
    credentials["connector_type"] = payload.provider
    credentials["query"] = "daily_metrics"
    if payload.metric_id:
        credentials["metric_id"] = payload.metric_id
    return credentials


def _connect_integration(provider: str, config: dict):
    connector = get_connector(provider)
    connect_kwargs = {k: v for k, v in config.items() if k not in {"query", "connector_type"}}
    ok, message = connector.connect(**connect_kwargs)
    if not ok:
        raise HTTPException(status_code=422, detail=message)
    return connector


async def _read_upload_bytes(file_payload: UploadFile) -> tuple[bytes, str]:
    suffix = _validate_filename(file_payload.filename)

    # Fast path: if the client sent a Content-Length header, reject before reading.
    # This avoids allocating the full upload buffer just to throw it away.
    content_length = file_payload.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > MAX_DATASET_FILE_SIZE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=(
                        f"Dataset file exceeds the maximum allowed size of "
                        f"{MAX_DATASET_FILE_SIZE_BYTES // (1024 * 1024)} MB."
                    ),
                )
        except ValueError:
            pass  # Malformed Content-Length — proceed and let the read-size check handle it

    file_bytes = await file_payload.read()
    if not file_bytes:
        raise HTTPException(status_code=422, detail="Uploaded dataset file is empty.")
    if len(file_bytes) > MAX_DATASET_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"Dataset file exceeds the maximum allowed size of "
                f"{MAX_DATASET_FILE_SIZE_BYTES // (1024 * 1024)} MB."
            ),
        )
    return file_bytes, suffix



@router.get("/", response_model=DatasetListResponse)
async def list_datasets(
    current_user: Annotated[dict, Depends(get_current_user)],
) -> DatasetListResponse:
    user_id = current_user["user_id"]
    access_token = current_user["access_token"]
    datasets = await asyncio.to_thread(get_user_datasets, user_id, access_token)
    summaries = [
        DatasetSummary(
            id=row["id"],
            name=row["name"],
            connector_type=row["connector_type"],
            row_count=row.get("row_count"),
            created_at=row.get("created_at"),
        )
        for row in datasets
    ]
    return DatasetListResponse(datasets=summaries)


@router.get("/templates", response_model=DatasetTemplateListResponse)
async def list_templates(
    current_user: Annotated[dict, Depends(get_current_user)],
) -> DatasetTemplateListResponse:
    del current_user
    return DatasetTemplateListResponse(
        templates=AGENCY_TEMPLATES,
        integrations=INTEGRATION_CATALOG,
    )


@router.post("/integrations/test", response_model=IntegrationTestResponse)
async def test_integration_connection(
    payload: IntegrationWorkspaceRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> IntegrationTestResponse:
    del current_user
    config = _integration_config(payload, require_metric_id=False)
    connector = _connect_integration(payload.provider, config)
    ok, message = await asyncio.to_thread(connector.test_connection)
    if not ok:
        raise HTTPException(status_code=422, detail=message)
    return IntegrationTestResponse(status="ok", message=message)


@router.post("/integrations/workspace", response_model=IntegrationWorkspaceResponse, status_code=201)
async def create_integration_workspace(
    payload: IntegrationWorkspaceRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> IntegrationWorkspaceResponse:
    user_id = current_user["user_id"]
    access_token = current_user["access_token"]
    config = _integration_config(payload, require_metric_id=True)
    connector = _connect_integration(payload.provider, config)

    try:
        df_raw = await asyncio.to_thread(connector.fetch_data, "daily_metrics")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Integration sync failed: {exc}") from exc

    if df_raw.empty:
        raise HTTPException(status_code=422, detail="Integration connected, but no rows were returned for the selected lookback window.")

    mapping = {field: field for field in DEMO_DATASET_MAPPING if field in df_raw.columns}
    validation_errors = validate_mapping(mapping, df_raw)
    if validation_errors:
        raise HTTPException(status_code=422, detail="; ".join(validation_errors))

    df_canonical = apply_mapping(df_raw, mapping)
    dataset_id = await asyncio.to_thread(
        save_dataset_meta,
        user_id,
        payload.workspace_name.strip(),
        payload.provider,
        mapping,
        config,
        len(df_canonical),
        access_token,
    )

    if not dataset_id:
        raise HTTPException(status_code=500, detail="Integration synced, but workspace metadata persistence failed.")

    return IntegrationWorkspaceResponse(
        dataset_id=dataset_id,
        name=payload.workspace_name.strip(),
        connector_type=payload.provider,
        row_count=len(df_canonical),
        message="Native integration workspace saved and ready for repeat analysis.",
    )


@router.post("/preview", response_model=DatasetPreviewResponse)
async def preview_dataset(
    file_payload: UploadFile = File(...),
    current_user: Annotated[dict, Depends(get_current_user)] = None,
) -> DatasetPreviewResponse:
    del current_user

    file_bytes, suffix = await _read_upload_bytes(file_payload)
    try:
        df = await asyncio.to_thread(_read_tabular_bytes, file_bytes, suffix)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not parse dataset file: {exc}") from exc

    suggested_mapping = suggest_mapping(df)
    validation_errors = validate_mapping(suggested_mapping, df)
    return DatasetPreviewResponse(
        columns=[str(column) for column in df.columns],
        row_count=len(df),
        suggested_mapping=suggested_mapping,
        validation_errors=validation_errors,
        preview_rows=_serialize_preview_rows(df),
    )


@router.post("/", response_model=DatasetCreateResponse, status_code=201)
async def create_dataset(
    dataset_name: str = Form(...),
    mapping_json: str = Form(...),
    file_payload: UploadFile = File(...),
    current_user: Annotated[dict, Depends(get_current_user)] = None,
) -> DatasetCreateResponse:
    user_id = current_user["user_id"]
    access_token = current_user["access_token"]

    dataset_name = dataset_name.strip()
    if not dataset_name or len(dataset_name) > 200:
        raise HTTPException(
            status_code=422,
            detail="dataset_name must be between 1 and 200 characters.",
        )

    try:
        mapping = json.loads(mapping_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="mapping_json must be valid JSON.") from exc

    if not isinstance(mapping, dict):
        raise HTTPException(status_code=422, detail="mapping_json must be a JSON object.")

    file_bytes, suffix = await _read_upload_bytes(file_payload)

    try:
        df_raw = await asyncio.to_thread(_read_tabular_bytes, file_bytes, suffix)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not parse dataset file: {exc}") from exc

    validation_errors = validate_mapping(mapping, df_raw)
    if validation_errors:
        raise HTTPException(status_code=422, detail="; ".join(validation_errors))

    df_canonical = apply_mapping(df_raw, mapping)
    if df_canonical.empty:
        raise HTTPException(
            status_code=422,
            detail="Dataset mapping produced no usable rows. Check your date and metric columns.",
        )

    file_type = "excel" if suffix in {".xls", ".xlsx"} else "csv"
    content_type = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if file_type == "excel"
        else "text/csv"
    )

    try:
        storage_key = await asyncio.to_thread(
            upload_user_dataset_bytes,
            user_id,
            file_bytes,
            file_payload.filename or "dataset.csv",
            content_type,
        )
    except Exception as exc:
        logger.error("Failed to upload dataset object for user %s: %s", user_id, exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to persist dataset file to secure storage.",
        ) from exc

    dataset_id = await asyncio.to_thread(
        save_dataset_meta,
        user_id,
        dataset_name,
        "csv",
        mapping,
        {
            "storage_key": storage_key,
            "storage_bucket": USER_DATASET_BUCKET,
            "file_type": file_type,
            "original_filename": file_payload.filename or "dataset.csv",
        },
        len(df_canonical),
        access_token,
    )

    if not dataset_id:
        await asyncio.to_thread(delete_user_dataset_object, storage_key)
        raise HTTPException(
            status_code=500,
            detail="Dataset file was stored, but metadata persistence failed.",
        )

    return DatasetCreateResponse(
        dataset_id=dataset_id,
        name=dataset_name,
        row_count=len(df_canonical),
        message="Dataset saved and ready for repeat analysis.",
    )


@router.post("/demo", response_model=DemoDatasetResponse, status_code=201)
async def create_demo_dataset(
    current_user: Annotated[dict, Depends(get_current_user)],
) -> DemoDatasetResponse:
    user_id = current_user["user_id"]
    access_token = current_user["access_token"]

    if not DEMO_DATASET_PATH.exists():
        raise HTTPException(status_code=500, detail="Demo dataset is missing from the repository.")

    file_bytes = await asyncio.to_thread(DEMO_DATASET_PATH.read_bytes)
    try:
        demo_df = await asyncio.to_thread(pd.read_csv, io.BytesIO(file_bytes))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not parse the demo dataset: {exc}") from exc

    try:
        storage_key = await asyncio.to_thread(
            upload_user_dataset_bytes,
            user_id,
            file_bytes,
            "demo-ecommerce-workspace.csv",
            "text/csv",
        )
    except Exception as exc:
        logger.error("Failed to upload demo dataset for %s: %s", user_id, exc)
        raise HTTPException(status_code=502, detail="Could not persist the demo dataset.") from exc

    dataset_id = await asyncio.to_thread(
        save_dataset_meta,
        user_id,
        "Demo | Northstar Outfitters",
        "csv",
        DEMO_DATASET_MAPPING,
        {
            "storage_key": storage_key,
            "storage_bucket": USER_DATASET_BUCKET,
            "file_type": "csv",
            "original_filename": "demo-ecommerce-workspace.csv",
        },
        len(demo_df),
        access_token,
    )

    if not dataset_id:
        await asyncio.to_thread(delete_user_dataset_object, storage_key)
        raise HTTPException(status_code=500, detail="Demo file upload succeeded, but workspace creation failed.")

    return DemoDatasetResponse(
        dataset_id=dataset_id,
        name="Demo | Northstar Outfitters",
        row_count=len(demo_df),
        message="Demo workspace created. Use it to explore the agency workflow before connecting a live client.",
    )


@router.delete("/{dataset_id}", response_model=DatasetDeleteResponse)
async def remove_dataset(
    dataset_id: str,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> DatasetDeleteResponse:
    user_id = current_user["user_id"]
    access_token = current_user["access_token"]
    ok = await asyncio.to_thread(delete_dataset, dataset_id, user_id, access_token)
    if not ok:
        raise HTTPException(status_code=404, detail="Dataset not found or could not be deleted.")
    return DatasetDeleteResponse(status="ok", message="Dataset deleted.")
