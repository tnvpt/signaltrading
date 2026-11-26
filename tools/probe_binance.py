"""Bounded public diagnostic; no credentials, routing bypass or proxy changes."""

import asyncio
import json
import os
from pathlib import Path
import time
import urllib.request

from websockets.asyncio.client import connect


async def probe(url):
    result = {"url": url, "handshake": False, "frames": 0}
    started = time.monotonic()
    try:
        async with asyncio.timeout(12):
            async with connect(url, open_timeout=5, close_timeout=1, ping_interval=None) as socket:
                result["handshake"] = True
                message = await socket.recv()
                result["frames"] = 1
                result["first_frame"] = json.loads(message)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return result


def source_excerpt():
    url = "https://raw.githubusercontent.com/binance/binance-connector-python/master/common/src/binance_common/websocket.py"
    try:
        lines = urllib.request.urlopen(url, timeout=10).read().decode().splitlines()
        matches = set()
        for index, line in enumerate(lines):
            if any(term in line for term in ("url_path}", "url_path}/", '"/stream', '"/ws', "url_path =")):
                matches.update(range(max(0, index - 3), min(len(lines), index + 4)))
        return {"url": url, "excerpt": [f"{i + 1}: {lines[i]}" for i in sorted(matches)]}
    except Exception as exc:
        return {"url": url, "error": f"{type(exc).__name__}: {exc}"}


async def main():
    # Same official host, legacy vs routed market stream from Binance's SDK.
    urls = ["wss://fstream.binance.com/stream?streams=btcusdt@aggTrade",
            "wss://fstream.binance.com/market/stream?streams=btcusdt@aggTrade"]
    results = await asyncio.gather(*(probe(url) for url in urls))
    report = {"proxy_variables_present": [name for name in os.environ
                                           if name.lower().endswith("proxy")],
              "source": await asyncio.to_thread(source_excerpt), "probes": results}
    Path("endpoint-probe-result.txt").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())