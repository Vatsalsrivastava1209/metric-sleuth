from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator
import re

# Shared allowlist for metric field validation (mirrors analyze.py).
# Allows alphanumeric, underscore, and hyphen: 'revenue', 'conv_rate-v2', etc.
_METRIC_RE = re.compile(r'^[a-zA-Z0-9_\-]{1,100}$')

# Common standard responses
class ErrorResponse(BaseModel):
    detail: str

class HealthResponse(BaseModel):
    status: str
    message: str

# Analysis request/response models
class AnalyzeRequest(BaseModel):
    dataset_id: str | None = Field(default=None, description="Optional dataset ID if analyzing pre-loaded data")
    metric: str = Field(..., description="The primary metric to analyze (e.g., 'revenue')")
    storage_key: str | None = Field(default=None, description="Supabase storage key for the dataset payload")
    job_id: str | None = Field(default=None, description="Optional caller-provided job UUID")
    # NOTE: No access_token field. JWTs are never passed to Celery workers.
    # Background tasks use service-role + session impersonation (_impersonate_user)
    # for durable, non-expiring, per-user RLS enforcement. See src/db.py.

    @field_validator("storage_key")
    @classmethod
    def _validate_storage_key(cls, v: str | None) -> str | None:
        if v is not None:
            if ".." in v:
                raise ValueError("storage_key cannot contain directory traversal characters ('..').")
            # We enforce that the storage_key is reasonable in length.
            if len(v) > 255:
                raise ValueError("storage_key must be 255 characters or fewer.")
            lowered = v.lower()
            if not lowered.endswith((".csv", ".json", ".parquet")):
                raise ValueError("storage_key must reference a csv, json, or parquet object.")
        return v

    @field_validator("metric")
    @classmethod
    def _validate_metric(cls, v: str) -> str:
        if not _METRIC_RE.match(v):
            raise ValueError(
                "Invalid 'metric' value. Must be 1–100 characters, "
                "containing only letters, digits, underscores, or hyphens "
                "(e.g. 'revenue', 'conv_rate-v2')."
            )
        return v

    @field_validator("dataset_id")
    @classmethod
    def _validate_dataset_id(cls, v: str | None) -> str | None:
        if v and not re.match(r"^[a-zA-Z0-9_\-]{1,200}$", v):
            raise ValueError(
                "Invalid 'dataset_id' value. Must be 1–200 characters, "
                "containing only letters, digits, underscores, or hyphens."
            )
        return v
        
    @classmethod
    def as_form(
        cls,
        metric: str = __import__('fastapi').Form(...),
        dataset_id: str = __import__('fastapi').Form(None),
        storage_key: str = __import__('fastapi').Form(None),
        job_id: str = __import__('fastapi').Form(None),
    ):
        return cls(metric=metric, dataset_id=dataset_id, storage_key=storage_key, job_id=job_id)

class AnalyzeResponse(BaseModel):
    job_id: str = Field(..., description="The Celery Task ID to poll for status")
    message: str

class JobStatusResponse(BaseModel):
    job_id: str
    state: str
    meta: dict | None = None


class DatasetSummary(BaseModel):
    id: str
    name: str
    connector_type: str
    row_count: int | None = None
    created_at: str | None = None


class DatasetPreviewResponse(BaseModel):
    columns: list[str]
    row_count: int
    suggested_mapping: dict[str, str]
    validation_errors: list[str]
    preview_rows: list[dict]


class DatasetCreateResponse(BaseModel):
    dataset_id: str
    name: str
    row_count: int
    message: str


class DatasetListResponse(BaseModel):
    datasets: list[DatasetSummary]


class DatasetDeleteResponse(BaseModel):
    status: str
    message: str


class DatasetTemplate(BaseModel):
    id: str
    label: str
    description: str
    connectors: list[str]
    metrics: list[str]
    recommended_for: str


class IntegrationCatalogItem(BaseModel):
    id: str
    label: str
    status: str
    summary: str


