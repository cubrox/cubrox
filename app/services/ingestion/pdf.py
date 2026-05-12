"""PDF text extraction via pdfplumber.

Per ADR-003, this is the only library allowed for PDF parsing —
PyMuPDF (`fitz`) is forbidden because its AGPL license would force
the same terms onto Cubrox. pdfplumber is MIT-licensed.

Parsing happens in-process for ≤25 MB uploads (Cloud Run gives us
32 MB of request-body headroom). The raw PDF bytes are never written
to disk or to GCS; only the extracted text persists, in the `Passage`
row.
"""

import io

import pdfplumber


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
            pages = [page.extract_text() or "" for page in pdf.pages]
    except Exception as exc:  # pdfplumber raises a mix of exception types
        raise PdfParseError(str(exc)) from exc

    text = "\n\n".join(pages)
    if not text.strip():
        raise EmptyPdfTextError()
    return text
