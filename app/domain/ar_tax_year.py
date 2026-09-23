"""Invoice-level manual-context resolver, not general AR recognition.

Allocation recognition uses each parent payment date instead. Independent of FX.
"""
from datetime import date
from typing import Protocol


class ReceiptDatedInvoice(Protocol):
    payment_date: date | None


def resolve_ar_tax_year(invoice: ReceiptDatedInvoice) -> int | None:
    """None means unresolved. Future SOLL policy belongs here, not in callers."""
    return invoice.payment_date.year if invoice.payment_date is not None else None
