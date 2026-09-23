# Receivables persistence API

This additive subsystem uses the existing `data/.Accounting.db`, `Base` metadata,
UUID string IDs, UTC timestamp defaults (`utc_now`), request-scoped SQLAlchemy
sessions, and decimal-string storage. It does not create accounting entries.

`main.create_app()` registers `ReceivablesRouter` alongside the existing routers.
The running app registers routers explicitly; `APP_ROUTER_INFO` is not its loader.
No new framework, migration tool, authentication policy, or dependency is added.

## Tables and fields

All IDs are UUID strings (`VARCHAR(36)`). Dates use SQL `DATE`. Timestamps use the
existing `DateTime(timezone=True)`/`utc_now` defaults; SQLite reads them back as
UTC values without timezone metadata. Create/update responses refresh the stored
record so timestamps have the same representation as subsequent GET responses.

| Table | Fields |
| --- | --- |
| `outgoing_invoices` | `id`, `invoice_number`, `invoice_date`, `due_date`, `customer_name`, `customer_reference`, `currency`, `net_amount`, `vat_amount`, `gross_amount`, `pdf_filename`, `pdf_sha256`, `remarks`, `created_at`, `updated_at` |
| `incoming_payments` | `id`, `payment_date`, `amount`, `currency`, `payer_name`, `bank_reference`, `payment_method`, `remarks`, `created_at`, `updated_at` |
| `invoice_payment_allocations` | `id`, `invoice_id`, `payment_id`, `amount_allocated`, `created_at` |

Invoice number/date/customer/currency/gross, payment date/amount/currency, and both
allocation references/amount are non-null. IDs and timestamps are generated.
Other business fields are nullable. Invoice numbers are unique (case-sensitive),
with a database unique constraint; surrounding whitespace on invoice numbers and
customer names is trimmed and blank input is rejected. The expense-recognition
invoice-number canonicalization policy is not applied to issued invoice numbers.

Amounts are stored as decimal strings in `VARCHAR(64)`, never SQLite floating
point. Request schemas accept at most 24 digits and 6 fractional places and reject
nonfinite values. Prefer JSON strings for money. Database checks enforce decimal
text and positive gross/payment/allocation amounts; supplied net/VAT may be zero.
API validation requires exact `net_amount + vat_amount == gross_amount` when both
components are supplied. No implicit tolerance or rounding is applied. If future
PDFs contain a separate rounding adjustment, that needs an explicit policy/field;
it is not silently hidden in this foundation.

Currencies accept any three uppercase ASCII letters, independent of the expense
recognition currency list. Database checks enforce this shape too; this is not an
ISO registry lookup. Short optional text fields have a 255-character API limit,
`payment_method` 64, PDF SHA-256 exactly 64 hexadecimal characters if supplied.
`remarks` is text. Filenames are metadata only: no file is opened or hash computed.

Both allocation foreign keys are indexed and use `ON DELETE RESTRICT`.
`PRAGMA foreign_keys=ON` is installed on each application database connection.
The same connection hook must be used by independently constructed test/script
engines. Direct external SQLite clients must enable foreign keys as usual.

```text
outgoing_invoices (1)
        |
        N
invoice_payment_allocations
        N
        |
incoming_payments (1)
```

## Routes

All paths have the prefix `/acct/v0`:

| Methods | Path |
| --- | --- |
| GET, POST | `/outgoing-invoices` |
| GET, PATCH | `/outgoing-invoices/{id}` |
| GET, POST | `/incoming-payments` |
| GET, PATCH | `/incoming-payments/{id}` |
| POST | `/invoice-payment-allocations` |
| DELETE | `/invoice-payment-allocations/{id}` |

POST returns 201, GET/PATCH 200, allocation DELETE 204. Invalid schema or merged
PATCH data returns 422; missing IDs return 404; invalid allocation/update business
rules return 400; duplicate invoice numbers/database conflicts return 409. A
SQLite lock timeout returns 503 with a retry message. There are no destructive
invoice/payment DELETE endpoints. Allocation removal does not delete the facts
of the invoice/payment; no reconciliation audit log exists in this version.

Create/update/read schemas are `OutgoingInvoice{Create,Update,Read}Schema` and
`IncomingPayment{Create,Update,Read}Schema`. Allocations have
`InvoicePaymentAllocation{Create,Read}Schema`. Unknown/derived fields are forbidden
in inputs. PATCH applies only supplied fields, permits clearing nullable fields,
and rejects null for required fields after merging with the stored record.

Example invoice POST body:

```json
{"invoice_number":"2026-001","invoice_date":"2026-09-15","customer_name":"Customer Ltd","currency":"EUR","gross_amount":"600.00"}
```

Example payment POST body:

```json
{"payment_date":"2026-09-16","amount":"500.00","currency":"EUR"}
```

Example allocation POST body (use IDs returned by those requests):

```json
{"invoice_id":"<invoice UUID>","payment_id":"<payment UUID>","amount_allocated":"500.00"}
```

## Computed responses and transactional validation

Invoice reads (including lists) contain `paid_amount`, `outstanding_amount`, and
`payment_status`. Totals are computed in Python with `Decimal` from the allocation
rows, never SQL `SUM` over text. `paid` means no outstanding balance. Otherwise
`overdue` takes precedence when `due_date < date.today()` (server-local date).
Otherwise any allocation gives `partially_paid`, and no allocation gives `open`.
A missing due date never yields overdue. These are not database columns.

Payment reads include `allocated_amount` and `unallocated_amount`. Responses also
include lightweight allocation lists: invoice responses add `payment_date`;
payment responses add `invoice_number`. Each includes allocation ID, both parent
IDs, allocated amount, and creation timestamp. No recursive parent embedding.
Like the existing entry list, lists are unpaginated; this is a basic local API.

Every service write owns a fresh session transaction, starting with SQLite
`BEGIN IMMEDIATE` before reading invoice/payment balances. This serializes writers
across connections/processes, including PATCH and allocation removal. The lock is
held through validation, insert/update/delete, and commit. Exceptions roll back.
Application callers must use this service and a fresh request/session transaction;
raw external SQL does not enforce cross-row balance/currency business rules.

Allocation requires existing parents, strictly positive amount, equal currencies,
and enough remaining balance on both parents. PATCH cannot shrink an amount below
its allocations or change currency while any allocation remains. This closes the
update path to invalidating previously valid reconciliations. The tests exercise
competing connections for both the invoice and payment limits.

## Initialization and future PDFs

There are no migrations. `init_db()` calls `Base.metadata.create_all()`, which adds
these three missing tables to an existing populated database without changing
existing tables or data. It is repeatable, but does not alter already-existing
columns/constraints; future schema changes will need a separate strategy.

`AR_INVOICE_PDF_DIRECTORY = DATA_DIR / "AR_invoice_pdf"` in
`app/core/config.py` names the outgoing source archive. Explicit deterministic
directory import is documented in `outgoing_invoice_pdf_import.md`. No PDF serving,
payment matching, FX settlement, frontend changes, or AP recognition changes exist.

Tests: run the project's configured Python interpreter with
`-m unittest discover -s tests -v`. `tests/test_receivables.py` uses real ASGI
requests and temporary file-backed SQLite databases (needed for concurrency),
without importing `main` or triggering MNB synchronization.
