"""
Configuration settings for MetricSleuth.
All tuneable parameters are centralised here so changing a value
propagates throughout the entire pipeline.
"""

# ── Anomaly Detection ────────────────────────────────────────────────────────
ANOMALY_Z_THRESHOLD: float = 2.0          # |Z-score| above which a point is an anomaly
ANOMALY_ROLLING_WINDOW: int = 7           # Rolling-window size for local stats (days)
ANOMALY_METRICS: list[str] = [            # Metrics to scan for anomalies
    "revenue",
    "traffic",
    "conversion_rate",
]

# ── Correlation Analysis ──────────────────────────────────────────────────────
CORRELATION_PAIRS: list[tuple[str, str]] = [
    ("revenue", "traffic"),
    ("revenue", "conversion_rate"),
    ("revenue", "orders"),
]
STRONG_CORRELATION_THRESHOLD: float = 0.7   # |r| ≥ this → considered strong

# ── Segmentation ─────────────────────────────────────────────────────────────
SEGMENT_COLUMNS: list[str] = ["region", "device", "traffic_source"]

# ── Contribution Analysis ─────────────────────────────────────────────────────
CONTRIBUTION_FACTORS: list[str] = ["traffic", "conversion_rate", "orders"]

# ── Report ────────────────────────────────────────────────────────────────────
REPORT_TITLE: str = "MetricSleuth – Root Cause Analysis Report"

# ── Data ──────────────────────────────────────────────────────────────────────
DATE_COLUMN: str = "date"
REQUIRED_COLUMNS: list[str] = [
    "date", "revenue", "traffic", "orders",
    "conversion_rate", "region", "device", "traffic_source",
]
