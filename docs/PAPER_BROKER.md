# Paper broker and accounting — target contract

## Fidelity modes
1. BBO_BASIC: best bid/ask + configured adverse slippage, limited-fidelity only.
2. DEPTH_STRESS: walk synchronized visible book, plus adverse latency/slippage.
Neither mode recreates own market impact, hidden liquidity or guaranteed fills.
Missing depth -> capacity UNKNOWN; cannot certify x50/x100 feasibility.

Reference taker-only paper intents; no resting limits, scaling, trailing, partial
profit taking or stop widening in ref-1. Any such change is a new broker/profile.

## Entry and latency
Order intent contains signal_id, idempotency key, side/quantity, stop/target,
eligibility time and expiry. Persist intent before simulation. Reserve risk and
margin atomically, release on reject/cancel. No actual exchange submission.
Latency scenarios: automated paper 250ms; manual paper 1s/3s/5s, separate reports.
Fill only at first eligible *future* quote event (ingest_seq after intent) with
received time >=decision+latency and <expiry. At equality expiry wins.
Do not fill using the quote that caused decision even if latency=0 in tests.
With ref-1 TTL=5s, the manual 5s scenario cannot fill (expiry wins). This is an
intentional viability test, not a reason to extend expired signals. A longer TTL
requires a distinct research profile and renewed timing validation.

Recheck health, entry drift, affordability and signal validity at fill attempt.
BBO_BASIC requires fresh quote with top-of-book displayed quantity >=order size;
otherwise reject INSUFFICIENT_VISIBLE_SIZE (not a full depth-capacity guarantee).
Adverse slippage reference=max(1 tick, 2 bps of price). Long fill ask+slippage
rounded UP; Short bid-slippage rounded DOWN. Fee charged on actual notional.
If actual risk exceeds reserved budget, reduce quantity before simulated fill
or reject; do not fill first and claim a later retroactive risk adjustment.

DEPTH_STRESS uses available book levels up to configured cap; conservative
all-or-none entry rejects insufficient depth. Never consume more visible quantity
than modeled. No invented partial entry in reference profile.

## Exit precedence and execution
Stop-market: use declared trigger source, ref-1 LAST trade; mark-trigger experiment
must be separate. At stop breach create exit intent, then use next eligible quote
after exit latency (250ms reference), not stop price as guaranteed fill.
Long closes at bid-adverse slippage; Short at ask+adverse slippage.
Target is a market-exit trigger: Long bid>=target, Short ask<=target; it is NOT a
resting take-profit limit and can fill worse later. Maximum hold 900s triggers
market exit independently of profit. Prioritize stop, then target, then time exit
when indistinguishable; all original events remain ordered by ingest_seq.
After exit intent, no new entry; existing exposure remains until actual paper fill.
If data unavailable, keep position OPEN_UNPRICED; never assume it exited at stop.
If visible exit size is insufficient in BBO_BASIC, do not reject/erase the open
position: keep EXIT_PENDING/UNPRICED, record insufficient liquidity, and retry on
future eligible quotes. This can underestimate executable tail risk; reports
with unresolved exits are incomplete and cannot pass promotion. DEPTH_STRESS
requires its own explicit exit-depth/gap policy before certification; absent
policy -> no high-leverage feasibility PASS.
Certified liquidation event, if applicable, preempts a not-yet-filled protective
exit; apply venue-specific fees and residual rules, otherwise report UNKNOWN.

## Funding and ledger
Use Decimal and immutable double-entry-equivalent balanced ledger entries for
cash, fees, realized PnL and funding; quantities per symbol reconciled to fills.
For linear contracts: realized=q*(exit-entry) for Long, q*(entry-exit) for Short.
Unrealized uses mark, separately labeled executable liquidation value uses bid/ask.
Equity=cash+unrealized; margin is reserved collateral, not an expense.
Funding applied at actual venue funding timestamp/rate to eligible open position
using venue convention. Missing funding during an exposed interval -> incomplete
report, not zero assumed. Borrowing/interest out of scope for perpetual ref-1.
Cash must reconcile `initial_cash + realized_PnL - fees + signed_funding`.
Funding is signed; fees are a positive expense and must not be deducted twice.

## Recovery and fixtures
Never apply same fill/funding twice: stable ID + transactional unique constraint.
Checkpoint includes pending intents, reservations, positions and funding IDs.
Required tests: latency crossed expiry, quote moved outside entry zone, stop gap,
both stop/target in ambiguous bar, funding while open, fee rounding, crash/replay
idempotency, disk outage and unpriced position. No PnL certification from OHLC-only
fills for sub-minute strategy. Report each fidelity level explicitly.