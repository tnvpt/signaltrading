# Candle-watch MVP execution scope

This narrow milestone supersedes broad P1b-before-everything ordering for the
RSI observation product only. Trades collector retained unchanged. No quote/depth,
liquidation or paper broker needed to describe a closed-candle RSI observation.
They remain mandatory for later trading-risk/confirmed/execution claims.

Packages: (0) config/scope, (1) REST warmup + exchange closed klines, (2) Wilder
RSI14 and EMA context, (3) state/cooldown watches, (4) durable Telegram outbox,
(5) authorized delivery smoke + 24h operations. Numeric rules in RESEARCH_PROFILE.

Current implementation adds candles.py and watch.py without new dependencies.
REST warmup seeds states without catch-up alerts. WebSocket opens before REST
warmup and buffers bounded updates. Candle stream updates, not distance from last
closed 1H candle, determine transport health. Gaps/conflicting close reset/re-warm.
Only finalized exchange candles used; this is an alternative exchange-kline path,
not the future trade-derived 1s-lateness candle reducer. No claim v2 implemented.
MVP clock guard uses <=1000ms bound, not research-spec's stricter certified 250ms.
Indicator Decimal calculations preserve REST price strings. Watch journal types
are separate from v1 trade replay and cannot be passed to old replay CLI.

Known boundaries: cooldown persistence across process restart, watch replay runner,
config hash/checkpoint, full recovery audit, Telegram outbox/renderer and 24h soak
remain outstanding. No confirmed Long/Short, trade sizing or Telegram sending.
Update: checkpoint/cooldown persistence and watch-only Telegram outbox/renderer/
sender are now implemented with mocks; TELEGRAM_SETUP.md is current operational
guide. Actual Telegram TEST still requires private owner configuration. Broader
confirmed/cancel/grouping, full watch replay/config migration and soak remain open.
RSI already extreme during backfill does not create a live watch until rearmed:
prevents historical catch-up floods; this overrides initial-observation notification
wording only for REST backfill, not a fresh live-only feature warmup.

Acceptance: fixtures for RSI/EMA, duplicate/gap bars, independent timeframes,
unknown context, no historical notification, actual REST/WS evidence, named fault
tests. No market signal occurrence required during smoke. All previous tests stay.

## Evidence for first implementation slice
2026-11-26: 32 automated tests passed and compileall passed. Tests include live
loopback WebSocket buffering during REST warmup, four stream heartbeats, RSI
Wilder recursion, EMA seeding, closed/forming parsing, invalid values, gap/conflict,
duplicate handling, cooldown/rearm, independent timeframes and historical silence.
Public 30s smoke obtained 1992 historical candles across BTC/ETH x four intervals
and 800 real-time kline updates across all eight streams, no recovery/error.
No closed candle boundary occurred in that short capture (closed_bars=0); no watch
was expected/emitted. Live closed-bar-to-alert is NOT yet certified by this run.
Tests establish deterministic synthetic watch behavior, not profitability.

Not yet accepted: 24h soak, persistent restart dedup/cooldown, independent indicator
cross-check against another implementation, detailed metadata/clock monitoring,
historical replay for watch journal, Telegram delivery. Keep non-actionable output.