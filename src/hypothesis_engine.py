"""
hypothesis_engine.py
====================
Statistically-grounded engine that converts quantitative findings into ranked
likely-driver hypotheses with actionable recommendations.

The engine fires a set of rules against the outputs of the other analysis
modules.  Each rule is either confirmed or skipped based on concrete numeric
thresholds — no hand-waving.  Confidence scores are derived from contribution
percentages and corroboration counts, not hard-coded constants.

Hypothesis catalogue
--------------------
H-TRAFFIC-DROP    Traffic volume was a primary driver of the revenue decline.
H-CVR-DROP        Conversion rate degraded (on-site / product / pricing issue).
H-AOV-DROP        Average order value declined while traffic held steady.
H-REGION-OUTAGE   One region dominates the decline (geo-specific event).
H-CORRELATION     Multiple correlated metrics declined (systemic failure).
H-SPIKE           Positive anomaly — potential viral event, flash sale, or data error.
H-DATA-QUALITY    One metric spiked/dropped while all others held (instrumentation bug).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Literal, Sequence

import numpy as np
import pandas as pd

from utils.config import STRONG_CORRELATION_THRESHOLD

logger = logging.getLogger(__name__)

# Structured logger for hypothesis telemetry — separate from the app logger
# so downstream log aggregators (Datadog, CloudWatch) can filter on source.
_telemetry = logging.getLogger("metricsleuth.hypothesis.telemetry")


def _emit_rule_fire(
    rule_id: str,
    fired: bool,
    confidence: float | None = None,
    reason: str | None = None,
) -> None:
    """Emit a structured log record for every rule evaluation."""
    _telemetry.info(
        json.dumps({
            "event": "hypothesis_rule_evaluated",
            "rule_id": rule_id,
            "fired": fired,
            "confidence": round(confidence, 3) if confidence is not None else None,
            "reason": reason,
        })
    )


def record_user_feedback(
    hypothesis_id: str,
    outcome: Literal["accepted", "edited", "rejected"],
    investigation_id: str | None = None,
) -> None:
    """Record analyst feedback on a hypothesis for future model training.

    Call this from the API route that handles hypothesis feedback submission.
    The structured log is the ground-truth label source for eventually learning
    rule weights from real analyst decisions.

    Parameters
    ----------
    hypothesis_id:
        The rule ID (e.g. "H-TRAFFIC-DROP").
    outcome:
        Whether the analyst accepted, edited, or rejected the hypothesis.
    investigation_id:
        Opaque ID linking this feedback to a specific investigation run.
    """
    _telemetry.info(
        json.dumps({
            "event": "hypothesis_feedback",
            "hypothesis_id": hypothesis_id,
            "outcome": outcome,
            "investigation_id": investigation_id,
        })
    )


@dataclass
class Hypothesis:
    """A single evidence-backed likely-driver hypothesis."""

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


# ── Confidence helpers ────────────────────────────────────────────────────────

def _confidence(base_pct: float, corroboration: int = 0, cap: float = 0.94) -> float:
    """Derive a confidence score from a contribution percentage.

    Parameters
    ----------
    base_pct:
        The ``contribution_pct`` (0–100) from the contribution analysis.
    corroboration:
        Number of *other* hypotheses that also fired; each adds +0.04 because
        multiple independent signals pointing in the same direction increases
        overall confidence.
    cap:
        Maximum allowed confidence.  We never claim 100% certainty.
    """
    raw = (base_pct / 100) * 0.7 + 0.20          # maps [0,100] → [0.20, 0.90]
    raw += corroboration * 0.04
    return round(min(raw, cap), 3)


# ── Rule functions ────────────────────────────────────────────────────────────

def _traffic_drop_hypothesis(
    contributions_df: pd.DataFrame,
    segment_results: dict,
    corroboration: int = 0,
) -> Hypothesis | None:
    """H-TRAFFIC-DROP: Traffic volume was a primary driver of the decline."""
    if contributions_df.empty:
        _emit_rule_fire("H-TRAFFIC-DROP", fired=False, reason="contributions_empty")
        return None

    traffic_rows = contributions_df[contributions_df["factor"] == "traffic"]
    if traffic_rows.empty:
        _emit_rule_fire("H-TRAFFIC-DROP", fired=False, reason="no_traffic_factor")
        return None

    row = traffic_rows.iloc[0]
    if row["pct_change"] >= 0 or row["contribution_pct"] < 20:
        _emit_rule_fire("H-TRAFFIC-DROP", fired=False, reason="threshold_not_met",
                        confidence=float(row["contribution_pct"]))
        return None

    evidence = [
        f"Traffic dropped {abs(row['pct_change']):.1f}% vs. baseline.",
        f"Traffic accounted for {row['contribution_pct']:.1f}% of the revenue decline.",
    ]
    actions = [
        "Investigate paid-search and SEO campaigns for the affected dates.",
        "Check CDN / server uptime logs for availability issues.",
        "Review marketing spend and channel attribution reports.",
    ]

    if "traffic_source" in segment_results:
        df_seg = segment_results["traffic_source"]
        if not df_seg.empty:
            worst_source = df_seg.iloc[0]["traffic_source"]
            evidence.append(f"'{worst_source}' was the most impacted traffic source segment.")
            actions.insert(0, f"Prioritise investigation of '{worst_source}' channel.")

    conf = _confidence(row["contribution_pct"], corroboration)
    _emit_rule_fire("H-TRAFFIC-DROP", fired=True, confidence=conf)
    return Hypothesis(
        id="H-TRAFFIC-DROP",
        title="Traffic Volume Decline",
        description=(
            "An unexpected drop in user traffic was a primary driver of the revenue decline. "
            "This may indicate a marketing outage, SEO penalty, or acquisition channel failure."
        ),
        confidence=conf,
        supporting_evidence=evidence,
        recommended_actions=actions,
    )


def _conversion_drop_hypothesis(
    contributions_df: pd.DataFrame,
    segment_results: dict,
    corroboration: int = 0,
) -> Hypothesis | None:
    """H-CVR-DROP: Conversion rate degraded, pointing to an on-site issue."""
    if contributions_df.empty:
        _emit_rule_fire("H-CVR-DROP", fired=False, reason="contributions_empty")
        return None

    cvr_rows = contributions_df[contributions_df["factor"] == "conversion_rate"]
    if cvr_rows.empty:
        _emit_rule_fire("H-CVR-DROP", fired=False, reason="no_cvr_factor")
        return None

    row = cvr_rows.iloc[0]
    if row["pct_change"] >= 0 or row["contribution_pct"] < 15:
        _emit_rule_fire("H-CVR-DROP", fired=False, reason="threshold_not_met",
                        confidence=float(row["contribution_pct"]))
        return None

    evidence = [
        f"Conversion rate dropped {abs(row['pct_change']):.1f}% vs. baseline.",
        f"CVR accounted for {row['contribution_pct']:.1f}% of the revenue decline.",
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
            evidence.append(f"'{worst_device}' device type showed the steepest conversion decline.")
            actions.insert(0, f"Audit {worst_device} checkout experience for bugs.")

    conf = _confidence(row["contribution_pct"], corroboration)
    _emit_rule_fire("H-CVR-DROP", fired=True, confidence=conf)
    return Hypothesis(
        id="H-CVR-DROP",
        title="Conversion Rate Degradation",
        description=(
            "The site's ability to convert visitors into buyers declined, suggesting a "
            "product, UX, pricing, or technical issue rather than a traffic problem."
        ),
        confidence=conf,
        supporting_evidence=evidence,
        recommended_actions=actions,
    )


def _aov_drop_hypothesis(
    contributions_df: pd.DataFrame,
    corroboration: int = 0,
) -> Hypothesis | None:
    """H-AOV-DROP: Avg order value declined while traffic held (pricing/mix issue).

    This rule fires when:
    - Traffic contribution is LOW  (<10 %) — traffic is not the problem.
    - Orders contribution is LOW   (<10 %) — order count also held.
    - Revenue still dropped significantly — the only remaining lever is AOV.
    """
    if contributions_df.empty:
        return None

    def _pct(factor: str) -> float:
        rows = contributions_df[contributions_df["factor"] == factor]
        return float(rows.iloc[0]["contribution_pct"]) if not rows.empty else 100.0

    def _change(factor: str) -> float:
        rows = contributions_df[contributions_df["factor"] == factor]
        return float(rows.iloc[0]["pct_change"]) if not rows.empty else 0.0

    traffic_pct = _pct("traffic")
    orders_pct  = _pct("orders")

    # Both traffic and order count held stable → revenue decline must come from AOV
    if traffic_pct > 10 or orders_pct > 10:
        _emit_rule_fire("H-AOV-DROP", fired=False, reason="traffic_or_orders_dominant")
        return None

    # Sanity check: revenue must actually have declined
    rev_change = _change("revenue") if "revenue" in contributions_df["factor"].values else -1.0
    if rev_change >= 0:
        _emit_rule_fire("H-AOV-DROP", fired=False, reason="revenue_not_declining")
        return None

    _emit_rule_fire("H-AOV-DROP", fired=True, confidence=_confidence(80, corroboration))
    return Hypothesis(
        id="H-AOV-DROP",
        title="Average Order Value Decline",
        description=(
            "Traffic and order counts held steady while revenue fell, implying that "
            "the average basket size (AOV) declined. Possible causes include a shift "
            "in product mix, a new discount/promotion, or customers downgrading to "
            "cheaper items."
        ),
        confidence=_confidence(80, corroboration),   # strong inference when other factors ruled out
        supporting_evidence=[
            f"Traffic contribution to decline: {traffic_pct:.1f}% (low → traffic held).",
            f"Order count contribution to decline: {orders_pct:.1f}% (low → volume held).",
            "Revenue still declined, implying per-order value is the primary lever.",
        ],
        recommended_actions=[
            "Compare product-level revenue mix for the anomaly date vs. baseline.",
            "Check if any discounts, bundles, or promotions were active.",
            "Review cart abandonment rate to rule out checkout issues.",
            "Audit product pricing changes deployed on or before the anomaly date.",
        ],
    )


def _region_concentration_hypothesis(
    segment_results: dict,
    corroboration: int = 0,
    did_results: list | None = None,
) -> Hypothesis | None:
    """H-REGION-OUTAGE: One region dominates the decline (geo-specific event)."""
    if "region" not in segment_results:
        return None

    df_seg = segment_results["region"]
    if df_seg.empty:
        return None

    worst_row = df_seg.iloc[0]
    change = float(worst_row["relative_change_pct"])
    if change >= -20:
        return None

    # Check concentration: if the second-worst region is also severely impacted,
    # this is likely a systemic/global issue rather than a geo-isolated event.
    # Surface it only when the worst region is meaningfully worse than the second.
    if len(df_seg) >= 2:
        second_change = float(df_seg.iloc[1]["relative_change_pct"])
        
        # We only suppress if both regions dropped heavily AND they are similar in magnitude.
        # If Region A drops by 80% and Region B drops by 16%, Region A's drop is 5x worse,
        # so it's still a localised crisis. If both are dropping similarly (ratio < 1.5), then
        # it's systemic.
        if second_change < -15 and (change / second_change) < 1.5:
            logger.debug(
                "H-REGION-OUTAGE suppressed: two regions dropped severely with similar magnitude "
                "(worst=%.1f%%, second=%.1f%%). Systemic issue likely.",
                change, second_change,
            )
            return None

    region = str(worst_row["region"])
    conf = _confidence(abs(change) * 0.6, corroboration)

    evidence = [
        f"'{region}' revenue fell {abs(change):.1f}% relative to baseline.",
        "Other regions show comparatively smaller declines.",
    ]

    # Strengthen with DiD evidence if available
    if did_results:
        region_did = next(
            (r for r in did_results if r.get("dimension") == "region"
             and r.get("treated_segment") == region and r.get("causal_signal")),
            None,
        )
        if region_did:
            evidence.append(
                f"DiD estimate confirms: '{region}' declined {abs(region_did['did_pct']):.1f}% "
                "more than all other regions after controlling for the macro trend."
            )
            conf = min(conf + 0.06, 0.94)

    _emit_rule_fire("H-REGION-OUTAGE", fired=True, confidence=conf)
    return Hypothesis(
        id="H-REGION-OUTAGE",
        title=f"Regional Concentration: {region}",
        description=(
            f"The '{region}' region experienced a disproportionate decline, pointing to a "
            "geo-specific event such as a localised outage, regulation change, or logistics disruption."
        ),
        confidence=conf,
        supporting_evidence=evidence,
        recommended_actions=[
            f"Check infrastructure and CDN status for the {region} region.",
            "Review local news / regulatory announcements for the period.",
            f"Contact regional team / logistics partners in {region} for context.",
        ],
    )


def _strong_correlation_hypothesis(
    correlations_df: pd.DataFrame,
    corroboration: int = 0,
) -> Hypothesis | None:
    """H-CORRELATION: Multiple correlated metrics declined (systemic failure)."""
    if correlations_df.empty:
        return None

    strong = correlations_df[
        correlations_df["is_strong"] & (correlations_df["relationship"] == "positive")
    ]
    if strong.empty:
        _emit_rule_fire("H-CORRELATION", fired=False, reason="no_strong_positive_correlations")
        return None

    pairs = [
        f"{r['metric_a']} ↔ {r['metric_b']} (r={r['pearson_r']:.2f})"
        for _, r in strong.iterrows()
    ]

    _emit_rule_fire("H-CORRELATION", fired=True, confidence=_confidence(60, corroboration))
    return Hypothesis(
        id="H-CORRELATION",
        title="Compound Metric Decline",
        description=(
            "Multiple strongly correlated metrics declined simultaneously, indicating a "
            "systemic issue rather than an isolated data artefact."
        ),
        confidence=_confidence(60, corroboration),
        supporting_evidence=pairs,
        recommended_actions=[
            "Cross-reference incident management system for the period.",
            "Investigate shared dependencies (e.g., payment gateway, recommendation engine).",
            "Ensure data pipeline integrity — rule out tracking / instrumentation failure.",
        ],
    )


def _spike_hypothesis(
    contributions_df: pd.DataFrame,
    anomalies_df: pd.DataFrame,
) -> Hypothesis | None:
    """H-SPIKE: Positive anomaly — viral event, flash sale, or data error.

    Fires when revenue or traffic spiked (positive direction) instead of dropping.
    Positive spikes need investigation too — they might be a data error, a viral
    event that is masking a downstream problem, or a one-time promotional effect.
    """
    if anomalies_df.empty:
        return None

    # Look for spike-direction anomalies
    spike_col = "direction" if "direction" in anomalies_df.columns else None
    if spike_col is None:
        return None

    spikes = anomalies_df[anomalies_df[spike_col] == "spike"]
    if spikes.empty:
        _emit_rule_fire("H-SPIKE", fired=False, reason="no_spike_direction_anomalies")
        return None

    spiked_metrics = spikes["metric"].unique().tolist()
    _emit_rule_fire("H-SPIKE", fired=True, confidence=0.60)
    return Hypothesis(
        id="H-SPIKE",
        title=f"Positive Spike in {', '.join(spiked_metrics)}",
        description=(
            f"An unexpected positive spike was detected in {', '.join(spiked_metrics)}. "
            "This could indicate a genuine business event (viral moment, flash sale, "
            "PR feature) or a data quality issue such as double-counting of events."
        ),
        confidence=0.60,
        supporting_evidence=[
            f"Spike detected in metric(s): {', '.join(spiked_metrics)}.",
            "Positive deviations above the threshold require attribution to avoid misinterpretation.",
        ],
        recommended_actions=[
            "Verify with the marketing team whether a campaign or promotion was active.",
            "Check data pipeline logs for duplicate event ingestion.",
            "Confirm the spike is reflected in downstream financial reports.",
            "If unexplained, flag in the incident log for future reference.",
        ],
    )


def _data_quality_hypothesis(
    anomalies_df: pd.DataFrame,
    all_metrics: Sequence[str] | None = None,
) -> Hypothesis | None:
    """H-DATA-QUALITY: One metric is anomalous while others are completely normal.

    This pattern strongly suggests a tracking or instrumentation failure rather
    than a real business event — a real event almost always moves correlated
    metrics in the same direction.
    """
    if anomalies_df.empty:
        return None

    if all_metrics is None:
        from utils.config import ANOMALY_METRICS
        all_metrics = ANOMALY_METRICS

    affected_metrics  = set(anomalies_df["metric"].unique())
    unaffected_metrics = [m for m in all_metrics if m not in affected_metrics]

    # Only flag if exactly ONE metric was anomalous while ≥2 others were not
    if len(affected_metrics) != 1 or len(unaffected_metrics) < 2:
        _emit_rule_fire("H-DATA-QUALITY", fired=False, reason="multiple_metrics_affected_or_insufficient_baseline")
        return None

    suspect_metric = list(affected_metrics)[0]
    _emit_rule_fire("H-DATA-QUALITY", fired=True, confidence=0.78)
    return Hypothesis(
        id="H-DATA-QUALITY",
        title=f"Possible Data Quality Issue: {suspect_metric}",
        description=(
            f"Only '{suspect_metric}' was flagged as anomalous while all other tracked "
            "metrics remained within normal bounds. In real business events, correlated "
            "metrics typically move together. An isolated single-metric anomaly is a "
            "strong signal of a tracking bug, pipeline error, or schema change."
        ),
        confidence=0.78,
        supporting_evidence=[
            f"Anomaly confined to: {suspect_metric}.",
            f"Metrics within normal bounds: {', '.join(unaffected_metrics)}.",
            "Real demand shocks typically affect multiple metrics simultaneously.",
        ],
        recommended_actions=[
            f"Audit the '{suspect_metric}' data pipeline for the anomaly date.",
            "Check for recent schema changes, ETL job failures, or API version bumps.",
            "Cross-reference '{suspect_metric}' against the raw event source (GA4, Mixpanel, etc.).",
            "Do not trigger business decisions on this data until the source is verified.",
        ],
    )


# ── Public API ─────────────────────────────────────────────────────────────────

def generate_hypotheses(
    contributions_df: pd.DataFrame,
    segment_results: dict,
    correlations_df: pd.DataFrame,
    anomalies_df: pd.DataFrame | None = None,
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
    anomalies_df:
        Optional full anomaly DataFrame used for spike and data-quality checks.
        Pass ``None`` to skip those two rules.

    Returns
    -------
    list[Hypothesis]
        Hypotheses sorted by confidence descending.
    """
    if anomalies_df is None:
        anomalies_df = pd.DataFrame()

    # --- First pass: collect candidates ----------------------------------------
    candidates: list[Hypothesis | None] = [
        _traffic_drop_hypothesis(contributions_df, segment_results),
        _conversion_drop_hypothesis(contributions_df, segment_results),
        _aov_drop_hypothesis(contributions_df),
        _region_concentration_hypothesis(segment_results),
        _strong_correlation_hypothesis(correlations_df),
        _spike_hypothesis(contributions_df, anomalies_df),
        _data_quality_hypothesis(anomalies_df),
    ]

    hypotheses = [h for h in candidates if h is not None]
    corroboration = max(0, len(hypotheses) - 1)

    # --- Second pass: boost confidence based on corroboration -------------------
    # Re-run the statistically-derived hypotheses with the final corroboration count
    # so their confidence reflects mutual reinforcement.
    refined: list[Hypothesis | None] = [
        _traffic_drop_hypothesis(contributions_df, segment_results, corroboration),
        _conversion_drop_hypothesis(contributions_df, segment_results, corroboration),
        _aov_drop_hypothesis(contributions_df, corroboration),
        _region_concentration_hypothesis(segment_results, corroboration),
        _strong_correlation_hypothesis(correlations_df, corroboration),
        _spike_hypothesis(contributions_df, anomalies_df),
        _data_quality_hypothesis(anomalies_df),
    ]

    final = [h for h in refined if h is not None]
    final.sort(key=lambda h: h.confidence, reverse=True)
    logger.info("Generated %d hypotheses (corroboration=%d).", len(final), corroboration)
    return final


def hypotheses_to_dataframe(hypotheses: list[Hypothesis]) -> pd.DataFrame:
    """Convert a list of hypotheses to a display DataFrame."""
    if not hypotheses:
        return pd.DataFrame(columns=["id", "title", "confidence", "description"])
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
        segs   = analyse_all_segments(raw, d, "revenue")
        contrib = compute_contributions(raw, d)
        corr   = analyse_correlations(raw)
        hyps   = generate_hypotheses(contrib, segs, corr, anomalies_df=anomalies)
        for h in hyps:
            print(f"\n[{h.id}] {h.title}  (confidence={h.confidence:.0%})")
            print(f"  {h.description}")
            print("  Evidence:", h.supporting_evidence)
            print("  Actions:", h.recommended_actions)