class DatasetTemplateListResponse(BaseModel):
    templates: list[DatasetTemplate]
    integrations: list[IntegrationCatalogItem]


class DemoDatasetResponse(BaseModel):
    dataset_id: str
    name: str
    row_count: int
    message: str


class IntegrationWorkspaceRequest(BaseModel):
    provider: str = Field(..., description="shopify, ga4, meta_ads, google_ads, or klaviyo")
    workspace_name: str = Field(..., min_length=1, max_length=200)
    credentials: dict[str, Any] = Field(default_factory=dict)
    lookback_days: int = Field(default=90, ge=7, le=365)
    metric_id: str | None = None

    @field_validator("provider")
    @classmethod
    def _validate_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"shopify", "ga4", "meta_ads", "google_ads", "klaviyo"}:
            raise ValueError("provider must be one of: shopify, ga4, meta_ads, google_ads, klaviyo.")
        return normalized


class IntegrationTestResponse(BaseModel):
    status: str
    message: str
    columns: list[str] = Field(default_factory=list)
    preview_rows: list[dict] = Field(default_factory=list)


class IntegrationWorkspaceResponse(BaseModel):
    dataset_id: str
    name: str
    connector_type: str
    row_count: int
    message: str


class ProfileResponse(BaseModel):
    id: str
    email: str | None = None
    agency_name: str = ""
    subscription_tier: str = "free"
    llm_backend: str = "gemini"
    llm_api_key_configured: bool = False
    slack_webhook_url: str = ""
    alert_email: str = ""
    stripe_customer_id: str = ""


