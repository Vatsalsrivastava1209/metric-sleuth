-- MetricSleuth enterprise hardening migration
-- Canonical delta for the durable analysis run model and aligned RLS policies.

CREATE TABLE IF NOT EXISTS public.analysis_runs (
    id              TEXT PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    dataset_id      TEXT,
    metric          TEXT NOT NULL,
    storage_key     TEXT,
    source_type     TEXT NOT NULL DEFAULT 'saved_dataset',
    status          TEXT NOT NULL DEFAULT 'QUEUED'
                     CHECK (status IN ('QUEUED', 'RUNNING', 'SUCCESS', 'FAILURE')),
    status_message  TEXT NOT NULL DEFAULT '',
    progress_meta   JSONB NOT NULL DEFAULT '{}',
    error_message   TEXT,
    report_id       UUID,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS analysis_runs_user_created_idx
    ON public.analysis_runs(user_id, created_at DESC);

ALTER TABLE public.analysis_runs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "analysis_runs_select_own" ON public.analysis_runs;
DROP POLICY IF EXISTS "analysis_runs_insert_own" ON public.analysis_runs;
DROP POLICY IF EXISTS "analysis_runs_update_own" ON public.analysis_runs;

CREATE POLICY "analysis_runs_select_own" ON public.analysis_runs
    FOR SELECT USING (
        COALESCE(auth.uid()::text, current_setting('request.jwt.claim.sub', true)) = user_id::text
    );

CREATE POLICY "analysis_runs_insert_own" ON public.analysis_runs
    FOR INSERT WITH CHECK (
        COALESCE(auth.uid()::text, current_setting('request.jwt.claim.sub', true)) = user_id::text
    );

CREATE POLICY "analysis_runs_update_own" ON public.analysis_runs
    FOR UPDATE USING (
        COALESCE(auth.uid()::text, current_setting('request.jwt.claim.sub', true)) = user_id::text
    );

DO $$
BEGIN
    IF to_regclass('public.user_datasets') IS NOT NULL THEN
        EXECUTE 'DROP POLICY IF EXISTS "Users can view own datasets" ON public.user_datasets';
        EXECUTE 'DROP POLICY IF EXISTS "Users can insert own datasets" ON public.user_datasets';
        EXECUTE 'DROP POLICY IF EXISTS "Users can delete own datasets" ON public.user_datasets';
    END IF;
END $$;
