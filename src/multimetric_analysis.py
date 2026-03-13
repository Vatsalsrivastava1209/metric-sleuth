"""
multimetric_analysis.py
=======================
Detects compound anomalies — dates where multiple metrics simultaneously
fall outside their expected ranges.

A compound anomaly is a much stronger signal than a single-metric anomaly:
it suggests a systemic event rather than statistical noise.

Severity scale
--------------
* 1 metric anomalous  → LOW
* 2 metrics anomalous → MEDIUM
* 3+ metrics anomalous → HIGH / CRITICAL
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd
import numpy as np

from utils.config import ANOMALY_METRICS, DATE_COLUMN

logger = logging.getLogger(__name__)

# Severity thresholds (number of simultaneously anomalous metrics)
_SEVERITY_MAP = {
    1: "LOW",
    2: "MEDIUM",
    3: "HIGH",
}


@dataclass
class CompoundAnomaly:
    """A single date with simultaneous anomalies across multiple metrics."""

    date: pd.Timestamp
    affected_metrics: list[str]
    compound_anomaly_score: float   # 0-1 normalised severity
    severity_level: str             # LOW / MEDIUM / HIGH / CRITICAL
    metric_details: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "date":                  self.date,
            "affected_metrics":      ", ".join(self.affected_metrics),
            "n_affected":            len(self.affected_metrics),
            "compound_anomaly_score": round(self.compound_anomaly_score, 4),
            "severity_level":        self.severity_level,
        }


def _severity(n_affected: int, total_metrics: int) -> tuple[float, str]:
    """Return (normalised_score, severity_label) for *n_affected* out of *total*."""
    score = n_affected / max(total_metrics, 1)
    if n_affected >= 3:
        label = "CRITICAL" if score >= 1.0 else "HIGH"
    else:
        label = _SEVERITY_MAP.get(n_affected, "LOW")
    return round(score, 4), label


def build_anomaly_presence_matrix(
    anomaly_results: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Build a date × metric boolean matrix of anomaly presence.

    Parameters
    ----------
    anomaly_results:
        Mapping ``{metric: anomaly_df}`` where each ``anomaly_df`` has at least
        ``date`` and ``is_anomaly`` columns (output of anomaly detection modules).

    Returns
    -------
    pd.DataFrame
        Index = date, columns = metric names, values = bool (True = anomalous).
    """
    frames: dict[str, pd.Series] = {}
    for metric, adf in anomaly_results.items():
        if adf.empty or "is_anomaly" not in adf.columns:
            continue
        adf = adf.copy()
        adf["date"] = pd.to_datetime(adf["date"])
        s = adf.set_index("date")["is_anomaly"].astype(bool)
        frames[metric] = s

    if not frames:
        return pd.DataFrame()

    matrix = pd.DataFrame(frames).fillna(False)
    matrix.index.name = "date"
    return matrix


def detect_compound_anomalies(
    anomaly_results: dict[str, pd.DataFrame],
    min_metrics: int = 2,
) -> pd.DataFrame:
    """Find dates where *min_metrics* or more metrics are simultaneously anomalous.

    Parameters
    ----------
    anomaly_results:
        Mapping ``{metric: anomaly_df}`` — typically from running anomaly detection
        (Z-score or Prophet) on each metric independently.
    min_metrics:
        Minimum number of simultaneously anomalous metrics to count as compound.
        Default is 2 (at least two metrics must be anomalous on the same day).

    Returns
    -------
    pd.DataFrame
        One row per compound-anomaly date with columns:
        ``date``, ``affected_metrics``, ``n_affected``,
        ``compound_anomaly_score``, ``severity_level``.
        Sorted by ``compound_anomaly_score`` descending.
    """
    matrix = build_anomaly_presence_matrix(anomaly_results)
    if matrix.empty:
        logger.info("No anomaly data available for compound analysis.")
        return pd.DataFrame()

    total_metrics = len(matrix.columns)
    compound_rows: list[dict] = []

    for date, row in matrix.iterrows():
        affected = [m for m in row.index if row[m]]
        n = len(affected)
        if n < min_metrics:
            continue

        score, severity = _severity(n, total_metrics)
        ca = CompoundAnomaly(
            date=pd.Timestamp(date),
            affected_metrics=affected,
            compound_anomaly_score=score,
            severity_level=severity,
        )
        compound_rows.append(ca.to_dict())

    if not compound_rows:
        logger.info("No compound anomalies found (min_metrics=%d).", min_metrics)
        return pd.DataFrame(
            columns=["date", "affected_metrics", "n_affected",
                     "compound_anomaly_score", "severity_level"]
        )

    result = (
        pd.DataFrame(compound_rows)
        .sort_values("compound_anomaly_score", ascending=False)
        .reset_index(drop=True)
    )
    logger.info("Found %d compound anomaly event(s).", len(result))
    return result


def get_anomaly_co_occurrence(
    anomaly_results: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Compute a pairwise co-occurrence count matrix for metric anomalies.

    Useful for understanding which pairs of metrics tend to fail together.

    Returns
    -------
    pd.DataFrame
        N×N symmetric matrix where entry (i,j) counts dates where both
        metric i and metric j were simultaneously anomalous.
    """
    matrix = build_anomaly_presence_matrix(anomaly_results)
    if matrix.empty:
        return pd.DataFrame()

    metrics = list(matrix.columns)
    cooc = pd.DataFrame(0, index=metrics, columns=metrics)
    for m1 in metrics:
        for m2 in metrics:
            cooc.loc[m1, m2] = int((matrix[m1] & matrix[m2]).sum())
    return cooc


def enrich_with_compound_score(
    df: pd.DataFrame,
    compound_df: pd.DataFrame,
) -> pd.DataFrame:
    """Add ``compound_anomaly_score`` and ``severity_level`` columns to *df*.

    Dates with no compound anomaly get score 0 and severity "NONE".

    Parameters
    ----------
    df:
        Original time-series DataFrame with a ``date`` column.
    compound_df:
        Output of :func:`detect_compound_anomalies`.

    Returns
    -------
    pd.DataFrame
        Copy of *df* with two extra columns.
    """
    df = df.copy()
    df["compound_anomaly_score"] = 0.0
    df["severity_level"] = "NONE"

    if compound_df.empty:
        return df

    for _, row in compound_df.iterrows():
        mask = df[DATE_COLUMN] == row["date"]
        df.loc[mask, "compound_anomaly_score"] = row["compound_anomaly_score"]
        df.loc[mask, "severity_level"] = row["severity_level"]

    return df


# ── Example usage ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, pathlib, logging
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
    from src.data_loader import load_data
    from src.anomaly_detection import detect_anomalies

    logging.basicConfig(level=logging.INFO)
    raw = load_data("data/sample_ecommerce.csv")

    # Build per-metric anomaly results using the fast Z-score detector
    from utils.config import ANOMALY_METRICS
    anom_map = {}
    for m in ANOMALY_METRICS:
        adf = detect_anomalies(raw, metrics=[m])
        # Standardise to have an is_anomaly column
        if not adf.empty:
            adf = raw[["date"]].copy().merge(
                adf[["date", "metric"]].assign(is_anomaly=True),
                on="date", how="left"
            )
            adf["is_anomaly"] = adf["is_anomaly"].fillna(False)
        anom_map[m] = adf

    compound = detect_compound_anomalies(anom_map)
    print(compound.to_string(index=False))
