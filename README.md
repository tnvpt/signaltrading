# SignalTrading — market research MVP

Collector public data Binance USDⓈ-M Futures, ghi JSONL và scanner pump/dump.
**Không đặt lệnh, không cần API key. Alert là watch event, không phải khuyến nghị Long/Short.**

## Chạy trên Linux / WSL (Python 3.11+)

### Candle-watch (JSON mặc định, Telegram opt-in)
Telegram watch đã có tích hợp opt-in và mock tests; cấu hình an toàn, lệnh TEST
và chạy thật tại [TELEGRAM_SETUP](docs/TELEGRAM_SETUP.md). Mặc định không gửi.

Từ thư mục gốc project sau khi cài đặt:
```bash
.venv/bin/python -m signaltrading.watch --symbols BTCUSDT ETHUSDT --duration 120
```
Khi bỏ `--symbols`, watcher tự chọn tối đa 8 altcoin Binance USDT perpetual
đang giao dịch, có đủ tuổi niêm yết để warmup và khối lượng 24h từ 1 đến 50
triệu USDT. Watcher xếp hạng theo độ lớn biến động giá 24h ở cả hai chiều,
chọn lại khi kết nối lại và ghi danh sách vào log. Có thể chỉnh bộ lọc:

```bash
.venv/bin/python -m signaltrading.watch --top-altcoins 8 --min-quote-volume 1000000 --max-quote-volume 50000000 --duration 0
```

Autostart uses `--rotate-futures`. This mode includes BTC/ETH and cycles through
active Binance USDT perpetuals with enough listing history in groups of 8.
Each group gets 300 seconds including warmup. The list refreshes after each pass.
Alerts cover the current group only. To run with Telegram manually:

```bash
.venv/bin/python -m signaltrading.watch --rotate-futures --duration 0 --telegram --env-file .env
```

REST warmup 3m/5m/15m/1h, WebSocket nến đã đóng, RSI Wilder14 + EMA context,
watch không phải tín hiệu vào lệnh. `--duration 0` chạy liên tục. Chưa có Telegram
ở chế độ mặc định; SQLite lưu checkpoint/cooldown/outbox qua restart.
Không chạy hai process cùng output directory.
Chi tiết phạm vi và nghiệm thu: `docs/MVP_EXECUTION.md`.

Chạy từ thư mục gốc project:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m signaltrading.cli collect --symbols BTCUSDT ETHUSDT --duration 60
.venv/bin/python -m signaltrading.cli replay --input data/2026-11-26.jsonl
```

Thay tên file replay bằng ngày UTC thực tế. `--duration 0` chạy liên tục;
Ctrl+C để dừng. `--threshold-pct 2` là ngưỡng biến động tuyệt đối 2% cho từng
cửa sổ 30/60/180 giây. Đây là baseline cố định, **chưa phải đo bất thường theo
lịch sử coin**, chưa có chuẩn hóa volume, trend filter hay tín hiệu vào lệnh.

## Dữ liệu và chất lượng

- Public combined market stream: `wss://fstream.binance.com/market/stream?streams=btcusdt@aggTrade`.
- Ghi aggregate trades: symbol, aggregate ID, trade timestamp `T`, giá, lượng,
  phía chủ động suy ra từ maker flag, và thời gian máy nhận (UTC epoch ms).
- Chỉ tính volume giao dịch trong cửa sổ; giá gốc là quan sát gần nhất trước
  hoặc tại ranh giới. Warmup phải đủ độ dài cửa sổ.
- Dữ liệu trễ >3 giây, timestamp tương lai >1 giây, ID/thời gian lùi, ID bị
  thiếu hoặc khoảng ngừng >10 giây sẽ làm mất hiệu lực lịch sử quan sát.
  Sau reconnect phải warmup lại. Đồng bộ đồng hồ máy bằng NTP.
- Aggregate ID gap là kiểm tra bảo thủ về tính liên tục, không tự tải bù.
- Watchdog độc lập theo symbol: mặc định 10 giây để nhận trade hợp lệ đầu tiên
  và 10 giây im lặng sau trade gần nhất. Handshake không đồng nghĩa dữ liệu tốt.
  Exponential backoff tối đa khoảng 31 giây; tự phản hồi ping của server.
