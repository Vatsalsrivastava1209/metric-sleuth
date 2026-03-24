"""
pages/2_📊_Dashboard.py
========================
Main RCA Dashboard — the existing MetricSleuth analytics engine,
wrapped with auth guard, tier gates, and Supabase report persistence.
"""

from __future__ import annotations
import io, sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.auth import get_current_user, render_tier_badge, logout
from src.billing import gate, check_access
from src.db import save_report_meta, get_user_datasets

from src.data_loader import load_data, load_data_from_upload
from src.anomaly_detection import detect_anomalies, annotate_dataframe, get_anomaly_dates
from src.segmentation_analysis import analyse_all_segments
from src.correlation_analysis import analyse_correlations, build_correlation_matrix
from src.contribution_analysis import compute_contributions
from src.hypothesis_engine import generate_hypotheses, hypotheses_to_dataframe
from src.report_generator import build_report, report_to_markdown
from src.llm_summary import generate_executive_summary
from utils.config import ANOMALY_METRICS, PROPHET_FORECAST_DAYS, PROPHET_INTERVAL_WIDTH

st.set_page_config(page_title="Dashboard | MetricSleuth", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
html,body,[class*="css"],.stApp{font-family:'Space Grotesk',sans-serif;}
.stApp{background:#060912;color:#c9d1e3;}
[data-testid="stSidebar"]{background:#0b0f1e;border-right:1px solid #1a2040;}
[data-testid="stSidebar"] *{color:#8892b0!important;}
[data-testid="metric-container"]{background:#0d1327;border:1px solid #1e2d52;border-radius:10px;padding:14px 18px;}
[data-testid="metric-container"] label{color:#3f5185!important;font-size:.72rem;letter-spacing:1.5px;text-transform:uppercase;}
[data-testid="metric-container"] [data-testid="stMetricValue"]{color:#e2e8f0!important;font-family:'JetBrains Mono',monospace;font-size:1.5rem;}
.section-label{font-size:.68rem;letter-spacing:2.5px;text-transform:uppercase;color:#2d4070;margin-bottom:.25rem;}
button[role="tab"]{font-size:.78rem;letter-spacing:1.5px;text-transform:uppercase;color:#3a4a6b!important;}
button[role="tab"][aria-selected="true"]{color:#00e5ff!important;border-bottom:2px solid #00e5ff;}
.stButton>button{background:#00e5ff;color:#060912;border:none;border-radius:6px;font-weight:700;font-size:.78rem;letter-spacing:1.5px;text-transform:uppercase;padding:.55rem 1.8rem;transition:opacity .15s;}
.stButton>button:hover{opacity:.8;}
</style>""", unsafe_allow_html=True)

user = get_current_user()
uid  = user["id"] if user else "anonymous"
tier = user["tier"] if user else "free"
is_logged_in = user is not None

_THEME = "plotly_dark"
_PAPER = "rgba(0,0,0,0)"
_PLOT  = "rgba(255,255,255,0.015)"
_GRID  = "rgba(255,255,255,0.04)"
C_CYAN, C_PURPLE, C_RED, C_AMBER, C_GREEN = "#00e5ff", "#7b68ee", "#ff4d6d", "#ffb703", "#06d6a0"

def _bl(**extra):
    return dict(template=_THEME, paper_bgcolor=_PAPER, plot_bgcolor=_PLOT,
                font=dict(family="Space Grotesk", color="#8892b0", size=11),
                xaxis=dict(gridcolor=_GRID, zeroline=False),
                yaxis=dict(gridcolor=_GRID, zeroline=False),
                margin=dict(l=40, r=20, t=50, b=40), **extra)

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<div style="font-size:1.4rem;font-weight:700;background:linear-gradient(90deg,#00e5ff,#7b68ee);'
        '-webkit-background-clip:text;-webkit-text-fill-color:transparent;">MetricSleuth</div>'
        '<div style="font-size:.65rem;color:#2d4070;letter-spacing:2px;text-transform:uppercase;'
        'font-family:JetBrains Mono,monospace;">Root Cause Analysis Engine</div>',
        unsafe_allow_html=True,
    )
    render_tier_badge()
    st.divider()

    st.markdown('<p class="section-label">Navigation</p>', unsafe_allow_html=True)
    if st.button("🔗 Connect Data"):
        st.switch_page("pages/1_🔗_Connect.py")
    if st.button("📈 Reports"):
        st.switch_page("pages/3_📈_Reports.py")
    if st.button("💳 Billing"):
        st.switch_page("pages/4_💳_Billing.py")
    if st.button("⚙️ Settings"):
        st.switch_page("pages/5_⚙️_Settings.py")
    if is_logged_in:
        if st.button("🚪 Log Out"):
            logout()
            st.switch_page("Home.py")
    else:
        if st.button("🔑 Log In / Sign Up"):
            st.switch_page("pages/6_🔑_Login.py")

    st.divider()
    st.markdown('<p class="section-label">Data Source</p>', unsafe_allow_html=True)

    # Load active dataset from session, or fallback to sample
    active_df_json = st.session_state.get("active_df")
    active_ds_name = st.session_state.get("active_dataset_name", "Sample dataset")

    st.divider()
    st.markdown('<p class="section-label">Date Range</p>', unsafe_allow_html=True)
    date_range_option = st.selectbox("Range", ["All data","Last 7 days","Last 30 days","Last quarter","Custom"], label_visibility="collapsed")
    custom_start, custom_end = None, None
    if date_range_option == "Custom":
        custom_start = st.date_input("From")
        custom_end   = st.date_input("To")

    st.divider()
    st.markdown('<p class="section-label">Detection</p>', unsafe_allow_html=True)
    detector       = st.radio("Detector", ["Z-score", "Prophet"], label_visibility="collapsed")
    z_threshold    = st.slider("Z-score threshold", 1.0, 4.0, 2.0, 0.25)
    rolling_window = st.slider("Rolling window (days)", 3, 21, 7)
    forecast_days  = st.slider("Forecast horizon (days)", 7, 90, PROPHET_FORECAST_DAYS)

    st.divider()
    st.markdown(f'<p style="font-size:.68rem;color:#1e2d52;letter-spacing:1px;">MetricSleuth v2.0 SaaS · {active_ds_name}</p>', unsafe_allow_html=True)



# ── Data load ─────────────────────────────────────────────────────────────────
try:
    if active_df_json:
        df_raw = pd.read_json(io.StringIO(active_df_json), orient="split")
        df_raw["date"] = pd.to_datetime(df_raw["date"])
        st.info(f"**{active_ds_name}** — {len(df_raw):,} rows")
    else:
        df_raw = load_data(ROOT / "data" / "sample_ecommerce.csv")
        st.info(f"Sample dataset — {len(df_raw):,} rows. [Connect your own data →](pages/1_🔗_Connect.py)")
except (FileNotFoundError, ValueError) as exc:
    st.error(str(exc))
    st.stop()

# ── Date filter ────────────────────────────────────────────────────────────────
def _apply_date_filter(df: pd.DataFrame) -> pd.DataFrame:
    max_date = df["date"].max()
    if date_range_option == "Last 7 days":
        return df[df["date"] >= max_date - pd.Timedelta(days=7)]
    elif date_range_option == "Last 30 days":
        return df[df["date"] >= max_date - pd.Timedelta(days=30)]
    elif date_range_option == "Last quarter":
        return df[df["date"] >= max_date - pd.Timedelta(days=90)]
    elif date_range_option == "Custom" and custom_start and custom_end:
        return df[(df["date"] >= pd.Timestamp(custom_start)) & (df["date"] <= pd.Timestamp(custom_end))]
    return df

df_raw = _apply_date_filter(df_raw)

@st.cache_data
def _run_pipeline(df_json: str) -> dict:
    df = pd.read_json(io.StringIO(df_json), orient="split")
    df["date"] = pd.to_datetime(df["date"])
    anomalies_df    = detect_anomalies(df)
    annotated_df    = annotate_dataframe(df, anomalies_df)
    correlations_df = analyse_correlations(df)
    corr_matrix     = build_correlation_matrix(df, ["revenue","traffic","orders","conversion_rate"])
    dates           = get_anomaly_dates(anomalies_df)
    return dict(df=df, annotated_df=annotated_df, anomalies_df=anomalies_df,
                correlations_df=correlations_df, corr_matrix=corr_matrix, anomaly_dates=dates)

with st.spinner("Running pipeline…"):
    cache_key = df_raw.to_json(orient="split", date_format="iso")
    pipeline  = _run_pipeline(cache_key)

df       = pipeline["df"]
ann_df   = pipeline["annotated_df"]
anomalies= pipeline["anomalies_df"]
corr_df  = pipeline["correlations_df"]
corr_mat = pipeline["corr_matrix"]
a_dates  = pipeline["anomaly_dates"]

if z_threshold != 2.0 or rolling_window != 7:
    anomalies = detect_anomalies(df, threshold=z_threshold, window=rolling_window)
    ann_df    = annotate_dataframe(df, anomalies)
    a_dates   = get_anomaly_dates(anomalies)

prophet_anomaly_df = pd.DataFrame()
if detector == "Prophet":
    if not check_access("prophet_detection", tier):
        gate("prophet_detection")
    else:
        with st.spinner("Fitting Prophet models…"):
            try:
                from src.prophet_anomaly_detection import detect_all_metrics as prophet_detect
                prophet_anomaly_df = prophet_detect(df, interval_width=PROPHET_INTERVAL_WIDTH)
                prophet_only = prophet_anomaly_df[prophet_anomaly_df["is_anomaly"]]
                if not prophet_only.empty:
                    anomalies = prophet_only[["date","metric","observed_value","expected_value","deviation"]].rename(columns={"deviation":"deviation_score"})
                    anomalies["direction"] = prophet_only["direction"].values
                    a_dates = sorted(anomalies["date"].unique().tolist())
            except ImportError:
                st.warning("Prophet not installed — falling back to Z-score.")

# ── KPI header ────────────────────────────────────────────────────────────────
st.markdown(
    '<h1 style="font-size:1.6rem;font-weight:700;color:#e2e8f0;letter-spacing:-.5px;margin-bottom:2px;">'
    'Root Cause Analysis</h1>'
    f'<p style="font-size:.82rem;color:#3a4a6b;letter-spacing:1px;">'
    f'Statistical anomaly detection · {date_range_option} · {detector} detector</p>',
    unsafe_allow_html=True,
)
st.divider()

k1,k2,k3,k4,k5 = st.columns(5)
k1.metric("Total Revenue",    f"${df['revenue'].sum():,.0f}")
k2.metric("Avg Daily Traffic", f"{df['traffic'].mean():,.0f}")
k3.metric("Total Orders",     f"{df['orders'].sum():,.0f}")
k4.metric("Avg Conversion",   f"{df['conversion_rate'].mean():.2%}")
k5.metric("Anomalies Found",  str(len(anomalies)))
st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(
    ["TRENDS", "ANOMALIES", "SEGMENTS", "CORRELATIONS", "FORECAST", "RCA REPORT", "HISTORY"]
)

# ── TRENDS ────────────────────────────────────────────────────────────────────
with tab1:
    st.markdown("#### Metric Time Series")
    metric_choice = st.selectbox("Metric", ANOMALY_METRICS, format_func=lambda x: x.replace("_"," ").upper(), key="trend_m")
    normal_pts = ann_df[~ann_df["is_anomaly"]]
    anom_pts   = ann_df[ann_df["is_anomaly"]]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=normal_pts["date"], y=normal_pts[metric_choice], mode="lines", name="Normal", line=dict(color=C_CYAN, width=1.8)))
    if not anom_pts.empty:
        fig.add_trace(go.Scatter(x=anom_pts["date"], y=anom_pts[metric_choice], mode="markers", name="Anomaly",
                                 marker=dict(color=C_RED, size=9, symbol="circle-open", line=dict(width=2, color=C_RED))))
    if detector == "Prophet" and not prophet_anomaly_df.empty:
        pm = prophet_anomaly_df[prophet_anomaly_df["metric"] == metric_choice]
        if not pm.empty:
            fig.add_trace(go.Scatter(x=pd.concat([pm["date"], pm["date"][::-1]]),
                                     y=pd.concat([pm["upper_bound"], pm["lower_bound"][::-1]]),
                                     fill="toself", fillcolor="rgba(0,229,255,0.08)", line=dict(color="rgba(0,0,0,0)"), name="Confidence band"))
            fig.add_trace(go.Scatter(x=pm["date"], y=pm["expected_value"], mode="lines", line=dict(color=C_PURPLE, width=1, dash="dot"), name="Prophet forecast"))
    fig.update_layout(legend=dict(orientation="h", y=1.08), **_bl())
    st.plotly_chart(fig, use_container_width=True)

# ── ANOMALIES ─────────────────────────────────────────────────────────────────
with tab2:
    st.markdown("#### Detected Anomalies")
    if anomalies.empty:
        st.success("No anomalies detected at the current threshold.")
    else:
        score_col = "deviation_score" if "deviation_score" in anomalies.columns else "deviation"
        fig_a = px.scatter(anomalies, x="date", y=score_col, color="metric", symbol="direction",
                           size=score_col, size_max=18, color_discrete_sequence=[C_CYAN, C_PURPLE, C_RED], template=_THEME)
        fig_a.update_layout(paper_bgcolor=_PAPER, plot_bgcolor=_PLOT, font=dict(family="Space Grotesk", color="#8892b0", size=11), margin=dict(l=40,r=20,t=50,b=40))
        st.plotly_chart(fig_a, use_container_width=True)
        display_a = anomalies.copy()
        display_a["date"] = pd.to_datetime(display_a["date"]).dt.strftime("%Y-%m-%d")
        st.dataframe(display_a, use_container_width=True)

# ── SEGMENTS ──────────────────────────────────────────────────────────────────
with tab3:
    st.markdown("#### Segment Attribution")
    if not a_dates:
        st.warning("No anomalies — segment analysis requires at least one anomaly date.")
    else:
        c1, c2 = st.columns(2)
        seg_date   = c1.selectbox("Date", a_dates, format_func=lambda d: str(d)[:10], key="sd")
        seg_metric = c2.selectbox("Metric", ANOMALY_METRICS, format_func=lambda x: x.replace("_"," ").upper(), key="sm")
        seg_results = analyse_all_segments(df, seg_date, seg_metric)
        for dim, seg_df in seg_results.items():
            if seg_df.empty: continue
            fig_s = px.bar(seg_df, x=dim, y="relative_change_pct", color="relative_change_pct",
                           color_continuous_scale=[C_RED, C_AMBER, C_GREEN], template=_THEME)
            fig_s.update_layout(title=dict(text=dim.replace("_"," ").upper(), font=dict(size=11,color="#3a4a6b")),
                                 coloraxis_showscale=False, paper_bgcolor=_PAPER, plot_bgcolor=_PLOT,
                                 font=dict(family="Space Grotesk",color="#8892b0",size=11), margin=dict(l=40,r=20,t=50,b=40))
            st.plotly_chart(fig_s, use_container_width=True)

# ── CORRELATIONS ──────────────────────────────────────────────────────────────
with tab4:
    st.markdown("#### Metric Correlations")
    left, right = st.columns(2)
    with left:
        if not corr_df.empty:
            pairs = [f"{r['metric_a']} / {r['metric_b']}" for _,r in corr_df.iterrows()]
            fig_b = px.bar(corr_df, x=pairs, y="pearson_r", color="pearson_r",
                           color_continuous_scale="RdYlGn", range_color=[-1,1], template=_THEME)
            fig_b.update_layout(paper_bgcolor=_PAPER,plot_bgcolor=_PLOT,font=dict(family="Space Grotesk",color="#8892b0",size=11),margin=dict(l=40,r=20,t=50,b=40))
            st.plotly_chart(fig_b, use_container_width=True)
            st.dataframe(corr_df, use_container_width=True)
    with right:
        fig_h = px.imshow(corr_mat, text_auto=".2f", color_continuous_scale="RdBu_r", zmin=-1, zmax=1, template=_THEME)
        fig_h.update_layout(paper_bgcolor=_PAPER, font=dict(family="Space Grotesk",color="#8892b0",size=11), margin=dict(l=40,r=20,t=50,b=40))
        st.plotly_chart(fig_h, use_container_width=True)

# ── FORECAST ──────────────────────────────────────────────────────────────────
with tab5:
    st.markdown("#### Prophet Forecast")
    if not gate("forecast"):
        pass
    else:
        fc_metric = st.selectbox("Metric to forecast", ANOMALY_METRICS, format_func=lambda x: x.replace("_"," ").upper(), key="fc_m")
        if st.button("Generate Forecast", key="fc_btn"):
            with st.spinner("Fitting Prophet model…"):
                try:
                    from src.prophet_anomaly_detection import forecast_future
                    fc_df = forecast_future(df, fc_metric, periods=forecast_days, interval_width=PROPHET_INTERVAL_WIDTH)
                    hist_end   = df["date"].max()
                    historical = fc_df[fc_df["ds"] <= hist_end]
                    future_fc  = fc_df[fc_df["ds"] > hist_end]
                    fig_fc = go.Figure()
                    fig_fc.add_trace(go.Scatter(x=df["date"], y=df[fc_metric], mode="lines", name="Historical", line=dict(color=C_CYAN, width=1.8)))
                    fig_fc.add_trace(go.Scatter(x=historical["ds"], y=historical["yhat"], mode="lines", name="Model fit", line=dict(color=C_PURPLE, width=1, dash="dot")))
                    if not future_fc.empty:
                        fig_fc.add_trace(go.Scatter(x=pd.concat([future_fc["ds"],future_fc["ds"][::-1]]),
                                                    y=pd.concat([future_fc["yhat_upper"],future_fc["yhat_lower"][::-1]]),
                                                    fill="toself", fillcolor="rgba(123,104,238,0.12)", line=dict(color="rgba(0,0,0,0)"), name="95% CI"))
                        fig_fc.add_trace(go.Scatter(x=future_fc["ds"], y=future_fc["yhat"], mode="lines", name="Forecast", line=dict(color=C_AMBER, width=2, dash="dash")))
                    fig_fc.update_layout(legend=dict(orientation="h",y=1.08), **_bl())
                    st.plotly_chart(fig_fc, use_container_width=True)
                except ImportError:
                    st.error("Prophet not installed. Run: pip install prophet")
                except Exception as exc:
                    st.error(f"Forecast failed: {exc}")
        else:
            st.info("Select a metric and click Generate Forecast.")

# ── RCA REPORT ─────────────────────────────────────────────────────────────────
with tab6:
    st.markdown("#### Automated Root Cause Analysis")
    if not a_dates:
        st.warning("No anomalies detected. Lower the Z-score threshold in the sidebar.")
    else:
        report_date = st.selectbox("Anomaly date", a_dates, format_func=lambda d: str(d)[:10], key="rd")
        if st.button("RUN ANALYSIS", key="run_rca"):
            with st.spinner("Analysing…"):
                seg_r       = analyse_all_segments(df, report_date, "revenue")
                contrib_df  = compute_contributions(df, report_date)
                hyps        = generate_hypotheses(contrib_df, seg_r, corr_df)
                anom_day    = anomalies[anomalies["date"] == report_date]
                report_dict = build_report(anom_day, corr_df, seg_r, contrib_df, hyps, report_date)

                # LLM summary (tier-gated internally — falls back to rule-based)
                user_profile = user.get("profile", {})
                import os
                if check_access("llm_summary", tier):
                    os.environ["LLM_API_KEY"] = user_profile.get("llm_api_key", "")
                    os.environ["LLM_BACKEND"]  = user_profile.get("llm_backend", "gemini")
                exec_summary = generate_executive_summary(report_dict)
                report_md    = report_to_markdown(report_dict)

            # Persist to Supabase
            top_hyp = hyps[0].title if hyps else ""
            top_conf = hyps[0].confidence if hyps else 0.0
            if is_logged_in:
                save_report_meta(
                    user_id=uid,
                    dataset_id=st.session_state.get("active_dataset_id"),
                    anomaly_date=str(report_date)[:10],
                    primary_metric="revenue",
                    executive_summary=exec_summary,
                    n_anomalies=len(anom_day),
                    n_hypotheses=len(hyps),
                    top_hypothesis=top_hyp,
                    confidence=top_conf,
                    report_md=report_md,
                )

            # Auto-index into RAG
            try:
                from src.rag_indexer import index_report as _idx
                _idx(report_dict, executive_summary=exec_summary)
            except Exception:
                pass

            # Display
            st.markdown("**Executive Summary**")
            st.markdown(f'<div style="background:#0d1327;border:1px solid #1e2d52;border-radius:8px;padding:1.2rem;font-size:.9rem;line-height:1.7;color:#c9d1e3;">{exec_summary}</div>', unsafe_allow_html=True)
            st.divider()
            st.markdown("**Root Cause Hypotheses**")
            hyp_df = hypotheses_to_dataframe(hyps)
            if not hyp_df.empty:
                st.dataframe(hyp_df, use_container_width=True)
            if not contrib_df.empty:
                st.markdown("**Factor Contribution**")
                fig_p = px.pie(contrib_df, names="factor", values="contribution_pct", hole=0.5,
                               color_discrete_sequence=[C_CYAN,C_PURPLE,C_AMBER,C_GREEN], template=_THEME)
                fig_p.update_layout(paper_bgcolor=_PAPER, font=dict(family="Space Grotesk",color="#8892b0",size=11), margin=dict(l=20,r=20,t=50,b=20))
                st.plotly_chart(fig_p, use_container_width=True)
            st.markdown("**Recommended Actions**")
            for i, action in enumerate(report_dict.get("recommended_actions", []), 1):
                st.markdown(f'<p style="color:#4a6fa5;font-size:.85rem;"><span style="color:#00e5ff;font-family:JetBrains Mono;">{i:02d}</span>&nbsp;&nbsp;{action}</p>', unsafe_allow_html=True)
            st.divider()
            with st.expander("Full Markdown Report"):
                st.markdown(report_md)
            dl1, dl2 = st.columns(2)
            if not is_logged_in:
                st.info("🔒 Sign up for a free account to download RCA reports.")
                dl1.button("DOWNLOAD MARKDOWN", disabled=True)
                dl2.button("DOWNLOAD PDF", disabled=True)
            else:
                dl1.download_button("DOWNLOAD MARKDOWN", data=report_md, file_name=f"rca_{str(report_date)[:10]}.md", mime="text/markdown", key="dl_md")
                with dl2:
                    if gate("pdf_export"):
                        try:
                            from src.report_export import export_report_pdf
                            pdf_bytes = export_report_pdf(report_dict, executive_summary=exec_summary)
                            st.download_button("DOWNLOAD PDF", data=pdf_bytes, file_name=f"rca_{str(report_date)[:10]}.pdf", mime="application/pdf", key="dl_pdf")
                        except ImportError:
                            st.caption("Install reportlab: pip install reportlab")

# ── HISTORY (RAG) ─────────────────────────────────────────────────────────────
with tab7:
    st.markdown("#### Historical RCA Query")
    if not gate("rag_history"):
        pass
    else:
        try:
            from src.rag_indexer import _import_deps; _import_deps()
            from src.rag_query import query as rag_query, get_index_stats
            from src.rag_indexer import list_indexed_reports, clear_index
            rag_available = True
        except Exception:
            rag_available = False

        if not rag_available:
            st.error("RAG dependencies not installed.\n```\npip install chromadb sentence-transformers\n```")
        else:
            stats = get_index_stats()
            n_docs = stats["total_documents"]
            s1, s2, s3 = st.columns(3)
            s1.metric("Reports Indexed", n_docs)
            s2.metric("Index Location", "data/rag_index")
            s3.metric("Embed Model", "all-MiniLM-L6-v2")
            st.divider()
            if n_docs == 0:
                st.info("Knowledge base is empty. Run an RCA analysis first — it will be indexed automatically.")
            else:
                if "rag_messages" not in st.session_state:
                    st.session_state["rag_messages"] = []
                for msg in st.session_state["rag_messages"]:
                    role_color = "#00e5ff" if msg["role"] == "user" else "#7b68ee"
                    role_label = "YOU" if msg["role"] == "user" else "METRICSLEUTH"
                    st.markdown(f'<div style="margin-bottom:.8rem;"><span style="font-family:JetBrains Mono;font-size:.65rem;color:{role_color};letter-spacing:2px;">{role_label}</span><div style="background:#0d1327;border:1px solid #1e2d52;border-radius:8px;padding:.9rem;margin-top:.25rem;font-size:.87rem;line-height:1.65;color:#c9d1e3;">{msg["content"]}</div></div>', unsafe_allow_html=True)
                question = st.chat_input("Ask about past anomalies…")
                if question:
                    st.session_state["rag_messages"].append({"role": "user", "content": question})
                    with st.spinner("Searching knowledge base…"):
                        result = rag_query(question)
                    st.session_state["rag_messages"].append({"role": "assistant", "content": result.answer, "sources": result.sources})
                    st.rerun()
                if st.session_state["rag_messages"]:
                    if st.button("Clear conversation", key="clear_chat"):
                        st.session_state["rag_messages"] = []
                        st.rerun()
