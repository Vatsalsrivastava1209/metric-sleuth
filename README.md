# Metric Sleuth

Client anomaly detection and white-label investigation briefs for ecommerce agencies.

Metric Sleuth is a SaaS product for agencies managing multiple ecommerce or paid media accounts. The product is no longer framed as a generic enterprise analytics platform. The wedge is narrower and more useful: help agency teams catch client KPI anomalies early, investigate likely drivers quickly, and send a clean client-ready brief without rebuilding the story from scratch.

## What the product does

- Saves storefront and channel exports as reusable client workspaces.
- Detects unusual movement in metrics like `revenue`, `traffic`, `orders`, and `conversion_rate`.
- Runs segmentation, correlation, and contribution analysis to rank likely drivers.
- Generates internal investigation briefs plus client-ready summary exports.
- Organizes reports in an incident inbox for portfolio-level review.
- Supports historical pattern search for teams that want to compare new incidents with past ones.

## Product positioning

The intended buyer is not "all enterprises with data."

The intended buyer is:
- ecommerce agencies
- paid media agencies
- growth teams managing repeated client reporting workflows

The product pitch is:

> Metric Sleuth helps ecommerce agencies detect client KPI anomalies early, explain likely drivers using connected data, and send white-label briefs in minutes.

## Architecture

- `frontend/`: Next.js application for the public landing page, authentication, portfolio dashboard, client workspaces, incident inbox, settings, billing, and exports.
- `api/`: FastAPI backend for investigation jobs, dataset APIs, billing webhooks, exports, account settings, and pattern-library endpoints.
- `src/`: analytics, storage, billing, connector, retrieval, persistence, and observability logic.
- `supabase/`: schema and RLS setup for multi-tenant persistence and private dataset storage.
- `tests/`: backend and analytical regression coverage.

## Primary workflow

1. Sign in through the Next.js app.
2. Save a storefront or channel export as a client workspace.
3. Run an investigation against a saved workspace or one-off upload.
4. Review the incident in the portfolio dashboard or incident inbox.
5. Switch between internal investigation mode and client-summary mode.
6. Export markdown or PDF deliverables for the account team.

## Local development

### Backend

```bash
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend expects the backend at `http://localhost:8000` unless `NEXT_PUBLIC_API_URL` or `METRICSLEUTH_API_URL` is set.

## Required services

- Supabase for auth, Postgres, and private file storage
- Redis for rate limiting and job ownership checks
- Celery worker for asynchronous investigations
- Stripe for agency billing and plan lifecycle

## Security and multi-tenancy

- Supabase Row-Level Security gates profiles, datasets, and reports.
- Background jobs use service-role connectivity with session impersonation instead of expiring user JWTs.
- Durable dataset files live in a private storage bucket scoped by user path prefixes.
- The API enforces JWT auth, security headers, and backend-side rate limiting.
- Client-ready exports still require authenticated access; they are shorter and safer than the internal analyst narrative.

## Evaluation and testing

```bash
python -m pytest -q
```

The anomaly detector includes a lightweight backtesting path in `src/anomaly_evaluation.py` so labeled incident dates can be scored with precision, recall, and F1 during regression testing.

## Production rollout

Use the runbook in [docs/PRODUCTION_ROLLOUT.md](/C:/Users/12vat/metric-sleuth/docs/PRODUCTION_ROLLOUT.md) for:

- exact Supabase migration order
- deploy sequencing across API, worker, beat, and frontend
- smoke tests and post-deploy validation
