#!/usr/bin/env bash
# Start on interactive Ubuntu terminal opening; no restart loop or secret output.
set -eu
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
STATE="$ROOT/data/candle-watch"
mkdir -p -- "$STATE"

case "${1:-start}" in
  start)
    if [[ ! -x "$ROOT/.venv/bin/python" || ! -f "$ROOT/.env" ]]; then
      printf '%s\n' 'SignalTrading: thiếu .venv hoặc .env; chưa khởi chạy.' >&2
      exit 1
    fi
    # Both checks are non-destructive. The watcher also owns its SQLite flock.
    if ! flock -n "$STATE/autostart.lock" true; then exit 0; fi
    if ! flock -n "$STATE/watch.sqlite3.lock" true; then exit 0; fi
    nohup bash "$ROOT/tools/autostart.sh" run </dev/null >>"$STATE/autostart.log" 2>&1 &
    ;;
  run)
    exec 9>"$STATE/autostart.lock"
    flock -n 9 || exit 0
    flock -n "$STATE/watch.sqlite3.lock" true || exit 0
    cd -- "$ROOT"
    printf '%s\n' "$(date -Is) Starting SignalTrading watch"
    exec "$ROOT/.venv/bin/python" -u -m signaltrading.watch \
      --duration 0 --telegram --env-file "$ROOT/.env" --output "$STATE"
    ;;
  check)
    bash -n "$ROOT/tools/autostart.sh"
    [[ -x "$ROOT/.venv/bin/python" && -f "$ROOT/.env" ]]
    printf '%s\n' 'Startup prerequisites present; no bot started or message sent.'
    ;;
  *) printf '%s\n' 'Usage: bash tools/autostart.sh [start|check]' >&2; exit 2 ;;
esac