"""
pages/5_⚙️_Settings.py
======================
Account settings — LLM config, alert settings, and logout.
"""

from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st
from src.auth import require_auth, render_tier_badge, logout
from src.billing import check_access, gate
from src.db import get_profile, update_profile

st.set_page_config(page_title="Settings | MetricSleuth", page_icon="⚙️", layout="wide")
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;600;700&family=JetBrains+Mono&display=swap');
html,body,[class*="css"],.stApp{font-family:'Space Grotesk',sans-serif;}
.stApp{background:#060912;color:#c9d1e3;}
[data-testid="stSidebar"]{background:#0b0f1e;border-right:1px solid #1a2040;}
.stButton>button{background:#00e5ff;color:#060912;border:none;border-radius:6px;font-weight:700;font-size:.78rem;letter-spacing:1.5px;text-transform:uppercase;padding:.55rem 1.8rem;}
</style>""", unsafe_allow_html=True)

user = require_auth()
uid  = user["id"]
tier = user["tier"]

with st.sidebar:
    st.markdown('<div style="font-size:1.2rem;font-weight:700;background:linear-gradient(90deg,#00e5ff,#7b68ee);-webkit-background-clip:text;-webkit-text-fill-color:transparent;">MetricSleuth</div>', unsafe_allow_html=True)
    render_tier_badge()
    st.divider()
    st.markdown(f"<small style='color:#3a4a6b;'>{user['email']}</small>", unsafe_allow_html=True)
    if st.button("🚪 Log Out"):
        logout()
        st.switch_page("Home.py")
    if st.button("⬅ Dashboard"):
        st.switch_page("pages/2_📊_Dashboard.py")

st.markdown("## ⚙️ Settings")
profile = get_profile(uid)

# ── LLM Configuration ─────────────────────────────────────────────────────────
with st.expander("🧠 AI / LLM Configuration", expanded=True):
    if gate("llm_summary"):
        st.caption("Configure the AI backend used for executive summaries.")
        llm_backend = st.selectbox(
            "LLM Backend",
            ["gemini", "openai"],
            index=0 if profile.get("llm_backend", "gemini") == "gemini" else 1,
        )
        llm_api_key = st.text_input(
            "API Key",
            value=profile.get("llm_api_key", ""),
            type="password",
            placeholder="Paste your Gemini or OpenAI API key here",
        )
        if st.button("Save LLM Config", key="save_llm"):
            ok = update_profile(uid, {"llm_backend": llm_backend, "llm_api_key": llm_api_key})
            if ok:
                # Update session
                user["profile"]["llm_backend"] = llm_backend
                user["profile"]["llm_api_key"] = llm_api_key
                st.success("LLM configuration saved.")
            else:
                st.error("Failed to save. Please try again.")

# ── Slack Alerts ──────────────────────────────────────────────────────────────
with st.expander("🔔 Slack Alerts"):
    if gate("slack_alerts"):
        st.caption("Receive anomaly alerts directly in your Slack channel.")
        slack_url = st.text_input(
            "Slack Incoming Webhook URL",
            value=profile.get("slack_webhook_url", ""),
            placeholder="https://hooks.slack.com/services/...",
        )
        if st.button("Save Slack Config", key="save_slack"):
            ok = update_profile(uid, {"slack_webhook_url": slack_url})
            st.success("Slack config saved." if ok else "Failed to save.")

# ── Email Alerts ──────────────────────────────────────────────────────────────
with st.expander("📧 Email Alerts"):
    if gate("email_alerts"):
        st.caption("Receive anomaly alert emails when the scheduler detects issues.")
        alert_email = st.text_input(
            "Alert destination email",
            value=profile.get("alert_email", ""),
            placeholder="alerts@yourcompany.com",
        )
        if st.button("Save Email Config", key="save_email"):
            ok = update_profile(uid, {"alert_email": alert_email})
            st.success("Email config saved." if ok else "Failed to save.")

# ── Account ───────────────────────────────────────────────────────────────────
with st.expander("👤 Account"):
    st.markdown(f"**Email:** {user['email']}")
    st.markdown(f"**Plan:** {tier.title()}")
    st.markdown(f"**User ID:** `{uid}`")
    st.caption("To delete your account, contact support@metricsleuth.io")
