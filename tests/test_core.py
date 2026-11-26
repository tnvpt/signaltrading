from dataclasses import asdict
import tempfile
from pathlib import Path
import unittest

from signaltrading.core import Recorder, Scanner, Trade, parse_trade, replay


def trade(index, price=100, received_offset=0):
    timestamp = 1_000_000 + index * 1000
    return Trade("BTCUSDT", index, timestamp, timestamp + received_offset, price, 1, "buy")


class CoreTests(unittest.TestCase):
    def test_parse_combined_trade(self):
        result = parse_trade({"data": {"e": "aggTrade", "s": "BTCUSDT", "a": 7,
                             "T": 1000, "p": "100.5", "q": "2", "m": True}}, 1100)
        self.assertEqual(result.aggressor, "sell")
        self.assertEqual(result.price, 100.5)

    def test_invalid_price(self):
        for price in ("NaN", "Infinity", "-1", "0"):
            with self.subTest(price=price), self.assertRaises(ValueError):
                parse_trade({"e": "aggTrade", "s": "BTCUSDT", "a": 1, "T": 1,
                             "p": price, "q": "1", "m": False}, 1)

    def test_warmup_volume_cooldown(self):
        scanner = Scanner(windows=(30,))
        for index in range(30):
            self.assertEqual(scanner.consume(trade(index)), [])
        alerts = scanner.consume(trade(30, 103))
        self.assertEqual(len(alerts), 1)
        self.assertAlmostEqual(alerts[0].change_pct, 3)
        self.assertEqual(alerts[0].quote_volume, 3003)
        self.assertFalse(alerts[0].actionable)
        self.assertEqual(scanner.consume(trade(31, 103)), [])

    def test_dump(self):
        scanner = Scanner(windows=(30,))
        for index in range(30):
            scanner.consume(trade(index))
        self.assertEqual(scanner.consume(trade(30, 97))[0].kind, "dump_watch")

    def test_bad_data_requires_new_warmup(self):
        for mode in ("stale", "future", "gap", "order"):
            with self.subTest(mode=mode):
                scanner = Scanner(windows=(30,))
                for index in range(30):
                    scanner.consume(trade(index))
                bad = {"stale": trade(30, 103, 4000), "future": trade(30, 103, -2000),
                       "gap": trade(32, 103), "order": trade(28, 103)}[mode]
                self.assertEqual(scanner.consume(bad), [])
                self.assertIsNotNone(scanner.last_issue)
                self.assertEqual(scanner.consume(trade(33, 103)), [])

    def test_duplicate_ignored(self):
        scanner = Scanner()
        scanner.consume(trade(0))
        scanner.consume(trade(0))
        self.assertEqual(len(scanner.history["BTCUSDT"]), 1)

    def test_replay_matches_live_and_resets_on_disconnect(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = Recorder(Path(directory))
            scanner = Scanner(windows=(30,))
            expected = []
            for index in range(31):
                item = trade(index, 103 if index == 30 else 100)
                recorder.write("trade", asdict(item), item.received_ms)
                expected.extend(scanner.consume(item))
            recorder.write("status", {"state": "disconnected"}, item.received_ms)
            recorder.write("trade", asdict(trade(31, 110)), trade(31).received_ms)
            recorder.close()
            result = list(replay(next(Path(directory).glob("*.jsonl")), Scanner(windows=(30,))))
            self.assertEqual(result, expected)

    def test_corrupt_replay_fails_with_line(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.jsonl"
            path.write_text("not json\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "line 1"):
                list(replay(path, Scanner()))


if __name__ == "__main__":
    unittest.main()