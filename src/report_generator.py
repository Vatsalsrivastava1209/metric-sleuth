"""
report_generator.py
===================
Assembles all analysis outputs into a structured, human-readable
Root Cause Analysis (RCA) report.

The report is returned both as a Python dictionary (for programmatic use)
and as a Markdown string (for display in Streamlit or export to file).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd

from utils.config import REPORT_TITLE
from src.hypothesis_engine import Hypothesis

logger = logging.getLogger(__name__)


def _md_table(df: pd.DataFrame) -> str:
    """Render a DataFrame as a Markdown table string."""
    if df.empty:
        return "_No data available._"
    return df.to_markdown(index=False)


def build_report(
    anomalies_df: pd.DataFrame,
    correlations_df: pd.DataFrame,
    segment_results: dict[str, pd.DataFrame],
    contributions_df: pd.DataFrame,
    hypotheses: list[Hypothesis],
    selected_date: pd.Timestamp | None = None,
    primary_metric: str = "revenue",
) -> dict[str, Any]:
    """Build a structured RCA report as a nested dictionary.

    Parameters
    ----------
    anomalies_df:
        Output of :func:`anomaly_detection.detect_anomalies`.
    correlations_df:
        Output of :func:`correlation_analysis.analyse_correlations`.
    segment_results:
        Output of :func:`segmentation_analysis.analyse_all_segments`.
    contributions_df:
        Output of :func:`contribution_analysis.compute_contributions`.
    hypotheses:
        Sorted list from :func:`hypothesis_engine.generate_hypotheses`.
    selected_date:
        The specific anomaly date being analysed (ISO formatted in report).
    primary_metric:
        Metric under investigation.

    Returns
    -------
    dict
        Structured RCA report dictionary.
    """
    report: dict[str, Any] = {
        "title": REPORT_TITLE,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "primary_metric": primary_metric,
        "anomaly_date": str(selected_date.date()) if selected_date else "N/A",
        "anomaly_summary": [],
        "correlation_findings": [],
        "segment_impact": {},
        "contribution_breakdown": [],
        "hypotheses": [],
        "recommended_actions": [],
    }

    # ── Anomaly summary ───────────────────────────────────────────────────────
    if not anomalies_df.empty:
        for _, row in anomalies_df.iterrows():
            report["anomaly_summary"].append({
                "date": str(row["date"]),
                "metric": row["metric"],
                "observed": row["observed_value"],
                "expected": row["expected_value"],
                "z_score": row["z_score"],
                "direction": row["direction"],
            })

    # ── Correlation findings ──────────────────────────────────────────────────
    if not correlations_df.empty:
        for _, r in correlations_df.iterrows():
            report["correlation_findings"].append({
                "pair": f"{r['metric_a']} ↔ {r['metric_b']}",
                "pearson_r": r["pearson_r"],
                "relationship": r["relationship"],
                "is_strong": r["is_strong"],
            })

    # ── Segment impact ────────────────────────────────────────────────────────
    for dim, df_seg in segment_results.items():
        if not df_seg.empty:
            report["segment_impact"][dim] = df_seg.to_dict(orient="records")

    # ── Contribution breakdown ────────────────────────────────────────────────
    if not contributions_df.empty:
        report["contribution_breakdown"] = contributions_df.to_dict(orient="records")

    # ── Hypotheses & recommended actions ─────────────────────────────────────
    all_actions: list[str] = []
    for h in hypotheses:
        report["hypotheses"].append(h.to_dict())
        all_actions.extend(h.recommended_actions)

    # De-duplicate while preserving order
    seen: set[str] = set()
    for action in all_actions:
        if action not in seen:
            report["recommended_actions"].append(action)
            seen.add(action)

    return report


def report_to_markdown(report: dict[str, Any]) -> str:
    """Convert a structured report dict to a Markdown string.

    Parameters
    ----------
    report:
        Output of :func:`build_report`.

    Returns
    -------
    str
        Full Markdown-formatted RCA report.
    """
    lines: list[str] = []
    lines.append(f"# {report['title']}")
    lines.append(f"\n**Generated:** {report['generated_at']}  ")
    lines.append(f"**Primary Metric:** `{report['primary_metric']}`  ")
    lines.append(f"**Anomaly Date:** `{report['anomaly_date']}`")

    # ── Anomaly summary ───────────────────────────────────────────────────────
    lines.append("\n---\n##  Anomalies Detected\n")
    if report["anomaly_summary"]:
        anom_df = pd.DataFrame(report["anomaly_summary"])
        lines.append(_md_table(anom_df))
    else:
        lines.append("_No anomalies detected._")

    # ── Correlation findings ──────────────────────────────────────────────────
    lines.append("\n---\n##  Correlation Findings\n")
    if report["correlation_findings"]:
        corr_df = pd.DataFrame(report["correlation_findings"])
        lines.append(_md_table(corr_df))
    else:
        lines.append("_No correlation data._")

    # ── Contribution breakdown ────────────────────────────────────────────────
    lines.append("\n---\n##  Contribution Breakdown\n")
    if report["contribution_breakdown"]:
        cont_df = pd.DataFrame(report["contribution_breakdown"])[
            ["factor", "pct_change", "contribution_pct"]
        ]
        cont_df.columns = ["Factor", "% Change vs Baseline", "% Contribution to Drop"]
        lines.append(_md_table(cont_df))
    else:
        lines.append("_No contribution data._")

    # ── Segment impact ────────────────────────────────────────────────────────
    lines.append("\n---\n##  Segment Impact Analysis\n")
    if report["segment_impact"]:
        for dim, records in report["segment_impact"].items():
            lines.append(f"### {dim.title()}\n")
            seg_df = pd.DataFrame(records)[[dim, "baseline_mean", "anomaly_value", "relative_change_pct"]]
            seg_df.columns = [dim.title(), "Baseline Mean", "Anomaly Value", "Δ %"]
            lines.append(_md_table(seg_df))
    else:
        lines.append("_No segment data._")

    # ── Hypotheses ────────────────────────────────────────────────────────────
    lines.append("\n---\n##  Potential Root Causes\n")
    if report["hypotheses"]:
        for h in report["hypotheses"]:
            conf_bar = "🟢" if h["confidence"] >= 0.75 else "🟡" if h["confidence"] >= 0.5 else "🔴"
            lines.append(f"### {conf_bar} [{h['id']}] {h['title']}  _(confidence: {h['confidence']:.0%})_\n")
            lines.append(f"{h['description']}\n")
            if h["supporting_evidence"]:
                lines.append("**Evidence:**")
                for ev in h["supporting_evidence"]:
                    lines.append(f"- {ev}")
            lines.append("")
    else:
        lines.append("_No hypotheses generated._")

    # ── Recommended actions ───────────────────────────────────────────────────
    lines.append("\n---\n##  Recommended Actions\n")
    if report["recommended_actions"]:
        for i, action in enumerate(report["recommended_actions"], 1):
            lines.append(f"{i}. {action}")
    else:
        lines.append("_No actions recommended._")

    return "\n".join(lines)


def save_report(report_md: str, output_path: str) -> None:
    """Write the Markdown report to *output_path*.

    Parameters
    ----------
    report_md:
        Markdown string returned by :func:`report_to_markdown`.
    output_path:
        File path (e.g. ``"output/rca_report.md"``).
    """
    from pathlib import Path
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(report_md)
    logger.info("Report saved to %s", output_path)


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

    import logging
    logging.basicConfig(level=logging.INFO)

    raw = load_data("data/sample_ecommerce.csv")
    anomalies = detect_anomalies(raw)
    dates = get_anomaly_dates(anomalies)

    if dates:
        d = dates[0]
        segs = analyse_all_segments(raw, d, "revenue")
        contrib = compute_contributions(raw, d)
        corr = analyse_correlations(raw)
        hyps = generate_hypotheses(contrib, segs, corr)

        anomalies_for_date = anomalies[anomalies["date"] == d]
        report = build_report(anomalies_for_date, corr, segs, contrib, hyps, d)
        md = report_to_markdown(report)
        print(md[:2000])
        save_report(md, "output/rca_report.md")
