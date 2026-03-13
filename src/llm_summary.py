"""
llm_summary.py
==============
LLM-powered executive summary generation for RCA reports.

Supports two backends — configure via ``utils/config.py``:

* ``"gemini"``  — Google Gemini API  (google-generativeai)
* ``"openai"``  — OpenAI ChatCompletion (openai)

The module is designed to degrade gracefully:  if the API key is missing
or the library is not installed the function returns a rule-based fallback
summary instead of raising an error.
"""

from __future__ import annotations

import logging
import textwrap
from typing import Any

import pandas as pd

from utils.config import (
    LLM_BACKEND,
    LLM_MODEL,
    LLM_API_KEY,
    LLM_MAX_TOKENS,
    LLM_TEMPERATURE,
)

logger = logging.getLogger(__name__)


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_prompt(report: dict[str, Any]) -> str:
    """Convert a structured RCA report dict to a concise LLM prompt."""

    # Anomaly digest
    anomaly_lines: list[str] = []
    for a in report.get("anomaly_summary", []):
        anomaly_lines.append(
            f"  - {a['metric']} {a['direction']} on {a['date']}: "
            f"observed {a['observed']:.2f} vs expected {a['expected']:.2f} "
            f"(z={a['z_score']:.2f})"
        )
    anomaly_block = "\n".join(anomaly_lines) or "  None detected."

    # Contribution digest
    contrib_lines: list[str] = []
    for c in report.get("contribution_breakdown", []):
        contrib_lines.append(
            f"  - {c['factor']}: {c['pct_change']:.1f}% change, "
            f"{c['contribution_pct']:.1f}% of total drop"
        )
    contrib_block = "\n".join(contrib_lines) or "  No data."

    # Segment digest (top entry per dimension)
    seg_lines: list[str] = []
    for dim, records in report.get("segment_impact", {}).items():
        if records:
            top = records[0]
            seg_lines.append(
                f"  - {dim}: worst segment '{top.get(dim, '?')}' "
                f"({top.get('relative_change_pct', 0):.1f}% vs baseline)"
            )
    seg_block = "\n".join(seg_lines) or "  No segment data."

    # Hypotheses digest
    hyp_lines = [
        f"  - [{h['id']}] {h['title']} (confidence {h['confidence']:.0%})"
        for h in report.get("hypotheses", [])
    ]
    hyp_block = "\n".join(hyp_lines) or "  None generated."

    prompt = textwrap.dedent(f"""
    You are a senior data analyst writing an executive summary for a business intelligence report.

    Below is structured data from a Root Cause Analysis (RCA) system called MetricSleuth.
    Write a concise, professional, plain-English executive summary (3-5 sentences) that explains:
    1. What happened (which metric, on what date, by how much)
    2. Why it likely happened (most probable cause based on the data)
    3. Which segment or channel was most impacted
    4. A single most important recommended next investigation step

    Do NOT use bullet points. Write in flowing prose. Be specific with numbers.

    --- ANOMALIES ---
    Primary metric: {report.get('primary_metric', 'revenue')}
    Anomaly date: {report.get('anomaly_date', 'N/A')}
    {anomaly_block}

    --- FACTOR CONTRIBUTIONS ---
    {contrib_block}

    --- SEGMENT IMPACT ---
    {seg_block}

    --- HYPOTHESES ---
    {hyp_block}

    Write the executive summary now:
    """).strip()

    return prompt


# ── LLM backends ─────────────────────────────────────────────────────────────

def _call_gemini(prompt: str) -> str:
    """Call the Google Gemini API."""
    try:
        import google.generativeai as genai  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "google-generativeai is not installed. Run: pip install google-generativeai"
        ) from exc

    genai.configure(api_key=LLM_API_KEY)
    model = genai.GenerativeModel(LLM_MODEL or "gemini-1.5-flash")
    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            max_output_tokens=LLM_MAX_TOKENS,
            temperature=LLM_TEMPERATURE,
        ),
    )
    return response.text.strip()


def _call_openai(prompt: str) -> str:
    """Call the OpenAI ChatCompletion API."""
    try:
        from openai import OpenAI  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "openai is not installed. Run: pip install openai"
        ) from exc

    client = OpenAI(api_key=LLM_API_KEY)
    response = client.chat.completions.create(
        model=LLM_MODEL or "gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=LLM_MAX_TOKENS,
        temperature=LLM_TEMPERATURE,
    )
    return response.choices[0].message.content.strip()


