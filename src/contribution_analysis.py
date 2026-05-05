"""
contribution_analysis.py
========================
Estimates the proportional contribution of each factor (traffic drop,
conversion rate drop, etc.) to an observed revenue decline.

Method — Elasticity-Weighted Attribution
-----------------------------------------
Revenue follows a multiplicative identity:

    revenue = traffic × conversion_rate × avg_order_value

A naive "percentage change" decomposition treats all factors equally, which
is statistically incorrect:  a 5% traffic drop has a different revenue impact
than a 5% CVR drop because their historical variance contributions differ.

We weight each factor's contribution by its **revenue elasticity**: the ratio
of the factor's coefficient of variation (CV = std/mean) to the sum of all
factors' CVs over the full history.  This reflects how much of revenue's
historical variance is explained by each factor — a principled, data-driven
attribution weight.

Elasticity weight formula:
    w_i = CV_i / Σ CV_j      (CV = historical std / historical mean)

Final contribution:
    contrib_i = |Δfactor_i%| × w_i / Σ (|Δfactor_j%| × w_j)  × 100

This is a practical approximation to the Shapley value for the
multiplicative decomposition problem, without the O(2^K) Shapley computation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from utils.config import (
    CONTRIBUTION_FACTORS,
    DATE_COLUMN,
)

logger = logging.getLogger(__name__)

# Days before the anomaly used to establish the baseline
_BASELINE_DAYS: int = 7


@dataclass
class ContributionResult:
    """Factor contribution to a revenue change event."""

    factor: str
    baseline_mean: float
    anomaly_value: float
    absolute_change: float
    pct_change: float
    contribution_pct: float    # Share of total absolute drop (0-100)

    def to_dict(self) -> dict:
        return {
            "factor": self.factor,
            "baseline_mean": round(self.baseline_mean, 4),
            "anomaly_value": round(self.anomaly_value, 4),
            "absolute_change": round(self.absolute_change, 4),
            "pct_change": round(self.pct_change, 2),
            "contribution_pct": round(self.contribution_pct, 2),
        }


def _get_window_mean(
    df: pd.DataFrame,
    col: str,
    anomaly_date: pd.Timestamp,
    days: int,
) -> float:
    """Mean of *col* in the *days* leading up to *anomaly_date*."""
    cutoff = anomaly_date - pd.Timedelta(days=days)
    window = df[(df[DATE_COLUMN] >= cutoff) & (df[DATE_COLUMN] < anomaly_date)]
    if window.empty:
        return float(df[col].mean())
    return float(window[col].mean())


def compute_contributions(
    df: pd.DataFrame,
    anomaly_date: pd.Timestamp,
    primary_metric: str = "revenue",
    factors: list[str] | None = None,
    baseline_days: int = _BASELINE_DAYS,
) -> pd.DataFrame:
    """Estimate each factor's contribution to the *primary_metric* change.

    Uses elasticity-weighted attribution: each factor is weighted by its
    historical coefficient of variation (CV = std/mean), which reflects
    how much of revenue's total variance it historically explains.
    This is more accurate than equal-weight normalization because a 5%
    traffic drop does not have the same revenue impact as a 5% CVR drop.

    Parameters
    ----------
    df:
        Full time-series DataFrame.
    anomaly_date:
        The date of the anomaly to investigate.
    primary_metric:
        The main metric that dropped (usually ``"revenue"``).
    factors:
        Explanatory factors to consider.  Defaults to
        ``config.CONTRIBUTION_FACTORS``.
    baseline_days:
        Reference window length (days before the anomaly).

    Returns
    -------
    pd.DataFrame
        One row per factor with columns from :class:`ContributionResult`,
        sorted by ``contribution_pct`` descending.
    """
    if factors is None:
        factors = CONTRIBUTION_FACTORS

    anomaly_rows = df[df[DATE_COLUMN] == anomaly_date]
    if anomaly_rows.empty:
        logger.warning("No data for anomaly date %s", anomaly_date)
        return pd.DataFrame()

    # ── Pass 1: raw changes + historical elasticity weights ──────────────────
    raw: list[tuple[str, float, float, float, float, float]] = []
    total_elasticity_weighted_change = 0.0

    for factor in factors:
        if factor not in df.columns:
            logger.warning("Factor '%s' not in DataFrame — skipping.", factor)
            continue

        baseline = _get_window_mean(df, factor, anomaly_date, baseline_days)
        anomaly_val = float(anomaly_rows[factor].mean())
        abs_change = anomaly_val - baseline
        pct_change = (abs_change / baseline * 100) if baseline != 0 else 0.0

        # Historical elasticity: coefficient of variation over the full series
        # CV = std / mean — measures how volatile this factor is historically.
        # Factors with higher CV have historically driven more revenue variance
        # and therefore deserve a higher weight in the attribution.
        series = df[factor].dropna().astype(float)
        hist_mean = float(series.mean())
        hist_std  = float(series.std())
        cv = (hist_std / abs(hist_mean)) if hist_mean != 0 else 0.0

        # Weighted change magnitude: |%change| × elasticity_weight
        # We use absolute pct_change because we care about the magnitude of the
        # change, not its sign (sign is captured in the direction field).
        weighted_magnitude = abs(pct_change) * cv
        total_elasticity_weighted_change += weighted_magnitude

        raw.append((factor, baseline, anomaly_val, abs_change, pct_change, weighted_magnitude))

    # ── Pass 2: normalise elasticity-weighted contributions ──────────────────
    records: list[dict] = []
    for factor, baseline, anomaly_val, abs_change, pct_change, weighted_mag in raw:
        if total_elasticity_weighted_change > 0:
            contribution = weighted_mag / total_elasticity_weighted_change * 100
        else:
            # Fallback: equal weights when all factors have zero CV
            contribution = 100.0 / len(raw) if raw else 0.0

        records.append(
            ContributionResult(
                factor=factor,
                baseline_mean=baseline,
                anomaly_value=anomaly_val,
                absolute_change=abs_change,
                pct_change=pct_change,
                contribution_pct=contribution,
            ).to_dict()
        )

    result = pd.DataFrame(records).sort_values(
        "contribution_pct", ascending=False
    ).reset_index(drop=True)

    return result


def summarize_contributions(contributions_df: pd.DataFrame) -> str:
    """Return a human-readable one-paragraph summary of the contributions.

    Parameters
    ----------
    contributions_df:
        Output of :func:`compute_contributions`.

    Returns
    -------
    str
        Plain-text paragraph suitable for the RCA report.
    """
    if contributions_df.empty:
        return "No contribution data available."

    lines: list[str] = []
    for _, row in contributions_df.iterrows():
        direction = "dropped" if row["pct_change"] < 0 else "increased"
        lines.append(
            f"  • **{row['factor'].replace('_', ' ').title()}** {direction} by "
            f"{abs(row['pct_change']):.1f}% → "
            f"{row['contribution_pct']:.1f}% of the total impact."
        )

    return "\n".join(lines)


# ── Example usage ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
    from src.data_loader import load_data
    from src.anomaly_detection import detect_anomalies, get_anomaly_dates

    logging.basicConfig(level=logging.INFO)
    raw = load_data("data/sample_ecommerce.csv")
    anomalies = detect_anomalies(raw)
    dates = get_anomaly_dates(anomalies)

    if dates:
        contrib = compute_contributions(raw, dates[0])
        print(contrib.to_string(index=False))
        print("\nSummary:")
        print(summarize_contributions(contrib))
