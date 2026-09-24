"""Exact-decimal receivables persistence for the application's SQLite database."""
from contextlib import contextmanager
from datetime import date
from decimal import Decimal, localcontext, InvalidOperation

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
import logging
from app.domain.ar_tax_year import resolve_ar_tax_year
from sqlalchemy.orm import Session

from app.db.models import IncomingPaymentORM, InvoicePaymentAllocationORM, OutgoingInvoiceORM
from app.schemas.receivables_schema import (
    IncomingPaymentCreateSchema, IncomingPaymentReadSchema, IncomingPaymentUpdateSchema,
    InvoicePaymentAllocationCreateSchema, InvoicePaymentAllocationReadSchema,
    OutgoingInvoiceCreateSchema, OutgoingInvoiceReadSchema, OutgoingInvoiceUpdateSchema,
)
from app.schemas.receivables_schema import ArConversionReportSchema, ArConversionResultSchema
from app.services.local_currency_conversion import LocalCurrencyConversion


class ReceivablesError(ValueError):
    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(detail)
        self.status_code = status_code


def row_data(row) -> dict:
    return {column.key: getattr(row, column.key) for column in row.__table__.columns}


def total(allocations) -> Decimal:
    # Never ask SQLite to SUM text money: it would coerce to floating point.
    with localcontext() as context:
        context.prec = 64
        return sum((Decimal(item.amount_allocated) for item in allocations), Decimal("0"))


