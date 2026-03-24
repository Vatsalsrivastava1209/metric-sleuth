# MetricSleuth SaaS

> **AI-powered Root Cause Analysis engine for business metrics — now as a deployable Multi-Tenant SaaS.**

MetricSleuth automatically detects anomalies in time-series KPIs (revenue, traffic, conversion rate) and traces them back to their likely root causes using statistical analysis and a rule-based hypothesis engine. 

This repository contains the full production-ready SaaS application, packaged as a multi-page interactive Streamlit dashboard with built-in user authentication, role-based data isolation, tiered billing, and cloud deployment configurations.

---

## 🌟 SaaS Features

| Module | What it does |
|---|---|
| **Multi-Tenancy** | Secure Row-Level Security (RLS) ensuring isolated user data |
| **Authentication** | Built-in Supabase auth (Email/Password) with session management |
| **Stripe Billing** | Tiered pricing (Free/Pro/Business) and gating for premium features |
| **Data Connectors** | CSV upload + mapped DB support (PostgreSQL, MySQL, BigQuery) |
| **Schema Mapper** | Auto-detects and fuzzy-matches custom DB data columns |
| **Anomaly Engine** | Z-score + Facebook Prophet time-series anomaly detection |
| **AI Root Cause** | Factoring analysis, correlations, and LLM-powered summaries |
| **RAG History** | Full knowledge base of all past RCA reports for semantic search |
| **Alerts & Exports** | Download markdown/PDF reports and send alerts to Slack/Email |

---

## 📂 Project Structure

```
metric-sleuth/
├── Home.py                       # Landing Page & Auth Entrypoint
├── pages/                        # Multi-page App Routes
│   ├── 1_🔗_Connect.py           # Data Sources & Schema Mapping
│   ├── 2_📊_Dashboard.py         # Main RCA Dashboard
│   ├── 3_📈_Reports.py           # Historical RCA Reports
│   ├── 4_💳_Billing.py           # Stripe Subscription Management
│   └── 5_⚙️_Settings.py          # User Preferences & Alerts
├── src/                          # Backend Logic
│   ├── auth.py                   # Supabase auth abstractions
│   ├── billing.py                # Stripe & Feature-gate logic
│   ├── db.py                     # DB CRUD layer with RLS compliance
│   ├── schema_mapper.py          # Fuzzy matching logic
│   ├── connectors/               # Supported database connectors
│   └── (RCA engine files)        # The core statistical analysis layer
├── app/
│   └── webhook.py                # Lightweight Flask Stripe Webhook Server
├── supabase/
│   └── schema.sql                # Full DB Schema, triggers, & RLS policies
├── requirements.txt
├── docker-compose.yml
├── Dockerfile
└── .env.example
```

---

## 🚀 Quick Start (Local Development)

### 1. Configure Environment

Copy the example environment variable template:
```bash
cp .env.example .env
```
Fill out `.env` with your **Supabase details** (URL, ANON_KEY, SERVICE_KEY) and **Stripe details** (Secret Keys, Price IDs).

> **Important**: You must run the SQL script located in `supabase/schema.sql` via your Supabase project's SQL Editor to set up the appropriate tables, triggers, and RLS policies.

### 2. Run with Docker Compose

Running the entire stack locally via Docker is strongly recommended. This spins up both the **Streamlit Web Application** on `http://localhost:8501` and the **Stripe Webhook Server** on `http://localhost:5001`.

```bash
docker-compose up --build
```

### 3. Alternative: Run Natively Python

If you prefer to run it natively without Docker:

```bash
pip install -r requirements.txt

# In terminal 1: Start the Webhook Server
python app/webhook.py

# In terminal 2: Start the SaaS Application
streamlit run Home.py
```

---

## ☁️ Deployment

This project includes fully configured deployment files for popular cloud hosts.

### Option A: Railway (One-Click)
Deploy instantly using the Railway CLI or by linking your Github repo to Railway. The `railway.toml` handles the build and entrypoint port bindings natively.

```bash
railway up
```

### Option B: Render.com
A `render.yaml` blueprint is provided giving you a fully managed infrastructure consisting of two independent services: the Streamlit App and Webhook Server, complete with persistent disks for the RAG index.

### Option C: Your Custom Virtual Machine
Deploy anywhere Docker is installed using:
```bash
docker-compose up -d --build
```

