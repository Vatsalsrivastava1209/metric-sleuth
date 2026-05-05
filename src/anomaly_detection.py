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
    ANOMALY_MIN_COVERAGE_RATIO,
    ANOMALY_MIN_HISTORY_POINTS,
    ANOMALY_METRICS,
    ANOMALY_METRIC_THRESHOLDS,
    ANOMALY_METRIC_WINDOWS,
    ANOMALY_MIN_STD_THRESHOLD,
    ANOMALY_ROLLING_WINDOW,
    ANOMALY_Z_THRESHOLD,
    DATE_COLUMN,
)

logger = logging.getLogger(__name__)

try:
    import ruptures as rpt  # type: ignore
    _RUPTURES_AVAILABLE = True
except ImportError:
    _RUPTURES_AVAILABLE = False


@dataclass
class AnomalyResult:
    """Container for a single detected anomaly."""

    date: pd.Timestamp
    metric: str
    observed_value: float
    expected_value: float   # lagged rolling median baseline at that point
    z_score: float
    deviation_score: float  # |z_score|
    direction: str          # "drop" or "spike"
    detector: str = "z_score"  # which detector flagged this row

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "metric": self.metric,
            "observed_value": round(self.observed_value, 4),
            "expected_value": round(self.expected_value, 4),
            "z_score": round(self.z_score, 4),
            "deviation_score": round(self.deviation_score, 4),
            "direction": self.direction,
            "detector": self.detector,
        }


