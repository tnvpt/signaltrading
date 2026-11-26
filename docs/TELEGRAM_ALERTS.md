# Telegram alerts — primary notification channel

Status: documentation-only extension `telegram-spec-1` to research-spec-1.
Target contract: watch-only subset now implemented; see TELEGRAM_SETUP.md. No
actual bot connection/message sending verified yet. Telegram is primary; dashboard optional
support for charts/research. Neither notification nor button places an order.

## 1. Timeframes and classification
Monitor 3m and 5m independently; context is closed 15m/1H bars. Distinguish:
- WATCH_OVERSOLD: RSI observation, consider watching for Long confirmation.
- WATCH_OVERBOUGHT: RSI observation, consider watching for Short confirmation.
- CONFIRMED_LONG / CONFIRMED_SHORT: versioned setup plus required risk gates.
- INVALIDATED / EXPIRED: lifecycle updates, not fresh entry opportunities.
- SYSTEM_HEALTH: data or delivery failure/recovery, not market advice.

RSI observation profile is `rsi-watch-1` in RESEARCH_PROFILE. It is NOT a new entry
strategy and does not change ref-1 strategy conditions. Long continuation does
not mean oversold reversal Long. A future oversold-reversal strategy requires its
own specification/research; never relabel a watch as confirmation.

Use closed complete candles. Default confirmed-mode notification only; optional
EARLY30 signals retain their explicit label and separate research results.
Forming-candle previews are OFF in this release. They would need a separate
version, `TEMPORARY / NẾN CHƯA ĐÓNG` label and cancellation rules.

## 2. Vietnamese message templates
Templates below are illustrative, not current market calls. Plain text default;
if formatting is enabled later, escape dynamic symbols/reasons before rendering.

WATCH:
```
🟡 BTCUSDT · QUÁ BÁN · 3p · Binance USDM
Theo dõi khả năng Long — CHƯA xác nhận vào lệnh.
RSI14: 28,4 | Xu hướng 15p: GIẢM · 1h: GIẢM
Ngược xu hướng lớn; không bắt đáy chỉ vì quá bán.
Nến đóng: 14:30:00 UTC+7 | Dữ liệu tính đến: 14:30:01 UTC+7
```

WATCH alternative:
```
🟡 ETHUSDT · QUÁ MUA · 5p · Binance USDM
Theo dõi khả năng Short — CHƯA xác nhận vào lệnh.
RSI14: 74,2 | Xu hướng 15p: TĂNG · 1h: TĂNG
Ngược xu hướng lớn; quá mua có thể kéo dài.
Nến đóng: 14:30:00 UTC+7 | Dữ liệu tính đến: 14:30:01 UTC+7
```

CONFIRMED:
```
🔴 ETHUSDT · SHORT · 5p · Binance USDM
ĐÃ XÁC NHẬN: breakdown + retest thất bại.
Xu hướng 15p: ĐI NGANG · 1h: GIẢM
Entry: <min>–<max> | Stop: <stop> | Target: <target>
Phát hiện: <decision time UTC+7> | Hết hiệu lực: <expiry UTC+7>
Không đuổi giá ngoài entry. Đòn bẩy: CHƯA XÁC MINH.
Tín hiệu nghiên cứu, không bảo đảm lợi nhuận. ID: <short ID>
```

LONG uses green marker and actual setup reason, not Short reason with side flipped.
No invented entry/stop/target or win probability. Confirmed market candidates that
fail required risk gates are NOT sent in confirmed template; optional diagnostic
message must say `KHÔNG ĐỦ ĐIỀU KIỆN`, explain rejection and omit entry instruction.
Unknown liquidation capability can coexist with basic-paper eligibility, but must
display UNKNOWN and never imply high-leverage eligibility or recommend x50/x100.

