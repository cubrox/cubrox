"""Tests for header/footer cropping in PDF extraction (INGEST-P2-1 #169).

pdfplumber pulls every line on a page, including running page headers
(titles, chapter names) and footers (page numbers, copyright lines) that
interrupt sentence flow on the reading surface. `extract_text` now crops the
top HEADER_MARGIN_FRACTION and bottom FOOTER_MARGIN_FRACTION off each page
before extracting.

These tests build synthetic PDFs with `reportlab` (a test-only dependency)
so text can be placed at exact y-coordinates: in the header band, the footer
band, or the body.
"""

import io

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from app.services.ingestion.pdf import (
    FOOTER_MARGIN_FRACTION,
    HEADER_MARGIN_FRACTION,
    extract_text,
)

_WIDTH, _HEIGHT = letter  # 612 x 792 pt


def _pdf(pages: list[dict[str, str]]) -> bytes:
    """Build a PDF from a list of pages.

    Each page dict may set `header`, `body`, and `footer` text. reportlab's
    origin is the BOTTOM-left, so a high y is near the top of the page.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    for page in pages:
        if header := page.get("header"):
            # ~2% from the top -> inside the 8% header band.
            c.drawString(72, _HEIGHT * 0.98, header)
        if body := page.get("body"):
            # Middle of the page -> safely inside the body band.
            c.drawString(72, _HEIGHT * 0.5, body)
        if footer := page.get("footer"):
            # ~2% from the bottom -> inside the 8% footer band.
            c.drawString(72, _HEIGHT * 0.02, footer)
        c.showPage()
    c.save()
    return buf.getvalue()


def test_header_and_footer_are_cropped_out() -> None:
    """The DoD case: a two-page PDF with a header on page 1 and a footer on
    page 2. After extraction neither the header nor footer text appears, but
    the body of both pages does."""
    pdf = _pdf(
        [
            {"header": "The Kitab-i-Iqan Chapter 3", "body": "Page one body sentence."},
            {"footer": "Copyright Bahai Publishing Trust 1978", "body": "Page two body sentence."},
        ]
    )

    text = extract_text(pdf)

    assert "Page one body sentence." in text
    assert "Page two body sentence." in text
    assert "Kitab-i-Iqan" not in text
    assert "Copyright" not in text


def test_footer_page_numbers_are_removed() -> None:
    """Running footers (page numbers) on every page are stripped."""
    pdf = _pdf(
        [
            {"body": "First chapter opening.", "footer": "- 47 -"},
            {"body": "The chapter continues here.", "footer": "- 48 -"},
        ]
    )

    text = extract_text(pdf)

    assert "First chapter opening." in text
    assert "The chapter continues here." in text
    assert "- 47 -" not in text
    assert "- 48 -" not in text


def test_body_only_pdf_is_unchanged_by_cropping() -> None:
    """DoD: a PDF with no header/footer content returns the same body text —
    cropping blank margins must not remove content."""
    pdf = _pdf(
        [
            {"body": "Only body text on page one."},
            {"body": "Only body text on page two."},
        ]
    )

    text = extract_text(pdf)

    assert "Only body text on page one." in text
    assert "Only body text on page two." in text


def test_body_spanning_multiple_lines_survives() -> None:
    """A fuller body block (not just one line) round-trips intact — guards
    against the crop being too aggressive on a realistically dense page."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    lines = [f"Body line number {i} of the passage." for i in range(1, 15)]
    y = _HEIGHT * 0.85  # starts below the 8% header band
    c.drawString(72, _HEIGHT * 0.97, "RUNNING HEADER TO DROP")
    for line in lines:
        c.drawString(72, y, line)
        y -= 24
    c.drawString(72, _HEIGHT * 0.02, "footer 1")
    c.showPage()
    c.save()

    text = extract_text(buf.getvalue())

    for line in lines:
        assert line in text
    assert "RUNNING HEADER TO DROP" not in text
    assert "footer 1" not in text


def test_margin_fractions_are_module_constants() -> None:
    """DoD: the crop fractions are tunable module-level constants."""
    assert 0 < HEADER_MARGIN_FRACTION < 0.5
    assert 0 < FOOTER_MARGIN_FRACTION < 0.5
