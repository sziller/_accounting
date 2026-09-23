"""Retained VAT behavior selected independently of static parameter histories."""
from datetime import date
from decimal import Decimal
import unittest
from unittest.mock import patch
from app.domain.accounting_rules import (
    LEGACY_VAT_TREATMENT_COMPATIBILITY_HISTORY as RULES,
    resolve_vat_treatment_legacy, get_vat_rate_percent,
)
from app.domain.historical_values import resolve_historical_value, HistoricalValueUnavailable
from app.engine.accounting_entry_processor import AccountingEntryProcessor
from app.schemas.accounting_entry_schema import AccountingEntryCreateSchema


class HistoricalVatTreatmentTests(unittest.TestCase):
    def test_only_retained_compatibility_rule_is_registered(self):
        self.assertEqual(RULES, {1: resolve_vat_treatment_legacy})
        for category, expected in [('buro','19'), ('fachliteratur','7'), ('raum','0')]:
            self.assertEqual(get_vat_rate_percent(category, 'domestic', tax_year=2026), Decimal(expected))
        for scope in ('eu','third_country','not_applicable'):
            self.assertEqual(get_vat_rate_percent('unknown', scope, tax_year=2026), Decimal('0'))
        with self.assertRaisesRegex(ValueError, '^Unknown category code: unknown$'):
            get_vat_rate_percent('unknown', 'domestic', tax_year=2026)

    def test_callable_change_points_and_uncovered_year(self):
        def rule_a(**kwargs): return Decimal('19')
        def rule_b(**kwargs): return Decimal('7')
        history = {2000: rule_a, 2030: rule_b}
        for year, expected in [(2000,rule_a), (2029,rule_a), (2030,rule_b), (2040,rule_b)]:
            self.assertIs(resolve_historical_value(history, year), expected)
        with self.assertRaises(HistoricalValueUnavailable):
            resolve_historical_value(history, 1999)
        self.assertEqual(history, {2000:rule_a, 2030:rule_b})

    def test_processor_dispatches_by_payment_year_with_narrow_arguments(self):
        calls = []
        def rule_a(*, category_code, tax_scope, tax_year):
            calls.append(('a',category_code,tax_scope,tax_year))
            return resolve_vat_treatment_legacy(category_code=category_code, tax_scope=tax_scope, tax_year=tax_year)
        def rule_b(*, category_code, tax_scope, tax_year):
            calls.append(('b',category_code,tax_scope,tax_year))
            return Decimal('7')  # Artificial test behavior only.
        with patch.dict(RULES, {2000:rule_a, 2030:rule_b}, clear=True):
            for year, invoice_year, name, rate in [(2029,2001,'a','19'), (2029,2040,'a','19'), (2030,2001,'b','7'), (2040,2001,'b','7')]:
                payload = AccountingEntryCreateSchema(category_code='buro', counterparty_name='Test',
                    payment_date=date(year,2,10), invoice_date=date(invoice_year,1,1),
                    amount_original='119.00', currency_original='EUR')
                result = AccountingEntryProcessor().process(payload)
                self.assertEqual(calls[-1], (name,'buro','domestic',year))
                self.assertEqual(result.vat_rate_percent, Decimal(rate))
                self.assertEqual(result, AccountingEntryProcessor().process(payload))
                if name == 'a':
                    self.assertEqual(str(result.vat_amount), '19.00')
