import unittest
from sqlalchemy.orm import Session
from app.db.models import OutgoingInvoiceORM
import test_receivables as fixtures


class ArRecognitionApiTests(unittest.TestCase):
    setUp = fixtures.ReceivablesTests.setUp
    request = fixtures.ReceivablesTests.request
    invoice = fixtures.ReceivablesTests.invoice
    payment = fixtures.ReceivablesTests.payment
    allocate = fixtures.ReceivablesTests.allocate

    def events(self, invoice):
        status, result = self.request('GET', 'outgoing-invoices/'+invoice['id']+'/recognition-events')
        self.assertEqual(status,200,result)
        return result

    def test_unpaid_manual_exact_strings_nullable_and_missing(self):
        invoice=self.invoice(amount='100.123456',net_amount=None,vat_amount=None)
        self.assertEqual(self.events(invoice),[])
        path='outgoing-invoices/'+invoice['id']
        self.request('PATCH',path,{'payment_date':'2024-01-01'})
        with Session(self.engine) as db:
            db.get(OutgoingInvoiceORM,invoice['id']).amount_common='90.123456'
            db.commit()
        before=self.request('GET',path)[1]
        event,=self.events(invoice)
        self.assertEqual(event['amount_original'],'100.123456')
        self.assertEqual(event['amount_common'],'90.123456')
        self.assertIsNone(event['net_amount_original'])
        self.assertIsNone(event['vat_amount_original'])
        self.assertEqual(event['source'],'manual_invoice_payment')
        self.assertEqual(event['tax_year'],2024)
        self.assertEqual(self.request('GET',path)[1],before)
        self.assertEqual(self.request('GET','outgoing-invoices/missing/recognition-events')[0],404)
        self.request('PATCH',path,{'payment_date':None})
        self.assertEqual(self.events(invoice),[])

    def test_allocations_precedence_partial_full_cross_year_and_current_dates(self):
        invoice=self.invoice(amount='1190.00',net_amount='1000.00',vat_amount='190.00',payment_date='2020-01-01')
        a=self.payment('595',payment_date='2026-12-20')
        b=self.payment('595',payment_date='2027-01-10')
        self.allocate(invoice,a,'595')
        event,=self.events(invoice)
        self.assertEqual((event['source'],event['net_amount_original'],event['vat_amount_original']),
                         ('allocation','500.00','95.00'))
        self.allocate(invoice,b,'595')
        self.assertEqual([e['tax_year'] for e in self.events(invoice)],[2026,2027])
        self.request('PATCH','incoming-payments/'+b['id'],{'payment_date':'2028-01-01'})
        self.assertEqual([e['tax_year'] for e in self.events(invoice)],[2026,2028])
        full=self.invoice('FULL',amount='1190.00',net_amount='1000.00',vat_amount='190.00')
        self.allocate(full,self.payment('1190'),'1190')
        event,=self.events(full)
        self.assertEqual(event['net_amount_original'],'1000.00')
        self.assertEqual(event['vat_amount_original'],'190.00')
