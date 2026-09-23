from datetime import date
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from sqlalchemy.orm import Session
from app.db.models import OutgoingInvoiceORM, ExchangeRateORM, EurUsdExchangeRateORM
from app.domain.ar_tax_year import resolve_ar_tax_year
from app.services.receivables_service import ReceivablesService
import test_receivables as fixtures


class ArProcessingTests(unittest.TestCase):
    setUp = fixtures.ReceivablesTests.setUp
    request = fixtures.ReceivablesTests.request
    invoice = fixtures.ReceivablesTests.invoice
    payment = fixtures.ReceivablesTests.payment
    allocate = fixtures.ReceivablesTests.allocate

    def process(self, invoice):
        status, result = self.request('POST', 'outgoing-invoices/' + invoice['id'] + '/process')
        self.assertEqual(status, 200, result)
        return result

    def test_tax_year_has_no_invoice_fallback(self):
        for payment, expected in ((None, None), (date(2024, 1, 2), 2024), (date(2026, 1, 2), 2026)):
            self.assertEqual(resolve_ar_tax_year(SimpleNamespace(
                payment_date=payment, invoice_date=date(1999, 1, 1))), expected)

    def test_stale_y_replaced_x_balances_preserved_and_idempotent(self):
        invoice = self.invoice(net_amount='80', vat_amount='20', payment_date='2024-12-31')
        other = self.invoice('OTHER')
        payment = self.payment('10')
        self.allocate(invoice, payment, '10')
        before = self.request('GET', 'outgoing-invoices/' + invoice['id'])[1]
        with Session(self.engine) as db:
            db.get(OutgoingInvoiceORM, invoice['id']).amount_common = '999'
            db.commit()
        result = self.process(invoice)
        self.assertEqual(result['status'], 'processed')
        self.assertEqual(result['entry']['amount_common'], '100.00')
        self.assertEqual(result['trace']['tax_year'], 2024)
        self.assertEqual(result['trace']['fx_source'], 'same_currency')
        for field, value in before.items():
            if field not in ('amount_common', 'updated_at'):
                self.assertEqual(result['entry'][field], value, field)
        self.assertEqual(self.process(invoice)['entry'], result['entry'])
        self.assertIsNone(self.request('GET', 'outgoing-invoices/' + other['id'])[1]['amount_common'])

    def test_fx_uses_invoice_date_not_receipt_date_and_unpaid_can_process(self):
        with Session(self.engine) as db:
            for model, quote, source, rate in ((ExchangeRateORM, 'HUF', 'MNB', '400'),
                                               (EurUsdExchangeRateORM, 'USD', 'ECB', '1.1000')):
                for day, value in ((date(2026, 2, 6), rate), (date(2026, 2, 9), '999')):
                    db.add(model(rate_date=day, base_currency='EUR', quote_currency=quote,
                                 source=source, rate=value, unit='1'))
            db.commit()
        for quote, amount, expected, source, payment_date in (
                ('HUF', '402', '1.01', 'MNB', '2027-01-01'),
                ('USD', '110', '100.00', 'ECB', None),
                ('EUR', '12.3456', '12.3456', 'same_currency', None)):
            invoice = self.invoice(quote, amount, currency=quote, invoice_date='2026-02-08',
                                   payment_date=payment_date)
            result = self.process(invoice)
            self.assertEqual(result['status'], 'processed', result)
            self.assertEqual(result['entry']['amount_common'], expected)
            self.assertEqual(result['entry']['payment_date'], payment_date)
            self.assertEqual(result['trace']['fx_lookup_date'], '2026-02-08')
            self.assertEqual(result['trace']['fx_source'], source)
            self.assertEqual(result['trace']['tax_year'], 2027 if payment_date else None)
            if quote != 'EUR':
                self.assertIn('2026-02-06', result['message'])

    def test_bulk_all_rows_failure_isolation_and_rollback_after_assignment(self):
        good = self.invoice('GOOD')
        bad = self.invoice('BAD', currency='USD')
        for invoice in (good, bad):
            with Session(self.engine) as db:
                db.get(OutgoingInvoiceORM, invoice['id']).amount_common = '999'
                db.commit()
        status, report = self.request('POST', 'outgoing-invoices/process-entries')
        self.assertEqual(status, 200)
        self.assertEqual((report['processed'], report['failed']), (1, 1))
        self.assertIn('No ECB', next(r for r in report['invoices'] if r['id'] == bad['id'])['message'])
        self.assertEqual(self.request('GET', 'outgoing-invoices/' + bad['id'])[1]['amount_common'], '999')
        self.assertEqual(self.request('GET', 'outgoing-invoices/' + good['id'])[1]['amount_common'], '100.00')
        with Session(self.engine) as db:
            db.get(OutgoingInvoiceORM, good['id']).amount_common = '888'
            db.commit()
        before = self.request('GET', 'outgoing-invoices/' + good['id'])[1]
        with patch.object(ReceivablesService, '_invoice_read', side_effect=ValueError('Injected after flush')):
            self.assertEqual(self.process(good)['status'], 'failed')
        self.assertEqual(self.request('GET', 'outgoing-invoices/' + good['id'])[1], before)
        self.assertEqual(self.process({'id':'missing'})['status'], 'failed')
