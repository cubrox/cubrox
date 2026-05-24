"""Tests for the bionic-emphasis text transform.

Covers the Definition of Done from issue #17 (READ-3):
  - bionicize() bolds the first ~half of long alpha-only words
  - Words shorter than MIN_WORD_LEN are not modified
  - Numbers and punctuation are not modified
  - Whitespace and newlines are preserved exactly
  - Function never produces unbalanced HTML tags
  - Adversarial input (literal <, >, &) is escaped before bionicizing
  - The reading view applies the filter ONLY when prefs.bionic_enabled is True
  - The reading view does NOT bionicize when prefs.bionic_enabled is False
"""

import hashlib
import uuid
from datetime import UTC, datetime
from html.parser import HTMLParser

from fastapi.testclient import TestClient
from markupsafe import Markup
from sqlmodel import Session

from app.models.passage import Passage
from app.models.preference import Preference
from app.services.reading.bionic import MAX_BOLD_CHARS, MIN_WORD_LEN, bionicize
from tests.conftest import signed_in

# ---------------------------------------------------------------------------
# Unit tests on bionicize() directly
# ---------------------------------------------------------------------------


def test_returns_markup_so_jinja_doesnt_double_escape() -> None:
    """The function returns markupsafe.Markup so the deliberate <b> tags
    we emit aren't escaped again when Jinja renders the template.
    Without this, the user would see literal '<b>' text on screen."""
    result = bionicize("hello world")
    assert isinstance(result, Markup)


def test_bolds_first_half_of_long_word() -> None:
    """The classic case: a long word gets the first ceil(len/2) chars
    bolded, capped at MAX_BOLD_CHARS."""
    result = str(bionicize("understanding"))
    # 13 chars → ceil(13/2) = 7, capped at MAX_BOLD_CHARS (6).
    assert "<b>unders</b>tanding" == result


def test_short_words_pass_through_unchanged() -> None:
    """Words shorter than MIN_WORD_LEN don't get bolded — short words
    gain no benefit and the noise hurts more than it helps."""
    assert MIN_WORD_LEN == 4  # sanity-pin the constant
    result = str(bionicize("the cat sat on a mat"))
    assert result == "the cat sat on a mat"
    assert "<b>" not in result


def test_word_at_exact_minimum_length_gets_bolded() -> None:
    """The boundary case: a 4-char word IS bolded (>=, not >)."""
    result = str(bionicize("test"))
    # 4 chars → ceil(4/2) = 2 bolded.
    assert result == "<b>te</b>st"


def test_word_just_under_minimum_does_not_get_bolded() -> None:
    """The other side of the boundary: 3-char words are not bolded."""
    result = str(bionicize("cat"))
    assert result == "cat"
    assert "<b>" not in result


def test_very_long_word_caps_at_MAX_BOLD_CHARS() -> None:
    """An especially long word doesn't get nearly-all of itself
    bolded — the bold count tops out at MAX_BOLD_CHARS so there's
    always a sensible 'tail' for the eye to scan into."""
    assert MAX_BOLD_CHARS == 6  # sanity-pin
    word = "a" * 20
    result = str(bionicize(word))
    # Expect 6 'a's inside <b>, then 14 'a's outside.
    assert result == f"<b>{'a' * 6}</b>{'a' * 14}"


def test_numbers_are_not_bolded() -> None:
    result = str(bionicize("1234"))
    assert result == "1234"
    assert "<b>" not in result


def test_punctuation_only_tokens_are_not_bolded() -> None:
    result = str(bionicize("... !! ??"))
    assert result == "... !! ??"
    assert "<b>" not in result


def test_alphanumeric_tokens_are_not_bolded() -> None:
    """Identifiers like `var123` mix letters and digits — token.isalpha()
    is False, so they pass through. Avoids bolding code-like content
    where the visual emphasis is misleading."""
    result = str(bionicize("var123 word456"))
    assert "<b>" not in result


def test_preserves_single_space_whitespace() -> None:
    result = str(bionicize("understanding the world"))
    assert "understanding the world" not in result  # was bionicized
    # But the spaces are intact.
    assert " the " in result  # short word with surrounding spaces


def test_preserves_newlines_and_paragraph_breaks() -> None:
    """Whitespace structure (\\n, \\n\\n) survives the transform —
    the reading surface uses white-space: pre-wrap so these matter."""
    text = "first\nsecond\n\nthird"
    result = str(bionicize(text))
    assert "\n" in result
    assert "\n\n" in result
    # Each long word ('first', 'second', 'third' — all 5+ chars) bionicized
    assert "<b>" in result


def test_preserves_leading_and_trailing_whitespace() -> None:
    text = "  hello  "
    result = str(bionicize(text))
    assert result.startswith("  ")
    assert result.endswith("  ")


