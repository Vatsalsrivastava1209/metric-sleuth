"""
api/routers/export.py
=====================
Authenticated export endpoints for internal and client-ready report artifacts.

The product now serves agencies, so exports support two audiences:
1. internal: full investigative markdown
2. client: concise, branded incident brief built from persisted report metadata
"""

from __future__ import annotations

import html
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from api.dependencies import get_current_user, require_pro_tier

router = APIRouter(prefix="/api/v1/export", tags=["export"])
logger = logging.getLogger(__name__)


def _normalize_audience(audience: str | None) -> str:
    if isinstance(audience, str) and audience.strip().lower() == "client":
        return "client"
    return "internal"


def _format_confidence(confidence: object) -> str:
    try:
        value = float(confidence)
    except (TypeError, ValueError):
        return "Not recorded"

    if value <= 1:
        return f"{value:.0%}"
    return f"{value:.0f}%"


def _build_export_markdown(
    report: dict,
    audience: str,
    brand_name: str | None = None,
    workspace_name: str | None = None,
) -> tuple[str, str, str, str]:
    normalized_audience = _normalize_audience(audience)
    report_id = str(report.get("id", "report"))

    if normalized_audience == "client":
        agency_name = (brand_name or "Your Agency").strip() or "Your Agency"
        client_name = (workspace_name or "Client account").strip() or "Client account"
        metric_name = str(report.get("primary_metric") or "key metric")
        anomaly_date = str(report.get("anomaly_date") or "the latest reporting period")
        report_payload = report.get("report_payload") or {}
        hypotheses = report_payload.get("hypotheses") or []
        top_hypothesis_payload = hypotheses[0] if hypotheses else {}
        likely_driver = str(
            report.get("top_hypothesis")
            or top_hypothesis_payload.get("title")
            or "No dominant driver was captured. Review the internal brief before sending."
        )
        executive_summary = str(
            report.get("executive_summary")
            or "We detected a meaningful change and prepared a follow-up investigation summary."
        )
        confidence = _format_confidence(report.get("confidence"))
        n_anomalies = int(report.get("n_anomalies") or 0)
        n_hypotheses = int(report.get("n_hypotheses") or 0)
        evidence_points = [
            str(item)
            for item in (top_hypothesis_payload.get("supporting_evidence") or [])[:2]
            if str(item).strip()
        ]

        client_markdown = "\n".join(
            [
                f"# {agency_name} Client Incident Brief",
                "",
                "## Account",
                client_name,
                "",
                "## What changed",
                f"We detected an unusual movement in **{metric_name}** on **{anomaly_date}**.",
                "",
                "## Likely drivers",
                likely_driver,
                "",
                "## Recommended client update",
                executive_summary,
                "",
                "## Evidence snapshot",
                f"- Metric affected: {metric_name}",
                f"- Detection date: {anomaly_date}",
                f"- Confidence: {confidence}",
                f"- Supporting anomalies reviewed: {n_anomalies}",
                f"- Ranked hypotheses reviewed: {n_hypotheses}",
                *[f"- {point}" for point in evidence_points],
                "",
                "## Next step",
                "Validate the change against channel and storefront context, then send the client summary with the evidence above.",
            ]
        )
        return (
            client_markdown,
            "client-brief",
            f"{agency_name} Client Brief",
            agency_name,
        )

    internal_markdown = str(report.get("report_md") or "")
    return (
        internal_markdown,
        "internal-report",
        f"MetricSleuth Internal Investigation {report_id[:8]}",
        "MetricSleuth",
    )


