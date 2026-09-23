from dataclasses import replace
from datetime import date
from decimal import Decimal as D
from unittest.mock import patch
import unittest
from sqlalchemy.orm import Session
import test_receivables as fixtures
from app.db.models import OutgoingInvoiceORM
from app.domain.ar_recognition import ArInvoiceRecognitionFacts, ArAllocationRecognitionFacts, resolve_ar_recognition_events
from app.domain.ar_amount_allocation import allocate_invoice_amounts
from app.services.ar_recognition_service import ArRecognitionService
from app.services.local_currency_conversion import LocalCurrencyConversion


class ArRecognitionAmountsTests(unittest.TestCase):
    def invoice(self):
        return ArInvoiceRecognitionFacts('i', D('1190.00'), 'EUR', date(2020,1,1),
                                         D('1000.00'), D('190.00'), D('1190.00'))

    def allocation(self, amount, index):
        return ArAllocationRecognitionFacts('i', str(index), str(index), D(amount),
                                             date(2025+index,12,20), 'EUR')

    def test_full_manual_and_single_allocation_copy_subcent_values(self):
        invoice = replace(self.invoice(), gross_amount=D('1190.123456'),
                          net_amount=D('1000.123456'), amount_common=D('999.654321'))
        manual, = resolve_ar_recognition_events(invoice, ())
        allocated, = resolve_ar_recognition_events(invoice, (self.allocation('1190.123456',1),))
        for event in (manual, allocated):
            self.assertEqual(event.amount_original, invoice.gross_amount)
            self.assertEqual(event.net_amount_original, invoice.net_amount)
            self.assertEqual(event.vat_amount_original, invoice.vat_amount)
            self.assertEqual(event.amount_common, invoice.amount_common)

    def test_cross_year_and_unequal_partial(self):
        events = resolve_ar_recognition_events(self.invoice(),
                  (self.allocation('595',2), self.allocation('595',1)))
        self.assertEqual([e.tax_year for e in events], [2026,2027])
        for event in events:
            self.assertEqual((event.amount_original,event.net_amount_original,event.vat_amount_original,event.amount_common),
                             (D('595'), D('500.00'), D('95.00'), D('595.00')))
        partial = resolve_ar_recognition_events(self.invoice(),
                    (self.allocation('119',1),self.allocation('238',2)))
        self.assertEqual([e.net_amount_original for e in partial], [D('100'),D('200')])
        self.assertEqual([e.vat_amount_original for e in partial], [D('19'),D('38')])
        self.assertEqual(sum(e.amount_common for e in partial), D('357'))

    def test_rounding_residual_and_stability(self):
        invoice = replace(self.invoice(), gross_amount=D('3'), net_amount=D('2'),
                          vat_amount=D('1'), amount_common=D('2.000001'))
        allocations = tuple(self.allocation('1', i) for i in (1,2,3))
        partial = resolve_ar_recognition_events(invoice, allocations[:2])
        complete = resolve_ar_recognition_events(invoice, tuple(reversed(allocations)))
        self.assertEqual(partial, complete[:2])
        self.assertEqual([e.vat_amount_original for e in complete], [D('.33'),D('.34'),D('.33')])
        self.assertEqual(complete[-1].net_amount_original, D('.67'))
        self.assertEqual(complete[-1].amount_common, D('.666667'))
        for field, total in [('amount_original',invoice.gross_amount),('net_amount_original',invoice.net_amount),
                             ('vat_amount_original',invoice.vat_amount),('amount_common',invoice.amount_common)]:
            self.assertEqual(sum(getattr(e,field) for e in complete), total)
        self.assertEqual(sum(e.vat_amount_original for e in partial), D('.67'))

    def test_nullable_components_independent_and_half_up(self):
        for missing in ('net_amount', 'vat_amount', 'amount_common'):
            invoice = replace(self.invoice(), **{missing:None})
            for allocations in ((),(self.allocation('595',1),)):
                event, = resolve_ar_recognition_events(invoice, allocations)
                field = missing if missing == 'amount_common' else missing+'_original'
                self.assertIsNone(getattr(event,field))
        share, = allocate_invoice_amounts(gross_total=D('2'), net_total=D('.01'), vat_total=None,
                                         common_total=None, recognized_gross_amounts=(D('1'),))
        self.assertEqual(share.net_amount_original,D('.01'))


class ArRecognitionAmountsIntegrationTests(unittest.TestCase):
    setUp = fixtures.ReceivablesTests.setUp
    request = fixtures.ReceivablesTests.request
    invoice = fixtures.ReceivablesTests.invoice
    payment = fixtures.ReceivablesTests.payment
    allocate = fixtures.ReceivablesTests.allocate

    def test_foreign_existing_valuation_no_fx_and_deletion_manual_fallback(self):
        invoice = self.invoice(amount='100',currency='USD',net_amount='80',vat_amount='20',payment_date='2024-01-01')
        with Session(self.engine) as db:
            db.get(OutgoingInvoiceORM,invoice['id']).amount_common='90.123456'
            db.commit()
        payment = self.payment('40.123456',currency='USD',payment_date='2027-01-01')
        allocation = self.allocate(invoice,payment,'40.123456')
        path='outgoing-invoices/'+invoice['id']
        before=self.request('GET',path)[1]
        with Session(self.engine) as db, patch.object(LocalCurrencyConversion,'lookup',side_effect=AssertionError('No FX')):
            event,=ArRecognitionService(db).resolve_invoice_events(invoice['id'])
        self.assertEqual(event.amount_original,D('40.123456'))
        self.assertEqual(event.currency_original,'USD')
        self.assertEqual(event.amount_common,D('36.160645'))
        self.assertEqual(event.net_amount_original,D('32.10'))
        self.assertEqual(event.vat_amount_original,D('8.02'))
        self.assertEqual(event.tax_year,2027)
        self.assertEqual(self.request('GET',path)[1],before)
        self.assertEqual(self.request('DELETE','invoice-payment-allocations/'+allocation['id'])[0],204)
        with Session(self.engine) as db:
            event,=ArRecognitionService(db).resolve_invoice_events(invoice['id'])
        self.assertEqual((event.source,event.tax_year),('manual_invoice_payment',2024))
        self.assertEqual((event.amount_original,event.net_amount_original,event.vat_amount_original,event.amount_common),
                         (D('100'),D('80'),D('20'),D('90.123456')))
        stored=self.request('GET',path)[1]
        self.assertEqual(stored['payment_date'],'2024-01-01')
        self.assertEqual(D(stored['paid_amount']),0)
