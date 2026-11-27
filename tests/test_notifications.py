import asyncio
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from signaltrading.candles import Candle, WatchEngine
from signaltrading.notifications import WatchStore, deliver_one, render_watch, restore, snapshot, telegram_config, telegram_send


def observation():
    return {"observation_id": "a"*64, "symbol": "BTCUSDT", "interval": "3m",
            "kind": "WATCH_OVERSOLD", "rsi": "28.4", "context": {"15m": "DOWN", "1h": "DOWN"},
            "bar_close_ms": 1000000, "decision_ms": 1000100, "expires_ms": 1030100}


class NotificationTests(unittest.TestCase):
    def test_explicit_env_file_ignores_stale_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'test.env'
            path.write_text("TELEGRAM_BOT_TOKEN='123:fake'\nTELEGRAM_ALLOWED_CHAT_IDS='123,-456'\n")
            self.assertEqual(telegram_config({'TELEGRAM_BOT_TOKEN':'invalid'},env_file=path),
                             ('123:fake',('123','-456')))
            path.write_text("TELEGRAM_BOT_TOKEN='123:fake'\nTELEGRAM_ALLOWED_CHAT_IDS='[123]'\n")
            with self.assertRaisesRegex(ValueError,'numeric IDs'):
                telegram_config(env_file=path)

    def test_single_owner_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"watch.db"
            first=WatchStore(path)
            try:
                with self.assertRaises(RuntimeError):
                    WatchStore(path)
            finally:
                first.close()

    def test_renderer_and_config(self):
        text = render_watch(observation())
        self.assertIn("CHƯA xác nhận", text)
        self.assertIn("Ngược xu hướng", text)
        self.assertIn("https://www.binance.com/en/futures/BTCUSDT", text)
        altcoin = render_watch(dict(observation(), symbol="1000PEPEUSDT"))
        self.assertIn("https://www.binance.com/en/futures/1000PEPEUSDT", altcoin)
        self.assertLess(len(text), 1000)
        with self.assertRaises(ValueError):
            telegram_config({})
        self.assertEqual(telegram_config({"TELEGRAM_BOT_TOKEN": "123:fake", "TELEGRAM_ALLOWED_CHAT_IDS": "1,1,-2"}), ("123:fake", ("1", "-2")))

    def test_checkpoint_roundtrip_and_continuation(self):
        engine = WatchEngine()
        for index in range(20):
            p = Decimal(100+index)
            bar = Candle("BTCUSDT", "3m", index*180000, (index+1)*180000, p,p,p,p,Decimal(1))
            engine.consume(bar, bar.close_ms)
        recovered = restore(snapshot(engine))
        self.assertEqual(snapshot(recovered), snapshot(engine))
        p = Decimal(121)
        bar = Candle("BTCUSDT", "3m", 20*180000, 21*180000,p,p,p,p,Decimal(1))
        self.assertEqual(engine.consume(bar,bar.close_ms), recovered.consume(bar,bar.close_ms))
        self.assertEqual(snapshot(engine), snapshot(recovered))

    def test_http_timeout_never_leaks_token(self):
        with patch("signaltrading.notifications.urlopen", side_effect=TimeoutError("secret-token-in-url")):
            result = telegram_send("secret-token", "1", "test")
        self.assertEqual(result["status"], "DELIVERY_UNKNOWN")
        self.assertNotIn("secret", json.dumps(result))

    def test_http_success(self):
        from io import BytesIO
        with patch("signaltrading.notifications.urlopen", return_value=BytesIO(b'{"ok":true,"result":{"message_id":7}}')):
            self.assertEqual(telegram_send("fake", "1", "test"), {"status":"API_ACCEPTED","message_id":7})

    def test_http_rate_limit_and_permanent_rejection(self):
        from io import BytesIO
        from urllib.error import HTTPError
        for code,payload,expected in ((429,b'{"error_code":429,"parameters":{"retry_after":5}}',"RETRY_WAIT"),
                                       (401,b'{"error_code":401}',"FAILED")):
            error=HTTPError('https://redacted',code,'failure',{},BytesIO(payload))
            with patch("signaltrading.notifications.urlopen",side_effect=error):
                self.assertEqual(telegram_send('fake','1','test')['status'],expected)


