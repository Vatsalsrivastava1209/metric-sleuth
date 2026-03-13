"""
segmentation_analysis.py
========================
When an anomaly is detected, this module breaks down *which* segment
(region, device, traffic_source) diverged most from the baseline.

Approach
--------
For each anomaly date we compare the metric value for every segment
against the metric value on a "reference" window (the N days before the
anomaly).  The segment with the largest relative gap is flagged as the
primary contributor.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import numpy as np

from utils.config import DATE_COLUMN, SEGMENT_COLUMNS

logger = logging.getLogger(__name__)

# Default look-back period for the reference baseline (days)
_BASELINE_DAYS: int = 7


def _reference_window(
    df: pd.DataFrame,
    anomaly_date: pd.Timestamp,
    days: int = _BASELINE_DAYS,
) -> pd.DataFrame:
    """Return rows in the *days* before *anomaly_date* (exclusive)."""
    cutoff = anomaly_date - pd.Timedelta(days=days)
    return df[(df[DATE_COLUMN] >= cutoff) & (df[DATE_COLUMN] < anomaly_date)]


def segment_performance(
    df: pd.DataFrame,
    anomaly_date: pd.Timestamp,
    metric: str,
    segment_col: str,
    baseline_days: int = _BASELINE_DAYS,
) -> pd.DataFrame:
    """Compare a metric's performance per segment on the anomaly date vs. the baseline.

    Parameters
    ----------
    df:
        Full time-series DataFrame.
    anomaly_date:
        The date on which the anomaly occurred.
    metric:
        The metric column to analyse (e.g. ``"revenue"``).
    segment_col:
        Categorical column to group by (e.g. ``"region"``).
    baseline_days:
        Number of days before the anomaly used to build the reference mean.

    Returns
    -------
    pd.DataFrame
        Columns: ``segment_col``, ``anomaly_value``, ``baseline_mean``,
        ``absolute_change``, ``relative_change_pct``.
        Sorted by ``relative_change_pct`` ascending (worst first).
    """
    if segment_col not in df.columns:
        raise ValueError(f"Column '{segment_col}' not found in DataFrame.")
    if metric not in df.columns:
        raise ValueError(f"Metric '{metric}' not found in DataFrame.")

    # Data on the anomaly date
    anomaly_rows = df[df[DATE_COLUMN] == anomaly_date]
    # Reference window
    baseline_rows = _reference_window(df, anomaly_date, baseline_days)

    if anomaly_rows.empty:
        logger.warning("No data found for anomaly date %s", anomaly_date)
        return pd.DataFrame()

    anomaly_agg = anomaly_rows.groupby(segment_col)[metric].sum().rename("anomaly_value")
    baseline_agg = (
        baseline_rows.groupby(segment_col)[metric]
        .mean()
        .rename("baseline_mean")
    )

    result = pd.concat([anomaly_agg, baseline_agg], axis=1).reset_index()
    result["baseline_mean"] = result["baseline_mean"].fillna(result["anomaly_value"])
    result["absolute_change"] = result["anomaly_value"] - result["baseline_mean"]
    result["relative_change_pct"] = (
        result["absolute_change"] / result["baseline_mean"].replace(0, np.nan) * 100
    ).fillna(0)

    return result.sort_values("relative_change_pct").reset_index(drop=True)


def analyse_all_segments(
    df: pd.DataFrame,
    anomaly_date: pd.Timestamp,
    metric: str,
    segment_cols: list[str] | None = None,
    baseline_days: int = _BASELINE_DAYS,
) -> dict[str, pd.DataFrame]:
    """Run :func:`segment_performance` for every configured segment column.

    Parameters
    ----------
    df:
        Full time-series DataFrame.
    anomaly_date:
        Anomaly date to investigate.
    metric:
        Metric to analyse.
    segment_cols:
        Segment dimensions to iterate over.  Defaults to
        ``config.SEGMENT_COLUMNS``.
    baseline_days:
        Reference window length.

    Returns
    -------
    dict[str, pd.DataFrame]
        Mapping of ``segment_col → performance_table``.
    """
    if segment_cols is None:
        segment_cols = SEGMENT_COLUMNS

    results: dict[str, pd.DataFrame] = {}
    for col in segment_cols:
        try:
            perf = segment_performance(df, anomaly_date, metric, col, baseline_days)
            results[col] = perf
        except ValueError as exc:
            logger.error("Segmentation error for column '%s': %s", col, exc)

    return results


def get_most_impacted_segment(
    segment_results: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    """Find the single segment with the worst relative decline.

    Parameters
    ----------
    segment_results:
        Output of :func:`analyse_all_segments`.

    Returns
    -------
    dict
        Keys: ``dimension``, ``segment``, ``relative_change_pct``,
        ``absolute_change``.
    """
    worst: dict[str, Any] = {}
    worst_change = 0.0

    for dim, df_seg in segment_results.items():
        if df_seg.empty:
            continue
        row = df_seg.iloc[0]  # already sorted ascending (worst first)
        change = float(row["relative_change_pct"])
        if change < worst_change:
            worst_change = change
            worst = {
                "dimension": dim,
                "segment": row[dim],
                "relative_change_pct": round(change, 2),
                "absolute_change": round(float(row["absolute_change"]), 2),
            }

    return worst


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
        first_date = dates[0]
        segs = analyse_all_segments(raw, first_date, "revenue")
        for dim, table in segs.items():
            print(f"\n── {dim} ──")
            print(table.to_string(index=False))
