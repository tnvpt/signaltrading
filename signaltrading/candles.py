"""Closed exchange-candle observation engine. No entry recommendations."""

from collections import deque
from dataclasses import dataclass, asdict
from decimal import Decimal, InvalidOperation
import hashlib


INTERVALS = {"3m": 180_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000}


class CandleGap(ValueError):
    """History is discontinuous and must be re-warmed."""


def integer(value):
    if type(value) is not int or value < 0:
        raise ValueError("Expected non-negative integer")
    return value


def decimal(value):
    if not isinstance(value, str):
        raise ValueError("Expected decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Invalid decimal") from exc
    if not result.is_finite():
        raise ValueError("Non-finite decimal")
    return result


@dataclass(frozen=True)
class Candle:
    symbol: str
    interval: str
    open_ms: int
    close_ms: int  # Exclusive UTC boundary, unlike Binance's inclusive close time.
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self):
        if (not isinstance(self.symbol, str) or not self.symbol.isascii()
                or not self.symbol.isalnum() or self.symbol != self.symbol.upper()):
            raise ValueError("Invalid symbol")
        if self.interval not in INTERVALS:
            raise ValueError("Unsupported interval")
        integer(self.open_ms)
        integer(self.close_ms)
        duration = INTERVALS[self.interval]
        if self.open_ms % duration or self.close_ms != self.open_ms + duration:
            raise ValueError("Invalid candle boundaries")
        for value in (self.open, self.high, self.low, self.close, self.volume):
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError("Invalid OHLCV")
        if (self.low <= 0 or self.volume < 0 or self.low > min(self.open, self.close)
                or self.high < max(self.open, self.close) or self.low > self.high):
            raise ValueError("Inconsistent OHLCV")

    def record(self):
        return {key: str(value) if isinstance(value, Decimal) else value
                for key, value in asdict(self).items()}


def rest_candle(symbol, interval, row):
    if not isinstance(row, list) or len(row) < 7:
        raise ValueError("Malformed REST candle")
    return Candle(symbol, interval, integer(row[0]), integer(row[6]) + 1,
                  *(decimal(row[index]) for index in (1, 2, 3, 4, 5)))


def stream_candle(payload):
    """Return (closed candle or None, exchange event timestamp)."""
    if not isinstance(payload, dict):
        raise ValueError("Expected frame object")
    data = payload.get("data", payload)
    if not isinstance(data, dict) or data.get("e") != "kline":
        raise ValueError("Expected kline frame")
    if data.get("st", 1) != 1:
        raise ValueError("Non-USDM frame")
    k = data.get("k")
    if not isinstance(k, dict) or type(k.get("x")) is not bool:
        raise ValueError("Invalid candle status")
    if data.get("s") != k.get("s"):
        raise ValueError("Symbol mismatch")
    event_ms = integer(data["E"])
    candle = Candle(k["s"], k["i"], integer(k["t"]), integer(k["T"]) + 1,
                    *(decimal(k[key]) for key in ("o", "h", "l", "c", "v")))
    return (candle if k["x"] else None), event_ms


class WilderRSI:
    def __init__(self, period=14):
        self.period = period
        self.previous = None
        self.count = 0
        self.gain = Decimal(0)
        self.loss = Decimal(0)
        self.value = None

    def update(self, close):
        if self.previous is None:
            self.previous = close
            return None
        delta = close - self.previous
        self.previous = close
        gain, loss = max(delta, Decimal(0)), max(-delta, Decimal(0))
        self.count += 1
        if self.count <= self.period:
            self.gain += gain
            self.loss += loss
            if self.count < self.period:
                return None
            self.gain /= self.period
            self.loss /= self.period
        else:
            self.gain = (self.gain * (self.period - 1) + gain) / self.period
            self.loss = (self.loss * (self.period - 1) + loss) / self.period
        self.value = (Decimal(50) if self.gain == self.loss == 0 else Decimal(100)
                      if self.loss == 0 else 100 - 100 / (1 + self.gain / self.loss))
        return self.value


