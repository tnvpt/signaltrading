# Architecture and decisions

## Current
Python >=3.11, asyncio and websockets >=14,<16. Modular monolith. Stdlib unittest.
`core.py`: validated Trade, baseline Scanner, daily Recorder, deterministic replay.
`storage.py`: bounded async queue, single disk worker via to_thread, drain on exit.
`ingestion.py`: capture config, per-symbol watchdog, connection supervisor, stats.
`cli.py`: CLI, JSON alert output and explicit unsuccessful-capture exit code.

Recorder writes preserve arrival order. Saturation and disk errors abort capture;
they must never be treated as transient exchange errors. Backoff applies only to
network/protocol/session errors. Session manifest contains config hash/version.

## Target flow
Adapters -> validation/sequencing -> recorder + market state -> candle builder
-> features/regime -> strategy state machines -> risk gate -> signals/paper broker
-> audit/research/API/UI. Live and replay share engines, only clock/source/broker
change. LLM explanations are outside the latency-critical path.

## Proposed, not installed
SQLite for sessions/signals/paper accounting; Parquet when research needs justify
it; FastAPI and frontend only in P8. Add dependencies with pinned compatible
versions, rationale and tests. Do not introduce Kafka/microservices in the MVP.

## Performance objectives (not measured achievements)
p95 receive-to-decision <=100ms at declared symbol/event load; bounded queues,
bounded retention, observable overload. Network clock skew is separate from
internal monotonic latency. Current baseline scanner is O(trades in window) per
event and remains a known scaling limitation pending rolling aggregates.

## Reference learning
Freqtrade/Jesse: strategy lifecycle and validation. HftBacktest: latency/fills.
NautilusTrader: event-driven design. CCXT: REST normalization when justified.
Check licenses before copying code; no strategy has been imported.

## Detailed target contract
See SOLUTION_BLUEPRINT for component boundaries and capability gates,
TIME_AND_RECOVERY for persisted clock/journal semantics, PAPER_BROKER for fill
and ledger rules, SIGNAL_AND_API for read-only delivery. No new module dependency
is implied to exist by these documents. Performance budgets must be tested at
declared load; docs alone do not satisfy p95 or memory acceptance.

## Telegram-first projection (planned)
Observation/signal lifecycle -> durable transactional outbox -> independent sender
-> allowlisted chat. No HTTP wait in reducers. Delivery distinguishes API_ACCEPTED
from DELIVERY_UNKNOWN, supports bounded retry/expiry/restart. Local deduplication
cannot guarantee exactly-once external delivery. Dashboard secondary; API/frontend
not required for basic watches. See TELEGRAM_ALERTS.md; no integration installed.