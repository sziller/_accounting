# Explicit AR PDF archive import

Legacy compatibility workflow. For new invoices use [contract-based recognition](outgoing_invoice_recognition.md); the AR UI no longer scans or imports this directory.

## Configuration and scope

Canonical settings in `app/core/config.py`:

```python
AP_SOURCE_DOCUMENT_DIRECTORY = DATA_DIR / "AP_source_files"
AR_SOURCE_DOCUMENT_DIRECTORY = DATA_DIR / "AR_source_files"
```

All internal references/tests have been migrated; no ambiguous compatibility
aliases remain. The AP URL remains `GET /acct/v0/source-documents/{filename}`.
AR import does not change AP recognition, accounting entries, payments, or
allocations. The Accounts Receivable view provides explicit processing controls.
There is no startup import or filesystem watcher.

## Supported layout and synthetic examples

Supported parser family: **Honorarrechnung bilingual v1**, with DE/HU and
DE/EN variants and an explicit legacy DE/HU aggregate variant.

All example parties, invoice identifiers, dates and monetary amounts in this
contract and its parser fixtures are fictitious. Only the supported template
labels, ordering and number-format conventions reproduce the parser contract.
Private document inventories and observations belong outside the repository.

The parser preserves the printed invoice date. It does not correct it using a
filename, PDF metadata, the current year or service-period dates. A re-export
with the same invoice number is a conflict, not an automatic update.

Representative synthetic extraction structure:

```text
Honorarrechnung Nr.: 9101
9. April 2031
Example Issuer
... issuer banking and tax information ...
Ust-IdNr. - VATIN: DE123456789
Herr Test Recipient Mr. Test Recipient
Example Customer Ltd Example Customer Ltd
... recipient addresses ...
Honorarrechnung Invoice
... service lines and notes ...
Nettohonorar – net amount: 12 400 USD
Bruttohonorar
(siehe Vermerk) – gross amount: (see Note) 12 400 USD
Bitte überweisen Sie das Bruttohonorar innerhalb
der nächsten 14 Tage,
... signature ...
9101
```

## Exact parser rules

`parse_ar_invoice_text(text)` is independent of HTTP and persistence and returns
an `OutgoingInvoiceCreateSchema`. It normalizes whitespace within lines, retains
line order, and rejects more than one nonempty page.

- **Invoice number:** exactly one first-line `Honorarrechnung Nr.: NNNN`; its four
  printed digits must equal the final footer line. Filename digits are ignored.
- **Invoice date:** the next line must contain day, German month name, and four-digit
  year, e.g. `8. März 2032`. Validated as a calendar date.
- **Customer:** block after the unique issuer `Ust-IdNr. - VATIN:` line and before
  `Honorarrechnung Számla` or `Honorarrechnung Invoice`. The first recipient line
  must begin `Herr ` or contain an identical repeated bare contact name (at least
  two alphabetic name words, allowing internal hyphens/apostrophes); the next line must repeat the company identically twice,
  matching the observed bilingual columns. One copy becomes `customer_name`.
  An issuer-name match is rejected. Unknown recipient arrangements fail.
- **Net:** the full line following `Nettohonorar – net amount:` must contain one
  amount and currency. **Gross:** likewise after the observed two-line
  `Bruttohonorar` / `(siehe Vermerk) – gross amount: (see Note)` label.
- **Money:** decimal dots and optional correctly grouped space thousands are
  supported (`2350.00`, `12 400`, `1234`). Commas/ambiguous formatting fail.
  Decimal arithmetic only, followed by existing schema precision/positivity rules.
  Net and gross must agree in these supported no-VAT variants. No line-item
  reconstruction or adjustment of printed totals occurs.
- **Currency:** printed uppercase three-letter codes or `€` (normalized to `EUR`).
  Net and gross currency must agree. Neither EUR nor USD is assumed.
- **VAT:** null: neither observed variant prints a VAT amount. Zero is not inferred.
- **Due date:** null: both variants print 14-day terms, not an explicit due date.
  Terms are retained in remarks, not converted into a date.
- **Customer reference:** null: no purchase-order/customer reference label occurs.
  Customer company-registration or tax IDs are not substituted.
- **Remarks:** the observed German VAT note and payment terms, joined across their
  line breaks. DE/HU requires `Vermerk: Reverse-Charge-Regelung Megjegyzés:
  Közösségi adózás – fordított ÁFA`; DE/EN requires `Vermerk: nicht
  umsatzsteuerpflichtig -` / `Leistung an Kunden ausserhalb der EU`.
- **Source metadata:** importer supplies exact basename and lowercase SHA-256 of
  original bytes, never values extracted from the document's visible text.

Different page counts, numbering formats, recipient arrangements, note/term labels,
or monetary layouts need explicit parser extensions and representative fixtures.

## Services and endpoint

The Accounts Receivable view loads both datasets on initialization and on Refresh:
`GET /acct/v0/outgoing-invoices/source-files` returns
`{"directory":"AR_source_files","files":["example.pdf"]}`, and
`GET /acct/v0/outgoing-invoices` returns a bare array of invoice records. Source
filenames are sorted, case-insensitive by extension only, and omit directories
and symlinks outside the archive. A missing/empty directory returns an empty list;
unreadable directories return a path-free HTTP 503 error. Listing never imports.

The panel's Update DB button sends a body-free POST to the processing endpoint,
shows per-file results, and reloads both datasets. Backend-computed paid/outstanding
amounts are displayed verbatim. Loading, empty, and error states are independent
for each dataset. Panel logic lives in `app/static/js/ar_invoice_import.js`,
imported by the existing accounting-entry module.

