"""
causal_analysis.py
==================
Lightweight Difference-in-Differences (DiD) analysis for metric investigations.

Replaces pure correlation ("these metrics moved together") with a causal-lite
check: "did segment A move *differently* from all other segments, and by how
much?" A true DiD estimator controls for the macro trend by using the
unaffected segments as the counterfactual. This is what a senior analyst writes
in a brief — "CA revenue dropped 40% while TX/NY were flat" — and this module
produces that statement automatically.

Limitations
-----------
This is DiD in the panel-data sense, not a full causal inference framework.
It does not control for unobserved confounders. The output is evidence to
strengthen a hypothesis, not proof of causation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from utils.config import DATE_COLUMN, SEGMENT_COLUMNS

logger = logging.getLogger(__name__)


@dataclass
class DiDResult:
    """Difference-in-Differences estimate for a single segment value."""

    dimension: str        # e.g. "region"
    treated_segment: str  # e.g. "California"
    metric: str           # e.g. "revenue"
    pre_treated: float    # treated segment mean before anomaly date
    post_treated: float   # treated segment mean on/after anomaly date
    pre_control: float    # control (all other segments) mean before
    post_control: float   # control mean after
    did_estimate: float   # (post_t - pre_t) - (post_c - pre_c)
    did_pct: float        # did_estimate as % of pre_treated baseline
    causal_signal: bool   # True when |did_pct| >= threshold

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "treated_segment": self.treated_segment,
            "metric": self.metric,
            "pre_treated": round(self.pre_treated, 4),
            "post_treated": round(self.post_treated, 4),
            "pre_control": round(self.pre_control, 4),
            "post_control": round(self.post_control, 4),
            "did_estimate": round(self.did_estimate, 4),
            "did_pct": round(self.did_pct, 2),
            "causal_signal": self.causal_signal,
        }

    def to_narrative(self) -> str:
        direction = "declined" if self.did_pct < 0 else "increased"
        return (
            f"{self.treated_segment} {self.metric} {direction} "
            f"{abs(self.did_pct):.1f}% more than the rest of the portfolio "
            f"after controlling for the macro trend "
            f"(DiD estimate: {self.did_estimate:+.2f})."
        )


def _segment_means(
    df: pd.DataFrame,
    dimension: str,
    segment_value: str,
    metric: str,
    anomaly_date: pd.Timestamp,
    pre_window: int,
) -> tuple[float, float, float, float] | None:
    """Return (pre_treated, post_treated, pre_control, post_control) or None."""
    if dimension not in df.columns or metric not in df.columns or DATE_COLUMN not in df.columns:
        return None

    df = df.copy()
    df[DATE_COLUMN] = pd.to_datetime(df[DATE_COLUMN], errors="coerce")
    anomaly_date = pd.Timestamp(anomaly_date).normalize()

    cutoff_start = anomaly_date - pd.Timedelta(days=pre_window)

    pre_mask  = (df[DATE_COLUMN] >= cutoff_start) & (df[DATE_COLUMN] < anomaly_date)
    post_mask = df[DATE_COLUMN] >= anomaly_date

    treated_mask  = df[dimension] == segment_value
    control_mask  = df[dimension] != segment_value

    def _safe_mean(mask: pd.Series) -> float | None:
        vals = df.loc[mask, metric].dropna()
        return float(vals.mean()) if not vals.empty else None

    pre_t  = _safe_mean(pre_mask  & treated_mask)
    post_t = _safe_mean(post_mask & treated_mask)
    pre_c  = _safe_mean(pre_mask  & control_mask)
    post_c = _safe_mean(post_mask & control_mask)

    if any(v is None for v in [pre_t, post_t, pre_c, post_c]):
        return None
    if pre_t == 0:
        return None

    return pre_t, post_t, pre_c, post_c


def compute_did(
    df: pd.DataFrame,
    anomaly_date: pd.Timestamp | str,
    metric: str = "revenue",
    dimensions: list[str] | None = None,
    pre_window: int = 14,
    causal_threshold_pct: float = 15.0,
) -> list[DiDResult]:
    """Run DiD for all segment values across all requested dimensions.

    For each dimension (e.g. "region"), identifies the worst-affected segment
    value and computes the DiD estimate against the remaining segments as
    control. Returns results sorted by |did_pct| descending.

    Parameters
    ----------
    df:
        Full time-series DataFrame with a date column, metric columns,
        and at least one segment dimension column.
    anomaly_date:
        The date on which the anomaly occurred (treatment date).
    metric:
        The metric to analyse (default: "revenue").
    dimensions:
        Segment dimensions to test. Defaults to ``config.SEGMENT_COLUMNS``.
    pre_window:
        Days of history before anomaly_date used as the pre-treatment window.
    causal_threshold_pct:
        Minimum |did_pct| to set ``causal_signal=True``. Signals below this
        are considered noise.

    Returns
    -------
    list[DiDResult]
        One result per (dimension, treated_segment) pair, sorted by effect size.
    """
    if dimensions is None:
        dimensions = SEGMENT_COLUMNS

    anomaly_date = pd.Timestamp(anomaly_date).normalize()
    results: list[DiDResult] = []

    for dim in dimensions:
        if dim not in df.columns:
            continue

        segment_values = df[dim].dropna().unique().tolist()
        if len(segment_values) < 2:
            continue

        dim_results: list[DiDResult] = []
        for seg_val in segment_values:
            means = _segment_means(df, dim, str(seg_val), metric, anomaly_date, pre_window)
            if means is None:
                continue

            pre_t, post_t, pre_c, post_c = means
            did = (post_t - pre_t) - (post_c - pre_c)
            did_pct = (did / abs(pre_t)) * 100

            dim_results.append(DiDResult(
                dimension=dim,
                treated_segment=str(seg_val),
                metric=metric,
                pre_treated=pre_t,
                post_treated=post_t,
                pre_control=pre_c,
                post_control=post_c,
                did_estimate=did,
                did_pct=did_pct,
                causal_signal=abs(did_pct) >= causal_threshold_pct,
            ))

        # Surface only the worst-affected segment per dimension
        dim_results.sort(key=lambda r: abs(r.did_pct), reverse=True)
        if dim_results:
            results.append(dim_results[0])

    logger.info(
        "DiD analysis complete: %d dimension(s) tested, %d causal signal(s) found.",
        len(dimensions),
        sum(1 for r in results if r.causal_signal),
    )
    return results


def did_results_to_dataframe(results: list[DiDResult]) -> pd.DataFrame:
    """Convert DiD results to a display DataFrame."""
    if not results:
        return pd.DataFrame(columns=[
            "dimension", "treated_segment", "did_pct", "causal_signal", "narrative"
        ])
    rows = [
        {
            **r.to_dict(),
            "narrative": r.to_narrative(),
        }
        for r in results
    ]
    return pd.DataFrame(rows).sort_values("did_pct")
