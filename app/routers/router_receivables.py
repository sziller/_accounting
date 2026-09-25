"""Additive receivables routes, with the same request-scoped accounting DB session."""
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse
from pathlib import Path
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.db.database import get_db_session
from app.schemas.receivables_schema import (
    IncomingPaymentCreateSchema, IncomingPaymentReadSchema, IncomingPaymentUpdateSchema,
    InvoicePaymentAllocationCreateSchema, InvoicePaymentAllocationReadSchema,
    OutgoingInvoiceCreateSchema, OutgoingInvoiceReadSchema, OutgoingInvoiceUpdateSchema,
    ArConversionReportSchema, ArProcessingResultSchema, ArProcessingReportSchema,
)
from app.services.receivables_service import ReceivablesError, ReceivablesService
from app.schemas.ar_invoice_import_schema import ArInvoiceDirectoryResultSchema, ArInvoiceSourceFilesSchema
from app.services.ar_recognition_service import ArRecognitionService
from app.schemas.receivables_schema import ArRecognitionEventReadSchema
from app.core import config
from app.schemas.outgoing_invoice_recognition_schema import (
    OutgoingInvoiceBatchCreateSchema, OutgoingInvoiceBatchResultSchema,
)
from app.services.outgoing_invoice_contract import outgoing_invoice_create_contract


def _call(db, method, *args):
    try:
        return getattr(ReceivablesService(db), method)(*args)
    except ReceivablesError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    except ValidationError as exc:
        # PATCH is validated again after merging supplied fields with stored data.
        raise HTTPException(422, jsonable_encoder(exc.errors(include_context=False))) from exc


