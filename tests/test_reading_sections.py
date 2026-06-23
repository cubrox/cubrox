"""Tests for split_into_sections — passage splitting for interleaved comprehension."""

from app.services.reading.sections import split_into_sections


def test_returns_exactly_n_sections() -> None:
    text = "Para one.\n\nPara two.\n\nPara three.\n\nPara four.\n\nPara five.\n\nPara six."
    result = split_into_sections(text, n=3)
    assert len(result) == 3


def test_sections_concatenate_to_original() -> None:
    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph.\n\nFourth."
    result = split_into_sections(text, n=3)
    assert "".join(result) == text


def test_single_paragraph_pads_with_empty_strings() -> None:
    text = "Just one paragraph with no breaks."
    result = split_into_sections(text, n=3)
    assert len(result) == 3
    assert result[0] == text
    assert result[1] == ""
    assert result[2] == ""


def test_empty_text_returns_n_empty_strings() -> None:
    result = split_into_sections("", n=3)
    assert result == ["", "", ""]


def test_two_paragraphs_n3_pads_last() -> None:
    text = "Para A.\n\nPara B."
    result = split_into_sections(text, n=3)
    assert len(result) == 3
    assert result[2] == ""
    assert "".join(result) == text


def test_n1_returns_full_text_as_one_section() -> None:
    text = "Alpha.\n\nBeta.\n\nGamma."
    result = split_into_sections(text, n=1)
    assert result == [text]


def test_large_text_splits_into_roughly_equal_thirds() -> None:
    # 6 equal-length paragraphs → each section should get ~2
    para = "X" * 100
    text = "\n\n".join([para] * 6)
    result = split_into_sections(text, n=3)
    assert len(result) == 3
    # No section should be more than 3x the size of the smallest non-empty one
    non_empty = [len(s) for s in result if s]
    assert max(non_empty) <= 3 * min(non_empty)
