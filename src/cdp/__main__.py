"""CLI: python -m cdp {ingest,check,report,all} [--since YYYY-MM-DD] [--exchanges a,b]"""
import argparse
import logging
import sys

from . import config, pipeline, report, storage


def main(argv=None):
    p = argparse.ArgumentParser(prog="cdp", description="Crypto derivatives public-data pipeline")
    p.add_argument("command", choices=["ingest", "check", "report", "all"])
    p.add_argument("--since", default=config.DEFAULT_SINCE, help="history start for the first load")
    p.add_argument("--exchanges", help=f"comma-separated subset of {config.ENABLED_EXCHANGES + ['bitmex']}")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    con = storage.connect()
    exchanges = args.exchanges.split(",") if args.exchanges else None

    if args.command in ("ingest", "all"):
        print(pipeline.ingest(con, args.since, exchanges).to_string(index=False))
    results = None
    if args.command in ("check", "report", "all"):
        results = pipeline.check(con)
        bad = results[results["status"] != "ok"]
        print(f"\nData quality: {len(results)} checks, {len(bad)} with findings")
        if not bad.empty:
            print(bad[["check_name", "exchange", "symbol", "status", "detail"]].to_string(index=False))
    if args.command in ("report", "all"):
        for path in report.build(con, results):
            print("saved", path.relative_to(config.ROOT))
    con.close()
    return 1 if results is not None and (results["status"] == "fail").any() else 0


if __name__ == "__main__":
    sys.exit(main())
