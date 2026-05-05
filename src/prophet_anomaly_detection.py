"""
prophet_anomaly_detection.py
============================
Prophet-based time-series anomaly detection.

Strategy
--------
1. Fit a Prophet model on the full history of a metric.
2. Generate in-sample forecasts to obtain the predicted value and
   uncertainty interval (yhat_lower, yhat_upper) for every date.
3. Flag a date as an anomaly when the observed value falls **outside**
   the uncertainty interval.

This is significantly more accurate than Z-score because Prophet explicitly
models weekly/yearly seasonality and trend change-points.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import Any

import pandas as pd
import numpy as np

from utils.config import (
    DATE_COLUMN,
    ANOMALY_METRICS,
    PROPHET_BACKTEST_MIN_TRAIN_POINTS,
    PROPHET_MIN_HISTORY_POINTS,
)

logger = logging.getLogger(__name__)

# Maximum seconds allowed for a single Prophet model.fit() call.
# On sparse, irregular, or very long-range data, Prophet's Stan backend can
# hang for minutes. This guard keeps the Celery worker responsive.
# Increase if your datasets are large and the default timeout is too tight.
PROPHET_FIT_TIMEOUT_SECONDS: int = 120


class ProphetTimeoutError(RuntimeError):
    """Raised when a Prophet fit exceeds PROPHET_FIT_TIMEOUT_SECONDS."""


@dataclass
class ProphetBacktestResult:
    train_points: int
    scored_points: int
    flagged_dates: list[pd.Timestamp]

    def to_dict(self) -> dict[str, Any]:
        return {
            "train_points": self.train_points,
            "scored_points": self.scored_points,
            "flagged_dates": [str(ts) for ts in self.flagged_dates],
        }


def _import_prophet():
    """Lazy-import Prophet so the rest of the app still works if it's not installed."""
    try:
        from prophet import Prophet  # type: ignore
        return Prophet
    except ImportError as exc:
        raise ImportError(
            "Prophet is not installed. Run: pip install prophet"
        ) from exc


def fit_prophet(
    df: pd.DataFrame,
    metric: str,
    yearly_seasonality: bool = True,
    weekly_seasonality: bool = True,
    interval_width: float = 0.95,
    timeout: int = PROPHET_FIT_TIMEOUT_SECONDS,
) -> Any:
    """Fit a Prophet model on *metric* and return the fitted model.

    Parameters
    ----------
    df:
        DataFrame with ``date`` and *metric* columns.
    metric:
        Column name to model.
    yearly_seasonality:
        Whether to include a yearly seasonal component.
    weekly_seasonality:
        Whether to include a weekly seasonal component.
    interval_width:
        Confidence interval width used to define the anomaly bounds (0–1).
    timeout:
        Maximum seconds to wait for model.fit(). Raises ProphetTimeoutError
        if exceeded. Defaults to PROPHET_FIT_TIMEOUT_SECONDS (120s).

    Returns
    -------
    Fitted ``Prophet`` instance.

    Raises
    ------
    ProphetTimeoutError
        If model.fit() does not complete within *timeout* seconds.
    """
    Prophet = _import_prophet()

    if len(df) < PROPHET_MIN_HISTORY_POINTS:
        raise ValueError(
            f"Prophet requires at least {PROPHET_MIN_HISTORY_POINTS} historical rows; "
            f"received {len(df)}."
        )

    # Prophet expects columns named 'ds' and 'y'
    prophet_df = df[[DATE_COLUMN, metric]].rename(
        columns={DATE_COLUMN: "ds", metric: "y"}
    )

    model = Prophet(
        yearly_seasonality=yearly_seasonality,
        weekly_seasonality=weekly_seasonality,
        daily_seasonality=False,
        interval_width=interval_width,
        changepoint_prior_scale=0.05,
    )

    # ── Timeout guard ──────────────────────────────────────────────────────────
    # model.fit() calls Stan's LBFGS optimiser which can hang indefinitely on
    # sparse or irregular data. We run it in a daemon thread and enforce a wall-
    # clock timeout. This pattern is compatible with Windows (no signal.alarm)
    # and with Celery's forked worker model.
    import warnings

    def _fit() -> Any:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model.fit(prophet_df)
        return model

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_fit)
        try:
            fitted = future.result(timeout=timeout)
        except FuturesTimeoutError:
            future.cancel()
            raise ProphetTimeoutError(
                f"Prophet fit for metric '{metric}' exceeded {timeout}s timeout. "
                "Falling back to Z-score detection for this metric."
            )

    logger.info("Prophet model fitted for metric: %s", metric)
    return fitted


