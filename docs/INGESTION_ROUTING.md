# Aggregate-trade routing diagnosis and evidence

## Official source checked 2026-11-26
- https://github.com/binance/binance-connector-python/blob/master/clients/derivatives_trading_usds_futures/src/binance_sdk_derivatives_trading_usds_futures/websocket_streams/streams/market_api.py
  aggregate_trade_streams uses stream_url="market".
- https://github.com/binance/binance-connector-python/blob/master/common/src/binance_common/websocket.py
  connection construction replaces /stream with /{url_path}/stream.

The developers documentation returned a browser challenge; current official SDK
source and actual public data were used. SDK master is mutable; recheck on changes.
The historical futures connector repository is deprecated.

## Controlled probe
Same official host, library, network and symbol; no proxy modifications.
Legacy /stream?streams=btcusdt@aggTrade completed handshake but received no frame
within 12 seconds. /market/stream?streams=btcusdt@aggTrade delivered a valid trade
after approximately 1.86s including connection setup. This is not trading latency.
No proxy environment variable names were present in the diagnostic process.

## Fix and regression
Default URL now includes /market/stream. URL composition for BTC/ETH is covered
by a regression test. No silent fallback to another exchange is introduced.

## End-to-end smoke capture
30-second configured capture on 2026-11-26, BTCUSDT and ETHUSDT:
- CLI exit 0; 349 trade records (255 BTC, 94 ETH).
- 349 parsed/fresh frames; zero malformed frames, data issues or reconnects.
- Observed receive timestamp minus trade timestamp: 117–281ms. This includes
  exchange aggregation, clock offset and network delay, not pure network latency.
- Writer queue high watermark 40.
- Replay validated all records; recorded/replayed alert lists match. Both lists
  were empty, so this live run does not establish non-empty alert parity; synthetic
  core tests cover non-empty alerts.
- 20 automated tests passed after route fix.

This is smoke evidence only, not capacity/24h availability or profitable strategy
validation. Configured duration can be exceeded by graceful connection closure.

## Reproduce from checkout root
```
.venv/bin/python tools/probe_binance.py
.venv/bin/python tools/validate_capture.py --duration 60
.venv/bin/python -m unittest discover -s tests -v
```
Validator writes a unique data directory and verified-capture-result.txt. Probe
writes endpoint-probe-result.txt. Generated evidence/raw data are local/ignored.
Next: quote/mark streams with correct public/market routing, schema v2 provenance,
rolling aggregates, load tests and >=24h soak before strategy development.