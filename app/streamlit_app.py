"""
streamlit_app.py
================
MetricSleuth – AI-powered Root Cause Analysis Dashboard.

Run with:
    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

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
from utils.config import ANOMALY_METRICS, SEGMENT_COLUMNS, CORRELATION_PAIRS

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MetricSleuth | RCA Engine",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* Dark gradient background */
    .stApp {
        background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
        color: #e8eaf6;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: rgba(255,255,255,0.04);
        border-right: 1px solid rgba(255,255,255,0.08);
    }

    /* Metric cards */
    [data-testid="metric-container"] {
        background: rgba(255,255,255,0.06);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 12px;
        padding: 16px;
        backdrop-filter: blur(10px);
    }

    /* Cards / expanders */
    .stExpander {
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 12px;
    }

    /* Buttons */
    .stButton > button {
        background: linear-gradient(90deg, #667eea, #764ba2);
        color: white;
        border: none;
        border-radius: 8px;
        font-weight: 600;
        padding: 0.5rem 1.5rem;
        transition: opacity 0.2s;
    }
    .stButton > button:hover { opacity: 0.85; }

    /* Section header */
    .section-header {
        font-size: 1.15rem;
        font-weight: 600;
        color: #a78bfa;
        margin-bottom: 0.5rem;
    }

    /* Anomaly badge */
    .badge-drop {
        background: #ef4444;
        color: white;
        border-radius: 6px;
        padding: 2px 10px;
        font-size: 0.8rem;
    }
    .badge-spike {
        background: #22c55e;
        color: white;
        border-radius: 6px;
        padding: 2px 10px;
        font-size: 0.8rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

PLOTLY_THEME = "plotly_dark"
PLOTLY_PAPER_BG = "rgba(0,0,0,0)"
PLOTLY_PLOT_BG = "rgba(255,255,255,0.03)"


def _chart_defaults() -> dict:
    return dict(
        template=PLOTLY_THEME,
        paper_bgcolor=PLOTLY_PAPER_BG,
        plot_bgcolor=PLOTLY_PLOT_BG,
    )


@st.cache_data
def _run_pipeline(df_json: str) -> dict:
    """Cache the full RCA pipeline; keyed by the serialised DataFrame."""
    df = pd.read_json(df_json, orient="split")
    df["date"] = pd.to_datetime(df["date"])

    anomalies_df = detect_anomalies(df)
    annotated_df = annotate_dataframe(df, anomalies_df)
    correlations_df = analyse_correlations(df)
    corr_matrix = build_correlation_matrix(df, ["revenue", "traffic", "orders", "conversion_rate"])

    dates = get_anomaly_dates(anomalies_df)

    return {
        "df": df,
        "annotated_df": annotated_df,
        "anomalies_df": anomalies_df,
        "correlations_df": correlations_df,
        "corr_matrix": corr_matrix,
        "anomaly_dates": dates,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🔍 MetricSleuth")
    st.markdown("*AI-Powered Root Cause Analysis*")
    st.divider()

    st.markdown("### 📂 Data Source")
    data_source = st.radio(
        "Choose input",
        ["Use sample dataset", "Upload your own CSV"],
        label_visibility="collapsed",
    )

    uploaded_file = None
    if data_source == "Upload your own CSV":
        uploaded_file = st.file_uploader(
            "Upload CSV",
            type=["csv"],
            help="Must contain: date, revenue, traffic, orders, conversion_rate, region, device, traffic_source",
        )

    st.divider()
    st.markdown("### ⚙️ Detection Settings")
    z_threshold = st.slider("Z-score Threshold", 1.0, 4.0, 2.0, 0.25,
                             help="Higher = fewer, more extreme anomalies")
    rolling_window = st.slider("Rolling Window (days)", 3, 21, 7,
                                help="Window for baseline rolling stats")

    st.divider()
    st.markdown("### 📌 About")
    st.markdown(
        "MetricSleuth automatically detects metric anomalies and traces them "
        "back to their root causes using statistical analysis."
    )

# ─────────────────────────────────────────────────────────────────────────────
# Load data
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("# 🔍 MetricSleuth — Root Cause Analysis Engine")
st.markdown("Detect anomalies, investigate segments, and generate automated RCA reports.")
st.divider()

try:
    if data_source == "Upload your own CSV" and uploaded_file is not None:
        df_raw = load_data_from_upload(uploaded_file)
        st.success(f"✅ Uploaded dataset loaded — {len(df_raw)} rows")
    else:
        sample_path = ROOT / "data" / "sample_ecommerce.csv"
        df_raw = load_data(sample_path)
        st.info(f"📊 Using sample e-commerce dataset — {len(df_raw)} rows")

except (FileNotFoundError, ValueError) as exc:
    st.error(f"❌ {exc}")
    st.stop()

# Run full pipeline (cached)
with st.spinner("Running RCA pipeline…"):
    cache_key = df_raw.to_json(orient="split", date_format="iso")
    pipeline = _run_pipeline(cache_key)

df        = pipeline["df"]
ann_df    = pipeline["annotated_df"]
anomalies = pipeline["anomalies_df"]
corr_df   = pipeline["correlations_df"]
corr_mat  = pipeline["corr_matrix"]
a_dates   = pipeline["anomaly_dates"]

# Re-run anomaly detection with user-tuned thresholds if changed from defaults
if z_threshold != 2.0 or rolling_window != 7:
    anomalies = detect_anomalies(df, threshold=z_threshold, window=rolling_window)
    ann_df = annotate_dataframe(df, anomalies)
    a_dates = get_anomaly_dates(anomalies)

# ─────────────────────────────────────────────────────────────────────────────
# KPI Overview
# ─────────────────────────────────────────────────────────────────────────────

st.markdown('<p class="section-header">📈 Dataset Overview</p>', unsafe_allow_html=True)
kpi_cols = st.columns(5)
kpis = [
    ("Total Revenue", f"${df['revenue'].sum():,.0f}"),
    ("Avg Daily Traffic", f"{df['traffic'].mean():,.0f}"),
    ("Total Orders", f"{df['orders'].sum():,.0f}"),
    ("Avg Conversion", f"{df['conversion_rate'].mean():.2%}"),
    ("Anomalies Found", str(len(anomalies))),
]
for col, (label, value) in zip(kpi_cols, kpis):
    col.metric(label, value)

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# Tab layout
# ─────────────────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📉 Metric Trends",
    "🚨 Anomalies",
    "🗂️ Segments",
    "🔗 Correlations",
    "📋 RCA Report",
])

# ── Tab 1: Metric Trends ──────────────────────────────────────────────────────
with tab1:
    st.markdown("### Metric Trends Over Time")

    metric_choice = st.selectbox(
        "Select metric",
        ANOMALY_METRICS,
        format_func=lambda x: x.replace("_", " ").title(),
        key="trend_metric",
    )

    # Separate normal and anomaly points for styling
    normal = ann_df[~ann_df["is_anomaly"]]
    anom_points = ann_df[ann_df["is_anomaly"]]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=normal["date"], y=normal[metric_choice],
        mode="lines", name="Normal",
        line=dict(color="#818cf8", width=2),
        hovertemplate="%{x|%Y-%m-%d}<br>%{y:,.2f}<extra></extra>",
    ))
    if not anom_points.empty:
        fig.add_trace(go.Scatter(
            x=anom_points["date"], y=anom_points[metric_choice],
            mode="markers", name="Anomaly",
            marker=dict(color="#f43f5e", size=10, symbol="circle-open", line=dict(width=2)),
            hovertemplate="⚠️ %{x|%Y-%m-%d}<br>%{y:,.2f}<extra>Anomaly</extra>",
        ))

    fig.update_layout(
        title=f"{metric_choice.replace('_',' ').title()} — Daily Trend",
        xaxis_title="Date", yaxis_title=metric_choice,
        legend=dict(orientation="h"),
        **_chart_defaults(),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Multi-metric normalised comparison
    st.markdown("#### Normalised Metric Comparison")
    with st.expander("View all metrics normalised to [0, 1]"):
        fig2 = go.Figure()
        colors = ["#818cf8", "#34d399", "#f59e0b", "#f43f5e"]
        for metric, color in zip(ANOMALY_METRICS, colors):
            series = df[metric]
            mn, mx = series.min(), series.max()
            norm = (series - mn) / (mx - mn + 1e-10)
            fig2.add_trace(go.Scatter(
                x=df["date"], y=norm,
                mode="lines", name=metric.replace("_", " ").title(),
                line=dict(color=color, width=1.5),
            ))
        fig2.update_layout(
            title="All Metrics — Normalised", xaxis_title="Date", yaxis_title="Normalised value",
            **_chart_defaults(),
        )
        st.plotly_chart(fig2, use_container_width=True)

# ── Tab 2: Anomalies ──────────────────────────────────────────────────────────
with tab2:
    st.markdown("### 🚨 Detected Anomalies")

    if anomalies.empty:
        st.success("No anomalies detected with the current threshold settings.")
    else:
        st.markdown(
            f"Found **{len(anomalies)}** anomaly records across "
            f"**{anomalies['metric'].nunique()}** metric(s) on "
            f"**{anomalies['date'].nunique()}** date(s)."
        )

        # Anomaly scatter chart
        fig_anom = px.scatter(
            anomalies,
            x="date", y="deviation_score",
            color="metric", symbol="direction",
            size="deviation_score",
            hover_data=["observed_value", "expected_value", "z_score"],
            title="Anomaly Deviation Scores",
            labels={"deviation_score": "|Z-score|", "date": "Date"},
            template=PLOTLY_THEME,
        )
        fig_anom.update_layout(paper_bgcolor=PLOTLY_PAPER_BG, plot_bgcolor=PLOTLY_PLOT_BG)
        st.plotly_chart(fig_anom, use_container_width=True)

        # Table
        display_anom = anomalies.copy()
        display_anom["date"] = display_anom["date"].dt.strftime("%Y-%m-%d")
        st.dataframe(
            display_anom.style.background_gradient(
                subset=["deviation_score"], cmap="Reds"
            ),
            use_container_width=True,
        )

# ── Tab 3: Segments ───────────────────────────────────────────────────────────
with tab3:
    st.markdown("### 🗂️ Segment Analysis")

    if not a_dates:
        st.warning("No anomalies found — segment analysis requires at least one anomaly date.")
    else:
        seg_date = st.selectbox(
            "Select anomaly date to investigate",
            a_dates,
            format_func=lambda d: str(d)[:10],
            key="seg_date",
        )
        seg_metric = st.selectbox(
            "Metric",
            ANOMALY_METRICS,
            format_func=lambda x: x.replace("_", " ").title(),
            key="seg_metric",
        )

        seg_results = analyse_all_segments(df, seg_date, seg_metric)

        for dim, seg_df in seg_results.items():
            if seg_df.empty:
                continue
            st.markdown(f"#### {dim.replace('_', ' ').title()}")
            fig_seg = px.bar(
                seg_df,
                x=dim,
                y="relative_change_pct",
                color="relative_change_pct",
                color_continuous_scale=["#ef4444", "#f59e0b", "#22c55e"],
                title=f"{seg_metric.title()} Change by {dim.title()} (vs. 7-day baseline)",
                labels={"relative_change_pct": "% Change"},
                template=PLOTLY_THEME,
            )
            fig_seg.update_layout(
                paper_bgcolor=PLOTLY_PAPER_BG,
                plot_bgcolor=PLOTLY_PLOT_BG,
                coloraxis_showscale=False,
            )
            st.plotly_chart(fig_seg, use_container_width=True)

# ── Tab 4: Correlations ───────────────────────────────────────────────────────
with tab4:
    st.markdown("### 🔗 Correlation Analysis")

    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("#### Pairwise Correlations")
        if not corr_df.empty:
            fig_bar = px.bar(
                corr_df,
                x=[f"{r['metric_a']} ↔ {r['metric_b']}" for _, r in corr_df.iterrows()],
                y="pearson_r",
                color="pearson_r",
                color_continuous_scale="RdYlGn",
                range_color=[-1, 1],
                title="Pearson r Coefficients",
                labels={"x": "Metric Pair", "pearson_r": "r"},
                template=PLOTLY_THEME,
            )
            fig_bar.update_layout(paper_bgcolor=PLOTLY_PAPER_BG, plot_bgcolor=PLOTLY_PLOT_BG)
            st.plotly_chart(fig_bar, use_container_width=True)
            st.dataframe(corr_df, use_container_width=True)

    with col_right:
        st.markdown("#### Correlation Heatmap")
        fig_heat = px.imshow(
            corr_mat,
            text_auto=".2f",
            color_continuous_scale="RdBu_r",
            zmin=-1, zmax=1,
            title="Metric Correlation Matrix",
            template=PLOTLY_THEME,
        )
        fig_heat.update_layout(paper_bgcolor=PLOTLY_PAPER_BG)
        st.plotly_chart(fig_heat, use_container_width=True)

# ── Tab 5: RCA Report ─────────────────────────────────────────────────────────
with tab5:
    st.markdown("### 📋 Root Cause Analysis Report")

    if not a_dates:
        st.warning("No anomalies detected. Adjust the Z-score threshold in the sidebar.")
    else:
        report_date = st.selectbox(
            "Generate report for anomaly date",
            a_dates,
            format_func=lambda d: str(d)[:10],
            key="report_date",
        )

        if st.button("🚀 Run Full RCA Analysis", key="run_rca"):
            with st.spinner("Analysing root causes…"):
                seg_r = analyse_all_segments(df, report_date, "revenue")
                contrib_df = compute_contributions(df, report_date)
                hyps = generate_hypotheses(contrib_df, seg_r, corr_df)
                anomalies_for_date = anomalies[anomalies["date"] == report_date]
                report_dict = build_report(
                    anomalies_for_date, corr_df, seg_r, contrib_df, hyps, report_date
                )
                report_md = report_to_markdown(report_dict)

            # ── Hypotheses summary ────────────────────────────────────────
            st.markdown("#### 🔍 Root Cause Hypotheses")
            hyp_df = hypotheses_to_dataframe(hyps)
            if not hyp_df.empty:
                st.dataframe(hyp_df, use_container_width=True)
            else:
                st.info("No hypotheses generated for this date.")

            # ── Contribution donut chart ──────────────────────────────────
            if not contrib_df.empty:
                st.markdown("#### 📉 Contribution Breakdown")
                fig_pie = px.pie(
                    contrib_df,
                    names="factor",
                    values="contribution_pct",
                    title="What Caused the Drop?",
                    hole=0.4,
                    color_discrete_sequence=px.colors.qualitative.Pastel,
                    template=PLOTLY_THEME,
                )
                fig_pie.update_layout(paper_bgcolor=PLOTLY_PAPER_BG)
                st.plotly_chart(fig_pie, use_container_width=True)

            # ── Recommended actions ───────────────────────────────────────
            st.markdown("#### ✅ Recommended Actions")
            if report_dict.get("recommended_actions"):
                for i, action in enumerate(report_dict["recommended_actions"], 1):
                    st.markdown(f"{i}. {action}")
            else:
                st.info("No actions generated.")

            # ── Full Markdown report ──────────────────────────────────────
            st.divider()
            st.markdown("#### 📄 Full RCA Report")
            with st.expander("Expand full report", expanded=False):
                st.markdown(report_md)

            # Download button
            st.download_button(
                label="⬇️ Download RCA Report (.md)",
                data=report_md,
                file_name=f"rca_report_{str(report_date)[:10]}.md",
                mime="text/markdown",
                key="download_report",
            )
