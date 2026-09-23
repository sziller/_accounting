from __future__ import annotations

import unittest
import uuid
from datetime import date
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import AccountingEntryORM, Base
from app.domain.invoice_number_policy import (
    INVOICE_NUMBER_MAX_LENGTH,
    INVOICE_NUMBER_PATTERN,
    canonicalize_invoice_number,
    get_invoice_number_policy_metadata,
)
from app.engine.accounting_entry_processor import AccountingEntryProcessor
from app.routers.router_accounting_entries import AccountingEntriesRouter
from app.schemas.accounting_entry_schema import (
    AccountingEntryBatchCreateSchema,
    AccountingEntryCreateSchema,
    AccountingEntryUpdateSchema,
)
from app.services.accounting_entry_service import AccountingEntryService


def entry_payload(invoice_number: str | None, *, suffix: str = "1", has_invoice: bool = True) -> dict:
    return {
        "entry_type": "expense",
        "category_code": "buro",
        "tax_scope": "domestic",
        "counterparty_name": f"Supplier {suffix}",
        "payment_method": "bank_transfer",
        "payment_date": "2026-08-24",
        "has_invoice": has_invoice,
        "invoice_number": invoice_number,
        "invoice_date": "2026-08-24" if has_invoice else None,
        "amount_original": "10.00",
        "currency_original": "EUR",
        "remarks": None,
        "tags": [],
        "source_filename": None,
    }


def raw_row(invoice_number: str | None) -> AccountingEntryORM:
    """Build an ORM row for direct constraint tests, bypassing Pydantic/service."""
    return AccountingEntryORM(
        id=str(uuid.uuid4()),
        entry_type="expense",
        category_code="buro",
        tax_scope="domestic",
        counterparty_name="Direct DB Supplier",
        payment_method="bank_transfer",
        payment_date=date(2026, 8, 24),
        booking_year=2026,
        has_invoice=True,
        invoice_number=invoice_number,
        invoice_date=date(2026, 8, 24),
        amount_original="10.00",
        currency_original="EUR",
        amount_common="10.00",
        currency_common="EUR",
        vat_rate_percent="19.00",
        vat_amount="1.60",
        deductible_percent="100.00",
        deductible_amount="8.40",
        deductible_vat_amount="1.60",
        writeoff_method="immediate",
        tags_json="[]",
        conversion_status="not_required",
    )


class InvoiceNumberPolicyTests(unittest.TestCase):
    def test_missing_and_canonical_examples(self) -> None:
        cases = {
            None: None,
            "": "",
            "   \t\n": "",
            " ab 12 / 2026 ": "AB12/2026",
            "re-001": "RE-001",
            "INV_500.23": "INV_500.23",
        }
        for supplied, expected in cases.items():
            with self.subTest(supplied=supplied):
                self.assertEqual(canonicalize_invoice_number(supplied), expected)

    def test_every_allowed_punctuation_is_preserved(self) -> None:
        self.assertEqual(canonicalize_invoice_number("a/1-2.3_4"), "A/1-2.3_4")

    def test_forbidden_characters_fail_including_dedicated_comma_cases(self) -> None:
        forbidden = [
            "AB,123", "2026,001", "AB:12", "AB;12", "AB\\12",
            "AB#12", "AB@12", "AB?12", "ÁB12", "straße1", "AB!12",
        ]
        for supplied in forbidden:
            with self.subTest(supplied=supplied):
                with self.assertRaises(ValueError):
                    canonicalize_invoice_number(supplied)

    def test_length_is_measured_after_canonicalization(self) -> None:
        self.assertEqual(
            canonicalize_invoice_number("A " * INVOICE_NUMBER_MAX_LENGTH),
            "A" * INVOICE_NUMBER_MAX_LENGTH,
        )
        with self.assertRaises(ValueError):
            canonicalize_invoice_number("A " * (INVOICE_NUMBER_MAX_LENGTH + 1))


class InvoiceNumberSchemaAndProcessorTests(unittest.TestCase):
    def test_schema_accepts_missing_and_canonicalizes_populated_values(self) -> None:
        for supplied, expected in [(None, None), ("", ""), ("   ", "")]:
            with self.subTest(supplied=supplied):
                self.assertEqual(
                    AccountingEntryCreateSchema.model_validate(entry_payload(supplied)).invoice_number,
                    expected,
                )
        schema = AccountingEntryCreateSchema.model_validate(
            entry_payload(" ab 12 / 2026 ")
        )
        self.assertEqual(schema.invoice_number, "AB12/2026")

    def test_create_and_update_schema_reject_forbidden_characters(self) -> None:
        for schema_type in (AccountingEntryCreateSchema, AccountingEntryUpdateSchema):
            for supplied in ("AB,12", "AB#12"):
                with self.subTest(schema=schema_type.__name__, supplied=supplied):
                    with self.assertRaises(ValidationError):
                        schema_type.model_validate(entry_payload(supplied))

    def test_processor_accepts_missing_number_but_preserves_other_invoice_rules(self) -> None:
        processor = AccountingEntryProcessor()
        processor.process(AccountingEntryCreateSchema.model_validate(entry_payload(None)))
        processor.process(AccountingEntryCreateSchema.model_validate(entry_payload("")))
        with self.assertRaisesRegex(ValueError, "invoice_number must be empty"):
            processor.process(
                AccountingEntryCreateSchema.model_validate(
                    entry_payload("AB-1", has_invoice=False)
                )
            )

    def test_generated_schema_exposes_nullable_pattern_length_and_description(self) -> None:
        field_schema = AccountingEntryCreateSchema.model_json_schema()["properties"]["invoice_number"]
        serialized = str(field_schema)
        string_schema = next(
            option for option in field_schema["anyOf"] if option.get("type") == "string"
        )
        self.assertIn("null", serialized)
        self.assertEqual(string_schema["pattern"], INVOICE_NUMBER_PATTERN)
        self.assertEqual(string_schema["maxLength"], INVOICE_NUMBER_MAX_LENGTH)
        self.assertIn("canonical", serialized.lower())
        self.assertNotIn(",", INVOICE_NUMBER_PATTERN)


class InvoiceNumberPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite+pysqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_service_uses_canonical_string_for_uniqueness(self) -> None:
        service = AccountingEntryService(self.db)
        first = service.create_entry(
            AccountingEntryCreateSchema.model_validate(entry_payload("ab 12 / 2026"))
        )
        self.assertEqual(first.invoice_number, "AB12/2026")
        with self.assertRaisesRegex(ValueError, "Duplicate invoice_number"):
            service.create_entry(
                AccountingEntryCreateSchema.model_validate(
                    entry_payload("AB12/2026", suffix="2")
                )
            )

    def test_batch_canonicalizes_before_duplicate_detection(self) -> None:
        service = AccountingEntryService(self.db)
        created = service.create_entries_batch(
            [
                AccountingEntryCreateSchema.model_validate(entry_payload("ab 12 / 2026")),
                AccountingEntryCreateSchema.model_validate(entry_payload("AB12/2026", suffix="2")),
            ]
        )
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].invoice_number, "AB12/2026")

    def test_multiple_missing_numbers_are_independently_persistable(self) -> None:
        service = AccountingEntryService(self.db)
        created = service.create_entries_batch(
            [
                AccountingEntryCreateSchema.model_validate(entry_payload(None, suffix="1")),
                AccountingEntryCreateSchema.model_validate(entry_payload(None, suffix="2")),
                AccountingEntryCreateSchema.model_validate(entry_payload("", suffix="3")),
                AccountingEntryCreateSchema.model_validate(entry_payload("   ", suffix="4")),
            ]
        )
        self.assertEqual(len(created), 4)
        self.assertEqual([item.invoice_number for item in created], [None, None, "", ""])

    def test_update_persists_canonical_value(self) -> None:
        service = AccountingEntryService(self.db)
        created = service.create_entry(
            AccountingEntryCreateSchema.model_validate(entry_payload(None))
        )
        updated = service.update_entry(
            created.id,
            AccountingEntryUpdateSchema.model_validate(entry_payload("inv_500.23")),
        )
        self.assertIsNotNone(updated)
        self.assertEqual(updated.invoice_number, "INV_500.23")

    def test_single_batch_and_update_endpoint_handlers_share_policy(self) -> None:
        router = AccountingEntriesRouter()
        created = router.create_entry(
            AccountingEntryCreateSchema.model_validate(
                entry_payload("endpoint 1 / 2026")
            ),
            db=self.db,
        )
        self.assertEqual(created.invoice_number, "ENDPOINT1/2026")

        batch = router.create_entries_batch(
            AccountingEntryBatchCreateSchema.model_validate(
                {
                    "entries": [
                        entry_payload(None, suffix="endpoint-b1"),
                        entry_payload("", suffix="endpoint-b2"),
                    ]
                }
            ),
            db=self.db,
        )
        self.assertEqual([item.invoice_number for item in batch], [None, ""])

        updated = router.update_entry(
            entry_id=created.id,
            payload=AccountingEntryUpdateSchema.model_validate(
                entry_payload("endpoint_2.2026", suffix="endpoint-put")
            ),
            db=self.db,
        )
        self.assertEqual(updated.invoice_number, "ENDPOINT_2.2026")

    def test_database_check_accepts_only_canonical_or_missing_values(self) -> None:
        accepted = [None, "", "AB12/2026", "RE-2026-001", "INV_500.23"]
        for value in accepted:
            with self.subTest(accepted=value):
                self.db.add(raw_row(value))
                self.db.commit()

        rejected = ["ab12/2026", "AB 12/2026", "AB,12", "AB#12"]
        for value in rejected:
            with self.subTest(rejected=value):
                self.db.add(raw_row(value))
                with self.assertRaises(IntegrityError):
                    self.db.commit()
                self.db.rollback()

    def test_database_unique_index_exempts_missing_but_rejects_populated_duplicate(self) -> None:
        for value in (None, None, "", ""):
            self.db.add(raw_row(value))
        self.db.commit()
        self.db.add(raw_row("AB12/2026"))
        self.db.commit()
        self.db.add(raw_row("AB12/2026"))
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

class InvoiceNumberRecognitionContractTests(unittest.TestCase):
    def test_contract_uses_authoritative_policy_and_guides_missing_uncertain_values(self) -> None:
        contract = AccountingEntriesRouter().get_entry_create_contract()
        policy = contract["invoice_number_policy"]
        self.assertEqual(policy, get_invoice_number_policy_metadata())
        self.assertTrue(policy["missing_allowed"])
        self.assertEqual(policy["allowed_punctuation"], ["/", "-", ".", "_"])
        self.assertEqual(policy["forbidden_punctuation"], [","])
        self.assertEqual(policy["examples"]["canonical"], "AB12/2026")
        invoice_schema = contract["entry_item_schema"]["properties"]["invoice_number"]
        string_schema = next(
            option for option in invoice_schema["anyOf"] if option.get("type") == "string"
        )
        self.assertEqual(string_schema["pattern"], INVOICE_NUMBER_PATTERN)
        guidance = " ".join(contract["recognizer_rules"]).lower()
        self.assertIn("never invent", guidance)
        self.assertIn("must never cause the accounting entry to be omitted", guidance)
        self.assertIn("uncertain comma/dot", guidance)
        self.assertIn("remarks", guidance)


if __name__ == "__main__":
    unittest.main()
