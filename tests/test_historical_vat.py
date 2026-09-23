"""Change-point semantics and unchanged production VAT outputs."""
from datetime import date
from decimal import Decimal
import unittest
from unittest.mock import patch
from app.domain.historical_values import resolve_historical_value, HistoricalValueUnavailable
from app.domain.accounting_rules import (
    VAT_RATE_HISTORY, LEGACY_VAT_COMPATIBILITY_HISTORY, get_vat_rate_percent,
)
from app.engine.accounting_entry_processor import AccountingEntryProcessor
from app.schemas.accounting_entry_schema import AccountingEntryCreateSchema


class HistoricalVatTests(unittest.TestCase):
    def test_production_history_is_explicitly_legacy_compatibility(self):
        self.assertIs(VAT_RATE_HISTORY, LEGACY_VAT_COMPATIBILITY_HISTORY)
        expected = {'standard': '19', 'reduced': '7', 'none': '0',
                    'not_applicable': '0', 'multi_year': '19'}
        for vat_class, value in expected.items():
            history = LEGACY_VAT_COMPATIBILITY_HISTORY[vat_class]
            self.assertEqual(history, {1: Decimal(value)})
            # Actual current AP payment years, not legislative coverage assertions.
            for year in (2024, 2026):
                self.assertEqual(resolve_historical_value(history, year), Decimal(value))

    def test_unsorted_change_points_exact_values_and_no_mutation(self):
        history = {2028: Decimal('20.0000'), 2007: Decimal('19.0000'), 2030: Decimal('21.1234567890123456789')}
        before = history.copy()
        for year, point in [(2007,2007), (2026,2007), (2028,2028), (2029,2028), (2035,2030)]:
            self.assertIs(resolve_historical_value(history, year), history[point])
        self.assertEqual(history, before)
        self.assertEqual(resolve_historical_value({2021:'label'}, 2022), 'label')

    def test_before_first_and_empty_history_fail(self):
        for history in ({2007: Decimal('19')}, {}):
            with self.assertRaises(HistoricalValueUnavailable):
                resolve_historical_value(history, 2006)

    def test_production_rates_unchanged_across_supported_date_range(self):
        for year in (1, 2000, 2018, 2021, 2024, 2026, 9999):
            for category, expected in [('buro','19'), ('fachliteratur','7'), ('raum','0'),
                    ('umsatzsteuer-vorauszahlung','0'), ('werkzeug-mehrjaehrige-abschreibung','19')]:
                self.assertEqual(str(get_vat_rate_percent(category, 'domestic', tax_year=year)), expected)
            for scope in ('eu','third_country','not_applicable'):
                self.assertEqual(get_vat_rate_percent('buro', scope, tax_year=year), Decimal('0'))

    def test_processor_uses_payment_year_not_invoice_year(self):
        with patch.dict(VAT_RATE_HISTORY, {'standard': {2021: Decimal('19'), 2028: Decimal('20')}}):
            for payment_year, invoice_year, expected in [(2026,2028,'19'), (2026,2020,'19'), (2028,2020,'20')]:
                payload = AccountingEntryCreateSchema(category_code='buro', counterparty_name='Test',
                    payment_date=date(payment_year, 2, 10), invoice_date=date(invoice_year, 1, 1),
                    amount_original='119.00', currency_original='EUR')
                result = AccountingEntryProcessor().process(payload)
                self.assertEqual(str(result.vat_rate_percent), expected)
                self.assertEqual(result.booking_year, payment_year)
                if payment_year == 2026:
                    self.assertEqual(str(result.vat_amount), '19.00')