class OutboxTests(unittest.IsolatedAsyncioTestCase):
    async def test_candle_to_mock_delivery_end_to_end(self):
        with tempfile.TemporaryDirectory() as directory:
            store=WatchStore(Path(directory)/'watch.db')
            engine=store.load()
            events=[]
            for index in range(15):
                p=Decimal(200-index)
                bar=Candle('BTCUSDT','3m',index*180000,(index+1)*180000,p,p,p,p,Decimal(1))
                watch=engine.consume(bar,bar.close_ms)
                store.commit(engine,watch,('1',))
                if watch: events.append(watch)
            self.assertEqual(len(events),1)
            delivered=[]
            def send(token,chat,text):
                delivered.append(text)
                return {'status':'API_ACCEPTED','message_id':9}
            await deliver_one(store,'fake',('1',),now_ms=events[0]['decision_ms']+100,send=send)
            self.assertEqual(len(delivered),1)
            self.assertIn('QUÁ BÁN',delivered[0])
            store.close()
            store=WatchStore(Path(directory)/'watch.db')
            restored=store.load()
            self.assertEqual(snapshot(restored),snapshot(engine))
            self.assertIsNone(await deliver_one(store,'fake',('1',),now_ms=events[0]['decision_ms']+200,send=send))
            self.assertEqual(len(delivered),1)
            store.close()

    async def test_checkpoint_and_outbox_transaction_rolls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            store=WatchStore(Path(directory)/'watch.db')
            malformed=observation()
            malformed['kind']='UNSUPPORTED'
            with self.assertRaises(ValueError):
                store.commit(WatchEngine(),malformed,('1',))
            self.assertEqual(store.db.execute('SELECT count(*) FROM checkpoint').fetchone()[0],0)
            self.assertEqual(store.db.execute('SELECT count(*) FROM observations').fetchone()[0],0)
            store.close()

    async def test_permanent_failure_disables_future_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            store=WatchStore(Path(directory)/'watch.db')
            store.commit(WatchEngine(),observation(),('1',))
            await deliver_one(store,'fake',('1',),now_ms=1000200,
                              send=lambda *args:{'status':'FAILED','error':'destination_or_auth_rejected'})
            other=observation(); other['observation_id']='b'*64
            store.commit(WatchEngine(),other,('1',))
            self.assertEqual(store.db.execute('SELECT count(*) FROM outbox').fetchone()[0],1)
            store.close()
    async def test_dedup_restart_and_delivery(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"watch.db"
            store = WatchStore(path)
            engine = WatchEngine()
            store.commit(engine, observation(), ("1",))
            store.commit(engine, observation(), ("1",))
            self.assertEqual(store.db.execute("SELECT count(*) FROM outbox").fetchone()[0],1)
            status = await deliver_one(store,"fake",("1",),now_ms=1000200,
                                       send=lambda *args:{"status":"API_ACCEPTED","message_id":7})
            self.assertEqual(status,"API_ACCEPTED")
            store.close()
            store = WatchStore(path)
            self.assertIsNone(await deliver_one(store,"fake",("1",),now_ms=1000300))
            store.close()

    async def test_rate_limit_expires_and_unknown_not_retried(self):
        for response, expected in (({"status":"RETRY_WAIT","retry_after":60},"EXPIRED_UNSENT"),
                                   ({"status":"DELIVERY_UNKNOWN"},"DELIVERY_UNKNOWN")):
            with tempfile.TemporaryDirectory() as directory:
                store=WatchStore(Path(directory)/"watch.db")
                store.commit(WatchEngine(), observation(), ("1",))
                self.assertEqual(await deliver_one(store,"fake",("1",),now_ms=1000200,send=lambda *args:response),expected)
                self.assertIsNone(await deliver_one(store,"fake",("1",),now_ms=1000300))
                store.close()

    async def test_expiry_allowlist_health_and_inflight_recovery(self):
        for mode in ("expired","allowlist","health","restart"):
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/"watch.db"
                store=WatchStore(path)
                store.commit(WatchEngine(),observation(),("1",))
                if mode=="restart":
                    with store.db:
                        store.db.execute("UPDATE outbox SET status='IN_FLIGHT'")
                    store.close()
                    store=WatchStore(path)
                calls=[]
                await deliver_one(store,"fake",() if mode=="allowlist" else ("1",),
                                  now_ms=1030000 if mode=="expired" else 1000200,
                                  healthy=mode!="health",send=lambda *args:calls.append(1))
                self.assertEqual(calls,[])
                self.assertNotIn(store.db.execute("SELECT status FROM outbox").fetchone()[0],("PENDING","IN_FLIGHT"))
                store.close()