"""Split an over-long document into ordered parts at natural boundaries.

INGEST-3 (#145): a paste or PDF whose text exceeds the per-passage cap is
split into parts so a large document reads as a navigable sequence instead
of being truncated (PDF) or rejected (paste). Splitting prefers paragraph
boundaries (pdfplumber joins pages with blank lines), and hard-cuts a single
paragraph that is itself larger than the target. It never drops or reorders
text: ``"".join(split_into_parts(t)) == t`` for any input.
"""

from __future__ import annotations

import re

# Target size per part. Comfortably under the 100k single-passage render cap
# (each part renders within known-good limits) while keeping the number of
# parts — and Prev/Next clicks — low for a smooth reading flow.
PART_TARGET_CHARS = 80_000

# Hard ceiling on parts, so an absurdly large upload can't create unbounded
# rows. The ingestion caller rejects an upload that would exceed this.
MAX_PARTS = 60

# Split on runs of blank lines, KEEPING the delimiter (capturing group) so the
# pieces concatenate back to the original exactly.
_PARA_SPLIT = re.compile(r"(\n{2,})")


def _boundary_chunks(text: str) -> list[str]:
    """Break `text` into paragraph-sized chunks that concatenate to `text`.

    Each chunk is a paragraph plus the blank-line delimiter that follows it,
    so joining all chunks reproduces the input.
    """
    pieces = _PARA_SPLIT.split(text)  # [para, delim, para, delim, ..., para]
    chunks: list[str] = []
    for i in range(0, len(pieces), 2):
        para = pieces[i]
        delim = pieces[i + 1] if i + 1 < len(pieces) else ""
        chunk = para + delim
        if chunk:
            chunks.append(chunk)
    return chunks


def split_into_parts(text: str, *, target: int = PART_TARGET_CHARS) -> list[str]:
    """Split `text` into parts of at most `target` chars at paragraph
    boundaries.

    Guarantees:
      - ``"".join(result) == text`` — no loss, no reordering, nothing added.
      - every part is at most `target` chars (a single paragraph longer than
        `target` is hard-cut to honor the bound).
      - text at most `target` long returns ``[text]`` unchanged.
    """
    if len(text) <= target:
        return [text]

    parts: list[str] = []
    current = ""

    for chunk in _boundary_chunks(text):
        if len(chunk) > target:
            # A single paragraph bigger than target: flush what we have, then
            # hard-cut it into target-sized slices, keeping the tail in
            # `current` so the next chunk can pack onto it.
            if current:
                parts.append(current)
                current = ""
            for start in range(0, len(chunk), target):
                current = chunk[start : start + target]
                if len(current) == target:
                    parts.append(current)
                    current = ""
            continue

        if len(current) + len(chunk) > target:
            if current:
                parts.append(current)
            current = chunk
        else:
            current += chunk

    if current:
        parts.append(current)
    return parts
