"""Current IST-oriented receipt interpretation, not historical tax legislation."""
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Literal

from app.domain.ar_tax_year import resolve_ar_tax_year
from app.domain.ar_amount_allocation import allocate_invoice_amounts


@dataclass(frozen=True)
class ArInvoiceRecognitionFacts:
    invoice_id: str
    gross_amount: Decimal
    currency_original: str
    payment_date: date | None
    net_amount: Decimal | None = None
    vat_amount: Decimal | None = None
    amount_common: Decimal | None = None


@dataclass(frozen=True)
class ArAllocationRecognitionFacts:
    invoice_id: str
    allocation_id: str
    payment_id: str
    amount_allocated: Decimal
    payment_date: date
    currency: str


@dataclass(frozen=True)
class ArRecognitionEvent:
    invoice_id: str
    recognition_date: date
    tax_year: int
    amount_original: Decimal
    currency_original: str
    source: Literal['allocation', 'manual_invoice_payment']
    payment_id: str | None = None
    allocation_id: str | None = None
    net_amount_original: Decimal | None = None
    vat_amount_original: Decimal | None = None
    amount_common: Decimal | None = None


def resolve_ar_recognition_events(
    invoice: ArInvoiceRecognitionFacts,
    allocations: tuple[ArAllocationRecognitionFacts, ...],
) -> tuple[ArRecognitionEvent, ...]:
    """Allocations exclusively win; otherwise manual full receipt or no event.

    Inputs are validated persisted facts converted to Decimal by the loader.
    Accounting shares use existing invoice totals; no FX or database access.
    """
    if allocations:
        events = []
        for allocation in allocations:
            if allocation.invoice_id != invoice.invoice_id:
                raise ValueError('Allocation does not belong to invoice')
            if allocation.currency != invoice.currency_original:
                raise ValueError('Invoice and payment currencies must match')
            events.append(ArRecognitionEvent(
                invoice_id=invoice.invoice_id,
                recognition_date=allocation.payment_date,
                tax_year=allocation.payment_date.year,
                amount_original=allocation.amount_allocated,
                currency_original=invoice.currency_original,
                source='allocation', payment_id=allocation.payment_id,
                allocation_id=allocation.allocation_id,
            ))
        events.sort(key=lambda event: (
            event.recognition_date, event.payment_id, event.allocation_id))
        shares = allocate_invoice_amounts(
            gross_total=invoice.gross_amount, net_total=invoice.net_amount,
            vat_total=invoice.vat_amount, common_total=invoice.amount_common,
            recognized_gross_amounts=tuple(event.amount_original for event in events))
        return tuple(replace(event, net_amount_original=share.net_amount_original,
                             vat_amount_original=share.vat_amount_original,
                             amount_common=share.amount_common)
                     for event, share in zip(events, shares))
    if invoice.payment_date is None:
        return ()
    return (ArRecognitionEvent(
        invoice_id=invoice.invoice_id, recognition_date=invoice.payment_date,
        tax_year=resolve_ar_tax_year(invoice), amount_original=invoice.gross_amount,
        currency_original=invoice.currency_original, source='manual_invoice_payment',
        net_amount_original=invoice.net_amount, vat_amount_original=invoice.vat_amount,
        amount_common=invoice.amount_common,
    ),)
