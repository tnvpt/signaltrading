# Deterministic reference profile — ref-1

**Unvalidated research defaults, not optimized parameters or trading advice.**
These values resolve implementation ambiguity so independent models can produce
the same fixtures. Any change creates a new config hash. No automatic tuning in
live monitoring. Fees, metadata, capacity and margin rules are NOT guessed here.

## 1. Run identity and units
Run one setup timeframe S in {180,300}s and one confirmation mode in
{CONFIRMED,EARLY30}. Confirmation interval C=S for CONFIRMED, C=30s for EARLY30.
Use 30s microbars for impulse/range construction in both modes. Higher-timeframe
context 15m/1H; only closed, complete, known bars. Evaluate 4 configurations
independently, not four concurrent positions on a symbol. All decimals below are
dimensionless fractions unless named bps (1bp=0.0001); seconds are durations.

## 2. Reference features
| Feature | Exact definition |
|---|---|
| TR | max(H-L, abs(H-prevClose), abs(L-prevClose)) |
| ATR14 | Arithmetic mean of last 14 valid TRs on S; requires 15 contiguous S bars |
| EMA(N) | Seed SMA of first N contiguous valid closes, then alpha=2/(N+1); alpha*close+(1-alpha)*prevEMA |
| Body fraction | abs(close-open)/(high-low); zero range -> 0 |
| Close location | (close-low)/(high-low); zero range -> 0.5 |
| VWAP(event) | Sum(price*base_quantity)/sum(base_quantity), accepted trades from impulse start through current known time |
| Q(bar) | Sum accepted trade price*quantity in USDT, not base volume |
| R120(k) | close30[k]/close30[k-4]-1 |
| Q120(k) | Sum Q over bars k-3..k inclusive |

EMA regime: after EMA50 and EMA200 on 15m plus EMA50 on 1H available,
UP if 15m close>EMA200, EMA50>EMA200, EMA50[k]>EMA50[k-3], and
1H close>EMA50. DOWN is all reversed; otherwise RANGE. UNKNOWN if missing/invalid.
Regime values are frozen in candidate evidence, updated only on their bar closes.
Short reference allows DOWN or RANGE; Long reference allows UP or RANGE.

## 3. Impulse detector on every closed 30s bar k
Before testing k, build B from the 240 completed 120s windows ending at indices
k-244..k-5. Each window requires its 5 closes and 4 volume bars; all data contiguous
and complete. Thus minimum 249 valid 30s bars for this detector. Windows overlap:
this is a descriptive baseline, not 240 independent observations.

Let m=median(R120 in B), d=median(abs(R120-m) in B),
sigma=max(1.4826*d,0.001), q=median(Q120 in B).
q<=0 or insufficient data -> WARMING_UP, no event.

Pump if R120(k)>=max(0.01,m+4*sigma) AND Q120(k)/q>=2.
Both inequalities inclusive. Snapshot ATR14 on S, baseline and regime at detection;
unknown ATR/regime -> no strategy event (watch observation still permitted).
Impulse anchor P0=close30[k-4], impulse high=max(high30[k-3..k]), start=time of
bar k-3 start, detection known_at=bar k finalization. Event return threshold is
not a claim that a 1% move is universally unusual.

Each symbol/profile has at most one active pump event. Further impulses do not
extend/reset it. After terminal state, 300s cooldown before detecting a new event.

## 4. Parameter table
| Parameter | ref-1 | Meaning |
|---|---:|---|
| post_bars | 4 | Four subsequent closed 30s bars, excludes detection bar |
| range_max_atr | 1.5 | Frozen post range height <=1.5*ATR_snapshot |
| buffer | max(2*tick_size,0.10*ATR_snapshot) | Freeze with event |
| total_event_ttl_s | 900 | Since detection known_at; never extended |
| breakout_wait_s | 300 | Since range freeze |
| retest_wait_s | 180 | Since Short breakdown confirmation |
| min_net_reward_risk | 1.5 | Gate using stressed cash loss and net target PnL |
| target_R | 2 | Structural price-risk multiple before costs |
| maximum_hold_s | 900 | From first paper fill |
| signal_ttl_s | 5 | From decision; later user clicks cannot revive it |
| entry_drift | 0.10*abs(trigger_price-stop) | Max adverse distance from reference trigger |
| stop_floor | max(4*ticks,2*current_spread) | Reject narrower stop |
| stop_ceiling | 1.5*ATR_snapshot | Reject wider stop; never force it narrower |

