"""Orchestration: incremental ingest -> quality checks -> report."""
import logging
from dataclasses import asdict
from datetime import datetime, timezone

import pandas as pd

from . import config, quality, storage
from .http import ApiError
from .sources import EXCHANGES, Deribit, now_ms, to_ms

log = logging.getLogger(__name__)


def _start_ms(con, table: str, where: dict, since: str) -> int:
    last = storage.last_ts_ms(con, table, where)
    since_ms = to_ms(datetime.fromisoformat(since).replace(tzinfo=timezone.utc))
    return max(last + 1, since_ms) if last else since_ms


def ingest(con, since: str = config.DEFAULT_SINCE, exchanges=None) -> pd.DataFrame:
    """Load only what is missing since the last run for every (exchange, instrument)."""
    exchanges = exchanges or config.ENABLED_EXCHANGES
    end = now_ms()
    stats = []
    for asset, by_exchange in config.INSTRUMENTS.items():
        for name in exchanges:
            symbol = by_exchange[name]
            start = _start_ms(con, "raw_funding", {"exchange": name, "symbol": symbol}, since)
            try:
                df = EXCHANGES[name]().funding(symbol, asset, start, end)
            except ApiError as exc:
                log.error("%s %s: %s", name, symbol, exc)
                stats.append({"dataset": "funding", "exchange": name, "symbol": symbol, "rows": 0, "error": str(exc)[:80]})
                continue
            n = storage.upsert(con, "raw_funding", df, ["exchange", "symbol", "ts"])
            log.info("funding %-8s %-14s +%d rows", name, symbol, n)
            stats.append({"dataset": "funding", "exchange": name, "symbol": symbol, "rows": n, "error": ""})

    deribit = Deribit()
    for cur in config.DVOL_CURRENCIES:
        start = _start_ms(con, "raw_dvol", {"currency": cur}, since)
        df = deribit.dvol(cur, start, end)
        n = storage.upsert(con, "raw_dvol", df, ["currency", "ts"])
        log.info("dvol    %-8s +%d rows", cur, n)
        stats.append({"dataset": "dvol", "exchange": "deribit", "symbol": cur, "rows": n, "error": ""})
    return pd.DataFrame(stats)


def check(con) -> pd.DataFrame:
    df = con.execute("SELECT exchange, symbol, ts, funding_rate, interval_hours FROM raw_funding").df()
    results = pd.DataFrame([asdict(r) for r in quality.run_checks(df)])
    results.insert(0, "run_at", pd.Timestamp.now(tz="UTC"))
    con.register("dq", results)
    con.execute("INSERT INTO dq_results SELECT * FROM dq")
    con.unregister("dq")
    return results
