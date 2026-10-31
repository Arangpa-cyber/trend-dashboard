"""
추세 대시보드 서버 데이터 만들기 (GitHub Actions에서 매일 미국장 마감 뒤 실행)

- 종목 목록과 받을 일봉 개수는 index.html 안의 UNIVERSE, MARKET, DAYS_* 를 그대로 읽습니다.
  (종목을 바꿀 때는 index.html 한 곳만 고치면 됩니다.)
- 시세: Twelve Data 무료 키 (분당 8회 제한에 맞춰 8초 간격, 약 14분)
- 실적 일정: Nasdaq 실적 캘린더 (공식 API가 아니라서 막히면 실적 표시만 빠지고 나머지는 정상)
  지난 400일 발표일은 처음 한 번만 다 받고(약 4분), 그 뒤로는 새 날짜만 이어 받습니다.
- 결과: 저장소 맨 위의 data.json
"""
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
OUT = os.path.join(ROOT, "data.json")

universe_block = HTML[HTML.index("const UNIVERSE"):HTML.index("const MARKET")]
STOCKS = re.findall(r'\["([A-Z][A-Z0-9.]*)",\s*"', universe_block)
MARKET = json.loads(re.search(r"const MARKET = (\[.*?\]);", HTML).group(1))
DAYS_MARKET = int(re.search(r"const DAYS_MARKET = (\d+)", HTML).group(1))
DAYS_STOCK = int(re.search(r"const DAYS_STOCK = (\d+)", HTML).group(1))

KEY = os.environ.get("TWELVE_DATA_KEY", "").strip()
GAP = 8.0  # 초. 무료 키 분당 8회


def get_json(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_series(symbol, size):
    q = urllib.parse.urlencode({"symbol": symbol, "interval": "1day", "outputsize": size, "apikey": KEY})
    for attempt in range(3):
        try:
            j = get_json("https://api.twelvedata.com/time_series?" + q)
        except Exception as e:  # 네트워크 오류
            j = {"status": "error", "message": str(e)}
        if j.get("status") == "ok":
            return [[v["datetime"][:10], round(float(v["high"]), 4), round(float(v["low"]), 4),
                     round(float(v["close"]), 4), int(float(v.get("volume") or 0))]
                    for v in reversed(j["values"])]
        if j.get("code") == 429:  # 한도 초과: 1분 쉬고 다시
            print(f"  {symbol}: 한도 대기", flush=True)
            time.sleep(61)
            continue
        if j.get("code") == 401:
            sys.exit("API 키가 올바르지 않습니다. 저장소 Settings > Secrets 의 TWELVE_DATA_KEY 를 확인하세요.")
        print(f"  {symbol}: 실패 - {j.get('message')}", flush=True)
        time.sleep(GAP)
    return None


def fetch_earnings(symbols, start, end):
    """start-end 날짜(포함) 사이 실적 발표일 (Nasdaq 실적 캘린더) → {symbol: [{date, time}]}"""
    want, found = set(symbols), {}
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", "Accept": "application/json"}
    d = start
    while d <= end:
        if d.weekday() < 5:
            try:
                j = get_json(f"https://api.nasdaq.com/api/calendar/earnings?date={d.isoformat()}", headers, timeout=20)
                for row in ((j.get("data") or {}).get("rows") or []):
                    s = row.get("symbol")
                    if s in want:
                        found.setdefault(s, []).append({"date": d.isoformat(), "time": row.get("time", "")})
            except Exception as e:
                print(f"  실적 {d}: 실패 - {e}", flush=True)
            time.sleep(0.6)
        d += dt.timedelta(days=1)
    return found


HIST_DAYS = 400   # 차트에 노란 배경으로 칠할 지난 실적 발표일 범위
AHEAD_DAYS = 60   # 다가오는 실적 일정 범위


def main():
    if not KEY:
        sys.exit("TWELVE_DATA_KEY 환경변수가 없습니다.")
    prev = {}
    if os.path.exists(OUT):
        try:
            prev = json.load(open(OUT, encoding="utf-8"))
        except Exception:
            prev = {}
    old = prev.get("series", {})

    series, failed = {}, []
    symbols = MARKET + STOCKS
    print(f"시세 받기: {len(symbols)}종목 (약 {len(symbols) * GAP / 60:.0f}분)", flush=True)
    for i, s in enumerate(symbols, 1):
        t0 = time.time()
        rows = fetch_series(s, DAYS_MARKET if s in MARKET else DAYS_STOCK)
        if rows:
            series[s] = rows
        else:
            failed.append(s)
            if s in old:
                series[s] = old[s]  # 실패하면 어제 데이터 유지
        print(f"[{i}/{len(symbols)}] {s} {'OK' if rows else '실패'}", flush=True)
        time.sleep(max(0.0, GAP - (time.time() - t0)))

    if "QQQ" not in series:
        sys.exit("QQQ를 받지 못해 data.json을 갱신하지 않습니다.")

    # 실적: 지난 발표일은 전에 받은 것을 이어 쓰고, 그 뒤 날짜와 앞으로 60일만 새로 받음
    today = dt.date.today()
    hist_from = today - dt.timedelta(days=HIST_DAYS)
    hist = {s: [x for x in v if x >= hist_from.isoformat()] for s, v in (prev.get("earnHist") or {}).items()}
    upto = prev.get("earnHistUpTo")
    start = hist_from
    if upto and hist:
        start = max(hist_from, dt.date.fromisoformat(upto) - dt.timedelta(days=5))   # 며칠 겹쳐서 다시 확인
        hist = {s: [x for x in v if x < start.isoformat()] for s, v in hist.items()}
    print(f"실적 일정 받기: {start} - {today + dt.timedelta(days=AHEAD_DAYS)}", flush=True)
    found = fetch_earnings(STOCKS, start, today + dt.timedelta(days=AHEAD_DAYS))
    earnings = {}
    for s, rows in found.items():
        for r in rows:
            if r["date"] < today.isoformat():
                hist.setdefault(s, []).append(r["date"])
            elif s not in earnings:
                earnings[s] = r   # 다가오는 가장 가까운 발표일
    hist = {s: sorted(set(v)) for s, v in hist.items() if v}
    upto_new = (today - dt.timedelta(days=1)).isoformat()
    if not found and prev.get("earnHist"):   # Nasdaq이 막힌 날: 전에 받은 실적을 그대로 둠
        hist, upto_new = prev["earnHist"], prev.get("earnHistUpTo")
        earnings = prev.get("earnings", {})
    print(f"  다가오는 실적 {len(earnings)}종목, 지난 실적 {sum(len(v) for v in hist.values())}건", flush=True)

    data = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "asOf": series["QQQ"][-1][0],
        "failed": failed,
        "earnings": earnings,
        "earnHist": hist,
        "earnHistUpTo": upto_new,
        "series": series,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"완료: 기준일 {data['asOf']}, 실패 {failed or '없음'}, 크기 {os.path.getsize(OUT) / 1e6:.1f}MB")


if __name__ == "__main__":
    main()
