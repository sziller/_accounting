"""Retained deduction behavior across every AP recalculation path."""
from datetime import date
from decimal import Decimal
import unittest
from unittest.mock import patch

from app.domain.deduction_calculation import (
    DeductionResult, calculate_deductions, calculate_deductions_legacy,
    LEGACY_DEDUCTION_CALCULATION_COMPATIBILITY_HISTORY as HISTORY,
)
from app.engine import AccountingEntryProcessor as OlderProcessor
from app.engine.accounting_entry_processor import AccountingEntryProcessor
from app.schemas.accounting_entry_schema import AccountingEntryCreateSchema
from app.services.conversion_service import ConversionService
from tests.test_invoice_number_policy import raw_row


class HistoricalDeductionCalculationTests(unittest.TestCase):
    def payload(self, year=2026, **changes):
        values = dict(category_code='bewirtung', counterparty_name='Test',
                      payment_date=date(year, 2, 10), has_invoice=False,
                      invoice_date=None, amount_original='119.00', currency_original='EUR')
        values.update(changes)
        return AccountingEntryCreateSchema(**values)

    def test_compatibility_registration_and_exact_results(self):
        self.assertEqual(HISTORY, {1: calculate_deductions_legacy})
        for percent, gross, vat in [('70', '83.30', '13.30'),
                                    ('33.333', '39.67', '6.33'),
                                    ('0', '0.00', '0.00'), ('100', '119.00', '19.00')]:
            result = calculate_deductions(tax_year=2026, amount_common=Decimal('119'),
                                          vat_amount=Decimal('19'), deductible_percent=Decimal(percent))
            self.assertEqual(result, DeductionResult(Decimal(gross), Decimal(vat)))

    def test_vat_is_rounded_before_percentage_and_rounded_again(self):
        # Raw VAT is ~0.006386; applying 70% before rounding would give 0.00.
        for processor in (AccountingEntryProcessor(), OlderProcessor()):
            result = processor.process(self.payload(amount_original='0.04'))
            self.assertEqual(result.vat_amount, Decimal('0.01'))
            self.assertEqual(result.deductible_amount, Decimal('0.03'))
            self.assertEqual(result.deductible_vat_amount, Decimal('0.01'))

    def test_scopes_and_invoice_existence_preserved(self):
        for scope in ('domestic', 'eu', 'third_country', 'not_applicable'):
            for processor in (AccountingEntryProcessor(), OlderProcessor()):
                without = processor.process(self.payload(tax_scope=scope))
                with_invoice = processor.process(self.payload(
                    tax_scope=scope, has_invoice=True, invoice_date=date(2020, 1, 1)))
                for field in ('vat_amount', 'deductible_amount', 'deductible_vat_amount'):
                    self.assertEqual(getattr(without, field), getattr(with_invoice, field))
                self.assertEqual(without.deductible_amount, Decimal('83.30'))
                self.assertEqual(without.deductible_vat_amount,
                                 Decimal('13.30') if scope == 'domestic' else Decimal('0.00'))

    def test_payment_year_dispatch_in_all_three_callers(self):
        calls = []

        def alternate_test_rule(**inputs):
            calls.append(inputs)
            return DeductionResult(Decimal('12.34'), Decimal('5.67'))

        with patch.dict(HISTORY, {2000: calculate_deductions_legacy,
                                  2030: alternate_test_rule}, clear=True):
            for year in (2029, 2030, 2040):
                expected = Decimal('83.30') if year == 2029 else Decimal('12.34')
                for processor in (AccountingEntryProcessor(), OlderProcessor()):
                    result = processor.process(self.payload(
                        year, has_invoice=True, invoice_date=date(2020, 1, 1)))
                    self.assertEqual(result.deductible_amount, expected)
                row = raw_row(None)
                row.payment_date = date(year, 2, 10)
                row.category_code = 'bewirtung'
                row.amount_common = '119.00'
                row.vat_amount = row.deductible_amount = row.deductible_vat_amount = '999'
                ConversionService(None)._recalculate_derived_fields(row)
                self.assertEqual(Decimal(row.deductible_amount), expected)
                self.assertEqual(Decimal(row.vat_amount), Decimal('19.00'))
                self.assertEqual(Decimal(row.deductible_vat_amount),
                                 Decimal('13.30') if year == 2029 else Decimal('5.67'))
        self.assertEqual(len(calls), 6)
        for inputs in calls:
            self.assertEqual(inputs, dict(amount_common=Decimal('119.00'),
                                         vat_amount=Decimal('19.00'), deductible_percent=Decimal('70')))
