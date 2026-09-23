from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal as D
from unittest.mock import patch
from contextlib import ExitStack
import unittest
from sqlalchemy.orm import Session
import test_receivables as fixtures
from test_invoice_number_policy import raw_row
from app.db.models import OutgoingInvoiceORM
from app.services.yearly_accounting_summary_service import YearlyAccountingSummaryService


class YearlySummaryTests(unittest.TestCase):
    setUp=fixtures.ReceivablesTests.setUp
    request=fixtures.ReceivablesTests.request
    invoice=fixtures.ReceivablesTests.invoice
    payment=fixtures.ReceivablesTests.payment
    allocate=fixtures.ReceivablesTests.allocate

    def ap(self, **changes):
        row=raw_row(None)
        row.booking_year=2026
        row.payment_date=date(1999,1,1)  # Report must use persisted year, not source date.
        row.amount_common='100'
        row.vat_amount='19'
        row.deductible_amount='73.12'
        row.deductible_vat_amount='7.89'
        row.conversion_status='not_required'
        for key,value in changes.items(): setattr(row,key,value)
        with Session(self.engine) as db:
            db.add(row); db.commit()

    def common(self,invoice,value):
        with Session(self.engine) as db:
            db.get(OutgoingInvoiceORM,invoice['id']).amount_common=value
            db.commit()

    def summary(self,year=2026):
        with Session(self.engine) as db:
            result=YearlyAccountingSummaryService(db).build(year)
            self.assertFalse(db.new or db.dirty or db.deleted)
            return result

    def test_population_persisted_values_and_no_accounting_calls(self):
        self.ap()
        self.ap(booking_year=2025)
        for entry_type in ('income','tax','private','correction'):
            self.ap(entry_type=entry_type)
        invoice=self.invoice(payment_date='2026-12-20',invoice_date='2024-01-01',net_amount='80',vat_amount='20')
        self.common(invoice,'100')
        with ExitStack() as stack:
            for target in (
                'app.services.entry_processing_service.EntryProcessingService.process_entry',
                'app.services.receivables_service.ReceivablesService.process_ar_entry',
                'app.services.local_currency_conversion.LocalCurrencyConversion.lookup',
                'app.domain.accounting_rules.get_vat_rate_percent',
                'app.domain.accounting_rules.get_deductible_percent',
            ):
                stack.enter_context(patch(target,side_effect=AssertionError('Report must not calculate')))
            result=self.summary()
        self.assertEqual(result.ap_included_count,1)
        self.assertEqual(result.ap_non_expense_count,4)
        self.assertEqual(len(result.ap_breakdown),5)
        self.assertEqual(result.ap_expense_deductible_gross_common,D('73.12'))
        self.assertEqual(result.ap_deductible_vat_common,D('7.89'))
        self.assertEqual(result.gross_basis_result,D('26.88'))
        self.assertEqual(result.completeness,'complete')
        self.assertIn('ap_non_expense',[w.code for w in result.warnings])
        self.assertIn('processing_freshness_unverified',[w.code for w in result.warnings])
        with self.assertRaises(FrozenInstanceError): result.tax_year=2020

    def test_cross_year_full_sequence_before_filtering(self):
        invoice=self.invoice(amount='3',net_amount='2',vat_amount='1',invoice_date='2000-01-01',payment_date='1999-01-01')
        self.common(invoice,'3')
        for index,day in enumerate(('2025-01-01','2026-01-01','2027-01-01')):
            self.allocate(invoice,self.payment('1',payment_date=day),'1')
        result=self.summary()
        self.assertEqual(result.ar_event_count,1)
        self.assertEqual(result.recognized_ar_gross_common,D('1'))
        self.assertEqual(result.ar_components_by_original_currency[0].known_vat_original,D('.34'))
        self.assertEqual(self.summary(2025).ar_components_by_original_currency[0].known_vat_original,D('.33'))
        self.assertEqual(self.summary(2027).ar_event_count,1)

    def test_currency_components_missing_values_and_no_events(self):
        eur=self.invoice('EUR',net_amount='80',vat_amount='20',payment_date='2026-01-01')
        usd=self.invoice('USD',currency='USD',net_amount=None,vat_amount=None,payment_date='2026-01-01')
        self.invoice('UNPAID')
        self.common(eur,'100')
        result=self.summary()
        self.assertEqual(result.ar_event_count,2)
        self.assertEqual(result.ar_invoices_without_events,1)
        self.assertEqual(result.ar_common_excluded_count,1)
        self.assertEqual(result.recognized_ar_gross_common,D('100'))
        groups={g.currency_original:g for g in result.ar_components_by_original_currency}
        self.assertEqual(groups['EUR'].known_vat_original,D('20'))
        self.assertIsNone(groups['USD'].known_net_original)
        self.assertIsNone(groups['USD'].known_vat_original)
        self.assertEqual(groups['USD'].missing_net_count,1)
        self.assertEqual(groups['USD'].missing_vat_count,1)
        self.assertEqual(result.completeness,'incomplete')

    def test_incomplete_ap_mismatch_and_multi_year_warning(self):
        self.ap(amount_common=None,conversion_status='pending')
        self.ap(deductible_amount='NaN')
        self.ap(writeoff_method='multi_year')
        result=self.summary()
        self.assertEqual((result.ap_included_count,result.ap_excluded_count),(1,2))
        self.assertEqual(result.completeness,'incomplete')
        self.assertIn('multi_year_limitation',[w.code for w in result.warnings])
        self.assertEqual(self.summary(2027).ap_included_count,0)
        invoice=self.invoice(payment_date='2026-01-01',currency_common='USD')
        self.common(invoice,'100')
        result=self.summary()
        self.assertEqual(result.common_currencies,('EUR','USD'))
        self.assertIsNone(result.report_currency)
        self.assertIsNone(result.gross_basis_result)
        self.assertIsNone(result.recognized_ar_gross_common)
        self.assertIn('currency_mismatch',[w.code for w in result.warnings])

    def test_empty_year_and_invalid_year(self):
        self.invoice()
        result=self.summary()
        self.assertEqual(result.ar_event_count,0)
        self.assertEqual(result.gross_basis_result,D('0'))
        self.assertIsNone(result.report_currency)
        self.assertEqual(result.completeness,'complete')
        with self.assertRaises(ValueError): self.summary(0)

    def test_known_original_vat_never_combines_currencies(self):
        for currency,net,vat,common in (('EUR','80','20','100'),('USD','90','10','85')):
            invoice=self.invoice(currency,currency=currency,net_amount=net,vat_amount=vat,
                                 payment_date='2026-01-01')
            self.common(invoice,common)
        result=self.summary()
        self.assertEqual(result.report_currency,'EUR')
        self.assertEqual(result.recognized_ar_gross_common,D('185'))
        groups={group.currency_original:group for group in result.ar_components_by_original_currency}
        self.assertEqual(groups['EUR'].known_vat_original,D('20'))
        self.assertEqual(groups['USD'].known_vat_original,D('10'))
        self.assertEqual(groups['EUR'].known_net_original,D('80'))
        self.assertEqual(groups['USD'].known_net_original,D('90'))