`pdf_extraction_service.py` still provides byte-based embedded-text extraction and
safe file loading. `import_ar_invoice_pdf(filename, session_factory=...)` processes
one source. `process_ar_invoice_directory(session_factory=...)` handles the archive.

```text
POST /acct/v0/outgoing-invoices/process-directory
```

No body is required. Only top-level names with case-insensitive `.pdf` suffixes
are considered, in Python filename sort order. Other suffixes are ignored.
Directories named `.pdf`, unreadable files, malformed PDFs, and escaping symlinks
receive individual failures. Missing/unreadable archive directory returns HTTP 400
with `directory_unavailable`. An empty directory returns a successful empty report.

A completed batch returns HTTP 200 even if some PDFs failed:

```json
{
  "files": [
    {"filename":"example.pdf","status":"imported","outgoing_invoice_id":"<UUID>","invoice_number":"9101","error_code":null,"error":null}
  ],
  "imported":1,
  "already_imported":0,
  "failed":0
}
```

The status vocabulary is `imported`, `already_imported`, `failed`. Failed entries
include `error_code` and a path-free message. Conflicts include the existing
invoice ID; parse failures never produce partial invoice rows. Every file is
independent, so a failed file does not stop later files. The single-file service
is reusable by scripts; no separate single-PDF HTTP endpoint existed previously.

## Transactions and duplicates

After extraction and schema validation, `ReceivablesService.create_invoice_from_pdf`
uses the same `_write()` / SQLite `BEGIN IMMEDIATE` mechanism as existing writes.
Hash and number checks and insertion share one transaction. Concurrent importers
cannot insert duplicate documents. Each file uses a fresh session; there is no
batch-wide commit that could undo earlier successful files.

1. Matching SHA-256 (case-insensitive comparison): `already_imported`, including
   a renamed copy. The original stored filename is not overwritten.
2. Existing invoice number with different or null hash: `failed`, error code
   `invoice_number_conflict`. This may indicate a re-export or a manual invoice.
3. Otherwise insert with existing validation and invoice-number DB uniqueness.

No new hash index or migration was added: import checks are serialized in the
service, preserving current manual CRUD semantics. This guarantees deduplication
for this import path, not for external SQL/manual creation of arbitrary hashes.
A global unique hash policy would require auditing existing hashes, a reproducible
index upgrade, and deliberately changing manual CRUD behavior.

## Archive and diagnostics

The processor reads PDFs; it does not rename, move, delete, rewrite, or deliberately
touch file timestamps. File bytes and modification timestamps are checked in tests.
Normal filesystem access-time behavior may occur when reading.

Extraction error codes cover invalid filenames/extensions, missing/unreadable files,
malformed/encrypted PDFs, and absent embedded text. Parser codes include
`unsupported_layout`, `invoice_number_not_found`, `invoice_date_not_found`,
`customer_not_found`, `net_amount_not_found`, `gross_amount_not_found`,
`currency_conflict`, `totals_inconsistent`, `invalid_legacy_huf_amount`, and `invalid_invoice_values`.
Unexpected errors are logged server-side and become per-file `processing_failed`.

## Tests and template improvements

### Legacy DE/HU aggregate variant

This explicit variant is recognized by `Nettohonorar gesammt – nettó összeg`
or `(siehe Vermerk) – bruttó: (lásd megjegyzés)` within the single-page invoice.
It requires the `Honorarrechnung Számla` title, both unique aggregate rows, the
immediately preceding `Bruttohonorar` line for gross, and the existing reverse-charge
note. Mixing English aggregate labels into this variant is rejected. Component
`Nettohonorar` rows are not used to select or reconstruct the aggregate.

Only this variant accepts dot-grouped integer HUF totals matching
`[1-9][0-9]{0,2}(?:\.[0-9]{3})+`. After validation, dots are removed and the text is
converted directly to Decimal: `84.000` → `84000`, `228.000` → `228000`.
Ungrouped, signed, comma, decimal, and malformed grouped forms are not guessed.
Both currencies must be HUF and both amounts must agree. Its exact two-line terms
end in `der nächsten 14 Tage.`. Existing variants keep their decimal-dot grammar
and existing terms; date validation is unchanged for every variant.

`test_ar_legacy_invoice_parser.py` builds synthetic native PDFs with fictitious
parties, identifiers, dates and amounts, retaining the supported extraction
structure and grouping conventions. Imports use a temporary database.
`ar_honorarrechnung_legacy_de_hu.txt` also supports malformed-variant tests.
Private source PDFs are not required by the suite. All `/data/` content is local
and Git-ignored; private PDFs, images and databases must not be committed.

`tests/fixtures/ar_honorarrechnung_de_{en,hu}.txt` contain fictitious parties, identifiers, dates and amounts with the
observed labels/order. `tests/test_ar_invoice_import.py` builds native PDF fixtures
from them and tests extraction through persistence and the HTTP endpoint, repeated
and renamed documents, conflicts, errors/continuation, exact values/filenames,
archive preservation, and concurrent imports. No private PDFs were added as fixtures.

For greater reliability, give recipient/company fields explicit labels, print an
explicit due date and VAT amount when intended, use consistently labeled one-line
totals and ISO dates, and verify printed invoice dates in the source template.
A multi-page or revised template should be supplied for inspection before changing
these strict rules. No OCR, AI, or payment import/matching is added.
