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
MIN_HISTORY_BARS = 205
DEFAULT_TOP_ALTCOINS = 8
DEFAULT_MIN_VOLUME = 1_000_000
DEFAULT_MAX_VOLUME = 50_000_000


def request_json(path, params=None):
    url = REST_BASE + path + ("?" + urlencode(params) if params else "")
    with urlopen(url, timeout=10) as response:
        payload = json.load(response)
    if isinstance(payload, dict) and "code" in payload:
        raise ValueError(f"Binance REST error: {payload.get('code')}")
    return payload


def active_perpetuals(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list):
        raise ValueError("Malformed exchange metadata")
    return {item["symbol"]: item for item in payload["symbols"]
                 if item.get("status") == "TRADING" and item.get("contractType") == "PERPETUAL"
                 and item.get("quoteAsset") == "USDT" and item.get("marginAsset") == "USDT"}


def validate_instruments(payload, symbols):
    if not set(symbols) <= active_perpetuals(payload).keys():
        raise ValueError("Unsupported/inactive USDT linear perpetual symbol")


def discover_futures(fetch=request_json):
    contracts = active_perpetuals(fetch("/fapi/v1/exchangeInfo"))
    oldest = time.time_ns() // 1_000_000 - (MIN_HISTORY_BARS + 1) * INTERVALS["1h"]
    symbols = tuple(sorted(
        symbol for symbol, contract in contracts.items()
        if symbol.isascii() and symbol.isalnum() and symbol.endswith("USDT")
        and type(contract.get("onboardDate")) is int and 0 < contract["onboardDate"] <= oldest
    ))
    if not symbols:
        raise ValueError("No active USDT perpetuals with sufficient listing history")
    return symbols


def discover_altcoins(limit, min_volume, max_volume, fetch=request_json):
    contracts = active_perpetuals(fetch("/fapi/v1/exchangeInfo"))
    tickers = fetch("/fapi/v1/ticker/24hr")
    if not isinstance(tickers, list):
        raise ValueError("Malformed futures ticker list")
    oldest = time.time_ns() // 1_000_000 - (MIN_HISTORY_BARS + 1) * INTERVALS["1h"]
    scores = {}
    for ticker in tickers:
        symbol = ticker["symbol"]
        contract = contracts.get(symbol)
        if (not contract or symbol in {"BTCUSDT", "ETHUSDT"}
                or contract.get("underlyingType") != "COIN"
                or not symbol.isascii() or not symbol.isalnum() or not symbol.endswith("USDT")):
            continue
        onboard = contract.get("onboardDate")
        if type(onboard) is not int or not 0 < onboard <= oldest:
            continue
        try:
            volume = float(ticker["quoteVolume"])
            change = abs(float(ticker["priceChangePercent"]))
        except (KeyError, ValueError, TypeError):
            continue
        if 0 < volume and min_volume <= volume <= max_volume and math.isfinite(change):
            scores[symbol] = change
    selected = tuple(sorted(scores, key=lambda symbol: (-scores[symbol], symbol))[:limit])
    if not selected:
        raise ValueError("No eligible altcoins in the configured 24h quote volume range")
    return CaptureConfig(selected).symbols


def history(symbol, interval, server_ms):
    rows = request_json("/fapi/v1/klines", {"symbol": symbol, "interval": interval,
                                         "limit": 250, "endTime": server_ms - 1})
    if not isinstance(rows, list):
        raise ValueError("Expected historical candle list")
    candles = [rest_candle(symbol, interval, row) for row in rows]
    candles = [bar for bar in candles if bar.close_ms <= server_ms]
    if len(candles) < MIN_HISTORY_BARS:
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


