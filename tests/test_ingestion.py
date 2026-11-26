import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import time
import unittest

from websockets.asyncio.server import serve

from signaltrading.core import Scanner, Trade, parse_trade, replay
from signaltrading.ingestion import CaptureConfig, run_capture, build_trade_url
from signaltrading.storage import AsyncRecorder, StorageOverloaded, StorageFailure


def frame(symbol="BTCUSDT", index=1):
    return json.dumps({"stream": f"{symbol.lower()}@aggTrade", "data": {
        "e": "aggTrade", "s": symbol, "a": index, "T": time.time_ns() // 1_000_000,
        "p": "100", "q": "1", "m": False}})


def records(directory):
    return [json.loads(line) for path in Path(directory).glob("*.jsonl")
            for line in path.read_text().splitlines()]


class ValidationTests(unittest.TestCase):
    def test_aggregate_trades_use_market_route(self):
        self.assertEqual(build_trade_url(("BTCUSDT", "ETHUSDT")),
                         "wss://fstream.binance.com/market/stream?streams="
                         "btcusdt@aggTrade/ethusdt@aggTrade")

    def test_non_object_frames_and_fractional_ids(self):
        for payload in ([], None, {"data": []}, {"data": None}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                parse_trade(payload, 100)
        payload = json.loads(frame())["data"]
        payload["a"] = 1.5
        with self.assertRaises(ValueError):
            parse_trade(payload, 100)

    def test_replay_rejects_invalid_trade(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.jsonl"
            trade = asdict(Trade("BTCUSDT", 1, 1000, 1000, 100, 1, "buy"))
            trade["price"] = -1
            path.write_text(json.dumps({"schema_version": 1, "source": "binance_usdm",
                                        "type": "trade", "received_ms": 1000, "data": trade}))
            with self.assertRaisesRegex(ValueError, "line 1"):
                list(replay(path, Scanner()))

    def test_invalid_configuration(self):
        for kwargs in ({"symbols": ()}, {"stale_timeout": float("nan")},
                       {"queue_capacity": 0}, {"symbols": ("btcusdt",)}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                CaptureConfig(**kwargs)


class IngestionTests(unittest.IsolatedAsyncioTestCase):
    async def capture(self, handler, directory, *, symbols=("BTCUSDT",), duration=0.2):
        async with serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            config = CaptureConfig(symbols, first_trade_timeout=0.06, stale_timeout=0.06,
                                   watchdog_interval=0.01, retry_base=0.01)
            return await run_capture(config, Path(directory), Scanner(), duration,
                                     url=f"ws://127.0.0.1:{port}")

    async def test_valid_stream_record_and_replay(self):
        async def handler(socket):
            try:
                for index in range(1, 100):
                    await socket.send(frame(index=index))
                    await asyncio.sleep(0.01)
            except Exception:
                if socket.close_code is None:
                    raise

        with tempfile.TemporaryDirectory() as directory:
            stats = await self.capture(handler, directory)
            rows = records(directory)
            self.assertGreater(stats.fresh_trades, 0)
            self.assertEqual(stats.state, "HEALTHY")
            self.assertTrue(any(row["type"] == "trade" for row in rows))
            self.assertTrue(any(row["type"] == "session" and row["data"]["config_hash"] for row in rows))
            self.assertEqual(rows[-1]["type"], "summary")
            for path in Path(directory).glob("*.jsonl"):
                self.assertEqual(list(replay(path, Scanner())), [])

    async def test_silent_handshake_is_not_healthy(self):
        async def handler(socket):
            await socket.wait_closed()

        with tempfile.TemporaryDirectory() as directory:
            stats = await self.capture(handler, directory)
            self.assertEqual(stats.fresh_trades, 0)
            self.assertGreater(stats.reconnects, 0)
            self.assertIn("first_valid_trade_timeout", stats.last_disconnect_reason)

    async def test_watchdog_detects_one_missing_symbol(self):
        async def handler(socket):
            try:
                for index in range(1, 100):
                    await socket.send(frame(index=index))
                    await asyncio.sleep(0.01)
            except Exception:
                if socket.close_code is None:
                    raise

        with tempfile.TemporaryDirectory() as directory:
            stats = await self.capture(handler, directory, symbols=("BTCUSDT", "ETHUSDT"))
            self.assertGreater(stats.fresh_trades, 0)
            self.assertIn("ETHUSDT", stats.last_disconnect_reason)
            self.assertGreater(stats.reconnects, 0)

    async def test_malformed_then_server_error_is_audited(self):
        async def handler(socket):
            await socket.send("not-json")
            await socket.send(json.dumps({"code": -1, "msg": "test rejection"}))
            await socket.wait_closed()

        with tempfile.TemporaryDirectory() as directory:
            stats = await self.capture(handler, directory)
            self.assertGreater(stats.malformed_frames, 0)
            self.assertIn("exchange_error", stats.last_disconnect_reason)
            self.assertTrue(any(row["type"] == "diagnostic" for row in records(directory)))

    async def test_stale_after_first_trade(self):
        async def handler(socket):
            await socket.send(frame())
            await socket.wait_closed()

        with tempfile.TemporaryDirectory() as directory:
            # Include real loopback handshake/scheduler overhead before silence.
            stats = await self.capture(handler, directory, duration=0.8)
            self.assertGreater(stats.fresh_trades, 0)
            self.assertTrue(any("stale_symbol" in row["data"].get("reason", "")
                                for row in records(directory)))

    async def test_overflow_is_fatal_and_pending_records_flush(self):
        with tempfile.TemporaryDirectory() as directory:
            async with AsyncRecorder(Path(directory), capacity=1) as writer:
                writer.submit("status", {"state": "WARMING_UP"}, 1000)
                with self.assertRaises(StorageOverloaded):
                    writer.submit("status", {}, 1001)
            self.assertEqual(len(records(directory)), 1)

    async def test_disk_failure_propagates_without_hang(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(StorageFailure, "disk unavailable"):
                async with AsyncRecorder(Path(directory)) as writer:
                    def fail(*args):
                        raise OSError("disk unavailable")
                    writer.recorder.write = fail
                    writer.submit("status", {}, 1000)
                    await asyncio.wait((writer.task,), timeout=1)

    async def test_cancel_drains_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            async def work():
                async with AsyncRecorder(Path(directory)) as writer:
                    writer.submit("status", {"state": "WARMING_UP"}, 1000)
                    await asyncio.sleep(60)
            task = asyncio.create_task(work())
            await asyncio.sleep(0.02)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertEqual(len(records(directory)), 1)