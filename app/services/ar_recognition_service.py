"""Read-only recognition loading; no writes, FX, commits, or stored events."""
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import OutgoingInvoiceORM, IncomingPaymentORM, InvoicePaymentAllocationORM
from app.domain.ar_recognition import (
    ArInvoiceRecognitionFacts, ArAllocationRecognitionFacts, ArRecognitionEvent,
    resolve_ar_recognition_events,
)
from app.services.receivables_service import ReceivablesError


class ArRecognitionService:
    def __init__(self, db: Session):
        self.db = db

    def resolve_invoice_events(self, invoice_id: str) -> tuple[ArRecognitionEvent, ...]:
        invoice = OutgoingInvoiceORM
        allocation = InvoicePaymentAllocationORM
        payment = IncomingPaymentORM
        # One statement gives coherent current facts, independent of ORM identity
        # cache and database return order. Never flush caller's pending edits.
        statement = select(
            invoice.gross_amount, invoice.currency_original, invoice.payment_date,
            allocation.id, allocation.payment_id, allocation.amount_allocated,
            payment.payment_date, payment.currency,
            invoice.net_amount, invoice.vat_amount, invoice.amount_common,
        ).select_from(invoice).outerjoin(allocation, allocation.invoice_id == invoice.id).outerjoin(
            payment, payment.id == allocation.payment_id).where(invoice.id == invoice_id)
        with self.db.no_autoflush:
            rows = self.db.execute(statement).all()
        if not rows:
            raise ReceivablesError('outgoing_invoices record not found', 404)
        gross, currency, manual_date = rows[0][:3]
        components = tuple(Decimal(value) if value is not None else None for value in rows[0][8:])
        facts = ArInvoiceRecognitionFacts(invoice_id, Decimal(gross), currency, manual_date, *components)
        allocations = []
        for row in rows:
            _, _, _, allocation_id, payment_id, amount, payment_date, payment_currency = row[:8]
            if allocation_id is None:
                continue
            if payment_date is None or payment_currency is None:
                raise ReceivablesError('Allocation has no valid parent payment')
            allocations.append(ArAllocationRecognitionFacts(
                invoice_id, allocation_id, payment_id, Decimal(amount), payment_date, payment_currency))
        return resolve_ar_recognition_events(facts, tuple(allocations))
