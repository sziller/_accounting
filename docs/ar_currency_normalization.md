# Outgoing-invoice original and common amounts

`outgoing_invoices` now persists:

- `currency_original`: the currency printed on the invoice.
- `amount_original`: the printed gross invoice total, stored as exact decimal text.
- `currency_common`: the reporting currency, defaulting to `AR_COMMON_CURRENCY`
  in `app/core/config.py` (currently `EUR`). The setting applies to new invoices;
  changing it does not silently rewrite existing invoices.
- `amount_common`: nullable exact decimal text. Created/imported invoices always
  start with NULL, including invoices already denominated in the common currency.

The native PDF parser supplies `currency_original` and `amount_original`. Printed
net and VAT remain in the original currency. Existing `currency` and `gross_amount`
are retained as synchronized compatibility fields for current clients. Create and
PATCH accept either spelling; conflicting pairs are rejected. Paid/outstanding
amounts and payment allocations remain in the original invoice currency.

## Explicit normalization

The AR editor area contains **Normalize Pending Amounts**. It sends a body-free
`POST /acct/v0/outgoing-invoices/normalize-pending`, then refreshes the invoice table
and selected editor. The response contains `converted`, `pending`, and per-invoice
`invoices` records with `id`, `invoice_number`, `status`, `amount_common`,
`currency_common`, and a diagnostic `message`.

Only invoices with NULL `amount_common` are processed. No import, startup, GET,
refresh, or ordinary PATCH automatically performs normalization. The button is
disabled while editing to preserve unsaved changes. The calculated common amount
is read-only; create/PATCH reject client-supplied `amount_common`.

The initial conversion policy follows AP's existing local-rate implementation:

- Equal currencies: copy the exact original amount, on the explicit action.
- HUF to EUR: divide the original amount by the latest local **MNB EUR/HUF** rate
  on or before `invoice_date`; round to cents with `Decimal` and `ROUND_HALF_UP`.
  Invoice date is used because outgoing invoices do not yet have a payment date.
- Missing/invalid rates and unsupported currency pairs: leave NULL and report why.
  In particular, USD to EUR is not implemented by the current AP rate policy.
- No remote rate fetch occurs during this action. Rate maintenance stays separate.

A SQLite `BEGIN IMMEDIATE` transaction serializes normalization with invoice edits
and allocation changes. Previously converted rows are skipped. Editing the original
amount, original currency, common currency, or invoice date resets the common amount
to NULL; normalize again explicitly afterward. Other metadata edits retain it.

## Existing databases

`init_db()` still uses SQLAlchemy metadata for new tables, then invokes the
idempotent additive upgrade in `app/db/ar_currency_upgrade.py`. Existing tables
receive four columns via transactional `ALTER TABLE`; original values are backfilled
from `gross_amount` and `currency` without float conversion. `amount_common` stays
NULL. Invoice IDs, source metadata, timestamps, allocations, indexes, and existing
constraints are preserved. Repeated startup leaves existing converted amounts alone.

SQLite requires constant defaults to add NOT NULL original columns to populated
tables; those temporary values are replaced with each invoice's source values in
the same transaction. Application writes always explicitly supply validated fields.
No separate database or destructive table rebuild is introduced.
