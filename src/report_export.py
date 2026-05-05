"""
report_export.py
================
PDF export for MetricSleuth RCA reports using ReportLab.

Generates a professional, branded PDF that mirrors the Markdown report:

  - Cover page with title, date, and metadata
  - Executive summary (LLM or rule-based)
  - Anomaly table
  - Contribution breakdown table
  - Segment impact tables
  - Hypotheses & recommended actions

Usage
-----
    from src.report_export import export_report_pdf
    pdf_bytes = export_report_pdf(report_dict, executive_summary)
    with open("rca_report.pdf", "wb") as f:
        f.write(pdf_bytes)
"""

from __future__ import annotations

import io
import logging
from datetime import datetime
from typing import Any

from utils.config import REPORT_TITLE

logger = logging.getLogger(__name__)


def _import_reportlab():
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            HRFlowable, PageBreak,
        )
        return {
            "colors": colors, "TA_CENTER": TA_CENTER, "TA_LEFT": TA_LEFT,
            "TA_JUSTIFY": TA_JUSTIFY, "A4": A4,
            "getSampleStyleSheet": getSampleStyleSheet,
            "ParagraphStyle": ParagraphStyle, "cm": cm,
            "SimpleDocTemplate": SimpleDocTemplate, "Paragraph": Paragraph,
            "Spacer": Spacer, "Table": Table, "TableStyle": TableStyle,
            "HRFlowable": HRFlowable, "PageBreak": PageBreak,
        }
    except ImportError as exc:
        raise ImportError(
            "ReportLab is not installed. Run: pip install reportlab"
        ) from exc


# ── Colour palette ────────────────────────────────────────────────────────────
_DARK_BG   = (6/255,  9/255,  18/255)
_CYAN      = (0/255, 229/255, 255/255)
_PURPLE    = (123/255, 104/255, 238/255)
_MID_GREY  = (58/255, 74/255, 107/255)
_LIGHT_TXT = (226/255, 232/255, 240/255)
_ROW_ALT   = (13/255, 19/255, 39/255)
_WHITE     = (1.0, 1.0, 1.0)


def _make_styles(rl: dict):
    """Build a custom style sheet matching the MetricSleuth dark theme."""
    ParagraphStyle = rl["ParagraphStyle"]
    TA_CENTER = rl["TA_CENTER"]
    TA_JUSTIFY = rl["TA_JUSTIFY"]
    TA_LEFT = rl["TA_LEFT"]
    colors = rl["colors"]

    base = rl["getSampleStyleSheet"]()

    title_style = ParagraphStyle(
        "MSTitle",
        parent=base["Title"],
        fontSize=26,
        leading=32,
        textColor=colors.Color(*_LIGHT_TXT),
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "MSSubtitle",
        parent=base["Normal"],
        fontSize=9,
        textColor=colors.Color(*_MID_GREY),
        alignment=TA_CENTER,
        spaceAfter=12,
    )
    section_style = ParagraphStyle(
        "MSSection",
        parent=base["Heading2"],
        fontSize=11,
        textColor=colors.Color(*_CYAN),
        spaceBefore=14,
        spaceAfter=4,
        leading=16,
    )
    body_style = ParagraphStyle(
        "MSBody",
        parent=base["Normal"],
        fontSize=9,
        textColor=colors.Color(*_LIGHT_TXT),
        leading=14,
        alignment=TA_JUSTIFY,
    )
    caption_style = ParagraphStyle(
        "MSCaption",
        parent=base["Normal"],
        fontSize=8,
        textColor=colors.Color(*_MID_GREY),
        spaceAfter=4,
    )
    bullet_style = ParagraphStyle(
        "MSBullet",
        parent=body_style,
        leftIndent=14,
        bulletIndent=4,
        spaceAfter=3,
    )

    return {
        "title":    title_style,
        "subtitle": subtitle_style,
        "section":  section_style,
        "body":     body_style,
        "caption":  caption_style,
        "bullet":   bullet_style,
    }


