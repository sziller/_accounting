from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal
from unittest.mock import patch
import unittest
from sqlalchemy.orm import Session
import test_receivables as fixtures
from app.domain.ar_recognition import (
    ArInvoiceRecognitionFacts, ArAllocationRecognitionFacts, resolve_ar_recognition_events,
)
from app.services.ar_recognition_service import ArRecognitionService
from app.services.local_currency_conversion import LocalCurrencyConversion


class ArRecognitionDomainTests(unittest.TestCase):
    def test_manual_fallback_empty_and_immutable(self):
        self.assertEqual(resolve_ar_recognition_events(
            ArInvoiceRecognitionFacts('i', Decimal('1000.123456'), 'USD', None), ()), ())
        event, = resolve_ar_recognition_events(ArInvoiceRecognitionFacts(
            'i', Decimal('1000.123456'), 'USD', date(2027, 1, 10)), ())
        self.assertEqual((event.amount_original, event.currency_original, event.tax_year),
                         (Decimal('1000.123456'), 'USD', 2027))
        self.assertEqual(event.source, 'manual_invoice_payment')
        self.assertIsNone(event.payment_id)
        self.assertIsNone(event.allocation_id)
        with self.assertRaises(FrozenInstanceError):
            event.tax_year = 2020

    def test_ordering_partial_precedence_and_foreign_invoice_rejected(self):
        invoice = ArInvoiceRecognitionFacts('i', Decimal('1000'), 'EUR', date(1999, 1, 1))
        allocations = tuple(ArAllocationRecognitionFacts('i', aid, pid, Decimal('200'), day, 'EUR')
            for aid, pid, day in [('z', 'p2', date(2027, 1, 1)),
                                 ('b', 'p1', date(2026, 12, 20)),
                                 ('a', 'p1', date(2026, 12, 20))])
        result = resolve_ar_recognition_events(invoice, allocations)
        self.assertEqual(result, resolve_ar_recognition_events(invoice, tuple(reversed(allocations))))
        self.assertEqual([e.allocation_id for e in result], ['a', 'b', 'z'])
        self.assertEqual(sum(e.amount_original for e in result), Decimal('600'))
        self.assertTrue(all(e.source == 'allocation' for e in result))
        with self.assertRaisesRegex(ValueError, 'does not belong'):
            resolve_ar_recognition_events(invoice, (ArAllocationRecognitionFacts(
                'other', 'a', 'p', Decimal('1'), date(2026, 1, 1), 'EUR'),))


class ArRecognitionServiceTests(unittest.TestCase):
    setUp = fixtures.ReceivablesTests.setUp
    request = fixtures.ReceivablesTests.request
    invoice = fixtures.ReceivablesTests.invoice
    payment = fixtures.ReceivablesTests.payment
    allocate = fixtures.ReceivablesTests.allocate

    def events(self, invoice):
        with Session(self.engine) as db:
            with patch.object(LocalCurrencyConversion, 'lookup', side_effect=AssertionError('No FX')):
                result = ArRecognitionService(db).resolve_invoice_events(invoice['id'])
            self.assertFalse(db.new or db.dirty or db.deleted)
            return result

    def test_empty_manual_and_cross_year_allocation_dates(self):
        invoice = self.invoice(amount='1000', invoice_date='2026-12-01')
        self.assertEqual(self.events(invoice), ())
        self.request('PATCH', 'outgoing-invoices/' + invoice['id'], {'payment_date':'2025-01-01'})
        self.assertEqual(self.events(invoice)[0].tax_year, 2025)
        a = self.payment('500', payment_date='2026-12-20')
        b = self.payment('500', payment_date='2027-01-10')
        self.allocate(invoice, a, '500')
        only, = self.events(invoice)
        self.assertEqual((only.tax_year, only.amount_original, only.source),
                         (2026, Decimal('500'), 'allocation'))
        self.allocate(invoice, b, '500')
        before = self.request('GET', 'outgoing-invoices/' + invoice['id'])[1]
        events = self.events(invoice)
        self.assertEqual([e.tax_year for e in events], [2026, 2027])
        self.assertEqual([e.amount_original for e in events], [Decimal('500'), Decimal('500')])
        self.assertEqual([e.recognition_date for e in events], [date(2026,12,20), date(2027,1,10)])
        self.assertEqual(self.request('GET', 'outgoing-invoices/' + invoice['id'])[1], before)
        # The allocation was created now, but recognition follows the editable parent date.
        self.request('PATCH', 'incoming-payments/' + b['id'], {'payment_date':'2028-01-10'})
        self.assertEqual([e.tax_year for e in self.events(invoice)], [2026, 2028])

    def test_split_payment_each_invoice_own_exact_original_amount(self):
        a = self.invoice('A', '100', currency='USD', payment_date='2000-01-01')
        b = self.invoice('B', '100', currency='USD')
        payment = self.payment('100', currency='USD', payment_date='2027-01-10')
        self.allocate(a, payment, '40.123456')
        self.allocate(b, payment, '59.876544')
        for invoice, amount in ((a, '40.123456'), (b, '59.876544')):
            event, = self.events(invoice)
            self.assertEqual(event.invoice_id, invoice['id'])
            self.assertEqual(event.payment_id, payment['id'])
            self.assertEqual(event.amount_original, Decimal(amount))
            self.assertEqual(event.currency_original, 'USD')
            self.assertEqual(event.tax_year, 2027)
            self.assertIsNone(self.request('GET', 'outgoing-invoices/' + invoice['id'])[1]['amount_common'])
