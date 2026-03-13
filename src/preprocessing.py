"""
preprocessing.py
================
Feature-engineering steps that transform the raw DataFrame into a form
suitable for anomaly detection and correlation analysis.
"""

from __future__ import annotations

import pandas as pd
import numpy as np

from utils.config import DATE_COLUMN


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """Attach calendar-derived columns to the DataFrame.

    Adds
    ----
    ``day_of_week`` (0 = Monday … 6 = Sunday),
    ``week_of_year``,
    ``month``,
    ``is_weekend`` (bool).

    Parameters
    ----------
    df:
        DataFrame containing a ``date`` column of type ``datetime64``.

    Returns
    -------
    pd.DataFrame
        Original DataFrame with additional time columns (in-place copy).
    """
    df = df.copy()
    df["day_of_week"] = df[DATE_COLUMN].dt.dayofweek
    df["week_of_year"] = df[DATE_COLUMN].dt.isocalendar().week.astype(int)
    df["month"] = df[DATE_COLUMN].dt.month
    df["is_weekend"] = df["day_of_week"].isin([5, 6])
    return df


def compute_rolling_stats(
    df: pd.DataFrame,
    metrics: list[str],
    window: int = 7,
) -> pd.DataFrame:
    """Compute rolling mean and standard deviation for each metric.

    Parameters
    ----------
    df:
        Input DataFrame sorted by date.
    metrics:
        Column names to compute rolling statistics for.
    window:
        Rolling window size in rows (days).

    Returns
    -------
    pd.DataFrame
        DataFrame augmented with ``<metric>_rolling_mean`` and
        ``<metric>_rolling_std`` columns.
    """
    df = df.copy()
    for metric in metrics:
        df[f"{metric}_rolling_mean"] = (
            df[metric].rolling(window=window, min_periods=1).mean()
        )
        df[f"{metric}_rolling_std"] = (
            df[metric].rolling(window=window, min_periods=1).std().fillna(0)
        )
    return df


def compute_pct_change(
    df: pd.DataFrame,
    metrics: list[str],
    periods: int = 1,
) -> pd.DataFrame:
    """Add day-over-day (or N-period) percentage change columns.

    Parameters
    ----------
    df:
        Input DataFrame.
    metrics:
        Metrics to compute changes for.
    periods:
        Number of periods to shift when computing the difference.

    Returns
    -------
    pd.DataFrame
        DataFrame with ``<metric>_pct_change`` columns.
    """
    df = df.copy()
    for metric in metrics:
        df[f"{metric}_pct_change"] = df[metric].pct_change(periods=periods) * 100
    return df


def normalize_metrics(
    df: pd.DataFrame,
    metrics: list[str],
) -> pd.DataFrame:
    """Min-max normalise selected columns to the [0, 1] range.

    Useful for visualising metrics with different scales on the same chart.

    Parameters
    ----------
    df:
        Input DataFrame.
    metrics:
        Metrics to normalise.

    Returns
    -------
    pd.DataFrame
        DataFrame with extra ``<metric>_normalized`` columns.
    """
    df = df.copy()
    for metric in metrics:
        col = df[metric]
        min_val, max_val = col.min(), col.max()
        denom = max_val - min_val if max_val != min_val else 1.0
        df[f"{metric}_normalized"] = (col - min_val) / denom
    return df


def preprocess(
    df: pd.DataFrame,
    metrics: list[str],
    rolling_window: int = 7,
) -> pd.DataFrame:
    """Run the full preprocessing pipeline in one call.

    Applies :func:`add_time_features`, :func:`compute_rolling_stats`,
    :func:`compute_pct_change`, and :func:`normalize_metrics` sequentially.

    Parameters
    ----------
    df:
        Raw DataFrame from :func:`data_loader.load_data`.
    metrics:
        Metric columns to enrich.
    rolling_window:
        Window size passed to :func:`compute_rolling_stats`.

    Returns
    -------
    pd.DataFrame
        Fully preprocessed DataFrame.
    """
    df = add_time_features(df)
    df = compute_rolling_stats(df, metrics, window=rolling_window)
    df = compute_pct_change(df, metrics)
    df = normalize_metrics(df, metrics)
    return df


# ── Example usage ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
    from src.data_loader import load_data
    from utils.config import ANOMALY_METRICS, ANOMALY_ROLLING_WINDOW

    raw = load_data("data/sample_ecommerce.csv")
    processed = preprocess(raw, ANOMALY_METRICS, ANOMALY_ROLLING_WINDOW)
    print(processed.head(10))
