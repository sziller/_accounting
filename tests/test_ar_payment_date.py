"""Invoice receipt date is independent authoritative data, never inferred."""
import unittest
from unittest.mock import patch
from sqlalchemy.orm import Session
from app.db import database
from app.services.receivables_service import ReceivablesService
from tests import test_receivables as fixtures


class ArPaymentDateTests(unittest.TestCase):
    setUp = fixtures.ReceivablesTests.setUp
    request = fixtures.ReceivablesTests.request
    invoice = fixtures.ReceivablesTests.invoice

    def test_nullable_date_create_edit_clear_and_normalization_preserves_source(self):
        invoice = self.invoice(net_amount='80', vat_amount='20')
        self.assertIsNone(invoice['payment_date'])
        original = {key: invoice[key] for key in ('invoice_date', 'invoice_number',
            'customer_name', 'net_amount', 'vat_amount', 'gross_amount',
            'currency_original', 'amount_original')}
        path = 'outgoing-invoices/' + invoice['id']
        for value in ('2024-12-31', '2026-10-01', None):
            status, updated = self.request('PATCH', path, {'payment_date': value})
            self.assertEqual(status, 200, updated)
            self.assertEqual(updated['payment_date'], value)
            self.assertEqual({key: updated[key] for key in original}, original)
            with Session(self.engine) as db:
                ReceivablesService(db).normalize_pending_invoices()
            status, stored = self.request('GET', path)
            self.assertEqual(stored['payment_date'], value)
            self.assertEqual({key: stored[key] for key in original}, original)
        second = self.invoice('INV-2', payment_date='2025-01-02')
        self.assertEqual(second['payment_date'], '2025-01-02')
        status, _ = self.request('PATCH', path, {'payment_date': 'not-a-date'})
        self.assertEqual(status, 422)

    def test_existing_rows_survive_idempotent_startup_upgrade(self):
        invoice = self.invoice()
        with self.engine.begin() as connection:
            connection.exec_driver_sql('ALTER TABLE outgoing_invoices DROP COLUMN payment_date')
        with patch.object(database, 'engine', self.engine):
            database.init_db()
            database.init_db()
        status, stored = self.request('GET', 'outgoing-invoices/' + invoice['id'])
        self.assertEqual(status, 200, stored)
        self.assertEqual(stored, invoice)
