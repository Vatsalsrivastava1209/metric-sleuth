"""
anomaly_evaluation.py
=====================
Simple backtesting helpers for the anomaly detector.

This module does not claim to be a full benchmark suite. Its purpose is to
give the product a repeatable, auditable scoring path for labeled anomaly
dates so regression tests can track detector quality over time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from src.anomaly_detection import detect_anomalies, get_anomaly_dates
from src.prophet_anomaly_detection import backtest_prophet_detector
from utils.config import ANOMALY_EVAL_THRESHOLD_GRID, ANOMALY_EVAL_WINDOW_GRID


@dataclass
class DetectionMetrics:
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1_score: float

    def to_dict(self) -> dict[str, float | int]:
        return {
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4),
        }


def _normalize_dates(dates: Iterable[pd.Timestamp | str]) -> list[pd.Timestamp]:
    normalized = pd.to_datetime(list(dates), errors="coerce")
    return sorted(ts.normalize() for ts in normalized if not pd.isna(ts))


def score_detected_dates(
    detected_dates: Iterable[pd.Timestamp | str],
    labeled_dates: Iterable[pd.Timestamp | str],
    tolerance_days: int = 0,
) -> DetectionMetrics:
    """Score detected anomaly dates against labeled incidents."""
    detected = _normalize_dates(detected_dates)
    labeled = _normalize_dates(labeled_dates)

    remaining_detected = detected.copy()
    true_positives = 0

    for label in labeled:
        match_index = next(
            (
                index
                for index, detected_date in enumerate(remaining_detected)
                if abs((detected_date - label).days) <= tolerance_days
            ),
            None,
        )
        if match_index is not None:
            true_positives += 1
            remaining_detected.pop(match_index)

    false_positives = len(remaining_detected)
    false_negatives = max(len(labeled) - true_positives, 0)

    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) else 0.0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) else 0.0
    f1_score = (
        2 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )

    return DetectionMetrics(
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        precision=precision,
        recall=recall,
        f1_score=f1_score,
    )


def evaluate_detector(
    df: pd.DataFrame,
    labeled_dates: Iterable[pd.Timestamp | str],
    metrics: list[str] | None = None,
    threshold: float = 2.0,
    window: int = 7,
    tolerance_days: int = 0,
) -> dict[str, float | int]:
    """Run the detector on a frame and score it against labeled anomaly dates."""
    anomalies_df = detect_anomalies(df, metrics=metrics, threshold=threshold, window=window)
    scores = score_detected_dates(
        get_anomaly_dates(anomalies_df),
        labeled_dates=labeled_dates,
        tolerance_days=tolerance_days,
    ).to_dict()
    scores["detected_dates"] = len(get_anomaly_dates(anomalies_df))
    scores["detected_rows"] = len(anomalies_df)
    return scores


def tune_detector(
    df: pd.DataFrame,
    labeled_dates: Iterable[pd.Timestamp | str],
    metrics: list[str] | None = None,
    tolerance_days: int = 0,
    threshold_grid: list[float] | None = None,
    window_grid: list[int] | None = None,
) -> dict[str, float | int]:
    """Search a small threshold/window grid and return the best-scoring config."""
    thresholds = threshold_grid or ANOMALY_EVAL_THRESHOLD_GRID
    windows = window_grid or ANOMALY_EVAL_WINDOW_GRID
    best: dict[str, float | int] | None = None

    for threshold in thresholds:
        for window in windows:
            scores = evaluate_detector(
                df,
                labeled_dates=labeled_dates,
                metrics=metrics,
                threshold=threshold,
                window=window,
                tolerance_days=tolerance_days,
            )
            candidate = {
                **scores,
                "threshold": threshold,
                "window": window,
            }
            if best is None or (
                candidate["f1_score"],
                candidate["recall"],
                -candidate["false_positives"],
            ) > (
                best["f1_score"],
                best["recall"],
                -best["false_positives"],
            ):
                best = candidate

    return best or {
        "threshold": 0.0,
        "window": 0,
        "true_positives": 0,
        "false_positives": 0,
        "false_negatives": 0,
        "precision": 0.0,
        "recall": 0.0,
        "f1_score": 0.0,
        "detected_dates": 0,
        "detected_rows": 0,
    }


def evaluate_prophet_detector(
    df: pd.DataFrame,
    metric: str,
    labeled_dates: Iterable[pd.Timestamp | str],
    tolerance_days: int = 0,
) -> dict[str, float | int]:
    """Backtest Prophet out-of-sample and score it against labeled incidents."""
    result = backtest_prophet_detector(df, metric=metric)
    scores = score_detected_dates(
        result.flagged_dates,
        labeled_dates=labeled_dates,
        tolerance_days=tolerance_days,
    ).to_dict()
    scores["train_points"] = result.train_points
    scores["scored_points"] = result.scored_points
    scores["detected_dates"] = len(result.flagged_dates)
    return scores
