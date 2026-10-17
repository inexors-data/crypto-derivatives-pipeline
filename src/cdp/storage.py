"""DuckDB storage: idempotent upserts into raw tables, SQL views on top (staging -> marts)."""
import duckdb
import pandas as pd

from .config import DB_PATH, SQL_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_funding (
    exchange       VARCHAR NOT NULL,
    symbol         VARCHAR NOT NULL,
    asset          VARCHAR NOT NULL,
    ts             TIMESTAMPTZ NOT NULL,
    funding_rate   DOUBLE NOT NULL,
    interval_hours DOUBLE NOT NULL,
    loaded_at      TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (exchange, symbol, ts)
);
CREATE TABLE IF NOT EXISTS raw_dvol (
    currency  VARCHAR NOT NULL,
    ts        TIMESTAMPTZ NOT NULL,
    open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE,
    loaded_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (currency, ts)
);
CREATE TABLE IF NOT EXISTS dq_results (
    run_at   TIMESTAMPTZ,
    check_name VARCHAR, exchange VARCHAR, symbol VARCHAR,
    status   VARCHAR,   -- ok / warn / fail
    detail   VARCHAR
);
"""


def connect(path=DB_PATH) -> duckdb.DuckDBPyConnection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    con.execute("SET TimeZone = 'UTC'")
    con.execute(SCHEMA)
    con.execute((SQL_DIR / "marts.sql").read_text(encoding="utf-8"))
    return con


def upsert(con, table: str, df: pd.DataFrame, key: list[str]) -> int:
    """Insert new rows, overwrite existing ones with the same key. Safe to re-run."""
    if df.empty:
        return 0
    df = df.drop_duplicates(key, keep="last")
    con.register("incoming", df)
    cols = ", ".join(df.columns)
    updates = ", ".join(f"{c} = excluded.{c}" for c in df.columns if c not in key)
    con.execute(f"""
        INSERT INTO {table} ({cols}) SELECT {cols} FROM incoming
        ON CONFLICT ({", ".join(key)}) DO UPDATE SET {updates}, loaded_at = now()
    """)
    con.unregister("incoming")
    return len(df)


def last_ts_ms(con, table: str, where: dict) -> int | None:
    """Latest loaded timestamp for a series, used for incremental loads."""
    cond = " AND ".join(f"{k} = ?" for k in where)
    row = con.execute(f"SELECT epoch_ms(max(ts)) FROM {table} WHERE {cond}", list(where.values())).fetchone()
    return row[0]
