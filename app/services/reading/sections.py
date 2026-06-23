"""Split a passage into N roughly-equal sections for interleaved comprehension.

The reading view shows one comprehension question after each section, so the
reader reflects on each chunk of text before moving to the next. Sections are
split at paragraph boundaries (same strategy as INGEST-3's split_into_parts)
so a question never interrupts mid-paragraph.
"""

from __future__ import annotations

from app.services.ingestion.split import _boundary_chunks

_DEFAULT_N = 3


def split_into_sections(text: str, n: int = _DEFAULT_N) -> list[str]:
    """Split `text` into exactly `n` sections at paragraph boundaries.

    Sections are roughly equal in length (by character count). For very short
    texts with fewer than `n` paragraphs, trailing sections are empty strings.
    Always returns a list of exactly `n` strings.
    """
    if n <= 0:
        raise ValueError(f"n must be positive, got {n!r}")

    chunks = _boundary_chunks(text)
    if not chunks:
        return [""] * n

    target = max(1, len(text) // n)
    sections: list[str] = []
    current = ""

    for chunk in chunks:
        if current and len(current) >= target and len(sections) < n - 1:
            sections.append(current)
            current = chunk
        else:
            current += chunk

    sections.append(current)

    while len(sections) < n:
        sections.append("")

    return sections[:n]
