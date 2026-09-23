"""Historical deduction parameters preserve the established gross/VAT formulas."""
from datetime import date
from decimal import Decimal
import unittest
from unittest.mock import patch
from app.domain.accounting_rules import (
    LEGACY_CATEGORY_DEDUCTIBILITY_COMPATIBILITY_HISTORY as HISTORY,
    get_deductible_percent, get_writeoff_method,
)
from app.domain.historical_values import HistoricalValueUnavailable
from app.engine.accounting_entry_processor import AccountingEntryProcessor
from app.schemas.accounting_entry_schema import AccountingEntryCreateSchema


class HistoricalDeductibilityTests(unittest.TestCase):
    def test_compatibility_percentages_and_absent_category_fallback(self):
        expected = {'n/a':'100', 'werkzeug-mehrjaehrige-abschreibung':'33.333',
                    'auto':'0', 'raum':'100', 'bewirtung':'70', 'hausratversicherung':'50',
                    'haftpflichtversicherung':'50', 'festnetz':'50'}
        self.assertEqual(set(HISTORY), set(expected))
        for year in (1, 2018, 2024, 2026, 9999):
            for category, percent in expected.items():
                self.assertEqual(HISTORY[category], {1: Decimal(percent)})
                self.assertEqual(str(get_deductible_percent(category, tax_year=year)), percent)
            for category in ('buro', 'krankenversicherung', 'not-in-table'):
                self.assertEqual(get_deductible_percent(category, tax_year=year), Decimal('100'))

    def test_explicit_history_is_resolved_and_never_falls_back(self):
        with patch.dict(HISTORY, {'bewirtung': {2020: Decimal('70'), 2028: Decimal('60')}}):
            for year, value in [(2020,'70'), (2027,'70'), (2028,'60'), (2035,'60')]:
                self.assertEqual(get_deductible_percent('bewirtung', tax_year=year), Decimal(value))
            with self.assertRaises(HistoricalValueUnavailable):
                get_deductible_percent('bewirtung', tax_year=2019)
        with patch.dict(HISTORY, {'bewirtung': {}}):
            with self.assertRaises(HistoricalValueUnavailable):
                get_deductible_percent('bewirtung', tax_year=2026)

    def process(self, category, payment_year=2026, invoice_year=2020):
        return AccountingEntryProcessor().process(AccountingEntryCreateSchema(
            category_code=category, counterparty_name='Test', payment_date=date(payment_year, 2, 10),
            invoice_date=date(invoice_year, 1, 1), amount_original='119.00', currency_original='EUR'))

    def test_existing_amounts_vat_and_writeoff_unchanged(self):
        for category, amount, vat, method in [
            ('bewirtung','83.30','13.30','partial'), ('festnetz','59.50','0.00','partial'),
            ('hausratversicherung','59.50','0.00','partial'), ('haftpflichtversicherung','59.50','0.00','partial'),
            ('auto','0.00','0.00','none'), ('werkzeug-mehrjaehrige-abschreibung','39.67','6.33','multi_year'),
            ('buro','119.00','19.00','immediate')]:
            result = self.process(category)
            self.assertEqual(str(result.deductible_amount), amount)
            self.assertEqual(str(result.deductible_vat_amount), vat)
            self.assertEqual(result.writeoff_method, method)
            self.assertEqual(result, self.process(category))

    def test_payment_year_selects_history_invoice_year_does_not(self):
        with patch.dict(HISTORY, {'bewirtung': {2020: Decimal('70'), 2028: Decimal('60')}}):
            for payment_year, invoice_year, percent, amount, vat in [
                (2026,2020,'70','83.30','13.30'), (2026,2028,'70','83.30','13.30'),
                (2028,2020,'60','71.40','11.40')]:
                result = self.process('bewirtung', payment_year, invoice_year)
                self.assertEqual(str(result.deductible_percent), percent)
                self.assertEqual(str(result.deductible_amount), amount)
                self.assertEqual(str(result.deductible_vat_amount), vat)