def _rolling_zscore(
    series: pd.Series,
    window: int,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (z_scores, rolling_median, robust_std) for *series*.

    Uses robust estimators (Rolling Median and IQR-based Standard Deviation)
    to prevent anomaly masking (where large spikes skew the baseline).
    The current observation is excluded from its own rolling baseline.
    """
    history = series.shift(1)
    min_periods = max(3, min(window, 5))

    roll_mean = history.rolling(window=window, min_periods=min_periods).median()

    q75 = history.rolling(window=window, min_periods=min_periods).quantile(0.75)
    q25 = history.rolling(window=window, min_periods=min_periods).quantile(0.25)
    iqr = q75 - q25
    roll_std = iqr / 1.34898

    naive_std = history.rolling(window=window, min_periods=min_periods).std()
    roll_std = roll_std.where(roll_std > 0.0001, naive_std)

    # Low-variance guard: mask windows where the metric barely moved
    low_variance_mask = roll_std < ANOMALY_MIN_STD_THRESHOLD
    roll_std_safe = roll_std.where(~low_variance_mask, other=np.nan)

    z_scores = (series - roll_mean) / roll_std_safe  # NaN where variance is too low
    pct_delta = ((series - roll_mean).abs() / roll_mean.abs().replace(0, np.nan)).fillna(0.0)
    material_change_mask = low_variance_mask & (pct_delta >= 0.20)
    if material_change_mask.any():
        z_scores = z_scores.where(
            ~material_change_mask,
            other=np.sign(series - roll_mean) * np.inf,
        )
    if low_variance_mask.any():
        n_masked = int(low_variance_mask.sum())
        logger.debug(
            "Low-variance guard masked %d point(s); material changes are escalated separately.",
            n_masked,
        )
    return z_scores, roll_mean, roll_std


def _calendar_coverage_ratio(dates: pd.Series) -> float:
    """Estimate how complete the observed calendar is for a daily series."""
    normalized = pd.to_datetime(dates, errors="coerce").dropna().sort_values()
    if normalized.empty:
        return 0.0
    if len(normalized) == 1:
        return 1.0
    full_range = pd.date_range(normalized.iloc[0], normalized.iloc[-1], freq="D")
    if len(full_range) == 0:
        return 1.0
    return round(len(normalized.dt.normalize().unique()) / len(full_range), 4)


def detect_anomalies(
    df: pd.DataFrame,
    metrics: list[str] | None = None,
    threshold: float | None = None,
    window: int | None = None,
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
    coverage_ratio = _calendar_coverage_ratio(df[DATE_COLUMN]) if DATE_COLUMN in df.columns else 0.0

    if len(df) < ANOMALY_MIN_HISTORY_POINTS:
        logger.warning(
            "Skipping anomaly detection: history too short (%d rows, minimum=%d).",
            len(df),
            ANOMALY_MIN_HISTORY_POINTS,
        )
        return pd.DataFrame(
            columns=[
                "date", "metric", "observed_value", "expected_value",
                "z_score", "deviation_score", "direction",
            ]
        )

    if coverage_ratio < ANOMALY_MIN_COVERAGE_RATIO:
        logger.warning(
            "Skipping anomaly detection: calendar coverage ratio %.2f is below %.2f.",
            coverage_ratio,
            ANOMALY_MIN_COVERAGE_RATIO,
        )
        return pd.DataFrame(
            columns=[
                "date", "metric", "observed_value", "expected_value",
                "z_score", "deviation_score", "direction",
            ]
        )

    for metric in metrics:
        if metric not in df.columns:
            logger.warning("Metric '%s' not found in DataFrame — skipping.", metric)
            continue

        series = df[metric].astype(float)
        metric_threshold = threshold if threshold is not None else ANOMALY_METRIC_THRESHOLDS.get(metric, ANOMALY_Z_THRESHOLD)
        metric_window = window if window is not None else ANOMALY_METRIC_WINDOWS.get(metric, ANOMALY_ROLLING_WINDOW)
        z_scores, roll_mean, _ = _rolling_zscore(series, metric_window)

        # NaN Z-scores from the low-variance guard are safely excluded here
        anomaly_mask = z_scores.abs() >= metric_threshold

        for idx in df.index[anomaly_mask]:
            z = z_scores.loc[idx]
            if pd.isna(z):   # guard: skip any residual NaN (belt-and-suspenders)
                continue
            results.append(
                AnomalyResult(
                    date=df.loc[idx, DATE_COLUMN],
                    metric=metric,
                    observed_value=series.loc[idx],
                    expected_value=roll_mean.loc[idx],
                    z_score=z,
                    deviation_score=abs(z),
                    direction="drop" if z < 0 else "spike",
                    detector="z_score",
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

    logger.info("Detected %d anomaly records (detector=z_score).", len(anomalies_df))
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


def detect_changepoints(
    df: pd.DataFrame,
    metrics: list[str] | None = None,
    min_size: int = 7,
    penalty: float = 3.0,
) -> pd.DataFrame:
    """Detect level-shift changepoints using the PELT algorithm (ruptures).

    Z-score detects point spikes. PELT detects *sustained* level shifts —
    the baseline moves and never returns. This catches post-iOS-update
    plateaus, post-promo baseline changes, and algorithm penalty recoveries
    that z-score systematically misses because the new level becomes the
    rolling mean.

    Parameters
    ----------
    df:
        DataFrame with a ``date`` column and metric columns.
    metrics:
        Columns to scan. Defaults to ``config.ANOMALY_METRICS``.
    min_size:
        Minimum number of points between changepoints (avoids over-segmentation).
    penalty:
        PELT penalty (BIC-like). Higher = fewer changepoints detected.

    Returns
    -------
    pd.DataFrame
        One row per detected changepoint with columns:
        ``date``, ``metric``, ``observed_value``, ``expected_value``,
        ``z_score``, ``deviation_score``, ``direction``, ``detector``.
        Empty DataFrame when ruptures is not installed or no shifts found.
    """
    if not _RUPTURES_AVAILABLE:
        logger.info("ruptures not installed — changepoint detection skipped. Run: pip install ruptures")
        return pd.DataFrame(
            columns=["date", "metric", "observed_value", "expected_value",
                     "z_score", "deviation_score", "direction", "detector"]
        )

    if metrics is None:
        metrics = ANOMALY_METRICS

    if len(df) < ANOMALY_MIN_HISTORY_POINTS:
        return pd.DataFrame(
            columns=["date", "metric", "observed_value", "expected_value",
                     "z_score", "deviation_score", "direction", "detector"]
        )

    results: list[dict] = []

    for metric in metrics:
        if metric not in df.columns:
            continue

        series = df[metric].astype(float).fillna(method="ffill").values
        if len(series) < min_size * 2:
            continue

        try:
            algo = rpt.Pelt(model="rbf", min_size=min_size).fit(series)
            breakpoints = algo.predict(pen=penalty)
        except Exception as exc:
            logger.warning("PELT failed for metric '%s': %s", metric, exc)
            continue

        # breakpoints includes len(series) as the final sentinel — exclude it
        breakpoints = [bp for bp in breakpoints if bp < len(series)]

        for bp in breakpoints:
            if bp == 0:
                continue
            pre_window = series[max(0, bp - min_size): bp]
            post_window = series[bp: min(len(series), bp + min_size)]
            if len(pre_window) == 0 or len(post_window) == 0:
                continue

            pre_mean = float(np.median(pre_window))
            post_mean = float(np.median(post_window))
            if pre_mean == 0:
                continue

            shift_pct = (post_mean - pre_mean) / abs(pre_mean)
            # Only surface shifts larger than 10% to avoid noise
            if abs(shift_pct) < 0.10:
                continue

            date_val = df.iloc[bp][DATE_COLUMN] if DATE_COLUMN in df.columns else pd.NaT
            results.append({
                "date": date_val,
                "metric": metric,
                "observed_value": round(post_mean, 4),
                "expected_value": round(pre_mean, 4),
                "z_score": round(shift_pct * 10, 4),  # scaled for comparability with z-scores
                "deviation_score": round(abs(shift_pct) * 10, 4),
                "direction": "drop" if shift_pct < 0 else "spike",
                "detector": "changepoint",
            })

    if not results:
        logger.info("No changepoints detected for metrics: %s", metrics)
        return pd.DataFrame(
            columns=["date", "metric", "observed_value", "expected_value",
                     "z_score", "deviation_score", "direction", "detector"]
        )

    return pd.DataFrame(results).sort_values(
        ["date", "deviation_score"], ascending=[True, False]
    ).reset_index(drop=True)


# ── Example usage ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
    from src.data_loader import load_data

    logging.basicConfig(level=logging.INFO)
    raw = load_data("data/sample_ecommerce.csv")
    anomalies = detect_anomalies(raw)
    print(anomalies.to_string(index=False))
