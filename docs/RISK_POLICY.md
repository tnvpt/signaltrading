# Risk policy — future engine specification

Default execution disabled. x50/x100 stress profiles may be rejected even when
market setup is valid. Leverage does not define risk budget or stop distance.

Order of calculation: structural invalidation -> stop -> risk budget -> size ->
fees/slippage/depth -> margin/leverage feasibility. Use Decimal/tick integers for
financial math. For linear contracts, quantity * abs(entry-stop) + round-trip
fees + stressed slippage must not exceed risk budget after rounding.

Hard gates: freshness, metadata, stop side/distance, transaction costs, capacity,
portfolio exposure/correlation, liquidation buffer and account-state freshness.
Liquidation cannot be calculated as 1/leverage. It depends on maintenance tiers,
mark price, collateral, fees and exchange rules. Unknown rules/account state ->
liquidation_check UNKNOWN and execution_eligible false. Never fabricate precision.

Research defaults to review: risk/trade 0.1–0.25% equity, total open risk 0.5–1%;
persist daily stop across restarts. No martingale, averaging losses, widening stops
or increasing leverage merely to satisfy minimum notional. Protective stop fills
are not guaranteed. Isolated margin does not make an oversized position safe.

Reject codes include REJECT_STALE_QUOTES, REJECT_NO_MARK_PRICE,
REJECT_COST_TOO_HIGH, REJECT_LIQUIDATION_BUFFER, REJECT_SIGNAL_EXPIRED,
REJECT_PRICE_MOVED_AWAY. Scores/LLMs cannot override hard gates.

## Normative ref-1 paper risk configuration
Fixed risk_fraction=0.001 (0.1%), portfolio open+pending risk<=0.005 equity,
max three positions, max one per symbol. Paper equity starts at 10,000 USDT per
independent profile. Daily drawdown gate: 1% of 00:00 UTC marked equity, including
realized/unrealized PnL and fees; block new entries for rest of day once breached.
Record daily anchor durably. Unknown/unpriced equity blocks new entries and cannot
reset gate. No auto-close solely from daily entry gate; exits remain active.

Cross-coin correlation model deferred: conservatively treat all crypto positions
as one correlated bucket under total risk cap; do not claim this models correlation.
Reference gross notional cap<=2*equity regardless of requested leverage. Reserve
margin for pending orders and fees. No position sizing from desired leverage.

## Exact sizing for linear USDT paper contracts
Use adverse executable entry e (ask for Long, bid for Short), rounded structural
stop s, adverse stop slippage allowance ds per unit, entry slippage allowance de,
and explicit taker fee rates fe/fx. Fee rates must be >=0; no rebate optimism.
Per-unit stressed loss:
  ell = abs(e-s) + de + ds + fe*(e+de) + fx*(abs(s)+ds).
Rbudget=equity*risk_fraction. q0=floor_to_quantity_step(Rbudget/ell).
Then reduce q to meet min(metadata max quantity, capacity cap, free margin cap,
gross notional cap, remaining portfolio risk/ell). Round DOWN after all caps.
Reject if min quantity/notional unmet; never increase q. Verify exact worst-case
loss after rounding using model fills; for nonstandard fee/contracts reject.
Actual fill and target risk accounting uses actual prices; do not double-charge
spread already reflected in bid/ask entry. Slippage assumptions must be explicit.

Cost gate: expected round-trip fees+spread+slippage <=25% of q*abs(e-s), with
spread counted once as a conservative round-trip allowance. Stressed net target
PnL divided by stressed cash loss >=1.5. Both gates must pass; negative target
net PnL rejects. Reference stop floor/ceiling and entry drift in RESEARCH_PROFILE.

## Liquidation feasibility is separate
Reference isolated paper margin requirement = notional/requested_leverage plus
documented fee reserve, subject to exchange leverage tier maximum. Simulate
profiles x1/x5/x10/x20/x50/x100 separately with identical risk sizing inputs;
leverage changes collateral feasibility, not intended cash risk.
Unless verified venue liquidation engine exists, result UNKNOWN, never PASS.
With certified model require Short liq>s+buffer or Long liq<s-buffer, where
buffer=max(2*ds,2*current_spread,0.25*ATR_snapshot), plus mark/last basis stress
defined in venue fixture set. Equality rejects. Re-evaluate after fills/funding/
metadata changes. Price gaps can still exceed this buffer: no safety guarantee.

## Required numeric fixtures
Zero fee is allowed only for an explicit fee-version stating it; missing !=zero.
Test quantity below minimum, changing leverage tier, mark basis shock, stale equity,
simultaneous pending orders and daily-limit restart. Fixture example before caps:
e=100,s=99,de=0.01,ds=0.02,fe=fx=0.0005 -> ell=1.129515 USDT/unit;
Rbudget=10, step=0.01 -> q0=8.85. Subsequent caps may reduce or reject this q.