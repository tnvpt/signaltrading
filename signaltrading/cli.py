"""CLI with bounded capture duration and deterministic offline replay."""

import argparse
import asyncio
from dataclasses import asdict
import json
import logging
import math
from pathlib import Path

from .core import Scanner, replay
from .ingestion import CaptureConfig, run_capture

LOG = logging.getLogger("signaltrading")


async def collect(symbols, directory, scanner):
    """Compatibility wrapper for continuous collection."""
    return await run_capture(CaptureConfig(tuple(symbols)), directory, scanner, duration=0,
                             on_alert=lambda alert: print(json.dumps(asdict(alert)), flush=True))


async def bounded_collect(args, scanner):
    config = CaptureConfig(tuple(args.symbols), first_trade_timeout=args.first_trade_timeout,
                           stale_timeout=args.stale_timeout, queue_capacity=args.queue_capacity)
    stats = await run_capture(config, args.output, scanner, args.duration,
                              on_alert=lambda alert: print(json.dumps(asdict(alert)), flush=True))
    LOG.info("Capture summary: %s", json.dumps(asdict(stats)))
    if not all(stats.fresh_by_symbol.get(symbol, 0) for symbol in args.symbols):
        LOG.error("Incomplete capture: not all requested symbols delivered fresh trades")
        return 2
    return 0


def main():
    parser = argparse.ArgumentParser(description="Research scanner; alerts are NOT entry signals")
    parser.add_argument("mode", choices=("collect", "replay"))
    parser.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT"])
    parser.add_argument("--output", type=Path, default=Path("data"))
    parser.add_argument("--input", type=Path)
    parser.add_argument("--duration", type=float, default=60, help="Capture seconds; 0 means continuous")
    parser.add_argument("--threshold-pct", type=float, default=2.0)
    parser.add_argument("--first-trade-timeout", type=float, default=10)
    parser.add_argument("--stale-timeout", type=float, default=10)
    parser.add_argument("--queue-capacity", type=int, default=4096)
    args = parser.parse_args()
    if not math.isfinite(args.duration) or args.duration < 0 or not 0 < args.threshold_pct < float("inf"):
        parser.error("Duration must be non-negative; threshold must be finite and positive")
    args.symbols = sorted(set(s.upper() for s in args.symbols))
    if len(args.symbols) > 20 or any(not s.isalnum() or not s.endswith("USDT") for s in args.symbols):
        parser.error("Use up to 20 USDT symbols, e.g. BTCUSDT")
    try:
        CaptureConfig(tuple(args.symbols), first_trade_timeout=args.first_trade_timeout,
                      stale_timeout=args.stale_timeout, queue_capacity=args.queue_capacity)
    except ValueError as exc:
        parser.error(str(exc))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    scanner = Scanner(threshold_pct=args.threshold_pct)
    if args.mode == "replay":
        if args.input is None:
            parser.error("replay requires --input")
        for alert in replay(args.input, scanner):
            print(json.dumps(asdict(alert)))
    else:
        try:
            return asyncio.run(bounded_collect(args, scanner))
        except KeyboardInterrupt:
            LOG.info("Stopped")


if __name__ == "__main__":
    raise SystemExit(main())