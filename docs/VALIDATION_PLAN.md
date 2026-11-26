# Validation and evidence

## Automated
Run `.venv/bin/python -m unittest discover -s tests -v` from project root.
Current tests cover parsing, replay integrity, scanner warmup/cooldown, real local
WebSocket server, no-data handshake, per-symbol silence, malformed/exchange errors,
reconnect, stale stream, queue overflow, disk errors and cancellation/draining.
Tests use loopback only, no exchange credentials/network requirement.

## Ingestion gates
Short public capture must receive valid trades for every requested active symbol,
not just handshake. Record counts/health/config; incomplete CLI capture exits 2.
Then run >=24h soak; inject network/disk/queue faults; verify recovery and replay.
Measure load/latency/memory explicitly. Current P1 work does not satisfy soak gate.

## P2–P7
Compare UTC 3m/5m candles with exchange. Test boundary/late/duplicate/missing events,
known_at swings, frozen ranges, expiry/conflict, deterministic decisions. Live and
replay must agree for same arrival sequence/config/clock semantics.
Paper fills occur after decision + latency; buy ask/sell bid. Include fees,
funding where applicable, stress slippage, partial fills and conservative limits.
Never assume touched limit fills. If bar hits both stop/target, finer data or
conservative outcome required. Simulate manual delays 1/3/5s separately.

## Research
Time split train/validation/untouched test; purge/embargo overlapping events.
Universe as-of time, including delisted instruments where data supports it.
Record all experiments, limit tuning, inspect parameter stability and costs.
Report expectancy, profit factor, drawdown, streaks, MAE/MFE, fill/expiry ratios,
by side/timeframe/mode/regime. Positive outside-sample expectancy with uncertainty,
acceptable drawdown, cost/latency robustness and forward paper evidence required.
Trade count alone is not evidence; account for dependence and few-outlier profits.

## Reference acceptance matrix (must create fixtures before feature code)
| Contract | Required tests | Gate |
|---|---|---|
| v2 schema | Strict types/nullability, market mismatch, decimal preservation, v1 dispatch | No silent coercion |
| Time | [start,end), 1s lateness, clock skew, tick expiry equality | No future leakage |
| Recovery | Truncated journal, crash before/after durable intent/fill, restart gate | Rebuild same ledger |
| Features | EMA seed, ATR arithmetic, 249-bar baseline, invalid/synthetic bars | Exact decimal/tolerance fixtures |
| Short | Frozen range, strict breakdown, later retest, TTL/invalidations | Deterministic transitions |
| Long | Support threshold, close location, breakout boundary, chase reject | Deterministic transitions |
| Risk | ell=1.129515 fixture, step/min caps, unknown fees/liq, pending reserve | No oversized accepted order |
| Paper | Future quote only, adverse fills, stop gap, funding, duplicate fills | Balanced ledger |
| Delivery | Delayed/duplicate/out-of-order/resync, expired click | No revived signals |

## Load/soak acceptance proposal
Record exact host and real observed workload. Replay measured peak arrival rate
and 2x that rate for 30min, with declared supported universe. Target p95 internal
receive-to-decision<=100ms; zero silent drops; queue/memory bounded by configured
budgets. Report p50/p95/p99, event counts, queue watermark and RSS trend; failure
reduces advertised capacity, not the metric. 24h soak requires no unexplained
sequence loss, no unbounded growth and documented outage/recovery evidence.

## Strategy promotion decision
Pre-register baseline split (chronological 60/20/20 by UTC days when sufficient
history), with embargo at least maximum event lifetime+holding horizon (1800s
for ref-1), purge any event whose observation/position crosses split boundaries.
Limit ref-1 initial comparison to 4 mode/timeframe runs plus declared baseline;
additional parameter trials logged, not hidden. Block-bootstrap by UTC day to
report 95% expectancy uncertainty; with too few independent blocks report
INSUFFICIENT_EVIDENCE, not optimistic confidence. Require positive lower bound
under base costs, nonnegative point estimate under 2x modeled fees/slippage,
max drawdown<=5% for reference risk profile, and >=30 calendar days forward paper
with >=100 completed setups and >=20 active trading days. These are governance
minimums, not statistical guarantees; unmet sample requirement extends study.
Every Long/Short and mode must be assessed separately; rejected variants stay off.
No promotion to live execution follows automatically even if all criteria pass.

## Telegram and RSI observation acceptance
Use TELEGRAM_ALERTS.md section 8 as required named tests. RSI Wilder14 uses
15 valid closes, strict hysteresis rearm >35/<65, separate 3m/5m state and no
entry confirmation from threshold alone. Mock HTTP for API acceptance, 429,
permanent auth failure, ambiguous timeout, expired queued signal and restart.
Verify original TTL unchanged and tokens absent from all captured logs/errors.
Telegram acknowledgment is not device receipt; paper timing claims need measured
notification delay plus manual reaction. Authorized TEST message is a separate
smoke gate, not part of offline unit tests or permission to send trading alerts.