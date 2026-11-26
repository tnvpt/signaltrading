"""Public Binance aggregate-trade ingestion with explicit health and audit."""

import asyncio
from dataclasses import asdict, dataclass, field
import hashlib
import json
import logging
import math
from pathlib import Path
import random
import time
import uuid

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake

from .core import Scanner, parse_trade
from .storage import AsyncRecorder

LOG = logging.getLogger("signaltrading")
# Binance's current SDK routes aggregate trades to the market connection.
BASE_URL = "wss://fstream.binance.com/market/stream?streams="


def build_trade_url(symbols):
    return BASE_URL + "/".join(f"{symbol.lower()}@aggTrade" for symbol in symbols)


class StreamUnavailable(RuntimeError):
    """Handshake alone is insufficient, or a required symbol has gone quiet."""


@dataclass(frozen=True)
class CaptureConfig:
    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT")
    first_trade_timeout: float = 10
    stale_timeout: float = 10
    watchdog_interval: float = 0.25
    queue_capacity: int = 4096
    retry_base: float = 1

    def __post_init__(self):
        if (not self.symbols or len(self.symbols) > 20 or len(set(self.symbols)) != len(self.symbols)
                or any(not isinstance(s, str) or not s.isascii() or not s.isalnum()
                       or s != s.upper() or not s.endswith("USDT") for s in self.symbols)):
            raise ValueError("Expected 1–20 unique uppercase USDT symbols")
        if any(not math.isfinite(x) or x <= 0 for x in (
                self.first_trade_timeout, self.stale_timeout, self.watchdog_interval, self.retry_base)):
            raise ValueError("Capture timeouts must be finite and positive")
        if type(self.queue_capacity) is not int or self.queue_capacity <= 0:
            raise ValueError("Queue capacity must be a positive integer")


@dataclass
class CaptureStats:
    frames: int = 0
    parsed_trades: int = 0
    fresh_trades: int = 0
    malformed_frames: int = 0
    rejected_symbols: int = 0
    data_issues: int = 0
    reconnects: int = 0
    alerts: int = 0
    fresh_by_symbol: dict = field(default_factory=dict)
    state: str = "WARMING_UP"
    last_reason: str | None = None
    last_disconnect_reason: str | None = None


