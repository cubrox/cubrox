-- Initial Supabase schema for cubrox (SUPA-2 / #81).
--
-- Translation of alembic/versions/001-007. The `user` and
-- `magic_link_token` tables are intentionally omitted — Supabase's
-- built-in `auth.users` replaces them per SUPA-3 (#82). All
-- user-scoped tables FK to `auth.users(id)` via `owner_id`.
--
-- This migration is ADDITIVE: it creates the new Supabase schema
-- without removing anything on the legacy Neon side. The legacy
-- SQLModels and alembic/ get deleted in SUPA-2b (#87) once SUPA-3
-- swaps the auth layer.
--
-- pgcrypto is pre-installed on Supabase projects; gen_random_uuid()
-- works without an explicit CREATE EXTENSION.

-- ─────────────────────────────────────────────────────────────────
-- Tenant-scoped tables (FK owner_id -> auth.users)
-- ─────────────────────────────────────────────────────────────────

-- passage: user-submitted reading passages (paste or PDF).
-- Translated from alembic 004.
CREATE TABLE public.passage (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id        uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    text            text NOT NULL,
    text_hash       bytea NOT NULL,
    source_type     text NOT NULL,
    source_filename text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT passage_source_type_check CHECK (source_type IN ('paste', 'pdf'))
);

-- Newest-first per-owner listing (reading-history view).
CREATE INDEX ix_passage_owner_id_created_at
    ON public.passage (owner_id, created_at DESC);

-- Content-addressable lookup for cross-user passage de-duplication
-- + comprehension cache key (see comprehension_question_cache below).
CREATE INDEX ix_passage_text_hash
    ON public.passage (text_hash);


-- preference: one row per user, JSON-shaped value bag.
-- Translated from alembic 005. PK changes from user_id to owner_id.
CREATE TABLE public.preference (
    owner_id   uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    values     jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);


-- reading_event: append-only event log for the "100k lines processed"
-- PRD metric. Translated from alembic 007.
CREATE TABLE public.reading_event (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id        uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    passage_id      uuid NOT NULL REFERENCES public.passage(id) ON DELETE CASCADE,
    lines_processed integer NOT NULL,
    occurred_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT reading_event_lines_processed_positive CHECK (lines_processed >= 1)
);

-- Aggregate query for METRIC-3 groups by date.
CREATE INDEX ix_reading_event_occurred_at
    ON public.reading_event (occurred_at);


-- ─────────────────────────────────────────────────────────────────
-- System / cross-user tables (no owner_id; service-role only)
-- ─────────────────────────────────────────────────────────────────

-- comprehension_question_cache: cross-user LLM-output cache keyed
-- on (passage content hash, question type, model, prompt version).
-- Translated from alembic 002. Server-managed only — never written
-- from a user-bound session.
CREATE TABLE public.comprehension_question_cache (
    passage_hash    bytea NOT NULL,
    question_type   text NOT NULL,
    model_id        text NOT NULL,
    prompt_version  integer NOT NULL,
    questions       jsonb NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT comprehension_question_cache_pkey
        PRIMARY KEY (passage_hash, question_type, model_id, prompt_version)
);


-- rate_bucket: per-key token bucket for /login + /auth/verify rate
-- limiting. Translated from alembic 006. System table; the `key`
-- column is opaque (e.g. "login:ip:203.0.113.7").
CREATE TABLE public.rate_bucket (
    key         varchar(255) PRIMARY KEY,
    tokens      double precision NOT NULL,
    refilled_at timestamptz NOT NULL
);


-- todo: workshop demo scaffold (alembic 001). Not user-scoped in the
-- existing schema; carried over for parity until removed in a
-- separate cleanup PR.
CREATE TABLE public.todo (
    id         serial PRIMARY KEY,
    title      varchar(200) NOT NULL,
    done       boolean NOT NULL DEFAULT false,
    created_at timestamp NOT NULL DEFAULT now()
);
