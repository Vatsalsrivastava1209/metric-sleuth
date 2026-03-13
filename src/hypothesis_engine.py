"""
hypothesis_engine.py
====================
Rule-based engine that converts statistical findings into human-readable
hypotheses (potential root causes) and actionable recommendations.

The engine operates on the outputs of the other analysis modules and
produces a ranked list of hypotheses — each with a confidence score and
recommended action.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from utils.config import STRONG_CORRELATION_THRESHOLD

logger = logging.getLogger(__name__)


@dataclass
class Hypothesis:
    """A single potential root-cause hypothesis."""

    id: str
    title: str
    description: str
    confidence: float        # 0.0 – 1.0
    supporting_evidence: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "confidence": round(self.confidence, 2),
            "supporting_evidence": self.supporting_evidence,
            "recommended_actions": self.recommended_actions,
        }


# ── Rule helpers ──────────────────────────────────────────────────────────────

def _traffic_drop_hypothesis(
    contributions_df: pd.DataFrame,
    segment_results: dict,
) -> Hypothesis | None:
    """Generate a traffic-drop hypothesis when traffic is a major contributor."""
    if contributions_df.empty:
        return None

    traffic_rows = contributions_df[contributions_df["factor"] == "traffic"]
    if traffic_rows.empty:
        return None

    row = traffic_rows.iloc[0]
    if row["pct_change"] >= 0 or row["contribution_pct"] < 20:
        return None

    evidence = [
        f"Traffic dropped {abs(row['pct_change']):.1f}% vs. baseline.",
        f"Traffic accounted for {row['contribution_pct']:.1f}% of the revenue decline.",
    ]

    # Look for the most impacted traffic_source segment
    actions = [
        "Investigate paid-search and SEO campaigns for the affected dates.",
        "Check CDN / server uptime logs for availability issues.",
        "Review marketing spend and channel attribution reports.",
    ]

    if "traffic_source" in segment_results:
        df_seg = segment_results["traffic_source"]
        if not df_seg.empty:
            worst_source = df_seg.iloc[0]["traffic_source"]
            evidence.append(
                f"'{worst_source}' was the most impacted traffic source segment."
            )
            actions.insert(0, f"Prioritise investigation of '{worst_source}' channel.")

    return Hypothesis(
        id="H-TRAFFIC-DROP",
        title="Traffic Volume Decline",
        description=(
            "An unexpected drop in user traffic was a primary driver of the revenue decline. "
            "This may indicate a marketing outage, SEO penalty, or acquisition channel failure."
        ),
        confidence=min(0.9, row["contribution_pct"] / 100 + 0.3),
        supporting_evidence=evidence,
        recommended_actions=actions,
    )


def _conversion_drop_hypothesis(
    contributions_df: pd.DataFrame,
    segment_results: dict,
) -> Hypothesis | None:
    """Generate a conversion-rate hypothesis when CVR drops significantly."""
    if contributions_df.empty:
        return None

    cvr_rows = contributions_df[contributions_df["factor"] == "conversion_rate"]
    if cvr_rows.empty:
        return None

    row = cvr_rows.iloc[0]
    if row["pct_change"] >= 0 or row["contribution_pct"] < 15:
        return None

    evidence = [
        f"Conversion rate dropped {abs(row['pct_change']):.1f}% vs. baseline.",
        f"Conversion rate accounted for {row['contribution_pct']:.1f}% of the revenue decline.",
    ]

    actions = [
        "Review checkout funnel for UX breakages or payment gateway errors.",
        "Analyse A/B test results for any concurrent experiments.",
        "Check if promotional offers or pricing changed on the anomaly date.",
    ]

    if "device" in segment_results:
        df_seg = segment_results["device"]
        if not df_seg.empty:
            worst_device = df_seg.iloc[0]["device"]
            evidence.append(
                f"'{worst_device}' device type showed the steepest conversion decline."
            )
            actions.insert(0, f"Audit {worst_device} checkout experience for bugs.")

    return Hypothesis(
        id="H-CVR-DROP",
        title="Conversion Rate Degradation",
        description=(
            "The site's ability to convert visitors into buyers declined, suggesting a "
            "product, UX, pricing, or technical issue rather than a traffic problem."
        ),
        confidence=min(0.9, row["contribution_pct"] / 100 + 0.2),
        supporting_evidence=evidence,
        recommended_actions=actions,
    )


def _region_concentration_hypothesis(
    segment_results: dict,
) -> Hypothesis | None:
    """Hypothesise a regional outage when one region dominates the decline."""
    if "region" not in segment_results:
        return None

    df_seg = segment_results["region"]
    if df_seg.empty:
        return None

    worst_row = df_seg.iloc[0]
    change = float(worst_row["relative_change_pct"])
    if change >= -20:
        return None

    region = worst_row["region"]
    return Hypothesis(
        id="H-REGION-OUTAGE",
        title=f"Regional Concentration: {region}",
        description=(
            f"The '{region}' region experienced a disproportionate decline, pointing to a "
            "geo-specific event such as localised outage, regulation change, or logistics disruption."
        ),
        confidence=0.65,
        supporting_evidence=[
            f"'{region}' revenue fell {abs(change):.1f}% relative to baseline.",
            "Other regions show comparatively smaller declines.",
        ],
        recommended_actions=[
            f"Check infrastructure and CDN status for the {region} region.",
            "Review local news / regulatory announcements for the period.",
            f"Contact regional team / logistics partners in {region} for context.",
        ],
    )


def _strong_correlation_hypothesis(
    correlations_df: pd.DataFrame,
) -> Hypothesis | None:
    """Flag when a strong correlation metric also declined (compound effect)."""
    if correlations_df.empty:
        return None

    strong = correlations_df[
        correlations_df["is_strong"] & (correlations_df["relationship"] == "positive")
    ]
    if strong.empty:
        return None

    pairs = [
        f"{r['metric_a']} ↔ {r['metric_b']} (r={r['pearson_r']:.2f})"
        for _, r in strong.iterrows()
    ]

    return Hypothesis(
        id="H-CORRELATION",
        title="Compound Metric Decline",
        description=(
            "Multiple strongly correlated metrics declined simultaneously, indicating a "
            "systemic issue rather than an isolated data artefact."
        ),
        confidence=0.75,
        supporting_evidence=pairs,
        recommended_actions=[
            "Cross-reference incident management system for the period.",
            "Investigate shared dependencies (e.g., payment gateway, recommendation engine).",
            "Ensure data pipeline integrity — rule out tracking / instrumentation failure.",
        ],
    )


# ── Public API ─────────────────────────────────────────────────────────────────

def generate_hypotheses(
    contributions_df: pd.DataFrame,
    segment_results: dict,
    correlations_df: pd.DataFrame,
) -> list[Hypothesis]:
    """Run all rules and return a sorted list of plausible hypotheses.

    Parameters
    ----------
    contributions_df:
        Output of :func:`contribution_analysis.compute_contributions`.
    segment_results:
        Output of :func:`segmentation_analysis.analyse_all_segments`.
    correlations_df:
        Output of :func:`correlation_analysis.analyse_correlations`.

    Returns
    -------
    list[Hypothesis]
        Hypotheses sorted by confidence descending.
    """
    candidates: list[Hypothesis | None] = [
        _traffic_drop_hypothesis(contributions_df, segment_results),
        _conversion_drop_hypothesis(contributions_df, segment_results),
        _region_concentration_hypothesis(segment_results),
        _strong_correlation_hypothesis(correlations_df),
    ]

    hypotheses = [h for h in candidates if h is not None]
    hypotheses.sort(key=lambda h: h.confidence, reverse=True)
    logger.info("Generated %d hypotheses.", len(hypotheses))
    return hypotheses


def hypotheses_to_dataframe(hypotheses: list[Hypothesis]) -> pd.DataFrame:
    """Convert a list of hypotheses to a DataFrame for display."""
    if not hypotheses:
        return pd.DataFrame(
            columns=["id", "title", "confidence", "description"]
        )
    rows = [
        {
            "id": h.id,
            "title": h.title,
            "confidence": f"{h.confidence:.0%}",
            "description": h.description,
        }
        for h in hypotheses
    ]
    return pd.DataFrame(rows)


# ── Example usage ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
    from src.data_loader import load_data
    from src.anomaly_detection import detect_anomalies, get_anomaly_dates
    from src.segmentation_analysis import analyse_all_segments
    from src.correlation_analysis import analyse_correlations
    from src.contribution_analysis import compute_contributions

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
        for h in hyps:
            print(f"\n[{h.id}] {h.title}  (confidence={h.confidence:.0%})")
            print(f"  {h.description}")
            print("  Evidence:", h.supporting_evidence)
            print("  Actions:", h.recommended_actions)
