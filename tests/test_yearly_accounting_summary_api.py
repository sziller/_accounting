from contextlib import ExitStack
from dataclasses import asdict
from decimal import Decimal
import unittest
from unittest.mock import patch

from sqlalchemy import event

import test_yearly_accounting_summary as fixtures
from app.routers.router_yearly_accounting_summary import YearlyAccountingSummaryRouter


def wire_value(value):
    """Expected JSON shape, independent of the response schema."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: wire_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [wire_value(item) for item in value]
    return value


class YearlySummaryApiTests(unittest.TestCase):
    request = fixtures.YearlySummaryTests.request
    invoice = fixtures.YearlySummaryTests.invoice
    payment = fixtures.YearlySummaryTests.payment
    allocate = fixtures.YearlySummaryTests.allocate
    ap = fixtures.YearlySummaryTests.ap
    common = fixtures.YearlySummaryTests.common
    summary = fixtures.YearlySummaryTests.summary

    def setUp(self):
        fixtures.YearlySummaryTests.setUp(self)
        self.app.include_router(YearlyAccountingSummaryRouter())

    def get_summary(self, year=2026):
        return self.request('GET', f'yearly-accounting-summary/{year}')

    def test_exact_contract_and_no_processing_or_writes(self):
        self.ap(deductible_amount='73.123456', deductible_vat_amount='7.8900')
        invoice = self.invoice(payment_date='2026-12-20', net_amount='80', vat_amount='20')
        self.common(invoice, '100.006')
        expected = wire_value(asdict(self.summary()))

        def reject_writes(connection, cursor, statement, parameters, context, executemany):
            self.assertIn(statement.lstrip().split()[0].upper(), ('SELECT', 'PRAGMA'))

        event.listen(self.engine, 'before_cursor_execute', reject_writes)
        self.addCleanup(event.remove, self.engine, 'before_cursor_execute', reject_writes)
        with ExitStack() as stack:
            for target in (
                'app.services.entry_processing_service.EntryProcessingService.process_entry',
                'app.services.receivables_service.ReceivablesService.process_ar_entry',
                'app.services.local_currency_conversion.LocalCurrencyConversion.lookup',
                'app.domain.accounting_rules.get_vat_rate_percent',
                'app.domain.accounting_rules.get_deductible_percent',
            ):
                stack.enter_context(patch(target, side_effect=AssertionError('GET must not process')))
            status, body = self.get_summary()
        self.assertEqual(status, 200)
        self.assertEqual(body, expected)
        self.assertEqual(body['ap_expense_deductible_gross_common'], '73.123456')
        self.assertEqual(body['ap_breakdown'][0]['deductible_vat_amount'], '7.8900')
        self.assertEqual(body['recognized_ar_gross_common'], '100.006')
        self.assertEqual(body['completeness'], 'complete')
        self.assertEqual(set(body['warnings'][0]), {'code', 'count', 'message'})

    def test_cross_year_recognition_is_filtered_after_resolution(self):
        invoice = self.invoice(amount='3', invoice_date='2000-01-01', net_amount='2', vat_amount='1')
        self.common(invoice, '3')
        for year in (2025, 2026, 2027):
            payment = self.payment('1', payment_date=f'{year}-12-20')
            self.allocate(invoice, payment, '1')
        for year, vat in ((2025, '0.33'), (2026, '0.34'), (2027, '0.33')):
            status, body = self.get_summary(year)
            self.assertEqual(status, 200)
            self.assertEqual(body['tax_year'], year)
            self.assertEqual(body['ar_event_count'], 1)
            self.assertEqual(body['ar_components_by_original_currency'][0]['known_vat_original'], vat)
        self.assertEqual(self.get_summary(2000)[1]['ar_event_count'], 0)

    def test_mixed_currency_null_headlines_and_structured_warning(self):
        self.ap()
        invoice = self.invoice(payment_date='2026-01-01', currency_common='USD')
        self.common(invoice, '100')
        status, body = self.get_summary()
        self.assertEqual(status, 200)
        self.assertEqual(body['completeness'], 'incomplete')
        self.assertEqual(body['common_currencies'], ['EUR', 'USD'])
        for field in ('report_currency', 'recognized_ar_gross_common',
                      'ap_expense_deductible_gross_common', 'gross_basis_result',
                      'ap_deductible_vat_common'):
            self.assertIsNone(body[field])
        self.assertIsNone(body['ar_components_by_original_currency'][0]['known_net_original'])
        warning = next(w for w in body['warnings'] if w['code'] == 'currency_mismatch')
        self.assertEqual(warning['count'], 2)
        self.assertIn('EUR', warning['message'])

    def test_no_recognition_returns_string_zero(self):
        self.invoice()
        status, body = self.get_summary()
        self.assertEqual(status, 200)
        self.assertEqual(body['ar_event_count'], 0)
        self.assertEqual(body['recognized_ar_gross_common'], '0')
        self.assertEqual(body['ar_components_by_original_currency'], [])
        self.assertEqual(body['completeness'], 'complete')

    def test_invalid_years_and_readonly_route(self):
        with patch('app.services.yearly_accounting_summary_service.YearlyAccountingSummaryService.build') as build:
            for year in ('abc', '2026.5', '0', '-1', '10000'):
                status, body = self.get_summary(year)
                self.assertEqual(status, 422)
                self.assertEqual(body['detail'][0]['loc'], ['path', 'tax_year'])
            build.assert_not_called()
        self.assertEqual(self.request('POST', 'yearly-accounting-summary/2026')[0], 405)
        for year in (1, 9999):
            self.assertEqual(self.get_summary(year)[0], 200)

    def test_openapi_money_is_string_or_null(self):
        spec = self.app.openapi()
        operation = spec['paths']['/acct/v0/yearly-accounting-summary/{tax_year}']
        self.assertEqual(set(operation), {'get'})
        properties = spec['components']['schemas']['YearlyAccountingSummaryReadSchema']['properties']
        self.assertEqual([choice['type'] for choice in properties['gross_basis_result']['anyOf']],
                         ['string', 'null'])
