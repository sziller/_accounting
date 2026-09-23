"""Original/common AR persistence and explicit, local-only normalization."""
from datetime import date
from unittest.mock import patch
import unittest

from sqlalchemy.orm import Session

import test_receivables as fixtures
from app.core import config
from app.db import database
from app.db.models import ExchangeRateORM, OutgoingInvoiceORM, InvoicePaymentAllocationORM


class ArCurrencyTests(unittest.TestCase):
    setUp = fixtures.ReceivablesTests.setUp
    request = fixtures.ReceivablesTests.request
    invoice = fixtures.ReceivablesTests.invoice
    payment = fixtures.ReceivablesTests.payment
    allocate = fixtures.ReceivablesTests.allocate

    def normalize(self):
        status, report = self.request("POST", "outgoing-invoices/normalize-pending")
        self.assertEqual(status, 200, report)
        return report

    def test_canonical_create_legacy_compatibility_and_no_automatic_conversion(self):
        status, row = self.request("POST", "outgoing-invoices", {
            "invoice_number": "NEW", "invoice_date": "2026-09-15", "customer_name": "Customer",
            "currency_original": "EUR", "amount_original": "123456789012345678.123456",
        })
        self.assertEqual(status, 201, row)
        self.assertEqual(row["currency_original"], row["currency"])
        self.assertEqual(row["amount_original"], row["gross_amount"])
        self.assertEqual(row["amount_original"], "123456789012345678.123456")
        self.assertEqual(row["currency_common"], "EUR")
        self.assertIsNone(row["amount_common"])
        legacy = self.invoice("OLD", "12.34", currency="USD")
        self.assertEqual(legacy["currency_original"], "USD")
        self.assertEqual(legacy["amount_original"], "12.34")
        self.assertIsNone(legacy["amount_common"])
        with Session(self.engine) as db:
            stored = db.get(OutgoingInvoiceORM, row["id"])
            self.assertIsInstance(stored.amount_original, str)
            self.assertIsNone(stored.amount_common)
        with patch.object(config, "AR_COMMON_CURRENCY", "HUF"):
            self.assertEqual(self.invoice("CONFIG")["currency_common"], "HUF")
        self.assertIsNone(self.request("GET", "outgoing-invoices/" + row["id"])[1]["amount_common"])

    def test_manual_conversion_rate_date_rounding_and_pending_results(self):
        euro = self.invoice("EUR", "12.3456")
        huf = self.invoice("HUF", "402", currency="HUF")
        old = self.invoice("NO-RATE", "100", currency="HUF", invoice_date="2020-01-01")
        usd = self.invoice("USD", currency="USD")
        with Session(self.engine) as db:
            for day, rate in ((date(2026, 9, 10), "400"), (date(2026, 9, 16), "800")):
                db.add(ExchangeRateORM(rate_date=day, base_currency="EUR", quote_currency="HUF", rate=rate, unit="1", source="MNB"))
            db.commit()
        report = self.normalize()
        self.assertEqual((report["converted"], report["pending"]), (2, 2))
        results = {item["id"]: item for item in report["invoices"]}
        self.assertEqual(results[huf["id"]]["amount_common"], "1.01")
        self.assertIn("2026-09-10", results[huf["id"]]["message"])
        self.assertEqual(results[euro["id"]]["amount_common"], "12.3456")
        self.assertIn("No MNB", results[old["id"]]["message"])
        self.assertIn("No ECB", results[usd["id"]]["message"])
        again = self.normalize()
        self.assertEqual((again["converted"], again["pending"]), (0, 2))
        stored = self.request("GET", "outgoing-invoices/" + huf["id"])[1]
        self.assertEqual(stored["amount_original"], "402")
        self.assertEqual(stored["gross_amount"], "402")
        self.assertEqual(stored["amount_common"], "1.01")
        self.assertEqual(stored["outstanding_amount"], "402")

    def test_edits_invalidate_only_relevant_conversion_inputs_and_sync_aliases(self):
        row = self.invoice()
        path = "outgoing-invoices/" + row["id"]
        self.normalize()
        status, row = self.request("PATCH", path, {"remarks": "unchanged conversion"})
        self.assertEqual(status, 200, row)
        self.assertEqual(row["amount_common"], "100.00")
        for changes in ({"amount_original": "110.00"}, {"gross_amount": "120.00"},
                        {"invoice_date": "2026-09-14"}, {"currency_original": "HUF"},
                        {"currency": "EUR"}, {"currency_common": "HUF"}):
            self.normalize()
            status, row = self.request("PATCH", path, changes)
            self.assertEqual(status, 200, row)
            self.assertIsNone(row["amount_common"])
            self.assertEqual(row["amount_original"], row["gross_amount"])
            self.assertEqual(row["currency_original"], row["currency"])
        for changes in ({"amount_common": "99"}, {"amount_original": "1", "gross_amount": "2"},
                        {"currency_original": "USD", "currency": "EUR"}, {"amount_original": None},
                        {"currency_common": "BAD!"}):
            self.assertEqual(self.request("PATCH", path, changes)[0], 422)

    def test_allocations_stay_in_original_currency_and_restrict_edits(self):
        row = self.invoice()
        payment = self.payment("50")
        self.allocate(row, payment, "50")
        self.normalize()
        path = "outgoing-invoices/" + row["id"]
        self.assertEqual(self.request("PATCH", path, {"amount_original": "49"})[0], 400)
        self.assertEqual(self.request("PATCH", path, {"currency_original": "HUF"})[0], 400)
        row = self.request("GET", path)[1]
        self.assertEqual(row["paid_amount"], "50")
        self.assertEqual(row["outstanding_amount"], "50.00")
        self.assertEqual(row["amount_common"], "100.00")

    def test_old_database_upgrade_preserves_exact_values_and_is_repeatable(self):
        # Reproduce the old table's columns, retaining an allocation referencing it.
        payment = self.payment("1", currency="USD")
        with self.engine.begin() as db:
            db.exec_driver_sql("DROP TABLE invoice_payment_allocations")
            db.exec_driver_sql("DROP TABLE outgoing_invoices")
            db.exec_driver_sql("""CREATE TABLE outgoing_invoices (
                id VARCHAR(36) PRIMARY KEY, invoice_number TEXT UNIQUE NOT NULL,
                invoice_date DATE NOT NULL, due_date DATE, customer_name TEXT NOT NULL,
                customer_reference TEXT, currency VARCHAR(3) NOT NULL, net_amount TEXT,
                vat_amount TEXT, gross_amount TEXT NOT NULL, pdf_filename TEXT, pdf_sha256 TEXT,
                remarks TEXT, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)""")
            db.exec_driver_sql("""INSERT INTO outgoing_invoices
                (id, invoice_number, invoice_date, customer_name, currency, gross_amount, created_at, updated_at)
                VALUES ('legacy', 'LEGACY', '2026-01-01', 'Customer', 'USD',
                        '123456789012345678.123456', '2026-01-01', '2026-01-01')""")
            InvoicePaymentAllocationORM.__table__.create(db)
            db.exec_driver_sql("""INSERT INTO invoice_payment_allocations
                (id, invoice_id, payment_id, amount_allocated, created_at)
                VALUES ('allocation', 'legacy', ?, '1', '2026-01-01')""", (payment["id"],))
        with patch.object(database, "engine", self.engine):
            database.init_db()
            database.init_db()
        row = self.request("GET", "outgoing-invoices/legacy")[1]
        self.assertEqual(row["currency_original"], "USD")
        self.assertEqual(row["amount_original"], "123456789012345678.123456")
        self.assertEqual(row["currency_common"], "EUR")
        self.assertIsNone(row["amount_common"])
        self.assertEqual(row["created_at"], "2026-01-01T00:00:00")
        self.assertEqual(row["allocations"][0]["payment_id"], payment["id"])
        self.assertEqual(row["paid_amount"], "1")
        self.invoice("POST-UPGRADE")
        # Existing converted values must not be reset by subsequent startup.
        self.normalize()
        with patch.object(database, "engine", self.engine):
            database.init_db()
        rows = self.request("GET", "outgoing-invoices")[1]
        self.assertEqual(next(r for r in rows if r["invoice_number"] == "POST-UPGRADE")["amount_common"], "100.00")


if __name__ == "__main__":
    unittest.main()
