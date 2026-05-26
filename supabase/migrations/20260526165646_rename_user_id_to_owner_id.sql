-- Idempotent rename of `user_id` → `owner_id` on tenant-scoped tables (BUG-4 / #105).
--
-- Background: the production Supabase Postgres was data-migrated from
-- the old alembic-era Neon database, which used the column name
-- `user_id`. The SUPA-2c rename (`user_id` → `owner_id`) was applied to
-- the SQLModel definitions + the supabase/migrations/*.sql files
-- (which use `owner_id` from their initial state), but the production
-- database itself was never realigned. Surface symptom: paste fails
-- with `psycopg.errors.UndefinedColumn: column "owner_id" of relation
-- "passage" does not exist` after the #104 type-coercion fix moved
-- past the previous crash. See #105.
--
-- This migration is IDEMPOTENT:
--   - On production (still has `user_id`): does the rename.
--   - On local Supabase / per-PR branches (already `owner_id`): no-op.
--   - Re-running is safe.
--
-- Why IF EXISTS in every branch: the initial_schema migration already
-- creates the column as `owner_id` for fresh databases, so the IF
-- EXISTS guards make this migration land cleanly regardless of whether
-- a given database was bootstrapped from the alembic-era schema or
-- from a fresh `supabase db push`.

DO $$
BEGIN
    -- passage.user_id → owner_id
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'passage'
          AND column_name  = 'user_id'
    ) THEN
        ALTER TABLE public.passage RENAME COLUMN user_id TO owner_id;
    END IF;

    -- preference.user_id → owner_id  (also the primary key — the rename
    -- automatically renames the implicit PK constraint).
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'preference'
          AND column_name  = 'user_id'
    ) THEN
        ALTER TABLE public.preference RENAME COLUMN user_id TO owner_id;
    END IF;

    -- reading_event.user_id → owner_id
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'reading_event'
          AND column_name  = 'user_id'
    ) THEN
        ALTER TABLE public.reading_event RENAME COLUMN user_id TO owner_id;
    END IF;
END $$;

-- Rename indexes that reference the old column name.
-- (Postgres preserves the index logically when a column is renamed,
-- but the INDEX NAME stays as it was, so we rename for grep-ability.
-- The composite indexes were defined in the alembic-era migrations as
-- `ix_<table>_user_id_created_at`; rename to match the supabase-era
-- `ix_<table>_owner_id_created_at` shape.)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public'
          AND indexname  = 'ix_passage_user_id_created_at'
    ) THEN
        ALTER INDEX public.ix_passage_user_id_created_at
            RENAME TO ix_passage_owner_id_created_at;
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public'
          AND indexname  = 'ix_reading_event_user_id_created_at'
    ) THEN
        ALTER INDEX public.ix_reading_event_user_id_created_at
            RENAME TO ix_reading_event_owner_id_created_at;
    END IF;
END $$;

-- FK constraint cleanup + recreate.
--
-- We need to handle three FK relationships across these three tables:
--   * passage.owner_id        → auth.users(id)
--   * preference.owner_id     → auth.users(id)
--   * reading_event.owner_id  → auth.users(id)
--   * reading_event.passage_id → public.passage(id)   (NOT touched by the rename)
--
-- The alembic-era FKs pointed at `public.user(id)` (now-deleted) for
-- the owner side. The supabase-era FKs point at `auth.users(id)`. So
-- we drop ONLY the owner-side FKs (whether they reference public.user
-- or auth.users) and re-add them against auth.users. The passage_id
-- FK is left alone — its target (public.passage) exists in both eras
-- and the rename doesn't touch it.
--
-- The DROP loop is narrowed to FKs whose target is `auth.users` or
-- `public.user` to avoid silently dropping unrelated FKs (most
-- importantly `reading_event.passage_id_fkey`, which the supabase-era
-- schema needs preserved). See #106 review.
--
-- We use `NOT VALID` on the auth.users FKs and a follow-up
-- `VALIDATE CONSTRAINT` step. This is the standard Postgres pattern
-- for adding an FK to a table that may have rows whose foreign-key
-- values predate the constraint (e.g., orphan owner_id UUIDs left
-- behind by the alembic→Supabase data migration). With `NOT VALID`:
--   * The constraint is recorded in the catalog.
--   * Future INSERT / UPDATE rows are enforced normally.
--   * Existing rows are NOT validated yet, so the migration won't
--     abort mid-transaction if any orphan exists.
-- After the migration runs cleanly, the operator can validate by
-- running `ALTER TABLE ... VALIDATE CONSTRAINT ...` once they've
-- confirmed (or cleaned up) any orphans. See PR #106 body.
DO $$
DECLARE
    fk_record RECORD;
BEGIN
    FOR fk_record IN
        SELECT con.conname,
               con.conrelid::regclass AS table_name
        FROM pg_constraint con
        JOIN pg_class target ON target.oid = con.confrelid
        JOIN pg_namespace ns ON ns.oid = target.relnamespace
        WHERE con.contype = 'f'
          AND con.conrelid IN (
              'public.passage'::regclass,
              'public.preference'::regclass,
              'public.reading_event'::regclass
          )
          AND ns.nspname || '.' || target.relname IN ('auth.users', 'public.user')
    LOOP
        EXECUTE format(
            'ALTER TABLE %s DROP CONSTRAINT IF EXISTS %I',
            fk_record.table_name, fk_record.conname
        );
    END LOOP;
END $$;

-- Re-add the owner-side FKs as NOT VALID so the migration doesn't abort
-- on any pre-existing orphan rows in production.
ALTER TABLE public.passage
    ADD CONSTRAINT passage_owner_id_fkey
        FOREIGN KEY (owner_id) REFERENCES auth.users(id) ON DELETE CASCADE
        NOT VALID;

ALTER TABLE public.preference
    ADD CONSTRAINT preference_owner_id_fkey
        FOREIGN KEY (owner_id) REFERENCES auth.users(id) ON DELETE CASCADE
        NOT VALID;

ALTER TABLE public.reading_event
    ADD CONSTRAINT reading_event_owner_id_fkey
        FOREIGN KEY (owner_id) REFERENCES auth.users(id) ON DELETE CASCADE
        NOT VALID;

-- Ensure `reading_event.passage_id_fkey` is present and shaped per the
-- supabase-era initial_schema. The alembic-era version had the same
-- target (public.passage) and shape (ON DELETE CASCADE), so on prod
-- this is a no-op IF the FK already exists with the right shape — and
-- a safety-net if a previous version of this file (which had a
-- too-aggressive DROP loop) accidentally removed it. See #106 review.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint con
        JOIN pg_class target ON target.oid = con.confrelid
        WHERE con.contype = 'f'
          AND con.conrelid = 'public.reading_event'::regclass
          AND target.relname = 'passage'
    ) THEN
        ALTER TABLE public.reading_event
            ADD CONSTRAINT reading_event_passage_id_fkey
                FOREIGN KEY (passage_id) REFERENCES public.passage(id) ON DELETE CASCADE;
    END IF;
END $$;
