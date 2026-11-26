"""Deterministic parsing, freshness checks and event-time scanning."""

from collections import deque
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
import math
from pathlib import Path


@dataclass(frozen=True)
class Trade:
    symbol: str
    trade_id: int
    event_ms: int
    received_ms: int
    price: float
    quantity: float
    aggressor: str

    def __post_init__(self):
        if not isinstance(self.symbol, str) or not self.symbol.isascii() or not self.symbol.isalnum():
            raise ValueError("Invalid trade symbol")
        for name in ("trade_id", "event_ms", "received_ms"):
            value = getattr(self, name)
            if type(value) is not int or value < (0 if name == "trade_id" else 1):
                raise ValueError(f"Invalid {name}")
        for value in (self.price, self.quantity):
            if type(value) not in (float, int) or not math.isfinite(value) or value <= 0:
                raise ValueError("Price and quantity must be finite and positive")
        if self.aggressor not in ("buy", "sell"):
            raise ValueError("Invalid aggressor")


def parse_trade(payload: dict, received_ms: int) -> Trade:
    if not isinstance(payload, dict):
        raise ValueError("Expected object frame")
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        raise ValueError("Expected object payload")
    if data.get("e") != "aggTrade":
        raise ValueError("Expected Binance aggTrade event")
    try:
        price, quantity = float(Decimal(data["p"])), float(Decimal(data["q"]))
        if not all(math.isfinite(x) and x > 0 for x in (price, quantity)):
            raise ValueError("Price and quantity must be finite and positive")
        if type(data["m"]) is not bool:
            raise ValueError("Invalid maker flag")
        symbol = data["s"]
        if not isinstance(symbol, str) or not symbol.isalnum():
            raise ValueError("Invalid symbol")
        if type(data["a"]) is not int or type(data["T"]) is not int:
            raise ValueError("Expected integer ID and timestamp")
        trade_id, event_ms = data["a"], data["T"]
        if trade_id < 0 or event_ms <= 0:
            raise ValueError("Invalid ID or timestamp")
        return Trade(symbol.upper(), trade_id, event_ms, received_ms,
                     price, quantity, "sell" if data["m"] else "buy")
    except (KeyError, TypeError, InvalidOperation, OverflowError) as exc:
        raise ValueError("Malformed aggregate trade") from exc


@dataclass(frozen=True)
class Alert:
    symbol: str
    event_ms: int
    window_seconds: int
    change_pct: float
    quote_volume: float
    kind: str
    actionable: bool = False


class Scanner:
    """Fixed-threshold baseline, not an adaptive model or entry strategy.

    Requires continuous fresh observations for a full window. Gaps, stale
    data and out-of-order events invalidate the symbol's observation history.
    """

    def __init__(self, windows=(30, 60, 180), threshold_pct=2.0,
                 max_age_ms=3000, max_gap_ms=10000, cooldown_ms=60000):
        if not windows or any(type(w) is not int or w <= 0 for w in windows):
            raise ValueError("Windows must be positive")
        if (not math.isfinite(threshold_pct) or threshold_pct <= 0 or max_age_ms <= 0
                or max_gap_ms <= 0 or cooldown_ms < 0):
            raise ValueError("Invalid scanner limits")
        self.windows = tuple(sorted(set(windows)))
        self.threshold_pct = threshold_pct
        self.max_age_ms = max_age_ms
        self.max_gap_ms = max_gap_ms
        self.cooldown_ms = cooldown_ms
        self.history = {}
        self.last_alert = {}
        self.last_issue = None

    def reset(self):
        self.history.clear()
        self.last_alert.clear()
        self.last_issue = None

    def consume(self, trade: Trade) -> list[Alert]:
        self.last_issue = None
        age = trade.received_ms - trade.event_ms
        if age > self.max_age_ms or age < -1000:
            self.history.pop(trade.symbol, None)
            self.last_issue = "stale_or_clock_skew"
            return []
        queue = self.history.setdefault(trade.symbol, deque())
        if queue:
            previous = queue[-1]
            if trade.trade_id == previous.trade_id:
                return []
            if trade.trade_id < previous.trade_id or trade.event_ms < previous.event_ms:
                queue.clear()
                self.last_issue = "out_of_order"
                return []
            if trade.trade_id != previous.trade_id + 1 or trade.event_ms - previous.event_ms > self.max_gap_ms:
                queue.clear()
                self.last_issue = "observation_gap"
        queue.append(trade)
        cutoff = trade.event_ms - max(self.windows) * 1000
        # Keep a predecessor to measure the price at a window boundary.
        while len(queue) > 1 and queue[1].event_ms <= cutoff:
            queue.popleft()
        alerts = []
        for seconds in self.windows:
            start = trade.event_ms - seconds * 1000
            if queue[0].event_ms > start:
                continue
            baseline = queue[0]
            volume = 0.0
            for item in queue:
                if item.event_ms <= start:
                    baseline = item
                else:
                    volume += item.price * item.quantity
            change = (trade.price / baseline.price - 1) * 100
            if abs(change) < self.threshold_pct:
                continue
            kind = "pump_watch" if change > 0 else "dump_watch"
            key = (trade.symbol, seconds, kind)
            if trade.event_ms - self.last_alert.get(key, -10**18) < self.cooldown_ms:
                continue
            self.last_alert[key] = trade.event_ms
            alerts.append(Alert(trade.symbol, trade.event_ms, seconds, change, volume, kind))
        return alerts


class Recorder:
    """Append-only, UTC-daily JSONL. Close on exit; retention managed externally."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.handle = None
        self.day = None

    def write(self, kind: str, value: dict, received_ms: int):
        from datetime import datetime, timezone
        day = datetime.fromtimestamp(received_ms / 1000, timezone.utc).strftime("%Y-%m-%d")
        if day != self.day:
            self.close()
            self.handle = (self.directory / f"{day}.jsonl").open("a", encoding="utf-8")
            self.day = day
        row = {"schema_version": 1, "source": "binance_usdm", "type": kind,
               "received_ms": received_ms, "data": value}
        self.handle.write(json.dumps(row, allow_nan=False) + "\n")
        self.handle.flush()

    def close(self):
        if self.handle is not None:
            self.handle.close()
            self.handle = None
            self.day = None


def replay(path: Path, scanner: Scanner):
    """Replays recorded arrival order and original freshness, never wall clock."""
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("Expected object record")
                if row["schema_version"] != 1 or row["source"] != "binance_usdm":
                    raise ValueError("Unsupported schema/source")
                if row["type"] == "status":
                    if row["data"].get("reset_scanner", True):
                        scanner.reset()
                elif row["type"] == "trade":
                    trade = Trade(**row["data"])
                    if row["received_ms"] != trade.received_ms:
                        raise ValueError("Envelope/trade timestamp mismatch")
                    yield from scanner.consume(trade)
                elif row["type"] not in ("alert", "session", "summary", "diagnostic"):
                    raise ValueError("Unknown record type")
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                raise ValueError(f"Invalid record at line {number}: {exc}") from exc