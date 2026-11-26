# SignalTrading — solution specification index

Specification release: **research-spec-1**, 2026-11-26. Status: implementation
contract for offline research and paper trading, NOT approval for real-money use.
This release changes documentation only. Existing runtime remains the P1a trade
collector/baseline scanner, not the strategies specified here.
Addendum **telegram-spec-1** specifies primary Telegram delivery and independent
`rsi-watch-1` observations without changing ref-1 entry conditions.

## Read in order
1. [PRODUCT_SPEC.md](PRODUCT_SPEC.md): scope, users and non-goals.
2. [SOLUTION_BLUEPRINT.md](SOLUTION_BLUEPRINT.md): decisions, capability gates,
   component interfaces, deployment and unresolved prerequisites.
3. [ARCHITECTURE.md](ARCHITECTURE.md): present code versus target architecture.
4. [DATA_CONTRACTS.md](DATA_CONTRACTS.md) and [TIME_AND_RECOVERY.md](TIME_AND_RECOVERY.md):
   event schemas, ordering, bars, warmup, corrections and restart.
5. [RESEARCH_PROFILE.md](RESEARCH_PROFILE.md): reference parameters/formulas.
6. [STRATEGIES.md](STRATEGIES.md): exact reference state transitions.
7. [RISK_POLICY.md](RISK_POLICY.md): rejection gates, sizing and leverage.
8. [PAPER_BROKER.md](PAPER_BROKER.md): fills, exits, fees and accounting.
9. [SIGNAL_AND_API.md](SIGNAL_AND_API.md): lifecycle, delivery and proposed API.
10. [VALIDATION_PLAN.md](VALIDATION_PLAN.md): acceptance and research gates.
11. [OPERATIONS.md](OPERATIONS.md): operational safeguards.
12. [TASKS.md](TASKS.md): implementation sequence and definition of done.

Primary user notification: [TELEGRAM_ALERTS.md](TELEGRAM_ALERTS.md). Read alongside
RESEARCH_PROFILE and SIGNAL_AND_API before notifier implementation.
Implemented watch-only setup: [TELEGRAM_SETUP.md](TELEGRAM_SETUP.md); broader
TELEGRAM_ALERTS features remain target contract, not all implemented.
Evidence and pending gates: [WATCH_TELEGRAM_REPORT.md](WATCH_TELEGRAM_REPORT.md).
Narrow candle-watch implementation sequence: [MVP_EXECUTION.md](MVP_EXECUTION.md).

Historical evidence: [P0_P1_REPORT.md](P0_P1_REPORT.md) and
[INGESTION_ROUTING.md](INGESTION_ROUTING.md). They describe observed work, not
normative future behavior. Local result files are not production certificates.
Documentation gap analysis and remaining evidence gates: [SPEC_REVIEW.md](SPEC_REVIEW.md).

## Interpretation rules
- MUST/REJECT = mandatory contract; REFERENCE = unvalidated research choice.
- Current code/README CLI descriptions describe implemented behavior only.
- Reference formulas in RESEARCH_PROFILE and transitions in STRATEGIES supersede
  earlier prose sketches. RISK_POLICY hard gates always take precedence.
- Unknown required data -> explicit rejection, never an invented default.
- Any intentional change to formulas, bar timing, fills, risk or thresholds creates
  a new config/spec version and requires fixtures and research rerun.
- If documents conflict, stop the affected task, record the conflict and resolve
  it in a documented decision; do not silently choose convenient behavior.
- A model must not label a component implemented merely because it is specified.

## Document completeness boundary
This release fixes a deterministic baseline for research, not the best strategy.
Actual profitability, current exchange metadata/fees, certified liquidation math,
deployment capacity and live execution authorization remain evidence gates. See
the blocker register in SOLUTION_BLUEPRINT. P10 requires a separate specification.