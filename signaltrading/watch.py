"""Binance closed-kline monitoring with REST warmup and gap recovery."""

import argparse
import asyncio
from dataclasses import asdict, dataclass
import json
import logging
import math
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import urlopen

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake

from .candles import INTERVALS, CandleGap, WatchEngine, rest_candle, stream_candle
from .ingestion import CaptureConfig
from .storage import AsyncRecorder
from .notifications import WatchStore, telegram_config, sender_loop

LOG = logging.getLogger("signaltrading.watch")
REST_BASE = "https://fapi.binance.com"


def request_json(path, params=None):
    url = REST_BASE + path + ("?" + urlencode(params) if params else "")
    with urlopen(url, timeout=10) as response:
        payload = json.load(response)
    if isinstance(payload, dict) and "code" in payload:
        raise ValueError(f"Binance REST error: {payload.get('code')}")
    return payload


def validate_instruments(payload, symbols):
    if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list):
        raise ValueError("Malformed exchange metadata")
    available = {item["symbol"] for item in payload["symbols"]
                 if item.get("status") == "TRADING" and item.get("contractType") == "PERPETUAL"
                 and item.get("quoteAsset") == "USDT" and item.get("marginAsset") == "USDT"}
    if not set(symbols) <= available:
        raise ValueError("Unsupported/inactive USDT linear perpetual symbol")


def history(symbol, interval, server_ms):
    rows = request_json("/fapi/v1/klines", {"symbol": symbol, "interval": interval,
                                         "limit": 250, "endTime": server_ms - 1})
    if not isinstance(rows, list):
        raise ValueError("Expected historical candle list")
    candles = [rest_candle(symbol, interval, row) for row in rows]
    candles = [bar for bar in candles if bar.close_ms <= server_ms]
    if len(candles) < 205:
        raise ValueError("Insufficient history for stable warmup contract")
    return candles


def build_kline_url(symbols):
    streams = [f"{symbol.lower()}@kline_{interval}" for symbol in symbols for interval in INTERVALS]
    return "wss://fstream.binance.com/market/stream?streams=" + "/".join(streams)


@dataclass
class WatchStats:
    connections: int = 0
    frames: int = 0
    closed_bars: int = 0
    observations: int = 0
    recoveries: int = 0
    healthy: bool = False
    last_error: str | None = None


