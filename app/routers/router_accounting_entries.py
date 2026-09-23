from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core import config

from app.db.database import get_db_session
from app.schemas.accounting_entry_schema import (AccountingEntryCreateSchema,
                                                 AccountingEntryReadSchema,
                                                 AccountingEntryBatchCreateSchema,
                                                 AccountingEntryUpdateSchema)
from app.services.accounting_entry_service import AccountingEntryService
from app.services.conversion_service import ConversionService
from app.services.entry_processing_service import EntryProcessingService
from app.domain.accounting_rules import (CATEGORY_LABELS,
                                         CURRENCIES,
                                         ENTRY_TYPES,
                                         PAYMENT_METHODS,
                                         TAX_SCOPES)
from app.domain.invoice_number_policy import (
    get_invoice_number_policy_metadata,
    get_invoice_number_recognizer_rules,
)

lg = logging.getLogger(__name__)


class AccountingEntriesRouter(APIRouter):
    """
    Modular accounting-entry router compatible with the custom topology/factory
    system using module + class_name + init + args/attrs.
    """

    def __init__(
        self,
        *,
        prefix: str = "/acct",
        env_ns: str = "ACCT",
        db_roles: list[str] | None = None,
        lng: str = "en",
        err_msg: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            prefix=prefix,
            tags=tags or ["accounting_entries"],
            **kwargs,
        )

        self.env_ns = env_ns
        self.db_roles = db_roles or ["ACCT"]
        self.lng = lng
        self.err_msg = err_msg or {}

        # Attributes may be overwritten by factory after init via spec["args"]
        # or spec["attrs"].
        self.db_default_table_classname: str | None = None

        self._routes_registered = False

    def reinit(self) -> None:
        """
        Called by the custom router factory after construction and again after
        config attributes have been applied.

        Must be idempotent because the factory may call it more than once.
        """
        if self._routes_registered:
            return

        self._register_routes()
        self._routes_registered = True

    def _register_routes(self) -> None:
        self.add_api_route('/v0/entries/process', self.process_entries, methods=['POST'])
        self.add_api_route('/v0/entries/{entry_id}/process', self.process_entry, methods=['POST'])
        self.add_api_route(
            path="/v0/source-images/{filename}",
            endpoint=self.get_source_image,
            methods=["GET"],
            response_class=FileResponse,
            responses={200: {"content": {"image/jpeg": {}}}},
            summary="Get a JPEG source document by its exact filename",
        )

        self.add_api_route(
            path="/v0/entries",
            endpoint=self.create_entry,
            methods=["POST"],
            response_model=AccountingEntryReadSchema,
            status_code=status.HTTP_201_CREATED,
            summary="Create accounting entry",
        )

        self.add_api_route(
            path="/v0/entries",
            endpoint=self.list_entries,
            methods=["GET"],
            response_model=list[AccountingEntryReadSchema],
            summary="List accounting entries",
        )

        self.add_api_route(
            path="/v0/entries/{entry_id}",
            endpoint=self.get_entry,  # docstring creeated
            methods=["GET"],
            response_model=AccountingEntryReadSchema,
            summary="Get accounting entry by id",
        )

        self.add_api_route(
            path="/v0/entries/{entry_id}",
            endpoint=self.delete_entry,  # docstring creeated
            methods=["DELETE"],
            status_code=status.HTTP_204_NO_CONTENT,
            summary="Delete accounting entry",
        )

        self.add_api_route(
            path="/v0/entry-create-contract",
            endpoint=self.get_entry_create_contract,
            methods=["GET"],
            summary="Get create-entry JSON contract",
        )
        
        self.add_api_route(
            path="/v0/metadata",
            endpoint=self.get_metadata,
            methods=["GET"],
            summary="Get accounting-entry metadata",
        )

        self.add_api_route(
            path="/v0/entries/batch",
            endpoint=self.create_entries_batch,
            methods=["POST"],
            response_model=list[AccountingEntryReadSchema],
            status_code=status.HTTP_201_CREATED,
            summary="Create multiple accounting entries",
        )

        self.add_api_route(
            path="/v0/conversions/reprocess-pending",
            endpoint=self.reprocess_pending_conversions,
            methods=["POST"],
            summary="Reprocess pending currency conversions",
        )

        self.add_api_route(
            path="/v0/entries/{entry_id}",
            endpoint=self.update_entry,
            methods=["PUT"],
            response_model=AccountingEntryReadSchema,
            summary="Update one accounting entry",
        )
        

    @staticmethod
    def _service(db: Session) -> AccountingEntryService:
        return AccountingEntryService(db=db)

    def get_source_image(self, filename: str) -> FileResponse:
        """Serve an exact basename from the configured source directory, without DB access."""
        if not filename or filename in {".", ".."} or any(
            character in filename for character in ("/", "\\", "\x00")
        ):
            raise HTTPException(status_code=400, detail="Invalid source image filename")
        if Path(filename).suffix.lower() not in {".jpg", ".jpeg"}:
            raise HTTPException(status_code=415, detail="Only .jpg and .jpeg source images are supported")

        directory = config.AP_SOURCE_IMAGE_DIRECTORY.resolve()
        try:
            image_path = (directory / filename).resolve()
        except (OSError, RuntimeError):
            raise HTTPException(status_code=404, detail="Source image not found") from None
        if not image_path.is_relative_to(directory):
            raise HTTPException(status_code=400, detail="Invalid source image filename")
        if not image_path.is_file():
            raise HTTPException(status_code=404, detail="Source image not found")

        return FileResponse(image_path, media_type="image/jpeg")

    def create_entry(
            self,
            payload: AccountingEntryCreateSchema,
            db: Session = Depends(get_db_session),
    ) -> AccountingEntryReadSchema:
        """=== Method name: create_entry ===
        Create and persist one accounting entry from raw user- or recognizer-supplied data.

        HTTP endpoint:
        POST /acct/v0/entries

        The endpoint accepts one `AccountingEntryCreateSchema`, delegates accounting
        validation/calculation and persistence to `AccountingEntryService`, and returns
        the complete processed database-backed entry as `AccountingEntryReadSchema`.

        === Authorization ===
        - No authentication or authorization is currently required.
        - The application is intended for local use on `127.0.0.1`.

        === Parameters ===
        - `payload: AccountingEntryCreateSchema`
          Raw accounting-entry data supplied in the request body.
          Includes user/source-controlled fields such as:
          - entry type
          - category code
          - tax scope
          - counterparty name
          - payment method and payment date
          - invoice flag, invoice number, and invoice date
          - original amount and currency
          - remarks and tags
          - optional `source_filename`

          Backend-derived fields such as database ID, booking year, common-currency
          amount, exchange rate, VAT amounts, deductible amounts, write-off method,
          conversion status, and timestamps are not valid input fields.

        - `db: Session`
          SQLAlchemy session supplied automatically by FastAPI through
          `Depends(get_db_session)`. It is not supplied by the API caller.

        === Functionality ===
        1. FastAPI/Pydantic validates the incoming JSON against
           `AccountingEntryCreateSchema`.
        2. Unknown input fields are rejected by the schema.
        3. Creates an `AccountingEntryService` using the injected database session.
        4. The service:
           - normalizes the invoice number;
           - rejects an already existing non-empty invoice number;
           - passes the entry to `AccountingEntryProcessor`;
           - validates invoice-field consistency;
           - calculates derived accounting values;
           - determines the initial currency-conversion state;
           - creates an `AccountingEntryORM` row;
           - commits it to the database;
           - converts the persisted row into `AccountingEntryReadSchema`.
        5. Returns the fully processed entry.

        === Processing Rules ===
        - If `has_invoice` is true:
          - `invoice_number` may be missing when it was not recognized.
          - `invoice_date` is required.
        - If `has_invoice` is false:
          - `invoice_number` must be empty.
          - `invoice_date` must be null.
        - `booking_year` is derived from `payment_date`.
        - EUR entries receive their common-currency amount immediately.
        - Non-EUR entries are initially stored with pending conversion state.
        - VAT, deductible values, and write-off information are calculated by the
          backend and are not supplied by the caller.
        - `source_filename` is optional for this single-entry endpoint and is stored
          as source-association metadata when supplied.

        === Response Format ===
        Returns `AccountingEntryReadSchema`.

        The response contains:
        - database-generated identity and timestamps;
        - all accepted raw accounting fields;
        - normalized invoice/source metadata;
        - derived booking information;
        - original and common-currency amounts;
        - exchange-rate state;
        - VAT values;
        - deductible/write-off values;
        - conversion status and explanatory note.

        Successful creation is exposed by the route as:

        - **201 Created**

        === Errors ===
        - **422 Unprocessable Entity**
          - Request JSON does not conform to `AccountingEntryCreateSchema`.
          - Required fields are missing.
          - Field types or allowed values are invalid.
          - An unknown, obsolete, misspelled, or backend-derived field is supplied.

        - **400 Bad Request**
          - Accounting/business validation fails after schema validation.
          - Examples:
            - duplicate non-empty `invoice_number`;
            - inconsistent invoice fields;
            - other `ValueError` conditions raised by the service or processor.
          - Database uniqueness conflicts caught by the service are also translated
            into a `ValueError` and therefore returned here as HTTP 400.

        - **500 Internal Server Error**
          - May occur for unexpected exceptions not handled by the router/service.

        === Notes ===
        - This endpoint creates exactly one accounting entry.
        - AI invoice-recognition batches should normally use
          `POST /acct/v0/entries/batch` instead.
        - The canonical ChatGPT recognition format is exposed separately through
          `GET /acct/v0/entry-create-contract`.
        - Duplicate protection currently treats a normalized non-empty invoice number
          as globally unique.
        - Entries without an invoice number may be created repeatedly.
        - Unlike the update workflow, creation currently does not automatically invoke
          `ConversionService` after storing a pending non-EUR entry. Pending conversions
          can be resolved later through the conversion-reprocessing workflow.

        === by Sziller & ChatGPT ==="""
        try:
            service = self._service(db)
            return service.create_entry(payload)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    def list_entries(self, db: Session = Depends(get_db_session)) -> list[AccountingEntryReadSchema]:
        """=== Method name: list_entries ===
        Retrieve all persisted accounting entries from the accounting database.
        HTTP endpoint:
        GET /acct/v0/entries

        The endpoint delegates retrieval to `AccountingEntryService` and returns the
        currently stored accounting entries as a list of `AccountingEntryReadSchema`
        objects.

=== Authorization ===
- No authentication or authorization is currently required.
- The application is intended for local use on `127.0.0.1`.

=== Parameters ===
- No caller-supplied query or path parameters are currently supported.

- `db: Session`
  SQLAlchemy session supplied automatically by FastAPI through
  `Depends(get_db_session)`. It is not supplied by the API caller.

=== Functionality ===
1. A request-scoped SQLAlchemy session is supplied by `get_db_session`.
2. Creates an `AccountingEntryService` using that session.
3. Calls `service.list_entries()`.
4. The service queries all `AccountingEntryORM` rows.
5. Rows are ordered by:
   - `payment_date` descending;
   - then `created_at` descending.
6. Each ORM row is converted into an `AccountingEntryReadSchema`.
7. Returns the resulting list.

=== Response Format ===
Successful retrieval returns:

- **200 OK**
- A JSON array of `AccountingEntryReadSchema` objects.

Each entry contains the complete persisted accounting-entry state, including:

- database ID;
- entry type, category, and tax scope;
- counterparty information;
- payment data;
- invoice metadata;
- original amount and currency;
- common/reporting currency values;
- exchange-rate information;
- VAT values;
- deductible and write-off values;
- remarks and tags;
- optional `source_filename`;
- conversion status and note;
- creation and update timestamps.

If no accounting entries exist, the endpoint returns an empty list:

`[]`

=== Errors ===
- **500 Internal Server Error**
  - May occur for unexpected database-query, deserialization, or
    response-conversion failures.
  - No custom exception handling is implemented in this endpoint for
    unexpected SQLAlchemy errors.

=== Persistence Behavior ===
- This is a read-only endpoint.
- It does not modify or delete accounting entries.
- It does not commit database changes.
- It does not recalculate derived accounting values.
- It does not trigger pending currency conversions.
- It returns the values currently persisted in the database.

=== Ordering ===
Entries are returned in:

1. newest `payment_date` first;
2. for entries with the same payment date, newest `created_at` first.

This ordering is implemented by `AccountingEntryService.list_entries()`.

=== Notes ===
- The endpoint currently returns all accounting entries without pagination.
- No filtering, search, sorting parameters, date-range selection, or result
  limit are currently exposed.
- The endpoint does not distinguish between invoice-backed and non-invoice
  entries unless the caller inspects each entry's `has_invoice` value.
- `source_filename`, when present, is returned as persisted metadata only;
  this endpoint does not locate or open the corresponding physical source file.
- The browser frontend uses this endpoint to populate the main accounting-entry
  table.
- Because the ORM query selects the complete accounting-entry model, a mismatch
  between the current ORM and an older physical SQLite schema can cause this
  endpoint to fail until the development database is recreated or migrated.

=== by Sziller & ChatGPT ==="""
        service = self._service(db)
        return service.list_entries()

    def get_entry(
        self,
        entry_id: str,
        db: Session = Depends(get_db_session),
    ) -> AccountingEntryReadSchema:
        """=== Method name: get_entry ===
        Retrieve one accounting entry identified by its database entry ID.

        HTTP endpoint:
        GET /acct/v0/entries/{entry_id}

        The endpoint looks up one persisted accounting entry through
        `AccountingEntryService` and returns the complete processed entry as an
        `AccountingEntryReadSchema`.

        === Authorization ===
        - No authentication or authorization is currently required.
        - The application is intended for local use on `127.0.0.1`.

        === Parameters ===
        - `entry_id: str`
          Database-generated accounting-entry identifier supplied as a URL path
          parameter.

          Example:

          `GET /acct/v0/entries/3f78b26d-1e43-4f68-9f6d-...`

          The current API accepts the identifier as a plain string. UUID-format
          validation is not performed at the router boundary.

        - `db: Session`
          SQLAlchemy session supplied automatically by FastAPI through
          `Depends(get_db_session)`. It is not supplied by the API caller.

        === Functionality ===
        1. FastAPI extracts `entry_id` from the request URL.
        2. A request-scoped SQLAlchemy session is supplied by `get_db_session`.
        3. Creates an `AccountingEntryService` using that session.
        4. Calls `service.get_entry(entry_id)`.
        5. The service:
           - performs a primary-key lookup against `AccountingEntryORM`;
           - returns `None` if the row does not exist;
           - otherwise converts the ORM row into `AccountingEntryReadSchema`.
        6. If no matching entry exists, the router raises HTTP 404.
        7. Otherwise the complete accounting entry is returned.

        === Response Format ===
        Successful lookup returns:

        - **200 OK**
        - One `AccountingEntryReadSchema` object.

        The response contains the persisted accounting-entry state, including:

        - database ID;
        - entry classification;
        - category and tax scope;
        - counterparty;
        - payment information;
        - invoice metadata;
        - original amount and currency;
        - common/reporting currency values;
        - exchange-rate information;
        - VAT values;
        - deductible and write-off values;
        - remarks and tags;
        - optional `source_filename`;
        - conversion status and note;
        - creation and update timestamps.

        The endpoint returns both raw/source-controlled fields and backend-derived
        accounting fields.

        === Errors ===
        - **404 Not Found**
          - Raised when no accounting entry exists for the supplied `entry_id`.
          - Response detail:

            `Accounting entry not found: <entry_id>`

        - **500 Internal Server Error**
          - May occur for unexpected database, deserialization, or response-conversion
            failures.
          - No custom handling for unexpected SQLAlchemy exceptions is implemented
            in this endpoint.

        === Persistence Behavior ===
        - This is a read-only endpoint.
        - It does not modify the accounting entry.
        - It does not commit database changes.
        - It does not trigger currency conversion or recalculation.
        - It returns the values currently persisted in the database.

        === Notes ===
        - Lookup is performed by the accounting entry's database primary key.
        - The endpoint does not search by invoice number, counterparty, or
          `source_filename`.
        - `source_filename`, when present, identifies the source file associated with
          the accounting entry; this endpoint does not attempt to locate or open that
          physical file.
        - The browser frontend uses this endpoint when a user selects an entry and
          loads its detailed data for viewing or editing.
        - Any derived values returned here reflect the latest values currently stored
          on the accounting row; they are not recalculated by this GET request.

        === by Sziller & ChatGPT ==="""
        
        service = self._service(db)
        entry = service.get_entry(entry_id)

        if entry is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Accounting entry not found: {entry_id}",
            )

        return entry

    def delete_entry(
        self,
        entry_id: str,
        db: Session = Depends(get_db_session),
    ) -> None:
        """=== Method name: delete_entry ===
        Delete one accounting entry identified by its database entry ID.

        HTTP endpoint:
        DELETE /acct/v0/entries/{entry_id}

        The endpoint looks up the requested accounting entry through
        `AccountingEntryService` and permanently removes the corresponding
        `AccountingEntryORM` row from the accounting database.

        === Authorization ===
        - No authentication or authorization is currently required.
        - The application is intended for local use on `127.0.0.1`.

        === Parameters ===
        - `entry_id: str`
          Database-generated accounting-entry identifier supplied as a URL path
          parameter.

          Example:

          `DELETE /acct/v0/entries/3f78b26d-1e43-4f68-9f6d-...`

          The current router accepts the identifier as a plain string rather than
          performing UUID-format validation at the API boundary.

        - `db: Session`
          SQLAlchemy session supplied automatically by FastAPI through
          `Depends(get_db_session)`. It is not supplied by the API caller.

        === Functionality ===
        1. FastAPI extracts `entry_id` from the request URL.
        2. A request-scoped SQLAlchemy session is supplied by `get_db_session`.
        3. Creates an `AccountingEntryService` using that session.
        4. Calls `service.delete_entry(entry_id)`.
        5. The service:
           - looks up `AccountingEntryORM` by primary key;
           - returns `False` if no matching row exists;
           - otherwise marks the ORM row for deletion;
           - commits the transaction;
           - returns `True`.
        6. If the entry did not exist, the router raises HTTP 404.
        7. On successful deletion, the endpoint returns no response body.

        === Response Format ===
        Successful deletion returns:

        - **204 No Content**
        - No JSON payload or response body is returned.

        === Errors ===
        - **404 Not Found**
          - Raised when no accounting entry exists for the supplied `entry_id`.
          - Response detail:

            `Accounting entry not found: <entry_id>`

        - **500 Internal Server Error**
          - May occur for unexpected database or transaction failures.
          - The current endpoint does not add custom handling for unexpected
            SQLAlchemy exceptions.

        === Persistence Behavior ===
        - Deletion is immediate and physical.
        - The matching row is removed from the `accounting_entries` table when the
          service commits the transaction.
        - There is currently no:
          - soft-delete flag;
          - archive state;
          - reversal entry;
          - recycle bin;
          - deletion history;
          - audit record of the deleted values.

        === Notes ===
        - This endpoint deletes exactly one accounting entry.
        - Deletion is based solely on the database entry ID, not on invoice number,
          source filename, or other accounting fields.
        - If the supplied ID does not exist, no database change occurs.
        - `source_filename` is metadata stored on the accounting row only; deleting
          the entry does not currently perform any physical source-file operation.
        - Because deletion is destructive and no audit history currently exists,
          accidental deletion cannot be reconstructed by the application itself.
        - The current frontend does not expose this endpoint through a delete control,
          even though the API endpoint is registered and available.

        === by Sziller & ChatGPT ==="""

        service = self._service(db)
        deleted = service.delete_entry(entry_id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Accounting entry not found: {entry_id}",
            )

        return None

    def update_entry(
            self,
            entry_id: str,
            payload: AccountingEntryUpdateSchema,
            db: Session = Depends(get_db_session),
    ) -> AccountingEntryReadSchema:
        """=== Method name: update_entry ===  
        Replace the editable/raw fields of one existing accounting entry and
recalculate its backend-derived accounting values.

HTTP endpoint:
PUT /acct/v0/entries/{entry_id}

The endpoint accepts a complete `AccountingEntryUpdateSchema`, delegates the
update to `AccountingEntryService`, and returns the resulting persisted entry
as `AccountingEntryReadSchema`.

=== Authorization ===
- No authentication or authorization is currently required.
- The application is intended for local use on `127.0.0.1`.

=== Parameters ===
- `entry_id: str`
  Database-generated accounting-entry identifier supplied as a URL path
  parameter.

  Example:

  `PUT /acct/v0/entries/3f78b26d-1e43-4f68-9f6d-...`

  The current router accepts the identifier as a plain string rather than
  enforcing UUID-format validation at the API boundary.

- `payload: AccountingEntryUpdateSchema`
  Complete replacement data for the entry's editable/raw fields.

  `AccountingEntryUpdateSchema` currently inherits from
  `AccountingEntryCreateSchema`, so update input follows the same raw-field
  contract used for creation.

  Editable input includes fields such as:
  - entry type
  - category code
  - tax scope
  - counterparty name
  - payment method and payment date
  - invoice flag, invoice number, and invoice date
  - original amount and currency
  - remarks and tags
  - optional `source_filename`

  Backend-derived fields such as ID, booking year, common-currency amount,
  exchange rate, VAT values, deductible values, write-off method, conversion
  state, and timestamps are not valid update input.

- `db: Session`
  SQLAlchemy session supplied automatically by FastAPI through
  `Depends(get_db_session)`. It is not supplied by the API caller.

=== Functionality ===
1. FastAPI/Pydantic validates the request body against
   `AccountingEntryUpdateSchema`.
2. Unknown input fields are rejected.
3. Creates an `AccountingEntryService` using the injected database session.
4. Calls:

   `service.update_entry(entry_id=entry_id, payload=payload)`

5. The service:
   - loads the existing `AccountingEntryORM` row by primary key;
   - returns `None` if the entry does not exist;
   - normalizes the submitted invoice number;
   - checks that the submitted non-empty invoice number is not already used
     by another accounting entry;
   - reprocesses the complete raw payload through
     `AccountingEntryProcessor`;
   - replaces the persisted editable/raw fields;
   - replaces/recalculates derived fields such as booking year, common amount,
     VAT, deductibility, write-off method, and conversion state;
   - commits and refreshes the updated row;
   - if the resulting conversion state is `pending`, invokes
     `ConversionService.reprocess_entry()` and attempts to resolve the
     conversion using available historical exchange-rate data;
   - returns the final persisted entry as `AccountingEntryReadSchema`.
6. The router converts service-level `ValueError` exceptions into HTTP 400.
7. If the service returns `None`, the router returns HTTP 404.
8. Otherwise the updated accounting entry is returned.

=== Update Semantics ===
- This is a **PUT/full-replacement** update, not a PATCH operation.
- The client submits the current complete raw/editable representation of the
  accounting entry.
- Derived values are not directly edited.
- Derived values are recalculated from the submitted raw data.

For example, changing:
- `payment_date` recalculates `booking_year` and may change the applicable
  historical exchange-rate lookup date;
- `amount_original` recalculates common-currency and accounting amounts;
- `category_code` or `tax_scope` recalculates VAT/deductibility treatment;
- `currency_original` recalculates the conversion state;
- `source_filename` updates the stored source association metadata.

=== Invoice Rules ===
The processor enforces:

- If `has_invoice` is true:
  - `invoice_number` may be missing when it was not recognized.
  - `invoice_date` is required.

- If `has_invoice` is false:
  - `invoice_number` must be empty/null.
  - `invoice_date` must be null.

A non-empty invoice number may not duplicate the invoice number of another
accounting entry.

=== Currency Conversion Behavior ===
- EUR entries are processed directly into the common currency.
- Non-EUR entries are initially processed into a `pending` conversion state.
- During update, if the persisted result is pending, the service immediately
  invokes `ConversionService.reprocess_entry()`.
- If a suitable historical rate is available, the entry may be returned with
  conversion status `resolved` and recalculated EUR/VAT/deductible values.
- If no suitable rate is available, the entry remains pending.
- Unsupported conversion paths may be changed to a failed conversion state by
  the conversion service.

=== Response Format ===
Successful update returns:

- **200 OK**
- One `AccountingEntryReadSchema` object representing the resulting persisted
  state.

The response contains:
- database ID;
- updated raw accounting fields;
- optional `source_filename`;
- recalculated booking data;
- original/common-currency amounts;
- exchange-rate information;
- VAT values;
- deductible/write-off values;
- conversion status and note;
- creation and updated timestamps.

=== Errors ===
- **422 Unprocessable Entity**
  - Request JSON does not conform to `AccountingEntryUpdateSchema`.
  - Required fields are missing.
  - A field has an invalid type or allowed value.
  - An unknown, obsolete, misspelled, or backend-derived field is submitted.

- **400 Bad Request**
  - Business/accounting validation fails after schema validation.
  - Examples:
    - duplicate non-empty invoice number belonging to another entry;
    - inconsistent invoice fields;
    - other `ValueError` conditions raised by the service or processor.

- **404 Not Found**
  - No accounting entry exists for the supplied `entry_id`.
  - Response detail:

    `Accounting entry not found: <entry_id>`

- **500 Internal Server Error**
  - May occur for unexpected database, transaction, conversion, or internal
    processing failures not explicitly handled by this endpoint.

=== Persistence Behavior ===
- Existing raw and derived fields are overwritten with the newly processed
  values.
- The database row keeps the same primary-key `id`.
- `created_at` remains associated with the original row.
- `updated_at` is refreshed through SQLAlchemy's update behavior.
- Update currently performs an initial database commit before optional
  pending-currency reprocessing.
- Currency reprocessing may therefore involve a second commit.
- The complete update/conversion workflow is not currently one atomic
  database transaction.

=== Notes ===
- This endpoint should be used when manually correcting recognized accounting
  data after import.
- Ordinary clients should edit raw/source fields only and allow the backend to
  recalculate derived accounting data.
- `source_filename` is editable so an incorrect association between an entry
  and its recognized source file can currently be corrected manually.
- Unlike the batch endpoint, the single-entry PUT operation has no
  cross-entry `source_filename` consistency rule.
- The endpoint does not modify, rename, locate, or otherwise operate on any
  physical source file.
- Because this is full-replacement PUT semantics, callers should send the
  complete current editable payload rather than only the fields they intend
  to change.

=== by Sziller & ChatGPT ==="""
        try:
            service = self._service(db)
            result = service.update_entry(entry_id=entry_id, payload=payload)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Accounting entry not found: {entry_id}",
            )

        return result
    
    def get_metadata(self) -> dict:
        """=== Method name: get_metadata ===  
        Return the currently allowed accounting-entry metadata values used by the
        frontend and other API consumers.

        HTTP endpoint:
        GET /acct/v0/metadata

        This endpoint exposes the application's current selectable accounting
        vocabulary, including entry types, tax scopes, payment methods, currencies,
        and category codes with their human-readable labels.

        === Authorization ===
        - No authentication or authorization is currently required.
        - The application is intended for local use on `127.0.0.1`.

        === Parameters ===
        - None.

        This endpoint does not require:
        - request-body data;
        - path parameters;
        - query parameters;
        - a database session.

        === Functionality ===
        1. Reads the currently configured accounting-domain constants from
           `app.domain.accounting_rules`.
        2. Sorts the allowed values for:
           - entry types;
           - tax scopes;
           - payment methods;
           - currencies.
        3. Converts the category mapping into a list of objects containing:
           - category `code`;
           - human-readable category `label`.
        4. Sorts categories by category code.
        5. Returns the resulting metadata as JSON.

        No database query is performed.

        === Response Format ===
        Successful retrieval returns:

        - **200 OK**
        - A JSON object with the following structure:

        {
            "entry_types": [...],
            "tax_scopes": [...],
            "payment_methods": [...],
            "currencies": [...],
            "categories": [
                {
                    "code": "...",
                    "label": "..."
                }
            ]
        }

        === Response Fields ===
        - `entry_types`
          Sorted list of currently allowed accounting-entry type identifiers.

        - `tax_scopes`
          Sorted list of currently allowed tax-scope identifiers.

        - `payment_methods`
          Sorted list of currently allowed payment-method identifiers.

        - `currencies`
          Sorted list of currencies currently recognized by the accounting domain.

        - `categories`
          Sorted list of category descriptors.
          Each item contains:
          - `code`: machine-readable category value used in accounting-entry payloads;
          - `label`: human-readable category description intended for display.

        === Data Sources ===
        The response is built from the current domain definitions:

        - `ENTRY_TYPES`
        - `TAX_SCOPES`
        - `PAYMENT_METHODS`
        - `CURRENCIES`
        - `CATEGORY_LABELS`

        These are imported from:

        `app.domain.accounting_rules`

        The endpoint therefore reflects changes made to those domain registries
        without requiring database changes.

        === Errors ===
        - No normal application-specific error conditions are currently defined for
          this endpoint.

        - **500 Internal Server Error**
          - May occur only if an unexpected internal failure occurs while building
            the response.

        === Persistence Behavior ===
        - This is a read-only endpoint.
        - It does not access or modify the accounting database.
        - It does not create a SQLAlchemy session.
        - It does not trigger accounting processing or currency conversion.

        === Usage ===
        The browser frontend uses this endpoint to populate selectable controls such
        as:

        - entry-type dropdowns;
        - tax-scope dropdowns;
        - payment-method dropdowns;
        - currency dropdowns;
        - accounting-category dropdowns.

        The AI recognition contract also calls `get_metadata()` internally so the
        recognizer contract includes the current accounting-domain vocabulary.

        === Single-Source-of-Truth Role ===
        This endpoint is part of the application's schema/metadata synchronization
        mechanism.

        Its selectable values are taken directly from the accounting-domain
        registries rather than being maintained as a separate frontend-only list.

        As a result, changing a domain registry such as `CATEGORY_LABELS` changes:

        - the metadata returned to the frontend; and
        - the metadata embedded into
          `GET /acct/v0/entry-create-contract`.

        This helps keep user-facing selection values and AI-recognition guidance
        aligned with the application's current domain configuration.

        === Notes ===
        - The endpoint returns metadata only; it does not return accounting entries.
        - Category labels are display metadata. Accounting-entry payloads use the
          corresponding category `code`.
        - Sorting is applied for deterministic output and predictable frontend
          presentation.
        - The endpoint does not by itself define all structural validation rules for
          accounting-entry JSON; those are defined by the Pydantic input schemas.
        - Some allowed-value concepts are also represented by Pydantic types in the
          accounting-entry schema. This endpoint specifically reflects the imported
          domain registries used by this implementation.

        === by Sziller & ChatGPT ==="""
        return {"entry_types": sorted(ENTRY_TYPES),
                "tax_scopes": sorted(TAX_SCOPES),
                "payment_methods": sorted(PAYMENT_METHODS),
                "currencies": sorted(CURRENCIES),
                "categories": [ {"code": code, "label": label}
                                for code, label in sorted(CATEGORY_LABELS.items()) ] }

    def get_entry_create_contract(self) -> dict:
        """=== Method name: get_entry_create_contract ===
        Return the canonical machine-readable contract for AI-assisted accounting-entry
        recognition and batch submission.

        HTTP endpoint:
        GET /acct/v0/entry-create-contract

        This endpoint describes the exact JSON structure expected from an AI invoice
        or receipt recognizer before recognized entries are submitted to the
        bookkeeping API.

        The response combines mechanically generated Pydantic JSON Schemas with
        current accounting-domain metadata, canonical examples, endpoint information,
        and handwritten semantic instructions for the recognizer.

        === Authorization ===
        - No authentication or authorization is currently required.
        - The application is intended for local use on `127.0.0.1`.

        === Parameters ===
        - None.

        This endpoint requires no:
        - request body;
        - path parameters;
        - query parameters;
        - database session.

        === Functionality ===
        1. Builds canonical example payloads for:
           - a one-entry recognition batch;
           - a multi-entry recognition batch;
           - several explicitly invalid output shapes.
        2. Generates the authoritative batch JSON Schema directly from:

           `AccountingEntryBatchCreateSchema.model_json_schema()`

        3. Generates the authoritative individual-entry JSON Schema directly from:

           `AccountingEntryCreateSchema.model_json_schema()`

        4. Retrieves current accounting metadata through:

           `self.get_metadata()`

        5. Describes the API endpoints available for:
           - normal recognition-batch submission;
           - optional single-entry submission.
        6. Adds semantic recognizer rules explaining how invoice-recognition output
           should be constructed.
        7. Adds processing notes distinguishing recognizer-supplied raw data from
           backend-derived accounting data.
        8. Returns the complete contract as one JSON object.

        === Response Format ===
        Successful retrieval returns:

        - **200 OK**
        - A JSON object describing the current AI-recognition contract.

        The response contains the following major fields:

        - `contract_name`
          Human-readable identifier of the recognition contract.

        - `schema_name`
          Name of the authoritative batch Pydantic schema.

        - `schema_version`
          Current version identifier for the contract.

        - `purpose`
          Human-readable description of the contract's intended use.

        - `canonical_output_shape`
          Describes the required top-level recognizer-output structure:

          {
              "entries": [...]
          }

        - `json_schema`
          JSON Schema generated directly from
          `AccountingEntryBatchCreateSchema`.

        - `entry_item_schema`
          JSON Schema generated directly from
          `AccountingEntryCreateSchema`.

        - `metadata`
          Current accounting-domain metadata returned by `get_metadata()`,
          including allowed entry types, tax scopes, payment methods, currencies,
          and accounting categories.

        - `batch_submission_endpoint`
          Describes the normal endpoint for submitting recognized batches:

          `POST /acct/v0/entries/batch`

        - `single_entry_submission_endpoint`
          Describes the single-entry creation endpoint:

          `POST /acct/v0/entries`

          This endpoint remains available for GUI/manual/debugging use but is not the
          normal target for AI recognition output.

        - `batch_example_payload`
          Canonical batch-shaped example containing one accounting entry.

        - `multi_invoice_batch_example_payload`
          Canonical example demonstrating:
          - several accounting entries in one recognition batch;
          - several invoices originating from the same source image;
          - entries originating from different source images.

        - `invalid_output_shapes`
          Human-readable examples of recognizer-output structures that must not be
          used, such as:
          - a bare accounting-entry object;
          - a bare JSON array.

        - `recognizer_rules`
          Semantic instructions governing AI-generated recognition output.

        - `processing_notes`
          Additional guidance describing the boundary between recognized/raw input
          and backend-calculated accounting data.

        === Canonical Recognizer Output ===
        AI recognizers must produce exactly one top-level JSON object containing an
        `entries` array.

        Valid structural form:

        {
            "entries": [
                {...AccountingEntryCreateSchema...},
                {...AccountingEntryCreateSchema...}
            ]
        }

        Even when only one invoice or receipt is recognized, the output remains
        batch-shaped:

        {
            "entries": [
                {...single entry...}
            ]
        }

        The recognizer must not output:

        - a bare accounting-entry object;
        - a bare JSON array;
        - backend-generated ORM fields;
        - calculated accounting values;
        - obsolete fields;
        - invented explanatory fields.

        === Schema Ownership ===
        The structural portion of this contract is generated directly from the same
        Pydantic schemas used later to validate API submissions.

        Conceptually:

        `AccountingEntryCreateSchema`
                ->
        `AccountingEntryBatchCreateSchema`
                ->
        generated JSON Schema
                ->
        AI recognizer output
                ->
        `POST /acct/v0/entries/batch`
                ->
        the same Pydantic schemas validate the payload

        This establishes a single source of truth for viable structural input rules.

        Because the input schemas use `extra="forbid"`, the generated JSON Schema
        also communicates that additional/unknown object properties are not allowed.

        The endpoint does not independently reimplement field definitions,
        requiredness, types, or unknown-field behavior.

        === Metadata Ownership ===
        Selectable accounting-domain values are supplied through `get_metadata()`
        rather than copied into this contract independently.

        This includes:

        - entry types;
        - tax scopes;
        - payment methods;
        - currencies;
        - category codes and labels.

        This keeps recognizer guidance aligned with the accounting application's
        current domain registries.

        === Source-Filename Rules ===
        `source_filename` associates an accounting entry with the exact uploaded source
        file from which the invoice or receipt was recognized.

        The recognizer is instructed to:

        - preserve the uploaded attachment filename exactly;
        - preserve case, extension, spaces, and punctuation;
        - repeat a filename when several invoices originate from the same source
          image;
        - use different filenames when entries originate from different uploaded
          files;
        - never replace the filename with:
          - a filesystem path;
          - application-generated UUID;
          - file hash;
          - image description;
          - invented filename.

        For uploaded-file recognition batches, source-filename presence must satisfy
        the batch schema's consistency rule:

        - all entries provide `source_filename`; or
        - all entries leave `source_filename` null.

        Populated filenames may differ or repeat within the same batch.

        === Recognizer vs Backend Responsibilities ===
        The recognizer supplies raw/extracted information.

        Examples include:

        - entry classification;
        - category;
        - tax scope;
        - counterparty;
        - payment information;
        - invoice information;
        - original amount and currency;
        - remarks;
        - tags;
        - source filename.

        The recognizer must not supply backend-derived fields such as:

        - database ID;
        - creation/update timestamps;
        - booking year;
        - common-currency amount;
        - exchange-rate values;
        - VAT amount;
        - deductible amount;
        - write-off method.

        Those values are validated, calculated, enriched, and persisted by the
        bookkeeping backend.

        Uncertainty in extracted information should be recorded in `remarks` rather
        than represented through invented JSON properties.

        === Examples ===
        The endpoint includes static example payloads to demonstrate intended usage.

        These examples are explanatory aids.

        The generated Pydantic JSON Schemas remain authoritative for structural
        validation; handwritten examples and prose provide semantic guidance around
        those schemas.

        === Invalid-Shape Examples ===
        The `invalid_output_shapes` section documents common recognizer mistakes,
        including:

        1. returning one accounting-entry object directly;
        2. returning a JSON array directly.

        These examples are documentation only.

        Actual rejection of invalid request structures occurs later when a submitted
        payload is validated against `AccountingEntryBatchCreateSchema`.

        === Errors ===
        - No normal caller-generated validation errors are expected because this
          endpoint accepts no input payload.

        - **500 Internal Server Error**
          - May occur if an unexpected internal failure occurs while:
            - generating the Pydantic JSON Schemas;
            - retrieving accounting metadata;
            - constructing or serializing the contract response.

        === Persistence Behavior ===
        - This is a read-only endpoint.
        - It does not access the accounting-entry database.
        - It does not create or modify accounting entries.
        - It does not perform invoice recognition.
        - It does not submit entries to the batch endpoint.
        - It does not manipulate source files.
        - It does not perform accounting calculations or currency conversion.

        === Intended Workflow ===
        The intended AI-assisted workflow is:

        1. Request the current recognition contract from:

           `GET /acct/v0/entry-create-contract`

        2. Supply the contract together with invoice/receipt images to the AI
           recognizer.

        3. The recognizer returns canonical batch-shaped JSON:

           `{ "entries": [...] }`

        4. Submit that JSON to:

           `POST /acct/v0/entries/batch`

        5. The same authoritative Pydantic schemas represented in this contract
           validate the submitted payload.

        6. The accounting processor and service calculate derived values and persist
           valid entries.

        === Notes ===
        - This endpoint is an integration-contract endpoint rather than a CRUD
          accounting-data endpoint.
        - It is intended to make AI recognition reproducible and less dependent on
          manually maintained prompt instructions.
        - Structural field definitions are generated mechanically from Pydantic.
        - Accounting vocabulary is obtained from current domain metadata.
        - Handwritten `recognizer_rules`, `processing_notes`, and examples provide
          semantic guidance and therefore must still be maintained when recognition
          policy changes.
        - The contract currently carries version identifier `v0`.
        - The endpoint describes recognition and submission behavior but does not
          itself enforce recognizer compliance until generated output is submitted to
          the appropriate POST endpoint.

        === by Sziller & ChatGPT ==="""
        invoice_number_policy = get_invoice_number_policy_metadata()
        single_entry_example = {
            "entry_type": "expense",
            "category_code": "buro",
            "tax_scope": "domestic",
            "counterparty_name": "Example GmbH",
            "payment_method": "unknown",
            "payment_date": "2026-05-25",
            "has_invoice": True,
            "invoice_number": "RE-2026-001",
            "invoice_date": "2026-05-25",
            "amount_original": "123.45",
            "currency_original": "EUR",
            "remarks": "Extracted from invoice image. Payment date not visible; invoice date used as payment_date.",
            "tags": ["invoice"],
            "source_filename": "IMG_4821.JPG",
        }

        batch_example_payload = {
            "entries": [
                single_entry_example,
            ],
        }

        multi_invoice_batch_example_payload = {
            "entries": [
                {
                    "entry_type": "expense",
                    "category_code": "buro",
                    "tax_scope": "domestic",
                    "counterparty_name": "Example Supplier One GmbH",
                    "payment_method": "unknown",
                    "payment_date": "2026-05-25",
                    "has_invoice": True,
                    "invoice_number": "RE-2026-001",
                    "invoice_date": "2026-05-25",
                    "amount_original": "49.90",
                    "currency_original": "EUR",
                    "remarks": "First invoice extracted from multi-document input.",
                    "tags": ["invoice", "batch"],
                    "source_filename": "IMG_4821.JPG",
                },
                {
                    "entry_type": "expense",
                    "category_code": "betriebsbedarf",
                    "tax_scope": "domestic",
                    "counterparty_name": "Example Supplier Two GmbH",
                    "payment_method": "unknown",
                    "payment_date": "2026-05-25",
                    "has_invoice": True,
                    "invoice_number": "RE-2026-002",
                    "invoice_date": "2026-05-25",
                    "amount_original": "89.00",
                    "currency_original": "EUR",
                    "remarks": "Second invoice extracted from multi-document input.",
                    "tags": ["invoice", "batch"],
                    "source_filename": "IMG_4821.JPG",
                },
                {
                    "entry_type": "expense",
                    "category_code": "fachliteratur",
                    "tax_scope": "domestic",
                    "counterparty_name": "Example Supplier Three GmbH",
                    "payment_method": "card",
                    "payment_date": "2026-05-26",
                    "has_invoice": True,
                    "invoice_number": "RE-2026-003",
                    "invoice_date": "2026-05-26",
                    "amount_original": "24.50",
                    "currency_original": "EUR",
                    "remarks": "Invoice extracted from a different uploaded source file.",
                    "tags": ["invoice", "batch"],
                    "source_filename": "IMG_4822.JPG",
                },
            ],
        }

        return {
            "contract_name": "AIInvoiceRecognitionBatchContract",
            "schema_name": "AccountingEntryBatchCreateSchema",
            "schema_version": "v0",
            "purpose": (
                "This contract is for AI invoice recognition/formalization. "
                "Recognizer output must always be batch-shaped, even for one invoice."
            ),
            "canonical_output_shape": {
                "entries": [
                    "AccountingEntryCreateSchema",
                ],
            },
            "json_schema": AccountingEntryBatchCreateSchema.model_json_schema(),
            "entry_item_schema": AccountingEntryCreateSchema.model_json_schema(),
            "invoice_number_policy": invoice_number_policy,
            "metadata": self.get_metadata(),
            "batch_submission_endpoint": {
                "method": "POST",
                "path": "/acct/v0/entries/batch",
            },
            "single_entry_submission_endpoint": {
                "method": "POST",
                "path": "/acct/v0/entries",
                "status": "available_for_gui_or_debugging",
                "recognizer_instruction": "Do not use this endpoint for invoice-recognition output unless explicitly instructed.",
            },
            "batch_example_payload": batch_example_payload,
            "multi_invoice_batch_example_payload": multi_invoice_batch_example_payload,
            "invalid_output_shapes": [
                {
                    "description": "Bare single accounting-entry object is invalid for recognizer output.",
                    "shape": {
                        "entry_type": "expense",
                        "category_code": "buro",
                    },
                },
                {
                    "description": "Bare JSON array is invalid for recognizer output.",
                    "shape": [
                        {
                            "entry_type": "expense",
                            "category_code": "buro",
                        },
                    ],
                },
            ],
            "recognizer_rules": [
                "Always output exactly one top-level JSON object.",
                "The top-level object must contain an entries list.",
                "The entries value must be a JSON array.",
                "Each item in entries must conform to AccountingEntryCreateSchema.",
                "Output only fields defined by the supplied schema; do not add guessed, legacy, calculated, or explanatory keys, and keep uncertainty in remarks.",
                "For one invoice, output entries with one object.",
                "For multiple invoices, output one object per invoice or receipt.",
                "Populate source_filename invoice-by-invoice with the exact filename of the uploaded attachment used for that entry.",
                "Repeat the same source_filename when several entries originate from the same uploaded photo, and use different filenames for entries from different uploaded files.",
                "A recognition batch from uploaded files must provide source_filename on every entry; filenames may differ or repeat, but do not mix populated filenames with null source_filename values in one batch.",
                "Preserve source_filename exactly as presented: do not alter its case, extension, spaces, or punctuation.",
                "Never invent source_filename or replace it with an image description, filesystem path, application UUID, or file hash.",
                "If the source attachment filename genuinely cannot be determined, use null and explain the uncertainty in remarks.",
                "Do not output a bare single-entry object.",
                "Do not output a bare JSON array.",
                "Do not submit backend-derived fields such as id, created_at, updated_at, booking_year, amount_common, vat_amount, deductible_amount, or writeoff_method.",
                "The backend engine validates, calculates, enriches, and persists the entries.",
            ] + get_invoice_number_recognizer_rules(),
            "processing_notes": [
                "Submit only raw extracted/user-entered fields.",
                "source_filename identifies the exact uploaded source file from which that specific invoice or receipt was recognized.",
                "The backend engine calculates booking_year, VAT, deductible amounts, common-currency values, and writeoff_method.",
                "The AI extractor should not submit ORM fields, database IDs, timestamps, or calculated accounting fields.",
                "If a field is uncertain, preserve the uncertainty in the affected entry's remarks field.",
                "If the invoice currency is unsupported by the backend, use only schema-valid values and document the mismatch in remarks.",
            ],
        }

    def create_entries_batch(self,
                             payload: AccountingEntryBatchCreateSchema,
                             db: Session = Depends(get_db_session) ) -> list[AccountingEntryReadSchema]:
        """=== Method name: create_entries_batch ===  
        Create and persist multiple accounting entries from one batch JSON payload.
        
        HTTP endpoint:
        POST /acct/v0/entries/batch
        
        The endpoint accepts one `AccountingEntryBatchCreateSchema`, validates the
        batch envelope and all contained accounting entries, delegates processing and
        persistence to `AccountingEntryService`, and returns the entries that were
        successfully created as `AccountingEntryReadSchema` objects.
        
        This is the primary endpoint intended for importing accounting entries
        produced by the AI invoice-recognition workflow.
        
        === Authorization ===
        - No authentication or authorization is currently required.
        - The application is intended for local use on `127.0.0.1`.
        
        === Parameters ===
        - `payload: AccountingEntryBatchCreateSchema`
          JSON request body containing a non-empty `entries` list.
        
          Canonical request shape:
        
          {
              "entries": [
                  {...},
                  {...}
              ]
          }
        
          Each item must conform to `AccountingEntryCreateSchema`.
        
          Entry input includes raw/source-controlled fields such as:
          - entry type
          - category code
          - tax scope
          - counterparty name
          - payment method and payment date
          - invoice flag, invoice number, and invoice date
          - original amount and currency
          - remarks and tags
          - optional `source_filename`
        
          Backend-derived fields such as database ID, booking year, common-currency
          amount, exchange rate, VAT amounts, deductible amounts, write-off method,
          conversion state, and timestamps are not valid input fields.
        
        - `db: Session`
          SQLAlchemy session supplied automatically by FastAPI through
          `Depends(get_db_session)`. It is not supplied by the API caller.
        
        === Functionality ===
        1. FastAPI/Pydantic validates the complete request body against
           `AccountingEntryBatchCreateSchema`.
        2. The batch must contain at least one entry.
        3. Unknown fields are rejected both:
           - at the batch-envelope level; and
           - inside individual accounting-entry objects.
        4. Batch-level `source_filename` consistency is validated.
        5. Creates an `AccountingEntryService` using the injected database session.
        6. Passes `payload.entries` to `service.create_entries_batch()`.
        7. The service processes entries sequentially:
           - normalizes invoice numbers;
           - detects duplicate invoice numbers within the submitted batch;
           - checks invoice numbers against existing database entries;
           - skips recognized duplicates;
           - passes non-duplicate entries through `AccountingEntryProcessor`;
           - validates invoice/business rules;
           - calculates backend-derived accounting values;
           - creates corresponding `AccountingEntryORM` rows.
        8. All newly prepared rows are committed together after processing the batch.
        9. Persisted rows are refreshed and converted to
           `AccountingEntryReadSchema`.
        10. Returns only the entries that were actually created.
        
        === Batch Source-Filename Rule ===
        Within one batch, `source_filename` presence must be consistent.
        
        Valid:
        
        - every entry has `source_filename = null`; or
        - every entry has a populated `source_filename`.
        
        Invalid:
        
        - some entries have a populated `source_filename` while others leave it null.
        
        Example valid sourced batch:
        
        - entry 0 -> `IMG_4821.JPG`
        - entry 1 -> `IMG_4821.JPG`
        - entry 2 -> `IMG_4822.JPG`
        
        Filenames do not need to be identical.
        
        This allows:
        - several recognized invoices from the same photo to repeat one filename; and
        - one recognition batch to contain invoices originating from multiple photos.
        
        Blank or whitespace-only source filenames are normalized to `None` before
        batch consistency is evaluated.
        
        === Duplicate Invoice Behavior ===
        A normalized non-empty `invoice_number` is treated as unique.
        
        The service currently skips:
        
        - duplicate invoice numbers appearing earlier in the same submitted batch;
        - invoice numbers that already exist in the database.
        
        Skipped duplicate entries are not currently returned separately or described
        in the response.
        
        Therefore:
        
        - the number of returned entries may be smaller than the number of submitted
          entries;
        - absence from the returned list may indicate that an item was skipped as a
          duplicate.
        
        Entries without an invoice number are not deduplicated by this mechanism.
        
        === Accounting Processing Rules ===
        Each non-skipped entry is processed using the same accounting processor used
        for single-entry creation.
        
        Among other rules:
        
        - If `has_invoice` is true:
          - `invoice_number` may be missing when it was not recognized.
          - `invoice_date` is required.
        
        - If `has_invoice` is false:
          - `invoice_number` must be empty/null.
          - `invoice_date` must be null.
        
        - `booking_year` is derived from `payment_date`.
        - EUR entries receive their common-currency amount immediately.
        - Non-EUR entries are initially stored with pending conversion state.
        - VAT, deductible values, and write-off information are calculated by the
          backend rather than accepted from the caller.
        
        === Response Format ===
        Successful processing returns:
        
        - A JSON array of `AccountingEntryReadSchema` objects.
        - The array contains only entries actually created by this request.
        
        Each returned entry contains:
        - database-generated ID and timestamps;
        - accepted raw accounting fields;
        - optional `source_filename`;
        - normalized invoice information;
        - derived booking information;
        - original and common-currency values;
        - exchange-rate information;
        - VAT values;
        - deductible/write-off values;
        - conversion status and explanatory note.
        
        Example conceptual response:
        
        [
            {...created entry...},
            {...created entry...}
        ]
        
        If every submitted item is skipped because its invoice number is already
        known, the current implementation may return:
        
        []
        
        === Errors ===
        - **422 Unprocessable Entity**
          - Request JSON does not conform to `AccountingEntryBatchCreateSchema`.
          - `entries` is missing or empty.
          - An individual entry contains invalid field types or values.
          - An unknown, obsolete, misspelled, or backend-derived field is supplied.
          - An unknown field is added to the batch envelope.
          - The batch mixes populated and null `source_filename` values.
        
          The source-presence consistency error is:
        
          `All entries in one batch must either provide source_filename or all leave it null.`
        
        - **400 Bad Request**
          - Accounting/business validation fails after structural schema validation.
          - Examples include inconsistent invoice fields or another `ValueError`
            raised by the processor/service.
          - Database uniqueness conflicts translated by the service into
            `ValueError` are also returned as HTTP 400.
        
        - **500 Internal Server Error**
          - May occur for unexpected database, transaction, or internal processing
            failures not explicitly handled by the router.
        
        === Transaction Behavior ===
        - Entries are prepared sequentially.
        - The service performs one database commit after processing the batch.
        - An `IntegrityError` during that commit causes the transaction to be rolled
          back.
        - Therefore newly created rows from that commit are not intentionally
          persisted individually one-by-one.
        - Duplicate invoice numbers detected before commit are skipped rather than
          treated as batch-failing errors.
        
        === Recognition-Contract Relationship ===
        The expected batch structure is mechanically tied to the authoritative
        Pydantic input schemas.
        
        `GET /acct/v0/entry-create-contract` exposes:
        
        - the JSON Schema generated from `AccountingEntryBatchCreateSchema`;
        - the generated schema for `AccountingEntryCreateSchema`;
        - current accounting metadata;
        - recognizer-specific semantic instructions and examples.
        
        The intended workflow is therefore:
        
        Accounting schemas
            -> recognition contract
            -> AI-generated `{ "entries": [...] }`
            -> this batch endpoint
            -> same schemas validate the submitted result
            -> processor/service
            -> database
        
        Unknown or legacy fields are rejected rather than silently discarded.
        
        === Persistence Behavior ===
        - Successfully processed non-duplicate entries are physically inserted into
          the `accounting_entries` table.
        - Each created entry receives its own database-generated ID.
        - Multiple entries may legitimately share the same `source_filename`.
        - `source_filename` is metadata only; this endpoint does not locate, move,
          rename, upload, hash, or otherwise manage the corresponding physical file.
        - No document/archive record is created.
        
        === Notes ===
        - This endpoint is intended as the main ingestion path for recognized invoice
          batches.
        - A recognition batch may represent one or several uploaded source images.
        - One source image may contain several invoices and therefore produce several
          accounting entries carrying the same `source_filename`.
        - The canonical request envelope is always `{ "entries": [...] }`.
        - The current response does not explicitly report which submitted items were
          skipped as duplicates or why they were skipped; improving that operator
          feedback is a logical future enhancement.
        - Unlike the update workflow, batch creation does not currently invoke
          `ConversionService` immediately for newly created pending non-EUR entries.
          Such conversions can be resolved later through the conversion-reprocessing
          workflow.
        
        === by Sziller & ChatGPT ==="""
        try:
            service = self._service(db)
            return service.create_entries_batch(payload.entries)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    def reprocess_pending_conversions(self,
                                      db: Session = Depends(get_db_session) ) -> dict:
        """=== Method name: reprocess_pending_conversions ===
        Attempt to resolve accounting entries whose currency conversion is currently
        pending by using exchange-rate data already available to the application.

        HTTP endpoint:
        POST /acct/v0/conversions/reprocess-pending

        The endpoint delegates pending-conversion processing to `ConversionService`
        and returns a short summary containing the number of conversions successfully
        resolved during this invocation.

        === Authorization ===
        - No authentication or authorization is currently required.
        - The application is intended for local use on `127.0.0.1`.

        === Parameters ===
        - No caller-supplied request body, path parameters, or query parameters are
          currently required.

        - `db: Session`
          SQLAlchemy session supplied automatically by FastAPI through
          `Depends(get_db_session)`. It is not supplied by the API caller.

        === Functionality ===
        1. A request-scoped SQLAlchemy session is supplied by `get_db_session`.
        2. Creates a `ConversionService` using that database session.
        3. Calls:

           `service.reprocess_pending(limit=100)`

        4. The conversion service searches for accounting entries whose conversion
           state is currently pending.
        5. At most 100 pending entries are considered during one endpoint invocation.
        6. For each candidate, the service attempts to resolve the conversion using
           exchange-rate data available in the database.
        7. Successfully resolved entries have their conversion-related and dependent
           accounting values updated by the conversion service.
        8. The service returns the number of entries successfully resolved.
        9. The endpoint returns that count together with a human-readable summary.

        === Processing Limit ===
        The endpoint currently uses a fixed processing limit:

        `limit=100`

        Therefore, one invocation processes at most 100 pending conversion candidates.

        If more than 100 entries are pending, additional invocations may be necessary
        to process the remaining entries.

        The limit is currently an implementation constant and is not configurable by
        the API caller.

        === Response Format ===
        Successful execution returns:

        - **200 OK**
        - A JSON object with the following structure:

        {
            "resolved_count": 3,
            "message": "Resolved 3 pending conversion(s)."
        }

        === Response Fields ===
        - `resolved_count`
          Integer count of pending accounting entries that were successfully resolved
          during this invocation.

        - `message`
          Human-readable summary generated from `resolved_count`.

        If no pending conversion can be resolved, the endpoint returns:

        {
            "resolved_count": 0,
            "message": "Resolved 0 pending conversion(s)."
        }

        A zero count does not necessarily mean that no pending entries exist. It may
        also mean that the required exchange-rate data is not currently available or
        that none of the considered pending conversions could be resolved.

        === Currency-Conversion Role ===
        Accounting entries created with a non-common currency may initially be stored
        with a pending conversion state.

        This endpoint provides an explicit mechanism for revisiting those entries
        after exchange-rate data has become available.

        Conceptually:

        pending accounting entry
            -> available exchange-rate data
            -> ConversionService
            -> recalculated common-currency/accounting values
            -> resolved conversion state

        The router itself does not perform exchange-rate calculations; those rules
        belong to `ConversionService`.

        === Persistence Behavior ===
        - This endpoint may modify existing accounting-entry rows.
        - Successfully resolved entries may receive updated:
          - common-currency amount;
          - exchange rate;
          - exchange-rate date;
          - VAT-derived values;
          - deductible-derived values;
          - conversion status;
          - conversion note;
          - other conversion-dependent persisted values handled by
            `ConversionService`.
        - It does not create new accounting entries.
        - It does not delete accounting entries.
        - It does not import exchange rates itself.

        === Errors ===
        - No application-specific 400 or 404 handling is implemented directly in this
          router function.

        - **500 Internal Server Error**
          - May occur if an unexpected database, exchange-rate lookup, calculation,
            transaction, or other internal processing error propagates from
            `ConversionService`.
          - The router currently does not translate such exceptions into a custom
            HTTP response.

        === Notes ===
        - This is an action endpoint rather than a normal CRUD read operation:
          invoking it may change persisted accounting data.
        - It only works with exchange-rate information already available to the
          conversion subsystem; it does not itself fetch rates from an external
          provider.
        - `resolved_count` reports successful resolutions, not necessarily the total
          number of pending entries examined.
        - The fixed batch size of 100 prevents one invocation from attempting an
          unlimited number of pending conversions.
        - Re-running the endpoint is expected to be safe for entries that are no
          longer pending, because `reprocess_pending()` targets pending conversions.
        - Newly created non-EUR entries may remain pending until this workflow, an
          update operation, or another conversion-processing path successfully
          resolves them.

        === by Sziller & ChatGPT ==="""

        service = ConversionService(db=db)
        resolved_count = service.reprocess_pending(limit=100)

        return {
            "resolved_count": resolved_count,
            "message": f"Resolved {resolved_count} pending conversion(s).",
        }
    

    def process_entry(self, entry_id: str, db: Session = Depends(get_db_session)):
        return EntryProcessingService(db).process_entry(entry_id)

    def process_entries(self, db: Session = Depends(get_db_session)):
        return EntryProcessingService(db).process_entries()


Router = AccountingEntriesRouter
router_class = AccountingEntriesRouter