def _markdown_to_pdf_bytes(
    report_md: str,
    report_id: str,
    title: str,
    footer_label: str,
) -> bytes:
    """Convert markdown report text into PDF bytes with WeasyPrint."""
    try:
        from weasyprint import HTML  # type: ignore
    except ImportError as exc:
        raise ImportError("weasyprint not installed") from exc

    safe_markdown = html.escape(report_md)
    safe_report_id = html.escape(report_id)
    safe_title = html.escape(title)
    safe_footer = html.escape(footer_label)

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>{safe_title}</title>
      <style>
        body {{
          font-family: 'Helvetica Neue', Arial, sans-serif;
          font-size: 11pt;
          line-height: 1.6;
          color: #1f2937;
          max-width: 800px;
          margin: 0 auto;
          padding: 40px;
        }}
        h1 {{
          color: #12283a;
          border-bottom: 2px solid #d97706;
          padding-bottom: 8px;
          margin-bottom: 24px;
        }}
        pre {{
          white-space: pre-wrap;
          font-family: inherit;
          background: #f8fafc;
          padding: 18px;
          border-radius: 10px;
          border: 1px solid #e2e8f0;
        }}
        .footer {{
          margin-top: 40px;
          font-size: 8pt;
          color: #64748b;
          text-align: center;
        }}
        @page {{
          margin: 2cm;
          @bottom-center {{ content: "{safe_footer} | Page " counter(page) " of " counter(pages); }}
        }}
      </style>
    </head>
    <body>
      <h1>{safe_title}</h1>
      <pre>{safe_markdown}</pre>
      <div class="footer">{safe_footer} | Report ID: {safe_report_id}</div>
    </body>
    </html>
    """
    return HTML(string=html_content).write_pdf()


@router.api_route("/pdf/{report_id}", methods=["GET", "POST"])
async def export_pdf_report(
    report_id: str,
    audience: str = "internal",
    brand_name: str | None = None,
    current_user: Annotated[dict, Depends(require_pro_tier)] = None,
) -> Response:
    """Export a report as PDF.

    Internal reports return the full investigative markdown.
    Client reports return a shorter branded brief intended for agency delivery.
    """
    import asyncio

    from src.db import get_dataset, get_profile, get_report

    user_id = current_user["user_id"]
    access_token = current_user.get("access_token")
    normalized_audience = _normalize_audience(audience)
    report = await asyncio.to_thread(get_report, report_id, user_id, access_token)

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report '{report_id}' not found or does not belong to your account.",
        )

    if normalized_audience == "client":
        profile = await asyncio.to_thread(get_profile, user_id, access_token)
        workspace = None
        if report.get("dataset_id"):
            workspace = await asyncio.to_thread(
                get_dataset,
                str(report["dataset_id"]),
                user_id,
                access_token,
            )
        report_md, filename_suffix, title, footer_label = _build_export_markdown(
            report,
            normalized_audience,
            brand_name=brand_name or profile.get("full_name", ""),
            workspace_name=(workspace or {}).get("name"),
        )
    else:
        report_md, filename_suffix, title, footer_label = _build_export_markdown(
            report,
            normalized_audience,
        )

    if not report_md:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Report exists but has no markdown content. Re-run the investigation to regenerate it.",
        )

    try:
        pdf_bytes = await asyncio.to_thread(
            _markdown_to_pdf_bytes,
            report_md,
            report_id,
            title,
            footer_label,
        )
        logger.info(
            "PDF generated for report=%s user=%s audience=%s (%d bytes)",
            report_id,
            user_id,
            normalized_audience,
            len(pdf_bytes),
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="metricsleuth-{filename_suffix}-{report_id[:8]}.pdf"',
                "Content-Length": str(len(pdf_bytes)),
            },
        )
    except ImportError:
        md_bytes = report_md.encode("utf-8")
        return Response(
            content=md_bytes,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="metricsleuth-{filename_suffix}-{report_id[:8]}.md"',
                "Content-Length": str(len(md_bytes)),
                "X-Export-Fallback": "weasyprint-not-installed",
            },
        )
    except Exception as exc:
        logger.error("PDF generation failed for report=%s: %s", report_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PDF generation failed. Please try again or contact support.",
        ) from exc


@router.get("/markdown/{report_id}")
async def export_markdown_report(
    report_id: str,
    audience: str = "internal",
    brand_name: str | None = None,
    current_user: Annotated[dict, Depends(get_current_user)] = None,
) -> Response:
    """Download report markdown for either internal or client-facing use."""
    import asyncio

    from src.db import get_dataset, get_profile, get_report

    user_id = current_user["user_id"]
    access_token = current_user["access_token"]
    normalized_audience = _normalize_audience(audience)
    report = await asyncio.to_thread(get_report, report_id, user_id, access_token)

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report '{report_id}' not found.",
        )

    if normalized_audience == "client":
        profile = await asyncio.to_thread(get_profile, user_id, access_token)
        workspace = None
        if report.get("dataset_id"):
            workspace = await asyncio.to_thread(
                get_dataset,
                str(report["dataset_id"]),
                user_id,
                access_token,
            )
        report_md, filename_suffix, _, _ = _build_export_markdown(
            report,
            normalized_audience,
            brand_name=brand_name or profile.get("full_name", ""),
            workspace_name=(workspace or {}).get("name"),
        )
    else:
        report_md, filename_suffix, _, _ = _build_export_markdown(
            report,
            normalized_audience,
        )

    if not report_md:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Report has no markdown content.",
        )

    md_bytes = report_md.encode("utf-8")
    return Response(
        content=md_bytes,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="metricsleuth-{filename_suffix}-{report_id[:8]}.md"',
            "Content-Length": str(len(md_bytes)),
        },
    )
