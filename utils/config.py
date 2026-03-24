"""
Configuration settings for MetricSleuth.
All tuneable parameters are centralised here.
"""

# ── Anomaly Detection ────────────────────────────────────────────────────────
ANOMALY_Z_THRESHOLD: float = 2.0
ANOMALY_ROLLING_WINDOW: int = 7
ANOMALY_METRICS: list[str] = ["revenue", "traffic", "conversion_rate"]

# ── Prophet ───────────────────────────────────────────────────────────────────
PROPHET_INTERVAL_WIDTH: float = 0.95    # confidence band width (0-1)
PROPHET_FORECAST_DAYS: int = 30         # days to forecast into the future

# ── Correlation Analysis ──────────────────────────────────────────────────────
CORRELATION_PAIRS: list[tuple[str, str]] = [
    ("revenue", "traffic"),
    ("revenue", "conversion_rate"),
    ("revenue", "orders"),
]
STRONG_CORRELATION_THRESHOLD: float = 0.7

# ── Segmentation ─────────────────────────────────────────────────────────────
SEGMENT_COLUMNS: list[str] = ["region", "device", "traffic_source"]

# ── Contribution Analysis ─────────────────────────────────────────────────────
CONTRIBUTION_FACTORS: list[str] = ["traffic", "conversion_rate", "orders"]

# ── Multi-metric Compound Analysis ───────────────────────────────────────────
COMPOUND_MIN_METRICS: int = 2   # minimum simultaneous anomalies to flag compound

# ── LLM Summary ──────────────────────────────────────────────────────────────
# Set LLM_BACKEND to "gemini" or "openai"
# Set LLM_API_KEY to your API key (or use .streamlit/secrets.toml)
LLM_BACKEND: str = "gemini"          # "gemini" | "openai"
LLM_MODEL: str = "gemini-1.5-flash"  # or "gpt-4o-mini" for openai
LLM_API_KEY: str = ""                # set via env var or secrets.toml
LLM_MAX_TOKENS: int = 300
LLM_TEMPERATURE: float = 0.3

# ── Scheduler ────────────────────────────────────────────────────────────────
SCHEDULER_INTERVAL_HOURS: float = 24.0   # how often to run monitoring

# Email alerts (SMTP)
ALERT_EMAIL_ENABLED: bool = False
ALERT_EMAIL_FROM: str = ""
ALERT_EMAIL_TO: str = ""
ALERT_EMAIL_SMTP_HOST: str = "smtp.gmail.com"
ALERT_EMAIL_SMTP_PORT: int = 465
ALERT_EMAIL_PASSWORD: str = ""

# Slack alerts (Incoming Webhook)
ALERT_SLACK_ENABLED: bool = False
ALERT_SLACK_WEBHOOK_URL: str = ""

# ── Report ────────────────────────────────────────────────────────────────────
REPORT_TITLE: str = "MetricSleuth — Root Cause Analysis Report"

# ── Data ──────────────────────────────────────────────────────────────────────
DATE_COLUMN: str = "date"
REQUIRED_COLUMNS: list[str] = [
    "date", "revenue", "traffic", "orders",
    "conversion_rate", "region", "device", "traffic_source",
]


