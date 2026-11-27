# Telegram setup and verification (Linux / WSL)

## Recommended: explicit .env file (no source/export needed)
From checkout root, privately save straight-quoted token and numeric chat ID(s) in
`.env` using keys TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_CHAT_IDS. Then:
```bash
.venv/bin/python -m signaltrading.notifications --env-file .env
.venv/bin/python -m signaltrading.notifications --env-file .env --confirm-send-test
.venv/bin/python -m signaltrading.watch --duration 0 --telegram --env-file .env
```
The first command validates configuration. The second sends a TEST message.
The third sends RSI alerts on closed candles for the automatically selected
Binance USDT perpetual altcoins (up to 8 by default, ranked by absolute 24h
price change within the configured quote volume range). See the
[watcher options](../README.md) for
the volume filters, or use `--symbols` to monitor a fixed list.
Explicit file overrides stale shell variables for both credentials without executing
shell content or interpolating variables. Without --env-file, environment behavior
below is unchanged. No automatic .env loading. Older environment-only statements
in historical instructions do not limit this new explicit option.

No token has been supplied and no real Telegram message has been sent by the
agent. Automated tests use mocks only. Real-send acceptance remains pending until
the owner privately configures credentials and confirms intended destinations.

## 1. Prepare
Create bot using official @BotFather, open your bot and press Start. Privately
obtain intended numeric chat ID using official Bot API guidance; group chat IDs
may be negative. Never post token in chat/source/logs. Revoke leaked token.
No Binance API key or trading permissions needed. Only RSI watch notifications,
not confirmed entry recommendations, are implemented.

## 2. Set environment without echoing token
In an interactive WSL bash terminal, from project root:
```bash
read -rsp 'Telegram bot token: ' TELEGRAM_BOT_TOKEN; echo
export TELEGRAM_BOT_TOKEN
read -rp 'Allowed numeric chat IDs (comma separated): ' TELEGRAM_ALLOWED_CHAT_IDS
export TELEGRAM_ALLOWED_CHAT_IDS
.venv/bin/python -m signaltrading.notifications
```
The last command validates format only, makes NO request and sends nothing.
`.env.example` lists variable names; application does not auto-load `.env`.
Use a deployment secret manager/environment for unattended operation.

## 3. Explicit TEST send
If Chat ID lookup fails, after exporting token run:
`.venv/bin/python -m signaltrading.telegram_diagnose`.
This checks getMe/getWebhookInfo then getUpdates only without active webhook.
If shell variables do not match `.env`, use
`.venv/bin/python -m signaltrading.telegram_diagnose --env-file .env`.
This explicit diagnostic reads only the token assignment (UTF-8 BOM/CRLF and
straight quotes supported), does not execute the file and overrides process token
for this diagnostic. Watch and TEST also accept an explicit `--env-file`.
No send, webhook deletion or update-offset acknowledgment. Do not run concurrently
with another polling consumer; getUpdates may conflict. Output excludes token,
webhook URL and message text. Share only sanitized status if troubleshooting.

After verifying that the allowlist is yours, this command is explicit consent:
```bash
.venv/bin/python -m signaltrading.notifications --confirm-send-test
```
Expect API_ACCEPTED with message_id and personally check the TEST on your device.
API_ACCEPTED does not prove read/delivery timing. Timeout -> DELIVERY_UNKNOWN;
do not blindly rerun, first check chat. No token is printed in sanitized errors.

## 4. Start monitoring (explicit permission to send watches)
```bash
.venv/bin/python -m signaltrading.watch --duration 0 --telegram
```
Without `--telegram`, no sends occur. Existing trade CLI is unchanged. State and
outbox stored at data/candle-watch/watch.sqlite3, unique observation/destination
constraint, FULL SQLite synchronization and single-owner Linux flock. Reuse the
same output to resume checkpoints. No two writers to same output. Corrupt checkpoint
fails rather than silently resetting. Preserve DB/WAL during backup.

REST bridges saved indicators when previous last candle exists unchanged in the
250-row fetched history; otherwise full warmup and no historical watch flood.
Saved cooldown survives either path. Pending alerts at restart are superseded;
in-flight deliveries become DELIVERY_UNKNOWN, never blindly resent. Destination
auth/permission failure persistently disables it: inspect configuration, then
use a separately reviewed maintenance procedure before re-enabling (no automatic
reenable command in MVP).

## Tests and remaining limits
Run `.venv/bin/python -m unittest discover -s tests -v`. No live sends in tests.
Only watch delivery, not grouping/edit-cancel/confirmed notices, implemented.
No 24h soak claim, no latency guarantee, no known phone read time. SQLite operations
are synchronous small transactions; measure load before broadening universe.
No config migration across strategy version changes yet; keep rsi-watch-1 unchanged.
Cooldown/outbox tables have no retention yet; monitor disk. On notifier task failure,
process reports it at next supervise iteration; independent always-on notifier
health/alerts need further operational work. No real orders or x50/x100 safety claim.