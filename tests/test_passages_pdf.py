"""Tests for the PDF upload ingestion flow (INGEST-2 #14).

Covers the Definition of Done from issue #14:
  - Upload tests/fixtures/sample_passage.pdf → 303 to /read/<uuid>
  - Passage row has source_type='pdf', non-empty text, source_filename set
  - 26 MB upload → 413 (rejected before parsing)
  - text/plain upload → 415
  - Blank PDF (no extractable text) → 422 with user-readable message
  - No pymupdf / fitz import anywhere in app/
  - Unauthenticated upload → 303 to landing page
"""

import base64
import io
import subprocess
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models.passage import Passage
from tests.conftest import signed_in

FIXTURE_PDF = Path(__file__).parent / "fixtures" / "sample_passage.pdf"

# A valid PDF with no text content (one empty page). Used to exercise
# the empty-extraction code path without checking in a second fixture
# file.
BLANK_PDF_BYTES = base64.b64decode(
    "JVBERi0xLjMKJZOMi54gUmVwb3J0TGFiIEdlbmVyYXRlZCBQREYgZG9jdW1lbnQgKG9w"
    "ZW5zb3VyY2UpCjEgMCBvYmoKPDwKL0YxIDIgMCBSCj4+CmVuZG9iagoyIDAgb2JqCjw8"
    "Ci9CYXNlRm9udCAvSGVsdmV0aWNhIC9FbmNvZGluZyAvV2luQW5zaUVuY29kaW5nIC9O"
    "YW1lIC9GMSAvU3VidHlwZSAvVHlwZTEgL1R5cGUgL0ZvbnQKPj4KZW5kb2JqCjMgMCBv"
    "YmoKPDwKL0NvbnRlbnRzIDcgMCBSIC9NZWRpYUJveCBbIDAgMCA2MTIgNzkyIF0gL1Bh"
    "cmVudCA2IDAgUiAvUmVzb3VyY2VzIDw8Ci9Gb250IDEgMCBSIC9Qcm9jU2V0IFsgL1BE"
    "RiAvVGV4dCAvSW1hZ2VCIC9JbWFnZUMgL0ltYWdlSSBdCj4+IC9Sb3RhdGUgMCAvVHJh"
    "bnMgPDwKCj4+IAogIC9UeXBlIC9QYWdlCj4+CmVuZG9iago0IDAgb2JqCjw8Ci9QYWdl"
    "TW9kZSAvVXNlTm9uZSAvUGFnZXMgNiAwIFIgL1R5cGUgL0NhdGFsb2cKPj4KZW5kb2Jq"
    "CjUgMCBvYmoKPDwKL0F1dGhvciAoYW5vbnltb3VzKSAvQ3JlYXRpb25EYXRlIChEOjIw"
    "MjYwNTEyMTc0NTAwKzAwJzAwJykgL0NyZWF0b3IgKGFub255bW91cykgL0tleXdvcmRz"
    "ICgpIC9Nb2REYXRlIChEOjIwMjYwNTEyMTc0NTAwKzAwJzAwJykgL1Byb2R1Y2VyIChS"
    "ZXBvcnRMYWIgUERGIExpYnJhcnkgLSBcKG9wZW5zb3VyY2VcKSkgCiAgL1N1YmplY3Qg"
    "KHVuc3BlY2lmaWVkKSAvVGl0bGUgKHVudGl0bGVkKSAvVHJhcHBlZCAvRmFsc2UKPj4K"
    "ZW5kb2JqCjYgMCBvYmoKPDwKL0NvdW50IDEgL0tpZHMgWyAzIDAgUiBdIC9UeXBlIC9Q"
    "YWdlcwo+PgplbmRvYmoKNyAwIG9iago8PAovRmlsdGVyIFsgL0FTQ0lJODVEZWNvZGUg"
    "L0ZsYXRlRGVjb2RlIF0gL0xlbmd0aCA1OQo+PgpzdHJlYW0KR2FwUWgwRT1GLDBVXEgz"
    "VFxwTllUXlFLaz90Yz5JUCw7VyNVMV4yM2loUEVNX1BQJE8hM14sQzVRfj5lbmRzdHJl"
    "YW0KZW5kb2JqCnhyZWYKMCA4CjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDA2MSAw"
    "MDAwMCBuIAowMDAwMDAwMDkyIDAwMDAwIG4gCjAwMDAwMDAxOTkgMDAwMDAgbiAKMDAw"
    "MDAwMDM5MiAwMDAwMCBuIAowMDAwMDAwNDYwIDAwMDAwIG4gCjAwMDAwMDA3MjEgMDAw"
    "MDAgbiAKMDAwMDAwMDc4MCAwMDAwMCBuIAp0cmFpbGVyCjw8Ci9JRCAKWzw2YzhlMjY1"
    "MjFjOTZlYzA3OTM2YWU3NWMyOWI0NDQ1Yz48NmM4ZTI2NTIxYzk2ZWMwNzkzNmFlNzVj"
    "MjliNDQ0NWM+XQolIFJlcG9ydExhYiBnZW5lcmF0ZWQgUERGIGRvY3VtZW50IC0tIGRp"
    "Z2VzdCAob3BlbnNvdXJjZSkKCi9JbmZvIDUgMCBSCi9Sb290IDQgMCBSCi9TaXplIDgK"
    "Pj4Kc3RhcnR4cmVmCjkyOAolJUVPRgo="
)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_upload_pdf_redirects_to_read_route(client: TestClient, session: Session) -> None:
    signed_in(session)
    with FIXTURE_PDF.open("rb") as f:
        response = client.post(
            "/passages/pdf",
            files={"file": ("sample_passage.pdf", f, "application/pdf")},
            follow_redirects=False,
        )
    assert response.status_code == 303

    location = response.headers["location"]
    assert location.startswith("/read/")
    uuid.UUID(location.split("/")[-1])


