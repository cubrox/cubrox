-- ANALYTICS-1 (#166): capture the reader's active preferences on each event.
--
-- Additive, nullable JSONB column. Existing rows keep NULL (no backfill) —
-- a NULL snapshot means "the user had no preference row at event time", i.e.
-- all defaults. The write path (POST /passages/{id}/close) populates it from
-- the user's `preference.values` blob; ANALYTICS-2 reads it for
-- mode-correlation analysis.
--
-- JSONB (not JSON) to match `preference.values` and to keep the door open for
-- containment/GIN queries in the dashboard without a follow-up migration.
--
-- IF NOT EXISTS keeps the migration idempotent across re-applies and per-PR
-- Supabase branches. The reading_event RLS policy (owner_id = auth.uid())
-- already covers this column — no policy change needed.
ALTER TABLE public.reading_event
    ADD COLUMN IF NOT EXISTS preferences_snapshot jsonb DEFAULT NULL;