def test_balanced_html_tags_via_html_parser() -> None:
    """No unbalanced tags. Use stdlib HTMLParser to walk the output —
    it would raise on malformed HTML in modern Python."""

    class TagCounter(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.depth = 0
            self.max_depth = 0

        def handle_starttag(self, tag: str, attrs: object) -> None:  # type: ignore[override]
            self.depth += 1
            self.max_depth = max(self.max_depth, self.depth)

        def handle_endtag(self, tag: str) -> None:
            self.depth -= 1

    parser = TagCounter()
    output = str(bionicize("understanding the natural world of words"))
    parser.feed(output)
    parser.close()
    # Balanced means depth is 0 at end. <b> tags don't nest, so max_depth=1.
    assert parser.depth == 0
    assert parser.max_depth == 1


def test_adversarial_html_is_escaped_not_executed() -> None:
    """Critical security property: a passage containing literal `<` and
    `>` is escaped BEFORE the bionic <b> tags are inserted. The user's
    `<script>` text never becomes a live HTML element. The angle
    brackets escape independently from the bionic transform of the
    word 'script' between them."""
    text = "<script>alert(1)</script>"
    result = str(bionicize(text))
    # The user's `<script>` literal must NOT appear as a real tag.
    assert "<script>" not in result
    # The angle brackets are escaped.
    assert "&lt;" in result
    assert "&gt;" in result
    # The word 'script' (6 chars) gets bionicized, inside the escaped
    # brackets. The combined output is &lt;<b>scr</b>ipt&gt; — visible
    # to the user as text reading "<script>" with "scr" bolded, never
    # an executable script tag.
    assert "<b>scr</b>ipt" in result
    # alert(1) similarly: 'alert' bionicizes; the parens are escaped to
    # themselves (parens aren't special in HTML).
    assert "<b>ale</b>rt" in result


def test_empty_string_returns_empty_markup() -> None:
    result = bionicize("")
    assert str(result) == ""


def test_unicode_letters_handled() -> None:
    """The token regex uses re.UNICODE so non-ASCII letters are
    recognized as word chars and bionicized correctly."""
    # 'naïve' has 5 chars (one with diaeresis); should bold first 3.
    result = str(bionicize("naïve"))
    assert result == "<b>naï</b>ve"


def test_amp_in_user_text_is_escaped() -> None:
    """Beyond `<` and `>`, the ampersand also needs to be escaped to
    prevent HTML entity confusion (e.g., `&lt;` typed literally by the
    user shouldn't render as a `<` after our pass)."""
    text = "rock & roll"  # 'rock' is 4 chars → bionicized; & is escaped
    result = str(bionicize(text))
    assert "&amp;" in result
    assert "<b>ro</b>ck" in result


# ---------------------------------------------------------------------------
# Integration tests: the reading view applies the filter conditionally
# ---------------------------------------------------------------------------


def _make_passage(session: Session, user_id: uuid.UUID, text: str) -> Passage:
    p = Passage(
        user_id=user_id,
        text=text,
        text_hash=hashlib.sha256(text.encode("utf-8")).digest(),
        source_type="paste",
        source_filename=None,
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def test_reading_view_does_not_bionicize_when_disabled(
    client: TestClient, session: Session
) -> None:
    """Default is bionic_enabled=False; reading view shows raw text."""
    user = signed_in(session)
    passage = _make_passage(session, user.id, "understanding the natural world")

    response = client.get(f"/read/{passage.id}")
    body = response.text

    # Raw text appears verbatim inside the article.
    assert "understanding the natural world" in body
    # The bionic <b> markers are NOT in the article body.
    # (Note: <b> tags might appear in OTHER parts of the page — sidebar,
    # for example — so we scope the check to the article element.)
    article_start = body.find('<article id="reading-surface">')
    article_end = body.find("</article>", article_start)
    article_body = body[article_start:article_end]
    assert "<b>" not in article_body


def test_reading_view_bionicizes_when_enabled(client: TestClient, session: Session) -> None:
    """User with bionic_enabled=True gets the article's text bionicized."""
    user = signed_in(session)
    passage = _make_passage(session, user.id, "understanding the natural world")

    session.add(
        Preference(
            user_id=user.id,
            values={"bionic_enabled": True},
            updated_at=datetime.now(UTC),
        )
    )
    session.commit()

    response = client.get(f"/read/{passage.id}")
    body = response.text

    # The article body now contains <b> wraps.
    article_start = body.find('<article id="reading-surface">')
    article_end = body.find("</article>", article_start)
    article_body = body[article_start:article_end]
    assert "<b>" in article_body
    # The unbionicized raw form is NOT a substring (the long words
    # have <b> markers in the middle now).
    assert "understanding " not in article_body
    # But the visible text ('the' is short, passes through) is still readable.
    assert " the " in article_body


def test_reading_view_with_bionic_does_not_render_user_html_as_tags(
    client: TestClient, session: Session
) -> None:
    """End-to-end XSS check: with bionic enabled, a passage containing
    `<script>` is still rendered as escaped text. The bionic transform
    never bypasses Jinja's auto-escape for user content."""
    user = signed_in(session)
    passage = _make_passage(session, user.id, "<script>alert(1)</script>")

    session.add(
        Preference(
            user_id=user.id,
            values={"bionic_enabled": True},
            updated_at=datetime.now(UTC),
        )
    )
    session.commit()

    response = client.get(f"/read/{passage.id}")
    article_start = response.text.find('<article id="reading-surface">')
    article_end = response.text.find("</article>", article_start)
    article_body = response.text[article_start:article_end]

    # The user's `<script>` tag does NOT render as a real script element
    # inside the article. The angle brackets escape; the word 'script'
    # gets bionicized between them.
    assert "<script>" not in article_body
    # The escaped angle brackets are present.
    assert "&lt;" in article_body
    assert "&gt;" in article_body
    # The word 'script' is bionicized but rendered as visible text,
    # never as an executing tag.
    assert "<b>scr</b>ipt" in article_body