def _make_table(rl: dict, data: list[list], col_widths=None):
    """Create a styled ReportLab Table."""
    colors = rl["colors"]
    Table = rl["Table"]
    TableStyle = rl["TableStyle"]

    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        # Header row
        ("BACKGROUND",   (0, 0), (-1, 0), colors.Color(*_PURPLE)),
        ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING",(0, 0), (-1, 0), 6),
        ("TOPPADDING",   (0, 0), (-1, 0), 6),
        # Data rows
        ("FONTNAME",     (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",     (0, 1), (-1, -1), 8),
        ("TEXTCOLOR",    (0, 1), (-1, -1), colors.Color(*_LIGHT_TXT)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.Color(*_DARK_BG), colors.Color(*_ROW_ALT)]),
        ("GRID",         (0, 0), (-1, -1), 0.3, colors.Color(*_MID_GREY)),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",   (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 1), (-1, -1), 4),
    ]))
    return tbl


def export_report_pdf(
    report: dict[str, Any],
    executive_summary: str = "",
) -> bytes:
    """Generate a PDF version of the RCA report.

    Parameters
    ----------
    report:
        Structured report dictionary from :func:`report_generator.build_report`.
    executive_summary:
        Plain-text executive summary (from :func:`llm_summary.generate_executive_summary`).
        If empty, a short placeholder is used.

    Returns
    -------
    bytes
        Raw PDF bytes — write directly to a file or pass to Streamlit's
        ``st.download_button``.
    """
    rl = _import_reportlab()
    colors  = rl["colors"]
    A4      = rl["A4"]
    cm      = rl["cm"]
    Paragraph  = rl["Paragraph"]
    Spacer     = rl["Spacer"]
    HRFlowable = rl["HRFlowable"]
    PageBreak  = rl["PageBreak"]
    SimpleDocTemplate = rl["SimpleDocTemplate"]

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm,  bottomMargin=2*cm,
        title=REPORT_TITLE,
    )

    styles = _make_styles(rl)
    story  = []

    def hr():
        story.append(HRFlowable(
            width="100%", thickness=0.5,
            color=colors.Color(*_MID_GREY),
            spaceAfter=8, spaceBefore=8,
        ))

    def section(title: str):
        story.append(Paragraph(title.upper(), styles["section"]))
        story.append(Spacer(1, 0.1*cm))

    # ── Cover ─────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 1.5*cm))
    story.append(Paragraph("MetricSleuth", styles["title"]))
    story.append(Paragraph("Metric Investigation Report", styles["subtitle"]))
    story.append(Spacer(1, 0.4*cm))

    meta_rows = [
        ["Generated", report.get("generated_at", datetime.now().isoformat(timespec="seconds"))],
        ["Primary Metric", report.get("primary_metric", "revenue").title()],
        ["Anomaly Date", report.get("anomaly_date", "N/A")],
    ]
    meta_tbl = _make_table(rl, [["Field", "Value"]] + meta_rows, col_widths=[5*cm, 10*cm])
    story.append(meta_tbl)
    story.append(PageBreak())

    # ── Executive Summary ─────────────────────────────────────────────────────
    section("Executive Summary")
    summary_text = executive_summary or (
        "An automated metric investigation was performed. "
        "Please refer to the sections below for detailed findings."
    )
    story.append(Paragraph(summary_text, styles["body"]))
    hr()

    # ── Anomalies ─────────────────────────────────────────────────────────────
    section("Anomalies Detected")
    anomalies = report.get("anomaly_summary", [])
    if anomalies:
        header = ["Date", "Metric", "Observed", "Expected", "Z-Score", "Direction"]
        rows   = [header] + [
            [
                str(a.get("date", ""))[:10],
                a.get("metric", ""),
                f"{a.get('observed', 0):.2f}",
                f"{a.get('expected', 0):.2f}",
                f"{a.get('z_score', 0):.2f}",
                a.get("direction", "").upper(),
            ]
            for a in anomalies
        ]
        story.append(_make_table(rl, rows))
    else:
        story.append(Paragraph("No anomalies recorded.", styles["body"]))
    hr()

    # ── Contribution Breakdown ────────────────────────────────────────────────
    section("Factor Contribution")
    contrib = report.get("contribution_breakdown", [])
    if contrib:
        header = ["Factor", "% Change vs Baseline", "% Contribution to Drop"]
        rows   = [header] + [
            [
                c.get("factor", "").replace("_", " ").title(),
                f"{c.get('pct_change', 0):.1f}%",
                f"{c.get('contribution_pct', 0):.1f}%",
            ]
            for c in contrib
        ]
        story.append(_make_table(rl, rows))
    else:
        story.append(Paragraph("No contribution data available.", styles["body"]))
    hr()

    # ── Segment Impact ────────────────────────────────────────────────────────
    section("Segment Impact Analysis")
    seg_impact = report.get("segment_impact", {})
    for dim, records in seg_impact.items():
        story.append(Paragraph(dim.replace("_", " ").title(), styles["caption"]))
        if records:
            keys   = list(records[0].keys())
            header = [k.replace("_", " ").title() for k in keys]
            rows   = [header] + [
                [str(round(r[k], 2)) if isinstance(r[k], float) else str(r[k]) for k in keys]
                for r in records[:8]   # cap at 8 rows per segment
            ]
            story.append(_make_table(rl, rows))
        story.append(Spacer(1, 0.3*cm))
    hr()

    # ── Hypotheses ────────────────────────────────────────────────────────────
    section("Likely Drivers")
    for h in report.get("hypotheses", []):
        story.append(Paragraph(
            f"<b>[{h['id']}] {h['title']}</b>  —  Confidence: {h['confidence']:.0%}",
            styles["body"],
        ))
        story.append(Paragraph(h.get("description", ""), styles["body"]))
        for ev in h.get("supporting_evidence", []):
            story.append(Paragraph(f"• {ev}", styles["bullet"]))
        story.append(Spacer(1, 0.3*cm))
    hr()

    # ── Recommended Actions ───────────────────────────────────────────────────
    section("Recommended Actions")
    for i, action in enumerate(report.get("recommended_actions", []), 1):
        story.append(Paragraph(f"{i:02d}.  {action}", styles["bullet"]))

    # ── Build ─────────────────────────────────────────────────────────────────
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    logger.info("PDF report generated (%d bytes).", len(pdf_bytes))
    return pdf_bytes


# ── Example usage ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
    from src.data_loader import load_data
    from src.anomaly_detection import detect_anomalies, get_anomaly_dates
    from src.segmentation_analysis import analyse_all_segments
    from src.correlation_analysis import analyse_correlations
    from src.contribution_analysis import compute_contributions
    from src.hypothesis_engine import generate_hypotheses
    from src.report_generator import build_report

    raw      = load_data("data/sample_ecommerce.csv")
    anomalies = detect_anomalies(raw)
    dates    = get_anomaly_dates(anomalies)

    if dates:
        d       = dates[0]
        segs    = analyse_all_segments(raw, d, "revenue")
        contrib = compute_contributions(raw, d)
        corr    = analyse_correlations(raw)
        hyps    = generate_hypotheses(contrib, segs, corr)
        report  = build_report(anomalies[anomalies["date"]==d], corr, segs, contrib, hyps, d)
        pdf     = export_report_pdf(report, executive_summary="Test summary.")
        out_path = pathlib.Path("output/rca_report.pdf")
        out_path.parent.mkdir(exist_ok=True)
        out_path.write_bytes(pdf)
        print(f"PDF saved to {out_path} ({len(pdf):,} bytes)")