Lifecycle update:
```
⚪ ETHUSDT · SHORT 5p · ĐÃ HẾT HIỆU LỰC
Không sử dụng tín hiệu cũ để vào lệnh. ID: <same short ID>
```
Invalidation uses actual reason/time and says cancelled setup, NOT position closed.
The notifier does not know the user's manual position unless separately supplied.

Messages must remain concise (target <=1000 Unicode characters; hard application
limit 3500). Optional verified exchange/chart URL button only; no execution button.
Times persisted UTC, rendered with configured timezone default Asia/Ho_Chi_Minh.
Include full date when day changes; never mix unlabeled UTC/local time.

## 3. Multi-timeframe context and aggregation
Each message identifies exchange, symbol, setup timeframe, closed-bar known_at,
and 15m/1H direction using most recent complete known feature snapshots.
Context unavailable/stale -> `CHƯA ĐỦ DỮ LIỆU`; never infer it from 3m direction.
RSI watch can still be delivered with unknown context if its own data is healthy,
explicitly non-actionable. Confirmed signal still follows strategy/risk gates.

3m/5m watches remain independently identifiable. If same symbol/source/side
observations are both valid and their decisions <=300s apart, a follow-up may say
`3p/5p cùng trạng thái quá mua/quá bán`, retaining both timestamps/IDs. This is
observation agreement, not an entry strategy or stronger calibrated probability.
Opposite observations -> `3p/5p chưa đồng thuận`. Never blend entry/stop levels.
Confirmed signals keep separate IDs/TTLs; optional display grouping never extends
either expiry. Do not delay sending the first signal waiting for other timeframe.
No portfolio combining across research accounts is authorized by display grouping.

## 4. Configuration and credentials (proposed names, not runtime flags)
`TELEGRAM_BOT_TOKEN` is a deployment secret, never source/config hash/log/traceback.
`TELEGRAM_ALLOWED_CHAT_IDS` is a private allowlist; no broadcast to arbitrary IDs.
Nonsecret versioned settings: enabled=false until configured, timezone,
watch_enabled, confirmed_enabled, health_enabled, allowed symbols/timeframes,
cooldown_s=300, observation_send_deadline_s=30, outbox_capacity=1000,
max_attempts=3, request_timeout_s=2, max_inflight_per_chat=1.
Bot token appears in Bot API URL: redact entire URL/token in HTTP/proxy errors.
Do not echo a secret while validating configuration. Fail notifier closed on
missing credentials; analysis can continue with DELIVERY_UNAVAILABLE alarm locally.
Operator privately establishes chat ID and ability to message the bot; verify
current official Bot API methods/limits during implementation. No bot-admin rights
or exchange API keys required for outbound alerts. Sending smoke message requires
explicit user approval and an allowlisted destination, not merely a saved token.
Inbound commands/webhooks disabled in this spec; future commands need authorization.

## 5. Durable outbox and deadlines
Insert outbox atomically with the corresponding alert projection; engine never
waits for Telegram HTTP. Watch ID derives from profile/exchange/symbol/timeframe/
bar close/oversold-or-overbought episode; confirmed uses immutable signal_id.
Unique delivery key=(alert_id, chat_id, lifecycle_revision, template_version).
Store event ID/revision, payload hash, created/deadline times, attempts, status,
message_id if known, error category and Telegram API acknowledgment time.
No token, private raw HTTP URL or unneeded chat content in audit records.

Statuses: PENDING -> IN_FLIGHT -> API_ACCEPTED / RETRY_WAIT / FAILED /
DELIVERY_UNKNOWN / EXPIRED_UNSENT / SUPERSEDED. API_ACCEPTED does NOT mean device
displayed or user read. No read-receipt claim from outbound Bot API acknowledgment.
Transport deadlines use notifier clock; original decision/TTL never altered.

