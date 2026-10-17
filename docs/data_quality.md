# Data quality report

Run at: 2026-10-15 17:12 UTC. Checks: 30; ok 29, warn 1, fail 0.

## Coverage

| exchange   | symbol        |   rows | first_day           | last_ts                   |
|:-----------|:--------------|-------:|:--------------------|:--------------------------|
| binance    | BTCUSDT       |   1959 | 2025-01-01 00:00:00 | 2026-10-15 16:00:00+00:00 |
| binance    | ETHUSDT       |   1959 | 2025-01-01 00:00:00 | 2026-10-15 16:00:00+00:00 |
| deribit    | BTC-PERPETUAL |  15665 | 2025-01-01 00:00:00 | 2026-10-15 17:00:00+00:00 |
| deribit    | ETH-PERPETUAL |  15665 | 2025-01-01 00:00:00 | 2026-10-15 17:00:00+00:00 |
| okx        | BTC-USDT-SWAP |    283 | 2026-07-13 00:00:00 | 2026-10-15 16:00:00+00:00 |
| okx        | ETH-USDT-SWAP |    283 | 2026-07-13 00:00:00 | 2026-10-15 16:00:00+00:00 |

## Findings

| check_name   | exchange   | symbol        | status   | detail                                        |
|:-------------|:-----------|:--------------|:---------|:----------------------------------------------|
| outliers     | deribit    | BTC-PERPETUAL | warn     | 4 extreme values (robust z > 10), max 0.0856% |
