"""Review a saved Futures alert using only candles available at decision time."""

import argparse
from decimal import Decimal
import json
from pathlib import Path
import shutil
from statistics import median
import subprocess

from .candles import INTERVALS


def records(path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            # The running recorder may still be writing the last line.
            if not line.endswith("\n"):
                break
            yield json.loads(line)


def review_case(path, symbol=None):
    watch = None
    for row in records(path):
        if row["type"] == "watch" and (symbol is None or row["data"]["symbol"] == symbol):
            watch = row["data"]
    if watch is None:
        raise ValueError("No matching watch alert in this log")

    window = 20
    interval = watch["interval"]
    step = INTERVALS[interval]
    close_ms = watch["bar_close_ms"]
    bars = {}
    for row in records(path):
        if row["type"] == "watch" and row["data"]["observation_id"] == watch["observation_id"]:
            break
        if row["received_ms"] > watch["decision_ms"]:
            continue
        if row["type"] == "closed_analysis":
            candle = row["data"]["candle"]
        elif row["type"] == "kline_history":
            candle = row["data"]
        else:
            continue
        end = candle["close_ms"]
        if (candle["symbol"] == watch["symbol"] and candle["interval"] == interval
                and close_ms - window * step <= end <= close_ms):
            bars[end] = candle

    boundaries = range(close_ms - window * step, close_ms + 1, step)
    if any(end not in bars for end in boundaries):
        raise ValueError("The alert lacks 20 consecutive prior candles and its closed signal candle")
    history = [bars[end] for end in boundaries]
    prior, signal = history[:-1], history[-1]
    baseline = median(Decimal(candle["volume"]) for candle in prior)
    high, low, close = (Decimal(signal[key]) for key in ("high", "low", "close"))
    prior_high = max(Decimal(candle["high"]) for candle in prior)
    prior_low = min(Decimal(candle["low"]) for candle in prior)
    median_range = median(Decimal(candle["high"]) - Decimal(candle["low"]) for candle in prior)
    return {
        "alert": watch,
        "signal_range_vs_prior_20_median": (
            str(round((high - low) / median_range, 3)) if median_range else None
        ),
        "signal_close_location_pct": str(round(100 * (close - low) / (high - low), 1)) if high > low else None,
        "signal_close_vs_prior_range": "ABOVE" if close > prior_high else "BELOW" if close < prior_low else "INSIDE",
        "signal_volume_vs_prior_20_median": (
            str(round(Decimal(signal["volume"]) / baseline, 3)) if baseline else None
        ),
        "prior_20_high": str(prior_high),
        "prior_20_low": str(prior_low),
        "closed_candles": history,
    }


def replay_confirmation(path, case, horizon):
    """Check which signal-candle boundary broke first on consecutive live-recorded closes."""
    watch = case["alert"]
    signal = case["closed_candles"][-1]
    upper, lower = Decimal(signal["high"]), Decimal(signal["low"])
    signal_close = Decimal(signal["close"])
    step = INTERVALS[watch["interval"]]
    origin = watch["bar_close_ms"]
    seen = {}
    for row in records(path):
        if row["type"] != "closed_analysis" or row["received_ms"] <= watch["decision_ms"]:
            continue
        candle = row["data"]["candle"]
        if candle["symbol"] != watch["symbol"] or candle["interval"] != watch["interval"]:
            continue
        end = candle["close_ms"]
        if origin < end <= origin + horizon * step:
            seen.setdefault(end, Decimal(candle["close"]))

    closes = []
    for end in range(origin + step, origin + (horizon + 1) * step, step):
        if end not in seen:
            break
        closes.append(seen[end])
    first_break = None
    for number, close in enumerate(closes, 1):
        if close > upper or close < lower:
            first_break = {"direction": "UP" if close > upper else "DOWN",
                           "bars_after_alert": number, "close": str(close)}
            break
    return {
        "requested_bars": horizon,
        "consecutive_live_closes": len(closes),
        "complete": len(closes) == horizon,
        "first_signal_range_break": first_break,
        "last_observed_close_change_pct": (
            str(round(100 * (closes[-1] / signal_close - 1), 3)) if closes else None
        ),
    }


def make_prompt(case):
    return (
        "Reply in Vietnamese in at most 180 words. Analyze this historical Binance USD-M Futures RSI alert "
        "using only the supplied data as of decision_ms. Do not use external data or later prices. "
        "Compare continuation, reversal and waiting. Weigh relative volume, range expansion, "
        "where the signal closed within its candle (0=low, 100=high), and whether it broke the prior range. "
        "For each supported scenario give a concrete future closed-candle confirmation and "
        "invalidation level. If neither direction has enough evidence, say to wait. "
        "Distinguish conditions to test from confirmed entries. This case has no bid-ask, "
        "funding or open interest data. Do not invent them or recommend leverage.\n"
        + json.dumps(case, ensure_ascii=False, separators=(",", ":"))
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="One candle-watch JSONL log")
    parser.add_argument("--symbol", type=str.upper, help="Select the latest alert for this pair")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--replay", type=int, choices=range(1, 25), metavar="1-24",
                      help="Locally check the next N consecutive live-recorded candle closes")
    mode.add_argument("--run", action="store_true", help="Send this case through the connected ChatGPT account")
    args = parser.parse_args()
    try:
        case = review_case(args.input, args.symbol)
        if args.replay is not None:
            print(json.dumps(replay_confirmation(args.input, case, args.replay), indent=2))
            return 0
        prompt = make_prompt(case)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if not args.run:
        print(prompt)
        return 0

    cli = shutil.which("tradingagents") or Path.home() / ".local/bin/tradingagents"
    try:
        result = subprocess.run(
            [
                str(cli), "--model", "chatgpt/gpt-6-luna", "--reasoning", "low",
                "-p", prompt, "--limit", "question.time=45s",
                "--limit", "question.steps=4", "--limit", "output.finalTokens=600",
            ],
            timeout=60, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        parser.exit(2, "TradingAgents could not start or exceeded 60 seconds.\n")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
