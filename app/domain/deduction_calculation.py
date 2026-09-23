"""Retained deduction behavior; inputs are already resolved by the caller."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from app.domain.historical_values import resolve_historical_value


@dataclass(frozen=True)
class DeductionResult:
    deductible_amount: Decimal
    deductible_vat_amount: Decimal


def calculate_deductions_legacy(*, amount_common: Decimal, vat_amount: Decimal,
                                 deductible_percent: Decimal) -> DeductionResult:
    """Apply the shared percentage to gross and already-rounded VAT, then cents."""
    return DeductionResult(
        (amount_common * deductible_percent / Decimal('100')).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP),
        (vat_amount * deductible_percent / Decimal('100')).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP),
    )


# Year 1 is legacy compatibility coverage, not verified legislative history.
LEGACY_DEDUCTION_CALCULATION_COMPATIBILITY_HISTORY = {1: calculate_deductions_legacy}


def calculate_deductions(*, tax_year: int, amount_common: Decimal, vat_amount: Decimal,
                         deductible_percent: Decimal) -> DeductionResult:
    rule = resolve_historical_value(LEGACY_DEDUCTION_CALCULATION_COMPATIBILITY_HISTORY, tax_year)
    return rule(amount_common=amount_common, vat_amount=vat_amount,
                deductible_percent=deductible_percent)
