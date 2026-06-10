"""Tests for the document-splitting service (INGEST-3 #145).

The load-bearing invariant: splitting never loses, reorders, or adds text —
joining the parts reproduces the input exactly — and every part respects the
size bound.
"""

from app.services.ingestion.split import (
    MAX_PARTS,
    PART_TARGET_CHARS,
    split_into_parts,
)


def _assert_lossless(text: str, target: int) -> list[str]:
    parts = split_into_parts(text, target=target)
    assert "".join(parts) == text, "splitting must not lose or reorder text"
    assert all(len(p) <= target for p in parts), "every part must respect the target bound"
    return parts


def test_short_text_returns_single_part_unchanged() -> None:
    assert split_into_parts("hello world", target=80_000) == ["hello world"]


def test_text_at_target_is_not_split() -> None:
    text = "a" * 80_000
    assert split_into_parts(text, target=80_000) == [text]


def test_packs_paragraphs_to_boundaries_without_splitting_them() -> None:
    # Six ~30k paragraphs → packs two per ~80k part (a third would overflow).
    para = "A" * 30_000 + "\n\n"
    parts = _assert_lossless(para * 6, 80_000)
    assert len(parts) == 3
    # Each part is whole paragraphs (ends on the blank-line delimiter).
    assert all(p.endswith("\n\n") for p in parts)


def test_single_paragraph_larger_than_target_is_hard_cut() -> None:
    parts = _assert_lossless("X" * 250_000, 80_000)
    assert [len(p) for p in parts] == [80_000, 80_000, 80_000, 10_000]


def test_mixed_giant_then_small_paragraphs() -> None:
    text = "X" * 200_000 + "\n\n" + "Y" * 10_000 + "\n\n" + "Z" * 10_000
    parts = _assert_lossless(text, 80_000)
    assert len(parts) >= 3


def test_exact_multiple_of_target() -> None:
    parts = _assert_lossless("Q" * 160_000, 80_000)
    assert [len(p) for p in parts] == [80_000, 80_000]


def test_max_parts_is_a_sane_ceiling() -> None:
    # Sanity on the exported constants the ingestion caller enforces.
    assert PART_TARGET_CHARS > 0
    assert MAX_PARTS >= 2
