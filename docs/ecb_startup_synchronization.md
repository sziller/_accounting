# EUR/USD startup synchronization

Application construction runs `init_db()`, MNB EUR/HUF synchronization, then ECB
EUR/USD synchronization. Each owns and closes a separate session. Provider
failures are logged and nonfatal; schema/storage/configuration failures propagate.
No AP/AR amounts are converted by startup.

Configuration in `app/core/config.py`:
- `ECB_EXCHANGE_RATE_START_DATE = date(2021, 1, 1)`: explicit independent baseline,
  initially aligned with the existing bookkeeping history; changing MNB does not change ECB.
- `ECB_EXCHANGE_RATE_LOWER_BOUNDARY_TOLERANCE_DAYS = 7`: calendar-day lower-bound
  synchronization tolerance for ordinary weekend/adjacent holiday boundaries.
  This is a heuristic, not a publication calendar or completeness guarantee.
  It does not interpolate, fill weekends, or assert a publication frequency.

`EcbExchangeRateSyncService.synchronize(today=None)` injects
`EurUsdExchangeRateService` into the existing historical planner and supplies a
policy override. The ECB provider remains unchanged. There is no yearly chunking.
An empty archive requests the configured start through today. An earliest date
more than seven days after the start causes a lower backfill; every run also
refreshes inclusively from the latest stored date through today. Empty valid
responses store nothing and may be retried on subsequent startup.

## Additive schema upgrade

The project uses SQLAlchemy `Base.metadata.create_all()` in `init_db()`, not a
versioned migration framework. Registering `EurUsdExchangeRateORM` is the additive
migration: existing databases get `eur_usd_exchange_rates` automatically and
idempotently, without network access, copying rows, renaming, or altering the
existing `eur_huf_exchange_rates` table. Preexisting USD rows in the old generalized table
are not moved; production ECB synchronization and its dedicated lookup use the new table.

The new table has UUID `id`, `rate_date`, `base_currency`, `quote_currency`, decimal
text `rate`, `unit`, `source`, `created_at`, and `updated_at`. SQL constraints require
EUR/USD, unit 1, and one observation per date. The shared repository implementation
performs the same source-protected atomic upsert: identical observations preserve
IDs/timestamps; changed values update the same row; another source cannot overwrite.

```python
from app.services.ecb_exchange_rate_sync_service import EcbExchangeRateSyncService
from app.services.eur_usd_exchange_rate_service import EurUsdExchangeRateService

result = EcbExchangeRateSyncService(db).synchronize()
rate = EurUsdExchangeRateService(db).get_exact_rate(
    rate_date=day, base_currency="EUR", quote_currency="USD", source="ECB")
row = EurUsdExchangeRateService(db).get_latest_rate_on_or_before(
    rate_date=day, base_currency="EUR", quote_currency="USD", source="ECB")
```

Exact lookup returns `Decimal` or None. Latest lookup returns the stored row or
None, with its actual observation date (no synthetic rates or maximum-age rule).
`get_rate_date_bounds`, `list_rates`, and `upsert_rate` retain explicit identities.
The original `ExchangeRateService` continues to address the original table.
