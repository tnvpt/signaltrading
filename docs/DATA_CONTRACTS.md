# Data contracts

## Current schema v1 (retained for existing recordings)
Envelope: schema_version=1, source=binance_usdm, type, received_ms, data.
Types: trade, status, alert, session, summary, diagnostic.
Trade: symbol, trade_id (aggregate ID), event_ms (Binance trade timestamp T),
received_ms, positive finite price/quantity, aggressor buy/sell.
Envelope receive timestamp must equal trade receive timestamp.
Status `reset_scanner` defaults true for legacy recordings; HEALTHY transitions
use false. Replay ignores metadata/diagnostics/summary and recorded alerts.
Every session records its config hash, scanner version and endpoint. Files may
contain sequential sessions; run only one collector per output directory.

## Planned schema v2 — implement migration, never change v1 silently
Fields: exchange, market, symbol, event_type, exchange_event_ms (E if present),
trade_ms (T), received_utc_ms, received_monotonic_ns, sequence_id, session_id,
schema_version, payload. Each row must identify session and config provenance.
Preserve original price/quantity strings or tick integers for financial math.

Metadata: tick/quantity step, min quantity/notional, contract unit/type,
trading status, margin constraints and metadata version. Sequence rules are
adapter/stream-specific; do not assume all IDs are contiguous across sources.

## Health
Current HEALTHY means all requested symbols delivered recent structurally valid
trades, not completed scanner warmup or trading eligibility. DEGRADED invalidates
scanner state; missing/quiet symbols trigger reconnect. STOPPED terminates capture.
Target health is per stream: WARMING_UP/HEALTHY/DEGRADED/STALE/DISCONNECTED.
Use exchange-specific cadence and freshness, not one threshold for all streams.

## Future candles/signals
Candle: open/close UTC boundaries, OHLCV, timeframe, closed/forming, revision,
quality, known_at time. Late correction is audited, never silently repaints decisions.
Signal: identity, setup ID, exchange, symbol, side, strategy/config version,
decision/delivery/expiry times, reasons, entry/stop/target, costs, risk, quality,
eligibility and rejection codes. Scores are not calibrated probabilities by default.

## Normative v2 additions and migration
Required envelope adds `ingest_seq` (strictly increasing int per session),
`config_hash`, `origin` in LIVE/REST_BACKFILL/REPLAY_FIXTURE and `stream_id`.
`received_monotonic_ns` only meaningful within that session. Nullable exchange
timestamps remain null if source omits them, never replaced as though exchange
provided them. `symbol` nullable only for session/clock/system events.

Allowed payload discriminators: trade, bbo, mark, depth_snapshot, depth_delta,
instrument_metadata, clock_tick, clock_health, stream_health, session_start,
session_end, diagnostic. Strategy/order/ledger projections have separate contracts.
Trade preserves price/quantity decimal strings, aggregate ID and maker/aggressor,
source event time E separately from trade time T. BBO includes bid/ask prices,
sizes and update ID; reject bid>ask, nonpositive prices or negative sizes. Mark
includes mark/index, funding rate/time when supplied; missing fields remain null.
All fields strict type checked; reject bool as int, nonfinite values, unsupported
schema/discriminator and negative timestamps. Unknown source fields may be retained
in raw payload; unknown normalized contract fields require versioned handling.

Adapter MUST declare source cadence, sequence rules, symbol market discriminator
(e.g. st field), and required freshness per stream. Mismatched market -> reject;
do not accidentally mix UM and CM after venue migrations. Clock/health semantics
in TIME_AND_RECOVERY are part of data contract.

Migration reader dispatches by schema_version. v1 retains original arrival order
and float precision limitations, cannot manufacture historical mark/depth, exchange
E or monotonic time. If a v2-required experiment depends on unavailable v1 fields,
reject dataset as insufficient; no synthetic precision/provenance claims.
Migration preserves original files, emits mapping/checksum report and cannot mark
v1 as equivalent to lossless v2. Retain previous parser fixtures.