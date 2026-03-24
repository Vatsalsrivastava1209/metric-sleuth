"""
Home.py
=======
MetricSleuth — Landing page and login/signup gate.

This is the entry point for the Streamlit multi-page app.
Authenticated users are redirected to the Dashboard.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import streamlit as st
from src.auth import login, signup, is_authenticated

st.set_page_config(
    page_title="MetricSleuth | AI-Powered RCA",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Global CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
html, body, [class*="css"], .stApp { font-family: 'Space Grotesk', sans-serif; }
.stApp { background: #060912; color: #c9d1e3; }
[data-testid="stSidebar"] { display: none; }
.stButton > button {
    background: linear-gradient(135deg, #00e5ff, #7b68ee);
    color: #060912; border: none; border-radius: 8px;
    font-weight: 700; font-size: 0.85rem; letter-spacing: 1.5px;
    text-transform: uppercase; padding: .7rem 2rem;
    transition: opacity .15s; width: 100%;
}
.stButton > button:hover { opacity: .82; }
.stTextInput > div > input {
    background: #0d1327; border: 1px solid #1e2d52;
    color: #c9d1e3; border-radius: 8px; padding: 0.6rem 1rem;
}
.stTextInput > div > input:focus { border-color: #00e5ff; box-shadow: 0 0 0 2px rgba(0,229,255,.15); }
.auth-card {
    background: #0b0f1e; border: 1px solid #1a2040;
    border-radius: 16px; padding: 2.5rem;
    box-shadow: 0 20px 60px rgba(0,0,0,.5);
}
</style>
""", unsafe_allow_html=True)

# ── Redirect if already logged in ─────────────────────────────────────────────
if is_authenticated():
    st.switch_page("pages/2_📊_Dashboard.py")

# ── Hero section ──────────────────────────────────────────────────────────────
_, hero_col, _ = st.columns([1, 3, 1])
with hero_col:
    st.markdown("""
    <div style="text-align:center;padding:3rem 0 2rem;">
        <div style="font-size:2.6rem;font-weight:700;
            background:linear-gradient(90deg,#00e5ff,#7b68ee);
            -webkit-background-clip:text;-webkit-text-fill-color:transparent;
            letter-spacing:-1px;margin-bottom:.5rem;">
            MetricSleuth
        </div>
        <div style="font-size:1rem;color:#4a6fa5;max-width:520px;margin:0 auto;line-height:1.7;">
            AI-powered Root Cause Analysis for your business KPIs.<br>
            Detect anomalies, trace root causes, and get actionable insights — in minutes.
        </div>
    </div>
    """, unsafe_allow_html=True)

# ── Feature highlights ─────────────────────────────────────────────────────────
_, feat_col, _ = st.columns([0.5, 4, 0.5])
with feat_col:
    f1, f2, f3, f4 = st.columns(4)
    for col, icon, title, desc in [
        (f1, "🔍", "Anomaly Detection", "Z-score + Prophet ML detection on any metric"),
        (f2, "🧠", "AI Root Cause", "Ranked hypotheses with confidence scores"),
        (f3, "📈", "30-Day Forecast", "Prophet time-series forecasting built-in"),
        (f4, "💬", "RAG Memory", "Ask natural-language questions on past incidents"),
    ]:
        col.markdown(
            f"""<div style="background:#0b0f1e;border:1px solid #1a2040;border-radius:12px;
                padding:1.2rem;text-align:center;height:100%;">
                <div style="font-size:1.5rem;margin-bottom:.5rem;">{icon}</div>
                <div style="font-size:.8rem;font-weight:700;color:#c9d1e3;margin-bottom:.3rem;">{title}</div>
                <div style="font-size:.72rem;color:#3a4a6b;line-height:1.5;">{desc}</div>
            </div>""",
            unsafe_allow_html=True,
        )

st.markdown("<br>", unsafe_allow_html=True)

# ── Call to Action ────────────────────────────────────────────────────────────
_, cta_col, _ = st.columns([1, 1, 1])
with cta_col:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🚀 Try it Free Now", type="primary", use_container_width=True):
        st.switch_page("pages/1_🔗_Connect.py")

# ── Pricing strip ──────────────────────────────────────────────────────────────
st.markdown("<br><br>", unsafe_allow_html=True)
_, p_col, _ = st.columns([0.5, 4, 0.5])
with p_col:
    st.markdown(
        '<p style="text-align:center;font-size:.65rem;letter-spacing:2px;color:#1e2d52;'
        'text-transform:uppercase;margin-bottom:1.5rem;">Simple, transparent pricing</p>',
        unsafe_allow_html=True,
    )
    pc1, pc2, pc3 = st.columns(3)
    for col, tier, price, color, feats in [
        (pc1, "Free",     "$0/mo",   "#3a4a6b", ["1 dataset", "Z-score detection", "Markdown export", "Segment analysis"]),
        (pc2, "Pro",      "$29/mo",  "#00e5ff", ["5 datasets", "Prophet + Forecast", "PDF export", "AI summaries", "RAG history"]),
        (pc3, "Business", "$99/mo",  "#7b68ee", ["Unlimited datasets", "DB Connectors", "Slack + Email alerts", "Scheduler", "All Pro features"]),
    ]:
        feat_html = "".join(
            f'<div style="font-size:.76rem;color:#8892b0;padding:.2rem 0;">✓ {f}</div>'
            for f in feats
        )
        col.markdown(
            f"""<div style="background:#0b0f1e;border:1px solid {color}40;border-radius:12px;padding:1.5rem;text-align:center;">
                <div style="font-size:.65rem;letter-spacing:2px;color:{color};font-family:JetBrains Mono,monospace;margin-bottom:.3rem;">{tier.upper()}</div>
                <div style="font-size:1.6rem;font-weight:700;color:#e2e8f0;margin-bottom:1rem;">{price}</div>
                {feat_html}
            </div>""",
            unsafe_allow_html=True,
        )
