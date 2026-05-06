-- =============================================================================
-- MetricSleuth SaaS — Supabase Schema
-- Run this in: Supabase Dashboard → SQL Editor → New Query → Run
-- =============================================================================

-- ── 1. PROFILES ───────────────────────────────────────────────────────────────
-- Extends auth.users with SaaS-specific fields.
-- Automatically created when a new user signs up (via trigger below).

CREATE TABLE IF NOT EXISTS public.profiles (
    id                  UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email               TEXT,
    full_name           TEXT,
    subscription_tier   TEXT NOT NULL DEFAULT 'free'   -- 'free' | 'pro' | 'business'
                        CHECK (subscription_tier IN ('free', 'pro', 'business')),
    stripe_customer_id  TEXT,
    -- payment_failed_at: set by invoice.payment_failed webhook; cleared on successful payment.
    -- The UI reads this to show a "payment failed — update your card" warning banner
    -- WITHOUT immediately downgrading the user while Stripe is retrying.
    payment_failed_at   TIMESTAMPTZ,
    llm_backend         TEXT DEFAULT 'gemini',          -- 'gemini' | 'openai'

    -- ── LLM API Key Storage — Supabase Vault (P1-B Security Migration) ────────
    --
    -- STATUS: llm_api_key (plaintext TEXT) is DEPRECATED. New writes use
    -- llm_api_key_vault_id which stores the Vault secret name.
    --
    -- HOW VAULT WRITE WORKS (called from src/db.py update_profile):
    --   SELECT vault.create_secret(
    --     '<plaintext_key>',              -- the actual secret value
    --     'llm_key_' || user_id::text,    -- unique secret name per user
    --     'MetricSleuth LLM API key'      -- description
    --   );
    --   Then store the returned UUID in llm_api_key_vault_id.
    --
    -- HOW VAULT READ WORKS (called from src/db.py get_profile):
    --   SELECT decrypted_secret
    --   FROM vault.decrypted_secrets
    --   WHERE name = 'llm_key_' || user_id::text;
    --
    -- BACKFILL MIGRATION (run once after enabling Vault):
    --   UPDATE profiles
    --   SET llm_api_key_vault_id = (
    --     SELECT vault.create_secret(llm_api_key, 'llm_key_' || id::text, 'backfill')
    --     FROM profiles p2 WHERE p2.id = profiles.id
    --   )
    --   WHERE llm_api_key IS NOT NULL AND llm_api_key != '';
    --   -- After verifying all rows migrated:
    --   -- ALTER TABLE profiles DROP COLUMN llm_api_key;
    llm_api_key         TEXT DEFAULT '',    -- DEPRECATED: plaintext. Retained for backfill compatibility only.
    llm_api_key_vault_id TEXT,              -- Supabase Vault secret name = 'llm_key_{user_id}'

    slack_webhook_url   TEXT DEFAULT '',
    alert_email         TEXT DEFAULT '',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ── connection_config encryption note (P2) ───────────────────────────────────
-- The datasets.connection_config JSONB column stores database connection params
-- (host, port, username). In production, passwords MUST be stored via Supabase
-- Vault rather than in plaintext JSONB. Migration path is identical to llm_api_key
-- above: store a vault_secret_id in the JSONB, read the actual password at
-- connector runtime via vault.decrypted_secrets.
-- ALTER TABLE public.datasets ADD COLUMN IF NOT EXISTS connection_config_vault_id TEXT;

-- Auto-create profile on user signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    INSERT INTO public.profiles (id, email)
    VALUES (NEW.id, NEW.email);
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER profiles_updated_at
    BEFORE UPDATE ON public.profiles
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


-- ── 2. DATASETS ───────────────────────────────────────────────────────────────
-- Stores metadata about each connected data source per user.

CREATE TABLE IF NOT EXISTS public.datasets (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    name             TEXT NOT NULL,
    connector_type   TEXT NOT NULL DEFAULT 'csv'
                     CHECK (connector_type IN (
                        'csv', 'postgres', 'mysql', 'bigquery',
                        'shopify', 'ga4', 'meta_ads', 'google_ads', 'klaviyo'
                     )),
    schema_mapping   JSONB DEFAULT '{}',    -- maps user columns → canonical columns
    connection_config JSONB DEFAULT '{}',  -- encrypted connection params (no raw passwords)
    row_count        INTEGER,
    last_synced_at   TIMESTAMPTZ,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TRIGGER datasets_updated_at
    BEFORE UPDATE ON public.datasets
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- Index for fast user dataset lookups
CREATE INDEX IF NOT EXISTS datasets_user_id_idx ON public.datasets(user_id);

CREATE TABLE IF NOT EXISTS public.analysis_runs (
    id              TEXT PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    dataset_id      UUID REFERENCES public.datasets(id) ON DELETE SET NULL,
    source_label    TEXT NOT NULL DEFAULT '',
    metric          TEXT NOT NULL,
    storage_key     TEXT,
    source_type     TEXT NOT NULL DEFAULT 'saved_dataset',
    status          TEXT NOT NULL DEFAULT 'QUEUED'
                     CHECK (status IN ('QUEUED', 'RUNNING', 'SUCCESS', 'FAILURE')),
    status_message  TEXT NOT NULL DEFAULT '',
    progress_meta   JSONB NOT NULL DEFAULT '{}',
    error_message   TEXT,
    report_id       UUID,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    dead_lettered_at TIMESTAMPTZ,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TRIGGER analysis_runs_updated_at
    BEFORE UPDATE ON public.analysis_runs
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE INDEX IF NOT EXISTS analysis_runs_user_created_idx
    ON public.analysis_runs(user_id, created_at DESC);


-- ── 3. RCA REPORTS ───────────────────────────────────────────────────────────
-- Stores metadata for each generated RCA report (full report stored in RAG index on disk).

CREATE TABLE IF NOT EXISTS public.rca_reports (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    dataset_id       UUID REFERENCES public.datasets(id) ON DELETE SET NULL,
    anomaly_date     DATE NOT NULL,
    primary_metric   TEXT NOT NULL DEFAULT 'revenue',
    executive_summary TEXT,
    n_anomalies      INTEGER DEFAULT 0,
    n_hypotheses     INTEGER DEFAULT 0,
    top_hypothesis   TEXT,
    confidence       NUMERIC(4,2),
    report_md        TEXT,             -- full markdown report stored here
    report_payload   JSONB NOT NULL DEFAULT '{}',
    workflow_status  TEXT NOT NULL DEFAULT 'new'
                     CHECK (workflow_status IN ('new', 'investigating', 'ready_to_send', 'sent')),
    assigned_owner   TEXT DEFAULT '',
    internal_notes   TEXT DEFAULT '',
    share_token      TEXT UNIQUE,
    share_created_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    share_created_at TIMESTAMPTZ,
    share_expires_at TIMESTAMPTZ,
    share_last_accessed_at TIMESTAMPTZ,
    share_revoked_at TIMESTAMPTZ,
    last_client_delivery_at TIMESTAMPTZ,
    delivery_channel TEXT,
    feedback_rating  INTEGER CHECK (feedback_rating BETWEEN 1 AND 5),
    feedback_notes   TEXT DEFAULT '',
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast report lookups
-- Simple user_id lookup (kept for FK integrity checks)
CREATE INDEX IF NOT EXISTS rca_reports_user_id_idx    ON public.rca_reports(user_id);
CREATE INDEX IF NOT EXISTS rca_reports_dataset_id_idx  ON public.rca_reports(dataset_id);
-- P2-D Fix: Compound index for get_user_reports() which orders by created_at DESC.
-- Without this, sorted pagination does a sequential scan even when filtered by user_id.
-- The DESC ordering matches the query pattern in src/db.py get_user_reports().
CREATE INDEX IF NOT EXISTS rca_reports_user_created_idx
    ON public.rca_reports(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS rca_reports_workflow_idx
    ON public.rca_reports(user_id, workflow_status, created_at DESC);

CREATE TABLE IF NOT EXISTS public.incident_comments (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id     UUID NOT NULL REFERENCES public.rca_reports(id) ON DELETE CASCADE,
    user_id       UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    author_email  TEXT,
    body          TEXT NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS incident_comments_report_idx
    ON public.incident_comments(report_id, created_at ASC);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'analysis_runs_report_id_fkey'
    ) THEN
        ALTER TABLE public.analysis_runs
        ADD CONSTRAINT analysis_runs_report_id_fkey
        FOREIGN KEY (report_id)
        REFERENCES public.rca_reports(id)
        ON DELETE SET NULL;
    END IF;
END $$;


-- ── 4. RAG EMBEDDINGS (pgvector — replaces ChromaDB) ─────────────────────────
-- Stores RCA report text embeddings for semantic similarity search.
--
-- Why pgvector instead of ChromaDB:
--   - ChromaDB writes to a local filesystem directory that is ephemeral in Docker
--     (data lost on container restart unless a volume is mounted).
--   - ChromaDB has no native RLS: the where={"user_id": uid} filter only restricts
--     query results, not the underlying SQLite file (cross-tenant co-location risk).
--   - pgvector is Supabase-native: backed up, RLS-enforced, horizontally safe.
--
-- Embedding dimensions: production is pinned to 1536 for OpenAI
-- text-embedding-3-small. If you change the embedding backend, update both
-- this schema and src/rag_indexer.py together.

-- Enable the pgvector extension (requires Supabase project with pgvector enabled
-- in the Dashboard → Database → Extensions → vector).
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS public.rca_embeddings (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    report_id       UUID        REFERENCES public.rca_reports(id) ON DELETE CASCADE,
    -- Stable content hash: {user_id_prefix}_{anomaly_date}_{metric} — prevents duplicate indexing
    doc_id          TEXT        NOT NULL,
    -- Plain-text representation of the RCA report (used for fallback display)
    document        TEXT        NOT NULL,
    -- Metadata stored as JSONB for flexible querying (anomaly_date, primary_metric, etc.)
    metadata        JSONB       NOT NULL DEFAULT '{}',
    -- The semantic embedding vector. Dimension must match EMBED_DIMS in rag_indexer.py.
    embedding       vector(1536),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Unique constraint on (user_id, doc_id) — supports upsert (ON CONFLICT DO UPDATE)
-- and prevents duplicate indexing of the same report for the same tenant.
CREATE UNIQUE INDEX IF NOT EXISTS rca_embeddings_user_doc_id_idx
    ON public.rca_embeddings(user_id, doc_id);

-- HNSW index for fast approximate nearest-neighbour search (cosine distance).
-- ef_construction=128 and m=16 are good defaults for < 1M vectors.
-- Rebuild after bulk inserts with: REINDEX INDEX CONCURRENTLY rca_embeddings_hnsw_idx;
CREATE INDEX IF NOT EXISTS rca_embeddings_hnsw_idx
    ON public.rca_embeddings
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 128);

-- Fast lookup for list_indexed_reports() — filters by user_id without vector scan.
CREATE INDEX IF NOT EXISTS rca_embeddings_user_idx
    ON public.rca_embeddings(user_id, created_at DESC);

CREATE OR REPLACE FUNCTION public.set_claim(uid uuid)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  PERFORM set_config('request.jwt.claim.sub', uid::text, true);
END;
$$;

REVOKE ALL ON FUNCTION public.set_claim(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.set_claim(uuid) FROM anon;
REVOKE ALL ON FUNCTION public.set_claim(uuid) FROM authenticated;
GRANT EXECUTE ON FUNCTION public.set_claim(uuid) TO service_role;

CREATE OR REPLACE FUNCTION public.match_rca_embeddings(
    query_embedding  vector,
    match_user_id    uuid,
    match_count      int DEFAULT 3
)
RETURNS TABLE (
    id          uuid,
    doc_id      text,
    document    text,
    metadata    jsonb,
    similarity  float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        e.id,
        e.doc_id,
        e.document,
        e.metadata,
        1 - (e.embedding <=> query_embedding) AS similarity
    FROM public.rca_embeddings e
    WHERE
        e.user_id = match_user_id
        AND e.embedding IS NOT NULL
    ORDER BY e.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

GRANT EXECUTE ON FUNCTION public.match_rca_embeddings(vector, uuid, int) TO service_role;
GRANT EXECUTE ON FUNCTION public.match_rca_embeddings(vector, uuid, int) TO authenticated;


-- ── 5. ROW LEVEL SECURITY ─────────────────────────────────────────────────────
-- All tables already have RLS enabled (via project-level auto-RLS setting).
-- These policies ensure users only see their own data.

-- profiles: users can only read/update their own profile
-- P2-D SECURITY NOTE: There is intentionally NO INSERT policy here.
-- New profile rows are created exclusively by the SECURITY DEFINER trigger
-- ``handle_new_user`` (defined above). If you add an INSERT policy, users
-- could craft a Supabase client call to insert a profile row with an
-- arbitrary ``subscription_tier`` (e.g. 'business') at signup, bypassing
-- Stripe entirely. The trigger-only insertion is the correct pattern.
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "profiles_select_own" ON public.profiles
    FOR SELECT USING (auth.uid() = id);

CREATE POLICY "profiles_update_own" ON public.profiles
    FOR UPDATE USING (auth.uid() = id);

-- datasets: users can only CRUD their own datasets
ALTER TABLE public.datasets ENABLE ROW LEVEL SECURITY;

CREATE POLICY "datasets_select_own" ON public.datasets
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "datasets_insert_own" ON public.datasets
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "datasets_update_own" ON public.datasets
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "datasets_delete_own" ON public.datasets
    FOR DELETE USING (auth.uid() = user_id);

ALTER TABLE public.analysis_runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "analysis_runs_select_own" ON public.analysis_runs
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "analysis_runs_insert_own" ON public.analysis_runs
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "analysis_runs_update_own" ON public.analysis_runs
    FOR UPDATE USING (auth.uid() = user_id);

-- rca_reports: users can only CRUD their own reports
ALTER TABLE public.rca_reports ENABLE ROW LEVEL SECURITY;

CREATE POLICY "reports_select_own" ON public.rca_reports
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "reports_insert_own" ON public.rca_reports
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "reports_update_own" ON public.rca_reports
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "reports_delete_own" ON public.rca_reports
    FOR DELETE USING (auth.uid() = user_id);

ALTER TABLE public.incident_comments ENABLE ROW LEVEL SECURITY;

CREATE POLICY "incident_comments_select_own" ON public.incident_comments
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "incident_comments_insert_own" ON public.incident_comments
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "incident_comments_delete_own" ON public.incident_comments
    FOR DELETE USING (auth.uid() = user_id);

-- rca_embeddings: isolated per tenant — mirrors rca_reports policies.
-- Background workers write via service-role + _impersonate_user() (set_claim RPC),
-- so the COALESCE pattern is used here to support both JWT sessions and service-role
-- impersonation (identical to the pattern in api/supabase_rls.sql).
ALTER TABLE public.rca_embeddings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "embeddings_select_own" ON public.rca_embeddings
    FOR SELECT USING (
        COALESCE(auth.uid()::text, current_setting('request.jwt.claim.sub', true)) = user_id::text
    );

CREATE POLICY "embeddings_insert_own" ON public.rca_embeddings
    FOR INSERT WITH CHECK (
        COALESCE(auth.uid()::text, current_setting('request.jwt.claim.sub', true)) = user_id::text
    );

CREATE POLICY "embeddings_delete_own" ON public.rca_embeddings
    FOR DELETE USING (
        COALESCE(auth.uid()::text, current_setting('request.jwt.claim.sub', true)) = user_id::text
    );

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'temp-processing',
    'temp-processing',
    false,
    209715200,
    ARRAY[
        'text/csv',
        'application/json',
        'text/plain',
        'application/octet-stream'
    ]
)
ON CONFLICT (id) DO NOTHING;

CREATE POLICY "temp_processing_service_role_only" ON storage.objects
    FOR ALL USING (
        bucket_id = 'temp-processing'
        AND auth.role() = 'service_role'
    )
    WITH CHECK (
        bucket_id = 'temp-processing'
        AND auth.role() = 'service_role'
    );

-- Private storage for durable saved datasets.
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'user-datasets',
    'user-datasets',
    false,
    209715200,
    ARRAY[
        'text/csv',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    ]
)
ON CONFLICT (id) DO NOTHING;

CREATE POLICY "dataset_storage_select_own" ON storage.objects
    FOR SELECT USING (
        bucket_id = 'user-datasets'
        AND auth.role() = 'authenticated'
        AND auth.uid()::text = (storage.foldername(name))[1]
    );

CREATE POLICY "dataset_storage_insert_own" ON storage.objects
    FOR INSERT WITH CHECK (
        bucket_id = 'user-datasets'
        AND auth.role() = 'authenticated'
        AND auth.uid()::text = (storage.foldername(name))[1]
    );

CREATE POLICY "dataset_storage_update_own" ON storage.objects
    FOR UPDATE USING (
        bucket_id = 'user-datasets'
        AND auth.role() = 'authenticated'
        AND auth.uid()::text = (storage.foldername(name))[1]
    );

CREATE POLICY "dataset_storage_delete_own" ON storage.objects
    FOR DELETE USING (
        bucket_id = 'user-datasets'
        AND auth.role() = 'authenticated'
        AND auth.uid()::text = (storage.foldername(name))[1]
    );


-- ── 5. FEATURE ACCESS LOG ─────────────────────────────────────────────────────
-- Tamper-evident audit trail for high-sensitivity feature access decisions.
-- Referenced in supabase_rls.sql; must be defined here before RLS policies run.

CREATE TABLE IF NOT EXISTS public.feature_access_log (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    feature     TEXT        NOT NULL,
    tier        TEXT        NOT NULL,
    granted     BOOLEAN     NOT NULL,
    source      TEXT        NOT NULL DEFAULT 'server',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Fast lookup for audit queries (user_id + created_at compound index)
CREATE INDEX IF NOT EXISTS feature_access_log_user_idx
    ON public.feature_access_log(user_id, created_at DESC);


-- ── 6. HELPER VIEWS ───────────────────────────────────────────────────────────
-- SECURITY FIX: re-created with security_invoker = true.
--
-- The previous version was a standard view evaluated under the view owner's
-- privileges (the postgres superuser), which BYPASSES Row Level Security.
-- Any authenticated user with the anon key could run:
--   SELECT * FROM user_report_summary
-- and receive every tenant's user_id, total_reports, and last_report_at.
--
-- With security_invoker = true, Postgres evaluates the view under the QUERYING
-- user's session. The rca_reports RLS policy "reports_select_own" then naturally
-- restricts results to their own rows — each user sees exactly one row: their own.

CREATE OR REPLACE VIEW public.user_report_summary
    WITH (security_invoker = true)
AS
SELECT
    r.user_id,
    COUNT(*)                                        AS total_reports,
    COUNT(DISTINCT r.dataset_id)                    AS datasets_analysed,
    MAX(r.created_at)                               AS last_report_at,
    COUNT(*) FILTER (WHERE r.created_at >= NOW() - INTERVAL '30 days') AS reports_last_30d
FROM public.rca_reports r
GROUP BY r.user_id;