async def warmup(symbols, engine, writer, fetch=request_json, load=history):
    validate_instruments(await asyncio.to_thread(fetch, "/fapi/v1/exchangeInfo"), symbols)
    sent = time.time_ns() // 1_000_000
    payload = await asyncio.to_thread(fetch, "/fapi/v1/time")
    received = time.time_ns() // 1_000_000
    server_ms = payload["serverTime"]
    if type(server_ms) is not int or abs(server_ms - (sent + received) // 2) + (received - sent) // 2 > 1000:
        raise ValueError("Local/server clock uncertainty exceeds 1000ms MVP bound")
    # Keep exact checkpoint indicators if REST can bridge from their last close.
    # Context first, no alert from any historical bar.
    for symbol in symbols:
        for interval in ("15m", "1h", "3m", "5m"):
            bars = await asyncio.to_thread(load, symbol, interval, server_ms)
            previous = engine.series.get((symbol, interval))
            if previous and previous.last:
                matches = [bar for bar in bars if bar.open_ms == previous.last.open_ms]
                if not matches or matches[0] != previous.last:
                    engine.series.pop((symbol, interval), None)
            for bar in bars:
                writer.submit("kline_history", bar.record(), received)
                engine.consume(bar, server_ms, historical=True)
            expected_end = server_ms // INTERVALS[interval] * INTERVALS[interval]
            if not bars or bars[-1].close_ms != expected_end:
                raise CandleGap("Historical tail does not reach last completed interval")
    writer.submit("watch_status", {"state": "WARMED", "server_ms": server_ms}, received)


async def monitor_connection(socket, symbols, engine, writer, stats, *,
                             fetch=request_json, load=history, on_watch=None,
                             stream_timeout=10.0, store=None, chats=()):
    # Start receiving before REST work. Queue saturation aborts rather than lose bars.
    queue = asyncio.Queue(maxsize=2048)
    required = {(symbol, interval) for symbol in symbols for interval in INTERVALS}
    last_seen = {}
    started = time.monotonic()

    async def receiver():
        async for raw in socket:
            arrived = time.time_ns() // 1_000_000
            try:
                queue.put_nowait((raw, arrived))
            except asyncio.QueueFull as exc:
                raise CandleGap("Kline bootstrap/processing queue overloaded") from exc
        raise CandleGap("Kline socket closed")

    receiving = asyncio.create_task(receiver())
    try:
        boot = asyncio.create_task(warmup(symbols, engine, writer, fetch, load))
        try:
            done, _ = await asyncio.wait((boot, receiving, writer.task), return_when=asyncio.FIRST_COMPLETED)
            if writer.task in done:
                writer.task.result()
            if receiving in done:
                receiving.result()
            await boot
        finally:
            if not boot.done():
                boot.cancel()
            await asyncio.gather(boot, return_exceptions=True)
        # Warmup took time: per-stream health starts when buffered input processing begins.
        started = time.monotonic()
        while True:
            if receiving.done():
                receiving.result()
            if writer.task.done():
                writer.task.result()
            now = time.monotonic()
            if any(now - last_seen.get(key, started) >= stream_timeout for key in required):
                stats.healthy = False
                raise CandleGap("Missing/stale kline stream")
            try:
                raw, arrived = await asyncio.wait_for(queue.get(), timeout=0.25)
            except TimeoutError:
                continue
            payload = json.loads(raw)
            if isinstance(payload, dict) and "code" in payload:
                raise CandleGap(f"Exchange subscription error: {payload['code']}")
            bar, event_ms = stream_candle(payload)
            data = payload.get("data", payload)
            key = (data["s"], data["k"]["i"])
            if key not in required:
                raise CandleGap("Unexpected candle stream")
            # Buffered old updates may aid continuity, but cannot create delayed watch alerts.
            current_ms = time.time_ns() // 1_000_000
            age = current_ms - event_ms
            if age < -1000:
                raise CandleGap("Future exchange timestamp")
            if age <= 3000:
                last_seen[key] = now
            stats.frames += 1
            writer.submit("kline_frame", {"payload": payload, "arrived_ms": arrived}, current_ms)
            stats.healthy = len(last_seen) == len(required) and all(
                now - seen < stream_timeout for seen in last_seen.values())
            if bar is None:
                continue
            if event_ms < bar.close_ms:
                raise CandleGap("Closed bar before close boundary")
            # Even a delayed bar can repair indicator sequence, but cannot notify as current.
            watch = engine.consume(bar, current_ms, historical=(age > 3000
                                   or current_ms - bar.close_ms > 3000 or not stats.healthy))
            stats.closed_bars += 1
            writer.submit("closed_analysis", {"candle": bar.record(),
                          "rsi": str(engine.series[key].rsi.value), "watch_id": watch["observation_id"] if watch else None}, current_ms)
            if store:
                store.commit(engine, watch, chats)
            if watch:
                writer.submit("watch", watch, current_ms)
                stats.observations += 1
                if on_watch:
                    on_watch(watch)
    finally:
        receiving.cancel()
        await asyncio.gather(receiving, return_exceptions=True)


async def run_watch(symbols, output, duration=60, *, on_watch=None, telegram=False, env_file=None):
    CaptureConfig(tuple(symbols))  # Reuse strict USDT symbol validation.
    if not math.isfinite(duration) or duration < 0:
        raise ValueError("Duration must be finite and non-negative")
    stats = WatchStats()
    token, chats = telegram_config(env_file=env_file) if telegram else (None, ())
    store = WatchStore(Path(output) / "watch.sqlite3")
    engine = store.load()
    store.expire(time.time_ns()//1_000_000, unhealthy=True)
    sending = asyncio.create_task(sender_loop(store, token, chats, lambda: stats.healthy)) if telegram else None
    async with AsyncRecorder(output) as writer:
        writer.submit("watch_session", {"profile": "rsi-watch-1", "symbols": symbols,
                                        "intervals": list(INTERVALS), "orders_enabled": False},
                      time.time_ns() // 1_000_000)
        try:
            async with asyncio.timeout(duration if duration else None):
                attempts = 0
                while True:
                    if sending and sending.done():
                        sending.result()
                    try:
                        async with connect(build_kline_url(symbols), open_timeout=15, close_timeout=2,
                                           ping_interval=None, max_queue=32) as socket:
                            stats.connections += 1
                            stats.healthy = False
                            await monitor_connection(socket, symbols, engine, writer, stats, on_watch=on_watch,
                                                     store=store, chats=chats)
                    except (OSError, TimeoutError, ConnectionClosed, InvalidHandshake,
                            ValueError, KeyError, TypeError) as exc:
                        stats.recoveries += 1
                        stats.healthy = False
                        stats.last_error = f"{type(exc).__name__}: {exc}"[:250]
                        engine.reset_series()
                        store.expire(time.time_ns()//1_000_000, unhealthy=True)
                        writer.submit("watch_status", {"state": "DEGRADED", "reason": stats.last_error},
                                      time.time_ns() // 1_000_000)
                        LOG.warning("Rewarming after: %s", stats.last_error)
                        await asyncio.sleep(min(30, 2 ** min(attempts, 5)))
                        attempts += 1
        except TimeoutError:
            LOG.info("Watch duration reached")
        finally:
            if sending:
                sending.cancel()
                await asyncio.gather(sending, return_exceptions=True)
            writer.submit("watch_summary", asdict(stats), time.time_ns() // 1_000_000)
            store.close()
    return stats


def main():
    parser = argparse.ArgumentParser(description="Closed-candle RSI watch; no orders")
    parser.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT"])
    parser.add_argument("--duration", type=float, default=60)
    parser.add_argument("--output", type=Path, default=Path("data/candle-watch"))
    parser.add_argument("--telegram", action="store_true", help="Explicitly enable sends to env allowlist")
    parser.add_argument("--env-file", type=Path, help="Explicit Telegram credentials file; no shell sourcing")
    args = parser.parse_args()
    if not math.isfinite(args.duration) or args.duration < 0:
        parser.error("Duration must be finite and non-negative")
    symbols = tuple(sorted(set(s.upper() for s in args.symbols)))
    try:
        CaptureConfig(symbols)
        if args.telegram:
            telegram_config(env_file=args.env_file)
    except ValueError as exc:
        parser.error(str(exc))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        stats = asyncio.run(run_watch(symbols, args.output, args.duration,
                            on_watch=lambda item: print(json.dumps(item, ensure_ascii=False), flush=True),
                            telegram=args.telegram, env_file=args.env_file))
        LOG.info("Watch summary: %s", json.dumps(asdict(stats)))
        return 0 if stats.healthy else 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())