"""Stored-rate integration tests for AP and AR pending conversions."""
from datetime import date
from decimal import Decimal
from pathlib import Path
import unittest
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db.models import Base
from app.services.conversion_service import ConversionService
from app.services.receivables_service import ReceivablesService
from app.services.exchange_rate_service import ExchangeRateService
from app.services.eur_usd_exchange_rate_service import EurUsdExchangeRateService
from app.schemas.receivables_schema import OutgoingInvoiceCreateSchema
from test_invoice_number_policy import raw_row


class PendingConversionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

    def rate(self, currency, day, value):
        service = EurUsdExchangeRateService if currency == 'USD' else ExchangeRateService
        service(self.db).upsert_rate(rate_date=day, base_currency='EUR', quote_currency=currency,
            source='ECB' if currency == 'USD' else 'MNB', rate=Decimal(value))

    def records(self, currency, amount='110.00', day=date(2026, 2, 10)):
        ap = raw_row('AP')
        ap.currency_original, ap.amount_original, ap.amount_common = currency, amount, None
        ap.payment_date, ap.conversion_status = day, 'pending'
        self.db.add(ap)
        self.db.commit()
        ar = ReceivablesService(self.db).create_invoice(OutgoingInvoiceCreateSchema(
            invoice_number='AR', invoice_date=day, customer_name='Customer',
            currency=currency, gross_amount=Decimal(amount)))
        return ap, ar

    def process(self):
        count = ConversionService(self.db).reprocess_pending()
        report = ReceivablesService(self.db).normalize_pending_invoices()
        return count, report

    def test_usd_division_real_workflows_and_idempotency(self):
        self.rate('USD', date(2026, 2, 10), '1.1000')
        ap, ar = self.records('USD')
        usd_lookup = EurUsdExchangeRateService.get_latest_rate_on_or_before
        with patch.object(EurUsdExchangeRateService, 'get_latest_rate_on_or_before', usd_lookup), patch.object(
                ExchangeRateService, 'get_latest_rate_on_or_before', side_effect=AssertionError('MNB queried')):
            count, report = self.process()
        self.assertEqual(count, 1)
        self.assertEqual((ap.amount_common, ap.exchange_rate, ap.exchange_rate_date, ap.conversion_status),
                         ('100.00', '1.1000', date(2026, 2, 10), 'resolved'))
        self.assertEqual((report.converted, report.pending), (1, 0))
        self.assertEqual(report.invoices[0].amount_common, Decimal('100.00'))
        self.assertIn('ECB', report.invoices[0].message)
        count, report = self.process()
        self.assertEqual((count, report.converted, report.pending), (0, 0, 0))

    def test_weekend_latest_prior_rate_and_half_up_rounding(self):
        self.rate('USD', date(2026, 2, 6), '1.1000')
        self.rate('USD', date(2026, 2, 9), '2.2000')
        ap, _ = self.records('USD', '1.1055', date(2026, 2, 8))
        _, report = self.process()
        self.assertEqual(ap.amount_common, '1.01')
        self.assertEqual(ap.exchange_rate_date, date(2026, 2, 6))
        self.assertEqual(report.invoices[0].amount_common, Decimal('1.01'))
        self.assertIn('2026-02-06', report.invoices[0].message)

    def test_missing_history_stays_pending_without_future_fallback(self):
        self.rate('USD', date(2026, 2, 11), '1.1000')
        ap, _ = self.records('USD')
        count, report = self.process()
        self.assertEqual((count, report.converted, report.pending), (0, 0, 1))
        self.assertEqual(ap.conversion_status, 'pending')
        self.assertIsNone(ap.amount_common)
        self.assertIn('No ECB', ap.conversion_note)
        self.assertIn('No ECB', report.invoices[0].message)

    def test_huf_unchanged_and_never_queries_ecb(self):
        self.rate('HUF', date(2026, 2, 6), '400')
        ap, _ = self.records('HUF', '402')
        with patch.object(EurUsdExchangeRateService, 'get_latest_rate_on_or_before', side_effect=AssertionError('ECB queried')):
            count, report = self.process()
        self.assertEqual((count, ap.amount_common), (1, '1.01'))
        self.assertEqual(report.invoices[0].amount_common, Decimal('1.01'))

    def test_same_currency_does_not_lookup_rates(self):
        ap, _ = self.records('EUR', '12.3456')
        with patch.object(ExchangeRateService, 'get_latest_rate_on_or_before', side_effect=AssertionError('FX queried')):
            count, report = self.process()
        self.assertEqual((count, ap.amount_common, ap.conversion_status), (1, '12.3456', 'not_required'))
        self.assertEqual(report.invoices[0].amount_common, Decimal('12.3456'))
        self.assertEqual(report.converted, 1)

    def test_button_labels_and_ar_restored_label(self):
        import re
        html = Path('app/templates/index.html').read_text()
        for identifier, expected in [('reprocess-pending-conversions', 'Process Entries'), ('normalize-ar-invoices', 'Process Entries'), ('process-ar-entry', 'Process Entry')]:
            label = re.search(r'<button\b[^>]*\bid="' + identifier + r'"[^>]*>(.*?)</button>', html, re.S).group(1).strip()
            self.assertEqual(label, expected)
        self.assertIn('normalize.textContent = "Process Entries"',
                      Path('app/static/js/ar_invoice_import.js').read_text())
