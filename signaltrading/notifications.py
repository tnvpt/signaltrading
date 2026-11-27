"""Durable watch checkpoints/outbox and secret-safe outbound Telegram transport."""

import argparse
import asyncio
from collections import deque
from datetime import datetime
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .candles import Candle, EMA, Series, WatchEngine, WilderRSI


def snapshot(engine):
    series = []
    for (symbol, interval), state in engine.series.items():
        series.append({"symbol": symbol, "interval": interval, "last": state.last.record() if state.last else None,
                       "rsi": vars(state.rsi), "ema50": vars(state.ema50), "ema200": vars(state.ema200),
                       "tail": list(state.ema50_tail), "zone": state.zone})
    return json.dumps({"version": 1, "cooldown_ms": engine.cooldown_ms, "series": series,
                       "last_watch": [[*key, value] for key, value in engine.last_watch.items()]},
                      default=lambda value: str(value) if isinstance(value, Decimal) else value)


def restore(text):
    data = json.loads(text)
    if data["version"] != 1:
        raise ValueError("Unsupported watch checkpoint version")
    engine = WatchEngine(data["cooldown_ms"])
    engine.last_watch = {tuple(row[:3]): row[3] for row in data["last_watch"]}
    for item in data["series"]:
        state = Series()
        if item["last"]:
            row = item["last"]
            state.last = Candle(**{key: Decimal(value) if key in ("open", "high", "low", "close", "volume")
                                   else value for key, value in row.items()})
        for name, cls in (("rsi", WilderRSI), ("ema50", EMA), ("ema200", EMA)):
            values = item[name]
            indicator = cls(values["period"])
            for key, value in values.items():
                setattr(indicator, key, Decimal(value) if key in ("previous", "gain", "loss", "value", "total")
                        and value is not None else value)
            setattr(state, name, indicator)
        state.ema50_tail = deque((Decimal(v) if v is not None else None for v in item["tail"]), maxlen=4)
        state.zone = item["zone"]
        engine.series[(item["symbol"], item["interval"])] = state
    return engine


