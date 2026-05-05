# Metric Sleuth Production Rollout Runbook

This document is the canonical rollout guide for the current production
architecture:

- `frontend/` -> Next.js
- `api/` -> FastAPI
- `api/worker.py` + `api/tasks.py` -> Celery worker / beat
- Supabase -> Auth, Postgres, Storage
- Redis -> rate limiting, Celery broker/backend
- Stripe -> billing

This runbook is written for the current repository state as of April 9, 2026.

## 1. Rollout strategy

Use this order:

1. Validate the release candidate locally.
2. Back up Supabase and prepare secrets.
3. Apply database/storage migrations.
4. Deploy backend API.
5. Deploy Celery worker.
6. Deploy Celery beat.
7. Deploy frontend.
8. Run smoke tests.
9. Run post-deploy validation.
10. Watch logs and queue health for at least one full investigation cycle.

Do not deploy frontend first. The frontend depends on backend contracts that may
change with the same release.

## 2. Supabase migration order

### Existing environment

For an existing project, apply only the ordered migration files in
[`supabase/migrations`](/C:/Users/12vat/metric-sleuth/supabase/migrations).

Current order:

1. [`20260408_enterprise_hardening.sql`](/C:/Users/12vat/metric-sleuth/supabase/migrations/20260408_enterprise_hardening.sql)
2. [`20260409_memory_fail_closed_and_schema_alignment.sql`](/C:/Users/12vat/metric-sleuth/supabase/migrations/20260409_memory_fail_closed_and_schema_alignment.sql)

Execution checklist:

1. Open Supabase Dashboard -> SQL Editor.
2. Confirm the target project is the correct environment.
3. Take a database backup / snapshot before applying changes.
4. Run the migration files in lexical order, one file at a time.
5. Confirm each file completes without errors before moving to the next.

### Fresh environment

For a brand-new environment:

1. Apply [`schema.sql`](/C:/Users/12vat/metric-sleuth/supabase/schema.sql)
2. Skip [`api/supabase_rls.sql`](/C:/Users/12vat/metric-sleuth/api/supabase_rls.sql)
   It is now a compatibility note, not an executable migration source.

For a fresh environment built from `schema.sql`, the two migration files above
should already be reflected in the bootstrap schema.

## 3. Required environment variables

### API and worker services

These must be present in both the FastAPI service and every Celery process:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_KEY`
- `REDIS_URL`
- `CELERY_RESULT_BACKEND`
- `APP_SECRET_KEY`
- `USE_PROPHET`
- `CORS_ORIGINS`
- `DOCS_ENABLED`

Billing-enabled environments also need:

- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRICE_PRO`
- `STRIPE_PRICE_BUSINESS`

Semantic memory environments also need:

- `EMBED_BACKEND=openai`
- `EMBED_API_KEY` or `OPENAI_API_KEY`

Optional LLM summary defaults:

- `LLM_BACKEND`
- `LLM_MODEL`
- `LLM_API_KEY`
- `LLM_MAX_TOKENS`
- `LLM_TEMPERATURE`

### Frontend service

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `NEXT_PUBLIC_API_URL`
- `METRICSLEUTH_API_URL` if you use server-side routing helpers that rely on it

### Important notes

- `APP_BASE_URL` should point at the deployed frontend URL, not a local port.
- Do not use `EMBED_BACKEND=gemini` with the current production schema.
  Semantic memory is pinned to 1536-dimensional OpenAI embeddings.

## 4. Pre-deploy checks

Run these from the repo before deploying:

```bash
python -m pytest -q
python -m py_compile src/rag_indexer.py src/rag_query.py api/routers/memory.py api/routers/analyze.py src/db.py src/anomaly_detection.py src/prophet_anomaly_detection.py src/anomaly_evaluation.py src/llm_summary.py src/report_export.py
cd frontend
npm run lint
```

Expected current baseline:

- backend tests pass
- Python compile check passes
- frontend lint passes

## 5. Deployment checklist

### Phase A: Supabase

1. Verify `vector` extension is enabled.
2. Confirm buckets exist after migration:
   - `temp-processing`
   - `user-datasets`
3. Confirm RPC functions exist:
   - `public.set_claim`
   - `public.match_rca_embeddings`
4. Confirm RLS is enabled on:
   - `profiles`
   - `datasets`
   - `analysis_runs`
   - `rca_reports`
   - `rca_embeddings`
5. Confirm `analysis_runs` has:
   - `started_at`
   - `completed_at`
   - `report_id` foreign key

### Phase B: Backend API

1. Deploy the API image from [`Dockerfile`](/C:/Users/12vat/metric-sleuth/Dockerfile).
2. Confirm `/api/health` returns `200`.
3. Confirm the API has live connectivity to:
   - Supabase
   - Redis
   - Stripe, if enabled

### Phase C: Celery worker

1. Deploy a dedicated worker process from the same backend image.
2. Use the worker command already modeled in [`docker-compose.yml`](/C:/Users/12vat/metric-sleuth/docker-compose.yml):

```bash
celery -A api.worker.celery_app worker --loglevel=info --concurrency=4 --max-tasks-per-child=100
```

