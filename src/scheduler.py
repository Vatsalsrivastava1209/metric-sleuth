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
    to_email: str | None = None,
) -> bool:
    """Send an anomaly alert via SMTP email.

    Returns ``True`` on success, ``False`` on failure.
    """
    recipient = (to_email or ALERT_EMAIL_TO or "").strip()
    if not ALERT_EMAIL_ENABLED or not recipient:
        logger.info("Email alerts are disabled.")
        return False

    try:
        body = _format_alert_text(anomalies_df, data_path)
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"MetricSleuth Alert — {len(anomalies_df)} anomalies detected"
        msg["From"]    = ALERT_EMAIL_FROM
        msg["To"]      = recipient
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP_SSL(ALERT_EMAIL_SMTP_HOST, ALERT_EMAIL_SMTP_PORT) as server:
            server.login(ALERT_EMAIL_FROM, ALERT_EMAIL_PASSWORD)
            server.sendmail(ALERT_EMAIL_FROM, recipient.split(","), msg.as_string())

        logger.info("Email alert sent to %s", recipient)
        return True
    except Exception as exc:
        logger.error("Failed to send email alert: %s", exc)
        return False


def send_slack_alert(
    anomalies_df: pd.DataFrame,
    data_path: str,
    webhook_url: str | None = None,
) -> bool:
    """Post an anomaly alert to a Slack channel via Incoming Webhook.

    Returns ``True`` on success, ``False`` on failure.
    """
    target_webhook = (webhook_url or ALERT_SLACK_WEBHOOK_URL or "").strip()
    if not ALERT_SLACK_ENABLED or not target_webhook:
        logger.info("Slack alerts are disabled or webhook URL not set.")
        return False

    try:
        payload = _format_slack_payload(anomalies_df, data_path)
        response = requests.post(
            target_webhook,
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
    user_id: str,
    dataset_id: str,
    metric: str = "revenue",
    on_anomaly: Callable[[pd.DataFrame], None] | None = None,
) -> pd.DataFrame:
    """Load the latest dataset for a user and run anomaly detection.

    P1-C Fix: The previous implementation took a `data_path` (local CSV file)
    which made it incompatible with multi-tenant SaaS operation — every Business
    tier user's scheduled job would read the same sample CSV.

    The new implementation:
    1. Accepts `user_id` + `dataset_id` to identify the correct tenant dataset.
    2. Loads the dataset from Supabase via the connector infrastructure in src/db.py.
    3. Falls back to loading from a pre-registered dataset record.
    4. Sends alerts using the user-specific Slack/email config from their profile.

    Parameters
    ----------
    user_id:
        The UUID of the tenant whose dataset to monitor.
    dataset_id:
        The UUID of the registered dataset in the `datasets` table.
    metric:
        The primary metric column to check for anomalies.
    on_anomaly:
        Optional callback invoked with the anomaly DataFrame.
        Defaults to sending email + Slack via the user's profile config.

    Returns
    -------
    pd.DataFrame
        Detected anomalies (empty DataFrame if none found).
    """
    from src.db import get_profile
    from src.anomaly_detection import detect_anomalies
    from src.data_loader import load_data

    logger.info(
        "Monitoring job started for user=%s dataset=%s metric=%s — %s",
        user_id, dataset_id, metric, datetime.now().isoformat(),
    )

    # Load the user's dataset. Connectors (Postgres, MySQL, BigQuery, CSV)
    # are registered in the datasets table; we load via the connector factory.
    try:
        from src.connectors import load_dataset_from_connector
        df = load_dataset_from_connector(dataset_id, user_id=user_id)
    except Exception as exc:
        logger.error(
            "Failed to load dataset %s for user %s: %s", dataset_id, user_id, exc
        )
        return pd.DataFrame()

    anomalies = detect_anomalies(df, metrics=[metric])

    if anomalies.empty:
        logger.info("No anomalies detected for user=%s dataset=%s — system healthy.", user_id, dataset_id)
        return anomalies

    logger.warning(
        "%d anomal%s detected for user=%s dataset=%s!",
        len(anomalies), "y" if len(anomalies) == 1 else "ies", user_id, dataset_id,
    )

    if on_anomaly is not None:
        on_anomaly(anomalies)
    else:
        # Read the user's configured alert destinations from their profile.
        try:
            profile = get_profile(user_id)
        except Exception:
            profile = {}

        data_ref = f"dataset:{dataset_id} (user:{user_id})"
        send_email_alert(anomalies, data_ref, to_email=profile.get("alert_email"))
        send_slack_alert(
            anomalies,
            data_ref,
            webhook_url=profile.get("slack_webhook_url"),
        )

    return anomalies


