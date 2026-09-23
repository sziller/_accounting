"""ECB supplied-contract tests with synthetic CSV values and mocked HTTP only."""
import csv
from datetime import date, datetime
from decimal import Decimal
from http.client import IncompleteRead
from io import StringIO, BytesIO
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, parse_qs

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.models import Base, ExchangeRateORM
from app.services.ecb_exchange_rate_provider import EcbHistoricalRateProvider, EcbExchangeRateProviderError
from app.services.exchange_rate_service import ExchangeRateService
from app.services.historical_exchange_rate_service import HistoricalExchangeRateService, ExchangeRateProviderError

START, END = date(2009, 5, 1), date(2009, 5, 31)
CSV = (Path(__file__).parent / "fixtures" / "ecb_eur_usd.csv").read_text()
HEADER = CSV.splitlines()[0] + "\n"
HTTP_TARGET = "app.services.ecb_exchange_rate_provider.urlopen"


def response(body=CSV, status=200):
    result = MagicMock()
    result.__enter__.return_value = result
    result.status = status
    result.read.return_value = body.encode("utf-8") if isinstance(body, str) else body
    return result


def changed_csv(**changes):
    reader = csv.DictReader(StringIO(CSV))
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, reader.fieldnames)
    writer.writeheader()
    for row in reader:
        writer.writerow({**row, **changes})
    return stream.getvalue()