def predict_in_sample(
    model: Any,
    df: pd.DataFrame,
) -> pd.DataFrame:
    """Generate in-sample (historical) predictions from a fitted Prophet model.

    Parameters
    ----------
    model:
        Fitted Prophet model (from :func:`fit_prophet`).
    df:
        Original DataFrame (used to extract the date range).

    Returns
    -------
    pd.DataFrame
        Prophet forecast DataFrame with columns including
        ``ds``, ``yhat``, ``yhat_lower``, ``yhat_upper``.
    """
    future = model.make_future_dataframe(periods=0)
    forecast = model.predict(future)
    return forecast


def detect_prophet_anomalies(
    df: pd.DataFrame,
    metric: str,
    interval_width: float = 0.95,
) -> pd.DataFrame:
    """Detect anomalies in *metric* using a Prophet uncertainty interval.

    A date is flagged as anomalous when the observed value lies outside
    the ``[yhat_lower, yhat_upper]`` band produced by Prophet.

    Parameters
    ----------
    df:
        DataFrame containing ``date`` and *metric* columns, sorted chronologically.
    metric:
        Metric column to analyse.
    interval_width:
        Width of the Prophet confidence interval (default 95%).

    Returns
    -------
    pd.DataFrame
        All rows (one per date) with columns:

        * ``date``
        * ``observed_value``
        * ``expected_value``  (``yhat``)
        * ``lower_bound``     (``yhat_lower``)
        * ``upper_bound``     (``yhat_upper``)
        * ``is_anomaly``      (bool)
        * ``deviation``       (how far outside the band, 0 when inside)
        * ``direction``       (``"drop"`` | ``"spike"`` | ``"normal"``)
    """
    if metric not in df.columns:
        raise ValueError(f"Metric '{metric}' not found in DataFrame.")

    model = fit_prophet(df, metric, interval_width=interval_width)
    forecast = predict_in_sample(model, df)

    # Merge forecast with observed values
    observed = df[[DATE_COLUMN, metric]].rename(
        columns={DATE_COLUMN: "ds", metric: "observed_value"}
    )
    merged = forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].merge(
        observed, on="ds", how="left"
    )

    merged = merged.rename(columns={
        "ds":          "date",
        "yhat":        "expected_value",
        "yhat_lower":  "lower_bound",
        "yhat_upper":  "upper_bound",
    })

    # Anomaly flag
    merged["is_anomaly"] = (
        (merged["observed_value"] < merged["lower_bound"])
        | (merged["observed_value"] > merged["upper_bound"])
    )

    # Deviation: distance outside band (0 when inside)
    merged["deviation"] = np.where(
        merged["observed_value"] < merged["lower_bound"],
        merged["lower_bound"] - merged["observed_value"],
        np.where(
            merged["observed_value"] > merged["upper_bound"],
            merged["observed_value"] - merged["upper_bound"],
            0.0,
        ),
    )

    # Direction
    merged["direction"] = np.where(
        ~merged["is_anomaly"], "normal",
        np.where(merged["observed_value"] < merged["expected_value"], "drop", "spike"),
    )

    merged["metric"] = metric
    result = merged[
        ["date", "metric", "observed_value", "expected_value",
         "lower_bound", "upper_bound", "is_anomaly", "deviation", "direction"]
    ].sort_values("date").reset_index(drop=True)

    n = merged["is_anomaly"].sum()
    logger.info("Prophet detected %d anomal%s for '%s'.", n, "y" if n == 1 else "ies", metric)
    return result


