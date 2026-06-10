-- INGEST-3 (#145): auto-split large documents into navigable parts.
--
-- Additive columns. A standalone passage keeps document_id=NULL,
-- part_index=0, part_count=1 (unchanged behavior). A document split into N
-- parts shares one document_id with part_index 0..N-1 and part_count=N.
-- The index serves the reading view's sibling lookup
-- (WHERE document_id = ? ORDER BY part_index).
--
-- IF NOT EXISTS keeps this idempotent across re-applies / per-PR branches.
ALTER TABLE public.passage
    ADD COLUMN IF NOT EXISTS document_id uuid,
    ADD COLUMN IF NOT EXISTS part_index integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS part_count integer NOT NULL DEFAULT 1;

CREATE INDEX IF NOT EXISTS ix_passage_document_id_part_index
    ON public.passage (document_id, part_index);
