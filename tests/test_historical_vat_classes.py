"""Independent category classification and VAT-rate histories."""
from datetime import date
from decimal import Decimal
import unittest
from unittest.mock import patch
from app.domain.accounting_rules import (
    LEGACY_CATEGORY_VAT_CLASS_COMPATIBILITY_HISTORY as CLASSES,
    VAT_RATE_HISTORY, get_vat_class, get_vat_rate_percent,
)
from app.domain.historical_values import HistoricalValueUnavailable
from app.engine.accounting_entry_processor import AccountingEntryProcessor
from app.schemas.accounting_entry_schema import AccountingEntryCreateSchema


class HistoricalVatClassTests(unittest.TestCase):
    def test_all_legacy_classifications_and_rates_preserved(self):
        groups = {
            'standard': 'honorar eingang steuerberatung buro einrichtung betriebsbedarf werkzeug porto-mit-ust werbung handy-vertrag bewirtung bahn n/a',
            'reduced': 'fachliteratur ubernachtung',
            'none': 'krankenversicherung pfegeversicherung rentenversicherung hausratversicherung haftpflichtversicherung reiseversicherung raum betriebskosten porto-ohne-ust handy-prepaid festnetz auto bvg',
            'not_applicable': 'umsatzsteuer-vorauszahlung einkommen-kirchen-soli-vorauszahlung',
            'multi_year': 'werkzeug-mehrjaehrige-abschreibung',
        }
        rates = {'standard':'19', 'reduced':'7', 'none':'0', 'not_applicable':'0', 'multi_year':'19'}
        self.assertEqual(set(CLASSES), {c for group in groups.values() for c in group.split()})
        for klass, categories in groups.items():
            for category in categories.split():
                self.assertEqual(CLASSES[category], {1: klass})
                for year in (1, 2024, 2026, 9999):
                    self.assertEqual(get_vat_class(category, tax_year=year), klass)
                    self.assertEqual(get_vat_rate_percent(category, 'domestic', tax_year=year), Decimal(rates[klass]))

    def test_unknown_category_and_non_domestic_bypass(self):
        with self.assertRaisesRegex(ValueError, '^Unknown category code: unknown$'):
            get_vat_rate_percent('unknown', 'domestic', tax_year=2026)
        with patch('app.domain.accounting_rules.get_vat_class', side_effect=AssertionError('class lookup')), patch.dict(
                VAT_RATE_HISTORY, {}, clear=True):
            for scope in ('eu','third_country','not_applicable'):
                self.assertEqual(get_vat_rate_percent('unknown', scope, tax_year=2026), Decimal('0'))

    def test_independent_class_and_rate_changes_and_payment_year(self):
        with patch.dict(CLASSES, {'buro': {2020:'standard', 2030:'reduced'}}), patch.dict(
                VAT_RATE_HISTORY, {'standard': {2007:Decimal('19')}, 'reduced': {1983:Decimal('7'), 2032:Decimal('8')}}):
            for year, invoice_year, klass, rate in [
                (2029,2020,'standard','19'), (2029,2035,'standard','19'),
                (2030,2020,'reduced','7'), (2032,2020,'reduced','8')]:
                self.assertEqual(get_vat_class('buro', tax_year=year), klass)
                self.assertEqual(get_vat_rate_percent('buro','domestic',tax_year=year), Decimal(rate))
                result = AccountingEntryProcessor().process(AccountingEntryCreateSchema(
                    category_code='buro', counterparty_name='Test', payment_date=date(year,2,10),
                    invoice_date=date(invoice_year,1,1), amount_original='119.00', currency_original='EUR'))
                self.assertEqual(result.vat_rate_percent, Decimal(rate))
                self.assertEqual(result.booking_year, year)
                if year == 2029:
                    self.assertEqual(str(result.vat_amount), '19.00')
            with self.assertRaises(HistoricalValueUnavailable):
                get_vat_class('buro', tax_year=2019)
