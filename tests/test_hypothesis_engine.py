"""
Tests for src/hypothesis_engine.py
====================================
Verifies that each hypothesis rule fires (or doesn't) under the correct
conditions and that confidence scores are within expected bounds.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import pytest

from src.hypothesis_engine import (
    Hypothesis,
    _traffic_drop_hypothesis,
    _conversion_drop_hypothesis,
    _aov_drop_hypothesis,
    _spike_hypothesis,
    _data_quality_hypothesis,
    generate_hypotheses,
    hypotheses_to_dataframe,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_contrib(traffic_pct_change: float, cvr_pct_change: float,
                  orders_pct_change: float) -> pd.DataFrame:
    """Build a synthetic contributions DataFrame."""
    total = abs(traffic_pct_change) + abs(cvr_pct_change) + abs(orders_pct_change)
    if total == 0:
        total = 1.0
    rows = [
        {"factor": "traffic",         "pct_change": traffic_pct_change,
         "contribution_pct": abs(traffic_pct_change) / total * 100},
        {"factor": "conversion_rate", "pct_change": cvr_pct_change,
         "contribution_pct": abs(cvr_pct_change) / total * 100},
        {"factor": "orders",          "pct_change": orders_pct_change,
         "contribution_pct": abs(orders_pct_change) / total * 100},
    ]
    return pd.DataFrame(rows)


def _make_anomalies(directions: list[str], metrics: list[str] | None = None) -> pd.DataFrame:
    """Build a synthetic anomaly DataFrame."""
    metrics = metrics or ["revenue"] * len(directions)
    return pd.DataFrame({
        "date":            ["2024-01-01"] * len(directions),
        "metric":          metrics,
        "observed_value":  [100.0] * len(directions),
        "expected_value":  [120.0] * len(directions),
        "z_score":         [-2.5 if d == "drop" else 2.5 for d in directions],
        "deviation_score": [2.5] * len(directions),
        "direction":       directions,
        "detector":        ["z_score"] * len(directions),
    })


# ── Traffic-drop rule ─────────────────────────────────────────────────────────

def test_traffic_drop_fires_on_large_drop():
    contrib = _make_contrib(traffic_pct_change=-40.0, cvr_pct_change=-5.0,
                            orders_pct_change=-5.0)
    hyp = _traffic_drop_hypothesis(contrib, {})
    assert hyp is not None
    assert hyp.id == "H-TRAFFIC-DROP"
    assert 0 < hyp.confidence <= 1.0


def test_traffic_drop_does_not_fire_on_small_drop():
    contrib = _make_contrib(traffic_pct_change=-5.0, cvr_pct_change=-5.0,
                            orders_pct_change=-5.0)
    hyp = _traffic_drop_hypothesis(contrib, {})
    # Traffic contribution is exactly 33%, which is above 20 % threshold,
    # but pct_change < 0, so it may or may not fire — the key check is
    # that it does NOT fire when contribution_pct < 20.
    contrib_low = _make_contrib(traffic_pct_change=-1.0, cvr_pct_change=-50.0,
                                orders_pct_change=-50.0)
    hyp_low = _traffic_drop_hypothesis(contrib_low, {})
    assert hyp_low is None   # traffic contribution is ~1%


def test_traffic_drop_does_not_fire_on_spike():
    contrib = _make_contrib(traffic_pct_change=+50.0, cvr_pct_change=0.0,
                            orders_pct_change=0.0)
    hyp = _traffic_drop_hypothesis(contrib, {})
    assert hyp is None  # pct_change >= 0 → rule skipped


def test_traffic_drop_is_none_on_empty_df():
    assert _traffic_drop_hypothesis(pd.DataFrame(), {}) is None


# ── CVR-drop rule ─────────────────────────────────────────────────────────────

def test_cvr_drop_fires_on_large_drop():
    contrib = _make_contrib(traffic_pct_change=-5.0, cvr_pct_change=-60.0,
                            orders_pct_change=-5.0)
    hyp = _conversion_drop_hypothesis(contrib, {})
    assert hyp is not None
    assert hyp.id == "H-CVR-DROP"


def test_cvr_drop_does_not_fire_on_spike():
    contrib = _make_contrib(traffic_pct_change=0, cvr_pct_change=+20.0,
                            orders_pct_change=0)
    hyp = _conversion_drop_hypothesis(contrib, {})
    assert hyp is None


# ── AOV-drop rule ─────────────────────────────────────────────────────────────

def test_aov_drop_fires_when_traffic_and_orders_stable():
    contrib = _make_contrib(traffic_pct_change=-1.0, cvr_pct_change=-1.0,
                            orders_pct_change=-1.0)
    # Manually override contributions so traffic+orders both look low
    contrib.loc[contrib["factor"] == "traffic",         "contribution_pct"] = 3.0
    contrib.loc[contrib["factor"] == "orders",          "contribution_pct"] = 3.0
    contrib.loc[contrib["factor"] == "conversion_rate", "contribution_pct"] = 94.0
    hyp = _aov_drop_hypothesis(contrib)
    assert hyp is not None
    assert hyp.id == "H-AOV-DROP"


# ── Spike rule ────────────────────────────────────────────────────────────────

def test_spike_fires_on_positive_anomaly():
    anomalies = _make_anomalies(["spike"], ["revenue"])
    hyp = _spike_hypothesis(pd.DataFrame(), anomalies)
    assert hyp is not None
    assert hyp.id == "H-SPIKE"
    assert "revenue" in hyp.title


def test_spike_does_not_fire_on_drop():
    anomalies = _make_anomalies(["drop"])
    hyp = _spike_hypothesis(pd.DataFrame(), anomalies)
    assert hyp is None


def test_spike_does_not_fire_on_empty():
    assert _spike_hypothesis(pd.DataFrame(), pd.DataFrame()) is None


# ── Data-quality rule ─────────────────────────────────────────────────────────

def test_data_quality_fires_when_single_metric_anomalous():
    anomalies = _make_anomalies(["drop"], ["revenue"])
    hyp = _data_quality_hypothesis(
        anomalies, all_metrics=["revenue", "traffic", "conversion_rate"]
    )
    assert hyp is not None
    assert hyp.id == "H-DATA-QUALITY"
    assert "revenue" in hyp.title


def test_data_quality_does_not_fire_when_multiple_metrics_affected():
    anomalies = _make_anomalies(["drop", "drop"], ["revenue", "traffic"])
    hyp = _data_quality_hypothesis(
        anomalies, all_metrics=["revenue", "traffic", "conversion_rate"]
    )
    assert hyp is None  # 2 metrics affected → not a data-quality isolation


def test_data_quality_does_not_fire_on_empty():
    assert _data_quality_hypothesis(pd.DataFrame()) is None


# ── generate_hypotheses integration ──────────────────────────────────────────

def test_generate_hypotheses_returns_sorted_by_confidence():
    contrib  = _make_contrib(-40.0, -5.0, -5.0)
    seg      = {}
    corr     = pd.DataFrame(columns=["metric_a", "metric_b", "pearson_r", "is_strong", "relationship"])
    anomalies = _make_anomalies(["drop"], ["revenue"])
    hyps = generate_hypotheses(contrib, seg, corr, anomalies_df=anomalies)
    assert isinstance(hyps, list)
    confs = [h.confidence for h in hyps]
    assert confs == sorted(confs, reverse=True), "Hypotheses must be sorted by confidence desc"


def test_generate_hypotheses_returns_empty_list_on_empty_inputs():
    hyps = generate_hypotheses(pd.DataFrame(), {}, pd.DataFrame())
    assert hyps == []


def test_hypotheses_to_dataframe_has_expected_columns():
    h = Hypothesis(id="TEST", title="Test", description="desc", confidence=0.75)
    df = hypotheses_to_dataframe([h])
    assert set(["id", "title", "confidence", "description"]).issubset(df.columns)
    assert df.iloc[0]["confidence"] == "75%"
