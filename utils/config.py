"""
Configuration settings for MetricSleuth.

All tuneable parameters are centralised here.
Secrets (API keys, passwords, webhook URLs) are read from environment
variables and never hardcoded.
"""

from __future__ import annotations

import os

# Platform limits
MAX_UPLOAD_SIZE_BYTES: int = 200 * 1024 * 1024
MAX_UPLOAD_SIZE_LABEL: str = "200 MB"
MAX_INLINE_INGEST_RECORDS: int = int(os.getenv("MAX_INLINE_INGEST_RECORDS", "100000"))

# Anomaly detection
ANOMALY_Z_THRESHOLD: float = 2.0
ANOMALY_ROLLING_WINDOW: int = 7
ANOMALY_METRICS: list[str] = ["revenue", "traffic", "conversion_rate"]
ANOMALY_MIN_STD_THRESHOLD: float = 1e-3
ANOMALY_METRIC_THRESHOLDS: dict[str, float] = {
    "revenue": 2.0,
    "traffic": 2.2,
    "conversion_rate": 2.4,
}
ANOMALY_METRIC_WINDOWS: dict[str, int] = {
    "revenue": 7,
    "traffic": 7,
    "conversion_rate": 14,
}
ANOMALY_MIN_HISTORY_POINTS: int = int(os.getenv("ANOMALY_MIN_HISTORY_POINTS", "14"))
ANOMALY_MIN_COVERAGE_RATIO: float = float(os.getenv("ANOMALY_MIN_COVERAGE_RATIO", "0.75"))
ANOMALY_EVAL_THRESHOLD_GRID: list[float] = [1.8, 2.0, 2.2, 2.5, 3.0]
ANOMALY_EVAL_WINDOW_GRID: list[int] = [7, 14, 21]

# Prophet
PROPHET_INTERVAL_WIDTH: float = 0.95
PROPHET_FORECAST_DAYS: int = 30
PROPHET_MIN_HISTORY_POINTS: int = int(os.getenv("PROPHET_MIN_HISTORY_POINTS", "21"))
PROPHET_BACKTEST_MIN_TRAIN_POINTS: int = int(os.getenv("PROPHET_BACKTEST_MIN_TRAIN_POINTS", "28"))
USE_PROPHET: bool = os.getenv("USE_PROPHET", "true").lower() in ("true", "1", "yes")

# Correlation analysis
CORRELATION_PAIRS: list[tuple[str, str]] = [
    ("revenue", "traffic"),
    ("revenue", "conversion_rate"),
    ("revenue", "orders"),
]
STRONG_CORRELATION_THRESHOLD: float = 0.7

# Segmentation
SEGMENT_COLUMNS: list[str] = ["region", "device", "traffic_source"]

# Contribution analysis
CONTRIBUTION_FACTORS: list[str] = ["traffic", "conversion_rate", "orders"]

# Multi-metric compound analysis
COMPOUND_MIN_METRICS: int = 2

# LLM summary
LLM_BACKEND: str = os.getenv("LLM_BACKEND", "gemini")
LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-1.5-flash")
LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "300"))
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.3"))

# Scheduler
SCHEDULER_INTERVAL_HOURS: float = float(os.getenv("SCHEDULER_INTERVAL_HOURS", "24.0"))

# Email alerts
ALERT_EMAIL_ENABLED: bool = os.getenv("ALERT_EMAIL_ENABLED", "false").lower() == "true"
ALERT_EMAIL_FROM: str = os.getenv("ALERT_EMAIL_FROM", "")
ALERT_EMAIL_TO: str = os.getenv("ALERT_EMAIL_TO", "")
ALERT_EMAIL_SMTP_HOST: str = os.getenv("ALERT_EMAIL_SMTP_HOST", "smtp.gmail.com")
ALERT_EMAIL_SMTP_PORT: int = int(os.getenv("ALERT_EMAIL_SMTP_PORT", "465"))
ALERT_EMAIL_PASSWORD: str = os.getenv("ALERT_EMAIL_PASSWORD", "")

# Slack alerts
ALERT_SLACK_ENABLED: bool = os.getenv("ALERT_SLACK_ENABLED", "false").lower() == "true"
ALERT_SLACK_WEBHOOK_URL: str = os.getenv("ALERT_SLACK_WEBHOOK_URL", "")

# Report
REPORT_TITLE: str = "MetricSleuth - Metric Investigation Report"

# Data
DATE_COLUMN: str = "date"
REQUIRED_COLUMNS: list[str] = [
    "date",
    "revenue",
    "traffic",
    "orders",
    "conversion_rate",
    "region",
    "device",
    "traffic_source",
]