class ProfileUpdateRequest(BaseModel):
    agency_name: str | None = None
    llm_backend: str | None = None
    llm_api_key: str | None = None
    slack_webhook_url: str | None = None
    alert_email: str | None = None

    @field_validator("agency_name")
    @classmethod
    def _validate_agency_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        trimmed = value.strip()
        if not trimmed:
            return ""
        if len(trimmed) > 120:
            raise ValueError("agency_name must be 120 characters or fewer.")
        return trimmed

    @field_validator("llm_backend")
    @classmethod
    def _validate_backend(cls, value: str | None) -> str | None:
        if value is None:
            return value
        lowered = value.lower().strip()
        if lowered not in {"gemini", "openai"}:
            raise ValueError("llm_backend must be either 'gemini' or 'openai'.")
        return lowered

    @field_validator("alert_email")
    @classmethod
    def _validate_email(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return value
        if "@" not in value or "." not in value.split("@")[-1]:
            raise ValueError("alert_email must look like a valid email address.")
        return value.strip()

    @field_validator("slack_webhook_url")
    @classmethod
    def _validate_slack_url(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return value
        if not value.startswith("https://hooks.slack.com/"):
            raise ValueError("slack_webhook_url must be a Slack incoming webhook URL.")
        return value.strip()


class ProfileUpdateResponse(BaseModel):
    status: str
    message: str


class ReportWorkflowUpdateRequest(BaseModel):
    workflow_status: str | None = None
    assigned_owner: str | None = None
    internal_notes: str | None = None

    @field_validator("workflow_status")
    @classmethod
    def _validate_workflow_status(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().lower()
        if normalized not in {"new", "investigating", "ready_to_send", "sent"}:
            raise ValueError("workflow_status must be one of: new, investigating, ready_to_send, sent.")
        return normalized

    @field_validator("assigned_owner")
    @classmethod
    def _validate_assigned_owner(cls, value: str | None) -> str | None:
        if value is None:
            return value
        trimmed = value.strip()
        if not trimmed:
            return ""
        if len(trimmed) > 120:
            raise ValueError("assigned_owner must be 120 characters or fewer.")
        return trimmed

    @field_validator("internal_notes")
    @classmethod
    def _validate_internal_notes(cls, value: str | None) -> str | None:
        if value is None:
            return value
        trimmed = value.strip()
        if len(trimmed) > 5000:
            raise ValueError("internal_notes must be 5000 characters or fewer.")
        return trimmed


class ReportCommentCreateRequest(BaseModel):
    body: str = Field(..., min_length=2, max_length=2000)


class ReportCommentResponse(BaseModel):
    id: str
    author_email: str | None = None
    body: str
    created_at: str | None = None


class ReportCommentListResponse(BaseModel):
    comments: list[ReportCommentResponse]


class ReportWorkflowResponse(BaseModel):
    id: str
    workflow_status: str
    assigned_owner: str = ""
    internal_notes: str = ""
    share_token: str | None = None
    last_client_delivery_at: str | None = None
    delivery_channel: str | None = None
    feedback_rating: int | None = None
    feedback_notes: str | None = None


class ReportShareResponse(BaseModel):
    share_token: str
    public_path: str


class ReportDeliveryRequest(BaseModel):
    brand_name: str | None = None

    @field_validator("brand_name")
    @classmethod
    def _validate_brand_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        trimmed = value.strip()
        if len(trimmed) > 120:
            raise ValueError("brand_name must be 120 characters or fewer.")
        return trimmed


class ReportDeliveryResponse(BaseModel):
    status: str
    message: str


class ReportFeedbackRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    notes: str | None = Field(default=None, max_length=1000)


class ReportOpsSummaryResponse(BaseModel):
    median_minutes_to_brief: float
    briefs_delivered_last_30d: int
    ready_to_send_count: int
    failed_runs_last_14d: int
    stuck_runs: int


class PublicBriefResponse(BaseModel):
    agency_name: str
    workspace_name: str
    anomaly_date: str
    primary_metric: str
    executive_summary: str
    likely_driver: str
    evidence: list[str]
    report_id: str


class CheckoutRequest(BaseModel):
    tier: str = Field(..., description="Requested subscription tier.")
    success_url: str = Field(..., description="Absolute URL to redirect to on success.")
    cancel_url: str = Field(..., description="Absolute URL to redirect to on cancellation.")

    @field_validator("tier")
    @classmethod
    def _validate_tier(cls, value: str) -> str:
        lowered = value.lower().strip()
        if lowered not in {"pro", "business"}:
            raise ValueError("tier must be 'pro' or 'business'.")
        return lowered

    @field_validator("success_url", "cancel_url")
    @classmethod
    def _validate_return_urls(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("Return URLs must be absolute http(s) URLs.")
        return value


class CheckoutResponse(BaseModel):
    checkout_url: str


class PortalRequest(BaseModel):
    return_url: str

    @field_validator("return_url")
    @classmethod
    def _validate_return_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("return_url must be an absolute http(s) URL.")
        return value


class PortalResponse(BaseModel):
    portal_url: str


class MemoryQueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000)


class MemorySource(BaseModel):
    anomaly_date: str | None = None
    primary_metric: str | None = None
    generated_at: str | None = None
    n_hypotheses: int | None = None
    user_id: str | None = None


class MemoryQueryResponse(BaseModel):
    answer: str
    sources: list[MemorySource] = Field(default_factory=list)


class MemoryStatsResponse(BaseModel):
    total_documents: int
    index_dir: str
    is_empty: bool
    error: str | None = None


class IndexedReportResponse(BaseModel):
    id: str
    anomaly_date: str | None = None
    primary_metric: str | None = None
    generated_at: str | None = None
    n_hypotheses: int | None = None
    user_id: str | None = None


class IndexedReportListResponse(BaseModel):
    reports: list[IndexedReportResponse]

# ── M2M Ingestion schemas ────────────────────────────────────────────

class IngestRecord(BaseModel):
    """A single time-series record in an M2M ingestion payload.

    The `date` field is required and must be an ISO 8601 date string
    (YYYY-MM-DD). All other fields are metric/dimension values that
    are application-defined — `extra = "allow"` permits them to pass
    through without explicit enumeration.

    Pydantic will reject records missing the `date` field entirely,
    which prevents malformed payloads from entering the pipeline.
    """
    date: str = Field(
        ...,
        description="ISO 8601 date string (YYYY-MM-DD)",
        min_length=8,
        max_length=32,
    )

    model_config = {"extra": "allow"}

    @field_validator("date")
    @classmethod
    def _validate_date_format(cls, v: str) -> str:
        """Reject obviously invalid date strings before they reach Pandas."""
        import re as _re
        # Accept YYYY-MM-DD with optional time component (ISO 8601 subset)
        if not _re.match(r'^\d{4}-\d{2}-\d{2}', v):
            raise ValueError(
                f"Invalid date format '{v}'. Expected ISO 8601 (YYYY-MM-DD)."
            )
        return v

    @model_validator(mode="before")
    @classmethod
    def _truncate_large_fields(cls, data: Any) -> Any:
        """Prevent dictionary bombing and deep nesting RAM spikes."""
        if not isinstance(data, dict):
            return data

        # Limit sprawling keys in a single telemetry row
        if len(data) > 50:
            raise ValueError("Too many fields in a single record (max 50).")

        validated = {}
        for k, v in data.items():
            if k == "date":
                validated[k] = v
                continue

            # Prevent megabyte-length strings from consuming RAM
            if isinstance(v, str):
                validated[k] = v[:1000]
            # Deeply nested objects consume heavy parsing loops and aren't supported
            # by the pandas flatten pipeline anyway. Fail them early.
            elif isinstance(v, (dict, list)):
                raise ValueError(f"Nested objects/arrays not permitted in time-series telemetry (field: '{k}').")
            else:
                validated[k] = v
        return validated


class IngestRequest(BaseModel):
    """M2M ingestion payload from Airflow, Fivetran, and similar pipelines.

    IMPORTANT: `records` is now typed as `list[IngestRecord]` (not `list[dict]`).
    Previously this field bypassed Pydantic validation entirely because it used
    the raw `dict` type — malformed or malicious payloads could propagate to
    the Celery pipeline unchanged.

    Now every record is validated: the `date` field is required and format-checked,
    and extra fields are allowed but cleanly passed through as a typed IngestRecord.
    """
    dataset_name: str = Field(
        ...,
        description="Target dataset to append to or create",
        min_length=1,
        max_length=200,
    )
    metric: str = Field(
        ...,
        description="Primary metric column name for the RCA analyzer to track",
    )
    records: list[IngestRecord] = Field(
        ...,
        description="JSON array of time-series data (each record must contain 'date')",
        min_length=1,
    )

    @field_validator("metric")
    @classmethod
    def _validate_metric(cls, v: str) -> str:
        if not _METRIC_RE.match(v):
            raise ValueError(
                "metric must be 1–100 characters, containing only letters, "
                "digits, underscores, or hyphens."
            )
        return v


class IngestResponse(BaseModel):
    status: str
    message: str
    job_id: str | None = None


class IngestSignedUrlResponse(BaseModel):
    upload_url: str
    storage_key: str
    job_id: str


class IngestStagedRequest(BaseModel):
    dataset_name: str = Field(..., min_length=1, max_length=200)
    metric: str = Field(..., description="Primary metric column name for the investigation pipeline")
    storage_key: str = Field(..., min_length=3, max_length=255)
    file_format: str = Field(..., description="One of csv, split, records, parquet")
    job_id: str | None = Field(default=None, description="Optional caller-provided job UUID")

    @field_validator("metric")
    @classmethod
    def _validate_staged_metric(cls, v: str) -> str:
        if not _METRIC_RE.match(v):
            raise ValueError(
                "metric must be 1-100 characters, containing only letters, digits, underscores, or hyphens."
            )
        return v

    @field_validator("file_format")
    @classmethod
    def _validate_file_format(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"csv", "split", "records", "parquet"}:
            raise ValueError("file_format must be one of: csv, split, records, parquet.")
        return normalized
