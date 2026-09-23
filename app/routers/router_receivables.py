"""Additive receivables routes, with the same request-scoped accounting DB session."""
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.encoders import jsonable_encoder
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
from app.services.ar_invoice_import_service import process_ar_invoice_directory, list_ar_invoice_source_files
from app.services.pdf_extraction_service import PdfExtractionError
from app.services.ar_recognition_service import ArRecognitionService
from app.schemas.receivables_schema import ArRecognitionEventReadSchema


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
        self.add_api_route('/v0/outgoing-invoices/{id}/recognition-events', self.recognition_events,
                           methods=['GET'], response_model=list[ArRecognitionEventReadSchema])
        self.add_api_route("/v0/outgoing-invoices/source-files", self.source_files,
                           methods=["GET"], response_model=ArInvoiceSourceFilesSchema)
        self.add_api_route("/v0/outgoing-invoices/process-directory", self.process_directory,
                           methods=["POST"], response_model=ArInvoiceDirectoryResultSchema)
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
        try:
            return list_ar_invoice_source_files()
        except PdfExtractionError as exc:
            raise HTTPException(503, {"code": exc.code, "message": str(exc)}) from exc

    def process_directory(self, db: Session = Depends(get_db_session)):
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

    def delete_allocation(self, id: str, db: Session = Depends(get_db_session)):
        _call(db, "delete_allocation", id)
        return Response(status_code=204)