## 5. Volume and pattern roles
Candlestick body/wick, event VWAP, trade delta and book imbalance may be displayed
as diagnostic features. They are NOT implicit entry conditions in ref-1 except
close-location condition explicitly in STRATEGIES. Adding RSI/divergence/absorption
or volume-decay filter is a new experiment. Do not invent discretionary labels.

## 6. Data/cost profile
Reference trade age <=1000ms, BBO age <=500ms, mark age <=2000ms; all ages include
recorded clock uncertainty. Future timestamps outside validated clock uncertainty
reject. Any dependency health not HEALTHY -> no risk-eligible candidate.
Book depth if required age<=500ms and sequence synchronized. Initial clock/warmup
policies in TIME_AND_RECOVERY. These stricter target limits do not describe the
existing v1 scanner defaults. Calibration requires measured source cadence.

Risk numbers, fees and price rounding in RISK_POLICY; fill assumptions in
PAPER_BROKER. Config loader MUST reject missing fee version or nonfinite values,
unknown keys, impossible intervals, unsupported modes and unknown spec versions.

## 7. Independent observation profile rsi-watch-1 (telegram-spec-1)
This is an added non-actionable observation layer, NOT a modification of ref-1
entry strategies or evidence that mean reversion works. RSI-only alerts must say
watch for possible confirmation, never automatically confirm Long/Short.

Wilder RSI14, separately on closed complete 3m/5m bars. For delta=close-prevClose,
gain=max(delta,0), loss=max(-delta,0). First average gain/loss is arithmetic mean
of first 14 deltas (15 closes required); thereafter avg=(prev_avg*13+current)/14.
If both averages zero RSI=50; loss=0/gain>0 ->100; gain=0/loss>0 ->0; else
RSI=100-100/(1+avg_gain/avg_loss). Persist exact feature inputs/known_at. Never
round displayed RSI before threshold comparison; invalid/synthetic gap resets
warmup, no shortened estimate.

Initial state WARMING_UP -> NEUTRAL at first valid RSI; if already <=30 or >=70,
create one watch episode at that first valid close, labeled initial observation.
NEUTRAL enters OVERSOLD if RSI<=30, OVERBOUGHT if RSI>=70. While OVERSOLD, no
new episode until RSI>35; while OVERBOUGHT, none until RSI<65. On rearm bar, also
evaluate entry to the opposite zone (e.g. 25->75 creates OVERBOUGHT immediately).
Data discontinuity clears episode and requires fresh full warmup; a first valid
post-gap extreme is labeled initial observation, not claimed newly crossed.

Watch records observation_id, episode_id, exchange/symbol/timeframe, RSI value,
bar close/known_at, profile version, 15m/1H context snapshot and data quality.
Watch cooldown=300s per symbol/timeframe/type; send deadline=30s, not entry TTL.
State updates even when cooldown suppresses notification. Details and templates
in [TELEGRAM_ALERTS.md](TELEGRAM_ALERTS.md). Unknown HTF explicitly displayed;
unknown own timeframe quality suppresses watch. This profile does not require
funding, liquidation/account state to describe RSI, but never implies trade safety.

For watch context only: 15m UP if close>EMA200, EMA50>EMA200 and
EMA50[k]>EMA50[k-3]; DOWN if all reversed, else RANGE. 1H UP if close>EMA50,
DOWN if close<EMA50, else RANGE. Missing valid history -> UNKNOWN. Per-timeframe
labels do not change ref-1 combined regime. Both labels opposing watch direction
require explicit countertrend warning; mixed labels say mixed context.