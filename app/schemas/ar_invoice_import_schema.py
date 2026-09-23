"""Explicit directory-processing reports; no accounting-entry state is embedded."""
from typing import Literal

from pydantic import BaseModel


class ArInvoiceSourceFilesSchema(BaseModel):
    directory: str
    files: list[str]


class ArInvoiceFileResultSchema(BaseModel):
    filename: str
    status: Literal["imported", "already_imported", "failed"]
    outgoing_invoice_id: str | None = None
    invoice_number: str | None = None
    error_code: str | None = None
    error: str | None = None


class ArInvoiceDirectoryResultSchema(BaseModel):
    files: list[ArInvoiceFileResultSchema]
    imported: int
    already_imported: int
    failed: int
