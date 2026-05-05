-- MetricSleuth canonical migration delta
-- Aligns semantic memory and analysis run metadata with the current backend.

ALTER TABLE public.analysis_runs
    ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;

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

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'temp-processing',
  'temp-processing',
  false,
  209715200,
  ARRAY['text/csv', 'application/json', 'text/plain', 'application/octet-stream']
)
ON CONFLICT (id) DO NOTHING;

DROP POLICY IF EXISTS "temp_processing_service_role_only" ON storage.objects;
CREATE POLICY "temp_processing_service_role_only"
ON storage.objects FOR ALL
USING (
  bucket_id = 'temp-processing'
  AND auth.role() = 'service_role'
)
WITH CHECK (
  bucket_id = 'temp-processing'
  AND auth.role() = 'service_role'
);

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
