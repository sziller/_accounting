# scripts/import_mnb_rates.py

"""
=== Script: import_mnb_rates ===
Command-line utility for importing historical MNB EUR/HUF exchange rates into
the local bookkeeping database.

The script provides the manual operator entry point for populating or extending
the application's local `eur_huf_exchange_rates` data from the Magyar Nemzeti Bank
(MNB) remote exchange-rate service.

It does not perform accounting-entry conversion itself. Its responsibility is
to obtain and persist exchange-rate data that can later be consumed by
`ConversionService`.

=== Default Behavior ===
When invoked without arguments:

`python scripts/import_mnb_rates.py`

the script imports MNB EUR/HUF exchange-rate data for:

- start date: `config.MNB_EXCHANGE_RATE_START_DATE`
- end date: current local calendar date
- request strategy: yearly chunks

Conceptually:

CLI
    ->
initialize database schema
    ->
open SQLAlchemy session
    ->
MnbExchangeRateImportService
    ->
MNB remote service
    ->
persist exchange rates
    ->
close session

=== Command-Line Arguments ===
- `--start YYYY-MM-DD`
  Inclusive start date of the requested import range.

  Default:

  `config.MNB_EXCHANGE_RATE_START_DATE`

- `--end YYYY-MM-DD`
  Inclusive end date of the requested import range.

  Default:

  current date at script execution time.

- `--no-chunk`
  Disable yearly request chunking and submit the full requested date range in
  one MNB import operation.

=== Chunking Strategy ===
By default, the requested interval is divided into calendar-year chunks.

Example:

2024-10-01 -> 2024-12-31
2025-01-01 -> 2025-12-31
2026-01-01 -> requested end date

This keeps individual MNB import requests bounded and makes long historical
imports more operationally manageable.

=== Persistence ===
The script initializes the application's database schema through `init_db()`
before importing.

A SQLAlchemy session is then created explicitly through
`create_db_session()` and passed to `MnbExchangeRateImportService`.

Exact duplicate/upsert semantics belong to the exchange-rate
service/repository layer rather than this script.

=== Output ===
For every requested date chunk the script prints:

- requested date range;
- number of imported/upserted rates;
- number of skipped rates.

After all chunks complete it prints aggregate totals.

=== Errors ===
- Invalid CLI date format is rejected by argparse.
- An end date before the start date terminates execution with `SystemExit`.
- Remote-fetch, parsing, or persistence exceptions raised by
  `MnbExchangeRateImportService` are not caught here and therefore propagate
  to the command-line caller.
- The database session is closed in all cases through `finally`.

=== Relationship to Conversion Processing ===
This script imports exchange-rate reference data only.

It does not:

- search for pending accounting entries;
- recalculate accounting entries;
- call `ConversionService.reprocess_pending()`;
- start the FastAPI server.

After rates have been imported, pending accounting entries may be resolved
through the application's conversion-processing workflow.

=== Intended Usage ===
This script is appropriate for:

- initial historical exchange-rate bootstrap;
- manually extending locally stored rate history;
- repairing known historical gaps;
- operator-triggered synchronization before reprocessing pending entries.

=== by Sziller & ChatGPT ===
"""
from __future__ import annotations

import argparse
from datetime import date

from app.core import config

from app.db.database import create_db_session, init_db
from app.services.mnb_exchange_rate_import_service import (
    MnbExchangeRateImportService,
)
from app.services.date_ranges import iter_year_chunks


def parse_iso_date(value: str) -> date:
    """
    === Function: parse_iso_date ===
    Parse one command-line date argument in ISO `YYYY-MM-DD` format.

    === Parameters ===
    - `value: str`
      Raw command-line argument supplied by argparse.

    === Returns ===
    - `datetime.date`
      Parsed calendar date.

    === Errors ===
    - Raises `argparse.ArgumentTypeError` when the supplied value cannot be
      interpreted as an ISO calendar date.

    Example invalid input:

    `2026/08/23`

    Expected form:

    `2026-08-23`

    === by Sziller & ChatGPT ===
    """
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid date '{value}'. Expected YYYY-MM-DD."
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    """
    === Function: build_parser ===
    Construct and configure the command-line parser for historical MNB
    EUR/HUF exchange-rate imports.

    === Functionality ===
    Defines the supported CLI options:

    - `--start`
      Inclusive import start date.
      Default: `config.MNB_EXCHANGE_RATE_START_DATE`.

    - `--end`
      Inclusive import end date.
      Default: current date.

    - `--no-chunk`
      Request the complete date range in one operation instead of splitting it
      into calendar-year chunks.

    === Returns ===
    - Configured `argparse.ArgumentParser`.

    === Notes ===
    Date strings are validated through `parse_iso_date()`.

    === by Sziller & ChatGPT ===
    """
    parser = argparse.ArgumentParser(
        description="Import MNB EUR/HUF historical exchange rates."
    )

    parser.add_argument(
        "--start",
        type=parse_iso_date,
        default=config.MNB_EXCHANGE_RATE_START_DATE,
        help=f"Start date in YYYY-MM-DD format. Default: {config.MNB_EXCHANGE_RATE_START_DATE} (config.py).",
    )

    parser.add_argument(
        "--end",
        type=parse_iso_date,
        default=date.today(),
        help="End date in YYYY-MM-DD format. Default: today.",
    )

    parser.add_argument(
        "--no-chunk",
        action="store_true",
        help="Import the full date range in one MNB request instead of yearly chunks.",
    )

    return parser


def main() -> None:
    """=== script function ====
    Import MNB EUR/HUF exchange rates into the local accounting database.
    === by Sziller & ChatGPT ==="""
    parser = build_parser()
    args = parser.parse_args()

    if args.end < args.start:
        raise SystemExit("--end must be greater than or equal to --start")

    init_db()

    db = create_db_session()

    total_imported = 0
    total_skipped = 0

    try:
        service = MnbExchangeRateImportService(db=db)

        if args.no_chunk:
            chunks = [(args.start, args.end)]
        else:
            chunks = list(iter_year_chunks(args.start, args.end))

        for chunk_start, chunk_end in chunks:
            print(f"Importing MNB EUR/HUF rates: {chunk_start} → {chunk_end}")

            result = service.import_eur_huf_rates(
                start_date=chunk_start,
                end_date=chunk_end,
            )

            total_imported += result.imported_count
            total_skipped += result.skipped_count

            print(
                f"  imported/upserted={result.imported_count}, "
                f"skipped={result.skipped_count}"
            )

        print(
            f"Done. Total imported/upserted={total_imported}, "
            f"total skipped={total_skipped}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
