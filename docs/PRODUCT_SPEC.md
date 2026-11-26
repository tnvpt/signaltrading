# Product specification

## Goal
Explainable real-time research assistant for 3m/5m crypto perpetual Long/Short
setups. Market data first; paper trading before execution. No profitability or
timing guarantee. x50/x100 are feasibility/stress profiles, never requirements
that override risk controls.

## Initial scope
- One verified exchange, then 10–20 liquid instruments selected using metadata.
- Context 15m/1H, setup 3m/5m, early confirmation on closed 15s/30s bars.
- Two hypotheses: failed-pump reversal Short and breakout-hold continuation Long.
- Separate early/confirmed versions, reporting and configuration.
- Distinguish market candidate, risk-eligible signal and executable order.
- No live execution or account keys in P0–P9.

## User experience
Market scanner, chart with frozen setup levels, signal lifecycle/expiry,
data-health view, research report and replay. Display exchange explicitly.
Never silently substitute Binance data for MEXC execution prices.

## Non-goals
Predicting whale intent, guaranteed entries, arbitrary win probabilities,
LLM-generated numeric entry/stop, martingale and averaging down.

## Evidence gates
Handshake is not data success. Mock tests are not production validation.
Positive backtest is not live profitability. Missing data means UNKNOWN/NO_TRADE.

## Specification entry point and user acceptance
Read [README.md](README.md) for research-spec-1 document precedence. Current scope
is documentation-first; no further feature coding until solution review is done.
Deterministic reference thresholds are research defaults, not validated edge.

User stories: explain why coin is watched; see Long versus Short scenario without
forced direction; see why trade is rejected; inspect evidence available at decision;
replay the same decision; distinguish correct later direction from survivable entry.
Acceptance requires visible expiry and data health, not merely candlestick names.
No promise that all price spikes can be avoided or protective stops always fill.

## Telegram-first notification requirement (telegram-spec-1)
Primary interaction is concise Vietnamese messages to the user's own Telegram
bot/chat; dashboard is optional supporting analysis. Monitor 3m/5m separately,
with closed 15m/1H trend context. Deliver RSI watch observations separately from
versioned confirmed Long/Short signals and cancellation/expiry/health updates.
Oversold !=Long confirmation; overbought !=Short confirmation. No auto orders.
See [TELEGRAM_ALERTS.md](TELEGRAM_ALERTS.md) for templates, credential safety,
outbox/TTL/anti-spam and acknowledgment limitations. Telegram integration is
specified only, not implemented or connected. No token is needed for docs review.