- Replay dùng thứ tự nhận và timestamp đã ghi, không dùng đồng hồ hiện tại.
- JSONL append theo ngày UTC; writer bất đồng bộ qua queue có giới hạn, một
  disk worker. Overflow/disk error dừng capture, không bỏ dữ liệu âm thầm.
  **Chưa có retention hay nén**; phải theo dõi dung lượng đĩa. Không chạy nhiều
  collector vào cùng thư mục. Tối đa 20 symbols để giới hạn phạm vi MVP.
- Chi phí xử lý scanner tuyến tính theo số trade giữ trong cửa sổ; chưa
  benchmark cho toàn thị trường. Không quảng cáo độ trễ trước khi đo thực tế.

Session manifest lưu config hash và scanner version; cuối phiên có summary.
CLI trả exit code 2 nếu có symbol chưa nhận được trade mới hợp lệ trong phiên.
Điều này không thay thế kiểm chứng liên tục 24h hay chứng nhận chiến lược.

### Chẩn đoán và xác minh dữ liệu thật

```bash
.venv/bin/python tools/probe_binance.py
.venv/bin/python tools/validate_capture.py --duration 60
```

Probe đối chiếu legacy `/stream` và routed `/market/stream` trên cùng host,
không đổi proxy. Validator tạo thư mục riêng, kiểm tra số trade BTC/ETH,
timestamp và replay alert parity. Báo cáo cục bộ `endpoint-probe-result.txt`,
`verified-capture-result.txt` được gitignore. Xem `docs/INGESTION_ROUTING.md`.

## Đặc tả và bàn giao

**Ưu tiên hiện tại: hoàn thiện và review giải pháp trước khi code tính năng tiếp.**
Điểm bắt đầu: [bộ tài liệu research-spec-1](docs/README.md). Các cấu hình nghiên cứu
tham chiếu trong tài liệu chưa được chứng minh có lợi nhuận, không phải cấu hình
runtime hiện tại và không cho phép giao dịch thật/x50/x100.

Kênh cảnh báo chính được thiết kế là **bot Telegram của người dùng**, theo khung
3p/5p với bối cảnh 15p/1h. Đặc tả [telegram-spec-1](docs/TELEGRAM_ALERTS.md)
phân biệt quá mua/quá bán để theo dõi với setup Long/Short đã xác nhận.
**Đã có Telegram watch opt-in với mock tests; chưa cấu hình token hay gửi tin thật.**

Đọc `docs/PRODUCT_SPEC.md`, `docs/ARCHITECTURE.md`, `docs/DATA_CONTRACTS.md`,
`docs/STRATEGIES.md`, `docs/RISK_POLICY.md`, `docs/VALIDATION_PLAN.md`,
`docs/OPERATIONS.md` và `docs/TASKS.md` trước khi triển khai tiếp.
P0/P1a đang củng cố ingestion; chưa hoàn thành P1b (quote/mark/v2/benchmark/soak).

## Phạm vi chưa triển khai

Chưa có order book, mark/index price, funding, OI, chart, FastAPI, AI,
MEXC adapter, strategy reversal/continuation, mô phỏng khớp lệnh hay thanh lý.
Replay hiện chỉ phát lại watch events, **không phải paper trading/PnL backtest**.
Không thay nguồn Binance thành MEXC âm thầm. Không vượt hạn chế truy cập của sàn.
Đòn bẩy cao có thể thanh lý trước khi xu hướng dự đoán xảy ra.

## Lộ trình

1. Đo và kiểm chứng collector, replay và data-quality trên môi trường chạy.
2. Thu thập mark price, best bid/ask; thống kê biến động nền theo coin.
3. Định nghĩa pump → stall → breakdown và pump → hold → continuation.
4. Paper trading có phí, spread, trượt giá và báo cáo MAE/drawdown.
5. Dashboard, giải thích tín hiệu; chỉ cân nhắc execution sau kiểm chứng.

## Tài liệu tham khảo (không sao chép strategy)

- Binance market streams: https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams
- Freqtrade: https://github.com/freqtrade/freqtrade
- Lookahead analysis: https://www.freqtrade.io/en/stable/lookahead-analysis/
- Jesse: https://github.com/jesse-ai/jesse
- HftBacktest: https://github.com/nkaz001/hftbacktest

Khả năng truy cập endpoint và giới hạn hiện hành cần kiểm chứng ở nơi triển khai.
Không có cam kết lợi nhuận. Repo tham khảo không phải bằng chứng strategy có lãi.