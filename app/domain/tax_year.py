"""AP tax-year policy boundary; see docs/accounting_rule_contract.md.

Current policy uses payment date. No invoice/accrual mode is implemented.
"""
from datetime import date
from typing import Protocol


class PaymentDatedEntry(Protocol):
    payment_date: date


def resolve_tax_year(entry: PaymentDatedEntry) -> int:
    """Resolve AP rule context from authoritative payment date, never stored Y."""
    return entry.payment_date.year