# ── Rule-based fallback ───────────────────────────────────────────────────────

def _fallback_summary(report: dict[str, Any]) -> str:
    """Generate a basic rule-based summary when no LLM is available."""
    metric = report.get("primary_metric", "revenue")
    date   = report.get("anomaly_date", "an unspecified date")

    # Pick worst anomaly
    anomalies = report.get("anomaly_summary", [])
    worst = max(anomalies, key=lambda a: abs(a.get("z_score", 0)), default={})

    # Pick top contributing factor
    contrib = report.get("contribution_breakdown", [])
    top_factor = contrib[0] if contrib else {}

    # Top segment
    seg_impact = report.get("segment_impact", {})
    top_seg_dim, top_seg_val = "N/A", "N/A"
    for dim, records in seg_impact.items():
        if records:
            top_seg_dim = dim
            top_seg_val = records[0].get(dim, "N/A")
            break

    # Top hypothesis
    hyps = report.get("hypotheses", [])
    top_hyp = hyps[0]["title"] if hyps else "an unidentified cause"

    summary_parts = [
        f"On {date}, a significant anomaly was detected in the {metric} metric."
    ]
    if worst:
        pct = abs((worst.get('observed', 0) - worst.get('expected', 1))
                  / max(abs(worst.get('expected', 1)), 1e-9) * 100)
        summary_parts.append(
            f"The observed value was approximately {pct:.0f}% below the expected baseline."
        )
    if top_factor:
        summary_parts.append(
            f"{top_factor.get('factor', 'An unknown factor').replace('_', ' ').title()} "
            f"was the primary driver, contributing {top_factor.get('contribution_pct', 0):.0f}% "
            f"of the total decline."
        )
    if top_seg_val != "N/A":
        summary_parts.append(
            f"The impact was most concentrated in the '{top_seg_val}' {top_seg_dim} segment."
        )
    summary_parts.append(
        f"The most likely root cause is {top_hyp}. "
        "Immediate investigation of the affected channel and segment is recommended."
    )
    return " ".join(summary_parts)


# ── Public API ────────────────────────────────────────────────────────────────

def generate_executive_summary(
    report: dict[str, Any],
    force_fallback: bool = False,
) -> str:
    """Generate a natural-language executive summary from a structured RCA report.

    Tries the configured LLM backend first; falls back to a rule-based
    summary if the API is unavailable or not configured.

    Parameters
    ----------
    report:
        Structured report dict from :func:`report_generator.build_report`.
    force_fallback:
        If ``True``, skip the LLM and return the rule-based summary directly.
        Useful for testing without API credentials.

    Returns
    -------
    str
        Plain-English executive summary (3–5 sentences).
    """
    if force_fallback or not LLM_API_KEY:
        logger.info("LLM API key not set — using rule-based fallback summary.")
        return _fallback_summary(report)

    prompt = _build_prompt(report)

    try:
        backend = (LLM_BACKEND or "").lower()
        if backend == "gemini":
            return _call_gemini(prompt)
        elif backend == "openai":
            return _call_openai(prompt)
        else:
            logger.warning("Unknown LLM backend '%s' — using fallback.", LLM_BACKEND)
            return _fallback_summary(report)
    except Exception as exc:
        logger.error("LLM call failed (%s) — using fallback summary.", exc)
        return _fallback_summary(report)


# ── Example usage ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, pathlib, logging
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
    from src.data_loader import load_data
    from src.anomaly_detection import detect_anomalies, get_anomaly_dates
    from src.segmentation_analysis import analyse_all_segments
    from src.correlation_analysis import analyse_correlations
    from src.contribution_analysis import compute_contributions
    from src.hypothesis_engine import generate_hypotheses
    from src.report_generator import build_report

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
        anom_day = anomalies[anomalies["date"] == d]
        report = build_report(anom_day, corr, segs, contrib, hyps, d)

        print("=== Executive Summary (fallback) ===")
        print(generate_executive_summary(report, force_fallback=True))
        print("\n=== Executive Summary (LLM) ===")
        print(generate_executive_summary(report))