class WatchStore:
    """One process owns this DB. Checkpoint and observation/outbox commit together."""

    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        import fcntl
        self.lock = path.with_suffix(path.suffix + ".lock").open("a")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock.close()
            raise RuntimeError("Watch database is already owned by another process") from None
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS checkpoint (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS observations (id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS outbox (
              id INTEGER PRIMARY KEY, observation_id TEXT NOT NULL, chat TEXT NOT NULL,
              text TEXT NOT NULL, deadline INTEGER NOT NULL, status TEXT NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0, next_ms INTEGER NOT NULL DEFAULT 0,
              message_id INTEGER, error TEXT, UNIQUE(observation_id,chat));
            CREATE TABLE IF NOT EXISTS disabled_destinations (chat TEXT PRIMARY KEY);
        """)
        with self.db:
            self.db.execute("UPDATE outbox SET status='DELIVERY_UNKNOWN',error='restart_in_flight' WHERE status='IN_FLIGHT'")

    def load(self):
        row = self.db.execute("SELECT data FROM checkpoint WHERE id=1").fetchone()
        return restore(row[0]) if row else WatchEngine()

    def commit(self, engine, watch=None, chats=()):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO checkpoint VALUES (1,?)", (snapshot(engine),))
            if watch:
                self.db.execute("INSERT OR IGNORE INTO observations VALUES (?,?)",
                                (watch["observation_id"], json.dumps(watch)))
                for chat in chats:
                    if self.db.execute("SELECT 1 FROM disabled_destinations WHERE chat=?", (chat,)).fetchone():
                        continue
                    count = self.db.execute("SELECT count(*) FROM outbox WHERE status IN ('PENDING','RETRY_WAIT','IN_FLIGHT')").fetchone()[0]
                    self.db.execute("INSERT OR IGNORE INTO outbox(observation_id,chat,text,deadline,status) VALUES (?,?,?,?,?)",
                                    (watch["observation_id"], chat, render_watch(watch), watch["expires_ms"],
                                     "PENDING" if count < 1000 else "DELIVERY_DROPPED"))

    def expire(self, now_ms, *, unhealthy=False):
        with self.db:
            self.db.execute("UPDATE outbox SET status='EXPIRED_UNSENT' WHERE status IN ('PENDING','RETRY_WAIT') AND deadline<=?", (now_ms+2000,))
            if unhealthy:
                self.db.execute("UPDATE outbox SET status='SUPERSEDED',error='data_unhealthy' WHERE status IN ('PENDING','RETRY_WAIT')")

    def close(self):
        self.db.close()
        self.lock.close()


def render_watch(watch):
    oversold = watch["kind"] == "WATCH_OVERSOLD"
    if watch["kind"] not in ("WATCH_OVERSOLD", "WATCH_OVERBOUGHT"):
        raise ValueError("Only RSI watch notifications are supported")
    labels = {"UP": "TĂNG", "DOWN": "GIẢM", "RANGE": "ĐI NGANG", "UNKNOWN": "CHƯA ĐỦ DỮ LIỆU"}
    context = watch["context"]
    opposing = "DOWN" if oversold else "UP"
    counter = all(context.get(key) == opposing for key in ("15m", "1h"))
    def stamp(value):
        return datetime.fromtimestamp(value/1000, ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%d/%m %H:%M:%S UTC+7")
    return (f"🟡 {watch['symbol']} · {'QUÁ BÁN' if oversold else 'QUÁ MUA'} · {watch['interval']} · Binance USDM\n"
            f"Theo dõi khả năng {'Long' if oversold else 'Short'} — CHƯA xác nhận vào lệnh.\n"
            f"RSI14: {Decimal(watch['rsi']):.1f} | 15p: {labels.get(context.get('15m'), labels['UNKNOWN'])} · "
            f"1h: {labels.get(context.get('1h'), labels['UNKNOWN'])}\n"
            + ("Ngược xu hướng lớn. " if counter else "")
            + "Không vào lệnh chỉ vì RSI; không xác minh x50/x100.\n"
            f"Nến đóng: {stamp(watch['bar_close_ms'])}\n"
            f"Quan sát: {stamp(watch['decision_ms'])} | Hạn gửi: {stamp(watch['expires_ms'])}\n"
            f"Mở Binance Futures: https://www.binance.com/en/futures/{watch['symbol']}\n"
            f"ID: {watch['observation_id'][:12]}")


def telegram_config(environ=None, *, env_file=None):
    if env_file is not None:
        from .telegram_diagnose import read_env_value
        env = {name: read_env_value(env_file, name) for name in
               ("TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_CHAT_IDS")}
    else:
        env = os.environ if environ is None else environ
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chats = tuple(dict.fromkeys(s.strip() for s in env.get("TELEGRAM_ALLOWED_CHAT_IDS", "").split(",") if s.strip()))
    if not re.fullmatch(r"\d+:[A-Za-z0-9_-]+", token):
        raise ValueError("TELEGRAM_BOT_TOKEN missing/invalid. Use --env-file .env to read saved file directly.")
    if not chats:
        raise ValueError("TELEGRAM_ALLOWED_CHAT_IDS is empty. Set numeric chat ID in selected configuration source.")
    if any(not re.fullmatch(r"-?[0-9]+", c) or int(c) == 0 for c in chats):
        raise ValueError("TELEGRAM_ALLOWED_CHAT_IDS must contain nonzero numeric IDs separated by commas, not username/JSON/brackets.")
    return token, chats


def telegram_send(token, chat, text):
    """Returns sanitized classification only; no exception URL/token escapes."""
    request = Request(f"https://api.telegram.org/bot{token}/sendMessage",
                      data=json.dumps({"chat_id": chat, "text": text}).encode(),
                      headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=2) as response:
            data = json.load(response)
    except HTTPError as exc:
        try:
            data = json.loads(exc.read(65536))
        except (ValueError, OSError):
            data = {"error_code": exc.code}
    except Exception:
        return {"status": "DELIVERY_UNKNOWN", "error": "transport_uncertain"}
    if not isinstance(data, dict):
        return {"status": "DELIVERY_UNKNOWN", "error": "invalid_api_response"}
    if data.get("ok") is True and isinstance(data.get("result"), dict) and type(data["result"].get("message_id")) is int:
        return {"status": "API_ACCEPTED", "message_id": data["result"]["message_id"]}
    if data.get("error_code") == 429:
        parameters = data.get("parameters")
        delay = parameters.get("retry_after", 1) if isinstance(parameters, dict) else 1
        return {"status": "RETRY_WAIT", "retry_after": delay if type(delay) is int and delay > 0 else 1}
    if data.get("error_code") in (400, 401, 403, 404):
        return {"status": "FAILED", "error": "destination_or_auth_rejected"}
    return {"status": "DELIVERY_UNKNOWN", "error": "api_outcome_uncertain"}


async def deliver_one(store, token, allowed_chats, *, now_ms=None, send=telegram_send, healthy=True):
    now_ms = time.time_ns()//1_000_000 if now_ms is None else now_ms
    store.expire(now_ms, unhealthy=not healthy)
    if not healthy:
        return None
    row = store.db.execute("SELECT id,chat,text,deadline,attempts FROM outbox WHERE status IN ('PENDING','RETRY_WAIT') AND next_ms<=? ORDER BY id LIMIT 1", (now_ms,)).fetchone()
    if not row:
        return None
    ident, chat, text, deadline, attempts = row
    if chat not in allowed_chats:
        result = {"status": "FAILED", "error": "destination_not_allowlisted"}
    else:
        with store.db:
            store.db.execute("UPDATE outbox SET status='IN_FLIGHT',attempts=attempts+1 WHERE id=?", (ident,))
        result = await asyncio.to_thread(send, token, chat, text)
    status = result["status"]
    next_ms = 0
    if status == "RETRY_WAIT":
        next_ms = now_ms + result.get("retry_after", 1)*1000
        if next_ms + 2000 >= deadline:
            status = "EXPIRED_UNSENT"
        elif attempts + 1 >= 3:
            status = "FAILED"
    with store.db:
        store.db.execute("UPDATE outbox SET status=?,next_ms=?,message_id=?,error=? WHERE id=?",
                         (status, next_ms, result.get("message_id"), result.get("error"), ident))
        if result.get("error") == "destination_or_auth_rejected":
            store.db.execute("INSERT OR IGNORE INTO disabled_destinations VALUES (?)", (chat,))
            store.db.execute("UPDATE outbox SET status='FAILED',error='destination_disabled' WHERE chat=? AND status IN ('PENDING','RETRY_WAIT')", (chat,))
    return status


async def sender_loop(store, token, chats, health):
    while True:
        work = asyncio.create_task(deliver_one(store, token, chats, healthy=health()))
        try:
            await asyncio.shield(work)
        except asyncio.CancelledError:
            await work  # Finish HTTP thread before SQLite closes; no blind resend.
            raise
        await asyncio.sleep(1.1)  # Conservative single sender; no throughput guarantee.


def main():
    parser = argparse.ArgumentParser(description="Explicit Telegram TEST; environment or explicit --env-file")
    parser.add_argument("--confirm-send-test", action="store_true")
    parser.add_argument("--env-file", type=Path, help="Read token and chat IDs from file; ignore old shell values")
    args = parser.parse_args()
    try:
        token, chats = telegram_config(env_file=args.env_file)
    except ValueError as exc:
        parser.error(str(exc))
    if not args.confirm_send_test:
        print("Configuration valid. Nothing sent. Use --confirm-send-test only after approving destination(s).")
        return 0
    results = [telegram_send(token, chat, "TEST SignalTrading — kiểm tra kết nối, KHÔNG phải tín hiệu giao dịch.") for chat in chats]
    print(json.dumps(results))
    return 0 if all(r["status"] == "API_ACCEPTED" for r in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())