class EcbHistoricalRateProviderTests(unittest.TestCase):
    def fetch(self, body=CSV):
        with patch(HTTP_TARGET, return_value=response(body)):
            return EcbHistoricalRateProvider().fetch_rates(quote_currency="USD", start_date=START, end_date=END)

    def assert_invalid(self, body, code):
        with self.assertRaises(EcbExchangeRateProviderError) as caught:
            self.fetch(body)
        self.assertEqual(caught.exception.code, code)

    def test_exact_endpoint_query_timeout_and_no_network_at_construction(self):
        with patch(HTTP_TARGET, return_value=response()) as request:
            provider = EcbHistoricalRateProvider()
            request.assert_not_called()
            provider.fetch_rates(quote_currency=" usd ", start_date=START, end_date=END)
        request.assert_called_once()
        http_request = request.call_args.args[0]
        url = urlsplit(http_request.full_url)
        self.assertEqual((url.scheme, url.netloc, url.path),
                         ("https", "data-api.ecb.europa.eu", "/service/data/EXR/D.USD.EUR.SP00.A"))
        self.assertEqual(parse_qs(url.query), {"startPeriod":["2009-05-01"], "endPeriod":["2009-05-31"], "format":["csvdata"]})
        self.assertEqual(http_request.get_method(), "GET")
        self.assertEqual(http_request.get_header("Accept"), "text/csv")
        self.assertEqual(request.call_args.kwargs, {"timeout":30.0})  # No unverified SSL context.
        self.assertEqual(provider.source, "ECB")
        self.assertEqual(provider.quote_currencies, frozenset({"USD"}))
        self.assertEqual(provider.history_policy.lower_boundary_tolerance_days, 0)
        self.assertFalse(provider.history_policy.chunk_by_year)

    def test_exact_decimals_identity_multiple_observations_and_no_fill(self):
        rows = self.fetch()
        self.assertEqual([row.rate_date for row in rows], [date(2009,5,4), date(2009,5,8)])
        for row in rows:
            self.assertEqual((row.base_currency, row.quote_currency, row.source, row.unit), ("EUR","USD","ECB","1"))
            self.assertIsInstance(row.rate, Decimal)
        self.assertEqual(str(rows[0].rate), "1.1490")
        self.assertEqual(str(rows[1].rate), "1.1750123456789012345678901234567890")
        self.assertEqual(rows[0].rate.as_tuple().exponent, -4)
        # Neither unpublished weekdays nor the intervening/final weekends are generated.
        self.assertEqual(len(rows), 2)

    def test_header_names_allow_reordering_extra_columns_quoted_fields_and_bom(self):
        rows = list(csv.DictReader(StringIO(CSV)))
        fields = ["OBS_VALUE", "NOTE", "TIME_PERIOD", "EXR_SUFFIX", "CURRENCY_DENOM", "CURRENCY", "EXR_TYPE", "FREQ"]
        stream = StringIO(newline="")
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({**row,"NOTE":"ignored, quoted\nmetadata"})
        self.assertEqual(self.fetch("\ufeff" + stream.getvalue()), self.fetch())

    def test_header_only_csv_is_valid_empty_result(self):
        self.assertEqual(self.fetch(HEADER), [])
        self.assertEqual(self.fetch(HEADER + "\n\n"), [])

    def test_blank_body_is_a_failure_not_no_observations(self):
        for body in ("", " \r\n\t", "\ufeff"):
            with self.subTest(body=body):
                self.assert_invalid(body, "empty_response")

    def test_missing_required_fields_fail(self):
        for field in HEADER.strip().split(","):
            with self.subTest(field=field):
                self.assert_invalid(",".join(name for name in HEADER.strip().split(",") if name != field) + "\n", "missing_fields")
        self.assert_invalid('<html>Upstream error</html>', "missing_fields")

    def test_malformed_csv_duplicate_headers_row_width_and_encoding(self):
        for body in (HEADER.rstrip() + ",OBS_VALUE\n", HEADER + '"unterminated',
                     CSV.replace("1.1490", "1.1490,extra"), CSV.replace(",1.1490", ""),
                     HEADER.rstrip() + ",\n", b"\xff\xfe\x00"):
            with self.subTest(body=body):
                self.assert_invalid(body, "malformed_csv")

    def test_invalid_rates_fail_without_repair(self):
        for value in ("", "abc", "1,1490", "1_1490", "NaN", "Infinity", "-Infinity", "0", "-1", "1/1.1490"):
            with self.subTest(value=value):
                self.assert_invalid(changed_csv(OBS_VALUE=value), "invalid_rate")

    def test_invalid_dates_fail(self):
        for value in ("", "2009-02-30", "2009-05", "20090504", "04/05/2009", "2009-05-04T00:00:00"):
            with self.subTest(value=value):
                self.assert_invalid(changed_csv(TIME_PERIOD=value), "invalid_date")

    def test_out_of_range_dates_fail(self):
        for value in ("2009-04-30", "2009-06-01"):
            self.assert_invalid(changed_csv(TIME_PERIOD=value), "date_out_of_range")

    def test_wrong_series_dimensions_fail_in_every_observation(self):
        for field, wrong in (("FREQ","M"), ("CURRENCY","HUF"), ("CURRENCY_DENOM","USD"),
                             ("EXR_TYPE","OTHER"), ("EXR_SUFFIX","E")):
            with self.subTest(field=field):
                self.assert_invalid(changed_csv(**{field:wrong}), "wrong_series")
                self.assert_invalid(changed_csv(**{field:""}), "wrong_series")
        self.assert_invalid(changed_csv(CURRENCY="EUR", CURRENCY_DENOM="USD"), "wrong_series")
        self.assert_invalid(CSV.replace("D,USD,EUR,SP00,A,2009-05-08", "D,GBP,EUR,SP00,A,2009-05-08"), "wrong_series")

    def test_duplicate_dates_are_rejected(self):
        self.assert_invalid(CSV + CSV.splitlines()[1] + "\n", "duplicate_date")

    def test_http_failures_are_explicit_including_empty_non_csv_status(self):
        for status in (204, 301, 400, 404, 429, 500):
            with self.subTest(status=status), patch(HTTP_TARGET, side_effect=HTTPError("https://data-api.ecb.europa.eu", status, "error", {}, BytesIO(b"error"))):
                with self.assertRaises(EcbExchangeRateProviderError) as caught:
                    EcbHistoricalRateProvider().fetch_rates(quote_currency="USD", start_date=START, end_date=END)
                self.assertEqual(caught.exception.code, "http_error")
                self.assertIn(str(status), str(caught.exception))
        with patch(HTTP_TARGET, return_value=response("", status=204)):
            with self.assertRaises(EcbExchangeRateProviderError) as caught:
                EcbHistoricalRateProvider().fetch_rates(quote_currency="USD", start_date=START, end_date=END)
            self.assertEqual(caught.exception.code, "http_error")

    def test_timeout_connection_and_incomplete_read_failures(self):
        for error, code in ((TimeoutError(), "timeout"), (URLError(TimeoutError()), "timeout"),
                            (URLError("offline"), "connection_failed"), (OSError("reset"), "connection_failed")):
            with self.subTest(error=error), patch(HTTP_TARGET, side_effect=error):
                with self.assertRaises(EcbExchangeRateProviderError) as caught:
                    EcbHistoricalRateProvider().fetch_rates(quote_currency="USD", start_date=START, end_date=END)
                self.assertEqual(caught.exception.code, code)
        for error in (TimeoutError(), IncompleteRead(b"partial")):
            reply = response()
            reply.read.side_effect = error
            with patch(HTTP_TARGET, return_value=reply):
                with self.assertRaises(EcbExchangeRateProviderError):
                    EcbHistoricalRateProvider().fetch_rates(quote_currency="USD", start_date=START, end_date=END)
            reply.__exit__.assert_called_once()

    def test_invalid_arguments_fail_before_network(self):
        with patch(HTTP_TARGET) as request:
            for quote in ("HUF", "EUR", "GBP", "EURUSD"):
                with self.subTest(quote=quote), self.assertRaises(ValueError):
                    EcbHistoricalRateProvider().fetch_rates(quote_currency=quote, start_date=START, end_date=END)
            for start, end in ((END,START), ("2009-05-01",END), (datetime(2009,5,1),END)):
                with self.assertRaises(ValueError):
                    EcbHistoricalRateProvider().fetch_rates(quote_currency="USD", start_date=start, end_date=end)
            request.assert_not_called()
        for timeout in (0,-1,float("inf"),float("nan"),True,None,"30"):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                EcbHistoricalRateProvider(timeout=timeout)

    def test_custom_timeout_and_single_bounded_request_without_chunking(self):
        with patch(HTTP_TARGET, return_value=response()) as request:
            EcbHistoricalRateProvider(timeout=12).fetch_rates(quote_currency="USD", start_date=date(2001,1,1), end_date=END)
        request.assert_called_once()
        self.assertEqual(request.call_args.kwargs["timeout"], 12)


class EcbHistoricalRateIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.db.close)
        self.history = HistoricalExchangeRateService(self.db)
        huf = ExchangeRateService(self.db).upsert_rate(rate_date=date(2009,5,4), base_currency="EUR",
                                                     quote_currency="HUF", rate=Decimal("390.2500"), source="MNB")
        self.huf_id = huf.id
        self.huf_before = self.snapshot(huf)

    @staticmethod
    def snapshot(row):
        return {column.key:getattr(row,column.key) for column in row.__table__.columns}

    def import_csv(self, body=CSV):
        with patch(HTTP_TARGET, return_value=response(body)):
            return self.history.import_rates(quote_currency="USD", provider=EcbHistoricalRateProvider(), start_date=START, end_date=END)

    def test_real_parser_generic_persistence_exact_values_huf_isolation_and_upserts(self):
        self.assertEqual(self.import_csv(), 2)
        usd = list(self.db.scalars(select(ExchangeRateORM).where(ExchangeRateORM.quote_currency == "USD").order_by(ExchangeRateORM.rate_date)))
        self.assertEqual([(r.base_currency,r.source,r.unit) for r in usd], [("EUR","ECB","1")]*2)
        self.assertEqual([r.rate for r in usd], ["1.1490","1.1750123456789012345678901234567890"])
        before = [self.snapshot(row) for row in usd]
        self.assertEqual(self.import_csv(), 2)
        self.db.expire_all()
        self.assertEqual([self.snapshot(row) for row in usd], before)
        self.assertEqual(self.snapshot(self.db.get(ExchangeRateORM,self.huf_id)), self.huf_before)
        self.assertEqual(len(list(self.db.scalars(select(ExchangeRateORM)))), 3)
        self.import_csv(CSV.replace("1.1490", "1.1500"))
        self.assertEqual(usd[0].rate, "1.1500")
        self.assertEqual(usd[0].id, before[0]["id"])
        self.assertEqual(self.snapshot(self.db.get(ExchangeRateORM,self.huf_id)), self.huf_before)

    def test_valid_empty_import_and_invalid_later_row_do_not_write_partial_data(self):
        self.assertEqual(self.import_csv(HEADER), 0)
        with self.assertRaises(ExchangeRateProviderError) as caught:
            self.import_csv(CSV.replace("1.1750123456789012345678901234567890", "invalid"))
        self.assertIsInstance(caught.exception.__cause__, EcbExchangeRateProviderError)
        self.assertEqual(caught.exception.__cause__.code, "invalid_rate")
        self.assertEqual(len(list(self.db.scalars(select(ExchangeRateORM)))), 1)
        self.assertEqual(self.snapshot(self.db.get(ExchangeRateORM,self.huf_id)), self.huf_before)


if __name__ == "__main__":
    unittest.main()
