"""PDF text extraction via pdfplumber.

Per ADR-003, this is the only library allowed for PDF parsing —
PyMuPDF (`fitz`) is forbidden because its AGPL license would force
the same terms onto Masterkey. pdfplumber is MIT-licensed.

Parsing happens in-process for ≤25 MB uploads (Cloud Run gives us
32 MB of request-body headroom). The raw PDF bytes are never written
to disk or to GCS; only the extracted text persists, in the `Passage`
row.
"""

import io

import pdfplumber
from pdfplumber.page import Page

# INGEST-P2-1 (#169): fraction of each page's height treated as the header
# band (top) and footer band (bottom). Text inside these bands — running
# titles, page numbers, copyright lines — is excluded before extraction so it
# doesn't interrupt sentence flow on the reading surface. 8% ≈ 0.63in on US
# Letter, just under a standard 1in margin, so headerless pages keep all body
# text. Module-level so they're tunable without hunting through the code.
HEADER_MARGIN_FRACTION = 0.08
FOOTER_MARGIN_FRACTION = 0.08


class PdfParseError(Exception):
    """pdfplumber failed to read the file (corrupt, encrypted, etc.)."""


class EmptyPdfTextError(Exception):
    """The PDF parsed but produced no extractable text.

    Most commonly: the document is scanned images with no OCR layer.
    The route layer converts this to a 422 with a user-readable
    "try copy-pasting" message.
    """


def extract_text(pdf_bytes: bytes) -> str:
    """Return text extracted from the PDF, joined with `\\n\\n` between pages.

    Raises:
        PdfParseError: if pdfplumber cannot open the file.
        EmptyPdfTextError: if the file opens but yields no text after
            stripping whitespace (typically a scanned PDF without OCR).
    """
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = [_extract_page_body(page) for page in pdf.pages]
    except Exception as exc:  # pdfplumber raises a mix of exception types
        raise PdfParseError(str(exc)) from exc

    text = "\n\n".join(pages)
    if not text.strip():
        raise EmptyPdfTextError()
    return text


def _extract_page_body(page: Page) -> str:
    """Extract a page's text with the header and footer bands cropped out.

    Crops to the vertical middle of the page — excluding the top
    HEADER_MARGIN_FRACTION and bottom FOOTER_MARGIN_FRACTION — using
    `within_bbox` (pdfplumber's recommended cropping API). The crop is silent:
    a page whose text all sits in the margins yields "" here, and the
    all-empty-document case is handled once, upstream, by `extract_text`.

    The only fallback is for a page box pdfplumber can't crop (degenerate or
    out-of-bounds mediabox): rather than fail the whole upload, that one page
    is extracted uncropped. That path can't re-introduce a header on a normal
    page — it fires solely on a `within_bbox` error, not on an empty crop.
    """
    top = page.height * HEADER_MARGIN_FRACTION
    bottom = page.height * (1 - FOOTER_MARGIN_FRACTION)
    try:
        return page.within_bbox((0, top, page.width, bottom)).extract_text() or ""
    except ValueError:
        return page.extract_text() or ""
