# P0/P1a implementation evidence

## Delivered
- Eight handoff specifications (product, architecture, contracts, strategies,
  risk, validation, operations and ordered tasks).
- Separated ingestion supervisor and bounded async writer from CLI.
- Symbol watchdog, first-valid-trade timeout, reconnect, bounded diagnostics,
  server-error reporting, session config hash and capture summary.
- Stricter live/replay Trade validation; preserved schema v1 recordings.
- Incomplete CLI capture exits 2 rather than calling handshake a success.
- Fatal storage errors are distinguished from reconnectable network errors.

## Automated evidence
19 tests passed, including 8 original tests and 11 added cases. compileall passed.
Loopback WebSocket tests exercise real sockets, malformed/server errors, silent
handshake, missing symbol, stale stream, recording/replay, reconnect, cancellation,
overflow and disk failure. These are not production/latency/soak certification.

## Public smoke evidence
2026-11-26: 25-second configured capture requested BTCUSDT and ETHUSDT.
Handshake completed; zero application frames/trades received. Watchdog reported
first_valid_trade_timeout:BTCUSDT, reconnected, then reported incomplete capture.
Endpoint used: wss://fstream.binance.com/stream?streams=btcusdt@aggTrade/ethusdt@aggTrade
This confirms failure observability, NOT working exchange market-data delivery.
This was the historical result before routing diagnosis. Follow-up established
that the current SDK routes aggTrade via /market/stream; changing the default
produced actual BTC/ETH trades. See INGESTION_ROUTING.md for source/probe evidence
and the successful 349-trade capture. No access bypass or exchange substitution.

## Remaining gates
Extended per-symbol freshness/availability, quote/mark streams, schema v2,
rolling aggregates/memory cap, raw numeric precision, benchmarking and >=24h soak.
No entry strategy, risk engine, paper broker, API/UI or live orders implemented.
Workspace currently has no .git; no commit/push was performed.