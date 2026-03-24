"""
pages/4_💳_Billing.py
======================
Billing and subscription management page.
Displays current plan, upgrade options, and Stripe Checkout / Portal links.
"""

from __future__ import annotations
import sys, os
from pathlib import Path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st
from src.auth import require_auth, render_tier_badge, refresh_profile
from src.billing import PLANS, create_checkout_session, create_portal_session
from src.db import get_profile, count_user_datasets

st.set_page_config(page_title="Billing | MetricSleuth", page_icon="💳", layout="wide")
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;600;700&family=JetBrains+Mono&display=swap');
html,body,[class*="css"],.stApp{font-family:'Space Grotesk',sans-serif;}
.stApp{background:#060912;color:#c9d1e3;}
[data-testid="stSidebar"]{background:#0b0f1e;border-right:1px solid #1a2040;}
</style>""", unsafe_allow_html=True)

user = require_auth()
uid  = user["id"]
tier = user["tier"]

# Handle post-checkout refresh
if st.query_params.get("upgraded"):
    refresh_profile()
    user = st.session_state.get("ms_user", user)
    tier = user.get("tier", "free")
    st.success("🎉 Your plan has been upgraded! Welcome to the next level.")
    st.query_params.clear()

with st.sidebar:
    st.markdown('<div style="font-size:1.2rem;font-weight:700;background:linear-gradient(90deg,#00e5ff,#7b68ee);-webkit-background-clip:text;-webkit-text-fill-color:transparent;">MetricSleuth</div>', unsafe_allow_html=True)
    render_tier_badge()
    st.divider()
    if st.button("⬅ Dashboard"):
        st.switch_page("pages/2_📊_Dashboard.py")

st.markdown("## 💳 Plan & Billing")
profile = get_profile(uid)
current_plan = PLANS.get(tier, PLANS["free"])
n_datasets   = count_user_datasets(uid)
max_ds       = current_plan["features"]["max_datasets"]

# Current plan card
plan_color = current_plan["color"]
st.markdown(
    f"""<div style="background:#0b0f1e;border:2px solid {plan_color}60;border-radius:16px;
        padding:1.5rem 2rem;margin-bottom:1.5rem;display:flex;align-items:center;gap:2rem;">
        <div>
            <div style="font-size:.65rem;letter-spacing:2px;color:{plan_color};font-family:JetBrains Mono;">CURRENT PLAN</div>
            <div style="font-size:1.8rem;font-weight:700;color:#e2e8f0;">{current_plan['label']}</div>
            <div style="font-size:.85rem;color:#4a6fa5;">${current_plan['price_monthly']}/month</div>
        </div>
        <div style="border-left:1px solid #1a2040;padding-left:2rem;">
            <div style="font-size:.72rem;color:#3a4a6b;">DATASETS</div>
            <div style="font-size:1.3rem;font-weight:700;color:#c9d1e3;">
                {n_datasets} / {'∞' if max_ds == -1 else max_ds}
            </div>
        </div>
    </div>""",
    unsafe_allow_html=True,
)

# Manage billing button (for paid users)
if tier in ("pro", "business") and profile.get("stripe_customer_id"):
    base_url = st.secrets.get("APP_BASE_URL", os.getenv("APP_BASE_URL", "http://localhost:8501"))
    portal_url = create_portal_session(
        profile["stripe_customer_id"],
        return_url=f"{base_url}/4_💳_Billing",
    )
    if portal_url:
        st.link_button("Manage Subscription (Stripe Portal) →", portal_url)

st.divider()

# ── Plan comparison ───────────────────────────────────────────────────────────
st.markdown("### All Plans")

plan_cols = st.columns(3)
for col, (plan_id, plan) in zip(plan_cols, PLANS.items()):
    is_current = plan_id == tier
    color = plan["color"]
    border = f"2px solid {color}" if is_current else f"1px solid {color}30"

    features_html = "".join(
        f'<div style="font-size:.76rem;color:#8892b0;padding:.25rem 0;">'
        f'{"✅" if v else "❌"} {k.replace("_"," ").title()}</div>'
        for k, v in plan["features"].items()
        if k not in ("max_datasets", "date_history_days")
    )

    with col:
        st.markdown(
            f"""<div style="background:#0b0f1e;border:{border};border-radius:14px;padding:1.5rem;text-align:center;min-height:520px;">
                <div style="font-size:.65rem;letter-spacing:2px;color:{color};font-family:JetBrains Mono;margin-bottom:.3rem;">
                    {plan['label'].upper()}{" · CURRENT" if is_current else ""}
                </div>
                <div style="font-size:2rem;font-weight:700;color:#e2e8f0;margin-bottom:.2rem;">
                    ${plan['price_monthly']}<span style="font-size:.9rem;color:#3a4a6b;">/mo</span>
                </div>
                <div style="font-size:.76rem;color:#3a4a6b;margin-bottom:1rem;">
                    {plan['features']['max_datasets'] if plan['features']['max_datasets'] != -1 else '∞'} datasets ·
                    {'Unlimited' if plan['features']['date_history_days'] == -1 else str(plan['features']['date_history_days'])+'d history'}
                </div>
                <hr style="border-color:#1a2040;margin:1rem 0;">
                {features_html}
            </div>""",
            unsafe_allow_html=True,
        )
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        if is_current:
            st.button("Current Plan", key=f"cur_{plan_id}", disabled=True)
        elif plan["price_monthly"] > 0:
            if st.button(f"Upgrade to {plan['label']} →", key=f"upg_{plan_id}", type="primary"):
                base_url = st.secrets.get("APP_BASE_URL", os.getenv("APP_BASE_URL", "http://localhost:8501"))
                url = create_checkout_session(
                    user_id=uid,
                    user_email=user["email"],
                    tier=plan_id,
                    success_url=f"{base_url}/4_💳_Billing",
                    cancel_url=f"{base_url}/4_💳_Billing",
                )
                if url:
                    st.markdown(f'<meta http-equiv="refresh" content="0; url={url}">', unsafe_allow_html=True)
                else:
                    st.error("Could not create checkout session. Stripe keys may not be configured.")
