"""
digest.py
=========
Portfolio-level Slack and Email digest for agency Monday morning reviews.

Aggregates open incidents across all client workspaces and sends a ranked
severity digest to Slack (via webhook) and/or Email (via SMTP). The digest
is the primary driver of the "Monday Morning Portfolio Review" workflow —
one message, all clients, sorted by urgency.

Gated by billing features "slack_alerts" and "email_alerts" (Portfolio plan).

Usage
-----
    from src.digest import send_portfolio_digest

    incidents = [
        {
            "client_name": "Acme Store",
            "workspace_id": "ws_123",
            "metric": "revenue",
            "direction": "drop",
            "deviation_score": 3.8,
            "revenue_impact": -12500.0,
            "top_hypothesis": "Traffic Volume Decline",
            "anomaly_date": "2026-04-28",
        },
        ...
    ]
    send_portfolio_digest(incidents, user_tier="business")
"""

from __future__ import annotations

import json
import logging
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import requests

from utils.config import (
    ALERT_EMAIL_ENABLED,
    ALERT_EMAIL_FROM,
    ALERT_EMAIL_PASSWORD,
    ALERT_EMAIL_SMTP_HOST,
    ALERT_EMAIL_SMTP_PORT,
    ALERT_EMAIL_TO,
    ALERT_SLACK_ENABLED,
    ALERT_SLACK_WEBHOOK_URL,
)

logger = logging.getLogger(__name__)


# ── Incident ranking ──────────────────────────────────────────────────────────

def _severity_score(incident: dict[str, Any]) -> float:
    """Composite urgency score: deviation magnitude × revenue impact magnitude."""
    deviation = abs(float(incident.get("deviation_score", 0)))
    revenue_impact = abs(float(incident.get("revenue_impact", 0)))
    # Normalise revenue impact to a 0-5 scale at $50k impact ceiling
    revenue_score = min(revenue_impact / 10_000, 5.0)
    return deviation + revenue_score


