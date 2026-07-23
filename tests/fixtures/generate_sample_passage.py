"""Regenerate tests/fixtures/sample_passage.pdf.

Run: `uv run python tests/fixtures/generate_sample_passage.py`

This is a two-page PDF representing a realistically-margined book page: body
text sits in the vertical middle, with a running header and a page-number
footer in the top/bottom margins. It exercises the PDF ingestion pipeline
end-to-end (test_passages_pdf.py) AND the header/footer crop (#169) — the
header and footer land in the cropped bands and must NOT survive extraction,
while the body markers ("O Son of Spirit!", "Second page") must.

The previous fixture placed body text flush against the page edges, which is
not how real documents are laid out; it broke once header/footer cropping
landed. reportlab is a test-only dependency.
"""

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

_WIDTH, _HEIGHT = letter  # 612 x 792 pt; reportlab origin is bottom-left.
OUT = Path(__file__).parent / "sample_passage.pdf"

# Page 1: header (drop), body markers (keep), footer (drop).
PAGE1_BODY = [
    "O Son of Spirit!",
    "My first counsel is this: Possess a pure, kindly and radiant heart,",
    "that thine may be a sovereignty ancient, imperishable and everlasting.",
    "(A representative passage exercising the Master Key PDF pipeline.)",
]
PAGE2_BODY = [
    "Second page.",
    "Multi-page handling is part of the Definition of Done.",
]


def _draw_page(c: canvas.Canvas, header: str, body: list[str], footer: str) -> None:
    c.setFont("Helvetica", 11)
    c.drawString(72, _HEIGHT * 0.96, header)  # ~4% from top -> header band
    y = _HEIGHT * 0.75  # body starts well below the 8% header band
    for line in body:
        c.drawString(72, y, line)
        y -= 20
    c.drawString(_WIDTH / 2, _HEIGHT * 0.03, footer)  # ~3% from bottom -> footer band
    c.showPage()


def main() -> None:
    c = canvas.Canvas(str(OUT), pagesize=letter)
    _draw_page(c, "The Hidden Words - Part I", PAGE1_BODY, "- 1 -")
    _draw_page(c, "The Hidden Words - Part I", PAGE2_BODY, "- 2 -")
    c.save()
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