async def capture_session(url, config, scanner, writer, stats, on_alert=None):
    """One connection. A symbol-level watchdog runs even when no frames arrive."""
    last_seen = {}
    started = time.monotonic()
    diagnostic_written = False

    def status(state, reason, reset=True, **extra):
        stats.state, stats.last_reason = state, reason
        if reset:
            scanner.reset()
        writer.submit("status", {"state": state, "reason": reason,
                                 "reset_scanner": reset, **extra}, time.time_ns() // 1_000_000)

    status("WARMING_UP", "connecting")
    async with connect(url, open_timeout=15, close_timeout=2, ping_interval=None,
                       max_queue=32, max_size=1_048_576) as socket:
        started = time.monotonic()
        LOG.info("WebSocket handshake complete; waiting for valid trades")

        async def receive():
            nonlocal diagnostic_written
            async for message in socket:
                received = time.time_ns() // 1_000_000
                stats.frames += 1
                try:
                    payload = json.loads(message)
                    if isinstance(payload, dict) and "code" in payload:
                        raise StreamUnavailable(f"exchange_error: {str(payload)[:256]}")
                    trade = parse_trade(payload, received)
                except (ValueError, TypeError, UnicodeError) as exc:
                    stats.malformed_frames += 1
                    # No raw-frame flood: one bounded diagnostic per connection.
                    if not diagnostic_written:
                        writer.submit("diagnostic", {"reason": str(exc)[:256],
                                                     "frame_preview": str(message)[:256]}, received)
                        diagnostic_written = True
                    status("DEGRADED", "malformed_frame")
                    continue
                if trade.symbol not in config.symbols:
                    stats.rejected_symbols += 1
                    status("DEGRADED", "unexpected_symbol")
                    continue
                stats.parsed_trades += 1
                writer.submit("trade", asdict(trade), received)
                alerts = scanner.consume(trade)
                if scanner.last_issue:
                    stats.data_issues += 1
                    last_seen.pop(trade.symbol, None)
                    status("DEGRADED", scanner.last_issue)
                    continue
                last_seen[trade.symbol] = time.monotonic()
                stats.fresh_trades += 1
                stats.fresh_by_symbol[trade.symbol] = stats.fresh_by_symbol.get(trade.symbol, 0) + 1
                # HEALTHY describes transport freshness, not strategy warmup.
                if len(last_seen) == len(config.symbols) and stats.state != "HEALTHY":
                    status("HEALTHY", "all_symbols_fresh", reset=False)
                    LOG.info("All requested symbols delivering fresh trades")
                for alert in alerts:
                    stats.alerts += 1
                    writer.submit("alert", asdict(alert), received)
                    if on_alert is not None:
                        on_alert(alert)
            raise StreamUnavailable("stream_closed")

        async def watchdog():
            while True:
                await asyncio.sleep(config.watchdog_interval)
                now = time.monotonic()
                for symbol in config.symbols:
                    if symbol not in last_seen:
                        if now - started >= config.first_trade_timeout:
                            raise StreamUnavailable(f"first_valid_trade_timeout:{symbol}")
                    elif now - last_seen[symbol] >= config.stale_timeout:
                        raise StreamUnavailable(f"stale_symbol:{symbol}")

        receiver = asyncio.create_task(receive(), name="market-receiver")
        guard = asyncio.create_task(watchdog(), name="market-watchdog")
        try:
            done, _ = await asyncio.wait((receiver, guard, writer.task),
                                         return_when=asyncio.FIRST_COMPLETED)
            for task in (writer.task, guard, receiver):
                if task in done:
                    task.result()
            raise StreamUnavailable("session_task_stopped")
        finally:
            receiver.cancel()
            guard.cancel()
            await asyncio.gather(receiver, guard, return_exceptions=True)


async def run_capture(config: CaptureConfig, directory: Path, scanner: Scanner,
                      duration=60, *, url=None, on_alert=None):
    if not math.isfinite(duration) or duration < 0:
        raise ValueError("Duration must be finite and non-negative")
    url = url or build_trade_url(config.symbols)
    stats = CaptureStats()
    session_id = str(uuid.uuid4())
    settings = {**asdict(config), "windows": scanner.windows,
                "threshold_pct": scanner.threshold_pct, "max_age_ms": scanner.max_age_ms,
                "max_gap_ms": scanner.max_gap_ms, "cooldown_ms": scanner.cooldown_ms}
    config_hash = hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()
    async with AsyncRecorder(directory, config.queue_capacity) as writer:
        writer.submit("session", {"session_id": session_id, "config": settings,
                                  "config_hash": config_hash, "scanner_version": "baseline-v1",
                                  "endpoint": url}, time.time_ns() // 1_000_000)
        try:
            async with asyncio.timeout(duration if duration else None):
                attempts = 0
                while True:
                    before = stats.fresh_trades
                    try:
                        await capture_session(url, config, scanner, writer, stats, on_alert)
                    except (OSError, TimeoutError, ConnectionClosed, InvalidHandshake,
                            StreamUnavailable) as exc:
                        scanner.reset()
                        stats.state, stats.last_reason = "DISCONNECTED", str(exc)[:256]
                        stats.last_disconnect_reason = stats.last_reason
                        stats.reconnects += 1
                        writer.submit("status", {"state": stats.state, "reason": stats.last_reason,
                                                 "reset_scanner": True}, time.time_ns() // 1_000_000)
                        if stats.fresh_trades > before:
                            attempts = 0
                        delay = min(30, config.retry_base * 2 ** min(attempts, 5))
                        attempts += 1
                        LOG.warning("%s; reconnect in %.2fs", stats.last_reason, delay)
                        await asyncio.sleep(delay + random.random() * config.retry_base)
        except TimeoutError:
            LOG.info("Capture duration reached")
        finally:
            scanner.reset()
            writer.submit("status", {"state": "STOPPED", "reason": "capture_finished",
                                     "reset_scanner": True}, time.time_ns() // 1_000_000)
            writer.submit("summary", {**asdict(stats), "session_id": session_id,
                                      "queue_high_watermark": writer.high_watermark},
                          time.time_ns() // 1_000_000)
    return stats