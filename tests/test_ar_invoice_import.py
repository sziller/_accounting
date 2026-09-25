"""Real extracted-layout shapes with synthetic parties and native PDF text streams."""
import hashlib
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

import test_receivables as fixtures
from app.core import config
from app.db.models import OutgoingInvoiceORM
from app.services.ar_invoice_import_service import import_ar_invoice_pdf, process_ar_invoice_directory
from app.services.ar_invoice_parser import ArInvoiceParseError, parse_ar_invoice_text
from app.services.pdf_extraction_service import extract_pdf_text

FIXTURES = Path(__file__).parent / "fixtures"
EN = (FIXTURES / "ar_honorarrechnung_de_en.txt").read_text()
HU = (FIXTURES / "ar_honorarrechnung_de_hu.txt").read_text()


def make_pdf(text):
    writer = PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({
        NameObject("/F1"): DictionaryObject({
            NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"), NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        })
    })})
    stream = DecodedStreamObject()
    commands = [b"BT /F1 10 Tf 12 TL 20 820 Td"]
    for line in text.splitlines():
        escaped = line.encode("cp1252").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
        commands.append(b"(" + escaped + b") Tj T*")
    commands.append(b"ET")
    stream.set_data(b"\n".join(commands))
    page[NameObject("/Contents")] = stream
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class ArInvoiceImportTests(unittest.TestCase):
    request = fixtures.ReceivablesTests.request

    def setUp(self):
        fixtures.ReceivablesTests.setUp(self)
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        setting = patch.object(config, "AR_SOURCE_DOCUMENT_DIRECTORY", self.directory)
        setting.start()
        self.addCleanup(setting.stop)
        self.factory = sessionmaker(bind=self.engine)

    def source(self, filename="invoice.pdf", text=EN):
        original = make_pdf(text)
        (self.directory / filename).write_bytes(original)
        return original

    def process(self):
        return process_ar_invoice_directory(session_factory=self.factory)

    def rows(self):
        with Session(self.engine) as db:
            return list(db.scalars(select(OutgoingInvoiceORM).order_by(OutgoingInvoiceORM.invoice_number)))

    def test_two_real_layout_variants_all_fields(self):
        for text, number, expected_date, customer, currency, amount in (
            (EN, "9101", date(2031, 4, 9), "Example Customer Ltd", "USD", "12400"),
            (HU, "9102", date(2032, 3, 8), "Example Customer zRt.", "EUR", "2350.00"),
        ):
            parsed = parse_ar_invoice_text(extract_pdf_text(make_pdf(text)))
            self.assertEqual(parsed.invoice_number, number)
            self.assertEqual(parsed.invoice_date, expected_date)
            self.assertEqual(parsed.customer_name, customer)
            self.assertEqual(parsed.currency, currency)
            self.assertEqual(parsed.net_amount, Decimal(amount))
            self.assertEqual(parsed.gross_amount, Decimal(amount))
            self.assertEqual(parsed.currency_original, currency)
            self.assertEqual(parsed.amount_original, Decimal(amount))
            self.assertEqual(parsed.currency_common, "EUR")
            self.assertIsNone(parsed.vat_amount)
            self.assertIsNone(parsed.due_date)
            self.assertIsNone(parsed.payment_date)
            self.assertIsNone(parsed.customer_reference)
            self.assertIn("14 Tage", parsed.remarks)

    def test_directory_order_persistence_and_archive_unchanged(self):
        originals = {name: self.source(name, text) for name, text in (("Z.PDF", HU), (" A invoice.pdf", EN))}
        before = {p.name: p.stat().st_mtime_ns for p in self.directory.iterdir()}
        result = self.process()
        self.assertEqual(result.imported, 2)
        self.assertEqual([item.filename for item in result.files], [" A invoice.pdf", "Z.PDF"])
        rows = self.rows()
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row.currency_original, row.currency)
            self.assertEqual(row.amount_original, row.gross_amount)
            self.assertEqual(row.currency_common, "EUR")
            self.assertIsNone(row.amount_common)
            self.assertEqual(row.pdf_sha256, hashlib.sha256(originals[row.pdf_filename]).hexdigest())
            path = self.directory / row.pdf_filename
            self.assertEqual(path.read_bytes(), originals[row.pdf_filename])
            self.assertEqual(path.stat().st_mtime_ns, before[row.pdf_filename])
        self.assertEqual(rows[0].currency, "USD")
        self.assertEqual(rows[0].gross_amount, "12400")

    def test_repeat_and_renamed_hash_are_skipped(self):
        original = self.source()
        self.assertEqual(self.process().imported, 1)
        (self.directory / "renamed.pdf").write_bytes(original)
        result = self.process()
        self.assertEqual(result.already_imported, 2)
        self.assertEqual(result.imported, 0)
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.rows()[0].pdf_filename, "invoice.pdf")

    def test_same_number_different_pdf_conflict_preserves_record(self):
        self.source("a.pdf")
        self.source("b.pdf", EN.replace("12 400", "12 300"))
        result = self.process()
        self.assertEqual(result.imported, 1)
        self.assertEqual(result.failed, 1)
        self.assertEqual(result.files[1].error_code, "invoice_number_conflict")
        self.assertEqual(self.rows()[0].gross_amount, "12400")

    def test_manual_invoice_number_with_no_hash_is_conflict(self):
        self.source()
        status, _ = self.request("POST", "outgoing-invoices", {
            "invoice_number": "9101", "invoice_date": "2031-04-09", "customer_name": "Manual",
            "currency": "USD", "gross_amount": "12400",
        })
        self.assertEqual(status, 201)
        self.assertEqual(self.process().files[0].error_code, "invoice_number_conflict")
        self.assertIsNone(self.rows()[0].pdf_sha256)

    def test_bad_file_does_not_stop_batch_and_non_pdf_ignored(self):
        (self.directory / "a-broken.pdf").write_bytes(b"%PDF-1.7\nbroken")
        (self.directory / "b.txt").write_text("ignored")
        self.source("c-good.pdf")
        (self.directory / "d-directory.pdf").mkdir()
        result = self.process()
        self.assertEqual([item.filename for item in result.files], ["a-broken.pdf", "c-good.pdf", "d-directory.pdf"])
        self.assertEqual([item.status for item in result.files], ["failed", "imported", "failed"])
        self.assertEqual(len(self.rows()), 1)

    def test_parse_failures_never_write_partial_records(self):
        variants = [
            EN.replace("Honorarrechnung Nr.: 9101", "Unknown invoice"),
            EN.replace("9. April 2031", "invalid date"),
            EN.replace("Example Customer Ltd Example Customer Ltd", "Unknown recipient"),
            EN.replace("Nettohonorar – net amount: 12 400 USD", "Nettohonorar – net amount: 12 300 USD"),
            EN.replace("gross amount:", "unknown total:"),
            EN.replace("12 400 USD", "12,400 USD"),
            EN.replace("gross amount: (see Note) 12 400 USD", "gross amount: (see Note) 12 400 EUR"),
            EN.replace("der nächsten 14 Tage,", "pay whenever"),
        ]
        for i, text in enumerate(variants):
            self.source(f"{i}.pdf", text)
        result = self.process()
        self.assertEqual(result.failed, len(variants))
        self.assertEqual(self.rows(), [])

    def test_exact_decimal_symbol_currency_and_unsupported_pages(self):
        text = HU.replace("2350.00 EUR", "0.100001 €")
        self.source(text=text)
        self.assertEqual(self.process().imported, 1)
        row = self.rows()[0]
        self.assertEqual(row.gross_amount, "0.100001")
        self.assertEqual(row.currency, "EUR")
        with self.assertRaises(ArInvoiceParseError):
            parse_ar_invoice_text(EN + "\f" + EN)

    def test_explicit_endpoint_and_missing_directory(self):
        self.source()
        status, report = self.request("POST", "outgoing-invoices/process-directory")
        self.assertEqual(status, 200)
        self.assertEqual(report["imported"], 1)
        status, again = self.request("POST", "outgoing-invoices/process-directory")
        self.assertEqual(status, 200)
        self.assertEqual(again["already_imported"], 1)
        with patch.object(config, "AR_SOURCE_DOCUMENT_DIRECTORY", self.directory / "absent"):
            self.assertEqual(self.request("POST", "outgoing-invoices/process-directory")[0], 400)

    def test_concurrent_imports_are_idempotent(self):
        self.source()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: import_ar_invoice_pdf("invoice.pdf", session_factory=self.factory), range(2)))
        self.assertCountEqual([item.status for item in results], ["imported", "already_imported"])
        self.assertEqual(len(self.rows()), 1)

    def test_path_rejections_do_not_write(self):
        for filename in ("../secret.pdf", "subdir/../../secret.pdf", "image.jpg", "missing.pdf"):
            result = import_ar_invoice_pdf(filename, session_factory=self.factory)
            self.assertEqual(result.status, "failed")
        self.assertEqual(self.rows(), [])

    def test_source_files_endpoint_sorted_safe_and_read_only(self):
        self.source("z.PDF")
        self.source(" a.pdf", HU)
        (self.directory / "ignored.txt").write_text("ignored")
        (self.directory / "folder.pdf").mkdir()
        (self.directory / "outside.pdf").symlink_to(Path(__file__).resolve())
        status, body = self.request("GET", "outgoing-invoices/source-files")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"directory": self.directory.name, "files": [" a.pdf", "z.PDF"]})
        self.assertEqual(self.rows(), [])

    def test_source_files_missing_empty_and_unreadable(self):
        self.assertEqual(self.request("GET", "outgoing-invoices/source-files")[1]["files"], [])
        with patch.object(config, "AR_SOURCE_DOCUMENT_DIRECTORY", self.directory / "missing"):
            self.assertEqual(self.request("GET", "outgoing-invoices/source-files"),
                             (200, {"directory": "missing", "files": []}))
        with patch.object(Path, "iterdir", side_effect=PermissionError("private path")):
            status, body = self.request("GET", "outgoing-invoices/source-files")
            self.assertEqual(status, 503)
            self.assertNotIn("private path", str(body))


if __name__ == "__main__":
    unittest.main()
