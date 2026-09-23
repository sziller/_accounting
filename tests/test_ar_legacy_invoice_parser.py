"""Explicit legacy variant tested without private invoice files or local data."""
from datetime import date
from decimal import Decimal
from pathlib import Path
import unittest

import test_ar_invoice_import as fixtures
from app.services.ar_invoice_parser import ArInvoiceParseError, parse_ar_invoice_text
from app.services.pdf_extraction_service import extract_pdf_text

LEGACY = (Path(__file__).parent / 'fixtures/ar_honorarrechnung_legacy_de_hu.txt').read_text()
NET = 'Nettohonorar gesammt – nettó összeg 84.000 HUF'
GROSS = '(siehe Vermerk) – bruttó: (lásd megjegyzés) 84.000 HUF'
VATIN = 'Ust-IdNr. - VATIN: DE123456789'


class LegacyInvoiceParserTests(unittest.TestCase):
    setUp = fixtures.ArInvoiceImportTests.setUp
    request = fixtures.ArInvoiceImportTests.request
    process = fixtures.ArInvoiceImportTests.process
    rows = fixtures.ArInvoiceImportTests.rows
    source = fixtures.ArInvoiceImportTests.source

    def parse(self, text):
        return parse_ar_invoice_text(extract_pdf_text(fixtures.make_pdf(text)))

    def reject(self, text, code=None):
        with self.assertRaises(ArInvoiceParseError) as caught:
            self.parse(text)
        if code:
            self.assertEqual(caught.exception.code, code)

    def test_legacy_layouts_import_with_exact_magnitudes(self):
        # Fictitious parties, identifiers, dates and amounts retain the supported
        # number conventions. No production archive is required by the suite.
        for number, amount in (('9201', '84000'), ('9202', '228000')):
            text = LEGACY
            if number == '9202':
                text = text.replace('9201', '9202').replace('24.000', '12.000').replace(
                    '60.000', '216.000').replace('84.000', '228.000')
            original = fixtures.make_pdf(text)
            parsed = parse_ar_invoice_text(extract_pdf_text(original))
            self.assertEqual(parsed.invoice_number, number)
            self.assertEqual(parsed.invoice_date, date(2030, 2, 18))
            self.assertEqual(parsed.customer_name, 'Example Cooperative')
            self.assertEqual(parsed.net_amount, Decimal(amount))
            self.assertEqual(parsed.gross_amount, Decimal(amount))
            self.assertEqual(parsed.amount_original, Decimal(amount))
            self.assertEqual(parsed.currency_original, 'HUF')
            self.assertIsNone(parsed.vat_amount)
            self.assertIsNone(parsed.payment_date)
            (self.directory / f'{number}.pdf').write_bytes(original)
        result = self.process()
        self.assertEqual((result.imported, result.failed), (2, 0))
        self.assertEqual([row.gross_amount for row in self.rows()], ['84000', '228000'])
        self.assertEqual(self.process().already_imported, 2)

    def test_synthetic_aggregate_not_component_and_contact_forms(self):
        self.assertEqual(self.parse(LEGACY).gross_amount, Decimal('84000'))
        second = LEGACY.replace('24.000', '12.000').replace('60.000', '216.000').replace('84.000', '228.000')
        self.assertEqual(self.parse(second).net_amount, Decimal('228000'))
        self.assertEqual(self.parse(LEGACY.replace('Test Contact Test Contact', 'Herr Test Contact Test Contact')).net_amount,
                         Decimal('84000'))

    def test_recipient_validation_is_retained(self):
        for text in (
            LEGACY.replace('Test Contact Test Contact\n', ''),
            LEGACY.replace('Test Contact Test Contact', 'Unknown contact'),
            LEGACY.replace('Test Contact Test Contact', '123 123'),
            LEGACY.replace('Example Cooperative Example Cooperative', 'Unknown company'),
            LEGACY.replace('Example Cooperative Example Cooperative', 'Example Issuer Example Issuer'),
            LEGACY.replace('Test Contact Test Contact\nExample Cooperative Example Cooperative',
                           'Example Cooperative Example Cooperative\nTest Contact'),
        ):
            with self.subTest(text=text): self.reject(text, 'customer_not_found')

    def test_missing_duplicate_and_misordered_boundaries(self):
        for marker in (VATIN, 'Honorarrechnung Számla'):
            self.reject(LEGACY.replace(marker+'\n', ''))
            self.reject(LEGACY.replace(marker, marker+'\n'+marker))
        self.reject(LEGACY.replace(VATIN, 'Honorarrechnung Számla').replace(
            'Example Address 1\nHonorarrechnung Számla', 'Example Address 1\n'+VATIN))

    def test_missing_duplicate_mixed_and_invalid_totals(self):
        for marker in (NET, GROSS):
            self.reject(LEGACY.replace(marker+'\n', ''))
            self.reject(LEGACY.replace(marker, marker+'\n'+marker))
            self.reject(LEGACY.replace(marker, marker+'\n'+marker.replace('84.000', 'bad')))
        self.reject(LEGACY.replace(GROSS, GROSS.replace('84.000', '85.000')), 'totals_inconsistent')
        self.reject(LEGACY.replace(GROSS, GROSS.replace('HUF', 'EUR')), 'currency_conflict')
        self.reject(LEGACY.replace('HUF', 'USD'), 'currency_conflict')
        self.reject(LEGACY.replace('Bruttohonorar\n', ''), 'gross_amount_not_found')
        self.reject(LEGACY.replace(NET, NET+'\nNettohonorar – net amount: 84.000 HUF'), 'unsupported_layout')
        self.reject(LEGACY.replace('Honorarrechnung Számla', 'Honorarrechnung Invoice'), 'unsupported_layout')

    def test_legacy_grouping_is_strict(self):
        for amount in ('84.00', '84.0000', '084.000', '84000', '84,000', '84 000',
                       '1.23.000', '84.000,00', '84.000.00', '+84.000', '-84.000'):
            with self.subTest(amount=amount):
                self.reject(LEGACY.replace('84.000', amount), 'invalid_legacy_huf_amount')
        self.assertEqual(self.parse(LEGACY.replace('84.000', '1.084.000')).gross_amount, Decimal('1084000'))

    def test_dates_and_terms_remain_strict(self):
        for invalid in ('2030-02-18', '18/02/2030', '31. Februar 2030', '18. Unknown 2030'):
            self.reject(LEGACY.replace('18. Februar 2030', invalid), 'invoice_date_not_found')
        self.reject(LEGACY.replace('18. Februar 2030', 'Inserted line\n18. Februar 2030'), 'invoice_date_not_found')
        for invalid in ('der nächsten 14 Tagen', 'der nächsten 14 Tage', 'der nächsten 30 Tage.', 'der nächsten 14 Tage. whenever'):
            self.reject(LEGACY.replace('der nächsten 14 Tage.', invalid), 'unsupported_layout')
        self.reject(LEGACY.replace('der nächsten 14 Tage.', 'der nächsten 14 Tage.\nBitte überweisen Sie das Bruttohonorar innerhalb\nder nächsten 14 Tage.'), 'unsupported_layout')

    def test_existing_decimal_convention_is_unchanged(self):
        for text, old in ((fixtures.EN, '12 400 USD'), (fixtures.HU, '2350.00 EUR')):
            parsed = self.parse(text.replace(old, '84.000 HUF'))
            self.assertEqual(parsed.gross_amount, Decimal('84.000'))
            self.assertEqual(parsed.gross_amount.as_tuple().exponent, -3)
            self.assertEqual(parsed.currency_original, 'HUF')
        self.assertEqual(self.parse(fixtures.HU.replace('2350.00 EUR', '0.100001 EUR')).gross_amount,
                         Decimal('0.100001'))
