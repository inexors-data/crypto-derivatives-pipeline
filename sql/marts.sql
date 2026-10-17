-- Staging: one normalized row per funding observation, rate converted to annualized %.
CREATE OR REPLACE VIEW stg_funding AS
SELECT
    exchange,
    symbol,
    asset,
    ts,
    funding_rate,
    interval_hours,
    funding_rate * (24.0 / interval_hours) * 365 * 100 AS funding_apr_pct
FROM raw_funding;

-- Mart: daily average annualized funding per asset and exchange.
CREATE OR REPLACE VIEW mart_funding_daily AS
SELECT
    CAST(ts AS DATE)      AS day,
    asset,
    exchange,
    avg(funding_apr_pct)  AS funding_apr_pct,
    count(*)              AS observations
FROM stg_funding
GROUP BY ALL;

-- Mart: cross-exchange funding spread (basis for funding-arbitrage screening).
CREATE OR REPLACE VIEW mart_funding_spread AS
SELECT
    day,
    asset,
    max(funding_apr_pct) - min(funding_apr_pct)       AS spread_apr_pct,
    arg_max(exchange, funding_apr_pct)                AS richest_exchange,
    arg_min(exchange, funding_apr_pct)                AS cheapest_exchange,
    count(*)                                          AS exchanges
FROM mart_funding_daily
GROUP BY day, asset
HAVING count(*) > 1;

-- Mart: daily implied volatility index next to average funding.
CREATE OR REPLACE VIEW mart_vol_vs_funding AS
SELECT
    d.day,
    d.currency            AS asset,
    d.close               AS dvol,
    avg(f.funding_apr_pct) AS avg_funding_apr_pct
FROM (SELECT CAST(ts AS DATE) AS day, currency, close FROM raw_dvol) d
LEFT JOIN mart_funding_daily f ON f.day = d.day AND f.asset = d.currency
GROUP BY d.day, d.currency, d.close;