class EMA:
    def __init__(self, period):
        self.period = period
        self.count = 0
        self.total = Decimal(0)
        self.value = None

    def update(self, close):
        self.count += 1
        if self.count <= self.period:
            self.total += close
            if self.count == self.period:
                self.value = self.total / self.period
        else:
            alpha = Decimal(2) / (self.period + 1)
            self.value = alpha * close + (1 - alpha) * self.value
        return self.value


class Series:
    def __init__(self):
        self.last = None
        self.rsi = WilderRSI()
        self.ema50 = EMA(50)
        self.ema200 = EMA(200)
        self.ema50_tail = deque(maxlen=4)
        self.zone = "NEUTRAL"

    def update(self, candle):
        if candle.volume == 0:
            raise CandleGap("Zero-volume candle cannot warm reference features")
        if self.last:
            if candle.open_ms <= self.last.open_ms:
                if candle.open_ms == self.last.open_ms and candle != self.last:
                    raise CandleGap("Conflicting closed candle")
                return False
            if candle.open_ms != self.last.close_ms:
                raise CandleGap("Missing closed candle")
        self.last = candle
        self.rsi.update(candle.close)
        self.ema50_tail.append(self.ema50.update(candle.close))
        self.ema200.update(candle.close)
        return True

    def direction(self, decision_ms):
        if self.last is None or self.last.close_ms > decision_ms:
            return "UNKNOWN"
        if decision_ms - self.last.close_ms > INTERVALS[self.last.interval] + 1000:
            return "UNKNOWN"
        c, e50, e200 = self.last.close, self.ema50.value, self.ema200.value
        if self.last.interval == "1h":
            return "UNKNOWN" if e50 is None else "UP" if c > e50 else "DOWN" if c < e50 else "RANGE"
        if e200 is None or len(self.ema50_tail) < 4 or self.ema50_tail[0] is None:
            return "UNKNOWN"
        if c > e200 and e50 > e200 and e50 > self.ema50_tail[0]:
            return "UP"
        if c < e200 and e50 < e200 and e50 < self.ema50_tail[0]:
            return "DOWN"
        return "RANGE"


class WatchEngine:
    def __init__(self, cooldown_ms=300_000):
        self.series = {}
        self.last_watch = {}
        self.cooldown_ms = cooldown_ms

    def reset_series(self):
        # Preserve cooldown across network reconnect; restart persistence deferred.
        self.series.clear()

    def consume(self, candle, known_ms, *, historical=False):
        if known_ms < candle.close_ms:
            raise ValueError("Candle cannot be known before close")
        key = (candle.symbol, candle.interval)
        series = self.series.setdefault(key, Series())
        if not series.update(candle) or candle.interval not in ("3m", "5m"):
            return None
        rsi = series.rsi.value
        if rsi is None:
            return None
        zone = series.zone
        if zone == "OVERSOLD" and rsi > 35 or zone == "OVERBOUGHT" and rsi < 65:
            zone = "NEUTRAL"
        entered = None
        if zone == "NEUTRAL":
            if rsi <= 30:
                entered = zone = "OVERSOLD"
            elif rsi >= 70:
                entered = zone = "OVERBOUGHT"
        series.zone = zone
        # Backfill updates state but never creates catch-up notifications.
        if historical or entered is None:
            return None
        watch_key = (*key, entered)
        if known_ms - self.last_watch.get(watch_key, -10**18) < self.cooldown_ms:
            return None
        self.last_watch[watch_key] = known_ms
        identity = f"rsi-watch-1|binance_usdm|{key}|{candle.close_ms}|{entered}"
        context = {}
        for interval in ("15m", "1h"):
            context[interval] = self.series.get((candle.symbol, interval), Series()).direction(known_ms)
        return {"observation_id": hashlib.sha256(identity.encode()).hexdigest(),
                "profile": "rsi-watch-1", "source": "binance_usdm", "symbol": candle.symbol,
                "interval": candle.interval, "kind": f"WATCH_{entered}", "rsi": str(rsi),
                "bar_close_ms": candle.close_ms, "decision_ms": known_ms,
                "expires_ms": known_ms + 30_000, "context": context, "actionable": False}