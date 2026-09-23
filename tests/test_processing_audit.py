from datetime import date
from decimal import Decimal
import unittest
from unittest.mock import patch

from app.domain import accounting_rules, deduction_calculation
from app.engine.accounting_entry_processor import AccountingEntryProcessor, CurrencyConversionResult
from app.engine.processing_audit import process_with_trace
from app.schemas.accounting_entry_schema import AccountingEntryCreateSchema


class ProcessingAuditTests(unittest.TestCase):
    def payload(self, **changes):
        values = dict(category_code='bewirtung', counterparty_name='Test',
                      payment_date=date(2026, 2, 10), has_invoice=True,
                      invoice_date=date(2024, 1, 1), amount_original='119', currency_original='EUR')
        values.update(changes)
        return AccountingEntryCreateSchema(**values)

    def test_trace_preserves_result_and_is_repeatable(self):
        for year in (2024, 2026):
            payload = self.payload(payment_date=date(year, 2, 10))
            result, trace = process_with_trace(payload)
            self.assertEqual(result, AccountingEntryProcessor().process(payload))
            self.assertEqual((result, trace), process_with_trace(payload))
            self.assertEqual(trace.tax_year, year)
            self.assertEqual(trace.vat_treatment_rule, 'resolve_vat_treatment_legacy')
            self.assertEqual(trace.vat_class, 'standard')
            self.assertEqual(trace.vat_rate_percent, Decimal('19'))
            self.assertEqual(trace.deductible_percent, Decimal('70'))
            self.assertEqual(trace.deduction_rule, 'calculate_deductions_legacy')
            self.assertEqual(trace.conversion_path, 'same_currency')
            self.assertEqual(result.deductible_vat_amount, Decimal('13.30'))

    def test_bypassed_and_supplied_stages_are_not_misrepresented(self):
        _, trace = process_with_trace(self.payload(tax_scope='eu'))
        self.assertIsNone(trace.vat_class)
        self.assertEqual(trace.vat_rate_percent, 0)
        payload = self.payload(currency_original='USD')
        _, trace = process_with_trace(payload)
        self.assertIsNone(trace.deduction_rule)
        self.assertEqual(trace.conversion_path, 'pending')
        conversion = CurrencyConversionResult(Decimal('100'), Decimal('1.19'),
                                              date(2026, 2, 9), 'resolved', 'Test conversion')
        result, trace = process_with_trace(payload, conversion=conversion)
        self.assertEqual(result, AccountingEntryProcessor().process(payload, conversion=conversion))
        self.assertEqual(trace.conversion_path, 'supplied_conversion')

    def test_dispatch_uses_payment_year_and_fresh_dependencies(self):
        calls = []

        def test_treatment(**inputs):
            calls.append(('treatment', inputs['tax_year']))
            return Decimal('10')

        def test_deductions(**inputs):
            calls.append(('deductions', inputs))
            return deduction_calculation.calculate_deductions_legacy(**inputs)

        with patch.dict(accounting_rules.LEGACY_VAT_TREATMENT_COMPATIBILITY_HISTORY,
                        {2026: test_treatment}), patch.dict(
                deduction_calculation.LEGACY_DEDUCTION_CALCULATION_COMPATIBILITY_HISTORY,
                {2026: test_deductions}):
            result, trace = process_with_trace(self.payload())
        self.assertEqual(trace.vat_treatment_rule, 'test_treatment')
        self.assertEqual(trace.deduction_rule, 'test_deductions')
        self.assertIsNone(trace.vat_class)  # Unknown procedure's internals aren't inferred.
        self.assertEqual(calls, [('treatment', 2026), ('deductions', dict(
            amount_common=Decimal('119.00'), vat_amount=Decimal('10.82'),
            deductible_percent=Decimal('70')))])
        self.assertEqual(result.deductible_vat_amount, Decimal('7.57'))
