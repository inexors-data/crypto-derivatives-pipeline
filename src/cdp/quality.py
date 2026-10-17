"""Data-quality checks for funding series. Pure functions over DataFrames, so they are unit-testable."""
from dataclasses import dataclass

import pandas as pd

from .config import SAMPLE_STEP_HOURS

# Exchanges cap funding per period far below this; anything above is a parsing / unit error.
HARD_LIMIT_PER_PERIOD = 0.05
ROBUST_Z_WARN = 10.0
MAD_FLOOR = 0.00005  # 0.005% per period, a typical baseline funding move


@dataclass
class CheckResult:
    check_name: str
    exchange: str
    symbol: str
    status: str  # ok / warn / fail
    detail: str


def check_duplicates(df: pd.DataFrame) -> str | None:
    dupes = df.duplicated(["exchange", "symbol", "ts"]).sum()
    return f"{dupes} duplicate rows" if dupes else None


def check_gaps(df: pd.DataFrame, expected_hours: float, tolerance: float = 1.5) -> str | None:
    ts = df["ts"].sort_values()
    step = ts.diff().dt.total_seconds() / 3600
    gaps = step[step > expected_hours * tolerance]
    if gaps.empty:
        return None
    missing = int((gaps / expected_hours).round().sum() - len(gaps))
    worst = ts.loc[gaps.idxmax()]
    return f"{len(gaps)} gaps, ~{missing} missing points, largest {gaps.max():.0f}h ending {worst:%Y-%m-%d %H:%M}"


def check_monotonic_and_future(df: pd.DataFrame) -> str | None:
    future = (df["ts"] > pd.Timestamp.now(tz="UTC") + pd.Timedelta(minutes=5)).sum()
    return f"{future} timestamps in the future" if future else None


def check_outliers(df: pd.DataFrame) -> tuple[str, str] | None:
    rate = df["funding_rate"]
    hard = (rate.abs() > HARD_LIMIT_PER_PERIOD).sum()
    if hard:
        return "fail", f"{hard} values above hard limit {HARD_LIMIT_PER_PERIOD:.0%} per period"
    # Floor the MAD: series that sit near zero most of the time (e.g. Deribit) would
    # otherwise flag every ordinary move as extreme.
    mad = max((rate - rate.median()).abs().median(), MAD_FLOOR)
    z =0.6745 * (rate - rate.median()).abs() / mad  # robust z-score (MAD based)
    n = (z > ROBUST_Z_WARN).sum()
    return ("warn", f"{n} extreme values (robust z > {ROBUST_Z_WARN:g}), max {rate.abs().max():.4%}") if n else None


def check_freshness(df: pd.DataFrame, expected_hours: float) -> str | None:
    lag = (pd.Timestamp.now(tz="UTC") - df["ts"].max()).total_seconds() / 3600
    return f"last record {lag:.0f}h ago" if lag > expected_hours * 2 + 1 else None


def run_checks(df: pd.DataFrame) -> list[CheckResult]:
    results = []
    for (exchange, symbol), g in df.groupby(["exchange", "symbol"]):
        expected = SAMPLE_STEP_HOURS.get(exchange, g["interval_hours"].median())

        def add(name, outcome, fail_status="fail"):
            if outcome is None:
                results.append(CheckResult(name, exchange, symbol, "ok", ""))
            elif isinstance(outcome, tuple):
                results.append(CheckResult(name, exchange, symbol, *outcome))
            else:
                results.append(CheckResult(name, exchange, symbol, fail_status, outcome))

        add("duplicates", check_duplicates(g))
        add("gaps", check_gaps(g, expected), fail_status="warn")
        add("future_timestamps", check_monotonic_and_future(g))
        add("outliers", check_outliers(g))
        add("freshness", check_freshness(g, expected), fail_status="warn")
    return results