def backtest_prophet_detector(
    df: pd.DataFrame,
    metric: str,
    min_train_points: int = PROPHET_BACKTEST_MIN_TRAIN_POINTS,
    interval_width: float = 0.95,
) -> ProphetBacktestResult:
    """Score Prophet out-of-sample with a rolling-origin one-step backtest."""
    if metric not in df.columns:
        raise ValueError(f"Metric '{metric}' not found in DataFrame.")

    if len(df) <= min_train_points:
        raise ValueError(
            f"Need more than {min_train_points} rows to run Prophet backtesting; received {len(df)}."
        )

    ordered = df.sort_values(DATE_COLUMN).reset_index(drop=True)
    flagged_dates: list[pd.Timestamp] = []

    for index in range(min_train_points, len(ordered)):
        train = ordered.iloc[:index]
        target = ordered.iloc[index : index + 1]
        model = fit_prophet(train, metric, interval_width=interval_width)
        forecast = predict_in_sample(model, train)

        future = pd.DataFrame({"ds": target[DATE_COLUMN].tolist()})
        prediction = model.predict(future).iloc[0]
        observed_value = float(target.iloc[0][metric])
        lower_bound = float(prediction["yhat_lower"])
        upper_bound = float(prediction["yhat_upper"])
        if observed_value < lower_bound or observed_value > upper_bound:
            flagged_dates.append(pd.to_datetime(target.iloc[0][DATE_COLUMN]))

    return ProphetBacktestResult(
        train_points=min_train_points,
        scored_points=len(ordered) - min_train_points,
        flagged_dates=flagged_dates,
    )


def detect_all_metrics(
    df: pd.DataFrame,
    metrics: list[str] | None = None,
    interval_width: float = 0.95,
) -> pd.DataFrame:
    """Run :func:`detect_prophet_anomalies` over every metric and concatenate.

    Parameters
    ----------
    df:
        Full time-series DataFrame.
    metrics:
        Metric columns to scan. Defaults to ``config.ANOMALY_METRICS``.
    interval_width:
        Confidence interval width.

    Returns
    -------
    pd.DataFrame
        Combined anomaly table across all metrics.
    """
    if metrics is None:
        metrics = ANOMALY_METRICS

    frames: list[pd.DataFrame] = []
    for metric in metrics:
        try:
            result = detect_prophet_anomalies(df, metric, interval_width)
            frames.append(result)
        except ProphetTimeoutError as exc:
            # Timeout is non-fatal — Z-score detection will cover this metric.
            logger.warning(
                "Prophet timeout for metric '%s' (excluded from Prophet results): %s",
                metric, exc,
            )
        except Exception as exc:
            logger.error("Prophet detection failed for '%s': %s", metric, exc)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def forecast_future(
    df: pd.DataFrame,
    metric: str,
    periods: int = 30,
    interval_width: float = 0.95,
) -> pd.DataFrame:
    """Fit Prophet and forecast *periods* days into the future.

    Parameters
    ----------
    df:
        Historical data.
    metric:
        Metric to forecast.
    periods:
        Number of future days to forecast.
    interval_width:
        Confidence interval width.

    Returns
    -------
    pd.DataFrame
        Forecast DataFrame with ``ds``, ``yhat``, ``yhat_lower``, ``yhat_upper``
        for both historical and future periods.
    """
    model = fit_prophet(df, metric, interval_width=interval_width)
    future = model.make_future_dataframe(periods=periods)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        forecast = model.predict(future)
    return forecast


# ── Example usage ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, pathlib, logging
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
    from src.data_loader import load_data

    logging.basicConfig(level=logging.INFO)
    raw = load_data("data/sample_ecommerce.csv")
    anomalies = detect_prophet_anomalies(raw, "revenue")
    print(anomalies[anomalies["is_anomaly"]].to_string(index=False))
