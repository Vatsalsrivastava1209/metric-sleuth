"""
contribution_analysis.py
========================
Estimates the proportional contribution of each factor (traffic drop,
conversion rate drop, etc.) to an observed revenue decline.

Method
------
We use a simple multiplicative decomposition:

    revenue = traffic × conversion_rate × avg_order_value

The change in revenue can therefore be approximately attributed by
computing how much each factor changed relative to the baseline and
weighting those changes by their elasticity (coefficient of variation
w.r.t. revenue over the full history).
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

    records: list[dict] = []
    total_drop_magnitude = 0.0

    # First pass: compute raw changes
    raw: list[tuple[str, float, float, float, float]] = []
    for factor in factors:
        if factor not in df.columns:
            logger.warning("Factor '%s' not in DataFrame — skipping.", factor)
            continue

        baseline = _get_window_mean(df, factor, anomaly_date, baseline_days)
        anomaly_val = float(anomaly_rows[factor].mean())
        abs_change = anomaly_val - baseline
        pct_change = (abs_change / baseline * 100) if baseline != 0 else 0.0
        raw.append((factor, baseline, anomaly_val, abs_change, pct_change))
        total_drop_magnitude += abs(abs_change / baseline) if baseline != 0 else 0

    # Second pass: normalise contributions
    for factor, baseline, anomaly_val, abs_change, pct_change in raw:
        local_magnitude = abs(abs_change / baseline) if baseline != 0 else 0
        contribution = (
            (local_magnitude / total_drop_magnitude * 100)
            if total_drop_magnitude > 0
            else 0.0
        )
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
