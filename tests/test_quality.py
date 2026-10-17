import pandas as pd

from cdp import quality
from cdp.sources import parse_bitmex_row


def series(hours, rates=None, exchange="binance", symbol="BTCUSDT", interval=8):
    start = pd.Timestamp.now(tz="UTC").floor("h") - pd.Timedelta(hours=max(hours))
    ts = start + pd.to_timedelta(hours, unit="h")
    return pd.DataFrame({"exchange": exchange, "symbol": symbol, "ts": ts,
                         "funding_rate": rates if rates is not None else [0.0001] * len(hours),
                         "interval_hours": interval})


def statuses(df):
    return {r.check_name: r.status for r in quality.run_checks(df)}


def test_clean_series_passes_all_checks():
    df = series(list(range(0, 80, 8)))
    assert set(statuses(df).values()) == {"ok"}


def test_gap_is_detected_with_missing_count():
    df = series([0, 8, 16, 48, 56])  # 16h -> 48h: three 8h points missing
    msg = quality.check_gaps(df, expected_hours=8)
    assert "1 gaps" in msg and "~3 missing" in msg


def test_duplicates_fail():
    df = series([0, 8, 16])
    df = pd.concat([df, df.iloc[[1]]])
    assert statuses(df)["duplicates"] == "fail"


def test_hard_limit_outlier_fails():
    rates = [0.0001] * 9 + [0.5]  # 50% per period: a unit / parsing error
    assert statuses(series(list(range(0, 80, 8)), rates))["outliers"] == "fail"


def test_extreme_but_plausible_value_warns():
    rates = [0.0001, 0.00012, 0.00009, 0.00011, 0.0001, 0.0001, 0.00008, 0.00012, 0.0001, 0.01]
    assert statuses(series(list(range(0, 80, 8)), rates))["outliers"] == "warn"


def test_stale_series_warns():
    df = series(list(range(0, 80, 8)))
    df["ts"] -= pd.Timedelta(days=3)
    assert statuses(df)["freshness"] == "warn"


def test_bitmex_funding_interval_is_decoded():
    row = {"timestamp": "2026-01-01T04:00:00.000Z", "symbol": "XBTUSDT",
           "fundingInterval": "2000-01-01T08:00:00.000Z", "fundingRate": 0.0001}
    parsed = parse_bitmex_row(row, "BTC")
    assert parsed["interval_hours"] == 8
    assert parsed["ts"] == int(pd.Timestamp("2026-01-01T04:00:00Z").timestamp() * 1000)
