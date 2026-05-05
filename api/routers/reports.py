"""
api/routers/reports.py
======================
Agency incident workflow routes for collaboration, delivery, and public briefs.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import get_current_user
from api.schemas import (
    PublicBriefResponse,
    ReportCommentCreateRequest,
    ReportCommentListResponse,
    ReportCommentResponse,
    ReportDeliveryRequest,
    ReportDeliveryResponse,
    ReportFeedbackRequest,
    ReportOpsSummaryResponse,
    ReportShareResponse,
    ReportWorkflowResponse,
    ReportWorkflowUpdateRequest,
)
from src.db import (
    add_report_comment,
    create_report_share_token,
    get_dataset,
    get_profile,
    get_report,
    get_report_comments,
    get_shared_report,
    record_report_delivery,
    record_report_feedback,
    update_report_meta,
)
from src.observability import log_event

router = APIRouter(tags=["reports"])
logger = logging.getLogger(__name__)


def _workflow_response(report: dict[str, Any]) -> ReportWorkflowResponse:
    return ReportWorkflowResponse(
        id=str(report["id"]),
        workflow_status=str(report.get("workflow_status") or "new"),
        assigned_owner=str(report.get("assigned_owner") or ""),
        internal_notes=str(report.get("internal_notes") or ""),
        share_token=report.get("share_token"),
        last_client_delivery_at=report.get("last_client_delivery_at"),
        delivery_channel=report.get("delivery_channel"),
        feedback_rating=report.get("feedback_rating"),
        feedback_notes=report.get("feedback_notes"),
    )


def _comment_response(comment: dict[str, Any]) -> ReportCommentResponse:
    return ReportCommentResponse(
        id=str(comment["id"]),
        author_email=comment.get("author_email"),
        body=str(comment.get("body") or ""),
        created_at=comment.get("created_at"),
    )


def _build_client_brief_payload(
    report: dict[str, Any],
    workspace_name: str,
    agency_name: str,
) -> PublicBriefResponse:
    payload = report.get("report_payload") or {}
    hypotheses = payload.get("hypotheses") or []
    anomaly_summary = payload.get("anomaly_summary") or []
    top_hypothesis = hypotheses[0] if hypotheses else {}
    leading_anomaly = anomaly_summary[0] if anomaly_summary else {}

    evidence: list[str] = [
        f"Confidence: {round(float(report.get('confidence') or 0) * 100)}%",
        f"Supporting anomalies reviewed: {int(report.get('n_anomalies') or 0)}",
        f"Ranked likely drivers reviewed: {int(report.get('n_hypotheses') or 0)}",
    ]
    if leading_anomaly:
        observed = leading_anomaly.get("observed")
        expected = leading_anomaly.get("expected")
        if observed is not None and expected is not None:
            evidence.append(f"Observed vs baseline: {observed} vs {expected}")
    for item in (top_hypothesis.get("supporting_evidence") or [])[:2]:
        evidence.append(str(item))

    return PublicBriefResponse(
        agency_name=agency_name,
        workspace_name=workspace_name,
        anomaly_date=str(report.get("anomaly_date") or ""),
        primary_metric=str(report.get("primary_metric") or "metric"),
        executive_summary=str(
            report.get("executive_summary")
            or "A likely-driver summary was prepared for this incident."
        ),
        likely_driver=str(
            report.get("top_hypothesis")
            or top_hypothesis.get("title")
            or "No single dominant likely driver was recorded."
        ),
        evidence=evidence,
        report_id=str(report.get("id") or ""),
    )


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _build_share_path(token: str) -> str:
    return f"/brief/{token}"


def _load_ops_summary(user_id: str, access_token: str) -> dict[str, float | int]:
    from src.db import get_client

    client = get_client(access_token)
    reports_res = (
        client.table("rca_reports")
        .select("id, workflow_status, last_client_delivery_at, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(200)
        .execute()
    )
    runs_res = (
        client.table("analysis_runs")
        .select("id, status, started_at, completed_at, updated_at, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(200)
        .execute()
    )

    reports = reports_res.data or []
    runs = runs_res.data or []

    durations: list[float] = []
    failed_runs_last_14d = 0
    stuck_runs = 0
    now = _now_utc()
    cutoff_14d = now - timedelta(days=14)
    cutoff_30d = now - timedelta(days=30)

    for run in runs:
        started_at = run.get("started_at")
        completed_at = run.get("completed_at")
        updated_at = run.get("updated_at") or run.get("created_at")

        if started_at and completed_at:
            try:
                started = _parse_datetime(started_at)
                completed = _parse_datetime(completed_at)
                if started and completed:
                    durations.append(max((completed - started).total_seconds() / 60, 0))
            except Exception:
                pass

        updated = _parse_datetime(updated_at) or now

        if run.get("status") == "FAILURE" and updated >= cutoff_14d:
            failed_runs_last_14d += 1
        if run.get("status") == "RUNNING" and updated < now - timedelta(minutes=15):
            stuck_runs += 1

    delivered_last_30d = 0
    ready_to_send_count = 0
    for report in reports:
        if report.get("workflow_status") == "ready_to_send":
            ready_to_send_count += 1
        delivered_at = report.get("last_client_delivery_at")
        delivered_dt = _parse_datetime(delivered_at)
        if delivered_dt and delivered_dt >= cutoff_30d:
            delivered_last_30d += 1

    durations.sort()
    median = 0.0
    if durations:
        midpoint = len(durations) // 2
        if len(durations) % 2 == 0:
            median = round((durations[midpoint - 1] + durations[midpoint]) / 2, 2)
        else:
            median = round(durations[midpoint], 2)

    return {
        "median_minutes_to_brief": median,
        "briefs_delivered_last_30d": delivered_last_30d,
        "ready_to_send_count": ready_to_send_count,
        "failed_runs_last_14d": failed_runs_last_14d,
        "stuck_runs": stuck_runs,
    }


@router.get("/api/v1/reports/ops/summary", response_model=ReportOpsSummaryResponse)
async def report_ops_summary(
    current_user: Annotated[dict, Depends(get_current_user)],
) -> ReportOpsSummaryResponse:
    summary = await asyncio.to_thread(
        _load_ops_summary,
        current_user["user_id"],
        current_user["access_token"],
    )
    return ReportOpsSummaryResponse(**summary)


@router.patch("/api/v1/reports/{report_id}", response_model=ReportWorkflowResponse)
async def update_report_workflow(
    report_id: str,
    payload: ReportWorkflowUpdateRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> ReportWorkflowResponse:
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=422, detail="No report workflow fields were provided.")

    report = await asyncio.to_thread(
        update_report_meta,
        report_id,
        current_user["user_id"],
        updates,
        current_user["access_token"],
    )
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")

    log_event(
        logger,
        "report.workflow_updated",
        user_id=current_user["user_id"],
        report_id=report_id,
        fields=sorted(updates.keys()),
    )
    return _workflow_response(report)


@router.get("/api/v1/reports/{report_id}/comments", response_model=ReportCommentListResponse)
async def list_report_comments(
    report_id: str,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> ReportCommentListResponse:
    comments = await asyncio.to_thread(
        get_report_comments,
        report_id,
        current_user["user_id"],
        current_user["access_token"],
    )
    return ReportCommentListResponse(comments=[_comment_response(comment) for comment in comments])


@router.post("/api/v1/reports/{report_id}/comments", response_model=ReportCommentResponse, status_code=201)
async def create_report_comment(
    report_id: str,
    payload: ReportCommentCreateRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> ReportCommentResponse:
    comment = await asyncio.to_thread(
        add_report_comment,
        report_id,
        current_user["user_id"],
        current_user.get("email") or "",
        payload.body,
        current_user["access_token"],
    )
    if not comment:
        raise HTTPException(status_code=500, detail="Could not persist the internal comment.")

    log_event(logger, "report.comment_created", user_id=current_user["user_id"], report_id=report_id)
    return _comment_response(comment)


@router.post("/api/v1/reports/{report_id}/share-link", response_model=ReportShareResponse)
async def create_share_link(
    report_id: str,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> ReportShareResponse:
    report = await asyncio.to_thread(
        create_report_share_token,
        report_id,
        current_user["user_id"],
        current_user["access_token"],
    )
    if not report or not report.get("share_token"):
        raise HTTPException(status_code=500, detail="Could not create a client brief share link.")

    token = str(report["share_token"])
    log_event(logger, "report.share_link_created", user_id=current_user["user_id"], report_id=report_id)
    return ReportShareResponse(share_token=token, public_path=_build_share_path(token))


@router.post("/api/v1/reports/{report_id}/deliver/slack", response_model=ReportDeliveryResponse)
async def deliver_report_to_slack(
    report_id: str,
    payload: ReportDeliveryRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> ReportDeliveryResponse:
    user_id = current_user["user_id"]
    access_token = current_user["access_token"]
    report = await asyncio.to_thread(get_report, report_id, user_id, access_token)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")

    profile = await asyncio.to_thread(get_profile, user_id, access_token)
    webhook_url = str(profile.get("slack_webhook_url") or "").strip()
    if not webhook_url:
        raise HTTPException(status_code=409, detail="Configure a Slack webhook in Agency Settings before sending briefs.")

    if not report.get("share_token"):
        report = await asyncio.to_thread(create_report_share_token, report_id, user_id, access_token)
        if not report:
            raise HTTPException(status_code=500, detail="Could not prepare a share link for Slack delivery.")

    workspace = None
    if report.get("dataset_id"):
        workspace = await asyncio.to_thread(get_dataset, str(report["dataset_id"]), user_id, access_token)

    brand_name = payload.brand_name or profile.get("full_name") or "Your Agency"
    public_base_url = (
        os.getenv("APP_PUBLIC_URL")
        or os.getenv("FRONTEND_URL")
        or "http://localhost:3000"
    ).rstrip("/")
    share_path = _build_share_path(str(report["share_token"]))
    public_url = f"{public_base_url}{share_path}"
    workspace_name = (workspace or {}).get("name", "Client workspace")
    message = (
        f"*{brand_name}* prepared a client brief for *{workspace_name}*.\n"
        f"Metric: `{report.get('primary_metric')}` on `{report.get('anomaly_date')}`\n"
        f"Likely driver: {report.get('top_hypothesis') or 'Review the internal brief before forwarding.'}\n"
        f"Client brief: {public_url}"
    )

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(webhook_url, json={"text": message})
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Slack rejected the delivery request.")

    await asyncio.to_thread(record_report_delivery, report_id, user_id, "slack", access_token)
    log_event(logger, "report.delivered_slack", user_id=user_id, report_id=report_id)
    return ReportDeliveryResponse(status="ok", message="Client brief delivered to Slack.")


@router.post("/api/v1/reports/{report_id}/feedback", response_model=ReportWorkflowResponse)
async def record_feedback(
    report_id: str,
    payload: ReportFeedbackRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> ReportWorkflowResponse:
    report = await asyncio.to_thread(
        record_report_feedback,
        report_id,
        current_user["user_id"],
        payload.rating,
        payload.notes or "",
        current_user["access_token"],
    )
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")

    log_event(
        logger,
        "report.feedback_recorded",
        user_id=current_user["user_id"],
        report_id=report_id,
        rating=payload.rating,
    )
    return _workflow_response(report)


@router.get("/api/v1/portfolio/summary")
async def portfolio_summary(
    current_user: Annotated[dict, Depends(get_current_user)],
    days: int = 7,
    limit: int = 50,
) -> dict:
    """Return all open incidents across client workspaces ranked by urgency.

    This powers the "Monday Morning Portfolio Review" — one endpoint that gives
    an agency operator a ranked list of all clients needing attention, sorted by
    a composite severity score (deviation magnitude × revenue impact).

    Query params
    ------------
    days:
        How many days back to look for open incidents (default: 7).
    limit:
        Maximum number of incidents to return (default: 50, max: 200).

    Response schema
    ---------------
    {
        "total_open_incidents": int,
        "days_window": int,
        "generated_at": str,           # ISO-8601 UTC
        "incidents": [
            {
                "rank": int,
                "report_id": str,
                "workspace_id": str,
                "workspace_name": str,
                "anomaly_date": str,
                "primary_metric": str,
                "direction": str,       # "drop" | "spike"
                "deviation_score": float,
                "revenue_impact": float | null,
                "severity_score": float,
                "workflow_status": str,
                "top_hypothesis": str | null,
                "executive_summary": str | null,
            },
            ...
        ]
    }
    """
    limit = min(limit, 200)
    days = max(1, min(days, 90))

    user_id = current_user["user_id"]
    access_token = current_user["access_token"]

    def _load_portfolio() -> dict:
        from src.db import get_client

        client = get_client(access_token)
        cutoff = (_now_utc() - timedelta(days=days)).isoformat()

        res = (
            client.table("rca_reports")
            .select(
                "id, dataset_id, anomaly_date, primary_metric, workflow_status, "
                "confidence, n_anomalies, top_hypothesis, executive_summary, "
                "created_at, report_payload"
            )
            .eq("user_id", user_id)
            .gte("created_at", cutoff)
            .not_.in_("workflow_status", ["closed", "archived"])
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        reports = res.data or []

        # Fetch workspace names in one batch
        workspace_ids = list({r["dataset_id"] for r in reports if r.get("dataset_id")})
        workspace_map: dict[str, str] = {}
        if workspace_ids:
            ws_res = (
                client.table("datasets")
                .select("id, name")
                .in_("id", workspace_ids)
                .execute()
            )
            for ws in (ws_res.data or []):
                workspace_map[str(ws["id"])] = str(ws.get("name") or "Unnamed workspace")

        incidents = []
        for report in reports:
            payload = report.get("report_payload") or {}
            anomaly_summary = payload.get("anomaly_summary") or []

            # Worst anomaly in this report
            worst = max(anomaly_summary, key=lambda a: abs(float(a.get("deviation_score", 0))), default={})
            deviation_score = float(worst.get("deviation_score", 0))
            direction = str(worst.get("direction", "drop"))

            # Revenue impact: observed - expected for worst revenue anomaly
            revenue_impact: float | None = None
            revenue_anomalies = [a for a in anomaly_summary if a.get("metric") == "revenue"]
            if revenue_anomalies:
                ra = revenue_anomalies[0]
                obs = float(ra.get("observed_value", 0))
                exp = float(ra.get("expected_value", 0))
                revenue_impact = round(obs - exp, 2)

            # Composite severity: deviation magnitude + scaled revenue impact
            revenue_score = min(abs(revenue_impact) / 10_000, 5.0) if revenue_impact else 0.0
            severity_score = round(deviation_score + revenue_score, 3)

            incidents.append({
                "report_id": str(report["id"]),
                "workspace_id": str(report.get("dataset_id") or ""),
                "workspace_name": workspace_map.get(str(report.get("dataset_id") or ""), "Unknown"),
                "anomaly_date": str(report.get("anomaly_date") or ""),
                "primary_metric": str(report.get("primary_metric") or ""),
                "direction": direction,
                "deviation_score": round(deviation_score, 3),
                "revenue_impact": revenue_impact,
                "severity_score": severity_score,
                "workflow_status": str(report.get("workflow_status") or "new"),
                "top_hypothesis": report.get("top_hypothesis"),
                "executive_summary": report.get("executive_summary"),
            })

        incidents.sort(key=lambda x: x["severity_score"], reverse=True)
        for i, inc in enumerate(incidents, 1):
            inc["rank"] = i

        return {
            "total_open_incidents": len(incidents),
            "days_window": days,
            "generated_at": _now_utc().isoformat(),
            "incidents": incidents,
        }

    result = await asyncio.to_thread(_load_portfolio)
    log_event(
        logger,
        "portfolio.summary_viewed",
        user_id=user_id,
        open_incidents=result["total_open_incidents"],
        days=days,
    )
    return result


@router.get("/api/v1/public/brief/{share_token}", response_model=PublicBriefResponse)
async def read_public_brief(share_token: str) -> PublicBriefResponse:
    shared = await asyncio.to_thread(get_shared_report, share_token)
    if not shared:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared brief not found.")

    return _build_client_brief_payload(
        shared["report"],
        shared["workspace_name"],
        shared["agency_name"],
    )
