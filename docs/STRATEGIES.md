# Strategy hypotheses — not implemented / not proven profitable

## Shared
Context 15m/1H, setup independently tested on 3m and 5m. Confirmed uses closed
setup bars; Early uses separately versioned closed 15s/30s confirmation. Baselines
exclude current event. Define all thresholds in config before testing. Save
parameter-search history and frozen support/resistance at known_at timestamps.
No swing requiring future bars is usable before confirmation time.

## Failed Pump Reversal Short
IDLE -> PUMP_DETECTED -> POST_PUMP_RANGE -> BREAKDOWN_CONFIRMED -> RETEST_PENDING
-> READY -> TRIGGERED; every active state supports INVALIDATED/EXPIRED.

1. Detect return/volume anomaly using pre-event volatility/volume baseline.
2. After configured minimum closed microbars, freeze post-pump range boundaries.
3. Confirmation closes below frozen low by max(tick buffer, volatility buffer).
4. Require retest in configured deadline; no retest means skip, not chase.
5. Closed-bar rejection on retest plus valid stop beyond invalidation -> risk gate.
6. Entry executable only after decision; Short market fills against bid + costs.

Invalidate on reclaimed structure, new high invalidating original setup, data
failure, excessive spread, expired retest or insufficient room to target.
At most one trigger per pump event in v1; reentry is a separate experiment.

## Breakout Hold Continuation Long
IDLE -> IMPULSE_DETECTED -> PULLBACK_FORMED -> SUPPORT_HELD -> BREAKOUT_CONFIRMED
-> READY -> TRIGGERED; INVALIDATED/EXPIRED supported.

Freeze consolidation/support from closed bars; require support hold and breakout
confirmation. Reject if entry moved too far from trigger. Long market fills at ask.
Stop below structural invalidation. Do not mirror Short parameters automatically.

## Conflict/lifecycle
One eligible side per symbol; conflict -> NO_TRADE. Deterministic setup IDs,
cooldown, TTL, price-moved-away check and audited transitions. Late/backfilled
data may warm features but must never generate historical live entry signals.

## Normative ref-1 transitions (supersedes discretionary sketch above)
Use RESEARCH_PROFILE formulas, ATR_snapshot and buffer b, frozen at detection.
Terminal reason and every source ingest_seq MUST be persisted. No same-event
transition chain may use a range built using the bar which breaks that range.

### Shared post-pump range
Collect exactly four 30s bars following detection bar. Until range freeze, update
event_high from all accepted event trades. Freeze H=max(high of those four),
L=min(low), V=event_high and F=finalization time of fourth post bar.
If H-L<=0 or H-L>1.5*ATR_snapshot -> INVALIDATED(RANGE_NOT_COMPACT).
No synthetic/incomplete bar admissible. Total TTL or required health failure wins
over range creation. No transition tests use confirmation bars starting before F.
Short and Long hypotheses share setup_event_id but run independently in research.

### Short transitions
1. At freeze require regime DOWN/RANGE; otherwise INVALIDATED(REGIME_FILTER).
2. After F, first closed C-bar close < L-b confirms breakdown. Must occur before
   min(F+300s, event expiry). Store breakdown known_at D and event high so far Vd.
3. Only a later C-bar whose start >=D can confirm retest. Its high must be >=L-b
   and <=L+b; close <L-b and close-location<=0.35. Bounds inclusive except strict
   close comparisons. Any accepted trade price >Vd+b or C-close>L+b before entry
   invalidates. No retest before min(D+180s,event expiry) -> EXPIRED.
4. On valid retest, trigger_price=that close, stop_raw=max(Vd,retest high)+b.
   Freeze stop then pass candidate to risk gate. Do not update stop to fit risk.
5. One candidate evaluation at this decision; rejection terminates this hypothesis
   REJECTED(reason). No repeated evaluation until gate eventually passes.

### Long transitions
1. At freeze require regime UP/RANGE, L>=P0+0.5*(impulse_high-P0), and each of the
   four post closes >=that support threshold; else INVALIDATED(SUPPORT_NOT_HELD).
2. Frozen support=L. Any accepted trade price <L-b invalidates before entry.
3. First C-bar starting >=F that closes >H+b with close-location>=0.65 confirms
   continuation, before min(F+300s,event expiry).
4. trigger_price=that close, stop_raw=L-b, then one risk evaluation. No mandatory
   second retest in Long ref-1. Chase/drift gate limits adverse executable entry.

### Stop/target and event processing
Short stop rounded UP to tick; Long stop rounded DOWN. Compute target from
actual intended executable entry and rounded stop at 2R; Long target round DOWN,
Short target round UP (conservative). Nonpositive target -> reject.
Terminal hypothesis cannot revive. Candidate rejected by missing data does not
become valid later without a new versioned setup event after cooldown.
Regime filter uses the frozen detection-time regime, not a later value chosen
after seeing the outcome. Long and Short sub-hypotheses share one pump event;
event cooldown begins when both are terminal, or after a signal is consumed.
On consumption cancel sibling hypothesis. In independent research accounts use
the same detected event identity, but each account keeps its own lifecycle.
Target is frozen at intent using then-executable entry, not moved after actual
fill to manufacture 2R. Recheck actual net reward/risk before filling; reject if
the fixed target no longer meets gate. Stop never changes after intent.

### Arbitration within one paper run
Collect candidates with same decision ingest_seq. If opposite sides conflict on
same symbol -> reject both CONFLICT. Across profiles, research uses separate
paper accounts; production combination is out of scope. For multiple symbols,
sort by detection known_at then symbol then strategy_id before reserving risk.
One open/pending position per symbol, at most three portfolio positions, reserve
pending risk atomically. A trade from one symbol cannot consume risk twice.

### Required fixtures
- Close exactly L-b is not Short breakdown; H+b is not Long breakout.
- Expiry boundary equal to confirmation time expires, no trigger.
- Future-confirmed swing/pattern cannot alter old state.
- No microbar from post-range construction can also be breakout confirmation.
- Failure/recovery does not resurrect setup; no same pump reentry.
- Short retest high above L+b fails retest even if final close looks bearish.
- Stop rounded away from entry may make trade fail risk; never round toward entry.