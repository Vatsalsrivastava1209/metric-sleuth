BEGIN;

ALTER TABLE public.analysis_runs
    RENAME COLUMN dataset_id TO legacy_dataset_ref;

ALTER TABLE public.analysis_runs
    ADD COLUMN IF NOT EXISTS dataset_id UUID REFERENCES public.datasets(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS source_label TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS dead_lettered_at TIMESTAMPTZ;

UPDATE public.analysis_runs
SET dataset_id = legacy_dataset_ref::uuid
WHERE legacy_dataset_ref ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$';

UPDATE public.analysis_runs
SET source_label = legacy_dataset_ref
WHERE legacy_dataset_ref IS NOT NULL
  AND legacy_dataset_ref <> ''
  AND (
    legacy_dataset_ref !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
    OR source_type <> 'saved_dataset'
  );

ALTER TABLE public.analysis_runs
    DROP COLUMN legacy_dataset_ref;

ALTER TABLE public.rca_reports
    ADD COLUMN IF NOT EXISTS share_created_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS share_created_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS share_last_accessed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS share_revoked_at TIMESTAMPTZ;

COMMIT;
