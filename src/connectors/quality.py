"""
connectors/quality.py
=====================
Freshness and completeness quality checks for ingested connector data.

Every connector can call check_freshness() and check_completeness() on the
DataFrame it returns. The results surface on the portfolio dashboard so the
analyst sees "GA4 data is 26h stale — this anomaly may reflect a conversion
lag artifact" before writing the client brief.

Two classes of quality issues that cause bad RCA without this layer:
- Stale data: GA4 has a 24-48h processing delay. An "anomaly" on today's
  date is often just an unfilled day, not a real drop.
- Missing columns: If conversion_rate is null for 30% of rows, the anomaly
  detector will fire on noise rather than signal.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from utils.config import DATE_COLUMN, REQUIRED_COLUMNS

logger = logging.getLogger(__name__)


@dataclass
class ConnectorQualityReport:
    """Quality assessment for a single connector's data pull."""

    connector_type: str
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Freshness
    last_data_point: str | None = None
    hours_since_last_point: float | None = None
    freshness_ok: bool = True
    freshness_warning: str | None = None

    # Completeness
    row_count: int = 0
    missing_ratios: dict[str, float] = field(default_factory=dict)
    completeness_ok: bool = True
    completeness_warnings: list[str] = field(default_factory=list)

    # Known connector-specific caveats
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "connector_type": self.connector_type,
            "checked_at": self.checked_at,
            "last_data_point": self.last_data_point,
            "hours_since_last_point": self.hours_since_last_point,
            "freshness_ok": self.freshness_ok,
            "freshness_warning": self.freshness_warning,
            "row_count": self.row_count,
            "missing_ratios": {k: round(v, 3) for k, v in self.missing_ratios.items()},
            "completeness_ok": self.completeness_ok,
            "completeness_warnings": self.completeness_warnings,
            "caveats": self.caveats,
        }

    def summary_text(self) -> str:
        """One-line human-readable quality summary for the dashboard."""
        parts = []
        if not self.freshness_ok and self.freshness_warning:
            parts.append(self.freshness_warning)
        if not self.completeness_ok:
            parts.append(f"{len(self.completeness_warnings)} column(s) with high missing rates.")
        if self.caveats:
            parts.append(" ".join(self.caveats))
        return " | ".join(parts) if parts else "Data quality OK."


# ── Freshness check ───────────────────────────────────────────────────────────

# Per-connector freshness thresholds in hours.
# GA4 and Meta Ads have known processing delays — we warn later than for
# direct DB connectors where stale data is always a pipeline fault.
_FRESHNESS_THRESHOLDS: dict[str, float] = {
    "ga4":          36.0,   # GA4 processing delay is typically 24-48h
    "meta_ads":     36.0,
    "google_ads":   36.0,
    "klaviyo":      24.0,
    "shopify":      6.0,    # Shopify webhooks are near-real-time
    "csv":          float("inf"),  # manual uploads — freshness not meaningful
    "postgres":     6.0,
    "mysql":        6.0,
    "bigquery":     12.0,
    "default":      24.0,
}

# Known data-lag caveats surfaced in the quality report per connector type.
_CONNECTOR_CAVEATS: dict[str, list[str]] = {
    "ga4": [
        "GA4 has a 24-48h conversion processing delay. Anomalies on recent dates "
        "may reflect unfilled attribution windows rather than real traffic drops."
    ],
    "meta_ads": [
        "Meta Ads attribution data is reprocessed for 7-28 days after conversion. "
        "Revenue metrics for the last 7 days should be treated as preliminary."
    ],
    "google_ads": [
        "Google Ads conversion columns may lag 24h. Use view-through conversions carefully."
    ],
}


