"""Run a bounded public capture, then validate all records by replaying them."""

import argparse
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys
import time

# Allows execution from a checkout as well as an installed package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from signaltrading.core import Scanner, replay


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=60)
    args = parser.parse_args()
    if not 1 <= args.duration <= 300:
        parser.error("Diagnostic duration must be 1–300 seconds")
    directory = Path("data") / f"verified-{time.time_ns()}"
    result = subprocess.run(
        [sys.executable, "-m", "signaltrading.cli", "collect", "--duration", str(args.duration),
         "--symbols", "BTCUSDT", "ETHUSDT", "--output", str(directory)],
        capture_output=True, text=True, timeout=args.duration + 30)
    counts, symbols, issues = Counter(), Counter(), Counter()
    ages = []
    live_alerts = []
    replay_alerts = []
    scanner = Scanner()
    summaries = []
    for path in sorted(directory.glob("*.jsonl")):
        for line in path.open(encoding="utf-8"):
            row = json.loads(line)
            counts[row["type"]] += 1
            data = row["data"]
            if row["type"] == "trade":
                symbols[data["symbol"]] += 1
                ages.append(data["received_ms"] - data["event_ms"])
            elif row["type"] == "status":
                issues[data.get("reason", "unknown")] += 1
            elif row["type"] == "alert":
                live_alerts.append(data)
            elif row["type"] == "summary":
                summaries.append(data)
        replay_alerts.extend(asdict(alert) for alert in replay(path, scanner))
    report = {"directory": str(directory.resolve()), "exit_code": result.returncode,
              "counts": dict(counts), "trades_by_symbol": dict(symbols),
              "receive_minus_trade_ms": {"min": min(ages), "max": max(ages)} if ages else None,
              "status_reasons": dict(issues), "summaries": summaries,
              "replay_matches_recorded_alerts": live_alerts == replay_alerts,
              "stdout": result.stdout, "stderr": result.stderr}
    Path("verified-capture-result.txt").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if result.returncode == 0 and symbols["BTCUSDT"] and symbols["ETHUSDT"] and live_alerts == replay_alerts else 1


if __name__ == "__main__":
    raise SystemExit(main())