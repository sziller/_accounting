# Explicit Accounts Payable processing

## Field authority

| Fields | Authority | Producer |
|---|---|---|
| entry_type, category_code, tax_scope | X | User/source classification |
| counterparty_name, payment_method, payment_date | X | User/source |
| has_invoice, invoice_number, invoice_date | X | User/source invoice metadata |
| amount_original, currency_original | X | Original monetary facts |
| remarks, tags_json, source_filename | X | User/source metadata |
| booking_year | Y | payment_date.year |
| currency_common | Y | AccountingEntryProcessor.currency_common (EUR), not editable |
| amount_common, exchange_rate, exchange_rate_date | Y | Common currency / historical FX result |
| vat_rate_percent, vat_amount | Y | Category/scope rule, gross VAT calculation |
| deductible_percent, deductible_amount, deductible_vat_amount | Y | Category percentage, gross and VAT |
| writeoff_method | Y | Category rule |
| conversion_status, conversion_note | Y | Processing result |
| id, created_at | Protected system metadata | Never assigned by processing |
| updated_at | System metadata | Existing ORM onupdate mechanism |

No authoritative per-entry accounting overrides exist. VAT class is an intermediate
lookup, not a persisted column. There is no annual depreciation schedule column.

## Canonical processing

Validate persisted X using the input schema; resolve common amount from local FX;
run AccountingEntryProcessor.process with that conversion result; determine category
VAT rate and deductible/writeoff classification; calculate VAT from fresh common
gross, deductible gross and deductible VAT; derive booking year from payment date.
All downstream monetary calculations consume this run's results, never old Y.
Same-currency input uses the processor's existing cent rounding. FX uses the existing
LocalCurrencyConversion division and ROUND_HALF_UP cent policy. Category and scope
rules, gross-based deduction and writeoff classification are unchanged.

The processor now accepts an optional CurrencyConversionResult. Ordinary create/edit
paths keep their existing behavior when this is omitted. Explicit processing supplies
local MNB EUR/HUF or ECB EUR/USD latest-on-or-before payment_date observations.
USD was added to the AP input whitelist, which previously contradicted the implemented
USD conversion support. No FX collection occurs here.

## API and atomicity

POST /acct/v0/entries/{entry_id}/process calls EntryProcessingService.process_entry.
POST /acct/v0/entries/process calls process_entries, selecting every accounting entry
regardless of status or null fields, in payment_date/id order. No pending-only limit.

Each process_entry owns a BEGIN IMMEDIATE transaction, reloads X, computes the entire
result, then assigns only DERIVED_FIELDS to the ORM. Decimal values become strings.
It flushes, validates the read response, and commits once. Missing/invalid inputs,
missing FX, calculation or storage failures roll back the entire entry and return
status=failed with a message; no new partial Y or failure flag is persisted. Old Y
(including its old conversion status) is retained on failure. Bulk calls the same
operation per ID and continues, returning processed/failed counts and per-entry results.
A catastrophic failure to list the database still propagates as a request failure.

Success returns status=processed and the persisted entry. Repeating with unchanged
inputs/rules/rates produces identical Y; updated_at is lifecycle metadata, not Y.

## UI

Process Entry is above the selected AP form. Process Entries is below the AP workspace.
Both use processAccountingEntries in accounting_entries.js and reload the list and
current editor from the backend. Actions are disabled while editing so unsaved drafts
are not mistaken for persisted X, and while a processing request is in progress.
Selection may change during the request; the old selected entry is not forced back.
AR retains its separate pending-currency action. The legacy AP pending-only API remains
available for compatibility, but the AP frontend no longer calls it.

Tests seed amount_common=999.00, vat_amount=999.00, deductible_amount=999.00,
booking_year=1900 and stale FX on a EUR 119 entertainment entry. Processing persists
119.00 common, 19.00 VAT, 83.30 deductible gross, 13.30 deductible VAT, year 2026,
partial writeoff, and clears obsolete FX. Source fields remain byte-for-byte unchanged.

Tax-year selection and future historical-rule architecture are defined in
[Accounting-rule contract](accounting_rule_contract.md). booking_year now comes
through resolve_tax_year; current payment-date behavior and all rule values are unchanged.
