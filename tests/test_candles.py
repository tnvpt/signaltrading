import asyncio
from decimal import Decimal as D
import json
from pathlib import Path
import tempfile
import time
import unittest

from websockets.asyncio.server import serve
from websockets.asyncio.client import connect

from signaltrading.candles import Candle, CandleGap, EMA, INTERVALS, Series, WatchEngine, WilderRSI, stream_candle
from signaltrading.storage import AsyncRecorder
from signaltrading.watch import WatchStats, monitor_connection, validate_instruments, build_kline_url


def bar(index, price=100, interval="3m"):
    duration = INTERVALS[interval]
    p = D(str(price))
    return Candle("BTCUSDT", interval, index * duration, (index + 1) * duration,
                  p, p + 1, p - 1, p, D(1))


class CandleTests(unittest.TestCase):
    def test_rsi_monotonic_and_flat(self):
        for values, expected in ((range(100, 115), 100), (range(115, 100, -1), 0), ([100]*15, 50)):
            rsi = WilderRSI()
            for price in values[:-1]:
                self.assertIsNone(rsi.update(D(price)))
            self.assertEqual(rsi.update(D(values[-1])), expected)

    def test_wilder_recursion(self):
        rsi = WilderRSI()
        for price in range(100, 115):
            rsi.update(D(price))
        result = rsi.update(D(113))
        self.assertAlmostEqual(float(result), 92.8571428571)

    def test_ema_seed(self):
        ema = EMA(3)
        self.assertIsNone(ema.update(D(1)))
        self.assertIsNone(ema.update(D(2)))
        self.assertEqual(ema.update(D(3)), 2)
        self.assertEqual(ema.update(D(4)), 3)

    def test_gap_duplicate_conflict(self):
        series = Series()
        self.assertTrue(series.update(bar(0)))
        self.assertFalse(series.update(bar(0)))
        with self.assertRaises(CandleGap):
            series.update(bar(0, 102))
        with self.assertRaises(CandleGap):
            series.update(bar(2))

    def test_watch_hysteresis_and_independent_timeframes(self):
        engine = WatchEngine()
        found = []
        for index in range(20):
            b = bar(index, 100 + index)
            event = engine.consume(b, b.close_ms)
            if event:
                found.append(event)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["kind"], "WATCH_OVERBOUGHT")
        self.assertFalse(found[0]["actionable"])
        self.assertEqual(found[0]["context"]["15m"], "UNKNOWN")
        for index in range(15):
            b = bar(index, 120-index, "5m")
            event = engine.consume(b, b.close_ms)
        self.assertEqual(event["kind"], "WATCH_OVERSOLD")

    def test_warmup_never_emits_or_repeats_extreme(self):
        engine = WatchEngine()
        for index in range(20):
            b = bar(index, 100+index)
            self.assertIsNone(engine.consume(b, b.close_ms, historical=True))
        b = bar(20, 121)
        self.assertIsNone(engine.consume(b, b.close_ms))
        self.assertIsNone(engine.consume(b, b.close_ms))

    def test_rearm_and_cooldown(self):
        engine = WatchEngine(cooldown_ms=1_000_000)
        series = Series()
        series.last = bar(13)
        series.rsi.previous = D(100)
        series.rsi.count = 14
        series.rsi.gain, series.rsi.loss = D(1), D(0)
        engine.series[("BTCUSDT", "3m")] = series
        first = engine.consume(bar(14, 101), bar(14).close_ms)
        self.assertIsNotNone(first)
        # Directly provide controlled RSI evolution to isolate zone semantics.
        series.rsi.update = lambda close: setattr(series.rsi, "value", close)
        self.assertIsNone(engine.consume(bar(15, 64), bar(15).close_ms))
        self.assertEqual(series.zone, "NEUTRAL")
        self.assertIsNone(engine.consume(bar(16, 75), bar(16).close_ms))
        self.assertEqual(series.zone, "OVERBOUGHT")

    def test_no_future_candle(self):
        with self.assertRaises(ValueError):
            WatchEngine().consume(bar(0), 1)

    def test_market_and_url(self):
        with self.assertRaises(ValueError):
            validate_instruments({"symbols": []}, ("BTCUSDT",))
        self.assertIn("/market/stream?", build_kline_url(("BTCUSDT",)))
        self.assertIn("btcusdt@kline_3m", build_kline_url(("BTCUSDT",)))

    def test_stream_closed_and_forming_validation(self):
        payload = {"e": "kline", "E": 180001, "s": "BTCUSDT", "k": {
            "s": "BTCUSDT", "i": "3m", "t": 0, "T": 179999,
            "x": False, "o": "100", "h": "101", "l": "99", "c": "100", "v": "0"}}
        self.assertIsNone(stream_candle(payload)[0])
        payload["k"]["x"] = True
        self.assertEqual(stream_candle(payload)[0].close_ms, 180000)
        payload["k"]["c"] = "NaN"
        with self.assertRaises(ValueError):
            stream_candle(payload)
        with self.assertRaises(ValueError):
            stream_candle([])

    def test_context_warmup_and_stale(self):
        series = Series()
        for index in range(205):
            series.update(bar(index, 100+index, "15m"))
        self.assertEqual(series.direction(series.last.close_ms), "UP")
        self.assertEqual(series.direction(series.last.close_ms+2*INTERVALS["15m"]), "UNKNOWN")


class CandleConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_warmup_and_all_stream_heartbeats(self):
        now = time.time_ns() // 1_000_000
        def fetch(path):
            if path.endswith("time"):
                return {"serverTime": time.time_ns() // 1_000_000}
            return {"symbols": [{"symbol": "BTCUSDT", "status": "TRADING",
                                  "contractType": "PERPETUAL", "quoteAsset": "USDT", "marginAsset": "USDT"}]}

        def load(symbol, interval, server_ms):
            last = server_ms // INTERVALS[interval]
            return [bar(index, interval=interval) for index in range(last-205, last)]

        async def handler(socket):
            for interval, duration in INTERVALS.items():
                start = now // duration * duration
                await socket.send(json.dumps({"e": "kline", "E": time.time_ns()//1_000_000,
                    "s": "BTCUSDT", "k": {"s": "BTCUSDT", "i": interval, "t": start,
                    "T": start+duration-1, "x": False, "o": "100", "h": "101",
                    "l": "99", "c": "100", "v": "1"}}))
            await socket.wait_closed()

        with tempfile.TemporaryDirectory() as directory:
            async with serve(handler, "127.0.0.1", 0) as server:
                port = server.sockets[0].getsockname()[1]
                async with connect(f"ws://127.0.0.1:{port}") as socket:
                    async with AsyncRecorder(Path(directory)) as writer:
                        stats = WatchStats()
                        task = asyncio.create_task(monitor_connection(socket, ("BTCUSDT",), WatchEngine(),
                                                   writer, stats, fetch=fetch, load=load, stream_timeout=2))
                        await asyncio.sleep(0.3)
                        task.cancel()
                        with self.assertRaises(asyncio.CancelledError):
                            await task
                        self.assertTrue(stats.healthy)
                        self.assertEqual(stats.frames, 4)
                        self.assertEqual(stats.observations, 0)
            rows = [json.loads(line) for path in Path(directory).glob("*.jsonl") for line in path.read_text().splitlines()]
            self.assertEqual(sum(row["type"] == "kline_history" for row in rows), 820)


if __name__ == "__main__":
    unittest.main()