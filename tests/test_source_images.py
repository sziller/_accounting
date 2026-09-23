from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import quote, unquote

from fastapi import FastAPI

from app.core import config
from app.routers.router_accounting_entries import AccountingEntriesRouter


class SourceImageTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / "source_images"
        self.directory.mkdir()
        setting = patch.object(config, "AP_SOURCE_IMAGE_DIRECTORY", self.directory)
        setting.start()
        self.addCleanup(setting.stop)
        self.app = FastAPI()
        router = AccountingEntriesRouter()
        router.reinit()
        self.app.include_router(router)
        self.jpeg = (Path(__file__).resolve().parents[1] / "app/static/Accounting-LogoBitbucket.jpg").read_bytes()

    def request(self, encoded_filename: str) -> tuple[int, dict, bytes]:
        # Exercise routing and FileResponse through ASGI without an HTTP client
        # dependency or main.py's database/network startup side effects.
        raw_path = f"/acct/v0/source-images/{encoded_filename}"
        messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        asyncio.run(self.app(
            {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
             "http_version": "1.1", "method": "GET", "scheme": "http",
             "path": unquote(raw_path), "raw_path": raw_path.encode("ascii"),
             "query_string": b"", "root_path": "", "headers": [],
             "server": ("testserver", 80), "client": ("127.0.0.1", 1234)},
            receive, send,
        ))
        start = next(item for item in messages if item["type"] == "http.response.start")
        body = b"".join(item.get("body", b"") for item in messages if item["type"] == "http.response.body")
        return start["status"], dict(start["headers"]), body

    def test_jpeg_extensions_and_exact_filenames(self) -> None:
        for filename in ("receipt.jpg", "invoice.jpeg", "IMG_4821.JPG", "receipt.JpG",
                         "My Receipt 01.JPG", " receipt..01.JPG", "Árvíz #1%.jpeg"):
            with self.subTest(filename=filename):
                (self.directory / filename).write_bytes(self.jpeg)
                status, headers, body = self.request(quote(filename, safe=""))
                self.assertEqual(status, 200)
                self.assertEqual(headers[b"content-type"], b"image/jpeg")
                self.assertEqual(body, self.jpeg)

    def test_missing_file(self) -> None:
        self.assertEqual(self.request("missing.jpg")[0], 404)

    def test_missing_configured_directory(self) -> None:
        self.directory.rmdir()
        self.assertEqual(self.request("missing.jpg")[0], 404)

    def test_unsupported_extensions(self) -> None:
        for filename in ("source.png", "source.txt", "source.jpg.txt", "source"):
            with self.subTest(filename=filename):
                (self.directory / filename).write_bytes(b"not a JPEG")
                self.assertEqual(self.request(filename)[0], 415)

    def test_path_manipulation_is_rejected(self) -> None:
        (self.root / "secret.jpg").write_bytes(self.jpeg)
        for filename in ("../secret.jpg", "../../etc/passwd", "../config.py",
                         "subdir/../../secret.jpg", "/secret.jpg", "subdir/receipt.jpg",
                         "..\\secret.jpg", "subdir\\..\\..\\secret.jpg", "bad\x00.jpg"):
            with self.subTest(filename=filename):
                status, _, body = self.request(quote(filename, safe=""))
                self.assertIn(status, (400, 404))
                self.assertNotEqual(body, self.jpeg)

    def test_symlink_escape_is_rejected(self) -> None:
        # A sibling with the same prefix also must not pass containment checks.
        sibling = self.root / "source_images_private"
        sibling.mkdir()
        target = sibling / "secret.jpg"
        target.write_bytes(self.jpeg)
        (self.directory / "link.jpg").symlink_to(target)
        self.assertEqual(self.request("link.jpg")[0], 400)

    def test_directory_is_not_served(self) -> None:
        (self.directory / "directory.jpg").mkdir()
        self.assertEqual(self.request("directory.jpg")[0], 404)


if __name__ == "__main__":
    unittest.main()
