"""Proportional shares of existing invoice values; no VAT inference or FX."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, localcontext


@dataclass(frozen=True)
class ArAccountingShare:
    net_amount_original: Decimal | None
    vat_amount_original: Decimal | None
    amount_common: Decimal | None


def _component_quantum(total: Decimal) -> Decimal:
    """Use cents unless significant fractional digits require a finer quantum.

    Inspect the coefficient without context-sensitive normalize()/rounding.
    """
    if total.is_zero():
        return Decimal('0.01')
    _, digits, exponent = total.as_tuple()
    for digit in reversed(digits):
        if digit != 0:
            break
        exponent += 1
    return Decimal((0, (1,), min(-2, exponent)))


def allocate_invoice_amounts(*, gross_total: Decimal, net_total: Decimal | None,
                            vat_total: Decimal | None, common_total: Decimal | None,
                            recognized_gross_amounts: tuple[Decimal, ...]
                            ) -> tuple[ArAccountingShare, ...]:
    """Caller supplies event order. Shares are cumulative-target differences.

    Each component has one fixed, precision-aware HALF_UP quantum. Full settlement
    uses the exact stored total as its final target. No gross rounding or clipping.
    """
    with localcontext() as context:
        context.prec = 64  # Existing AR accounting calculation precision.
        if not gross_total.is_finite() or gross_total <= 0:
            raise ValueError('Invoice gross must be finite and positive')
        if any(not amount.is_finite() or amount <= 0 for amount in recognized_gross_amounts):
            raise ValueError('Recognized gross must be finite and positive')
        recognized = sum(recognized_gross_amounts, Decimal('0'))
        if recognized > gross_total:
            raise ValueError('Recognized gross exceeds invoice gross')
        totals = (net_total, vat_total, common_total)
        if any(value is not None and (not value.is_finite() or value < 0) for value in totals):
            raise ValueError('Invoice accounting totals must be finite and non-negative')
        if recognized_gross_amounts == (gross_total,):
            return (ArAccountingShare(*totals),)
        quanta = tuple(_component_quantum(total) if total is not None else None for total in totals)
        previous_targets = [Decimal('0')] * 3
        cumulative_gross = Decimal('0')
        shares = []
        for amount in recognized_gross_amounts:
            cumulative_gross += amount
            values = []
            for component, total in enumerate(totals):
                if total is None:
                    values.append(None)
                    continue
                target = (total if cumulative_gross == gross_total else
                          (total * cumulative_gross / gross_total).quantize(
                              quanta[component], rounding=ROUND_HALF_UP))
                values.append(target - previous_targets[component])
                previous_targets[component] = target
            shares.append(ArAccountingShare(*values))
        return tuple(shares)
