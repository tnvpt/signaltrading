# Watch persistence / Telegram implementation report

## Delivered
notifications.py: Decimal indicator checkpoint serialize/restore, SQLite atomic
checkpoint+observation+outbox, unique observation/chat IDs, Linux single-owner lock,
restart IN_FLIGHT -> DELIVERY_UNKNOWN, allowlist, bounded queue, expiry, persistent
destination disabling, watch renderer, secret-safe urllib transport and async sender.
watch.py: checkpoint bridging through REST, persistence per closed analysis, explicit
--telegram opt-in, no sends by default. `.env.example` documents variable names;
no automatic dotenv loading/dependency. TELEGRAM_SETUP.md provides safe interactive
secret entry and explicit TEST-send command.

## Automated evidence
44 tests passed (including original 32). New tests cover checkpoint continuation,
single owner, render/config, HTTP mock success/429/auth/timeout secret safety,
transaction rollback, outbox duplicate/restart/expiry/health/allowlist/permanent
disable, candle->watch->outbox->mock-send->restart with no duplicate.
AST/link checks passed. No real Telegram request was performed.

## Public closed-bar evidence
Recorded eight closed analyses at the same UTC boundary, BTC/ETH x 3m/5m/15m/1h.
All eight OHLCV records matched independent subsequent Binance REST retrieval.
Persisted checkpoint restored eight series. No new RSI watch was created at this
boundary; this is expected, not a failed test or reason to lower thresholds.
The capture artifacts inspected had no final summary; do not certify full-duration
or graceful-shutdown/24h soak completion from these artifacts. Closed-bar input and
analysis are verified; non-empty live watch->real Telegram still unverified.

## Remaining owner-dependent gate
Real bot token/chat allowlist not supplied. Configure privately and run explicit
TEST per TELEGRAM_SETUP.md. Until then actual Telegram delivery is PENDING,
not passed. API_ACCEPTED would still not mean read or measured phone latency.

## Remaining scope
Only watches, not confirmed entry signals, grouping/edit/lifecycle sends, automated
orders, leverage certification, full schema v2 journal/replay or 24h soak. SQLite
sync writes currently in engine path; load test before scaling. Config-version
migration/retention and proactive notifier health supervision need follow-up.