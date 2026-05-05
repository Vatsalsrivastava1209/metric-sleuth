BEGIN;

ALTER TABLE public.datasets
    DROP CONSTRAINT IF EXISTS datasets_connector_type_check;

ALTER TABLE public.datasets
    ADD CONSTRAINT datasets_connector_type_check
    CHECK (
        connector_type IN (
            'csv', 'postgres', 'mysql', 'bigquery',
            'shopify', 'ga4', 'meta_ads', 'google_ads', 'klaviyo'
        )
    );

ALTER TABLE public.rca_reports
    ADD COLUMN IF NOT EXISTS report_payload JSONB NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS workflow_status TEXT NOT NULL DEFAULT 'new',
    ADD COLUMN IF NOT EXISTS assigned_owner TEXT DEFAULT '',
    ADD COLUMN IF NOT EXISTS internal_notes TEXT DEFAULT '',
    ADD COLUMN IF NOT EXISTS share_token TEXT,
    ADD COLUMN IF NOT EXISTS share_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_client_delivery_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS delivery_channel TEXT,
    ADD COLUMN IF NOT EXISTS feedback_rating INTEGER,
    ADD COLUMN IF NOT EXISTS feedback_notes TEXT DEFAULT '';

ALTER TABLE public.rca_reports
    DROP CONSTRAINT IF EXISTS rca_reports_workflow_status_check;

ALTER TABLE public.rca_reports
    ADD CONSTRAINT rca_reports_workflow_status_check
    CHECK (workflow_status IN ('new', 'investigating', 'ready_to_send', 'sent'));

ALTER TABLE public.rca_reports
    DROP CONSTRAINT IF EXISTS rca_reports_feedback_rating_check;

ALTER TABLE public.rca_reports
    ADD CONSTRAINT rca_reports_feedback_rating_check
    CHECK (feedback_rating IS NULL OR feedback_rating BETWEEN 1 AND 5);

CREATE UNIQUE INDEX IF NOT EXISTS rca_reports_share_token_idx
    ON public.rca_reports(share_token)
    WHERE share_token IS NOT NULL;

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

ALTER TABLE public.incident_comments ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'incident_comments'
          AND policyname = 'incident_comments_select_own'
    ) THEN
        CREATE POLICY "incident_comments_select_own" ON public.incident_comments
            FOR SELECT USING (auth.uid() = user_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'incident_comments'
          AND policyname = 'incident_comments_insert_own'
    ) THEN
        CREATE POLICY "incident_comments_insert_own" ON public.incident_comments
            FOR INSERT WITH CHECK (auth.uid() = user_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'incident_comments'
          AND policyname = 'incident_comments_delete_own'
    ) THEN
        CREATE POLICY "incident_comments_delete_own" ON public.incident_comments
            FOR DELETE USING (auth.uid() = user_id);
    END IF;
END $$;

COMMIT;
