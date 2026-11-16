"""백테스트용 긴 일봉 받기 (한 번만 수동 실행).

화면은 이 파일을 쓰지 않는다. 매물대·치트·돌파 규칙을 5년 동안 시험하려고
시장 지표(MARKET)와 100종목(UNIVERSE)의 일봉을 BARS개씩 받아
backtest/prices.json.gz 에 저장한다. 형식은 data.json 의 series 와 같다:
{"generated": ..., "bars": BARS, "series": {티커: [[날짜, 고가, 저가, 종가, 거래량], ...]}, "failed": [...]}

Twelve Data 무료 키: 종목당 1회(분당 8회) → 약 104회, 13분 남짓.
매일 갱신 작업과 같은 키를 쓰므로 워크플로에서 같은 concurrency 묶음으로 돌려 겹치지 않게 한다.
"""
import datetime as dt
import gzip
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_data as bd  # noqa: E402  종목 목록·fetch_series 재사용

BARS = int(os.environ.get("BACKFILL_BARS", "1700"))   # 5년 시험 + 앞쪽 준비(200일선·1년 매물대·RS 12개월) 약 1.7년
OUT_DIR = os.path.join(bd.ROOT, "backtest")
OUT = os.path.join(OUT_DIR, "prices.json.gz")


def main():
    if not bd.KEY:
        sys.exit("TWELVE_DATA_KEY 환경변수가 없습니다.")
    symbols = list(dict.fromkeys(bd.MARKET + bd.STOCKS))
    print(f"{len(symbols)}개 종목, 종목당 일봉 {BARS}개", flush=True)
    series, failed = {}, []
    for i, s in enumerate(symbols):
        t0 = time.time()
        rows = bd.fetch_series(s, BARS)
        if rows:
            series[s] = rows
            print(f"  [{i + 1}/{len(symbols)}] {s}: {len(rows)}개 {rows[0][0]} - {rows[-1][0]}", flush=True)
        else:
            failed.append(s)
            print(f"  [{i + 1}/{len(symbols)}] {s}: 실패", flush=True)
        wait = bd.GAP - (time.time() - t0)
        if wait > 0 and i < len(symbols) - 1:
            time.sleep(wait)
    os.makedirs(OUT_DIR, exist_ok=True)
    data = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "bars": BARS, "series": series, "failed": failed}
    with gzip.open(OUT, "wt", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    short = [s for s, r in series.items() if len(r) < BARS]
    print(f"완료: {len(series)}개 저장, 실패 {failed or '없음'}, 일봉 모자람 {short or '없음'}, "
          f"크기 {os.path.getsize(OUT) / 1e6:.1f}MB", flush=True)


if __name__ == "__main__":
    main()