def rank_incidents(incidents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort incidents by composite severity score, highest first."""
    return sorted(incidents, key=_severity_score, reverse=True)


# ── Slack formatter ───────────────────────────────────────────────────────────

def _severity_emoji(score: float) -> str:
    if score >= 7:
        return ":red_circle:"
    if score >= 4:
        return ":large_yellow_circle:"
    return ":large_green_circle:"


def _format_slack_message(
    incidents: list[dict[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    """Build a Slack Block Kit message for the portfolio digest."""
    ranked = rank_incidents(incidents)
    open_count = len(ranked)

    header_text = (
        f"*MetricSleuth Portfolio Digest* — {generated_at}\n"
        f"{open_count} open incident{'s' if open_count != 1 else ''} across your client portfolio."
    )

    blocks: list[dict] = [
        {"type": "header", "text": {"type": "plain_text", "text": "MetricSleuth — Monday Portfolio Review"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": header_text}},
        {"type": "divider"},
    ]

    for i, inc in enumerate(ranked[:10], 1):  # cap at 10 to stay within Slack limits
        score = _severity_score(inc)
        emoji = _severity_emoji(score)
        client = inc.get("client_name", "Unknown Client")
        metric = inc.get("metric", "metric")
        direction = inc.get("direction", "change")
        hypothesis = inc.get("top_hypothesis", "Under investigation")
        date = inc.get("anomaly_date", "N/A")
        impact = inc.get("revenue_impact")
        impact_str = f"  |  Revenue impact: ${impact:+,.0f}" if impact else ""

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"{emoji}  *#{i} — {client}*\n"
                    f">{metric.replace('_', ' ').title()} {direction} on {date}{impact_str}\n"
                    f">Likely driver: _{hypothesis}_"
                ),
            },
        })

    if len(ranked) > 10:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"_...and {len(ranked) - 10} more. Log in to MetricSleuth for the full portfolio view._",
            },
        })

    blocks.append({"type": "divider"})
    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": "Sent by MetricSleuth Portfolio Digest"}],
    })

    return {"blocks": blocks}


def send_slack_digest(
    incidents: list[dict[str, Any]],
    webhook_url: str | None = None,
) -> bool:
    """Send the portfolio digest to a Slack webhook. Returns True on success."""
    url = webhook_url or ALERT_SLACK_WEBHOOK_URL
    if not url:
        logger.warning("Slack digest skipped: ALERT_SLACK_WEBHOOK_URL not configured.")
        return False

    generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    payload = _format_slack_message(incidents, generated_at)

    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        logger.info("Slack portfolio digest sent (%d incidents).", len(incidents))
        return True
    except Exception as exc:
        logger.error("Slack digest failed: %s", exc)
        return False


# ── Email formatter ───────────────────────────────────────────────────────────

def _format_email_html(
    incidents: list[dict[str, Any]],
    generated_at: str,
) -> str:
    """Build an HTML email body for the portfolio digest."""
    ranked = rank_incidents(incidents)
    rows = ""
    for i, inc in enumerate(ranked, 1):
        score = _severity_score(inc)
        color = "#c0392b" if score >= 7 else "#e67e22" if score >= 4 else "#27ae60"
        client = inc.get("client_name", "Unknown")
        metric = inc.get("metric", "metric").replace("_", " ").title()
        direction = inc.get("direction", "change")
        hypothesis = inc.get("top_hypothesis", "Under investigation")
        date = inc.get("anomaly_date", "N/A")
        impact = inc.get("revenue_impact")
        impact_str = f"${impact:+,.0f}" if impact else "—"

        rows += f"""
        <tr>
          <td style="padding:8px;color:{color};font-weight:bold">#{i}</td>
          <td style="padding:8px">{client}</td>
          <td style="padding:8px">{metric} {direction}</td>
          <td style="padding:8px">{date}</td>
          <td style="padding:8px">{impact_str}</td>
          <td style="padding:8px;font-style:italic">{hypothesis}</td>
        </tr>"""

    return f"""
    <html><body style="font-family:Arial,sans-serif;color:#333">
      <h2 style="color:#1a1a2e">MetricSleuth Portfolio Digest</h2>
      <p>{generated_at} &mdash; {len(ranked)} open incident(s)</p>
      <table border="0" cellspacing="0" cellpadding="0" style="border-collapse:collapse;width:100%">
        <thead style="background:#f0f0f0">
          <tr>
            <th style="padding:8px;text-align:left">#</th>
            <th style="padding:8px;text-align:left">Client</th>
            <th style="padding:8px;text-align:left">Incident</th>
            <th style="padding:8px;text-align:left">Date</th>
            <th style="padding:8px;text-align:left">Revenue Impact</th>
            <th style="padding:8px;text-align:left">Likely Driver</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
      <p style="color:#888;font-size:12px;margin-top:24px">
        Sent by MetricSleuth. Log in to investigate and export client briefs.
      </p>
    </body></html>
    """


def send_email_digest(
    incidents: list[dict[str, Any]],
    to_address: str | None = None,
    from_address: str | None = None,
    smtp_host: str | None = None,
    smtp_port: int | None = None,
    smtp_password: str | None = None,
) -> bool:
    """Send the portfolio digest via SMTP (SSL). Returns True on success."""
    to_addr   = to_address   or ALERT_EMAIL_TO
    from_addr = from_address or ALERT_EMAIL_FROM
    host      = smtp_host    or ALERT_EMAIL_SMTP_HOST
    port      = smtp_port    or ALERT_EMAIL_SMTP_PORT
    password  = smtp_password or ALERT_EMAIL_PASSWORD

    if not all([to_addr, from_addr, host, password]):
        logger.warning("Email digest skipped: SMTP credentials not fully configured.")
        return False

    generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    subject = f"MetricSleuth Portfolio Digest — {len(incidents)} Open Incident(s) ({generated_at})"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = from_addr
    msg["To"]      = to_addr

    plain_lines = [f"MetricSleuth Portfolio Digest — {generated_at}", ""]
    for i, inc in enumerate(rank_incidents(incidents), 1):
        plain_lines.append(
            f"#{i} {inc.get('client_name','?')} | {inc.get('metric','?')} {inc.get('direction','?')} "
            f"on {inc.get('anomaly_date','?')} | {inc.get('top_hypothesis','?')}"
        )
    msg.attach(MIMEText("\n".join(plain_lines), "plain"))
    msg.attach(MIMEText(_format_email_html(incidents, generated_at), "html"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=context) as server:
            server.login(from_addr, password)
            server.sendmail(from_addr, to_addr, msg.as_string())
        logger.info("Email portfolio digest sent to %s (%d incidents).", to_addr, len(incidents))
        return True
    except Exception as exc:
        logger.error("Email digest failed: %s", exc)
        return False


# ── Public API ────────────────────────────────────────────────────────────────

def send_portfolio_digest(
    incidents: list[dict[str, Any]],
    user_tier: str = "business",
    slack_webhook_url: str | None = None,
    email_to: str | None = None,
) -> dict[str, bool]:
    """Send the portfolio digest via all configured channels.

    Respects billing tier gates — slack_alerts and email_alerts are both
    Portfolio-plan features. Pass user_tier from the authenticated session.

    Parameters
    ----------
    incidents:
        List of incident dicts (see module docstring for schema).
    user_tier:
        Caller's billing tier. Used to gate channel access.
    slack_webhook_url:
        Override for the Slack webhook URL (testing or per-user webhooks).
    email_to:
        Override for the destination email address.

    Returns
    -------
    dict
        {"slack": bool, "email": bool} — True when delivery succeeded.
    """
    from src.billing import check_access

    results: dict[str, bool] = {"slack": False, "email": False}

    if not incidents:
        logger.info("Portfolio digest skipped: no incidents to report.")
        return results

    if check_access("slack_alerts", user_tier) and ALERT_SLACK_ENABLED:
        results["slack"] = send_slack_digest(incidents, webhook_url=slack_webhook_url)

    if check_access("email_alerts", user_tier) and ALERT_EMAIL_ENABLED:
        results["email"] = send_email_digest(incidents, to_address=email_to)

    return results
