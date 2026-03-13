"""
correlation_analysis.py
=======================
Computes pairwise Pearson correlations between business metrics and
identifies which relationships are statistically strong.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from utils.config import CORRELATION_PAIRS, STRONG_CORRELATION_THRESHOLD

logger = logging.getLogger(__name__)


@dataclass
class CorrelationResult:
    """Pearson correlation between two metrics."""

    metric_a: str
    metric_b: str
    pearson_r: float
    p_value: float
    is_strong: bool
    relationship: str   # "positive", "negative", or "weak"

    def to_dict(self) -> dict:
        return {
            "metric_a": self.metric_a,
            "metric_b": self.metric_b,
            "pearson_r": round(self.pearson_r, 4),
            "p_value": round(self.p_value, 6),
            "is_strong": self.is_strong,
            "relationship": self.relationship,
        }


def _classify_relationship(r: float, threshold: float) -> str:
    if abs(r) < threshold:
        return "weak"
    return "positive" if r > 0 else "negative"


def compute_correlation(
    df: pd.DataFrame,
    metric_a: str,
    metric_b: str,
    threshold: float = STRONG_CORRELATION_THRESHOLD,
) -> CorrelationResult:
    """Compute Pearson correlation between two columns.

    Parameters
    ----------
    df:
        DataFrame containing both metrics.
    metric_a, metric_b:
        Column names to correlate.
    threshold:
        Minimum |r| to classify a correlation as "strong".

    Returns
    -------
    CorrelationResult
    """
    series_a = df[metric_a].dropna().astype(float)
    series_b = df[metric_b].dropna().astype(float)

    # Align on index
    aligned = pd.concat([series_a, series_b], axis=1).dropna()
    r, p = stats.pearsonr(aligned[metric_a], aligned[metric_b])

    return CorrelationResult(
        metric_a=metric_a,
        metric_b=metric_b,
        pearson_r=float(r),
        p_value=float(p),
        is_strong=abs(r) >= threshold,
        relationship=_classify_relationship(r, threshold),
    )


def analyse_correlations(
    df: pd.DataFrame,
    pairs: list[tuple[str, str]] | None = None,
    threshold: float = STRONG_CORRELATION_THRESHOLD,
) -> pd.DataFrame:
    """Run correlation analysis over all configured metric pairs.

    Parameters
    ----------
    df:
        Time-series DataFrame.
    pairs:
        List of ``(metric_a, metric_b)`` tuples.  Defaults to config pairs.
    threshold:
        Strong-correlation threshold.

    Returns
    -------
    pd.DataFrame
        One row per pair with columns from :class:`CorrelationResult`.
    """
    if pairs is None:
        pairs = CORRELATION_PAIRS

    results: list[dict] = []
    for metric_a, metric_b in pairs:
        if metric_a not in df.columns or metric_b not in df.columns:
            logger.warning(
                "Skipping pair (%s, %s) — column(s) missing.", metric_a, metric_b
            )
            continue
        cr = compute_correlation(df, metric_a, metric_b, threshold)
        results.append(cr.to_dict())
        logger.info(
            "r(%s, %s) = %.4f  p=%.4f  strong=%s",
            metric_a, metric_b, cr.pearson_r, cr.p_value, cr.is_strong,
        )

    return pd.DataFrame(results)


def get_strong_correlators(
    correlations_df: pd.DataFrame,
    primary_metric: str = "revenue",
) -> list[str]:
    """Return metrics strongly correlated with *primary_metric*.

    Parameters
    ----------
    correlations_df:
        Output of :func:`analyse_correlations`.
    primary_metric:
        The target metric (typically ``"revenue"``).

    Returns
    -------
    list[str]
        Metric names with |r| ≥ threshold w.r.t. *primary_metric*.
    """
    if correlations_df.empty:
        return []

    mask = (
        (correlations_df["metric_a"] == primary_metric)
        | (correlations_df["metric_b"] == primary_metric)
    ) & correlations_df["is_strong"]

    strong = correlations_df[mask].copy()
    related: list[str] = []
    for _, row in strong.iterrows():
        other = row["metric_b"] if row["metric_a"] == primary_metric else row["metric_a"]
        related.append(other)
    return related


def build_correlation_matrix(
    df: pd.DataFrame,
    metrics: list[str],
) -> pd.DataFrame:
    """Return a full N×N Pearson correlation matrix for *metrics*.

    Useful for heatmap visualisations.
    """
    return df[metrics].corr(method="pearson")


# ── Example usage ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
    from src.data_loader import load_data

    logging.basicConfig(level=logging.INFO)
    raw = load_data("data/sample_ecommerce.csv")
    corr = analyse_correlations(raw)
    print(corr.to_string(index=False))
