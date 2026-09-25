"""Local PDF extraction only; no invoice interpretation or database writes."""
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from app.core import config


class PdfExtractionError(ValueError):
    """Stable diagnostic code and path-free message for future API/CLI callers."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ExtractedPdf:
    pdf_filename: str
    pdf_sha256: str
    page_texts: tuple[str, ...]

    @property
    def page_count(self) -> int:
        return len(self.page_texts)

    @property
    def text(self) -> str:
        # Keep page boundaries explicit rather than joining adjacent page words.
        return "\n\f\n".join(self.page_texts)


def extract_pdf_page_texts(pdf_bytes: bytes) -> tuple[str, ...]:
    """Extract embedded text in PDF content order, retaining each page separately.

    No OCR, external service, layout assumptions, or whitespace normalization.
    Blank pages are retained; a document with no usable text is rejected.
    """
    if not pdf_bytes.startswith(b"%PDF-"):
        raise PdfExtractionError("invalid_pdf", "Source does not have a PDF header")
    try:
        reader = PdfReader(BytesIO(pdf_bytes), strict=True)
        if reader.is_encrypted:
            raise PdfExtractionError("encrypted_pdf", "Encrypted PDFs are not supported")
        pages = tuple(page.extract_text() or "" for page in reader.pages)
    except PdfExtractionError:
        raise
    except Exception:
        # The PDF decoder can raise several low-level exception types. Do not
        # expose decoder internals or filenames to a future HTTP caller.
        raise PdfExtractionError("text_extraction_failed", "PDF text could not be extracted") from None
    if not any(text.strip() for text in pages):
        raise PdfExtractionError("no_embedded_text", "PDF contains no usable embedded text")
    return pages


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Return embedded text with explicit form-feed page separators."""
    return "\n\f\n".join(extract_pdf_page_texts(pdf_bytes))


def load_outgoing_invoice_pdf(filename: str) -> ExtractedPdf:
    """Read one exact basename from the configured directory and inspect it.

    Hash and extraction both use the same original byte snapshot. This function
    never creates an invoice, changes the PDF, or creates the source directory.
    """
    if not filename or filename in {".", ".."} or any(c in filename for c in ("/", "\\", "\x00")):
        raise PdfExtractionError("invalid_filename", "A source PDF basename is required")
    if Path(filename).suffix.lower() != ".pdf":
        raise PdfExtractionError("unsupported_extension", "Only .pdf source files are supported")
    try:
        directory = config.AR_SOURCE_DOCUMENT_DIRECTORY.resolve()
        source = (directory / filename).resolve()
        if not source.is_relative_to(directory):
            raise PdfExtractionError("invalid_filename", "Source PDF must remain inside the configured directory")
        if not source.is_file():
            raise PdfExtractionError("file_not_found", "Source PDF file not found")
        original_bytes = source.read_bytes()
    except PdfExtractionError:
        raise
    except (OSError, RuntimeError, ValueError):
        raise PdfExtractionError("file_unreadable", "Source PDF could not be read") from None
    return ExtractedPdf(
        pdf_filename=filename,
        pdf_sha256=sha256(original_bytes).hexdigest(),
        page_texts=extract_pdf_page_texts(original_bytes),
    )
