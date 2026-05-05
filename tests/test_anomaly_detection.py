"""
Tests for src/anomaly_detection.py
====================================
Verifies Z-score detection correctness, low-variance guard behaviour,
and detector label presence.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest

from src.anomaly_detection import (
    _rolling_zscore,
    detect_anomalies,
    annotate_dataframe,
    get_anomaly_dates,
)
from src.anomaly_evaluation import evaluate_detector, evaluate_prophet_detector, score_detected_dates


# ── Synthetic data builder ────────────────────────────────────────────────────

def _flat_df(n: int = 30, value: float = 100.0) -> pd.DataFrame:
    """DataFrame with a perfectly flat metric — useful for low-variance guard tests."""
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame({
        "date":            dates,
        "revenue":         [value] * n,
        "traffic":         [1000] * n,
        "conversion_rate": [0.05] * n,
    })


def _df_with_spike(n: int = 30, spike_pos: int = 15, spike_magnitude: float = 5.0) -> pd.DataFrame:
    """DataFrame with a single obvious spike in revenue."""
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    revenue = [100.0] * n
    revenue[spike_pos] = 100.0 + spike_magnitude * 50   # 5-sigma spike
    return pd.DataFrame({
        "date":            dates,
        "revenue":         revenue,
        "traffic":         [1000] * n,
        "conversion_rate": [0.05] * n,
    })


def _df_with_drop(n: int = 30, drop_pos: int = 15, drop_pct: float = 0.80) -> pd.DataFrame:
    """DataFrame with a single obvious drop in revenue."""
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    revenue = [100.0] * n
    revenue[drop_pos] = 100.0 * (1 - drop_pct)
    return pd.DataFrame({
        "date":            dates,
        "revenue":         revenue,
        "traffic":         [1000] * n,
        "conversion_rate": [0.05] * n,
    })


# ── Low-variance guard ────────────────────────────────────────────────────────

def test_low_variance_guard_suppresses_false_positives():
    """A perfectly flat metric must produce zero anomalies regardless of threshold."""
    df = _flat_df(value=100.0)
    anomalies = detect_anomalies(df, metrics=["revenue"], threshold=2.0)
    assert anomalies.empty, (
        "Low-variance guard failed: flat data produced anomalies. "
        f"Got:\n{anomalies}"
    )


def test_low_variance_guard_rolling_zscore_returns_nan_for_flat_series():
    """_rolling_zscore must return NaN z-scores for a perfectly flat series."""
    series = pd.Series([50.0] * 20)
    z, _, _ = _rolling_zscore(series, window=7)
    # After the first few warm-up rows the series is flat → NaN expected
    # (first row may be NaN due to std with min_periods=1 returning 0)
    non_nan = z.dropna()
    # All finite z-scores must be 0 (mean == value, std is ~0 → guarded)
    assert len(non_nan) == 0 or all(v == 0.0 for v in non_nan), (
        f"Expected NaN or 0 z-scores for flat series, got: {z.tolist()}"
    )


# ── Basic detection accuracy ──────────────────────────────────────────────────

def test_spike_is_detected():
    df = _df_with_spike(spike_pos=20)
    anomalies = detect_anomalies(df, metrics=["revenue"], threshold=2.0)
    assert not anomalies.empty, "A 5-sigma spike must be detected."
    spike_rows = anomalies[anomalies["direction"] == "spike"]
    assert not spike_rows.empty, "Detected anomaly must be labeled as 'spike'."


def test_drop_is_detected():
    df = _df_with_drop(drop_pos=20, drop_pct=0.80)
    anomalies = detect_anomalies(df, metrics=["revenue"], threshold=2.0)
    assert not anomalies.empty, "An 80% revenue drop must be detected."
    drop_rows = anomalies[anomalies["direction"] == "drop"]
    assert not drop_rows.empty, "Detected anomaly must be labeled as 'drop'."


def test_material_change_after_flat_history_is_detected():
    df = _df_with_drop(drop_pos=12, drop_pct=0.60)
    anomalies = detect_anomalies(df, metrics=["revenue"], threshold=2.0, window=7)
    assert not anomalies.empty, "A large drop after a flat baseline should still be treated as anomalous."
    assert np.isinf(anomalies["z_score"]).any() or (anomalies["z_score"].abs() >= 2.0).any()


def test_detector_label_present():
    """Every anomaly row must carry a 'detector' field."""
    df = _df_with_drop(drop_pos=20)
    anomalies = detect_anomalies(df, metrics=["revenue"], threshold=2.0)
    if not anomalies.empty:
        assert "detector" in anomalies.columns, "'detector' column missing from anomalies df."
        assert (anomalies["detector"] == "z_score").all(), (
            "All z-score anomalies must be labeled 'z_score'."
        )


# ── get_anomaly_dates ─────────────────────────────────────────────────────────

def test_get_anomaly_dates_returns_sorted_list():
    df = _df_with_drop(drop_pos=20)
    anomalies = detect_anomalies(df, metrics=["revenue"], threshold=2.0)
    dates = get_anomaly_dates(anomalies)
    assert dates == sorted(dates), "Anomaly dates must be in ascending order."


def test_get_anomaly_dates_empty_on_no_anomalies():
    df = _flat_df()
    anomalies = detect_anomalies(df, metrics=["revenue"], threshold=2.0)
    assert get_anomaly_dates(anomalies) == []


# ── annotate_dataframe ────────────────────────────────────────────────────────

def test_annotate_dataframe_adds_is_anomaly_column():
    df = _df_with_drop(drop_pos=20)
    anomalies = detect_anomalies(df, metrics=["revenue"])
    annotated = annotate_dataframe(df, anomalies)
    assert "is_anomaly" in annotated.columns
    if not anomalies.empty:
        assert annotated["is_anomaly"].any(), "At least one row must be flagged."


def test_annotate_dataframe_does_not_mutate_original():
    df = _flat_df()
    anomalies = detect_anomalies(df, metrics=["revenue"])
    _ = annotate_dataframe(df, anomalies)
    assert "is_anomaly" not in df.columns, "Original df must not be mutated."


def test_score_detected_dates_calculates_precision_recall():
    scores = score_detected_dates(
        detected_dates=["2024-01-10", "2024-01-20"],
        labeled_dates=["2024-01-10", "2024-01-15"],
        tolerance_days=0,
    )
    assert scores.true_positives == 1
    assert scores.false_positives == 1
    assert scores.false_negatives == 1
    assert scores.precision == pytest.approx(0.5)
    assert scores.recall == pytest.approx(0.5)


def test_evaluate_detector_reports_backtest_metrics():
    df = _df_with_drop(drop_pos=20, drop_pct=0.80)
    scores = evaluate_detector(
        df,
        labeled_dates=[df.loc[20, "date"]],
        metrics=["revenue"],
        threshold=2.0,
        window=7,
    )
    assert scores["true_positives"] >= 1
    assert scores["recall"] >= 0.99


def test_evaluate_prophet_detector_scores_backtest_output(monkeypatch):
    class _Result:
        train_points = 28
        scored_points = 2
        flagged_dates = [pd.Timestamp("2024-01-21")]

    monkeypatch.setattr("src.anomaly_evaluation.backtest_prophet_detector", lambda df, metric: _Result())
    scores = evaluate_prophet_detector(
        _df_with_drop(drop_pos=20, drop_pct=0.80),
        metric="revenue",
        labeled_dates=["2024-01-21"],
    )
    assert scores["true_positives"] == 1
    assert scores["detected_dates"] == 1
