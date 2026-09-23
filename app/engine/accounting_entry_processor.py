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
class CurrencyConversionResult:
    """=== engine class ====
    Represent the result of common-currency conversion.
    === by Sziller & ChatGPT ==="""

    amount_common: Decimal | None
    exchange_rate: Decimal | None
    exchange_rate_date: date | None
    conversion_status: str
    conversion_note: str | None


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
    amount_common: Decimal | None
    currency_common: str

    exchange_rate: Decimal | None
    exchange_rate_date: date | None

    vat_rate_percent: Decimal
    vat_amount: Decimal | None

    deductible_percent: Decimal
    deductible_amount: Decimal | None
    deductible_vat_amount: Decimal | None
    writeoff_method: str

    remarks: str | None
    tags: list[str]

    source_filename: str | None

    conversion_status: str
    conversion_note: str | None


class AccountingEntryProcessor:
    """=== engine class ====
    Validate business rules and calculate derived accounting-entry fields.
    === by Sziller & ChatGPT ==="""

    currency_common: str = "EUR"

    def process(self, payload: AccountingEntryCreateSchema, *,
                conversion: CurrencyConversionResult | None = None) -> ProcessedAccountingEntry:
        """=== engine function ====
        Convert raw API input into validated and calculated accounting-entry data.
        === by Sziller & ChatGPT ==="""
        self._validate_invoice_rules(payload)
        tax_year = resolve_tax_year(payload)

        conversion = conversion if conversion is not None else self._convert_to_common_currency(payload)

        vat_rate_percent = get_vat_rate_percent(
            category_code=payload.category_code,
            tax_scope=payload.tax_scope,
            tax_year=tax_year,
        )

        deductible_percent = get_deductible_percent(payload.category_code, tax_year=tax_year)
        writeoff_method = get_writeoff_method(payload.category_code, tax_year=tax_year)

        if conversion.amount_common is None:
            vat_amount = None
            deductible_amount = None
            deductible_vat_amount = None
        else:
            vat_amount = self._calculate_vat_from_gross(
                gross_amount=conversion.amount_common,
                vat_rate_percent=vat_rate_percent,
            )

            deductions = calculate_deductions(
                tax_year=tax_year, amount_common=conversion.amount_common,
                vat_amount=vat_amount, deductible_percent=deductible_percent,
            )
            deductible_amount = deductions.deductible_amount
            deductible_vat_amount = deductions.deductible_vat_amount

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
            amount_common=conversion.amount_common,
            currency_common=self.currency_common,
            exchange_rate=conversion.exchange_rate,
            exchange_rate_date=conversion.exchange_rate_date,
            vat_rate_percent=vat_rate_percent,
            vat_amount=vat_amount,
            deductible_percent=deductible_percent,
            deductible_amount=deductible_amount,
            deductible_vat_amount=deductible_vat_amount,
            writeoff_method=writeoff_method,
            remarks=payload.remarks,
            tags=payload.tags,
            source_filename=payload.source_filename,
            conversion_status=conversion.conversion_status,
            conversion_note=conversion.conversion_note,
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

    def _convert_to_common_currency(
        self,
        payload: AccountingEntryCreateSchema,
    ) -> CurrencyConversionResult:
        """=== engine function ====
        Convert original amount into common currency or mark conversion as pending.
        === by Sziller & ChatGPT ==="""
        if payload.currency_original == self.currency_common:
            return CurrencyConversionResult(
                amount_common=self._money(payload.amount_original),
                exchange_rate=None,
                exchange_rate_date=None,
                conversion_status="not_required",
                conversion_note=None,
            )

        return CurrencyConversionResult(
            amount_common=None,
            exchange_rate=None,
            exchange_rate_date=payload.payment_date,
            conversion_status="pending",
            conversion_note=(
                f"Missing historical exchange rate for "
                f"{payload.currency_original}->{self.currency_common} "
                f"on {payload.payment_date}."
            ),
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
