"""Read-only report contract; Pydantic JSON serializes Decimal as exact strings."""
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class SummaryReadSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class SummaryWarningReadSchema(SummaryReadSchema):
    code: str
    count: int
    message: str


class ApSummaryGroupReadSchema(SummaryReadSchema):
    entry_type: str
    category_code: str
    tax_scope: str
    currency_common: str | None
    record_count: int
    incomplete_count: int
    amount_common: Decimal | None
    vat_amount: Decimal | None
    deductible_amount: Decimal | None
    deductible_vat_amount: Decimal | None


class ArCurrencyComponentsReadSchema(SummaryReadSchema):
    currency_original: str
    event_count: int
    recognized_gross_original: Decimal
    known_net_original: Decimal | None
    known_vat_original: Decimal | None
    missing_net_count: int
    missing_vat_count: int


class YearlyAccountingSummaryReadSchema(SummaryReadSchema):
    tax_year: int
    report_currency: str | None
    common_currencies: tuple[str, ...]
    ap_included_count: int
    ap_excluded_count: int
    ap_non_expense_count: int
    ap_unassigned_year_count: int
    ar_event_count: int
    ar_common_excluded_count: int
    ar_invoices_without_events: int
    recognized_ar_gross_common: Decimal | None
    ap_expense_deductible_gross_common: Decimal | None
    gross_basis_result: Decimal | None
    ap_deductible_vat_common: Decimal | None
    ar_components_by_original_currency: tuple[ArCurrencyComponentsReadSchema, ...]
    ap_breakdown: tuple[ApSummaryGroupReadSchema, ...]
    completeness: Literal["complete", "incomplete"]
    warnings: tuple[SummaryWarningReadSchema, ...]
