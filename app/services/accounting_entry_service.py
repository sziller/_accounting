# app/services/accounting_entry_service.py

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.db.models import AccountingEntryORM
from app.domain.invoice_number_policy import (
    canonicalize_invoice_number,
    is_populated_invoice_number,
)
from app.engine.accounting_entry_processor import AccountingEntryProcessor, ProcessedAccountingEntry
from app.schemas.accounting_entry_schema import (AccountingEntryCreateSchema,
                                                 AccountingEntryReadSchema,
                                                 AccountingEntryUpdateSchema)
from app.services.conversion_service import ConversionService


def decimal_to_db(value: Decimal | None) -> str | None:
    """=== service function ====
    Convert a Decimal value into a database-safe string.
    === by Sziller & ChatGPT ==="""
    if value is None:
        return None

    return str(value)


def decimal_from_db(value: str | None) -> Decimal | None:
    """=== service function ====
    Convert a database string into Decimal, preserving missing values as None.
    === by Sziller & ChatGPT ==="""
    if value is None:
        return None

    return Decimal(value)


def tags_to_db(tags: list[str]) -> str:
    """=== service function ====
    Convert a list of tag strings into JSON text for database storage.
    === by Sziller & ChatGPT ==="""
    return json.dumps(tags, ensure_ascii=False)


def tags_from_db(tags_json: str | None) -> list[str]:
    """=== service function ====
    Convert database JSON text back into a list of tag strings.
    === by Sziller & ChatGPT ==="""
    if not tags_json:
        return []

    loaded = json.loads(tags_json)

    if not isinstance(loaded, list):
        return []

    return [str(item) for item in loaded]


