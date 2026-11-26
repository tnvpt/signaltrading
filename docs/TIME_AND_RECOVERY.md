# Event time, candle finalization, replay and recovery

Normative target; current schema v1 collector does not implement this contract.

## 1. Ordering and clocks
- Each recorded arrival receives increasing `ingest_seq` per session. Preserve
  socket order; simultaneous sockets are ordered by the recorder's assigned seq.
- UTC epoch ms identifies market/bar times; monotonic ns measures process delay
  and deadlines. Monotonic values cannot be compared across process restarts.
- Persist `clock_tick` every 250ms and `clock_health` changes. All expiry/freshness
  decisions in reducers use those events, not replay machine time.
- Measure bounded clock offset against a documented reference. Reference gate:
  offset uncertainty <=250ms and last check <=60s; otherwise UNKNOWN/NO_TRADE.
  RTT/2 is an uncertainty estimate, not proof of one-way network delay.
- Global event replay uses ingest_seq; do not sort history by trade timestamp and
  accidentally supply late information earlier than it was received.

## 2. Bar intervals and finalization
Timeframes: 15s, 30s, 1m, 3m, 5m, 15m, 1H, all UTC aligned.
For interval D ms, start=floor(trade_ms/D)*D, end=start+D; membership [start,end).
Reference allowed lateness L=1000ms. Finalize on first recorded clock tick whose
UTC >= end+L, only with clock health acceptable. `known_at` is that tick's seq/time.
Earliest signal using this bar is known_at, never end itself or an earlier close.

Within unfinalized bars order accepted trades by (trade_ms, aggregate_id) for
open/close; high/low over all accepted trades; volume summed once per unique ID.
Track base volume, quote notional and aggressor notional. Distinguish aggTrade
count from number of underlying fills; do not call aggregate count raw trade count.

Trades arriving after finalization yield an audited correction revision in a
separate corrected-data projection. They do not rewrite prior signals/PnL.
Arrival-faithful replay uses original finalizations; corrected-data experiments
must be labeled and cannot be reported as live-equivalent.

## 3. Empty bars, gaps and duplicates
Empty interval with healthy transport may produce a synthetic flat bar at prior
close, volume=0, `synthetic=true`; it is not admissible for reference setup,
ATR/volume baseline or regime warmup. No prior close -> no bar, explicitly missing.
Synthetic bar is not evidence the connection was healthy: health is independent.
Any gap/corrupt/stale stream marks overlapping bars incomplete. Required rolling
features must wait for a full valid window after discontinuity or verified
backfill. No interpolation and no false volume. Duplicate IDs with identical
payload are ignored for market features; conflicting duplicate payload -> DEGRADED.
Use adapter-defined contiguous IDs only where official semantics support them.

## 4. Backfill and warmup
Historical data has origin=REST_BACKFILL and actual availability time. It can warm
bar-based indicators if complete and schema-compatible; it cannot retroactively
create live entries, historical quote freshness, depth continuity or order fills.
Require all exact lookback windows in RESEARCH_PROFILE, no shortened estimates.
Do not mix snapshots from later metadata/universe into earlier research periods.

After discontinuity: invalidate active setups and pending entry intents; existing
paper positions remain open and UNPRICED/DEGRADED until valid prices return.
Never assume an outage exited at the old stop. Report adverse uncertainty.

## 5. Recovery/journaling
Target journal v2 is append-only with session, ingest_seq, hash/checksum manifest;
SQLite signal/order/ledger tables are rebuildable projections. Accepted in-memory
queue is not durable acknowledgment. Mark durable checkpoints only after the
documented flush/fsync boundary. Missing fsync leaves crash-loss risk explicit.

On startup: acquire single-writer lock, validate manifest/files, quarantine partial
tail (retain bytes), record recovery event, rebuild/checkpoint projections, reconcile
paper ledger, enter WARMING_UP. Do not silently skip corrupt records or claim a
complete session. New process/session ID, metadata/time/stream freshness rechecked.
Do not resend old READY signal or pending simulated entry after restart. Existing
positions recover from durable ledger and remain flagged if gap prevents pricing.

## 6. Tie precedence
On an event at an expiry boundary (`now >= expires_at`), expiry wins over entry.
Invalidation/data-failure wins over confirmation from the same event. Then process
exits for existing positions, setup transitions, candidate arbitration, risk,
new paper intents. Fills cannot precede order eligibility; see PAPER_BROKER.