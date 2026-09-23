"""Payment-date year seam preserves current AP results and field authority."""
from datetime import date
from types import SimpleNamespace
import unittest
from app.domain.tax_year import resolve_tax_year
from app.engine.accounting_entry_processor import AccountingEntryProcessor
from app.schemas.accounting_entry_schema import AccountingEntryCreateSchema


class TaxYearTests(unittest.TestCase):
    def test_payment_year_is_authoritative_even_with_other_invoice_and_booking_years(self):
        for year in (2021, 2024, 2026):
            entry = SimpleNamespace(payment_date=date(year, 11, 18),
                                    invoice_date=date(1999, 1, 1), booking_year=1900)
            self.assertEqual(resolve_tax_year(entry), year)

    def test_processor_keeps_existing_values_and_input_unchanged(self):
        for year in (2021, 2024, 2026):
            payload = AccountingEntryCreateSchema(
                category_code='bewirtung', tax_scope='domestic', counterparty_name='Vendor',
                payment_date=date(year, 11, 18), invoice_date=date(2020, 1, 1),
                amount_original='119.00', currency_original='EUR')
            before = payload.model_dump()
            result = AccountingEntryProcessor().process(payload)
            self.assertEqual(result.booking_year, year)
            self.assertEqual(payload.model_dump(), before)
            expected = {'amount_common':'119.00', 'vat_rate_percent':'19', 'vat_amount':'19.00',
                        'deductible_percent':'70', 'deductible_amount':'83.30',
                        'deductible_vat_amount':'13.30'}
            for key, value in expected.items():
                self.assertEqual(str(getattr(result, key)), value)
            self.assertEqual(result.writeoff_method, 'partial')
            self.assertEqual(result.conversion_status, 'not_required')
            self.assertEqual(result, AccountingEntryProcessor().process(payload))
