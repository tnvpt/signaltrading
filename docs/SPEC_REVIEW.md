# Solution documentation review — research-spec-1

## Changes in this documentation-only release
Closed previous specification gaps: navigation/precedence, capability gates,
component interfaces, source/universe rules, clock/finalization/late data, v2
migration/provenance, reference feature formulas and threshold units, deterministic
Long/Short transitions, TTL/conflicts/rounding, cost-aware sizing, paper fills,
funding/ledger, API delivery, deployment/recovery/security and named acceptance.

The ref-1 thresholds are fixed solely for reproducible implementation/research.
They are not claimed optimal, profitable or compatible with x50/x100 execution.
Spec explicitly rejects insufficient liquidation/capacity evidence. It also notes
that manual 5s latency cannot satisfy ref-1's 5s TTL: a useful negative test.

## Validation performed
Read back specification files, checked all local Markdown links in root README
and docs, and independently evaluated Decimal sizing example: ell=1.129515,
q0=8.85 for 10 USDT risk and 0.01 quantity step. Initial link check found zero
broken links. This is documentation consistency checking, not strategy validation.
No runtime code, dependency, strategy implementation or exchange execution changed.
No fresh public stream or unit test run was necessary to validate text-only edits;
prior 20-test/live-smoke evidence remains historical, not newly rerun evidence.

## Still evidence-dependent, not filled with guesses
- Verified quote/mark/depth schemas and reconstruction, precise metadata/fees.
- Venue-specific liquidation math, maintenance tiers and independent fixtures.
- Measured latency/capacity/clock uncertainty and 24h recovery/soak.
- Enough unbiased data and forward paper results for strategy promotion.
- Exit-depth stress policy for high-leverage certification.
- UI/dependency choices after compatibility/license review.
- Live execution specification, security design and separate authorization.

These are explicit blockers, not permission for a coding model to invent defaults.
The solution is ready for implementation breakdown and contract fixtures after
review; it is NOT ready for real-money operation or a profitability claim.

## Telegram addendum telegram-spec-1
Documents primary bot notification channel, Vietnamese watch/confirmed/lifecycle
templates, 3m/5m independence and 15m/1H context, Wilder RSI14 observation rules,
hysteresis/cooldown, outbox/expiry/retry/uncertain delivery, secret redaction and
named tests. rsi-watch-1 does not change ref-1 entries or add an oversold-reversal
trading strategy. No token requested, integration coded or real message sent.
Only Markdown documentation changed; local-link/required-section validation is
the acceptance for this addendum, not a Telegram connectivity certificate.