class ReceivablesService:
    def __init__(self, db: Session):
        self.db = db

    @contextmanager
    def _write(self):
        """Own a fresh transaction; serialize SQLite writers BEFORE reading balances.

        All allocation changes and invoice/payment updates take this same lock.
        Request-scoped sessions must not already contain a transaction.
        """
        if self.db.in_transaction():
            raise RuntimeError("Receivables writes require a fresh session transaction")
        try:
            self.db.execute(text("BEGIN IMMEDIATE"))
            yield
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ReceivablesError("Duplicate invoice number or database constraint violation", 409) from exc
        except OperationalError as exc:
            self.db.rollback()
            if "locked" in str(exc).lower():
                raise ReceivablesError("Database is busy; retry the request", 503) from exc
            raise
        except Exception:
            self.db.rollback()
            raise

    def _get(self, model, identity):
        row = self.db.get(model, identity)
        if row is None:
            raise ReceivablesError(f"{model.__tablename__} record not found", 404)
        return row

    def _allocations(self, **filters):
        return list(self.db.scalars(select(InvoicePaymentAllocationORM).filter_by(**filters).order_by(
            InvoicePaymentAllocationORM.created_at, InvoicePaymentAllocationORM.id
        )))

    @staticmethod
    def _apply(row, payload):
        for key, value in payload.model_dump().items():
            setattr(row, key, format(value, "f") if isinstance(value, Decimal) else value)

    def _invoice_read(self, row):
        allocations = self._allocations(invoice_id=row.id)
        paid = total(allocations)
        outstanding = Decimal(row.gross_amount) - paid
        # Overdue takes precedence over partially paid while any balance remains.
        status = "paid" if outstanding == 0 else (
            "overdue" if row.due_date is not None and row.due_date < date.today() else (
                "partially_paid" if paid > 0 else "open"
            )
        )
        return OutgoingInvoiceReadSchema.model_validate({
            **row_data(row), "paid_amount": paid, "outstanding_amount": outstanding,
            "payment_status": status,
            "allocations": [dict(row_data(item), payment_date=self._get(IncomingPaymentORM, item.payment_id).payment_date)
                            for item in allocations],
        })

    def _payment_read(self, row):
        allocations = self._allocations(payment_id=row.id)
        allocated = total(allocations)
        return IncomingPaymentReadSchema.model_validate({
            **row_data(row), "allocated_amount": allocated,
            "unallocated_amount": Decimal(row.amount) - allocated,
            "allocations": [dict(row_data(item), invoice_number=self._get(OutgoingInvoiceORM, item.invoice_id).invoice_number)
                            for item in allocations],
        })

    def create_invoice(self, payload: OutgoingInvoiceCreateSchema):
        with self._write():
            result = self._insert_invoice(payload)
        return result

    def _insert_invoice(self, payload):
        row = OutgoingInvoiceORM()
        self._apply(row, payload)
        self.db.add(row)
        self.db.flush()
        self.db.refresh(row)
        return self._invoice_read(row)

    def create_invoice_from_pdf(self, payload: OutgoingInvoiceCreateSchema):
        """Serialize import duplicate checks with insertion, without changing CRUD.

        Return a decision and the created/existing invoice. No source metadata on
        existing rows is overwritten. All importers must use this transaction.
        """
        if not payload.pdf_sha256 or not payload.pdf_filename:
            raise ReceivablesError("PDF import requires source filename and hash")
        with self._write():
            existing = self.db.scalar(select(OutgoingInvoiceORM).where(
                func.lower(OutgoingInvoiceORM.pdf_sha256) == payload.pdf_sha256.lower()
            ).order_by(OutgoingInvoiceORM.id))
            if existing is not None:
                return "already_imported", self._invoice_read(existing)
            existing = self.db.scalar(select(OutgoingInvoiceORM).where(
                OutgoingInvoiceORM.invoice_number == payload.invoice_number
            ))
            if existing is not None:
                return "invoice_number_conflict", self._invoice_read(existing)
            return "imported", self._insert_invoice(payload)

    def list_invoices(self):
        return [self._invoice_read(row) for row in self.db.scalars(select(OutgoingInvoiceORM).order_by(
            OutgoingInvoiceORM.invoice_date.desc(), OutgoingInvoiceORM.id
        ))]

    def get_invoice(self, identity):
        return self._invoice_read(self._get(OutgoingInvoiceORM, identity))

    def update_invoice(self, identity, payload: OutgoingInvoiceUpdateSchema):
        with self._write():
            row = self._get(OutgoingInvoiceORM, identity)
            current = {key: getattr(row, key) for key in OutgoingInvoiceCreateSchema.model_fields}
            changes = payload.model_dump(exclude_unset=True)
            # Either spelling is accepted, but explicit conflicting pairs fail.
            changes = OutgoingInvoiceCreateSchema.accept_original_aliases(changes)
            merged = OutgoingInvoiceCreateSchema.model_validate({**current, **changes})
            allocations = self._allocations(invoice_id=row.id)
            if merged.gross_amount < total(allocations):
                raise ReceivablesError("gross_amount cannot be less than existing allocations")
            if allocations and merged.currency != row.currency:
                raise ReceivablesError("Cannot change currency while invoice has allocations")
            if (merged.amount_original != Decimal(row.amount_original)
                    or merged.currency_original != row.currency_original
                    or merged.currency_common != row.currency_common
                    or merged.invoice_date != row.invoice_date):
                row.amount_common = None
            self._apply(row, merged)
            self.db.flush()
            self.db.refresh(row)
            result = self._invoice_read(row)
        return result

    def _calculate_common_amount(self, row):
        """Shared AR monetary calculation; preserves invoice-date FX policy."""
        conversion = LocalCurrencyConversion(self.db)
        amount = None
        message = ""
        if row.currency_original == row.currency_common:
            amount = Decimal(row.amount_original)
            message = "Original and common currency are identical."
        elif conversion.supports(row.currency_original, row.currency_common):
            source = conversion.sources[row.currency_original]
            rate = conversion.lookup(row.currency_original, row.currency_common, row.invoice_date)
            if rate is None:
                message = f"No {source} EUR/{row.currency_original} rate on or before {row.invoice_date}."
            else:
                try:
                    value = Decimal(rate.rate)
                    if not value.is_finite() or value <= 0 or Decimal(rate.unit) != 1:
                        raise ValueError()
                    amount = conversion.calculate(row.amount_original, value, precision=64)
                    if amount >= Decimal("1000000000000000000"):
                        amount = None
                        raise ValueError()
                    message = f"Converted using {source} EUR/{row.currency_original} rate {rate.rate} from {rate.rate_date}."
                except (InvalidOperation, ValueError):
                    message = "Invalid local exchange rate or converted amount out of range."
        else:
            message = f"Unsupported conversion: {row.currency_original} → {row.currency_common}."
        return amount, message

    def process_ar_entry(self, identity):
        """Recalculate only amount_common, with one atomic transaction per invoice."""
        reference = None
        try:
            with self._write():
                row = self._get(OutgoingInvoiceORM, identity)
                reference = row.invoice_number
                amount, message = self._calculate_common_amount(row)
                if amount is None:
                    raise ReceivablesError(message)
                row.amount_common = format(amount, "f")
                self.db.flush()
                self.db.refresh(row)
                entry = self._invoice_read(row)
                trace = dict(tax_year=resolve_ar_tax_year(row),
                             fx_date_policy="invoice_date", fx_lookup_date=row.invoice_date,
                             fx_source=("same_currency" if row.currency_original == row.currency_common
                                        else LocalCurrencyConversion.sources[row.currency_original]),
                             amount_common=amount)
            return dict(id=identity, invoice_number=reference, status="processed",
                        message=message, entry=entry, trace=trace)
        except (ValueError, InvalidOperation) as exc:
            return dict(id=identity, invoice_number=reference, status="failed", message=str(exc))
        except Exception:
            logging.getLogger(__name__).exception("AR processing failed for %s", identity)
            return dict(id=identity, invoice_number=reference, status="failed",
                        message="Invoice processing failed; no changes saved.")

    def process_ar_entries(self):
        identities = list(self.db.scalars(select(OutgoingInvoiceORM.id).order_by(
            OutgoingInvoiceORM.invoice_date, OutgoingInvoiceORM.id)))
        self.db.commit()
        results = [self.process_ar_entry(identity) for identity in identities]
        for result in results:
            result.pop("entry", None)
        return dict(processed=sum(r["status"] == "processed" for r in results),
                    failed=sum(r["status"] == "failed" for r in results), invoices=results)

    def normalize_pending_invoices(self):
        """Explicit action only; no conversion during import, CRUD, or startup.

        Follow AP's local historical lookup and cent rounding, using invoice_date
        as the existing FX policy. The manually entered payment_date is independent
        and does not select the FX date in this workflow.
        """
        results = []
        with self._write():
            rows = self.db.scalars(select(OutgoingInvoiceORM).where(
                OutgoingInvoiceORM.amount_common.is_(None)
            ).order_by(OutgoingInvoiceORM.invoice_date, OutgoingInvoiceORM.id))
            for row in rows:
                amount, message = self._calculate_common_amount(row)
                if amount is not None:
                    row.amount_common = format(amount, "f")
                results.append(ArConversionResultSchema(
                    id=row.id, invoice_number=row.invoice_number,
                    status="converted" if amount is not None else "pending",
                    amount_common=amount, currency_common=row.currency_common, message=message))
            self.db.flush()
        return ArConversionReportSchema(
            converted=sum(item.status == "converted" for item in results),
            pending=sum(item.status == "pending" for item in results), invoices=results)

    def create_payment(self, payload: IncomingPaymentCreateSchema):
        with self._write():
            row = IncomingPaymentORM()
            self._apply(row, payload)
            self.db.add(row)
            self.db.flush()
            self.db.refresh(row)
            result = self._payment_read(row)
        return result

    def list_payments(self):
        return [self._payment_read(row) for row in self.db.scalars(select(IncomingPaymentORM).order_by(
            IncomingPaymentORM.payment_date.desc(), IncomingPaymentORM.id
        ))]

    def get_payment(self, identity):
        return self._payment_read(self._get(IncomingPaymentORM, identity))

    def update_payment(self, identity, payload: IncomingPaymentUpdateSchema):
        with self._write():
            row = self._get(IncomingPaymentORM, identity)
            current = {key: getattr(row, key) for key in IncomingPaymentCreateSchema.model_fields}
            merged = IncomingPaymentCreateSchema.model_validate({**current, **payload.model_dump(exclude_unset=True)})
            allocations = self._allocations(payment_id=row.id)
            if merged.amount < total(allocations):
                raise ReceivablesError("amount cannot be less than existing allocations")
            if allocations and merged.currency != row.currency:
                raise ReceivablesError("Cannot change currency while payment has allocations")
            self._apply(row, merged)
            self.db.flush()
            self.db.refresh(row)
            result = self._payment_read(row)
        return result

    def delete_incoming_payment(self, identity):
        """Remove only this payment and its allocations in one serialized write."""
        with self._write():
            payment = self._get(IncomingPaymentORM, identity)
            for allocation in self._allocations(payment_id=payment.id):
                self.db.delete(allocation)
            # RESTRICT requires child DELETEs before the parent DELETE. Flush is
            # not a commit: a later failure restores every allocation as well.
            self.db.flush()
            self.db.delete(payment)

    def create_allocation(self, payload: InvoicePaymentAllocationCreateSchema):
        with self._write():
            invoice = self._get(OutgoingInvoiceORM, payload.invoice_id)
            payment = self._get(IncomingPaymentORM, payload.payment_id)
            if payment.currency != invoice.currency:
                raise ReceivablesError("Invoice and payment currencies must match")
            if payload.amount_allocated > Decimal(invoice.gross_amount) - total(self._allocations(invoice_id=invoice.id)):
                raise ReceivablesError("Allocation exceeds invoice outstanding amount")
            if payload.amount_allocated > Decimal(payment.amount) - total(self._allocations(payment_id=payment.id)):
                raise ReceivablesError("Allocation exceeds payment remaining amount")
            row = InvoicePaymentAllocationORM()
            self._apply(row, payload)
            self.db.add(row)
            self.db.flush()
            self.db.refresh(row)
            result = InvoicePaymentAllocationReadSchema.model_validate(row)
        return result

    def delete_allocation(self, identity):
        with self._write():
            self.db.delete(self._get(InvoicePaymentAllocationORM, identity))
