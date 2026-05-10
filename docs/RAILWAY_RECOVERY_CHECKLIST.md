# Railway Recovery Checklist

Use this when GitHub shows failing Railway deployment checks for `metric-sleuth`.

## Goal

End up with **one canonical Railway project** for this repo.

That project should contain exactly these services:

1. `metricsleuth-api`
2. `metricsleuth-worker`
3. `metricsleuth-beat`
4. `metricsleuth-frontend`
5. `redis`

If you see old duplicate Railway projects or duplicate frontend/api services, remove or disconnect them.

## 1. Clean up stale Railway projects

In Railway:

1. Open the GitHub-linked deployments for `metric-sleuth`.
2. Find which project/environment is the real one you want to keep.
3. Look for old projects that still report deploy status back to GitHub.
4. Remove or disconnect stale projects so GitHub stops showing fake-failing duplicate checks.

Expected result:

- One Railway project is authoritative.
- One environment is authoritative.
- GitHub deploy checks come from that one project only.

## 2. Create the required Railway services

### Service: `metricsleuth-api`

- Source: repo root
- Builder: Dockerfile
- Dockerfile path: `Dockerfile`
- Start command:

```bash
uvicorn api.main:app --host 0.0.0.0 --port $PORT
```

- Healthcheck path:

```text
/api/health
```

### Service: `metricsleuth-worker`

- Source: same repo root image as API
- Start command:

```bash
celery -A api.worker.celery_app worker --loglevel=info --concurrency=4 --max-tasks-per-child=100
```

### Service: `metricsleuth-beat`

- Source: same repo root image as API
- Start command:

```bash
celery -A api.worker.celery_app beat --loglevel=info --scheduler=celery.beat:PersistentScheduler --schedule=/data/celerybeat-schedule
```

- Important:
  Run exactly one beat service per environment.

### Service: `metricsleuth-frontend`

- Source: `frontend/`
- Builder: Dockerfile
- Dockerfile path: `frontend/Dockerfile`
- Start command:

```bash
npm run start
```

### Service: `redis`

- Use Railway Redis if available, or a dedicated Redis service.
- This must back:
  - Celery broker
  - Celery result backend
  - API-side rate limiting

## 3. Set environment variables

### Shared on `metricsleuth-api`, `metricsleuth-worker`, `metricsleuth-beat`

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_KEY`
- `REDIS_URL`
- `APP_SECRET_KEY`
- `CORS_ORIGINS`
- `DOCS_ENABLED=false`

Recommended:

- `ENVIRONMENT=production`
- `APP_VERSION=<git-sha-or-release-tag>`
- `USE_PROPHET=true`
- `REPORT_SHARE_TTL_DAYS=14`

If billing is enabled:

- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRICE_PRO`
- `STRIPE_PRICE_BUSINESS`

If semantic memory is enabled:

- `EMBED_BACKEND=openai`
- `EMBED_API_KEY` or `OPENAI_API_KEY`

If LLM summaries are enabled:

- `LLM_BACKEND`
- `LLM_MODEL`
- `LLM_API_KEY`

### On `metricsleuth-frontend`

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `NEXT_PUBLIC_API_URL`

Optional but useful:

- `METRICSLEUTH_API_URL`

## 4. Very common Railway mistakes

If Railway is red, check these first:

1. `APP_SECRET_KEY` missing on API/worker/beat
2. `REDIS_URL` missing or pointing at dead Redis
3. frontend pointing at the wrong API URL
4. frontend and backend pointing at different Supabase projects
5. worker/beat not deployed at all
6. old Railway projects still attached to GitHub status checks

## 5. Deploy order

Do this in order:

1. Apply Supabase migrations first
2. Deploy `redis`
3. Deploy `metricsleuth-api`
4. Deploy `metricsleuth-worker`
5. Deploy `metricsleuth-beat`
6. Deploy `metricsleuth-frontend`
7. Run smoke tests

Do not deploy frontend first.

## 6. Minimum post-deploy checks

### API

- `/api/health` returns `200`

### Worker

- analysis runs leave `QUEUED`
- jobs reach `RUNNING`
- successful jobs create reports

### Beat

- only one beat instance is running

### Frontend

- login works
- dashboard loads
- one-off analysis starts
- report page loads

## 7. When to trust Railway again

Trust Railway deploy checks only when:

- duplicate stale Railway projects are gone
- all four app services exist
- Redis is healthy
- API healthcheck is green
- smoke tests pass on the same environment

