# Signal lifecycle and proposed read-only API

Normative design only; no API server or UI implemented yet. API delivery never
places orders. Any future acknowledgment endpoint cannot reactivate expired data.

## Signal representation
Required fields: schema_version, signal_id, setup_event_id, run_id, exchange,
market, symbol, strategy_id/version, profile_hash, side, mode, setup_timeframe_s,
decision_ingest_seq, decision_utc_ms, known_at_utc_ms, expires_at_utc_ms, status,
trigger_price, entry_zone_min/max, structural_stop, target, reason_codes,
feature_snapshot_id, metadata_version, cost_model_version, data_quality_snapshot,
paper_eligibility, leverage_eligibility, risk_budget, quantity and notional.
Optional values are explicit null with reason, not absent fabricated numbers.
Financial decimals serialized as strings; timestamps integer ms; side LONG/SHORT.
signal_id = SHA256(run_id|setup_event_id|strategy_version|decision_ingest_seq|side).
Run includes immutable config hash; duplicate emissions of same ID are idempotent.

Leverage map per requested profile: PASS/REJECT/UNKNOWN + reasons; no calibrated
probability field in ref-1. Technical signal does not imply live eligibility.
Delivery timestamps are separate from decision/expiry. Never extend TTL because
delivery was delayed. No risk-rejected candidate sent as actionable signal.

## Lifecycle
Candidate -> risk evaluation -> ISSUED or REJECTED. ISSUED -> CONSUMED (paper intent),
EXPIRED or INVALIDATED. Market-analysis display may show rejected candidates with
clear badge. Signal lifecycle differs from setup lifecycle and position lifecycle.
Order cancellation does not convert consumed signal back to ISSUED.
Event updates append monotonically increasing stream seq; payload has previous
status, new status, reason and known_at. Browser reconnect loads snapshot plus
events after last seq. If history unavailable, full resync, not guessed continuity.

## Proposed endpoints
| Endpoint | Purpose |
|---|---|
| GET /v1/health | Process + dependency health, not readiness to trade |
| GET /v1/market/symbols | Universe and per-stream freshness |
| GET /v1/market/{symbol}/candles | Bounded closed/forming bars + revisions |
| GET /v1/setups | Filtered state transitions with cursor pagination |
| GET /v1/signals | Signals by status/run/symbol, explicit expiry |
| GET /v1/paper/positions | Positions, unpriced flags, equity/risk |
| GET /v1/research/runs/{id} | Manifest and summary, no secret/local paths |
| WS /v1/events | Versioned seq stream, heartbeats and resync instruction |

Default page 100, max1000; cursor stable by sequence, no unbounded full-journal API.
Invalid filters 400, unknown resource404, overload429/503; structured error code
and request ID, no traceback to client. Bind localhost by default. Remote deploy
requires TLS/authentication, origin allowlist, rate limits and access logging.
No endpoint for placing orders in P8. Raw journal/data downloads not public.

## UI acceptance
Show server data age, source exchange, mode, last finalized bar, signal TTL,
rejection reasons, costs, stop and liquidation UNKNOWN when applicable. Forming
bars visually distinct. On lost heartbeat clear actionable display; don't leave a
green signal frozen. Desktop/mobile alerts contain decision and expiry, not only
coin/side. Measure decision-to-browser/notification receipt separately; manual
reaction latency must be included in research before timing claims.

## Telegram notification projection
Telegram is primary human notification; read-only UI/API remains supplementary.
See [TELEGRAM_ALERTS.md](TELEGRAM_ALERTS.md). WATCH_OVERSOLD/OVERBOUGHT observations
have independent IDs/schema and cannot be serialized as confirmed signal with
invented entry/stop. Notification projection links source signal/observation ID,
lifecycle revision, context snapshots, destination allowlist key and template
version. Delivery status is separate from signal status and paper consumption.
API_ACCEPTED means Telegram API acknowledgment, not user read or filled order.
Confirmed notifications retain original ref-1 5s TTL; no extension for HTTP retry.
Do not display risk-rejected candidates as entry recommendations. Grouped 3m/5m
presentation cannot merge IDs, prices, expiry or authorize combined exposure.