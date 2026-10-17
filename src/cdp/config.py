from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "derivatives.duckdb"
SQL_DIR = ROOT / "sql"
IMG_DIR = ROOT / "docs" / "img"

DEFAULT_SINCE = "2025-01-01"

# asset -> exchange -> instrument symbol on that exchange
INSTRUMENTS = {
    "BTC": {"deribit": "BTC-PERPETUAL", "binance": "BTCUSDT", "okx": "BTC-USDT-SWAP", "bitmex": "XBTUSDT"},
    "ETH": {"deribit": "ETH-PERPETUAL", "binance": "ETHUSDT", "okx": "ETH-USDT-SWAP", "bitmex": "ETHUSDT"},
}

# BitMEX is off by default: it returns HTTP 403 from some regions.
ENABLED_EXCHANGES = ["deribit", "binance", "okx"]

DVOL_CURRENCIES = ["BTC", "ETH"]

# Expected spacing between funding records, used by the gap check.
# Deribit publishes hourly samples; for the others it is the funding interval.
SAMPLE_STEP_HOURS = {"deribit": 1}
