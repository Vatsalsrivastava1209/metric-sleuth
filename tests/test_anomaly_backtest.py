"""
test_anomaly_backtest.py
========================
CI regression test for the anomaly detector.

Runs the z-score detector against a canonical labeled dataset and asserts
that F1 does not drop below the minimum acceptable threshold. If this test
fails, the detector has regressed and the change must be investigated before
merging.

The fixture files are committed to tests/fixtures/ and must not be
regenerated in CI — they are the stable ground truth.
"""
import os
import pathlib

import pandas as pd
import pytest

from src.anomaly_evaluation import evaluate_detector

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
TIMESERIES_CSV = FIXTURES / "sample_timeseries.csv"
LABELED_CSV    = FIXTURES / "labeled_incidents.csv"

MIN_F1_THRESHOLD    = 0.60
MIN_RECALL_THRESHOLD = 0.60


@pytest.mark.skipif(
    not TIMESERIES_CSV.exists() or not LABELED_CSV.exists(),
    reason="Fixture files missing — run tests/fixtures/generate_fixtures.py",
)
def test_zscore_detector_f1_regression():
    """Z-score detector must achieve F1 >= 0.60 on the canonical fixture dataset."""
    df = pd.read_csv(TIMESERIES_CSV, parse_dates=["date"])
    labels_df = pd.read_csv(LABELED_CSV)
    labeled_dates = labels_df["date"].tolist()

    scores = evaluate_detector(
        df,
        labeled_dates=labeled_dates,
        metrics=["revenue", "traffic"],
        threshold=2.0,
        window=7,
        tolerance_days=1,
    )

    print("\n── Backtest results ──────────────────────────────────────────")
    for k, v in scores.items():
        print(f"  {k}: {v}")
    print("─────────────────────────────────────────────────────────────")

    assert scores["f1_score"] >= MIN_F1_THRESHOLD, (
        f"Detector F1 ({scores['f1_score']:.3f}) dropped below minimum "
        f"threshold ({MIN_F1_THRESHOLD}). Check recent anomaly_detection.py changes."
    )
    assert scores["recall"] >= MIN_RECALL_THRESHOLD, (
        f"Detector recall ({scores['recall']:.3f}) dropped below minimum "
        f"threshold ({MIN_RECALL_THRESHOLD}). The detector is missing real incidents."
    )


@pytest.mark.skipif(
    not TIMESERIES_CSV.exists() or not LABELED_CSV.exists(),
    reason="Fixture files missing — run tests/fixtures/generate_fixtures.py",
)
def test_zscore_detector_no_excessive_false_positives():
    """False positive rate must stay manageable (< 5 FP per 30 days)."""
    df = pd.read_csv(TIMESERIES_CSV, parse_dates=["date"])
    labels_df = pd.read_csv(LABELED_CSV)
    labeled_dates = labels_df["date"].tolist()

    scores = evaluate_detector(
        df,
        labeled_dates=labeled_dates,
        metrics=["revenue", "traffic"],
        threshold=2.0,
        window=7,
        tolerance_days=1,
    )

    total_days = len(df)
    fp_per_30_days = (scores["false_positives"] / total_days) * 30
    max_fp_per_30 = 5.0

    assert fp_per_30_days < max_fp_per_30, (
        f"False positive rate ({fp_per_30_days:.1f}/30d) exceeds maximum "
        f"({max_fp_per_30}/30d). Detector is too noisy for agency use."
    )
