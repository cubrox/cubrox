"""Passage ingestion routes.

Three endpoints across paste-text + PDF-upload paths:
  GET  /passages/new  — render the upload page (auth-required)
  POST /passages      — persist pasted text, redirect to /read/{id}
  POST /passages/pdf  — parse uploaded PDF in-process, persist text,
                        redirect to /read/{id}

All require an authenticated user; unauthenticated requests get the
standard landing-page redirect via the `current_user` dependency. Per
ADR guardrails, the paste route writes text byte-for-byte (no
normalization) so the SHA-256 hash matches what the comprehension cache
will look up. The PDF route hashes the *extracted* text, not the PDF
bytes — the cache is keyed on what the user reads, not how it arrived.
"""

import hashlib
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from app.db import get_session
from app.integrations.supabase.auth import current_user
from app.models.passage import Passage
from app.services.ingestion.pdf import EmptyPdfTextError, PdfParseError, extract_text
from app.services.ingestion.split import MAX_PARTS, split_into_parts
from app.templates import templates

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]
CurrentUser = Annotated[Any, Depends(current_user)]

# Hard ceiling on a single passage. ~100k chars is around 4k lines of
# regular prose — enough for a chapter-length excerpt, far enough below
# Cloud Run's 32 MB request body limit to stay safe.
MAX_TEXT_LEN = 100_000

# Cloud Run caps inbound request bodies at 32 MB. 25 MB leaves headroom
# for multipart framing overhead and keeps memory use bounded since we
# parse PDFs in-process per ADR-003.
MAX_PDF_BYTES = 25 * 1024 * 1024

EMPTY_PDF_MESSAGE = (
    "This PDF didn't produce any extractable text. Try copy-pasting the text directly."
)


def _persist_as_passages(
    *,
    session: Session,
    owner_id: uuid.UUID,
    text: str,
    source_type: str,
    source_filename: str | None,
) -> Passage:
    """Persist `text` as one passage, or — if it's over MAX_TEXT_LEN — as an
    ordered set of linked parts (INGEST-3 #145). Returns the FIRST passage
    (part 0), which the caller redirects to.

    Text within the cap stays a standalone passage (document_id=None) exactly
    as before. Over the cap, it's split into <= MAX_TEXT_LEN-render-safe parts
    that share one document_id; the reading view links them with Prev/Next.
    """
    if len(text) <= MAX_TEXT_LEN:
        parts = [text]
    else:
        parts = split_into_parts(text)

    if len(parts) > MAX_PARTS:
        raise HTTPException(
            status_code=422,
            detail=f"Document is too large to ingest, even split into parts (>{MAX_PARTS}).",
        )

    document_id = uuid.uuid4() if len(parts) > 1 else None
    part_count = len(parts)
    first: Passage | None = None
    for index, part_text in enumerate(parts):
        passage = Passage(
            owner_id=owner_id,
            text=part_text,
            text_hash=hashlib.sha256(part_text.encode("utf-8")).digest(),
            source_type=source_type,
            source_filename=source_filename,
            document_id=document_id,
            part_index=index,
            part_count=part_count,
        )
        session.add(passage)
        if index == 0:
            first = passage
    session.commit()
    assert first is not None  # parts is always non-empty
    session.refresh(first)
    return first


@router.get("/passages/new", response_class=HTMLResponse)
def new_passage_form(request: Request, user: CurrentUser) -> HTMLResponse:
    """Render the paste-text form."""
    return templates.TemplateResponse(
        request=request,
        name="pages/passages_new.html",
        context={"user": user},
    )


@router.post("/passages")
def create_passage(
    user: CurrentUser,
    session: SessionDep,
    text: Annotated[str, Form()],
) -> RedirectResponse:
    """Persist the pasted text and redirect to the reading view.

    Validation rules:
      - text is non-empty
      - over MAX_TEXT_LEN, the text is auto-split into linked parts
        (INGEST-3 #145) rather than rejected
      - each part's text_hash = SHA-256 of its EXACT bytes (no strip,
        no lowercase) so cross-user cache hits work
      - source_type='paste', source_filename=None
    """
    if len(text) == 0:
        raise HTTPException(status_code=422, detail="Text is required")

    first = _persist_as_passages(
        session=session,
        owner_id=user.id,
        text=text,
        source_type="paste",
        source_filename=None,
    )
    return RedirectResponse(url=f"/read/{first.id}", status_code=303)


@router.post("/passages/pdf")
async def create_passage_from_pdf(
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    file: Annotated[UploadFile, File()],
) -> RedirectResponse:
    """Parse an uploaded PDF in-process and persist its extracted text.

    Validation order (cheapest checks first, so we reject before reading
    the file into memory):
      1. Content-Length header ≤ 25 MB (avoids loading huge bodies)
      2. content_type == 'application/pdf' (no .txt or .docx)
      3. Actual byte length ≤ 25 MB (header can lie)
      4. pdfplumber successfully opens the file (else 422 with helpful text)
      5. Extracted text is non-empty after stripping (else 422 same message)
    """
    content_length = request.headers.get("content-length")
    if content_length is not None and int(content_length) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"PDF exceeds {MAX_PDF_BYTES // (1024 * 1024)} MB limit",
        )

    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=415,
            detail="Only PDF files are accepted (Content-Type: application/pdf)",
        )

    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"PDF exceeds {MAX_PDF_BYTES // (1024 * 1024)} MB limit",
        )

    try:
        text = extract_text(pdf_bytes)
    except (PdfParseError, EmptyPdfTextError):
        raise HTTPException(status_code=422, detail=EMPTY_PDF_MESSAGE) from None

    # Over the cap, auto-split into linked parts (INGEST-3 #145) instead of
    # silently truncating to MAX_TEXT_LEN — a large PDF reads in full.
    first = _persist_as_passages(
        session=session,
        owner_id=user.id,
        text=text,
        source_type="pdf",
        source_filename=file.filename,
    )
    return RedirectResponse(url=f"/read/{first.id}", status_code=303)
