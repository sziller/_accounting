"""Synthetic native PDFs test extraction mechanics, not an unobserved invoice layout."""
import hashlib
import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.core import config
from app.services.pdf_extraction_service import (
    PdfExtractionError, extract_pdf_text, load_outgoing_invoice_pdf,
)


def native_pdf(texts=("Extraction fixture",), *, password=None):
    writer = PdfWriter()
    for text in texts:
        page = writer.add_blank_page(width=595, height=842)
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})
        })
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 50 750 Td ({text}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = stream
    if password:
        writer.encrypt(password)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class PdfExtractionTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / "outgoing_invoices"
        self.directory.mkdir()
        setting = patch.object(config, "AR_INVOICE_PDF_DIRECTORY", self.directory)
        setting.start()
        self.addCleanup(setting.stop)

    def assert_error(self, code, operation, *args):
        with self.assertRaises(PdfExtractionError) as caught:
            operation(*args)
        self.assertEqual(caught.exception.code, code)
        self.assertNotIn(str(self.root), str(caught.exception))

    def test_native_text_extraction_preserves_page_order(self):
        text = extract_pdf_text(native_pdf(("First page 123.45", "Second page")))
        self.assertIn("First page 123.45", text)
        self.assertIn("\n\f\n", text)
        self.assertLess(text.index("First page"), text.index("Second page"))

    def test_full_file_loading_exact_filename_hash_and_page_count(self):
        original = native_pdf(("Page one", "Page two"))
        filename = " My Invoice 01.PDF"
        source = self.directory / filename
        source.write_bytes(original)
        result = load_outgoing_invoice_pdf(filename)
        self.assertEqual(result.pdf_filename, filename)
        self.assertEqual(result.pdf_sha256, hashlib.sha256(original).hexdigest())
        self.assertEqual(result.page_count, 2)
        self.assertIn("Page one", result.page_texts[0])
        self.assertIn("Page two", result.page_texts[1])
        self.assertEqual(source.read_bytes(), original)
        (self.directory / "renamed.pdf").write_bytes(original)
        self.assertEqual(load_outgoing_invoice_pdf("renamed.pdf").pdf_sha256, result.pdf_sha256)

    def test_malformed_and_non_pdf_bytes(self):
        self.assert_error("invalid_pdf", extract_pdf_text, b"not a PDF")
        self.assert_error("text_extraction_failed", extract_pdf_text, b"%PDF-1.7\nbroken")
        (self.directory / "wrong.pdf").write_bytes(b"not a PDF")
        self.assert_error("invalid_pdf", load_outgoing_invoice_pdf, "wrong.pdf")

    def test_blank_and_encrypted_documents(self):
        self.assert_error("no_embedded_text", extract_pdf_text, native_pdf(("",)))
        self.assert_error("encrypted_pdf", extract_pdf_text, native_pdf(password="secret"))

    def test_filename_and_path_restrictions(self):
        for filename in ("../secret.pdf", "subdir/../../secret.pdf", "/secret.pdf", "..\\secret.pdf", "bad\x00.pdf"):
            with self.subTest(filename=filename):
                self.assert_error("invalid_filename", load_outgoing_invoice_pdf, filename)
        self.assert_error("unsupported_extension", load_outgoing_invoice_pdf, "source.jpg")
        self.assert_error("file_not_found", load_outgoing_invoice_pdf, "missing.pdf")
        (self.directory / "folder.pdf").mkdir()
        self.assert_error("file_not_found", load_outgoing_invoice_pdf, "folder.pdf")

    def test_symlink_escape(self):
        sibling = self.root / "outgoing_invoices_private"
        sibling.mkdir()
        outside = sibling / "secret.pdf"
        outside.write_bytes(native_pdf())
        (self.directory / "link.pdf").symlink_to(outside)
        self.assert_error("invalid_filename", load_outgoing_invoice_pdf, "link.pdf")

    def test_missing_directory_is_not_created(self):
        self.directory.rmdir()
        self.assert_error("file_not_found", load_outgoing_invoice_pdf, "missing.pdf")
        self.assertFalse(self.directory.exists())


if __name__ == "__main__":
    unittest.main()
