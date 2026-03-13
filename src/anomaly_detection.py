"""
anomaly_detection.py
====================
Z-score–based anomaly detection for time-series business metrics.

Strategy
--------
For every metric we compute a rolling Z-score using a configurable window.
A point is flagged as an anomaly when ``|z| >= threshold``.  Rolling
statistics (rather than global ones) make the detector adaptive to gradual
trends and seasonality.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from utils.config import (
    ANOMALY_METRICS,
    ANOMALY_ROLLING_WINDOW,
    ANOMALY_Z_THRESHOLD,
    DATE_COLUMN,
)

logger = logging.getLogger(__name__)


@dataclass
class AnomalyResult:
    """Container for a single detected anomaly."""

    date: pd.Timestamp
    metric: str
    observed_value: float
    expected_value: float   # rolling mean at that point
    z_score: float
    deviation_score: float  # |z_score|
    direction: str          # "drop" or "spike"

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "metric": self.metric,
            "observed_value": round(self.observed_value, 4),
            "expected_value": round(self.expected_value, 4),
            "z_score": round(self.z_score, 4),
            "deviation_score": round(self.deviation_score, 4),
            "direction": self.direction,
        }


def _rolling_zscore(
    series: pd.Series,
    window: int,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (z_scores, rolling_mean, rolling_std) for *series*."""
    roll_mean = series.rolling(window=window, min_periods=1).mean()
    roll_std = series.rolling(window=window, min_periods=1).std().fillna(1e-9)
    z_scores = (series - roll_mean) / roll_std
    return z_scores, roll_mean, roll_std


def detect_anomalies(
    df: pd.DataFrame,
    metrics: list[str] | None = None,
    threshold: float = ANOMALY_Z_THRESHOLD,
    window: int = ANOMALY_ROLLING_WINDOW,
) -> pd.DataFrame:
    """Detect anomalies across multiple metrics using rolling Z-scores.

    Parameters
    ----------
    df:
        DataFrame containing at least the ``date`` column and the requested
        *metrics* columns, sorted chronologically.
    metrics:
        Column names to scan.  Defaults to ``config.ANOMALY_METRICS``.
    threshold:
        Absolute Z-score above which a data point is flagged.
    window:
        Rolling window size (number of rows / days).

    Returns
    -------
    pd.DataFrame
        One row per detected anomaly with columns:
        ``date``, ``metric``, ``observed_value``, ``expected_value``,
        ``z_score``, ``deviation_score``, ``direction``.
        Empty DataFrame when no anomalies are found.
    """
    if metrics is None:
        metrics = ANOMALY_METRICS

    results: list[dict] = []

    for metric in metrics:
        if metric not in df.columns:
            logger.warning("Metric '%s' not found in DataFrame — skipping.", metric)
            continue

        series = df[metric].astype(float)
        z_scores, roll_mean, _ = _rolling_zscore(series, window)

        anomaly_mask = z_scores.abs() >= threshold

        for idx in df.index[anomaly_mask]:
            z = z_scores.loc[idx]
            results.append(
                AnomalyResult(
                    date=df.loc[idx, DATE_COLUMN],
                    metric=metric,
                    observed_value=series.loc[idx],
                    expected_value=roll_mean.loc[idx],
                    z_score=z,
                    deviation_score=abs(z),
                    direction="drop" if z < 0 else "spike",
                ).to_dict()
            )

    if not results:
        logger.info("No anomalies detected for metrics: %s", metrics)
        return pd.DataFrame(
            columns=[
                "date", "metric", "observed_value", "expected_value",
                "z_score", "deviation_score", "direction",
            ]
        )

    anomalies_df = pd.DataFrame(results).sort_values(
        ["date", "deviation_score"], ascending=[True, False]
    ).reset_index(drop=True)

    logger.info("Detected %d anomaly records.", len(anomalies_df))
    return anomalies_df


def get_anomaly_dates(anomalies_df: pd.DataFrame) -> list[pd.Timestamp]:
    """Return the unique dates on which at least one anomaly occurred."""
    if anomalies_df.empty:
        return []
    return sorted(anomalies_df["date"].unique().tolist())


def get_worst_anomaly(anomalies_df: pd.DataFrame) -> dict | None:
    """Return the single anomaly with the highest deviation score, or None."""
    if anomalies_df.empty:
        return None
    worst = anomalies_df.sort_values("deviation_score", ascending=False).iloc[0]
    return worst.to_dict()


def annotate_dataframe(
    df: pd.DataFrame,
    anomalies_df: pd.DataFrame,
) -> pd.DataFrame:
    """Add a boolean ``is_anomaly`` column to *df* for quick chart colouring.

    Parameters
    ----------
    df:
        Original time-series DataFrame.
    anomalies_df:
        Output from :func:`detect_anomalies`.

    Returns
    -------
    pd.DataFrame
        Copy of *df* with an ``is_anomaly`` column.
    """
    df = df.copy()
    anomaly_dates = set(anomalies_df["date"].tolist()) if not anomalies_df.empty else set()
    df["is_anomaly"] = df[DATE_COLUMN].isin(anomaly_dates)
    return df


# ── Example usage ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
    from src.data_loader import load_data

    logging.basicConfig(level=logging.INFO)
    raw = load_data("data/sample_ecommerce.csv")
    anomalies = detect_anomalies(raw)
    print(anomalies.to_string(index=False))