3. Confirm the worker can connect to Redis.
4. Confirm the worker can read/write Supabase storage and tables.

### Phase D: Celery beat

1. Deploy a dedicated beat process from the same backend image.
2. Use the beat command modeled in [`docker-compose.yml`](/C:/Users/12vat/metric-sleuth/docker-compose.yml):

```bash
celery -A api.worker.celery_app beat --loglevel=info --scheduler=celery.beat:PersistentScheduler --schedule=/data/celerybeat-schedule
```

3. Only run one beat instance per environment unless you introduce leader election.

### Phase E: Frontend

1. Deploy the Next.js image from [`frontend/Dockerfile`](/C:/Users/12vat/metric-sleuth/frontend/Dockerfile).
2. Confirm the frontend is pointed at the new API URL.
3. Confirm authentication succeeds against the same Supabase project as the backend.

## 6. Smoke test runbook

Run these immediately after deploy.

### Auth and account

1. Log in through the frontend.
2. Open dashboard.
3. Open settings.
4. Confirm profile load succeeds.

### Dataset path

1. Open client workspace page.
2. Upload a CSV under 200 MB.
3. Save it as a durable workspace.
4. Confirm it appears in the dataset list.
5. Delete and re-create one test workspace to validate storage cleanup.

### One-off investigation

1. Open dashboard.
2. Choose one-off upload.
3. Upload a CSV.
4. Start investigation.
5. Polling should move through:
   - `QUEUED`
   - `RUNNING`
   - `SUCCESS` or `FAILURE`
6. On success, confirm:
   - `analysis_runs.report_id` is populated
   - a row exists in `rca_reports`
   - the temporary object is deleted from `temp-processing`

### Saved workspace investigation

1. Choose a saved workspace.
2. Run investigation.
3. Confirm the report lands in the incident inbox.

### Export path

1. Open a report.
2. Download markdown export.
3. Download PDF export.
4. Test both internal and client audience modes.

### Semantic memory

Run this only if embeddings are configured.

1. Open memory page.
2. Confirm stats show indexed documents or an explicit readiness error.
3. Ask a grounded question against prior reports.
4. Confirm a real answer and supporting sources are returned.
5. If embeddings are not configured, confirm the UI/API returns a clear unavailable state instead of fake results.

### Billing

1. Start a test checkout session.
2. Complete the Stripe test flow.
3. Confirm the webhook updates the subscription tier.
4. Confirm the frontend reflects the new plan.

## 7. Production validation queries

Use Supabase SQL Editor for spot checks.

### Recent analysis runs

```sql
select id, user_id, status, started_at, completed_at, report_id, created_at
from public.analysis_runs
order by created_at desc
limit 20;
```

### Failed investigations

```sql
select id, user_id, status_message, error_message, progress_meta, created_at
from public.analysis_runs
where status = 'FAILURE'
order by created_at desc
limit 20;
```

### Reports without linked runs

```sql
select r.id, r.user_id, r.created_at
from public.rca_reports r
left join public.analysis_runs a on a.report_id = r.id
where a.id is null
order by r.created_at desc
limit 20;
```

### Indexed embeddings

```sql
select id, user_id, report_id, created_at
from public.rca_embeddings
order by created_at desc
limit 20;
```

## 8. Observability checks

At minimum, verify:

1. API logs show request IDs.
2. Worker logs show investigation stage changes.
3. Queue backlog is not growing unexpectedly.
4. Repeated `FAILURE` runs are investigated before customer traffic ramps.
5. Stripe webhook failures are visible and retriable.

If you use an external logging system, filter on:

- `memory.query`
- `memory.cleared`
- investigation run IDs
- Stripe webhook event IDs

## 9. Rollback plan

### App rollback

1. Roll back frontend first if the issue is presentation-only.
2. Roll back API and workers together if the contract changed.
3. Do not roll back only workers when API contracts or task payloads changed.

### Database rollback

There is no safe blind rollback for Supabase SQL in this repo today.

Use this rule:

1. Take a backup before migration.
2. If migration fails partway, stop deploy, inspect the exact failing statement, and repair forward.
3. If a full environment rollback is required, restore from backup instead of hand-editing security policies under pressure.

## 10. Known rollout cautions

- [`render.yaml`](/C:/Users/12vat/metric-sleuth/render.yaml) currently models web services but does not fully describe the full production worker/beat topology by itself. Treat this runbook as authoritative until platform config is expanded.
- [`Dockerfile`](/C:/Users/12vat/metric-sleuth/Dockerfile) still creates `/app/data`, which is harmless, but semantic memory no longer relies on local disk state.
- Semantic memory is intentionally stricter now. Missing embedding config should produce a visible unavailable state, not silent degradation.

## 11. Exit criteria for a successful rollout

You are done only when all of the following are true:

1. Migrations applied cleanly.
2. API health check is green.
3. Worker and beat are connected and stable.
4. One-off upload investigation succeeds.
5. Saved workspace investigation succeeds.
6. Internal and client exports succeed.
7. Billing webhook updates a test tier correctly.
8. Semantic memory either works correctly or fails explicitly with the expected readiness error.
9. No unexplained `FAILURE` runs are accumulating.