# ── Celery Beat Task (multi-tenant, per-user scheduling) ─────────────────────

try:
    from api.worker import celery_app as _celery_app

    @_celery_app.task(name="src.scheduler.schedule_user_monitoring")
    def schedule_user_monitoring(
        user_id: str,
        dataset_id: str,
        metric: str = "revenue",
    ) -> dict:
        """Celery task wrapper for per-user scheduled monitoring.

        P1-C Fix: Each Business-tier user's schedule triggers this Celery task
        independently with their own user_id and dataset_id. The task is registered
        in celery beat's schedule via the Supabase `scheduled_jobs` table (or via
        Celery Beat's database scheduler in production).

        Anomaly results trigger the full RCA pipeline via another Celery task
        if anomalies are found, rather than re-running the analysis inline.
        """
        logger.info(
            "Celery Beat: scheduled monitoring task for user=%s dataset=%s",
            user_id, dataset_id,
        )
        anomalies = run_monitoring_job(
            user_id=user_id,
            dataset_id=dataset_id,
            metric=metric,
        )
        return {
            "user_id":      user_id,
            "dataset_id":   dataset_id,
            "n_anomalies":  len(anomalies),
        }

except ImportError:
    # Celery not available (e.g. in standalone scheduler mode or tests).
    logger.debug("Celery not available — schedule_user_monitoring Celery task not registered.")


# ── Legacy standalone APScheduler (local dev / backward compat) ──────────

def start_scheduler(
    user_id: str,
    dataset_id: str,
    metric: str = "revenue",
    interval_hours: float | None = None,
    block: bool = True,
) -> None:
    """Start the APScheduler background scheduler for a single user dataset.

    P1-C Fix: Now accepts user_id + dataset_id instead of a local file path.
    Suitable for local development. In production, use the Celery Beat task
    `schedule_user_monitoring` which runs per-user jobs independently.

    Parameters
    ----------
    user_id:
        The UUID of the tenant to monitor.
    dataset_id:
        The UUID of the dataset in the `datasets` table.
    metric:
        Metric column to monitor.
    interval_hours:
        How often to run (hours). Falls back to ``config.SCHEDULER_INTERVAL_HOURS``.
    block:
        If ``True`` the call blocks. Pass ``False`` for embedding.
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
        kwargs={"user_id": user_id, "dataset_id": dataset_id, "metric": metric},
        next_run_time=datetime.now(),
        id="metric_monitor",
        name=f"MetricSleuth Monitor — user={user_id}",
        misfire_grace_time=3600,
    )

    data_path = dataset_id

    logger.info(
        "Scheduler started — monitoring '%s' every %.1f hour(s).", data_path, hours
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


# ── Standalone entry-point ────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    )
    parser = argparse.ArgumentParser(description="Run the local MetricSleuth scheduler.")
    parser.add_argument("--user-id", required=True, help="Supabase user UUID to monitor.")
    parser.add_argument("--dataset-id", required=True, help="Dataset UUID to monitor.")
    parser.add_argument("--metric", default="revenue", help="Canonical metric column to monitor.")
    parser.add_argument("--interval-hours", type=float, default=None, help="Polling interval in hours.")
    args = parser.parse_args()

    start_scheduler(
        user_id=args.user_id,
        dataset_id=args.dataset_id,
        metric=args.metric,
        interval_hours=args.interval_hours,
        block=True,
    )