class ReceivablesRouter(APIRouter):
    def __init__(self, *, prefix="/acct", **kwargs):
        super().__init__(prefix=prefix, tags=["receivables"], **kwargs)
        self.add_api_route('/v0/outgoing-invoice-create-contract', self.create_contract, methods=['GET'])
        self.add_api_route('/v0/outgoing-invoices/batch', self.create_batch, methods=['POST'],
                           response_model=OutgoingInvoiceBatchResultSchema)
        self.add_api_route('/v0/outgoing-invoices/{id}/source-pdf', self.source_pdf, methods=['GET'],
                           response_class=FileResponse)
        self.add_api_route('/v0/outgoing-invoices/{id}/recognition-events', self.recognition_events,
                           methods=['GET'], response_model=list[ArRecognitionEventReadSchema])
        self.add_api_route("/v0/outgoing-invoices/source-files", self.source_files,
                           methods=["GET"], response_model=ArInvoiceSourceFilesSchema, deprecated=True)
        self.add_api_route("/v0/outgoing-invoices/process-directory", self.process_directory,
                           methods=["POST"], response_model=ArInvoiceDirectoryResultSchema, deprecated=True)
        self.add_api_route("/v0/outgoing-invoices/normalize-pending", self.normalize_pending,
                           methods=["POST"], response_model=ArConversionReportSchema)
        self.add_api_route("/v0/outgoing-invoices/process-entries", self.process_entries,
                           methods=["POST"], response_model=ArProcessingReportSchema)
        self.add_api_route("/v0/outgoing-invoices/{id}/process", self.process_entry,
                           methods=["POST"], response_model=ArProcessingResultSchema)
        for path, endpoint, method, schema in (
            ("outgoing-invoices", self.list_invoices, "GET", list[OutgoingInvoiceReadSchema]),
            ("outgoing-invoices", self.create_invoice, "POST", OutgoingInvoiceReadSchema),
            ("outgoing-invoices/{id}", self.get_invoice, "GET", OutgoingInvoiceReadSchema),
            ("outgoing-invoices/{id}", self.update_invoice, "PATCH", OutgoingInvoiceReadSchema),
            ("incoming-payments", self.list_payments, "GET", list[IncomingPaymentReadSchema]),
            ("incoming-payments", self.create_payment, "POST", IncomingPaymentReadSchema),
            ("incoming-payments/{id}", self.get_payment, "GET", IncomingPaymentReadSchema),
            ("incoming-payments/{id}", self.update_payment, "PATCH", IncomingPaymentReadSchema),
            ("invoice-payment-allocations", self.create_allocation, "POST", InvoicePaymentAllocationReadSchema),
        ):
            self.add_api_route(f"/v0/{path}", endpoint, methods=[method], response_model=schema,
                               status_code=201 if method == "POST" else 200)
        self.add_api_route("/v0/invoice-payment-allocations/{id}", self.delete_allocation,
                           methods=["DELETE"], status_code=204, response_class=Response)
        self.add_api_route("/v0/incoming-payments/{id}", self.delete_payment,
                           methods=["DELETE"], status_code=204, response_class=Response)
        self.add_api_route("/v0/outgoing-invoices/{id}", self.delete_invoice,
                           methods=["DELETE"], status_code=204, response_class=Response)

    def create_contract(self):
        return outgoing_invoice_create_contract(self.prefix)

    def create_batch(self, payload: OutgoingInvoiceBatchCreateSchema, db: Session = Depends(get_db_session)):
        results = []
        service = ReceivablesService(db)
        for index, invoice in enumerate(payload.invoices):
            try:
                entry = service.create_invoice(invoice.to_create())
                results.append(dict(index=index, invoice_number=invoice.invoice_number,
                                    status="created", status_code=201, entry=entry))
            except ReceivablesError as exc:
                results.append(dict(index=index, invoice_number=invoice.invoice_number,
                                    status="failed", status_code=exc.status_code, error=str(exc)))
        created = sum(item["status"] == "created" for item in results)
        return dict(created=created, failed=len(results) - created, invoices=results)

    def source_pdf(self, id: str, db: Session = Depends(get_db_session)):
        """Serve only the selected DB invoice's source; never scan or parse PDFs."""
        filename = _call(db, "get_invoice", id).pdf_filename
        if not filename:
            raise HTTPException(404, "Invoice has no associated PDF")
        if any(ord(c) < 32 or c in "/\\" for c in filename):
            raise HTTPException(400, "Invalid PDF basename")
        if Path(filename).suffix.lower() != '.pdf':
            raise HTTPException(415, "Only PDF source files are supported")
        try:
            directory = config.AR_SOURCE_DOCUMENT_DIRECTORY.resolve()
            source = (directory / filename).resolve()
            if not source.is_relative_to(directory):
                raise HTTPException(400, "PDF must remain inside the configured directory")
            if not source.is_file():
                raise HTTPException(404, "Source PDF not found")
        except (OSError, RuntimeError, ValueError):
            raise HTTPException(404, "Source PDF unavailable") from None
        return FileResponse(source, media_type="application/pdf", filename=filename,
                            content_disposition_type="inline", headers={"X-Content-Type-Options": "nosniff"})

    def recognition_events(self, id: str, db: Session = Depends(get_db_session)):
        try:
            return ArRecognitionService(db).resolve_invoice_events(id)
        except ReceivablesError as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc

    def process_entry(self, id: str, db: Session = Depends(get_db_session)):
        return _call(db, "process_ar_entry", id)

    def process_entries(self, db: Session = Depends(get_db_session)):
        return _call(db, "process_ar_entries")

    def list_invoices(self, db: Session = Depends(get_db_session)):
        return _call(db, "list_invoices")

    def normalize_pending(self, db: Session = Depends(get_db_session)):
        return _call(db, "normalize_pending_invoices")

    def source_files(self):
        # Legacy-only dependency: normalized creation and PDF display never load the parser.
        from app.services.ar_invoice_import_service import list_ar_invoice_source_files
        from app.services.pdf_extraction_service import PdfExtractionError
        try:
            return list_ar_invoice_source_files()
        except PdfExtractionError as exc:
            raise HTTPException(503, {"code": exc.code, "message": str(exc)}) from exc

    def process_directory(self, db: Session = Depends(get_db_session)):
        from app.services.ar_invoice_import_service import process_ar_invoice_directory
        from app.services.pdf_extraction_service import PdfExtractionError
        try:
            return process_ar_invoice_directory(session_factory=sessionmaker(bind=db.get_bind()))
        except PdfExtractionError as exc:
            raise HTTPException(400, {"code": exc.code, "message": str(exc)}) from exc

    def create_invoice(self, payload: OutgoingInvoiceCreateSchema, db: Session = Depends(get_db_session)):
        return _call(db, "create_invoice", payload)

    def get_invoice(self, id: str, db: Session = Depends(get_db_session)):
        return _call(db, "get_invoice", id)

    def update_invoice(self, id: str, payload: OutgoingInvoiceUpdateSchema, db: Session = Depends(get_db_session)):
        return _call(db, "update_invoice", id, payload)

    def list_payments(self, db: Session = Depends(get_db_session)):
        return _call(db, "list_payments")

    def create_payment(self, payload: IncomingPaymentCreateSchema, db: Session = Depends(get_db_session)):
        return _call(db, "create_payment", payload)

    def get_payment(self, id: str, db: Session = Depends(get_db_session)):
        return _call(db, "get_payment", id)

    def update_payment(self, id: str, payload: IncomingPaymentUpdateSchema, db: Session = Depends(get_db_session)):
        return _call(db, "update_payment", id, payload)

    def create_allocation(self, payload: InvoicePaymentAllocationCreateSchema, db: Session = Depends(get_db_session)):
        return _call(db, "create_allocation", payload)

    def delete_payment(self, id: str, db: Session = Depends(get_db_session)):
        _call(db, "delete_incoming_payment", id)
        return Response(status_code=204)

    def delete_invoice(self, id: str, db: Session = Depends(get_db_session)):
        _call(db, "delete_outgoing_invoice", id)
        return Response(status_code=204)

    def delete_allocation(self, id: str, db: Session = Depends(get_db_session)):
        _call(db, "delete_allocation", id)
        return Response(status_code=204)
