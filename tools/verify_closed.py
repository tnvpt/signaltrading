"""Compare recorded closed analyses against public REST; never sends Telegram."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from signaltrading.candles import rest_candle
from signaltrading.watch import request_json
from signaltrading.notifications import WatchStore


def main():
    directory=Path('data/closed-validation')
    analyses=[]
    summaries=[]
    for path in directory.glob('*.jsonl'):
        with path.open() as handle:
            for line in handle:
                row=json.loads(line)
                if row['type']=='closed_analysis':
                    analyses.append(row['data'])
                elif row['type']=='watch_summary':
                    summaries.append(row['data'])
    checks=[]
    for item in analyses:
        bar=item['candle']
        rows=request_json('/fapi/v1/klines',{'symbol':bar['symbol'],'interval':bar['interval'],
                          'startTime':bar['open_ms'],'endTime':bar['close_ms']-1,'limit':1})
        checks.append({'symbol':bar['symbol'],'interval':bar['interval'],
                       'matches_rest':len(rows)==1 and rest_candle(bar['symbol'],bar['interval'],rows[0]).record()==bar})
    store=WatchStore(directory/'watch.sqlite3')
    try:
        engine=store.load()
        checkpoint_series=len(engine.series)
    finally:
        store.close()
    report={'checks':checks,'summaries':summaries,'rest_match_all':bool(checks) and all(c['matches_rest'] for c in checks),
            'checkpoint_series':checkpoint_series,'telegram_real_send':'PENDING_PRIVATE_CONFIG'}
    Path('closed-verified-result.txt').write_text(json.dumps(report,indent=2))
    return 0 if report['rest_match_all'] and checkpoint_series==8 else 1


if __name__=='__main__':
    raise SystemExit(main())