def check_freshness(
    df: pd.DataFrame,
    connector_type: str = "default",
    date_column: str | None = None,
) -> tuple[bool, float | None, str | None]:
    """Check how recent the latest data point is.

    Returns
    -------
    (is_fresh, hours_since_last_point, warning_message)
        is_fresh is False when hours exceed the connector-specific threshold.
    """
    col = date_column or DATE_COLUMN
    if col not in df.columns or df.empty:
        return True, None, None

    try:
        dates = pd.to_datetime(df[col], errors="coerce").dropna()
        if dates.empty:
            return True, None, None

        last_point = dates.max()
        now = pd.Timestamp.now(tz=None)
        if last_point.tzinfo is not None:
            now = pd.Timestamp.now(tz="UTC")

        hours_ago = (now - last_point).total_seconds() / 3600
        threshold = _FRESHNESS_THRESHOLDS.get(connector_type, _FRESHNESS_THRESHOLDS["default"])

        if hours_ago > threshold:
            warning = (
                f"{connector_type.upper()} data is {hours_ago:.0f}h stale "
                f"(threshold: {threshold:.0f}h). Anomalies on recent dates may reflect "
                "an incomplete data pull rather than a real business event."
            )
            logger.warning(warning)
            return False, round(hours_ago, 1), warning

        return True, round(hours_ago, 1), None

    except Exception as exc:
        logger.warning("Freshness check failed: %s", exc)
        return True, None, None


# ── Completeness check ────────────────────────────────────────────────────────

_HIGH_MISSING_THRESHOLD = 0.20   # warn when >20% of rows are null for a column
_CRITICAL_MISSING_THRESHOLD = 0.50  # critical when >50%


def check_completeness(
    df: pd.DataFrame,
    columns: list[str] | None = None,
) -> tuple[bool, dict[str, float], list[str]]:
    """Check for missing values across key metric and dimension columns.

    Returns
    -------
    (is_complete, missing_ratios, warnings)
        is_complete is False when any column exceeds the high-missing threshold.
        missing_ratios maps column name to fraction of null rows.
        warnings contains human-readable descriptions of problematic columns.
    """
    if df.empty:
        return True, {}, []

    check_cols = columns or [c for c in REQUIRED_COLUMNS if c in df.columns]
    total_rows = len(df)
    missing_ratios: dict[str, float] = {}
    warnings: list[str] = []

    for col in check_cols:
        if col not in df.columns:
            missing_ratios[col] = 1.0
            warnings.append(f"Column '{col}' is entirely absent from the dataset.")
            continue

        null_ratio = df[col].isna().sum() / total_rows
        missing_ratios[col] = round(null_ratio, 4)

        if null_ratio >= _CRITICAL_MISSING_THRESHOLD:
            warnings.append(
                f"CRITICAL: '{col}' is missing in {null_ratio:.0%} of rows. "
                "Anomaly detection on this metric will produce unreliable results."
            )
        elif null_ratio >= _HIGH_MISSING_THRESHOLD:
            warnings.append(
                f"'{col}' is missing in {null_ratio:.0%} of rows. "
                "Results may be skewed — investigate the data pipeline."
            )

    is_complete = len(warnings) == 0
    return is_complete, missing_ratios, warnings


# ── Combined quality check ────────────────────────────────────────────────────

def run_quality_check(
    df: pd.DataFrame,
    connector_type: str = "default",
    date_column: str | None = None,
    columns: list[str] | None = None,
) -> ConnectorQualityReport:
    """Run both freshness and completeness checks and return a unified report."""
    report = ConnectorQualityReport(connector_type=connector_type)
    report.row_count = len(df)
    report.caveats = _CONNECTOR_CAVEATS.get(connector_type, [])

    # Freshness
    fresh_ok, hours, warn = check_freshness(df, connector_type, date_column)
    report.freshness_ok = fresh_ok
    report.hours_since_last_point = hours
    report.freshness_warning = warn

    if df is not None and not df.empty:
        col = date_column or DATE_COLUMN
        if col in df.columns:
            last = pd.to_datetime(df[col], errors="coerce").dropna().max()
            report.last_data_point = str(last.date()) if not pd.isna(last) else None

    # Completeness
    complete_ok, ratios, comp_warnings = check_completeness(df, columns)
    report.completeness_ok = complete_ok
    report.missing_ratios = ratios
    report.completeness_warnings = comp_warnings

    return report
