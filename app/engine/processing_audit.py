"""Opt-in current-rule diagnostic, not persisted execution provenance.

Call in a stable rule configuration. Selection metadata is resolved after the
normal processor runs; this cannot reconstruct rules used by an earlier DB row.
"""
from dataclasses import dataclass
from decimal import Decimal

from app.domain import accounting_rules, deduction_calculation
from app.domain.historical_values import resolve_historical_value
from app.engine.accounting_entry_processor import AccountingEntryProcessor, CurrencyConversionResult
from app.schemas.accounting_entry_schema import AccountingEntryCreateSchema


@dataclass(frozen=True)
class ProcessingTrace:
    tax_year: int
    vat_treatment_rule: str
    vat_class: str | None
    vat_rate_percent: Decimal
    deductible_percent: Decimal
    deduction_rule: str | None
    conversion_path: str


def process_with_trace(payload: AccountingEntryCreateSchema, *,
                       conversion: CurrencyConversionResult | None = None):
    """Return (normal processed result, immutable current-rule diagnostic).

    Supplied conversion provenance is deliberately not guessed from currency.
    No database access, API changes, rule mutation, or additional monetary work.
    """
    result = AccountingEntryProcessor().process(payload, conversion=conversion)
    year = result.booking_year
    treatment = resolve_historical_value(
        accounting_rules.LEGACY_VAT_TREATMENT_COMPATIBILITY_HISTORY, year)
    # Only the known legacy domestic procedure promises to use this class lookup.
    vat_class = None
    if treatment is accounting_rules.resolve_vat_treatment_legacy and payload.tax_scope == 'domestic':
        vat_class = accounting_rules.get_vat_class(payload.category_code, tax_year=year)
    deduction_rule = None
    if result.amount_common is not None:
        deduction_rule = resolve_historical_value(
            deduction_calculation.LEGACY_DEDUCTION_CALCULATION_COMPATIBILITY_HISTORY,
            year).__name__
    trace = ProcessingTrace(
        tax_year=year, vat_treatment_rule=treatment.__name__, vat_class=vat_class,
        vat_rate_percent=result.vat_rate_percent,
        deductible_percent=result.deductible_percent, deduction_rule=deduction_rule,
        conversion_path=('supplied_conversion' if conversion is not None else
                         'same_currency' if result.conversion_status == 'not_required' else 'pending'),
    )
    return result, trace
