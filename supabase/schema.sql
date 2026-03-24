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
    llm_backend         TEXT DEFAULT 'gemini',          -- 'gemini' | 'openai'
    llm_api_key         TEXT DEFAULT '',               -- stored encrypted via Supabase Vault in prod
    slack_webhook_url   TEXT DEFAULT '',
    alert_email         TEXT DEFAULT '',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

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
                     CHECK (connector_type IN ('csv', 'postgres', 'mysql', 'bigquery')),
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
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast report lookups
CREATE INDEX IF NOT EXISTS rca_reports_user_id_idx   ON public.rca_reports(user_id);
CREATE INDEX IF NOT EXISTS rca_reports_dataset_id_idx ON public.rca_reports(dataset_id);


-- ── 4. ROW LEVEL SECURITY ─────────────────────────────────────────────────────
-- All tables already have RLS enabled (via project-level auto-RLS setting).
-- These policies ensure users only see their own data.

-- profiles: users can only read/update their own profile
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


-- ── 5. HELPER VIEWS ───────────────────────────────────────────────────────────
-- Convenience view for the dashboard: user's report summary

CREATE OR REPLACE VIEW public.user_report_summary AS
SELECT
    r.user_id,
    COUNT(*)                                        AS total_reports,
    COUNT(DISTINCT r.dataset_id)                    AS datasets_analysed,
    MAX(r.created_at)                               AS last_report_at,
    COUNT(*) FILTER (WHERE r.created_at >= NOW() - INTERVAL '30 days') AS reports_last_30d
FROM public.rca_reports r
GROUP BY r.user_id;