class AccountingEntryService:
    """=== service class ====
    Coordinate accounting-entry use cases between API schemas, engine logic, and database rows.
    === by Sziller & ChatGPT ==="""

    def __init__(self, db: Session) -> None:
        """=== service function ====
        Store the active SQLAlchemy session and initialize the accounting processor.
        === by Sziller & ChatGPT ==="""
        self.db = db
        self.processor = AccountingEntryProcessor()

    def create_entry(
            self,
            payload: AccountingEntryCreateSchema,
    ) -> AccountingEntryReadSchema:
        """=== service function ====
        Process, persist, and return one accounting entry.
        === by Sziller & ChatGPT ==="""
        normalized_invoice_number = self._normalize_invoice_number(payload.invoice_number)

        if is_populated_invoice_number(normalized_invoice_number) and self._invoice_number_exists(normalized_invoice_number):
            raise ValueError(f"Duplicate invoice_number: {normalized_invoice_number}")

        processed = self.processor.process(payload)
        row = self._build_row(processed)

        self.db.add(row)

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ValueError(
                f"Duplicate or invalid accounting entry: {normalized_invoice_number}"
            ) from exc

        self.db.refresh(row)

        return self._to_read_schema(row)

    def create_entries_batch(
            self,
            payloads: list[AccountingEntryCreateSchema],
    ) -> list[AccountingEntryReadSchema]:
        """=== service function ====
        Process, persist, and return multiple accounting entries in one transaction, skipping duplicate invoice numbers.
        === by Sziller & ChatGPT ==="""
        rows: list[AccountingEntryORM] = []
        seen_invoice_numbers: set[str] = set()

        for payload in payloads:
            normalized_invoice_number = self._normalize_invoice_number(payload.invoice_number)

            if is_populated_invoice_number(normalized_invoice_number):
                if normalized_invoice_number in seen_invoice_numbers:
                    continue

                if self._invoice_number_exists(normalized_invoice_number):
                    continue

                seen_invoice_numbers.add(normalized_invoice_number)

            processed = self.processor.process(payload)
            row = self._build_row(processed)

            self.db.add(row)
            rows.append(row)

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ValueError("Batch insert failed because of a database uniqueness conflict.") from exc

        for row in rows:
            self.db.refresh(row)

        return [self._to_read_schema(row) for row in rows]

    def update_entry(
            self,
            entry_id: str,
            payload: AccountingEntryUpdateSchema,
    ) -> AccountingEntryReadSchema | None:
        """=== service function ====
        Update one accounting entry by replacing editable raw fields and recalculating derived fields.
        === by Sziller & ChatGPT ==="""
        row = self.db.get(AccountingEntryORM, entry_id)

        if row is None:
            return None

        normalized_invoice_number = self._normalize_invoice_number(payload.invoice_number)

        if is_populated_invoice_number(normalized_invoice_number):
            stmt = (
                select(AccountingEntryORM.id)
                .filter(AccountingEntryORM.invoice_number == normalized_invoice_number)
                .filter(AccountingEntryORM.id != entry_id)
                .limit(1)
            )

            duplicate_id = self.db.execute(stmt).scalar_one_or_none()

            if duplicate_id is not None:
                raise ValueError(f"Duplicate invoice_number: {normalized_invoice_number}")

        processed = self.processor.process(payload)

        row.entry_type = processed.entry_type
        row.category_code = processed.category_code
        row.tax_scope = processed.tax_scope
        row.counterparty_name = processed.counterparty_name
        row.payment_method = processed.payment_method
        row.payment_date = processed.payment_date
        row.booking_year = processed.booking_year

        row.has_invoice = processed.has_invoice
        row.invoice_number = self._normalize_invoice_number(processed.invoice_number)
        row.invoice_date = processed.invoice_date

        row.amount_original = decimal_to_db(processed.amount_original)
        row.currency_original = processed.currency_original
        row.amount_common = decimal_to_db(processed.amount_common)
        row.currency_common = processed.currency_common

        row.exchange_rate = decimal_to_db(processed.exchange_rate)
        row.exchange_rate_date = processed.exchange_rate_date

        row.vat_rate_percent = decimal_to_db(processed.vat_rate_percent)
        row.vat_amount = decimal_to_db(processed.vat_amount)

        row.deductible_percent = decimal_to_db(processed.deductible_percent)
        row.deductible_amount = decimal_to_db(processed.deductible_amount)
        row.deductible_vat_amount = decimal_to_db(processed.deductible_vat_amount)
        row.writeoff_method = processed.writeoff_method

        row.remarks = processed.remarks
        row.tags_json = tags_to_db(processed.tags)

        row.source_filename = processed.source_filename

        row.conversion_status = processed.conversion_status
        row.conversion_note = processed.conversion_note

        self.db.commit()
        self.db.refresh(row)

        if row.conversion_status == "pending":
            conversion_service = ConversionService(db=self.db)
            conversion_service.reprocess_entry(entry_id=entry_id)
            self.db.refresh(row)

        return self._to_read_schema(row)
    
    def list_entries(self) -> list[AccountingEntryReadSchema]:
        """=== service function ====
        Return all accounting entries ordered by payment date and creation date.
        === by Sziller & ChatGPT ==="""
        stmt = select(AccountingEntryORM).order_by(
            AccountingEntryORM.payment_date.desc(),
            AccountingEntryORM.created_at.desc(),
        )

        rows = self.db.execute(stmt).scalars().all()

        return [self._to_read_schema(row) for row in rows]

    def get_entry(self, entry_id: str) -> AccountingEntryReadSchema | None:
        """=== service function ====
        Return one accounting entry by id, or None if it does not exist.
        === by Sziller & ChatGPT ==="""
        row = self.db.get(AccountingEntryORM, entry_id)

        if row is None:
            return None

        return self._to_read_schema(row)

    def delete_entry(self, entry_id: str) -> bool:
        """=== service function ====
        Delete one accounting entry by id and report whether deletion happened.
        === by Sziller & ChatGPT ==="""
        row = self.db.get(AccountingEntryORM, entry_id)

        if row is None:
            return False

        self.db.delete(row)
        self.db.commit()

        return True

    @staticmethod
    def _normalize_invoice_number(value: str | None) -> str | None:
        """Canonicalize invoice numbers through the single domain policy.

        This defensive service boundary ensures create, update, batch duplicate
        checks, and persistence use the same canonical DB string even if a
        caller reaches the service without ordinary API schema construction.
        Missing ``None`` and ``""`` values remain non-populated and therefore
        do not participate in duplicate checks.
        """
        return canonicalize_invoice_number(value)

    def _invoice_number_exists(self, invoice_number: str | None) -> bool:
        """=== service function ====
        Check whether a non-empty invoice number already exists in the database.
        === by Sziller & ChatGPT ==="""
        normalized = self._normalize_invoice_number(invoice_number)

        if not is_populated_invoice_number(normalized):
            return False

        stmt = (
            select(AccountingEntryORM.id)
            .filter(AccountingEntryORM.invoice_number == normalized)
            .limit(1)
        )

        return self.db.execute(stmt).scalar_one_or_none() is not None

    @staticmethod
    def _build_row(processed: ProcessedAccountingEntry) -> AccountingEntryORM:
        """=== service function ====
        Convert processed accounting-entry data into an ORM row.
        === by Sziller & ChatGPT ==="""
        return AccountingEntryORM(
            entry_type=processed.entry_type,
            category_code=processed.category_code,
            tax_scope=processed.tax_scope,
            counterparty_name=processed.counterparty_name,
            payment_method=processed.payment_method,
            payment_date=processed.payment_date,
            booking_year=processed.booking_year,
            has_invoice=processed.has_invoice,
            invoice_number=AccountingEntryService._normalize_invoice_number(processed.invoice_number),
            invoice_date=processed.invoice_date,
            amount_original=decimal_to_db(processed.amount_original),
            currency_original=processed.currency_original,
            amount_common=decimal_to_db(processed.amount_common),
            currency_common=processed.currency_common,
            exchange_rate=decimal_to_db(processed.exchange_rate),
            exchange_rate_date=processed.exchange_rate_date,
            vat_rate_percent=decimal_to_db(processed.vat_rate_percent),
            vat_amount=decimal_to_db(processed.vat_amount),
            deductible_percent=decimal_to_db(processed.deductible_percent),
            deductible_amount=decimal_to_db(processed.deductible_amount),
            deductible_vat_amount=decimal_to_db(processed.deductible_vat_amount),
            writeoff_method=processed.writeoff_method,
            remarks=processed.remarks,
            tags_json=tags_to_db(processed.tags),
            source_filename=processed.source_filename,
            conversion_status=processed.conversion_status,
            conversion_note=processed.conversion_note,
        )

    @staticmethod
    def _to_read_schema(row: AccountingEntryORM) -> AccountingEntryReadSchema:
        """=== service function ====
        Convert an AccountingEntryORM row into an API read schema.
        === by Sziller & ChatGPT ==="""
        data: dict[str, Any] = {
            "id": row.id,
            "entry_type": row.entry_type,
            "category_code": row.category_code,
            "tax_scope": row.tax_scope,
            "counterparty_name": row.counterparty_name,
            "payment_method": row.payment_method,
            "payment_date": row.payment_date,
            "booking_year": row.booking_year,
            "has_invoice": row.has_invoice,
            "invoice_number": row.invoice_number,
            "invoice_date": row.invoice_date,
            "amount_original": Decimal(row.amount_original),
            "currency_original": row.currency_original,
            "amount_common": decimal_from_db(row.amount_common),
            "currency_common": row.currency_common,
            "exchange_rate": decimal_from_db(row.exchange_rate),
            "exchange_rate_date": row.exchange_rate_date,
            "vat_rate_percent": Decimal(row.vat_rate_percent),
            "vat_amount": decimal_from_db(row.vat_amount),
            "deductible_percent": Decimal(row.deductible_percent),
            "deductible_amount": decimal_from_db(row.deductible_amount),
            "deductible_vat_amount": decimal_from_db(row.deductible_vat_amount),
            "writeoff_method": row.writeoff_method,
            "remarks": row.remarks,
            "tags": tags_from_db(row.tags_json),
            "source_filename": row.source_filename,
            "conversion_status": row.conversion_status,
            "conversion_note": row.conversion_note,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

        return AccountingEntryReadSchema.model_validate(data)
