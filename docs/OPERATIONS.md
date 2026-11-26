# Operations

No API keys needed; never put exchange secrets in chat/source/logs. Use legitimate
public access only. Run one capture per directory. NTP clock sync required.

Start: `.venv/bin/python -m signaltrading.cli collect --symbols BTCUSDT ETHUSDT --duration 60`
Continuous: `--duration 0`. Ctrl+C drains accepted writer records. Daily JSONL UTC.
`--first-trade-timeout 10 --stale-timeout 10 --queue-capacity 4096` are configurable.
Health transitions and summary counters distinguish handshake, frames, parsed,
fresh trades, rejected/malformed frames and disconnect reasons. A structurally
valid duplicate currently counts in transport stats; not unique executed trades.
CLI exit 2 means some requested symbol never delivered fresh data in that capture;
exit 0 is not a 24h availability or strategy-quality certificate.

No first trade: inspect bounded diagnostic frame, server error, symbols/market,
DNS/TLS/proxy and current official endpoints. Do not retry an unsupported endpoint
forever without diagnosis. No region bypasses. Do not switch exchange silently.

Overflow/disk failure: fatal, stop capture, inspect stderr and disk. Accepted
records drain where storage works; the overflowing event is not accepted. Never
label a truncated session complete. Retention/compression/disk-space monitoring
are not yet implemented; operator must monitor storage. Flush is not fsync or a
guarantee against power failure. Partial final JSONL line must fail validation.

Independent watchdog checks per-symbol silence even if others continue trading.
Thresholds for illiquid symbols need explicit review. Current scanner resets are
conservative and do not backfill. mark/quote/depth health pending future work.

## Target production-research safeguards (not implemented yet)
Single-writer lock; supervisor restart enters WARMING_UP, not ready. Store config,
dependency/code/schema versions and disk budget with every session. Default raw
retention proposal 7 days, compressed archives 30 days only after checksum-verified
copy; experiment datasets pinned against deletion. Never delete active journal or
sole evidence. Require approved retention/disk budget before continuous collection.
Warn free disk<20%, stop new capture/eligibility<10% (configured measured filesystem).

Alert matrix: storage failure/clock unknown/queue overflow -> critical, block new
signals immediately; stream gap/stale -> degraded dependency; all healthy with full
warmup -> recovery notice. Severity never changes accounting/exits silently.
No alert-storm loop: throttle notifications while logging every transition.
Kill switch blocks entries; existing simulated positions remain governed by broker
exit rules. Global stop requires explicit documented liquidation/close policy,
not process termination presented as flattened exposure.

Local-only API by default, no credentials in source, logs or manifests. Remote
access needs TLS/auth and firewall rules. Dependency scans/license inventory,
backup restore test and access-log redaction are release checklist items.
LLM explanations cannot receive secrets or grant order authority. External news
or text is untrusted input, never a command to execution components.

## Telegram operation (planned, not connected)
Primary human notification channel; see TELEGRAM_ALERTS.md. Supply bot token only
via deployment secret and allowlist intended chats. Redact Bot API URL (contains
token). Monitor outbox age/failed/unknown/expired counts independently of market
health. Notifier failure must not block collection or paper exits. No exactly-once
or phone-read guarantee. No catch-up flood after restart; recheck original TTL.
Operator approval required before an actual TEST send. Inbound bot commands and
order buttons are outside this release; no exchange credentials needed.