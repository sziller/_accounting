# app/schemas/accounting_entry_schema.py

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.accounting_rules import (
    CURRENCIES,
    ENTRY_TYPES,
    PAYMENT_METHODS,
    TAX_SCOPES,
    WRITEOFF_METHODS,
    get_allowed_category_codes,
)
from app.domain.invoice_number_policy import (
    INVOICE_NUMBER_DESCRIPTION,
    INVOICE_NUMBER_MAX_LENGTH,
    INVOICE_NUMBER_PATTERN,
    canonicalize_invoice_number,
)


EntryType = Literal[
    "expense",
    "income",
    "tax",
    "private",
    "correction",
]

TaxScope = Literal[
    "domestic",
    "eu",
    "third_country",
    "not_applicable",
]

PaymentMethod = Literal[
    "cash",
    "bank_transfer",
    "card",
    "paypal",
    "blockchain",
    "unknown",
]

WriteoffMethod = Literal[
    "immediate",
    "partial",
    "multi_year",
    "none",
]


class AccountingEntryCreateSchema(BaseModel):
    """=== schema class ====
    Validate raw user-entered API data for creating one accounting entry.
    === by Sziller & ChatGPT ==="""

    model_config = ConfigDict(extra="forbid")

    entry_type: EntryType = "expense"
    category_code: str = Field(min_length=1, max_length=64)
    tax_scope: TaxScope = "domestic"

    counterparty_name: str = Field(min_length=1, max_length=255)

    payment_method: PaymentMethod = "bank_transfer"
    payment_date: date

    has_invoice: bool = True
    invoice_number: str | None = Field(
        default=None,
        max_length=INVOICE_NUMBER_MAX_LENGTH,
        pattern=INVOICE_NUMBER_PATTERN,
        description=INVOICE_NUMBER_DESCRIPTION,
    )
    invoice_date: date | None = None

    amount_original: Decimal = Field(
        gt=Decimal("0"),
        max_digits=18,
        decimal_places=8,
        examples=[Decimal("123.45")],
    )
    currency_original: str = Field(default="EUR", min_length=3, max_length=3)

    remarks: str | None = None
    tags: list[str] = Field(default_factory=list)

    source_filename: str | None = Field(default=None, max_length=255)

    @field_validator("invoice_number", mode="before")
    @classmethod
    def canonicalize_optional_invoice_number(cls, value: str | None) -> str | None:
        """Apply the authoritative invoice-number policy before field constraints."""
        return canonicalize_invoice_number(value)

    @field_validator("source_filename", mode="before")
    @classmethod
    def normalize_source_filename(cls, value: str | None) -> str | None:
        """Normalize empty or whitespace-only source filenames to missing values."""
        if value is None:
            return None

        if isinstance(value, str) and not value.strip():
            return None

        return value

    @field_validator("category_code")
    @classmethod
    def validate_category_code(cls, value: str) -> str:
        """=== schema function ====
        Validate that the category code is known by the domain rule registry.
        === by Sziller & ChatGPT ==="""
        normalized = value.strip().lower()

        if normalized not in get_allowed_category_codes():
            raise ValueError(f"Unknown category code: {value}")

        return normalized

    @field_validator("currency_original")
    @classmethod
    def validate_currency_original(cls, value: str) -> str:
        """=== schema function ====
        Validate and normalize the original transaction currency.
        === by Sziller & ChatGPT ==="""
        normalized = value.strip().upper()

        if normalized not in CURRENCIES:
            raise ValueError(f"Unsupported currency: {value}")

        return normalized

    @field_validator("counterparty_name")
    @classmethod
    def normalize_counterparty_name(cls, value: str) -> str:
        """=== schema function ====
        Normalize counterparty names by trimming whitespace.
        === by Sziller & ChatGPT ==="""
        return value.strip()

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        """=== schema function ====
        Normalize tag strings by trimming whitespace and removing empties.
        === by Sziller & ChatGPT ==="""
        return [item.strip() for item in value if item.strip()]

class AccountingEntryUpdateSchema(AccountingEntryCreateSchema):
    """=== schema class ====
    Validate full raw-field replacement data for updating one accounting entry.

    This schema intentionally mirrors AccountingEntryCreateSchema.

    Editable update data must contain only raw/user-controlled fields.
    Derived fields such as booking_year, amount_common, exchange_rate,
    VAT amounts, deductible amounts, writeoff_method, conversion_status,
    timestamps, and database ids are not accepted here.

    Updating an entry means replacing its editable raw fields and letting
    the backend processor recalculate all derived values.
    === by Sziller & ChatGPT ==="""

    pass


class AccountingEntryReadSchema(BaseModel):
    """=== schema class ====
    Represent one fully processed accounting entry returned by the API.
    === by Sziller & ChatGPT ==="""

    model_config = ConfigDict(from_attributes=True)

    id: str

    entry_type: str
    category_code: str
    tax_scope: str
    counterparty_name: str
    payment_method: str
    payment_date: date
    booking_year: int

    has_invoice: bool
    invoice_number: str | None
    invoice_date: date | None

    amount_original: Decimal
    currency_original: str
    amount_common: Decimal | None
    currency_common: str

    exchange_rate: Decimal | None
    exchange_rate_date: date | None

    vat_rate_percent: Decimal
    vat_amount: Decimal | None

    deductible_percent: Decimal
    deductible_amount: Decimal | None
    deductible_vat_amount: Decimal | None
    writeoff_method: WriteoffMethod

    remarks: str | None
    tags: list[str]

    source_filename: str | None

    created_at: datetime
    updated_at: datetime

    conversion_status: str
    conversion_note: str | None
    
class AccountingEntryBatchCreateSchema(BaseModel):
    """=== schema class ====
    Validate a batch of raw accounting-entry payloads.
    === by Sziller & ChatGPT ==="""

    model_config = ConfigDict(extra="forbid")

    entries: list[AccountingEntryCreateSchema] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_source_filename_consistency(self) -> "AccountingEntryBatchCreateSchema":
        """Require every entry in a batch to use the same source-presence state."""
        source_presence = [entry.source_filename is not None for entry in self.entries]

        if any(source_presence) and not all(source_presence):
            raise ValueError(
                "All entries in one batch must either provide source_filename "
                "or all leave it null."
            )

        return self
    