async def warmup(symbols, engine, writer, fetch=request_json, load=history, *, skip_unready=False):
    validate_instruments(await asyncio.to_thread(fetch, "/fapi/v1/exchangeInfo"), symbols)
    sent = time.time_ns() // 1_000_000
    payload = await asyncio.to_thread(fetch, "/fapi/v1/time")
    received = time.time_ns() // 1_000_000
    server_ms = payload["serverTime"]
    if type(server_ms) is not int or abs(server_ms - (sent + received) // 2) + (received - sent) // 2 > 1000:
        raise ValueError("Local/server clock uncertainty exceeds 1000ms MVP bound")
    # Keep exact checkpoint indicators if REST can bridge from their last close.
    # Context first, no alert from any historical bar.
    warmed = set()
    for symbol in symbols:
        try:
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
        except (CandleGap, ValueError) as exc:
            if not skip_unready:
                raise
            for interval in INTERVALS:
                engine.series.pop((symbol, interval), None)
            LOG.warning("Skipping %s in this rotation: %s", symbol, exc)
        else:
            warmed.add(symbol)
    if not warmed:
        raise CandleGap("No symbol in this group completed warmup")
    writer.submit("watch_status", {"state": "WARMED", "server_ms": server_ms, "symbols": sorted(warmed)}, received)
    return warmed


async def monitor_connection(socket, symbols, engine, writer, stats, *,
                             fetch=request_json, load=history, on_watch=None,
                             stream_timeout=10.0, store=None, chats=(), skip_unready=False):
    # Start receiving before REST work. Queue saturation aborts rather than lose bars.
    queue = asyncio.Queue(maxsize=max(2048, 1024 * len(symbols)))
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
        boot = asyncio.create_task(warmup(symbols, engine, writer, fetch, load, skip_unready=skip_unready))
        try:
            done, _ = await asyncio.wait((boot, receiving, writer.task), return_when=asyncio.FIRST_COMPLETED)
            if writer.task in done:
                writer.task.result()
            if receiving in done:
                receiving.result()
            warmed = await boot
            required = {key for key in required if key[0] in warmed}
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
            if key[0] in symbols and key[0] not in warmed:
                continue
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


async def run_watch(symbols, output, duration=60, *, on_watch=None, telegram=False, env_file=None,
                    top_altcoins=DEFAULT_TOP_ALTCOINS, min_volume=DEFAULT_MIN_VOLUME,
                    max_volume=DEFAULT_MAX_VOLUME, rotation_seconds=None):
    if rotation_seconds is not None and (
            symbols is not None or not math.isfinite(rotation_seconds) or rotation_seconds <= 0):
        raise ValueError("Futures rotation requires automatic selection and a positive interval")
    if symbols is not None:
        symbols = CaptureConfig(tuple(symbols)).symbols
    if not 1 <= top_altcoins <= 20 or not 0 <= min_volume < max_volume or not math.isfinite(max_volume):
        raise ValueError("Expected 1–20 altcoins and finite ordered 24h quote volume bounds")
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
                                        "rotation_seconds": rotation_seconds,
                                        "intervals": list(INTERVALS), "orders_enabled": False},
                      time.time_ns() // 1_000_000)
        try:
            async with asyncio.timeout(duration if duration else None):
                attempts = 0
                universe = ()
                cursor = 0
                while True:
                    if sending and sending.done():
                        sending.result()
                    try:
                        selected = symbols
                        if rotation_seconds is not None:
                            if cursor >= len(universe):
                                universe = await asyncio.to_thread(discover_futures)
                                cursor = 0
                            selected = universe[cursor:cursor + top_altcoins]
                            cursor += len(selected)
                            writer.submit("watch_universe", {"symbols": selected, "processed": cursor,
                                          "total": len(universe)}, time.time_ns() // 1_000_000)
                            LOG.info("Futures rotation %s/%s: %s", cursor, len(universe), ", ".join(selected))
                        elif selected is None:
                            selected = await asyncio.to_thread(discover_altcoins, top_altcoins, min_volume, max_volume)
                            writer.submit("watch_universe", {"symbols": selected, "top_altcoins": top_altcoins,
                                          "min_volume": min_volume, "max_volume": max_volume},
                                          time.time_ns() // 1_000_000)
                            LOG.info("Futures altcoins: %s", ", ".join(selected))
                        async with connect(build_kline_url(selected), open_timeout=15, close_timeout=2,
                                           ping_interval=None, max_queue=32) as socket:
                            stats.connections += 1
                            stats.healthy = False
                            # Thin markets may go longer between kline updates.
                            rotation = asyncio.timeout(rotation_seconds)
                            try:
                                async with rotation:
                                    await monitor_connection(
                                        socket, selected, engine, writer, stats, on_watch=on_watch,
                                        stream_timeout=45.0 if symbols is None else 10.0,
                                        store=store, chats=chats, skip_unready=rotation_seconds is not None,
                                    )
                            except TimeoutError:
                                if not rotation.expired():
                                    raise
                        attempts = 0
                        if rotation_seconds is not None:
                            engine.reset_series()
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
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--symbols", nargs="+", help="Follow a fixed list of USDT perpetuals")
    selection.add_argument("--top-altcoins", type=int, choices=range(1, 21), metavar="1–20",
                           default=DEFAULT_TOP_ALTCOINS, help="Rank by absolute 24h change (default: 8)")
    selection.add_argument("--rotate-futures", action="store_true",
                           help="Cycle through active USDT perpetuals in groups of 8")
    parser.add_argument("--rotation-seconds", type=float, default=300,
                        help="Seconds per Futures group, including warmup (default: 300)")
    parser.add_argument("--min-quote-volume", type=float, default=DEFAULT_MIN_VOLUME,
                        help="Minimum 24h volume in USDT for automatic selection (default: 1000000)")
    parser.add_argument("--max-quote-volume", type=float, default=DEFAULT_MAX_VOLUME,
                        help="Maximum 24h volume in USDT for automatic selection (default: 50000000)")
    parser.add_argument("--duration", type=float, default=60)
    parser.add_argument("--output", type=Path, default=Path("data/candle-watch"))
    parser.add_argument("--telegram", action="store_true", help="Explicitly enable sends to env allowlist")
    parser.add_argument("--env-file", type=Path, help="Explicit Telegram credentials file; no shell sourcing")
    args = parser.parse_args()
    if not math.isfinite(args.duration) or args.duration < 0:
        parser.error("Duration must be finite and non-negative")
    if not 0 <= args.min_quote_volume < args.max_quote_volume or not math.isfinite(args.max_quote_volume):
        parser.error("Expected finite ordered 24h quote volume bounds")
    if not math.isfinite(args.rotation_seconds) or args.rotation_seconds <= 0:
        parser.error("Rotation interval must be finite and positive")
    symbols = tuple(sorted(set(s.upper() for s in args.symbols))) if args.symbols else None
    try:
        if symbols is not None:
            CaptureConfig(symbols)
        if args.telegram:
            telegram_config(env_file=args.env_file)
    except ValueError as exc:
        parser.error(str(exc))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        stats = asyncio.run(run_watch(symbols, args.output, args.duration,
                            on_watch=lambda item: print(json.dumps(item, ensure_ascii=False), flush=True),
                            telegram=args.telegram, env_file=args.env_file, top_altcoins=args.top_altcoins,
                            min_volume=args.min_quote_volume, max_volume=args.max_quote_volume,
                            rotation_seconds=args.rotation_seconds if args.rotate_futures else None))
        LOG.info("Watch summary: %s", json.dumps(asdict(stats)))
        return 0 if stats.healthy else 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())