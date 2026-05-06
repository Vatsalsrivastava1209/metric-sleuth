-- =============================================================================
-- Migration: 20260507_stripe_idempotency_table.sql
-- Purpose  : Create the stripe_processed_events table referenced by
--            api/routers/webhooks.py for idempotency-safe event processing.
--
-- Background
-- ----------
-- Stripe guarantees at-least-once delivery. The webhook handler inserts the
-- event_id here before performing any DB writes. On a duplicate delivery the
-- UNIQUE constraint fires (Postgres error 23505), which the webhook handler
-- detects and returns 200 immediately — halting Stripe's retry loop.
--
-- Without this table the `except` clause in webhooks.py swallows the insert
-- error and proceeds, meaning a duplicate event causes a double-upgrade or
-- double-downgrade of the user's subscription tier (billing integrity failure).
--
-- Security
-- --------
-- Only the service_role (used by the FastAPI webhook router) may write to this
-- table. No user-facing policy is needed because no end-user ever touches it.
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.stripe_processed_events (
    event_id      TEXT        PRIMARY KEY,        -- Stripe event ID (e.g. "evt_...")
    event_type    TEXT        NOT NULL,           -- e.g. "checkout.session.completed"
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Fast range-query for ops dashboards (e.g. "how many events in the last hour")
CREATE INDEX IF NOT EXISTS stripe_events_processed_at_idx
    ON public.stripe_processed_events (processed_at DESC);

-- ── Row Level Security ────────────────────────────────────────────────────────
-- Enable RLS so that authenticated users (anon key) cannot read or modify
-- billing audit records. Only service_role (the webhook server) may access
-- this table.

ALTER TABLE public.stripe_processed_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "stripe_events_service_role_only"
    ON public.stripe_processed_events
    FOR ALL
    USING  (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- ── Optional: auto-purge events older than 90 days ───────────────────────────
-- Stripe only retries for ~72 hours, so events older than 90 days will never
-- arrive again. This cron expression requires pg_cron to be enabled in the
-- Supabase Dashboard → Database → Extensions → pg_cron.
-- Uncomment once pg_cron is available in your project:
--
-- SELECT cron.schedule(
--     'purge-old-stripe-events',
--     '0 3 * * *',   -- daily at 03:00 UTC
--     $$DELETE FROM public.stripe_processed_events WHERE processed_at < NOW() - INTERVAL '90 days'$$
-- );
