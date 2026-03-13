"""
scheduler.py
============
Automated anomaly monitoring using APScheduler.

Runs the anomaly detection pipeline on a schedule (default: daily) and
sends alert notifications via email and/or Slack when anomalies are found.

Usage (standalone)
------------------
    python src/scheduler.py

Usage (programmatic)
--------------------
    from src.scheduler import start_scheduler
    start_scheduler(data_path="data/sample_ecommerce.csv")
"""

from __future__ import annotations

import logging
import smtplib
import json
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Callable

import pandas as pd
import requests

from utils.config import (
    SCHEDULER_INTERVAL_HOURS,
    ALERT_EMAIL_ENABLED,
    ALERT_EMAIL_FROM,
    ALERT_EMAIL_TO,
    ALERT_EMAIL_SMTP_HOST,
    ALERT_EMAIL_SMTP_PORT,
    ALERT_EMAIL_PASSWORD,
    ALERT_SLACK_ENABLED,
    ALERT_SLACK_WEBHOOK_URL,
    ANOMALY_METRICS,
    DATE_COLUMN,
)

logger = logging.getLogger(__name__)


# ── Alert formatting ──────────────────────────────────────────────────────────

def _format_alert_text(anomalies_df: pd.DataFrame, data_path: str) -> str:
    """Build a plain-text alert message from an anomalies DataFrame."""
    lines = [
        f"MetricSleuth Alert — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Dataset: {data_path}",
        f"Anomalies detected: {len(anomalies_df)}",
        "",
    ]
    for _, row in anomalies_df.head(10).iterrows():
        lines.append(
            f"  [{row.get('direction', '?').upper()}] {row['metric']}  |  "
            f"Date: {str(row['date'])[:10]}  |  "
            f"Observed: {row.get('observed_value', '?'):.2f}  |  "
            f"Z-score: {row.get('deviation_score', row.get('z_score', '?'))}"
        )
    lines.append("")
    lines.append("Open MetricSleuth dashboard for full RCA analysis.")
    return "\n".join(lines)


def _format_slack_payload(anomalies_df: pd.DataFrame, data_path: str) -> dict:
    """Build a Slack Block Kit payload for the alert."""
    summary = _format_alert_text(anomalies_df, data_path)
    worst = anomalies_df.sort_values(
        "deviation_score" if "deviation_score" in anomalies_df.columns else "date",
        ascending=False,
    ).iloc[0]

    color = "#ff4d6d" if worst.get("direction") == "drop" else "#f59e0b"

    return {
        "attachments": [
            {
                "color": color,
                "title": f"MetricSleuth Alert — {len(anomalies_df)} anomal{'y' if len(anomalies_df)==1 else 'ies'} detected",
                "text": f"```{summary}```",
                "footer": "MetricSleuth RCA Engine",
                "ts": int(datetime.now().timestamp()),
            }
        ]
    }


# ── Notification senders ──────────────────────────────────────────────────────

def send_email_alert(
    anomalies_df: pd.DataFrame,
    data_path: str,
) -> bool:
    """Send an anomaly alert via SMTP email.

    Returns ``True`` on success, ``False`` on failure.
    """
    if not ALERT_EMAIL_ENABLED:
        logger.info("Email alerts are disabled.")
        return False

    try:
        body = _format_alert_text(anomalies_df, data_path)
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"MetricSleuth Alert — {len(anomalies_df)} anomalies detected"
        msg["From"]    = ALERT_EMAIL_FROM
        msg["To"]      = ALERT_EMAIL_TO
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP_SSL(ALERT_EMAIL_SMTP_HOST, ALERT_EMAIL_SMTP_PORT) as server:
            server.login(ALERT_EMAIL_FROM, ALERT_EMAIL_PASSWORD)
            server.sendmail(ALERT_EMAIL_FROM, ALERT_EMAIL_TO.split(","), msg.as_string())

        logger.info("Email alert sent to %s", ALERT_EMAIL_TO)
        return True
    except Exception as exc:
        logger.error("Failed to send email alert: %s", exc)
        return False


def send_slack_alert(
    anomalies_df: pd.DataFrame,
    data_path: str,
) -> bool:
    """Post an anomaly alert to a Slack channel via Incoming Webhook.

    Returns ``True`` on success, ``False`` on failure.
    """
    if not ALERT_SLACK_ENABLED or not ALERT_SLACK_WEBHOOK_URL:
        logger.info("Slack alerts are disabled or webhook URL not set.")
        return False

    try:
        payload = _format_slack_payload(anomalies_df, data_path)
        response = requests.post(
            ALERT_SLACK_WEBHOOK_URL,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        response.raise_for_status()
        logger.info("Slack alert sent (status %s).", response.status_code)
        return True
    except Exception as exc:
        logger.error("Failed to send Slack alert: %s", exc)
        return False


# ── Core monitoring job ───────────────────────────────────────────────────────

def run_monitoring_job(
    data_path: str,
    on_anomaly: Callable[[pd.DataFrame], None] | None = None,
) -> pd.DataFrame:
    """Load the latest dataset and run anomaly detection.

    Parameters
    ----------
    data_path:
        Path to the CSV dataset to monitor.
    on_anomaly:
        Optional callback invoked with the anomalies DataFrame when anomalies
        are found.  Defaults to sending email + Slack alerts.

    Returns
    -------
    pd.DataFrame
        Detected anomalies (empty DataFrame if none found).
    """
    from src.data_loader import load_data
    from src.anomaly_detection import detect_anomalies

    logger.info("Monitoring job started — %s", datetime.now().isoformat())

    try:
        df = load_data(data_path)
    except Exception as exc:
        logger.error("Failed to load dataset: %s", exc)
        return pd.DataFrame()

    anomalies = detect_anomalies(df, metrics=ANOMALY_METRICS)

    if anomalies.empty:
        logger.info("No anomalies detected — system healthy.")
        return anomalies

    logger.warning("%d anomal%s detected!", len(anomalies), "y" if len(anomalies)==1 else "ies")

    if on_anomaly is not None:
        on_anomaly(anomalies)
    else:
        # Default: fire both email and Slack
        send_email_alert(anomalies, data_path)
        send_slack_alert(anomalies, data_path)

    return anomalies


# ── Scheduler setup ───────────────────────────────────────────────────────────

def start_scheduler(
    data_path: str = "data/sample_ecommerce.csv",
    interval_hours: float | None = None,
    block: bool = True,
) -> None:
    """Start the APScheduler background scheduler.

    Parameters
    ----------
    data_path:
        Path to the dataset to monitor.
    interval_hours:
        How often to run the monitoring job (hours). Falls back to
        ``config.SCHEDULER_INTERVAL_HOURS``.
    block:
        If ``True`` the call blocks (suitable for standalone execution).
        Pass ``False`` if embedding in another process (e.g. Streamlit).
    """
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError as exc:
        raise ImportError(
            "APScheduler is not installed. Run: pip install APScheduler"
        ) from exc

    hours = interval_hours or SCHEDULER_INTERVAL_HOURS
    SchedulerClass = BlockingScheduler if block else BackgroundScheduler

    scheduler = SchedulerClass()
    scheduler.add_job(
        run_monitoring_job,
        trigger="interval",
        hours=hours,
        args=[data_path],
        next_run_time=datetime.now(),   # run immediately on start
        id="metric_monitor",
        name="MetricSleuth Daily Monitor",
        misfire_grace_time=3600,
    )

    logger.info(
        "Scheduler started — monitoring '%s' every %.1f hour(s).", data_path, hours
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


# ── Standalone entry-point ────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    )
    start_scheduler(data_path="data/sample_ecommerce.csv", block=True)
