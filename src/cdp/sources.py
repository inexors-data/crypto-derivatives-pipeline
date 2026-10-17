"""Public-API extractors. Each funding extractor returns a DataFrame with the unified schema:

    exchange, symbol, asset, ts (UTC), funding_rate (per funding period), interval_hours

No API keys are needed: every endpoint used here is public market data.
"""
from datetime import datetime, timezone

import pandas as pd

from .http import HttpClient

FUNDING_COLUMNS = ["exchange", "symbol", "asset", "ts", "funding_rate", "interval_hours"]
HOUR_MS = 3_600_000


def to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def now_ms() -> int:
    return to_ms(datetime.now(timezone.utc))


def _frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=FUNDING_COLUMNS)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df["funding_rate"] = df["funding_rate"].astype(float)
    return df


# ---------------------------------------------------------------- Deribit
class Deribit:
    """Deribit perpetuals accrue funding continuously; the API returns hourly samples
    of the 8h-equivalent rate (interest_8h)."""

    name = "deribit"
    window_hours = 744  # API returns at most ~one month of hourly points per request

    def __init__(self):
        self.http = HttpClient("https://www.deribit.com/api/v2", min_interval=0.05)

    def perpetuals(self) -> list[str]:
        result = self.http.get("public/get_instruments", {"kind": "future"})["result"]
        return sorted(i["instrument_name"] for i in result if i["settlement_period"] == "perpetual")

    def funding(self, symbol: str, asset: str, start_ms: int, end_ms: int) -> pd.DataFrame:
        rows = []
        window_start = start_ms
        while window_start < end_ms:
            window_end = min(window_start + self.window_hours * HOUR_MS, end_ms)
            data = self.http.get("public/get_funding_rate_history", {
                "instrument_name": symbol, "start_timestamp": window_start, "end_timestamp": window_end,
            })["result"]
            rows += [{"exchange": self.name, "symbol": symbol, "asset": asset, "ts": r["timestamp"],
                      "funding_rate": r["interest_8h"], "interval_hours": 8} for r in data]
            window_start = window_end + 1
        return _frame(rows)

    def dvol(self, currency: str, start_ms: int, end_ms: int, resolution: str = "1D") -> pd.DataFrame:
        """Deribit Volatility Index candles. Pages backwards using the `continuation` cursor."""
        candles, cursor = [], end_ms
        while cursor and cursor > start_ms:
            res = self.http.get("public/get_volatility_index_data", {
                "currency": currency, "start_timestamp": start_ms, "end_timestamp": cursor,
                "resolution": resolution,
            })["result"]
            candles += res["data"]
            cursor = res.get("continuation")
        df = pd.DataFrame(candles, columns=["ts", "open", "high", "low", "close"])
        df.insert(0, "currency", currency)
        df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        return df.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)


# ---------------------------------------------------------------- Binance USD-M
class Binance:
    name = "binance"
    page_limit = 1000

    def __init__(self):
        self.http = HttpClient("https://fapi.binance.com", min_interval=0.1)

    def funding(self, symbol: str, asset: str, start_ms: int, end_ms: int) -> pd.DataFrame:
        rows, cursor = [], start_ms
        while cursor < end_ms:
            page = self.http.get("fapi/v1/fundingRate", {
                "symbol": symbol, "startTime": cursor, "endTime": end_ms, "limit": self.page_limit,
            })
            if not page:
                break
            rows += [{"exchange": self.name, "symbol": symbol, "asset": asset, "ts": r["fundingTime"],
                      "funding_rate": r["fundingRate"], "interval_hours": 8} for r in page]
            if len(page) < self.page_limit:
                break
            cursor = page[-1]["fundingTime"] + 1
        df = _frame(rows)
        # Binance moves some symbols to 4h/1h funding; derive the real interval from the data.
        return _infer_interval(df)


# ---------------------------------------------------------------- OKX
class Okx:
    """OKX keeps roughly the last 3 months of funding history on the public endpoint."""

    name = "okx"
    page_limit = 100

    def __init__(self):
        self.http = HttpClient("https://www.okx.com", min_interval=0.25)  # 10 req / 2s limit

    def funding(self, symbol: str, asset: str, start_ms: int, end_ms: int) -> pd.DataFrame:
        rows, cursor = [], end_ms + 1
        while True:
            # `after` returns records older than the given timestamp -> page backwards in time.
            data = self.http.get("api/v5/public/funding-rate-history", {
                "instId": symbol, "after": cursor, "limit": self.page_limit,
            })["data"]
            data = [r for r in data if int(r["fundingTime"]) >= start_ms]
            if not data:
                break
            rows += [{"exchange": self.name, "symbol": symbol, "asset": asset, "ts": int(r["fundingTime"]),
                      "funding_rate": r["realizedRate"] or r["fundingRate"], "interval_hours": 8} for r in data]
            cursor = int(data[-1]["fundingTime"])
        return _infer_interval(_frame(rows))


# ---------------------------------------------------------------- BitMEX
class Bitmex:
    """Public endpoint, no signature required. Note: BitMEX geo-blocks some regions (HTTP 403)."""

    name = "bitmex"
    page_limit = 500

    def __init__(self):
        self.http = HttpClient("https://www.bitmex.com/api/v1", min_interval=1.0)

    def funding(self, symbol: str, asset: str, start_ms: int, end_ms: int) -> pd.DataFrame:
        rows, cursor = [], start_ms
        end_iso = datetime.fromtimestamp(end_ms / 1000, timezone.utc).isoformat()
        while True:
            page = self.http.get("funding", {
                "symbol": symbol, "count": self.page_limit, "reverse": "false",
                "startTime": datetime.fromtimestamp(cursor / 1000, timezone.utc).isoformat(), "endTime": end_iso,
            })
            if not page:
                break
            rows += [parse_bitmex_row(r, asset) for r in page]
            if len(page) < self.page_limit:
                break
            cursor = rows[-1]["ts"] + 1
        return _frame(rows)


def parse_bitmex_row(r: dict, asset: str) -> dict:
    # fundingInterval is encoded as a datetime offset from 2000-01-01, e.g. "2000-01-01T08:00:00.000Z" = 8h
    interval = pd.Timestamp(r["fundingInterval"]) - pd.Timestamp("2000-01-01", tz="UTC")
    return {"exchange": "bitmex", "symbol": r["symbol"], "asset": asset,
            "ts": int(pd.Timestamp(r["timestamp"]).timestamp() * 1000),
            "funding_rate": r["fundingRate"], "interval_hours": interval.total_seconds() / 3600}


def _infer_interval(df: pd.DataFrame) -> pd.DataFrame:
    """Set interval_hours from the median spacing between consecutive funding events."""
    if len(df) > 2:
        step = df.sort_values("ts")["ts"].diff().median()
        df["interval_hours"] = round(step.total_seconds() / 3600, 2)
    return df


EXCHANGES = {cls.name: cls for cls in (Deribit, Binance, Okx, Bitmex)}
