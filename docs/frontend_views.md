# Bookkeeping working views

Navigation is Accounts Payable (`#ap`, default), Accounts Receivable (`#ar`), and
New Entries (`#new`). Existing machine-facing AP/New Entries IDs remain
`process-view` and `input-view`; AR uses `ar-view`. Old `#process`/`#input` hashes
are aliases. `view_navigation.js` handles buttons, initial hashes, and hash changes.

Accounts Payable retains its editor, JPEG viewer and zoom/pan, entry navigation,
table, and currency maintenance. New Entries contains Manual New Entry, batch JSON,
and recognition-contract tools. It contains no AR import/editor widgets.

Accounts Receivable uses AP desktop proportions (38:62) with an invoice editor
on the left, a compact PDF source/import section at right-top, and an internally
scrolling selectable invoice table at right-bottom. The right column is sticky on desktop;
under 900px it becomes a normal single-column flow with a bounded scrolling table.

`ar_invoice_import.js` owns a single selected-invoice snapshot plus the fetched
invoice list. Table clicks and Previous/Next select from that list and relock the
editor. Refresh replaces the snapshot with fresh backend data, or clears it if the
selected ID has disappeared. Cancel restores snapshot values without a request.
A successful list refresh discards any unsaved form edits.

Editable fields match the PATCH schema: invoice number/date, due date, customer
name/reference, original/common currencies, original net/VAT/gross, PDF filename/SHA-256, and remarks. Common amount, paid,
outstanding, payment status, and creation/update timestamps are always read-only.
Save sends only changed editable fields to PATCH `/acct/v0/outgoing-invoices/{id}`;
decimal values stay strings and cleared nullable fields become null. After success,
the list reloads and reselects the returned ID with current backend values. Failure
messages appear beside the editor, preserving the unlocked draft for correction.
Controls are disabled during requests to avoid overlapping selections/saves/imports.

A PDF click matches the exact stored `pdf_filename`. Exactly one match selects it;
zero or multiple matches produce a message without fabricating/changing selection.
Filenames are not invoice IDs and PDF order is not used for invoice navigation.

Existing backend constraints still apply: duplicate invoice numbers, inconsistent
totals, reductions below allocated amounts, and currency changes while allocations
exist are rejected. Editing PDF metadata does not rename files or recalculate hashes.
No new API or persistence logic was introduced.

The browser harness in `tests/frontend/source_image_viewer.mjs` tests all three
views with fixture APIs, including AR edits/errors and existing AP/New Entries
workflows. Live layout verification uses read-only requests only.

Both persisted-record tables have sortable column-header buttons. A first click
sorts ascending, a repeated click reverses the direction, and selecting a different
column starts ascending. The active header shows an arrow and `aria-sort`; native
buttons also support keyboard activation. Monetary columns use exact decimal
comparison, dates use their ISO values, and missing values remain last. Sorting
preserves the selected record and editor draft. Previous/Next follows the displayed
order. The chosen order survives data refreshes within the page session.

AR currency normalization and migration details: [AR currency normalization](ar_currency_normalization.md).
