-- Smoke migration to verify Supabase GitHub App preview-branching after 2026-07-01 cubrox → cubrox/masterkey rename.
-- No-op: intentionally empty transaction so no schema changes land if this branch is merged accidentally.
BEGIN;
COMMIT;
