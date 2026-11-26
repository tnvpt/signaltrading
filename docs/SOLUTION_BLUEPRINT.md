# Solution blueprint — research-spec-1

## 1. Outcome and scope
An explainable market-monitoring and paper-trading system for USDT-settled linear
perpetuals. MVP has one exchange and one-way, isolated-margin paper profiles.
No inverse/quanto, portfolio margin, cross margin, hedge mode or real orders.
MEXC and other exchanges require their own verified adapter/capability matrix.

Three distinct outputs:
1. Observation: unusual activity; no entry/stop or execution eligibility implied.
2. Market signal: versioned technical setup with trigger/stop/expiry.
3. Paper order: signal passed data/cost/portfolio gates under simulated settings.

Market signal can exist while x50/x100 feasibility is UNKNOWN or REJECTED.
No specification requires the system to find a trade every day.

## 2. Fixed design decisions
| Decision | Reference choice | Reason |
|---|---|---|
| Architecture | Python asyncio modular monolith | Existing stack, replay determinism |
| Critical path | Numeric rules, no LLM call | Auditability and bounded processing |
| Timeframes | 3m and 5m separate runs | Avoid duplicate correlated positions |
| Confirmation | CONFIRMED + EARLY30 distinct versions | No disguised intrabar lookahead |
| Source | Binance USDM first, official routed streams | Trade smoke already observed |
| Market orders | Paper only, quote plus adverse cost model | No imaginary limit fills |
| Storage | Raw append journal + SQLite projections proposed | Recoverable evidence and views |
| Parallelism | Single deterministic reducer per run | Stable replay and ordering |
| Frontend/API | Deferred, read-only first | Must not create trading authority |
| ML | Deferred experiment, not required | Rules baseline before complexity |
| Human alerts | User's Telegram bot, dashboard secondary | Concise 3m/5m notifications with 15m/1H context |

SQLite/FastAPI/chart/Parquet dependencies are proposals, not installed components.
Evaluate licensing, supported Python versions and maintenance before adding them.
Do not copy strategy source without license review. Framework examples do not
prove profitability. Freqtrade/Jesse inform lifecycle, HftBacktest execution
realism, NautilusTrader event architecture, CCXT optional REST normalization.

## 3. Capability stages
| Stage | Required input | Permitted output |
|---|---|---|
| Observe | Valid trades + journal | Pump/dump watch events |
| Analyze | Complete bars + baselines + regime | Market candidates |
| Paper basic | Trades, BBO, mark, metadata, fees, paper equity | Conservative BBO paper simulation |
| Paper depth | Above + synchronized depth | Capacity/slippage stress experiments |
| Leverage certified | Above + validated margin/liq rules | Eligible/rejected x50/x100 simulation |
| Execute | Separate approved spec + authorization | Out of scope in this release |

No L2 depth -> execution capacity is UNKNOWN; BBO paper results are labeled
limited-fidelity and cannot certify high-leverage eligibility. No margin model ->
technical paper results remain possible, but liquidation safety cannot pass.

## 4. Component interface contracts (planned)
All reducers accept immutable event + persisted clock/config; they return events
or rejection reasons and cannot read wall clock/network themselves.

| Component | Input | Output / side effect |
|---|---|---|
| Adapter | Official socket/REST payload | Raw event + normalized v2 envelope |
| Journal | Envelope | Arrival-sequence append or fatal storage error |
| HealthReducer | Events + timer ticks | Per-stream health transitions |
| CandleReducer | Accepted trades + recorded clock | Closed bars/corrections |
| FeatureReducer | Closed bars/quotes/mark | Versioned feature snapshot |
| SetupReducer | Snapshot + profile | State transitions / candidate |
| RiskEvaluator | Candidate + cost/meta/account snapshots | Rejection list / paper order intent |
| PaperBroker | Intent + future events/ticks | Acks/fills/exits/account ledger |
| SignalProjection | Lifecycle events | Queryable UI/API read model |
| ResearchRunner | Manifest + journal range | Deterministic report + artifacts |
| NotificationOutbox | Observation/signal lifecycle + allowlist | Durable deduplicated delivery intent |
| TelegramSender | Unexpired outbox item | API acknowledgment/unknown/failure, never an order |

Adapter may do I/O; reducers may not. Record health/timer events before depending
on them for decisions. No write from frontend can bypass RiskEvaluator.

## 5. Universe and deployment
Reference seed universe: BTCUSDT/ETHUSDT only, verified as currently trading USDT
linear perpetuals through metadata. Do not assume a symbol's existence from name.
Expansion policy: daily 00:00 UTC, choose up to 20 eligible symbols by previous
completed 24h quote volume, tie alphabetically; require >=7 days listing/history,
verified metadata and paper capacity gate. Persist selection/as-of inputs. Start
new symbols only after warmup; removals block new entries, never discard positions.

Initial deployment: one supervised Linux/WSL process, one writer/output owner,
explicit config file, synchronized clock, local SSD. Declare host CPU/RAM/disk,
region and event load in benchmark report; no unmeasured VPS sizing promises.
At scale, partition only after measuring reducer/writer bottlenecks. Do not
promise identical cross-partition ordering without a new merge specification.

## 6. Requirements/blocker register
| ID | Required evidence / decision | Blocks |
|---|---|---|
| B01 | Quotes/mark endpoint schema/routing and cadence verified | Paper basic |
| B02 | Fresh instrument metadata + explicit fee schedule | Risk/order sizing |
| B03 | Depth reconstruction and conservative capacity model | High-leverage eligibility |
| B04 | Venue margin tiers, formulas and matched independent fixtures | Liquidation PASS |
| B05 | Clock-offset bound + healthy recorded time source | Time-sensitive eligibility |
| B06 | 24h soak, fault recovery, load budget on declared host | P1 operational signoff |
| B07 | Out-of-sample and forward paper evidence | Strategy promotion |
| B08 | Alert delivery delay and manual reaction budget validated | Manual timing claim |
| B09 | Separate live execution/security spec + user approval | All real orders |

Each evidence artifact includes date, source/version, operator, config/code hash,
command/procedure and pass/fail. A model cannot close blockers using assumptions.
Telegram delivery contract is TELEGRAM_ALERTS.md (telegram-spec-1). B08 requires
measured notification/manual latency, not merely successful Bot API response.
RSI observations can be developed before paper trading with healthy closed bars;
they do not bypass strategy/risk gates for confirmed messages or authorize orders.

## 7. Change/release process
Docs first -> fixtures/contract tests -> small implementation -> offline replay ->
public smoke where lawful -> fault/load test -> research report -> review.
Release manifest records spec/profile/schema/code hashes, dependency lock,
dataset checksums, metadata/fee versions, universe and all experiment IDs.
Research choices may change only as new profiles; never retune an untouched test
and continue calling it untouched. Code changes do not authorize live trading.