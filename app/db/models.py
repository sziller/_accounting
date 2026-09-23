# app/db/models.py

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.domain.invoice_number_policy import (
    INVOICE_NUMBER_MAX_LENGTH,
    build_invoice_number_sqlite_check,
)


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy ORM models.
    """

    pass


def utc_now() -> datetime:
    """
    Return a timezone-aware UTC timestamp.

    Used for created_at / updated_at fields.
    """
    return datetime.now(timezone.utc)


class AccountingEntryORM(Base):
    """
    Database representation of one bookkeeping/accounting entry.

    This is intentionally named AccountingEntry rather than Invoice because
    the legacy Spending object represents more than invoices: expenses,
    income, tax payments, entries without invoices, currency conversion,
    VAT treatment, write-off values, and reporting metadata.
    """

    __tablename__ = "accounting_entries"

    __table_args__ = (
        CheckConstraint(
            build_invoice_number_sqlite_check(),
            name="ck_accounting_entries_invoice_number_canonical",
        ),
        Index(
            "uq_accounting_entries_invoice_number_given",
            "invoice_number",
            unique=True,
            sqlite_where=text("invoice_number IS NOT NULL AND invoice_number != ''"),
        ),
    )
    
    # -------------------------------------------------------------------------
    # Identity
    # -------------------------------------------------------------------------

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # -------------------------------------------------------------------------
    # Classification
    # -------------------------------------------------------------------------

    entry_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )

    category_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    tax_scope: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )

    # -------------------------------------------------------------------------
    # Counterparty
    # -------------------------------------------------------------------------

    counterparty_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    # -------------------------------------------------------------------------
    # Payment data
    # -------------------------------------------------------------------------

    payment_method: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    payment_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    booking_year: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )

    # -------------------------------------------------------------------------
    # Invoice metadata
    # -------------------------------------------------------------------------

    has_invoice: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    invoice_number: Mapped[str | None] = mapped_column(
        String(INVOICE_NUMBER_MAX_LENGTH),
        nullable=True,
        index=True,
    )

    invoice_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        index=True,
    )

    # -------------------------------------------------------------------------
    # Original amount
    #
    # Monetary values are stored as strings to avoid SQLite floating-point
    # precision issues. The service/domain layer should convert these to Decimal.
    # -------------------------------------------------------------------------

    amount_original: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    currency_original: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        index=True,
    )

    # -------------------------------------------------------------------------
    # Common/reporting currency amount
    # -------------------------------------------------------------------------

    amount_common: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    
    currency_common: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="EUR",
        index=True,
    )

    # -------------------------------------------------------------------------
    # Exchange-rate snapshot
    # -------------------------------------------------------------------------

    exchange_rate: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    exchange_rate_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    # -------------------------------------------------------------------------
    # VAT snapshot
    # -------------------------------------------------------------------------

    vat_rate_percent: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    vat_amount: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    # -------------------------------------------------------------------------
    # Deduction / write-off snapshot
    # -------------------------------------------------------------------------

    deductible_percent: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    deductible_amount: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    deductible_vat_amount: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    writeoff_method: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="immediate",
    )

    # -------------------------------------------------------------------------
    # Free-form metadata
    # -------------------------------------------------------------------------

    remarks: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    tags_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # -------------------------------------------------------------------------
    # Optional recognition-source tracking
    # -------------------------------------------------------------------------

    source_filename: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    # -------------------------------------------------------------------------
    # Audit timestamps
    # -------------------------------------------------------------------------

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
    
    # Misc

    conversion_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="not_required",
        index=True,
    )

    conversion_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )


class ExchangeRateORM(Base):
    """=== db model class ====
    Store historical exchange-rate snapshots used for accounting conversions.
    === by Sziller & ChatGPT ==="""

    __tablename__ = "eur_huf_exchange_rates"
    
    __table_args__ = (
        UniqueConstraint(
            "rate_date",
            "base_currency",
            "quote_currency",
            "source",
            name="uq_exchange_rate_date_pair_source",
        ),
        Index("uq_exchange_rate_date_pair", "rate_date", "base_currency", "quote_currency", unique=True),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # The date for which the rate is officially valid/published.
    rate_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    # Uniform convention: 1 EUR = rate quote-currency units. Example MNB EUR/HUF:
    # base_currency = "EUR"
    # quote_currency = "HUF"
    # rate = "390.12"
    # meaning: 1 EUR = 390.12 HUF
    base_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        index=True,
    )

    quote_currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        index=True,
    )

    rate: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    unit: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="1",
    )

    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class EurUsdExchangeRateORM(Base):
    """Dedicated EUR/USD archive; 1 EUR = rate USD, stored as decimal text."""
    __tablename__ = "eur_usd_exchange_rates"
    __table_args__ = (
        UniqueConstraint("rate_date", name="uq_eur_usd_rate_date"),
        Index("uq_eur_usd_rate_pair", "rate_date", "base_currency", "quote_currency", unique=True),
        CheckConstraint("base_currency = 'EUR' AND quote_currency = 'USD'", name="ck_eur_usd_pair"),
        CheckConstraint("unit = '1'", name="ck_eur_usd_unit"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    rate_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    rate: Mapped[str] = mapped_column(String(64), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="1")
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


# Receivables use the same exact decimal-string storage as accounting entries.
def _money_check(column: str, *, positive: bool = True) -> str:
    check = (
        f"length({column}) BETWEEN 1 AND 64 AND "
        f"{column} NOT GLOB '*[^0-9.]*' AND "
        f"length({column}) - length(replace({column}, '.', '')) <= 1 AND "
        f"{column} GLOB '*[0-9]*'"
    )
    if positive:
        check += f" AND {column} GLOB '*[1-9]*'"
    return check


class ReceivableIdentityMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ReceivableTimestampMixin(ReceivableIdentityMixin):
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class OutgoingInvoiceORM(ReceivableTimestampMixin, Base):
    __tablename__ = "outgoing_invoices"
    __table_args__ = (
        UniqueConstraint("invoice_number", name="uq_outgoing_invoice_number"),
        CheckConstraint("length(trim(invoice_number)) > 0", name="ck_outgoing_invoice_number"),
        CheckConstraint("length(trim(customer_name)) > 0", name="ck_outgoing_customer"),
        CheckConstraint("length(currency) = 3 AND currency NOT GLOB '*[^A-Z]*'", name="ck_outgoing_currency"),
        CheckConstraint(_money_check("gross_amount"), name="ck_outgoing_gross"),
        CheckConstraint(_money_check("net_amount", positive=False), name="ck_outgoing_net"),
        CheckConstraint(_money_check("vat_amount", positive=False), name="ck_outgoing_vat"),
        CheckConstraint(_money_check("amount_original"), name="ck_outgoing_original"),
        CheckConstraint(_money_check("amount_common", positive=False), name="ck_outgoing_common"),
        CheckConstraint("length(currency_original) = 3 AND currency_original NOT GLOB '*[^A-Z]*'", name="ck_outgoing_original_currency"),
        CheckConstraint("length(currency_common) = 3 AND currency_common NOT GLOB '*[^A-Z]*'", name="ck_outgoing_common_currency"),
    )
    invoice_number: Mapped[str] = mapped_column(String(255), nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_reference: Mapped[str | None] = mapped_column(String(255))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    net_amount: Mapped[str | None] = mapped_column(String(64))
    vat_amount: Mapped[str | None] = mapped_column(String(64))
    gross_amount: Mapped[str] = mapped_column(String(64), nullable=False)
    # Legacy currency/gross_amount remain synchronized original-value aliases.
    amount_original: Mapped[str] = mapped_column(String(64), nullable=False)
    amount_common: Mapped[str | None] = mapped_column(String(64))
    currency_original: Mapped[str] = mapped_column(String(3), nullable=False)
    currency_common: Mapped[str] = mapped_column(String(3), nullable=False)
    pdf_filename: Mapped[str | None] = mapped_column(String(255))
    pdf_sha256: Mapped[str | None] = mapped_column(String(64))
    remarks: Mapped[str | None] = mapped_column(Text)


class IncomingPaymentORM(ReceivableTimestampMixin, Base):
    __tablename__ = "incoming_payments"
    __table_args__ = (
        CheckConstraint(_money_check("amount"), name="ck_incoming_amount"),
        CheckConstraint("length(currency) = 3 AND currency NOT GLOB '*[^A-Z]*'", name="ck_incoming_currency"),
    )
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    payer_name: Mapped[str | None] = mapped_column(String(255))
    bank_reference: Mapped[str | None] = mapped_column(String(255))
    payment_method: Mapped[str | None] = mapped_column(String(64))
    remarks: Mapped[str | None] = mapped_column(Text)


class InvoicePaymentAllocationORM(ReceivableIdentityMixin, Base):
    __tablename__ = "invoice_payment_allocations"
    __table_args__ = (
        CheckConstraint(_money_check("amount_allocated"), name="ck_allocation_amount"),
    )
    invoice_id: Mapped[str] = mapped_column(ForeignKey("outgoing_invoices.id", ondelete="RESTRICT"), nullable=False, index=True)
    payment_id: Mapped[str] = mapped_column(ForeignKey("incoming_payments.id", ondelete="RESTRICT"), nullable=False, index=True)
    amount_allocated: Mapped[str] = mapped_column(String(64), nullable=False)
