# Handoff / ordered work packages

Each PR/task: list scope, dependencies, files, test commands/results, live evidence,
known limitations. No placeholders claimed complete. Do not push or enable live
trading without explicit request. Preserve CLI compatibility and schema v1 replay.

| Package | Scope / modules | Dependencies | Acceptance |
|---|---|---|---|
| P0 | Audit existing collector/schema/config, docs | Existing baseline | Explain no-data case; failures observable |
| P1a | ingestion.py/storage.py, validation, watchdog/tests | P0 | Mock/replay/fault tests; actual trades verified separately |
| P1b | quotes/mark adapters, v2 envelope, bounded rolling aggregates | P1a | Per-stream health, same replay decisions, benchmark and soak |
| P2 | market/candles, metadata, late events | P1 | UTC 3m/5m parity; no future leakage |
| P3 | features/structure/regime | P2 | Fixtures, known_at timing, pre-event baselines |
| P4 | strategies/state machines | P3 | Both hypotheses, expiry/conflict/duplicate/negative tests |
| P5 | risk sizing/cost/eligibility | P2/P4 | Missing data rejects; rounding/stress cases |
| P6 | paper broker/accounting | P4/P5 | No pre-decision fills; reconcile equity/fees |
| P7 | research reports/walk-forward | P6 | Reproducible manifests and outside-sample results |
| P8 | API/UI | P4–P7 | Health, expiry, evidence; no stale actionable notifications |
| P8T-W | Telegram RSI watch delivery | P1/P2/P3 RSI + persisted outbox | Watch-only templates, mocks, secret redaction, dedup/retry/expiry |
| P8T-S | Telegram confirmed/lifecycle delivery | P4/P5 + P8T-W | Risk gating, original TTL, cancellation, unknown delivery handling |
| P9 | shadow operation | P7/P8 | Restart/soak/fault evidence |
| P10 | execution, separately authorized | All gates | Idempotency, reconciliation, protection, kill switch |

## Current boundaries
P0/P1a implementation is not P1 completion. No strategy, paper broker, financial
accounting, mark/quote data or liquidation calculator exists yet. Fix raw capture
before building signals. Code tests do not replace public endpoint or soak tests.

## Latest evidence
Aggregate-trade route fixed to /market/stream using official SDK source and
controlled probe. Public smoke: 349 BTC/ETH trades, no data issues/reconnects,
20 tests passed. See INGESTION_ROUTING.md. This does not complete P1b or soak.

## Next model
The approved narrow observation-MVP implementation is described in MVP_EXECUTION.md;
it relaxes quote/depth prerequisites for RSI watches only. Current slice implements
closed-kline warmup/stream engine; Telegram and durable restart state remain pending.
Read docs/README.md and review relevant contracts before further feature coding.
The prior documentation-only hold ended with approved MVP coding. research-spec-1 is a deterministic research baseline, not
trading approval. Do not invent measured latency, profitability, exchange support
or liquidation safety. No LLM in critical path. Risk can reject x50/x100.

## Definition of ready for each package
Owner reads relevant spec, resolves listed blockers, pins config/contract version,
adds named boundary/failure fixtures and dependency/license rationale before code.
P1b MUST first deliver v2 migration/clock/health contracts, then quote/mark routing
verification, then bounded rolling aggregates and soak. P2 needs candle timing
fixtures from TIME_AND_RECOVERY; P3 needs numerical RESEARCH_PROFILE fixtures;
P4 needs each STRATEGIES boundary; P5/P6 need sizing/ledger examples.
Each item has scope, dependency, changed files, test command/result, artifact path,
known limitations and reviewer. No multi-package completion claim from one smoke.

## Definition of done
Contract tests + negative/fault tests pass; existing fixtures retained; deterministic
replay and accounting where relevant; docs updated; actual evidence distinguished
from targets; no undeclared keys/placeholder behavior. Test coverage percentage
alone cannot substitute named safety invariants. No push or real order permission
is implied by task approval. Future live execution requires separate P10 spec.

## Telegram-first dependency clarification
P8T-W need not wait for dashboard or paper broker; it emits non-actionable watches
only. It still requires verified data/closed candles, RSI fixtures and durable
notification storage. P8T-S cannot skip strategy/risk gates; claims of manual timing
require P6/P7 delay research. P8T-W completion never implies confirmed signals.
Read TELEGRAM_ALERTS.md before implementation. Actual test message requires explicit
approval/allowlisted chat; never request or write token during documentation work.