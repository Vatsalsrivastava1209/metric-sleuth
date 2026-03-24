"""
schema_mapper.py
================
Flexible column mapping layer that lets users connect CSVs or database
tables with non-standard column names to MetricSleuth's canonical schema.

Canonical columns
-----------------
    date             : YYYY-MM-DD date column
    revenue          : numeric — primary target metric
    traffic          : numeric — visit/session count
    orders           : numeric — transaction count
    conversion_rate  : numeric — ratio (0–1 or 0–100)
    region           : categorical — geographic segment
    device           : categorical — device type segment
    traffic_source   : categorical — acquisition channel segment

Usage
-----
    from src.schema_mapper import suggest_mapping, apply_mapping, validate_mapping

    mapping = suggest_mapping(df)          # auto-suggestion
    # user tweaks mapping in the UI …
    df_canonical = apply_mapping(df, mapping)
    errors = validate_mapping(mapping)
"""

from __future__ import annotations

import logging
import re
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# ── Canonical field definitions ───────────────────────────────────────────────

CANONICAL_FIELDS = [
    "date",
    "revenue",
    "traffic",
    "orders",
    "conversion_rate",
    "region",
    "device",
    "traffic_source",
]

REQUIRED_FIELDS = ["date", "revenue", "traffic", "orders", "conversion_rate"]
OPTIONAL_FIELDS = ["region", "device", "traffic_source"]

# Synonyms used in fuzzy matching (keyword → canonical)
_SYNONYMS: dict[str, list[str]] = {
    "date":            ["date", "day", "time", "datetime", "timestamp", "period", "week", "month"],
    "revenue":         ["revenue", "sales", "income", "gmv", "amount", "total", "earnings", "turnover"],
    "traffic":         ["traffic", "visits", "sessions", "views", "users", "pageviews", "hits"],
    "orders":          ["orders", "transactions", "purchases", "conversions", "bookings", "units"],
    "conversion_rate": ["conversion", "cvr", "conv_rate", "cr", "rate"],
    "region":          ["region", "country", "geo", "market", "area", "location", "territory", "state"],
    "device":          ["device", "platform", "channel", "device_type", "os"],
    "traffic_source":  ["source", "traffic_source", "channel", "medium", "acquisition", "referral"],
}


# ── Type inference ────────────────────────────────────────────────────────────

def infer_column_types(df: pd.DataFrame) -> dict[str, str]:
    """
    Classify each column as 'date', 'numeric', or 'categorical'.

    Returns
    -------
    dict[str, str]
        e.g. {"date": "date", "revenue": "numeric", "region": "categorical"}
    """
    col_types: dict[str, str] = {}
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            col_types[col] = "date"
        elif pd.api.types.is_numeric_dtype(df[col]):
            col_types[col] = "numeric"
        else:
            # Try to coerce to date
            try:
                pd.to_datetime(df[col].dropna().head(10))
                col_types[col] = "date"
            except Exception:
                col_types[col] = "categorical"
    return col_types


def _normalize(name: str) -> str:
    """Lowercase, strip whitespace, replace separators with underscore."""
    return re.sub(r"[\s\-./]+", "_", name.strip().lower())


def _score_match(col_norm: str, synonyms: list[str]) -> float:
    """Return a match score (0–1) between a column name and a list of synonyms."""
    for syn in synonyms:
        if syn == col_norm:
            return 1.0
        if syn in col_norm or col_norm in syn:
            return 0.7
    return 0.0


# ── Auto-suggestion ───────────────────────────────────────────────────────────

def suggest_mapping(df: pd.DataFrame) -> dict[str, str]:
    """
    Auto-suggest a mapping from df columns to canonical field names.

    Returns
    -------
    dict[str, str]
        Mapping of {canonical_field → df_column}. Only includes confident matches.
    """
    col_types = infer_column_types(df)
    mapping: dict[str, str] = {}
    used_cols: set[str] = set()

    for canonical in CANONICAL_FIELDS:
        synonyms = _SYNONYMS.get(canonical, [canonical])
        best_col, best_score = "", 0.0

        for col in df.columns:
            if col in used_cols:
                continue
            col_norm = _normalize(col)
            score = _score_match(col_norm, synonyms)

            # Type filter
            if score > 0:
                expected_type = (
                    "date" if canonical == "date"
                    else "numeric" if canonical in {"revenue", "traffic", "orders", "conversion_rate"}
                    else "categorical"
                )
                if col_types.get(col) != expected_type:
                    score *= 0.3   # penalise type mismatch

            if score > best_score:
                best_col, best_score = col, score

        if best_score >= 0.5:
            mapping[canonical] = best_col
            used_cols.add(best_col)

    logger.info("Suggested mapping: %s", mapping)
    return mapping


# ── Validation ────────────────────────────────────────────────────────────────

def validate_mapping(mapping: dict[str, str], df: pd.DataFrame | None = None) -> list[str]:
    """
    Validate a canonical mapping.

    Returns
    -------
    list[str]
        List of error messages. Empty list = valid.
    """
    errors: list[str] = []

    for field in REQUIRED_FIELDS:
        if not mapping.get(field):
            errors.append(f"Required field '{field}' is not mapped.")

    if df is not None:
        for canonical, col in mapping.items():
            if col and col not in df.columns:
                errors.append(f"Mapped column '{col}' for '{canonical}' does not exist in the dataset.")

    return errors


# ── Apply mapping ─────────────────────────────────────────────────────────────

def apply_mapping(df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    """
    Rename and select columns according to the mapping.

    Parameters
    ----------
    df :
        Raw DataFrame from the connector.
    mapping :
        Dict of {canonical_field → source_column} (only mapped fields).

    Returns
    -------
    pd.DataFrame
        DataFrame with canonical column names, containing only mapped columns.
        Optional unmapped columns are filled with a default value.
    """
    # Invert: source_col → canonical
    rename_map = {v: k for k, v in mapping.items() if v}
    df_out = df.rename(columns=rename_map)

    # Keep only canonical columns that exist
    keep = [c for c in CANONICAL_FIELDS if c in df_out.columns]
    df_out = df_out[keep].copy()

    # Fill optional missing columns with defaults
    for col in OPTIONAL_FIELDS:
        if col not in df_out.columns:
            df_out[col] = "Unknown"

    # Coerce date column
    if "date" in df_out.columns:
        df_out["date"] = pd.to_datetime(df_out["date"], errors="coerce")
        df_out = df_out.dropna(subset=["date"])
        df_out = df_out.sort_values("date").reset_index(drop=True)

    # Coerce numeric columns
    for col in ["revenue", "traffic", "orders", "conversion_rate"]:
        if col in df_out.columns:
            df_out[col] = pd.to_numeric(df_out[col], errors="coerce").fillna(0)

    logger.info("Applied mapping — output shape: %s", df_out.shape)
    return df_out
