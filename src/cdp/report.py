"""Charts and a markdown data-quality report built from the marts."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .config import IMG_DIR, ROOT  # noqa: E402

COLORS = {"binance": "#E8A317", "okx": "#2A6FDB", "deribit": "#16A085", "bitmex": "#C0392B"}


def _style(ax, title, ylabel):
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold")
    ax.set_ylabel(ylabel)
    ax.grid(alpha=0.25)
    ax.spines[["top", "right"]].set_visible(False)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))


def funding_chart(con, asset: str):
    df = con.execute("SELECT day, exchange, funding_apr_pct FROM mart_funding_daily WHERE asset = ? ORDER BY day",
                     [asset]).df()
    wide = df.pivot(index="day", columns="exchange", values="funding_apr_pct").rolling(7, min_periods=3).mean()
    fig, ax = plt.subplots(figsize=(11, 4.5))
    for ex in wide.columns:
        ax.plot(wide.index, wide[ex], label=ex, color=COLORS.get(ex), lw=1.6)
    ax.axhline(0, color="grey", lw=0.8)
    _style(ax, f"{asset} perpetual funding, annualized (7-day rolling mean)", "% APR")
    ax.legend(frameon=False, ncol=4)
    return _save(fig, f"funding_{asset.lower()}.png")


def spread_chart(con):
    df = con.execute("SELECT day, asset, spread_apr_pct FROM mart_funding_spread ORDER BY day").df()
    fig, ax = plt.subplots(figsize=(11, 4))
    for asset, g in df.groupby("asset"):
        ax.plot(g["day"], g["spread_apr_pct"].rolling(7, min_periods=3).mean(), label=asset, lw=1.6)
    _style(ax, "Cross-exchange funding spread, max minus min (7-day rolling)", "% APR")
    ax.legend(frameon=False)
    return _save(fig, "funding_spread.png")


def dvol_chart(con):
    df = con.execute("SELECT day, asset, dvol, avg_funding_apr_pct FROM mart_vol_vs_funding ORDER BY day").df()
    fig, axes = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True)
    for ax, (asset, g) in zip(axes, df.groupby("asset")):
        ax.plot(g["day"], g["dvol"], color="#6C3483", lw=1.6, label="DVOL (implied vol)")
        _style(ax, f"{asset}: Deribit DVOL vs average funding", "DVOL")
        ax2 = ax.twinx()
        ax2.plot(g["day"], g["avg_funding_apr_pct"].rolling(7, min_periods=3).mean(),
                 color="#E8A317", lw=1.2, alpha=0.9, label="funding, % APR (7d)")
        ax2.set_ylabel("% APR")
        ax2.spines[["top"]].set_visible(False)
        lines = ax.get_lines() + ax2.get_lines()
        ax.legend(lines, [l.get_label() for l in lines], frameon=False, loc="upper left")
    return _save(fig, "dvol_vs_funding.png")


def _save(fig, name):
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    path = IMG_DIR / name
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def dq_markdown(results: pd.DataFrame, con) -> str:
    coverage = con.execute("""
        SELECT exchange, symbol, count(*) AS rows, min(ts)::DATE AS first_day, max(ts) AS last_ts
        FROM raw_funding GROUP BY ALL ORDER BY exchange, symbol
    """).df()
    issues = results[results["status"] != "ok"][["check_name", "exchange", "symbol", "status", "detail"]]
    summary = results["status"].value_counts().to_dict()
    lines = [
        "# Data quality report",
        "",
        f"Run at: {results['run_at'].iloc[0]:%Y-%m-%d %H:%M} UTC. "
        f"Checks: {len(results)}; ok {summary.get('ok', 0)}, warn {summary.get('warn', 0)}, fail {summary.get('fail', 0)}.",
        "",
        "## Coverage",
        "",
        coverage.to_markdown(index=False),
        "",
        "## Findings",
        "",
        issues.to_markdown(index=False) if not issues.empty else "No issues found.",
        "",
    ]
    text = "\n".join(lines)
    (ROOT / "docs" / "data_quality.md").write_text(text, encoding="utf-8")
    return text


def build(con, results: pd.DataFrame) -> list:
    paths = [funding_chart(con, a) for a in ("BTC", "ETH")]
    paths += [spread_chart(con), dvol_chart(con)]
    dq_markdown(results, con)
    return paths
