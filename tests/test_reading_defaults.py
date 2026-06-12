"""Tests for with_defaults — preference merge + legacy width normalization."""

from app.services.reading.defaults import DEFAULT_PREFERENCES, with_defaults


def test_none_returns_defaults() -> None:
    assert with_defaults(None) == DEFAULT_PREFERENCES
    assert with_defaults({}) == DEFAULT_PREFERENCES


def test_default_max_width_is_em_not_ch() -> None:
    # The width fix: defaults use em so the column is consistent across machines.
    assert DEFAULT_PREFERENCES["max_width"].endswith("em")


def test_stored_em_width_passes_through() -> None:
    assert with_defaults({"max_width": "38em"})["max_width"] == "38em"


def test_legacy_ch_width_is_normalized_to_em() -> None:
    """A width stored before the em switch must render as its em equivalent,
    so existing users get the cross-machine-consistent width without re-picking."""
    for ch, em in (("55ch", "28em"), ("65ch", "33em"), ("75ch", "38em"), ("85ch", "43em")):
        assert with_defaults({"max_width": ch})["max_width"] == em


def test_unknown_legacy_ch_width_falls_back_to_default() -> None:
    assert with_defaults({"max_width": "999ch"})["max_width"] == DEFAULT_PREFERENCES["max_width"]


def test_other_keys_still_merge_over_defaults() -> None:
    merged = with_defaults({"size": "24px", "max_width": "65ch"})
    assert merged["size"] == "24px"
    assert merged["max_width"] == "33em"  # legacy ch normalized
    assert merged["font"] == DEFAULT_PREFERENCES["font"]  # untouched key