Before each send/retry: re-read lifecycle, data eligibility and deadline. Watch
send deadline=decision+30s and no later than supersession/invalidation; historical
watch sent late must not look current. Confirmed deadline=signal expiry (5s ref-1).
Do not send if `now + request_timeout >= deadline` (conservative send budget).
This cannot guarantee Telegram delivery before expiry; include expiry visibly.
Expiry/cancel update may be sent as historical lifecycle notice even after entry
deadline, only if original was API_ACCEPTED or DELIVERY_UNKNOWN. Never send an old
entry message merely because its lifecycle update is queued behind it.

Priority: invalidation/expiry of sent signals, confirmed candidates, health changes,
then watch. All priorities still obey eligibility/deadlines. Bounded queue full:
remove expired/superseded watches first; if still full record DELIVERY_DROPPED,
alarm locally and preserve audit. Never block data engine or silently drop notice.
Per-chat sequential sender plus token bucket configured from current official
limits; defaults must be verified, not hard-code unverified platform throughput.

## 6. Retry, uncertain delivery and restart
Definitive rate limit: honor retry_after, but only if deadline allows. Explicit
transient failure: bounded exponential backoff (1s,2s) with jitter<=250ms, max3
attempts including first, subject to deadline. Permanent bad token/chat/permission
failure -> FAILED and disable affected destination with operator alarm.
HTTP timeout/reset after possible send -> DELIVERY_UNKNOWN, do not blindly resend
actionable message. Telegram sendMessage does not provide application idempotency
guarantee. Duplicate prevention in local DB cannot guarantee exactly-once external
delivery. Record uncertainty; operator sees health status. A lifecycle cancellation
for this ID is allowed to reduce stale-signal risk.

On restart IN_FLIGHT -> DELIVERY_UNKNOWN; reconcile known message_id only using
available supported API behavior, never invent a sent-message search capability.
PENDING/RETRY_WAIT revalidate TTL and state. Sent signals not resent as new.
If editing known message_id to mark cancellation fails, allow one linked follow-up
notice; editing alone cannot retract a phone notification already read. Updates
cannot claim user position has closed. Stop retry loop on shutdown, persist state.

## 7. Anti-spam and episode semantics
RSI state resets/hysteresis in RESEARCH_PROFILE; sustained RSI extreme is not a
new event every tick/bar. Watch cooldown key=(exchange,symbol,timeframe,watch_type),
300s, measured from last created watch even if notification fails. Cooldown blocks
new messages, NOT rearm state tracking. If a fresh zone entry occurs in cooldown,
record suppressed event and do not deliver it later without another new entry.
No watch may suppress an independent valid confirmed signal. Lifecycle updates
deduplicated by revision. Repeated health failure -> one transition notice plus
optional digest, not per-trade errors. Clock/stream failure stops relevant fresh
signal messages; recovery requires bar/feature warmup before resumed watch alerts.

## 8. Required tests and acceptance
- Wilder RSI seed/flat/monotonic/threshold/hysteresis/cooldown fixtures.
- 3m and 5m independent states, unavailable HTF, conflict/grouping timestamps.
- Safe renderer, Vietnamese labels/timezone/date, decimal formatting, no secrets.
- Outbox transactional rollback, duplicate key, priority, saturation, restart.
- Expired before enqueue/send/retry; 5s TTL vs 5s manual latency rejects.
- 429 retry_after exceeds TTL, permanent auth error, ambiguous timeout, edit failure.
- API_ACCEPTED is not READ; metrics never mislabel acknowledgment as phone latency.
- No real Telegram HTTP in unit/replay tests; mock responses + recorded clocks.
- Explicitly authorized smoke: known allowlisted chat, labeled TEST message,
  store API acknowledgment evidence with redacted identifiers; no trade advice.
- Evaluate manual reaction 1/3/5s plus measured notification lag in paper research.

Metrics: outbox size/age, accepted/failed/unknown/expired/dropped, HTTP API latency,
decision-to-API-ack, by type/timeframe. Phone receipt/reaction unknown unless a
separate consented measurement exists. Telegram is not a low-latency guarantee
and cannot certify suitability for x50/x100.