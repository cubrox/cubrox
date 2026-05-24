-- Row-Level Security policies for the cubrox schema (SUPA-2 / #81).
--
-- Threat model: the anon key is published in client code. Any
-- authenticated session calling the Data API gets the `authenticated`
-- role and bears a JWT whose `sub` claim Supabase exposes as
-- `auth.uid()`. RLS is the only thing standing between User A and
-- User B's data.
--
-- Per Supabase guidance, every table in the `public` schema has RLS
-- enabled. Tables that don't have a user-scoped access model
-- (caches, system tables, scaffold) get RLS turned on with NO
-- authenticated/anon policies — they remain accessible only via the
-- service role, which bypasses RLS.

-- ─────────────────────────────────────────────────────────────────
-- Enable RLS on every table
-- ─────────────────────────────────────────────────────────────────

ALTER TABLE public.passage                       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.preference                    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reading_event                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.comprehension_question_cache  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rate_bucket                   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.todo                          ENABLE ROW LEVEL SECURITY;


-- ─────────────────────────────────────────────────────────────────
-- passage — owner can do anything to own rows
-- ─────────────────────────────────────────────────────────────────

CREATE POLICY "owner can select own passages"
    ON public.passage FOR SELECT
    TO authenticated
    USING (owner_id = auth.uid());

CREATE POLICY "owner can insert own passages"
    ON public.passage FOR INSERT
    TO authenticated
    WITH CHECK (owner_id = auth.uid());

-- UPDATE needs USING (read row) + WITH CHECK (write row). Per
-- Supabase guidance: without USING, an UPDATE silently affects 0 rows.
CREATE POLICY "owner can update own passages"
    ON public.passage FOR UPDATE
    TO authenticated
    USING (owner_id = auth.uid())
    WITH CHECK (owner_id = auth.uid());

CREATE POLICY "owner can delete own passages"
    ON public.passage FOR DELETE
    TO authenticated
    USING (owner_id = auth.uid());


-- ─────────────────────────────────────────────────────────────────
-- preference — owner can do anything to own row (one row per user)
-- ─────────────────────────────────────────────────────────────────

CREATE POLICY "owner can select own preference"
    ON public.preference FOR SELECT
    TO authenticated
    USING (owner_id = auth.uid());

CREATE POLICY "owner can insert own preference"
    ON public.preference FOR INSERT
    TO authenticated
    WITH CHECK (owner_id = auth.uid());

CREATE POLICY "owner can update own preference"
    ON public.preference FOR UPDATE
    TO authenticated
    USING (owner_id = auth.uid())
    WITH CHECK (owner_id = auth.uid());

CREATE POLICY "owner can delete own preference"
    ON public.preference FOR DELETE
    TO authenticated
    USING (owner_id = auth.uid());


-- ─────────────────────────────────────────────────────────────────
-- reading_event — append-only domain; no UPDATE/DELETE policies on
-- purpose. Owner can insert + select own events. The app's METRIC-3
-- aggregate runs as the service role (cross-user date rollup).
-- ─────────────────────────────────────────────────────────────────

CREATE POLICY "owner can select own reading events"
    ON public.reading_event FOR SELECT
    TO authenticated
    USING (owner_id = auth.uid());

CREATE POLICY "owner can insert own reading events"
    ON public.reading_event FOR INSERT
    TO authenticated
    WITH CHECK (owner_id = auth.uid());


-- ─────────────────────────────────────────────────────────────────
-- Service-role-only tables: RLS enabled, NO authenticated/anon
-- policies. Reachable only via the service role (bypasses RLS).
-- ─────────────────────────────────────────────────────────────────

-- comprehension_question_cache: server-side cache, no user-bound access
-- rate_bucket: system token bucket, no user-bound access
-- todo: workshop scaffold, no access until removed
