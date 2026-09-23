# app/engine/accounting_entry_processor.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from app.domain.accounting_rules import (
    get_deductible_percent,
    get_vat_rate_percent,
    get_writeoff_method,
)
from app.schemas.accounting_entry_schema import AccountingEntryCreateSchema
from app.domain.tax_year import resolve_tax_year
from app.domain.deduction_calculation import calculate_deductions


CENT = Decimal("0.01")


@dataclass(frozen=True)
class ProcessedAccountingEntry:
    """=== engine class ====
    Immutable processed accounting-entry data ready for persistence.
    === by Sziller & ChatGPT ==="""

    entry_type: str
    category_code: str
    tax_scope: str
    counterparty_name: str
    payment_method: str
    payment_date: date
    booking_year: int

    has_invoice: bool
    invoice_number: str | None
    invoice_date: date | None

    amount_original: Decimal
    currency_original: str
    amount_common: Decimal
    currency_common: str

    exchange_rate: Decimal | None
    exchange_rate_date: date | None

    vat_rate_percent: Decimal
    vat_amount: Decimal

    deductible_percent: Decimal
    deductible_amount: Decimal
    deductible_vat_amount: Decimal
    writeoff_method: str

    remarks: str | None
    tags: list[str]

    source_filename: str | None


class AccountingEntryProcessor:
    """=== engine class ====
    Validate business rules and calculate derived accounting-entry fields.
    === by Sziller & ChatGPT ==="""

    currency_common: str = "EUR"

    def process(self, payload: AccountingEntryCreateSchema) -> ProcessedAccountingEntry:
        """=== engine function ====
        Convert raw API input into validated and calculated accounting-entry data.
        === by Sziller & ChatGPT ==="""
        self._validate_invoice_rules(payload)
        tax_year = resolve_tax_year(payload)

        amount_common = self._calculate_common_amount(payload)
        vat_rate_percent = get_vat_rate_percent(
            category_code=payload.category_code,
            tax_scope=payload.tax_scope,
            tax_year=tax_year,
        )

        vat_amount = self._calculate_vat_from_gross(
            gross_amount=amount_common,
            vat_rate_percent=vat_rate_percent,
        )

        deductible_percent = get_deductible_percent(payload.category_code, tax_year=tax_year)

        deductions = calculate_deductions(
            tax_year=tax_year, amount_common=amount_common,
            vat_amount=vat_amount, deductible_percent=deductible_percent,
        )
        deductible_amount = deductions.deductible_amount
        deductible_vat_amount = deductions.deductible_vat_amount

        writeoff_method = get_writeoff_method(payload.category_code, tax_year=tax_year)

        return ProcessedAccountingEntry(
            entry_type=payload.entry_type,
            category_code=payload.category_code,
            tax_scope=payload.tax_scope,
            counterparty_name=payload.counterparty_name,
            payment_method=payload.payment_method,
            payment_date=payload.payment_date,
            booking_year=tax_year,
            has_invoice=payload.has_invoice,
            invoice_number=payload.invoice_number,
            invoice_date=payload.invoice_date,
            amount_original=payload.amount_original,
            currency_original=payload.currency_original,
            amount_common=amount_common,
            currency_common=self.currency_common,
            exchange_rate=None,
            exchange_rate_date=None,
            vat_rate_percent=vat_rate_percent,
            vat_amount=vat_amount,
            deductible_percent=deductible_percent,
            deductible_amount=deductible_amount,
            deductible_vat_amount=deductible_vat_amount,
            writeoff_method=writeoff_method,
            remarks=payload.remarks,
            tags=payload.tags,
            source_filename=payload.source_filename,
        )

    def _validate_invoice_rules(self, payload: AccountingEntryCreateSchema) -> None:
        """=== engine function ====
        Validate consistency between invoice flag, invoice number, and invoice date.
        === by Sziller & ChatGPT ==="""
        if payload.has_invoice:
            if payload.invoice_date is None:
                raise ValueError("invoice_date is required when has_invoice is true")

        if not payload.has_invoice:
            if payload.invoice_number:
                raise ValueError("invoice_number must be empty when has_invoice is false")

            if payload.invoice_date is not None:
                raise ValueError("invoice_date must be empty when has_invoice is false")

    def _calculate_common_amount(self, payload: AccountingEntryCreateSchema) -> Decimal:
        """=== engine function ====
        Convert the original amount into common reporting currency.
        === by Sziller & ChatGPT ==="""
        if payload.currency_original == self.currency_common:
            return self._money(payload.amount_original)

        raise ValueError(
            f"Currency conversion not implemented yet: "
            f"{payload.currency_original} -> {self.currency_common}"
        )

    @staticmethod
    def _calculate_vat_from_gross(
        gross_amount: Decimal,
        vat_rate_percent: Decimal,
    ) -> Decimal:
        """=== engine function ====
        Calculate VAT amount from a gross amount and VAT percentage.
        === by Sziller & ChatGPT ==="""
        if vat_rate_percent == Decimal("0"):
            return Decimal("0.00")

        rate = vat_rate_percent / Decimal("100")
        vat = gross_amount * (Decimal("1") - (Decimal("1") / (Decimal("1") + rate)))

        return AccountingEntryProcessor._money(vat)

    @staticmethod
    def _money(value: Decimal) -> Decimal:
        """=== engine function ====
        Round a Decimal monetary value to cents.
        === by Sziller & ChatGPT ==="""
        return value.quantize(CENT, rounding=ROUND_HALF_UP)
