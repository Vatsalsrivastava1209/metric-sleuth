"""
pages/1_🔗_Connect.py
======================
Data Source Connector page — lets users add CSV uploads or database
connections, map columns to the canonical schema, and save datasets.
"""

from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st
from src.auth import get_current_user, render_tier_badge
from src.billing import gate, get_max_datasets, check_access
from src.db import get_user_datasets, save_dataset_meta, delete_dataset, count_user_datasets
from src.schema_mapper import suggest_mapping, apply_mapping, validate_mapping, CANONICAL_FIELDS, REQUIRED_FIELDS
from src.connectors.csv_connector import CSVConnector

st.set_page_config(page_title="Connect | MetricSleuth", page_icon="🔗", layout="wide")

# ── Shared CSS ────────────────────────────────────────────────────────────────
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;600;700&family=JetBrains+Mono&display=swap');
html,body,[class*="css"],.stApp{font-family:'Space Grotesk',sans-serif;}
.stApp{background:#060912;color:#c9d1e3;}
[data-testid="stSidebar"]{background:#0b0f1e;border-right:1px solid #1a2040;}
.stButton>button{background:#00e5ff;color:#060912;border:none;border-radius:6px;font-weight:700;font-size:.78rem;letter-spacing:1.5px;text-transform:uppercase;padding:.55rem 1.8rem;}
</style>""", unsafe_allow_html=True)

user = get_current_user()
uid  = user["id"] if user else "anonymous"
tier = user["tier"] if user else "free"
is_logged_in = user is not None

with st.sidebar:
    st.markdown('<div style="font-size:1.2rem;font-weight:700;background:linear-gradient(90deg,#00e5ff,#7b68ee);-webkit-background-clip:text;-webkit-text-fill-color:transparent;">MetricSleuth</div>', unsafe_allow_html=True)
    render_tier_badge()
    st.divider()
    if st.button("⬅ Dashboard"):
        st.switch_page("pages/2_📊_Dashboard.py")

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("## 🔗 Connect a Data Source")
st.caption("Upload a CSV or connect a database to start analysing your metrics.")

# ── Dataset limit banner ──────────────────────────────────────────────────────
max_ds    = get_max_datasets(tier)
current_n = count_user_datasets(uid) if is_logged_in else 0

if is_logged_in and max_ds != -1:
    remaining = max_ds - current_n
    if remaining <= 0:
        st.error(
            f"You've reached the **{max_ds} dataset limit** on your current plan. "
            "Delete an existing dataset or upgrade to add more."
        )
        _show_upgrade = True
    else:
        st.info(f"**{remaining}** of {max_ds} dataset slots remaining on your plan.")
        _show_upgrade = False
else:
    _show_upgrade = False

st.divider()

# ── Add new dataset ───────────────────────────────────────────────────────────
if not _show_upgrade:
    st.markdown("### Add New Dataset")

    connector_options = ["CSV / Excel Upload"]
    if check_access("db_connectors", tier):
        connector_options += ["PostgreSQL", "MySQL / MariaDB", "Google BigQuery"]

    connector_choice = st.selectbox(
        "Source type",
        connector_options,
        help="DB Connectors require the Business plan.",
    )

    # ── CSV flow ──────────────────────────────────────────────────────────────
    if connector_choice == "CSV / Excel Upload":
        ds_name  = st.text_input("Dataset name", placeholder="e.g. Q1 2025 E-commerce")
        uploaded = st.file_uploader("Upload file", type=["csv", "xlsx", "xls"])

        if uploaded and ds_name:
            conn = CSVConnector()
            ok, msg = conn.connect(uploaded)
            if not ok:
                st.error(msg)
            else:
                df_raw = conn.fetch_data()
                st.success(f"File loaded — {len(df_raw):,} rows × {len(df_raw.columns)} columns")

                # Schema mapping
                st.markdown("#### Map Your Columns")
                st.caption("MetricSleuth detected these matches. Adjust if needed.")

                suggested = suggest_mapping(df_raw)
                col_options = ["— not mapped —"] + list(df_raw.columns)
                mapping: dict[str, str] = {}

                scols = st.columns(2)
                for i, field in enumerate(CANONICAL_FIELDS):
                    col = scols[i % 2]
                    suggested_col = suggested.get(field, "")
                    idx = col_options.index(suggested_col) if suggested_col in col_options else 0
                    chosen = col.selectbox(
                        f"{'⚠ ' if field in REQUIRED_FIELDS else ''}**{field}**" + (" *(required)*" if field in REQUIRED_FIELDS else " *(optional)*"),
                        col_options, index=idx, key=f"map_{field}",
                    )
                    if chosen != "— not mapped —":
                        mapping[field] = chosen

                # Preview
                errors = validate_mapping(mapping, df_raw)
                if errors:
                    for e in errors:
                        st.warning(e)
                else:
                    with st.expander("Preview mapped data (first 5 rows)"):
                        try:
                            preview_df = apply_mapping(df_raw.head(100), mapping)
                            st.dataframe(preview_df.head(5), use_container_width=True)
                        except Exception as exc:
                            st.error(f"Preview failed: {exc}")

                    if st.button("🚀 Load & Continue to Dashboard", key="save_csv", type="primary"):
                        with st.spinner("Processing data…"):
                            df_canonical = apply_mapping(df_raw, mapping)
                            st.session_state["active_df"] = df_canonical.to_json(orient="split", date_format="iso")
                            st.session_state["active_dataset_name"] = ds_name
                            
                            if is_logged_in:
                                ds_id = save_dataset_meta(
                                    user_id=uid,
                                    name=ds_name,
                                    connector_type="csv",
                                    schema_mapping=mapping,
                                    row_count=len(df_raw),
                                )
                                if ds_id:
                                    st.session_state["active_dataset_id"] = ds_id
                            else:
                                if "active_dataset_id" in st.session_state:
                                    del st.session_state["active_dataset_id"]

                        st.success(f"Dataset **{ds_name}** loaded! Redirecting to dashboard…")
                        st.switch_page("pages/2_📊_Dashboard.py")

    # ── DB connectors (Business tier gate) ───────────────────────────────────
    elif connector_choice in ("PostgreSQL", "MySQL / MariaDB", "Google BigQuery"):
        if not gate("db_connectors"):
            pass   # gate() already rendered the upgrade prompt
        else:
            ctype_map = {
                "PostgreSQL":         "postgres",
                "MySQL / MariaDB":    "mysql",
                "Google BigQuery":    "bigquery",
            }
            ctype = ctype_map[connector_choice]
            ds_name = st.text_input("Dataset name", placeholder="e.g. Production DB - Revenue")

            with st.form(f"conn_form_{ctype}"):
                if ctype == "postgres":
                    host = st.text_input("Host", "localhost")
                    port = st.number_input("Port", value=5432, step=1)
                    database = st.text_input("Database name")
                    user_db  = st.text_input("Username")
                    password = st.text_input("Password", type="password")
                    query    = st.text_area("SQL Query", "SELECT * FROM metrics ORDER BY date DESC LIMIT 10000")
                    submitted = st.form_submit_button("Test & Connect")
                    if submitted:
                        from src.connectors.postgres_connector import PostgresConnector
                        conn = PostgresConnector()
                        ok, msg = conn.connect(host=host, port=int(port), database=database, user=user_db, password=password)
                        if ok:
                            st.success(msg)
                            df_raw = conn.fetch_data(query)
                            st.dataframe(df_raw.head(5), use_container_width=True)
                            suggested = suggest_mapping(df_raw)
                            st.json(suggested)
                            # Save (no password stored)
                            save_dataset_meta(uid, ds_name, "postgres", suggested, conn.to_config(), len(df_raw))
                            st.success("Dataset saved!")
                        else:
                            st.error(msg)

                elif ctype == "mysql":
                    host = st.text_input("Host", "localhost")
                    port = st.number_input("Port", value=3306, step=1)
                    database = st.text_input("Database name")
                    user_db  = st.text_input("Username")
                    password = st.text_input("Password", type="password")
                    query    = st.text_area("SQL Query", "SELECT * FROM metrics ORDER BY date DESC LIMIT 10000")
                    submitted = st.form_submit_button("Test & Connect")
                    if submitted:
                        from src.connectors.mysql_connector import MySQLConnector
                        conn = MySQLConnector()
                        ok, msg = conn.connect(host=host, port=int(port), database=database, user=user_db, password=password)
                        if ok:
                            st.success(msg)
                            df_raw = conn.fetch_data(query)
                            st.dataframe(df_raw.head(5), use_container_width=True)
                        else:
                            st.error(msg)

                elif ctype == "bigquery":
                    project_id = st.text_input("GCP Project ID")
                    creds_json = st.text_area("Service Account JSON (paste full JSON)", height=150)
                    query = st.text_area("BigQuery SQL", "SELECT * FROM `dataset.table` LIMIT 10000")
                    submitted = st.form_submit_button("Test & Connect")
                    if submitted:
                        from src.connectors.bigquery_connector import BigQueryConnector
                        conn = BigQueryConnector()
                        ok, msg = conn.connect(project_id=project_id, credentials_json=creds_json)
                        if ok:
                            st.success(msg)
                            df_raw = conn.fetch_data(query)
                            st.dataframe(df_raw.head(5), use_container_width=True)
                        else:
                            st.error(msg)

st.divider()

# ── Existing datasets ─────────────────────────────────────────────────────────
st.markdown("### Your Datasets")
if not is_logged_in:
    st.info("Log in to save and manage multiple datasets securely.")
else:
    datasets = get_user_datasets(uid)
    if not datasets:
        st.info("No datasets yet. Add one above to get started.")
    else:
        for ds in datasets:
            col_a, col_b, col_c = st.columns([4, 1, 1])
            col_a.markdown(
                f"**{ds['name']}** &nbsp;&nbsp;"
                f"<span style='font-size:.72rem;color:#3a4a6b;font-family:JetBrains Mono;'>"
                f"{ds['connector_type'].upper()} · {ds.get('row_count', '?'):,} rows · "
                f"{ds['created_at'][:10]}</span>",
                unsafe_allow_html=True,
            )
            if col_b.button("Load", key=f"load_{ds['id']}"):
                st.session_state["active_dataset_id"] = ds["id"]
                st.session_state["active_dataset_name"] = ds["name"]
                st.session_state["active_schema_mapping"] = ds["schema_mapping"]
                st.switch_page("pages/2_📊_Dashboard.py")
            if col_c.button("🗑", key=f"del_{ds['id']}", help="Delete dataset"):
                delete_dataset(ds["id"], uid)
                st.rerun()
