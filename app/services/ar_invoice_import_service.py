"""Explicit AR archive processing, one independent transaction per PDF."""
import logging

from pydantic import ValidationError

from app.core import config
from app.db.database import SessionLocal
from app.schemas.ar_invoice_import_schema import ArInvoiceDirectoryResultSchema, ArInvoiceFileResultSchema, ArInvoiceSourceFilesSchema
from app.schemas.receivables_schema import OutgoingInvoiceCreateSchema
from app.services.ar_invoice_parser import ArInvoiceParseError, parse_ar_invoice_text
from app.services.pdf_extraction_service import PdfExtractionError, load_outgoing_invoice_pdf
from app.services.receivables_service import ReceivablesError, ReceivablesService

logger = logging.getLogger(__name__)


def list_ar_invoice_source_files() -> ArInvoiceSourceFilesSchema:
    """List readable archive candidates without importing or exposing paths."""
    configured = config.AR_SOURCE_DOCUMENT_DIRECTORY
    try:
        directory = configured.resolve()
        files = sorted(path.name for path in directory.iterdir()
                       if path.suffix.lower() == ".pdf" and path.is_file()
                       and path.resolve().is_relative_to(directory))
    except (FileNotFoundError, NotADirectoryError):
        files = []
    except (OSError, RuntimeError):
        raise PdfExtractionError("directory_unavailable", "AR PDF directory could not be read") from None
    return ArInvoiceSourceFilesSchema(directory=configured.name, files=files)


def import_ar_invoice_pdf(filename: str, *, session_factory=SessionLocal) -> ArInvoiceFileResultSchema:
    """Load/parse a file without DB side effects, then atomically check and insert."""
    invoice_number = None
    try:
        source = load_outgoing_invoice_pdf(filename)
        parsed = parse_ar_invoice_text(source.text)
        invoice_number = parsed.invoice_number
        candidate = OutgoingInvoiceCreateSchema.model_validate({
            **parsed.model_dump(), "pdf_filename": source.pdf_filename, "pdf_sha256": source.pdf_sha256,
        })
        with session_factory() as db:
            decision, invoice = ReceivablesService(db).create_invoice_from_pdf(candidate)
        if decision == "invoice_number_conflict":
            return ArInvoiceFileResultSchema(
                filename=filename, status="failed", outgoing_invoice_id=invoice.id,
                invoice_number=invoice_number, error_code=decision,
                error="Invoice number already exists with a different or missing PDF hash; no record was changed",
            )
        return ArInvoiceFileResultSchema(filename=filename, status=decision,
                                         outgoing_invoice_id=invoice.id, invoice_number=invoice.invoice_number)
    except (PdfExtractionError, ArInvoiceParseError) as exc:
        code, message = exc.code, str(exc)
    except ValidationError:
        code, message = "invalid_invoice_values", "Extracted invoice or source metadata failed validation"
    except ReceivablesError as exc:
        code, message = "persistence_failed", str(exc)
    except Exception:
        # Isolate a file failure, including unexpected decoder/database failures.
        # Detailed diagnostics are server-side; the batch report never leaks paths.
        logger.exception("AR PDF processing failed")
        code, message = "processing_failed", "PDF processing failed; consult the server log"
    return ArInvoiceFileResultSchema(filename=filename, status="failed", invoice_number=invoice_number,
                                     error_code=code, error=message)


def process_ar_invoice_directory(*, session_factory=SessionLocal) -> ArInvoiceDirectoryResultSchema:
    """Process sorted top-level .pdf names. Other suffixes are ignored.

    Directories named .pdf and escaping symlinks receive per-file failures. Source
    bytes, basenames, and modification times are never deliberately changed.
    """
    try:
        names = sorted(path.name for path in config.AR_SOURCE_DOCUMENT_DIRECTORY.iterdir()
                       if path.suffix.lower() == ".pdf")
    except OSError:
        raise PdfExtractionError("directory_unavailable", "AR PDF directory is missing or unreadable") from None
    results = [import_ar_invoice_pdf(name, session_factory=session_factory) for name in names]
    return ArInvoiceDirectoryResultSchema(
        files=results,
        **{status: sum(item.status == status for item in results)
           for status in ("imported", "already_imported", "failed")},
    )
