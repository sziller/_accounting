from __future__ import annotations

import asyncio
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest.mock import patch

from fastapi import FastAPI
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import database
from app.db.database import enable_sqlite_foreign_keys, get_db_session
from app.db.models import Base, IncomingPaymentORM, InvoicePaymentAllocationORM, OutgoingInvoiceORM
from app.routers.router_receivables import ReceivablesRouter
from app.schemas.receivables_schema import InvoicePaymentAllocationCreateSchema
from app.services.receivables_service import ReceivablesError, ReceivablesService


class ReceivablesTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.engine = create_engine(f"sqlite:///{Path(temporary.name) / 'test.db'}",
                                    connect_args={"check_same_thread": False})
        event.listen(self.engine, "connect", enable_sqlite_foreign_keys)
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.app = FastAPI()
        self.app.include_router(ReceivablesRouter())

        def session():
            with Session(self.engine) as db:
                yield db
        self.app.dependency_overrides[get_db_session] = session

    def request(self, method, path, payload=None):
        messages = []
        body = json.dumps(payload).encode() if payload is not None else b""

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            messages.append(message)

        path = "/acct/v0/" + path
        asyncio.run(self.app({
            "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1", "method": method, "scheme": "http", "path": path,
            "raw_path": path.encode(), "query_string": b"", "root_path": "",
            "headers": [(b"content-type", b"application/json")],
            "server": ("testserver", 80), "client": ("127.0.0.1", 1234),
        }, receive, send))
        start = next(item for item in messages if item["type"] == "http.response.start")
        result = b"".join(item.get("body", b"") for item in messages if item["type"] == "http.response.body")
        return start["status"], json.loads(result) if result else None

    def invoice(self, number="INV-1", amount="100.00", **extra):
        status, body = self.request("POST", "outgoing-invoices", {
            "invoice_number": number, "invoice_date": "2026-09-15", "customer_name": "Customer",
            "currency": "EUR", "gross_amount": amount, **extra,
        })
        self.assertEqual(status, 201, body)
        return body

    def payment(self, amount="100.00", **extra):
        status, body = self.request("POST", "incoming-payments", {
            "payment_date": "2026-09-16", "amount": amount, "currency": "EUR", **extra,
        })
        self.assertEqual(status, 201, body)
        return body

    def allocate(self, invoice, payment, amount, expected=201):
        status, body = self.request("POST", "invoice-payment-allocations", {
            "invoice_id": invoice["id"], "payment_id": payment["id"], "amount_allocated": amount,
        })
        self.assertEqual(status, expected, body)
        return body

    def test_invoice_crud_decimal_roundtrip_and_unique_number(self):
        invoice = self.invoice(amount="123456789012345678.123456")
        self.assertEqual(invoice["gross_amount"], "123456789012345678.123456")
        path = "outgoing-invoices/" + invoice["id"]
        self.assertEqual(self.request("GET", path), (200, invoice))
        self.assertEqual(self.request("GET", "outgoing-invoices"), (200, [invoice]))
        status, updated = self.request("PATCH", path, {"remarks": "updated", "due_date": "2099-01-01"})
        self.assertEqual(status, 200)
        self.assertEqual(updated["remarks"], "updated")
        self.assertEqual(updated["gross_amount"], invoice["gross_amount"])
        self.assertEqual(updated["created_at"], invoice["created_at"])
        self.assertGreaterEqual(updated["updated_at"], invoice["updated_at"])
        status, _ = self.request("POST", "outgoing-invoices", {
            key: invoice[key] for key in ("invoice_number", "invoice_date", "customer_name", "currency", "gross_amount")
        })
        self.assertEqual(status, 409)
        other = self.invoice("INV-2")
        self.assertEqual(self.request("PATCH", "outgoing-invoices/" + other["id"], {"invoice_number": "INV-1"})[0], 409)
        with Session(self.engine) as db:
            stored = db.get(OutgoingInvoiceORM, invoice["id"])
            self.assertIsInstance(stored.gross_amount, str)
            self.assertEqual(stored.gross_amount, invoice["gross_amount"])

    def test_payment_crud(self):
        payment = self.payment("0.123456", currency="JPY")
        path = "incoming-payments/" + payment["id"]
        self.assertEqual(self.request("GET", path), (200, payment))
        self.assertEqual(self.request("GET", "incoming-payments"), (200, [payment]))
        status, updated = self.request("PATCH", path, {"payer_name": "Payer", "amount": "0.654321"})
        self.assertEqual(status, 200)
        self.assertEqual(updated["amount"], "0.654321")
        self.assertEqual(updated["payer_name"], "Payer")
        self.assertEqual(updated["allocations"], [])

    def test_invalid_inputs_and_readonly_fields(self):
        invoice_payload = {"invoice_number": "INV", "invoice_date": "2026-09-15", "customer_name": "Customer", "currency": "EUR", "gross_amount": "10"}
        for extra in ({"invoice_number": "  "}, {"customer_name": " "}, {"gross_amount": "0"},
                      {"gross_amount": "-1"}, {"net_amount": "-1"}, {"vat_amount": "-1"},
                      {"gross_amount": "NaN"}, {"gross_amount": "Infinity"}, {"currency": "EURO"},
                      {"invoice_date": "not-a-date"}, {"pdf_sha256": "bad"}, {"paid_amount": "1"},
                      {"outstanding_amount": "1"}, {"payment_status": "paid"},
                      {"net_amount": "8", "vat_amount": "3"}, {"gross_amount": "0.1234567"}):
            with self.subTest(extra=extra):
                self.assertEqual(self.request("POST", "outgoing-invoices", {**invoice_payload, **extra})[0], 422)
        for amount in ("0", "-1", "NaN", "Infinity"):
            self.assertEqual(self.request("POST", "incoming-payments", {
                "payment_date": "2026-09-16", "amount": amount, "currency": "EUR",
            })[0], 422)

    def test_patch_merge_validation_and_nullable_fields(self):
        invoice = self.invoice(net_amount="80", vat_amount="20", pdf_filename="Original Name.PDF", pdf_sha256="a" * 64)
        path = "outgoing-invoices/" + invoice["id"]
        for payload in ({"gross_amount": "90"}, {"gross_amount": None}, {"invoice_number": None}, {"currency": None}):
            self.assertEqual(self.request("PATCH", path, payload)[0], 422)
        status, updated = self.request("PATCH", path, {"net_amount": None, "pdf_filename": None, "gross_amount": "90"})
        self.assertEqual(status, 200)
        self.assertIsNone(updated["net_amount"])
        self.assertIsNone(updated["pdf_filename"])
        payment = self.payment()
        self.assertEqual(self.request("PATCH", "incoming-payments/" + payment["id"], {"amount": None})[0], 422)

    def test_partial_multiple_payments_and_derived_totals(self):
        invoice = self.invoice()
        first = self.payment("30.10")
        second = self.payment("69.90")
        self.allocate(invoice, first, "30.10")
        status, partial = self.request("GET", "outgoing-invoices/" + invoice["id"])
        self.assertEqual(status, 200)
        self.assertEqual(Decimal(partial["paid_amount"]), Decimal("30.10"))
        self.assertEqual(Decimal(partial["outstanding_amount"]), Decimal("69.90"))
        self.assertEqual(partial["payment_status"], "partially_paid")
        self.assertEqual(partial["allocations"][0]["payment_date"], first["payment_date"])
        self.allocate(invoice, second, "69.90")
        paid = self.request("GET", "outgoing-invoices/" + invoice["id"])[1]
        self.assertEqual(paid["payment_status"], "paid")
        self.assertEqual(Decimal(paid["paid_amount"]), Decimal("100"))
        self.assertEqual(Decimal(paid["outstanding_amount"]), 0)
        self.assertEqual(len(paid["allocations"]), 2)

    def test_payment_split_across_invoices_and_allocation_removal(self):
        first = self.invoice(amount="40")
        second = self.invoice("INV-2", "60")
        payment = self.payment()
        allocation = self.allocate(first, payment, "40")
        self.allocate(second, payment, "60")
        detail = self.request("GET", "incoming-payments/" + payment["id"])[1]
        self.assertEqual(Decimal(detail["unallocated_amount"]), 0)
        self.assertEqual({a["invoice_number"] for a in detail["allocations"]}, {"INV-1", "INV-2"})
        self.assertEqual(self.request("DELETE", "invoice-payment-allocations/" + allocation["id"]), (204, None))
        invoice = self.request("GET", "outgoing-invoices/" + first["id"])[1]
        self.assertEqual(invoice["payment_status"], "open")
        self.assertEqual(Decimal(invoice["outstanding_amount"]), 40)
        self.assertEqual(self.request("DELETE", "invoice-payment-allocations/" + allocation["id"])[0], 404)

    def test_allocation_limits_currency_and_missing_ids(self):
        invoice = self.invoice()
        payment = self.payment("50")
        for amount in ("0", "-1"):
            self.allocate(invoice, payment, amount, 422)
        self.allocate(invoice, payment, "51", 400)
        self.allocate(invoice, self.payment("200"), "101", 400)
        self.allocate(invoice, self.payment(currency="USD"), "1", 400)
        self.allocate({"id": "missing"}, payment, "1", 404)
        self.allocate(invoice, {"id": "missing"}, "1", 404)
        self.allocate(invoice, payment, "40")
        self.allocate(invoice, payment, "11", 400)
        self.allocate(invoice, self.payment("100"), "61", 400)

    def test_updates_cannot_invalidate_allocations(self):
        invoice = self.invoice()
        payment = self.payment()
        self.allocate(invoice, payment, "60")
        for path, field in (("outgoing-invoices/" + invoice["id"], "gross_amount"),
                            ("incoming-payments/" + payment["id"], "amount")):
            self.assertEqual(self.request("PATCH", path, {field: "59"})[0], 400)
            self.assertEqual(self.request("PATCH", path, {"currency": "USD"})[0], 400)
            self.assertEqual(self.request("PATCH", path, {field: "60"})[0], 200)
            self.assertEqual(self.request("DELETE", path)[0], 405)

    def test_status_precedence(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        invoice = self.invoice(due_date=yesterday)
        self.assertEqual(invoice["payment_status"], "overdue")
        payment = self.payment()
        self.allocate(invoice, payment, "40")
        self.assertEqual(self.request("GET", "outgoing-invoices/" + invoice["id"])[1]["payment_status"], "overdue")
        self.allocate(invoice, payment, "60")
        self.assertEqual(self.request("GET", "outgoing-invoices/" + invoice["id"])[1]["payment_status"], "paid")
        self.assertEqual(self.invoice("TODAY", due_date=date.today().isoformat())["payment_status"], "open")

    def test_database_foreign_keys_and_positive_constraint(self):
        invoice = self.invoice()
        payment = self.payment()
        for invoice_id, payment_id, amount in (("missing", payment["id"], "1"),
                                               (invoice["id"], "missing", "1"),
                                               (invoice["id"], payment["id"], "0"),
                                               (invoice["id"], payment["id"], "-1"),
                                               (invoice["id"], payment["id"], "garbage")):
            with Session(self.engine) as db:
                db.add(InvoicePaymentAllocationORM(invoice_id=invoice_id, payment_id=payment_id, amount_allocated=amount))
                with self.assertRaises(IntegrityError):
                    db.commit()
        self.allocate(invoice, payment, "1")
        for model, identity in ((OutgoingInvoiceORM, invoice["id"]), (IncomingPaymentORM, payment["id"])):
            with Session(self.engine) as db:
                db.delete(db.get(model, identity))
                with self.assertRaises(IntegrityError):
                    db.commit()

    def test_concurrent_allocations_cannot_overspend_invoice_or_payment(self):
        for shared in ("invoice", "payment"):
            with self.subTest(shared=shared):
                invoices = [self.invoice(f"{shared}-{i}") for i in range(2)]
                payments = [self.payment() for _ in range(2)]
                barrier = Barrier(2)

                def allocate(index):
                    payload = InvoicePaymentAllocationCreateSchema(
                        invoice_id=invoices[0 if shared == "invoice" else index]["id"],
                        payment_id=payments[0 if shared == "payment" else index]["id"],
                        amount_allocated="60",
                    )
                    with Session(self.engine) as db:
                        barrier.wait(timeout=5)
                        try:
                            ReceivablesService(db).create_allocation(payload)
                            return "created"
                        except ReceivablesError as exc:
                            self.assertEqual(exc.status_code, 400)
                            return "rejected"
                with ThreadPoolExecutor(max_workers=2) as executor:
                    results = list(executor.map(allocate, range(2)))
                self.assertCountEqual(results, ["created", "rejected"])

    def test_init_db_is_additive_and_repeatable(self):
        with self.engine.begin() as connection:
            connection.execute(text("CREATE TABLE existing_data (value TEXT)"))
            connection.execute(text("INSERT INTO existing_data VALUES ('preserved')"))
            for table in (InvoicePaymentAllocationORM.__table__, OutgoingInvoiceORM.__table__, IncomingPaymentORM.__table__):
                table.drop(connection)
        with patch.object(database, "engine", self.engine):
            database.init_db()
            database.init_db()
        with self.engine.connect() as connection:
            self.assertEqual(connection.scalar(text("SELECT value FROM existing_data")), "preserved")
        self.invoice()
        self.payment()

    def test_missing_records_and_openapi(self):
        for collection in ("outgoing-invoices", "incoming-payments"):
            self.assertEqual(self.request("GET", collection + "/missing")[0], 404)
            self.assertEqual(self.request("PATCH", collection + "/missing", {})[0], 404)
        schema = self.app.openapi()
        self.assertIn("/acct/v0/invoice-payment-allocations/{id}", schema["paths"])
        self.assertNotIn("paid_amount", schema["components"]["schemas"]["OutgoingInvoiceCreateSchema"]["properties"])


if __name__ == "__main__":
    unittest.main()
