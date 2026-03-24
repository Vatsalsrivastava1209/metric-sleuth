"""
pages/3_📈_Reports.py
======================
Past RCA Reports browser — shows all reports saved to Supabase for the
current user, with full markdown viewer.
"""

from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st
from src.auth import require_auth, render_tier_badge
from src.db import get_user_reports, get_report

st.set_page_config(page_title="Reports | MetricSleuth", page_icon="📈", layout="wide")
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;600;700&family=JetBrains+Mono&display=swap');
html,body,[class*="css"],.stApp{font-family:'Space Grotesk',sans-serif;}
.stApp{background:#060912;color:#c9d1e3;}
[data-testid="stSidebar"]{background:#0b0f1e;border-right:1px solid #1a2040;}
.stButton>button{background:#00e5ff;color:#060912;border:none;border-radius:6px;font-weight:700;}
</style>""", unsafe_allow_html=True)

user = require_auth()
uid  = user["id"]

with st.sidebar:
    st.markdown('<div style="font-size:1.2rem;font-weight:700;background:linear-gradient(90deg,#00e5ff,#7b68ee);-webkit-background-clip:text;-webkit-text-fill-color:transparent;">MetricSleuth</div>', unsafe_allow_html=True)
    render_tier_badge()
    st.divider()
    if st.button("⬅ Dashboard"):
        st.switch_page("pages/2_📊_Dashboard.py")

st.markdown("## 📈 RCA Report History")
st.caption("All anomaly analyses run on your datasets, stored automatically.")

reports = get_user_reports(uid)

if not reports:
    st.info("No reports yet. Go to the **Dashboard** → **RCA Report** tab to run your first analysis.")
else:
    df_r = pd.DataFrame(reports)
    df_r["anomaly_date"] = pd.to_datetime(df_r["anomaly_date"]).dt.strftime("%Y-%m-%d")
    df_r["created_at"]   = pd.to_datetime(df_r["created_at"]).dt.strftime("%Y-%m-%d %H:%M")
    df_r["confidence"]   = df_r["confidence"].apply(lambda x: f"{float(x or 0):.0%}")

    # Summary metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Reports",    len(reports))
    m2.metric("Metrics Analysed", df_r["primary_metric"].nunique())
    m3.metric("Latest Analysis",  df_r["created_at"].iloc[0] if len(reports) > 0 else "—")
    m4.metric("Avg Anomalies/Report", f"{df_r['n_anomalies'].mean():.1f}")

    st.divider()

    # Report list
    for _, row in df_r.iterrows():
        with st.expander(
            f"**{row['anomaly_date']}** — {row['primary_metric'].upper()} · "
            f"{row['n_anomalies']} anomalies · confidence {row['confidence']}"
        ):
            if row.get("executive_summary"):
                st.markdown(
                    f'<div style="background:#0d1327;border:1px solid #1e2d52;border-radius:8px;'
                    f'padding:1rem;font-size:.87rem;line-height:1.7;color:#c9d1e3;">'
                    f'{row["executive_summary"]}</div>',
                    unsafe_allow_html=True,
                )
            if row.get("top_hypothesis"):
                st.markdown(f"**Top hypothesis:** {row['top_hypothesis']}")

            col_a, col_b = st.columns(2)
            if col_a.button("View Full Report", key=f"view_{row['id']}"):
                full = get_report(row["id"], uid)
                if full and full.get("report_md"):
                    st.markdown(full["report_md"])
                else:
                    st.info("Full report markdown not available.")
            if col_b.button("Download Markdown", key=f"dl_{row['id']}"):
                full = get_report(row["id"], uid)
                if full and full.get("report_md"):
                    st.download_button(
                        "📥 Download",
                        data=full["report_md"],
                        file_name=f"rca_{row['anomaly_date']}.md",
                        mime="text/markdown",
                        key=f"dld_{row['id']}",
                    )
