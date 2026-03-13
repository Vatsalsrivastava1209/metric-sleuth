"""
streamlit_app.py
================
MetricSleuth – AI-powered Root Cause Analysis Dashboard.

Run with:
    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

# ── Path setup so src/ and utils/ are importable ──────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.data_loader import load_data, load_data_from_upload
from src.anomaly_detection import detect_anomalies, annotate_dataframe, get_anomaly_dates
from src.segmentation_analysis import analyse_all_segments
from src.correlation_analysis import analyse_correlations, build_correlation_matrix
from src.contribution_analysis import compute_contributions
from src.hypothesis_engine import generate_hypotheses, hypotheses_to_dataframe
from src.report_generator import build_report, report_to_markdown
from utils.config import ANOMALY_METRICS

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MetricSleuth | RCA Engine",
    page_icon="M",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

    html, body, [class*="css"], .stApp {
        font-family: 'Space Grotesk', sans-serif;
    }

    /* ── Background ── */
    .stApp {
        background: #060912;
        color: #c9d1e3;
    }

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {
        background: #0b0f1e;
        border-right: 1px solid #1a2040;
    }
    [data-testid="stSidebar"] * {
        color: #8892b0 !important;
    }

    /* ── Top wordmark ── */
    .wordmark {
        font-family: 'Space Grotesk', sans-serif;
        font-size: 1.8rem;
        font-weight: 700;
        letter-spacing: -0.5px;
        background: linear-gradient(90deg, #00e5ff, #7b68ee);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    .wordmark-sub {
        font-size: 0.78rem;
        color: #3a4a6b;
        letter-spacing: 2px;
        text-transform: uppercase;
        font-family: 'JetBrains Mono', monospace;
    }

    /* ── KPI cards ── */
    [data-testid="metric-container"] {
        background: #0d1327;
        border: 1px solid #1e2d52;
        border-radius: 10px;
        padding: 14px 18px;
    }
    [data-testid="metric-container"] label {
        color: #3f5185 !important;
        font-size: 0.72rem;
        letter-spacing: 1.5px;
        text-transform: uppercase;
    }
    [data-testid="metric-container"] [data-testid="stMetricValue"] {
        color: #e2e8f0 !important;
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.5rem;
    }

    /* ── Section labels ── */
    .section-label {
        font-size: 0.68rem;
        letter-spacing: 2.5px;
        text-transform: uppercase;
        color: #2d4070;
        margin-bottom: 0.25rem;
    }

    /* ── Divider override ── */
    hr {
        border-color: #111928 !important;
        margin: 1rem 0 !important;
    }

    /* ── Tables ── */
    .stDataFrame { border: 1px solid #1a2540; border-radius: 8px; }

    /* ── Tabs ── */
    button[role="tab"] {
        font-size: 0.78rem;
        letter-spacing: 1.5px;
        text-transform: uppercase;
        color: #3a4a6b !important;
    }
    button[role="tab"][aria-selected="true"] {
        color: #00e5ff !important;
        border-bottom: 2px solid #00e5ff;
    }

    /* ── Primary button ── */
    .stButton > button {
        background: #00e5ff;
        color: #060912;
        border: none;
        border-radius: 6px;
        font-weight: 700;
        font-size: 0.78rem;
        letter-spacing: 1.5px;
        text-transform: uppercase;
        padding: 0.55rem 1.8rem;
        transition: opacity 0.15s;
    }
    .stButton > button:hover { opacity: 0.8; }

    /* ── Selectbox / sliders ── */
    [data-testid="stSelectbox"] label,
    [data-testid="stSlider"] label { color: #3f5185 !important; }

    /* ── Expander ── */
    .streamlit-expanderHeader {
        background: #0d1327 !important;
        border: 1px solid #1a2040 !important;
        border-radius: 6px !important;
        color: #4a6fa5 !important;
        font-size: 0.78rem;
    }

    /* ── Hypothesis badge ── */
    .hyp-high { color: #00e5ff; }
    .hyp-mid  { color: #7b68ee; }
    .hyp-low  { color: #3a4a6b; }

    /* Scrollbar */
    ::-webkit-scrollbar { width: 4px; }
    ::-webkit-scrollbar-track { background: #060912; }
    ::-webkit-scrollbar-thumb { background: #1a2540; border-radius: 4px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Plotly theme ──────────────────────────────────────────────────────────────
_THEME = "plotly_dark"
_PAPER = "rgba(0,0,0,0)"
_PLOT  = "rgba(255,255,255,0.015)"
_GRID  = "rgba(255,255,255,0.04)"
_COLOR_CYAN   = "#00e5ff"
_COLOR_PURPLE = "#7b68ee"
_COLOR_RED    = "#ff4d6d"
_COLOR_AMBER  = "#ffb703"
_COLOR_GREEN  = "#06d6a0"

def _base_layout(**extra) -> dict:
    return dict(
        template=_THEME,
        paper_bgcolor=_PAPER,
        plot_bgcolor=_PLOT,
        font=dict(family="Space Grotesk", color="#8892b0", size=11),
        xaxis=dict(gridcolor=_GRID, zeroline=False),
        yaxis=dict(gridcolor=_GRID, zeroline=False),
        margin=dict(l=40, r=20, t=50, b=40),
        **extra,
    )


# ── Cached pipeline ───────────────────────────────────────────────────────────
@st.cache_data
def _run_pipeline(df_json: str) -> dict:
    """Run and cache the full RCA pipeline."""
    df = pd.read_json(io.StringIO(df_json), orient="split")   # <-- fix for FutureWarning
    df["date"] = pd.to_datetime(df["date"])

    anomalies_df  = detect_anomalies(df)
    annotated_df  = annotate_dataframe(df, anomalies_df)
    correlations_df = analyse_correlations(df)
    corr_matrix   = build_correlation_matrix(df, ["revenue", "traffic", "orders", "conversion_rate"])
    dates         = get_anomaly_dates(anomalies_df)

    return {
        "df":             df,
        "annotated_df":   annotated_df,
        "anomalies_df":   anomalies_df,
        "correlations_df": correlations_df,
        "corr_matrix":    corr_matrix,
        "anomaly_dates":  dates,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<div class="wordmark">MetricSleuth</div>'
        '<div class="wordmark-sub">Root Cause Analysis Engine</div>',
        unsafe_allow_html=True,
    )
    st.divider()

    st.markdown('<p class="section-label">Data Source</p>', unsafe_allow_html=True)
    data_source = st.radio(
        "data_source",
        ["Sample dataset", "Upload CSV"],
        label_visibility="collapsed",
    )

    uploaded_file = None
    if data_source == "Upload CSV":
        uploaded_file = st.file_uploader(
            "CSV file",
            type=["csv"],
            help="Required columns: date, revenue, traffic, orders, conversion_rate, region, device, traffic_source",
            label_visibility="collapsed",
        )

    st.divider()
    st.markdown('<p class="section-label">Detection Parameters</p>', unsafe_allow_html=True)
    z_threshold    = st.slider("Z-score threshold", 1.0, 4.0, 2.0, 0.25)
    rolling_window = st.slider("Rolling window (days)", 3, 21, 7)

    st.divider()
    st.markdown(
        '<p style="font-size:0.68rem;color:#1e2d52;letter-spacing:1px;">'
        'MetricSleuth v1.0 — Statistical RCA</p>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    '<h1 style="font-size:1.6rem;font-weight:700;color:#e2e8f0;letter-spacing:-0.5px;margin-bottom:2px;">'
    'Root Cause Analysis</h1>'
    '<p style="font-size:0.82rem;color:#3a4a6b;letter-spacing:1px;">Statistical anomaly detection and causal attribution for business metrics</p>',
    unsafe_allow_html=True,
)
st.divider()


# ─────────────────────────────────────────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────────────────────────────────────────
try:
    if data_source == "Upload CSV" and uploaded_file is not None:
        df_raw = load_data_from_upload(uploaded_file)
        st.success(f"Dataset loaded — {len(df_raw):,} rows")
    else:
        df_raw = load_data(ROOT / "data" / "sample_ecommerce.csv")
        st.info(f"Sample dataset — {len(df_raw):,} rows")
except (FileNotFoundError, ValueError) as exc:
    st.error(str(exc))
    st.stop()

with st.spinner("Running pipeline..."):
    cache_key = df_raw.to_json(orient="split", date_format="iso")
    pipeline  = _run_pipeline(cache_key)

df       = pipeline["df"]
ann_df   = pipeline["annotated_df"]
anomalies = pipeline["anomalies_df"]
corr_df  = pipeline["correlations_df"]
corr_mat = pipeline["corr_matrix"]
a_dates  = pipeline["anomaly_dates"]

if z_threshold != 2.0 or rolling_window != 7:
    anomalies = detect_anomalies(df, threshold=z_threshold, window=rolling_window)
    ann_df    = annotate_dataframe(df, anomalies)
    a_dates   = get_anomaly_dates(anomalies)


# ─────────────────────────────────────────────────────────────────────────────
# KPI BAR
# ─────────────────────────────────────────────────────────────────────────────
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total Revenue",   f"${df['revenue'].sum():,.0f}")
k2.metric("Avg Daily Traffic", f"{df['traffic'].mean():,.0f}")
k3.metric("Total Orders",    f"{df['orders'].sum():,.0f}")
k4.metric("Avg Conversion",  f"{df['conversion_rate'].mean():.2%}")
k5.metric("Anomalies Found", str(len(anomalies)))
st.divider()


# ─────────────────────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "TRENDS", "ANOMALIES", "SEGMENTS", "CORRELATIONS", "RCA REPORT",
])


# ── TRENDS ───────────────────────────────────────────────────────────────────
with tab1:
    st.markdown("#### Metric Time Series")

    metric_choice = st.selectbox(
        "Metric",
        ANOMALY_METRICS,
        format_func=lambda x: x.replace("_", " ").upper(),
        key="trend_metric",
    )

    normal_pts = ann_df[~ann_df["is_anomaly"]]
    anom_pts   = ann_df[ann_df["is_anomaly"]]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=normal_pts["date"], y=normal_pts[metric_choice],
        mode="lines", name="Normal",
        line=dict(color=_COLOR_CYAN, width=1.8),
        hovertemplate="%{x|%Y-%m-%d}<br>%{y:,.4f}<extra></extra>",
    ))
    if not anom_pts.empty:
        fig.add_trace(go.Scatter(
            x=anom_pts["date"], y=anom_pts[metric_choice],
            mode="markers", name="Anomaly",
            marker=dict(color=_COLOR_RED, size=9, symbol="circle-open",
                        line=dict(width=2, color=_COLOR_RED)),
            hovertemplate="ANOMALY — %{x|%Y-%m-%d}<br>%{y:,.4f}<extra></extra>",
        ))

    fig.update_layout(
        title=dict(text=metric_choice.replace("_", " ").upper(), font=dict(size=11, color="#3a4a6b")),
        legend=dict(orientation="h", y=1.08),
        **_base_layout(),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Normalised multi-metric overlay
    with st.expander("Normalised multi-metric overlay"):
        fig2 = go.Figure()
        palette = [_COLOR_CYAN, _COLOR_PURPLE, _COLOR_AMBER, _COLOR_GREEN]
        for metric, color in zip(ANOMALY_METRICS, palette):
            s = df[metric]
            norm = (s - s.min()) / ((s.max() - s.min()) + 1e-10)
            fig2.add_trace(go.Scatter(
                x=df["date"], y=norm,
                mode="lines",
                name=metric.replace("_", " ").upper(),
                line=dict(color=color, width=1.5),
            ))
        fig2.update_layout(
            title=dict(text="ALL METRICS — NORMALISED [0,1]", font=dict(size=11, color="#3a4a6b")),
            **_base_layout(),
        )
        st.plotly_chart(fig2, use_container_width=True)


# ── ANOMALIES ─────────────────────────────────────────────────────────────────
with tab2:
    st.markdown("#### Detected Anomalies")

    if anomalies.empty:
        st.success("No anomalies detected at the current threshold.")
    else:
        st.caption(
            f"{len(anomalies)} records  /  "
            f"{anomalies['metric'].nunique()} metric(s)  /  "
            f"{anomalies['date'].nunique()} date(s)"
        )

        fig_anom = px.scatter(
            anomalies,
            x="date", y="deviation_score",
            color="metric", symbol="direction",
            size="deviation_score", size_max=18,
            hover_data=["observed_value", "expected_value", "z_score"],
            labels={"deviation_score": "|Z-score|", "date": "Date"},
            color_discrete_sequence=[_COLOR_CYAN, _COLOR_PURPLE, _COLOR_RED],
            template=_THEME,
        )
        fig_anom.update_layout(
            title=dict(text="DEVIATION SCORES BY DATE", font=dict(size=11, color="#3a4a6b")),
            paper_bgcolor=_PAPER, plot_bgcolor=_PLOT,
            font=dict(family="Space Grotesk", color="#8892b0", size=11),
            margin=dict(l=40, r=20, t=50, b=40),
        )
        st.plotly_chart(fig_anom, use_container_width=True)

        display_anom = anomalies.copy()
        display_anom["date"] = display_anom["date"].dt.strftime("%Y-%m-%d")
        st.dataframe(display_anom, use_container_width=True)


# ── SEGMENTS ──────────────────────────────────────────────────────────────────
with tab3:
    st.markdown("#### Segment Attribution")

    if not a_dates:
        st.warning("No anomalies detected. Segment analysis requires at least one anomaly date.")
    else:
        c1, c2 = st.columns(2)
        seg_date = c1.selectbox(
            "Anomaly date",
            a_dates,
            format_func=lambda d: str(d)[:10],
            key="seg_date",
        )
        seg_metric = c2.selectbox(
            "Metric",
            ANOMALY_METRICS,
            format_func=lambda x: x.replace("_", " ").upper(),
            key="seg_metric",
        )

        seg_results = analyse_all_segments(df, seg_date, seg_metric)

        for dim, seg_df in seg_results.items():
            if seg_df.empty:
                continue
            fig_seg = px.bar(
                seg_df,
                x=dim, y="relative_change_pct",
                color="relative_change_pct",
                color_continuous_scale=["#ff4d6d", "#ffb703", "#06d6a0"],
                labels={"relative_change_pct": "Change vs Baseline (%)"},
                template=_THEME,
            )
            fig_seg.update_layout(
                title=dict(text=dim.replace("_", " ").upper(), font=dict(size=11, color="#3a4a6b")),
                coloraxis_showscale=False,
                paper_bgcolor=_PAPER, plot_bgcolor=_PLOT,
                font=dict(family="Space Grotesk", color="#8892b0", size=11),
                margin=dict(l=40, r=20, t=50, b=40),
            )
            st.plotly_chart(fig_seg, use_container_width=True)


# ── CORRELATIONS ──────────────────────────────────────────────────────────────
with tab4:
    st.markdown("#### Metric Correlations")

    left, right = st.columns(2)

    with left:
        if not corr_df.empty:
            pairs = [f"{r['metric_a']} / {r['metric_b']}" for _, r in corr_df.iterrows()]
            fig_bar = px.bar(
                corr_df, x=pairs, y="pearson_r",
                color="pearson_r",
                color_continuous_scale="RdYlGn",
                range_color=[-1, 1],
                labels={"x": "Pair", "pearson_r": "Pearson r"},
                template=_THEME,
            )
            fig_bar.update_layout(
                title=dict(text="PEARSON COEFFICIENTS", font=dict(size=11, color="#3a4a6b")),
                paper_bgcolor=_PAPER, plot_bgcolor=_PLOT,
                font=dict(family="Space Grotesk", color="#8892b0", size=11),
                margin=dict(l=40, r=20, t=50, b=40),
            )
            st.plotly_chart(fig_bar, use_container_width=True)
            st.dataframe(corr_df, use_container_width=True)

    with right:
        fig_heat = px.imshow(
            corr_mat,
            text_auto=".2f",
            color_continuous_scale="RdBu_r",
            zmin=-1, zmax=1,
            template=_THEME,
        )
        fig_heat.update_layout(
            title=dict(text="CORRELATION MATRIX", font=dict(size=11, color="#3a4a6b")),
            paper_bgcolor=_PAPER,
            font=dict(family="Space Grotesk", color="#8892b0", size=11),
            margin=dict(l=40, r=20, t=50, b=40),
        )
        st.plotly_chart(fig_heat, use_container_width=True)


# ── RCA REPORT ────────────────────────────────────────────────────────────────
with tab5:
    st.markdown("#### Automated Root Cause Analysis")

    if not a_dates:
        st.warning("No anomalies detected. Lower the Z-score threshold in the sidebar.")
    else:
        report_date = st.selectbox(
            "Anomaly date",
            a_dates,
            format_func=lambda d: str(d)[:10],
            key="report_date",
        )

        if st.button("RUN ANALYSIS", key="run_rca"):
            with st.spinner("Analysing..."):
                seg_r       = analyse_all_segments(df, report_date, "revenue")
                contrib_df  = compute_contributions(df, report_date)
                hyps        = generate_hypotheses(contrib_df, seg_r, corr_df)
                anom_day    = anomalies[anomalies["date"] == report_date]
                report_dict = build_report(anom_day, corr_df, seg_r, contrib_df, hyps, report_date)
                report_md   = report_to_markdown(report_dict)

            # Hypotheses table
            st.markdown("**Root Cause Hypotheses**")
            hyp_df = hypotheses_to_dataframe(hyps)
            if not hyp_df.empty:
                st.dataframe(hyp_df, use_container_width=True)
            else:
                st.info("No hypotheses generated for this date.")

            # Contribution donut
            if not contrib_df.empty:
                st.markdown("**Factor Contribution**")
                fig_pie = px.pie(
                    contrib_df,
                    names="factor", values="contribution_pct",
                    hole=0.5,
                    color_discrete_sequence=[_COLOR_CYAN, _COLOR_PURPLE, _COLOR_AMBER, _COLOR_GREEN],
                    template=_THEME,
                )
                fig_pie.update_traces(textfont=dict(family="JetBrains Mono"))
                fig_pie.update_layout(
                    title=dict(text="WHAT CAUSED THE DROP?", font=dict(size=11, color="#3a4a6b")),
                    paper_bgcolor=_PAPER,
                    font=dict(family="Space Grotesk", color="#8892b0", size=11),
                    margin=dict(l=20, r=20, t=50, b=20),
                )
                st.plotly_chart(fig_pie, use_container_width=True)

            # Recommended actions
            st.markdown("**Recommended Actions**")
            for i, action in enumerate(report_dict.get("recommended_actions", []), 1):
                st.markdown(
                    f'<p style="color:#4a6fa5;font-size:0.85rem;">'
                    f'<span style="color:#00e5ff;font-family:JetBrains Mono;">{i:02d}</span>&nbsp;&nbsp;{action}</p>',
                    unsafe_allow_html=True,
                )

            st.divider()
            with st.expander("Full report"):
                st.markdown(report_md)

            st.download_button(
                label="DOWNLOAD REPORT",
                data=report_md,
                file_name=f"rca_{str(report_date)[:10]}.md",
                mime="text/markdown",
                key="download_report",
            )