def test_uploaded_pdf_persists_extracted_text(client: TestClient, session: Session) -> None:
    user = signed_in(session)
    with FIXTURE_PDF.open("rb") as f:
        client.post(
            "/passages/pdf",
            files={"file": ("sample_passage.pdf", f, "application/pdf")},
            follow_redirects=False,
        )

    passages = session.exec(select(Passage)).all()
    assert len(passages) == 1
    p = passages[0]
    assert p.owner_id == user.id
    assert p.source_type == "pdf"
    assert p.source_filename == "sample_passage.pdf"
    # The fixture's page-1 content should round-trip through pdfplumber.
    assert "O Son of Spirit" in p.text
    # Multi-page joining: page-2 marker should also be present.
    assert "Second page" in p.text


# ---------------------------------------------------------------------------
# Rejections
# ---------------------------------------------------------------------------


def test_upload_over_25mb_returns_413(client: TestClient, session: Session) -> None:
    """The size-cap check fires before we read the body into memory.

    We don't need real PDF content here — the Content-Length header
    triggers the 413 before pdfplumber is even invoked.
    """
    signed_in(session)
    oversize = b"\x00" * (26 * 1024 * 1024)  # 26 MB
    response = client.post(
        "/passages/pdf",
        files={"file": ("huge.pdf", io.BytesIO(oversize), "application/pdf")},
        follow_redirects=False,
    )
    assert response.status_code == 413


def test_upload_wrong_content_type_returns_415(client: TestClient, session: Session) -> None:
    signed_in(session)
    response = client.post(
        "/passages/pdf",
        files={"file": ("notes.txt", io.BytesIO(b"just text, not a PDF"), "text/plain")},
        follow_redirects=False,
    )
    assert response.status_code == 415


def test_blank_pdf_returns_422_with_user_readable_message(
    client: TestClient, session: Session
) -> None:
    """Per PRD Risk #3, a blank or scanned-only PDF must surface a
    helpful message rather than a silent success or a 500."""
    signed_in(session)
    response = client.post(
        "/passages/pdf",
        files={"file": ("blank.pdf", io.BytesIO(BLANK_PDF_BYTES), "application/pdf")},
        follow_redirects=False,
    )
    assert response.status_code == 422
    body = response.json()
    assert "copy-pasting" in body["detail"]


def test_corrupt_pdf_returns_422_with_user_readable_message(
    client: TestClient, session: Session
) -> None:
    """A file that's labeled application/pdf but isn't actually a PDF
    should not bubble a 500 to the user — it should land on the same
    user-readable 422 as the blank-PDF path."""
    signed_in(session)
    response = client.post(
        "/passages/pdf",
        files={"file": ("garbage.pdf", io.BytesIO(b"not a real pdf"), "application/pdf")},
        follow_redirects=False,
    )
    assert response.status_code == 422
    assert "copy-pasting" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_unauthenticated_upload_redirects_to_landing(client: TestClient) -> None:
    with FIXTURE_PDF.open("rb") as f:
        response = client.post(
            "/passages/pdf",
            files={"file": ("sample_passage.pdf", f, "application/pdf")},
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert response.headers["location"] == "/"


# ---------------------------------------------------------------------------
# License guardrail (ADR-003): no PyMuPDF anywhere in app/
# ---------------------------------------------------------------------------


def test_no_pymupdf_or_fitz_import_in_app() -> None:
    """PyMuPDF is AGPL and forbidden by ADR-003. If anyone reaches for
    `fitz` because it's faster, this test fails the build before the PR
    lands."""
    app_dir = Path(__file__).parent.parent / "app"
    result = subprocess.run(
        ["grep", "-rEn", r"(\bimport fitz\b|\bfrom fitz\b|\bpymupdf\b)", str(app_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    # grep returns 1 when no matches are found — that's what we want.
    assert result.returncode == 1, f"Forbidden PyMuPDF import detected:\n{result.stdout}"


def test_over_cap_pdf_auto_splits_instead_of_truncating(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """INGEST-3 (#145): a large PDF is split into linked parts (no content
    lost) — replacing the old silent truncation to MAX_TEXT_LEN."""
    signed_in(session)
    big_text = "p" * 250_000  # ~3 parts at the 80k target
    monkeypatch.setattr("app.api.passages.extract_text", lambda _b: big_text)

    response = client.post(
        "/passages/pdf",
        files={"file": ("big.pdf", io.BytesIO(b"%PDF-1.4 dummy"), "application/pdf")},
        follow_redirects=False,
    )
    assert response.status_code == 303

    rows = session.exec(select(Passage).order_by(Passage.part_index)).all()
    assert len(rows) >= 2
    assert all(r.source_type == "pdf" and r.source_filename == "big.pdf" for r in rows)
    assert {r.part_count for r in rows} == {len(rows)}
    # Nothing truncated — the parts reproduce the full extracted text.
    assert "".join(r.text for r in rows) == big_text
