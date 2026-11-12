"""
추세 대시보드 서버 데이터 만들기 (GitHub Actions에서 매일 미국장 마감 뒤 실행)

- 종목 목록과 받을 일봉 개수는 index.html 안의 UNIVERSE, MARKET, DAYS_* 를 그대로 읽습니다.
  (종목을 바꿀 때는 index.html 한 곳만 고치면 됩니다.)
- 시세: Twelve Data 무료 키 (분당 8회 제한에 맞춰 8초 간격, 약 15분)
- 시작 시각: 예약은 00:30 UTC. 미국 동부 20:15(시간외 거래 마감 15분 뒤)보다 일찍 시작했으면 그때까지 기다립니다.
  (겨울에는 00:30 UTC가 동부 19:30이라 시간외 거래가 아직 진행 중)
- 거래량 확정 확인: 시장 지표(QQQ 등)는 맨 처음에 받고, 종목을 다 받은 뒤(약 15분 뒤) 다시 받아 마지막 날 거래량을 비교합니다.
  1% 넘게 다르거나 최근 20일 평균의 25%도 안 되면 15분 뒤 또 받아, 두 번 연속 같아질 때까지 최대 4번 확인합니다.
  끝까지 안 맞으면 '잠정'으로 보고 data.json의 partial에 적습니다(화면은 그날 분산일·팔로스루 판정을 보류).
  (2026-11-02 QQQ 거래량이 79만 주로 들어온 일, 2026-11-05 QQQ 거래량이 동부 21시 넘어서도 바뀐 일 이후 추가)
- 거래량 교차 확인: 시장 지표는 Nasdaq 일별 시세로 최근 5거래일 거래량을 한 번 더 맞춰 봅니다.
  두 출처가 평소엔 맞는데(5일 중앙값 비율 0.85-1.15) 어느 날만 15% 넘게 다르면 그날은 Nasdaq 값으로 바로잡고 fixed에 적습니다.
  그다음 최근 5거래일 모두 이상값 검사: 20일 평균의 25% 미만이거나, 4배 넘는데 그날 등락이 2% 안쪽이면 '잠정'.
  (2026-11-10 QQQ 거래량이 실제의 10배인 4.5억 주로 들어와 분산일로 잘못 세어진 일 이후 추가)
- QQQ 비중(근사): Nasdaq의 나스닥100 구성종목 시가총액으로 비중을 계산해 ndxw에 적습니다.
  (실제 QQQ는 분기마다 큰 종목 비중을 깎는 규칙이 있어 조금 다름. 막히면 전날 값을 그대로 씀)
- QQQ 보유 종목: Alpha Vantage ETF_PROFILE(QQQ)로 매일 비중을 받아 ndxw에 쓰고, 대시보드 종목 목록과 다르면 알림(notices)에 적음.
- 나스닥100 변경 발표: 매주 그 주 첫 거래일 자료를 받는 날, Nasdaq IR 보도자료 RSS와 Alpha Vantage 뉴스(NDAQ·QQQ)에서
  "Nasdaq-100" 편입·교체·정기 변경 발표를 찾아 알림에 적음. 그날 둘 다 실패하면 그 주 안에 다음 실행에서 다시.
- 실적 일정: Alpha Vantage 실적 달력(ALPHAVANTAGE_KEY, 하루 1회 요청으로 앞으로 3개월). 키가 없거나 실패하면 Nasdaq 실적 캘린더.
  지난 발표일은 전에 받은 일정이 지나갈 때마다 쌓아 둠. (2026-11-11부터 GitHub에서 Nasdaq이 403으로 막혀 추가)
- (예전) 실적 일정: Nasdaq 실적 캘린더 (공식 API가 아니라서 막히면 실적 표시만 빠지고 나머지는 정상)
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
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
OUT = os.path.join(ROOT, "data.json")

universe_block = HTML[HTML.index("const UNIVERSE"):HTML.index("const MARKET")]
STOCKS = re.findall(r'\["([A-Z][A-Z0-9.]*)",\s*"', universe_block)
NAMES = dict(re.findall(r'\["([A-Z][A-Z0-9.]*)",\s*"([^"]+)"\]', universe_block))   # 티커 → 회사 이름(보유 종목 이름 맞추기용)
MARKET = json.loads(re.search(r"const MARKET = (\[.*?\]);", HTML).group(1))
DAYS_MARKET = int(re.search(r"const DAYS_MARKET = (\d+)", HTML).group(1))
DAYS_STOCK = int(re.search(r"const DAYS_STOCK = (\d+)", HTML).group(1))

KEY = os.environ.get("TWELVE_DATA_KEY", "").strip()
GAP = 8.0  # 초. 무료 키 분당 8회
NY = ZoneInfo("America/New_York")
SETTLE_NY = dt.time(20, 15)   # 시간외 거래(20:00) 마감 15분 뒤부터 받기
RECHECK_ROUNDS, RECHECK_GAP = 4, 15 * 60   # 거래량이 안 맞으면 15분 간격으로 최대 4번 다시 확인


def wait_for_settle():
    """예약 실행이 동부 20:15보다 일찍 시작했으면(최대 90분 이르면) 그때까지 기다림. 낮에 수동 실행하면 기다리지 않음."""
    now = dt.datetime.now(NY)
    target = now.replace(hour=SETTLE_NY.hour, minute=SETTLE_NY.minute, second=0, microsecond=0)
    early = (target - now).total_seconds()
    if 0 < early <= 90 * 60:
        print(f"동부 {now:%H:%M} — 시간외 거래 마감 뒤 {SETTLE_NY:%H:%M}까지 {early / 60:.0f}분 기다림", flush=True)
        time.sleep(early)


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


NQ_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", "Accept": "application/json"}
XCHECK_DAYS = 5                       # 최근 몇 거래일을 교차 확인할지
XCHECK_TOL, XCHECK_BASE = 0.15, (0.85, 1.15)
BIG_VOL, BIG_QUIET, TINY_VOL = 4.0, 0.02, 0.25


def fetch_nasdaq_volumes(symbol):
    """Nasdaq 일별 시세에서 최근 거래량 {날짜: 거래량}. 막히면 빈 dict"""
    frm = (dt.date.today() - dt.timedelta(days=20)).isoformat()
    to = dt.date.today().isoformat()
    try:
        j = get_json(f"https://api.nasdaq.com/api/quote/{symbol}/historical?assetclass=etf&fromdate={frm}&todate={to}&limit=20", NQ_HEADERS, timeout=20)
        rows = (((j.get("data") or {}).get("tradesTable") or {}).get("rows")) or []
        out = {}
        for row in rows:
            m, d, y = row["date"].split("/")
            v = str(row.get("volume", "")).replace(",", "")
            if v.isdigit():
                out[f"{y}-{m}-{d}"] = int(v)
        return out
    except Exception as e:
        print(f"  Nasdaq {symbol} 시세: 실패 - {e}", flush=True)
        return {}


def crosscheck_volumes(series, partial):
    """시장 지표 최근 5거래일 거래량을 Nasdaq과 맞춰 보고(틀린 날은 바로잡음), 이상값은 잠정으로. → fixed"""
    fixed = {}
    for s in MARKET:
        rows = series.get(s)
        if not rows or len(rows) < 30:
            continue
        nq = fetch_nasdaq_volumes(s)
        time.sleep(0.6)
        tail = range(len(rows) - XCHECK_DAYS, len(rows))
        pairs = [(i, rows[i][4], nq[rows[i][0]]) for i in tail if rows[i][0] in nq and nq[rows[i][0]] > 0]
        confirmed = set()                     # 두 출처가 맞은 날(이상값 검사에서 '너무 큼'은 봐줌: 지수 재편일 등 실제 대량 거래)
        if pairs:
            ratios = sorted(td / q for _, td, q in pairs)
            med = ratios[len(ratios) // 2]
            if XCHECK_BASE[0] <= med <= XCHECK_BASE[1]:
                for i, td, q in pairs:
                    if abs(td / q - 1) <= XCHECK_TOL:
                        confirmed.add(i)
                    else:
                        rows[i][4] = q
                        confirmed.add(i)
                        fixed.setdefault(s, {})[rows[i][0]] = [td, q]
                        if rows[i][0] in partial.get(s, []):   # Nasdaq 확정값으로 바꿨으니 잠정 해제
                            partial[s] = [d for d in partial[s] if d != rows[i][0]]
                            if not partial[s]:
                                partial.pop(s)
                        print(f"  {s} {rows[i][0]} 거래량 바로잡음: Twelve Data {td:,} → Nasdaq {q:,}", flush=True)
            else:
                print(f"  {s} Nasdaq 거래량 기준이 달라 교차 확인 생략 (5일 중앙값 비율 {med:.2f})", flush=True)
        else:
            print(f"  {s} Nasdaq 거래량 없음 — 이상값 검사만", flush=True)
        # 이상값 검사: 최근 5거래일
        for i in tail:
            avg = sum(r[4] for r in rows[i - 20:i]) / 20
            v, chg = rows[i][4], abs(rows[i][3] / rows[i - 1][3] - 1)
            if avg > 0 and (v < avg * TINY_VOL or (i not in confirmed and v > avg * BIG_VOL and chg < BIG_QUIET)):
                if rows[i][0] not in partial.get(s, []):
                    partial[s] = partial.get(s, []) + [rows[i][0]]
                print(f"  {s} {rows[i][0]} 거래량 이상값 → 잠정: {v:,} (20일 평균 {avg:,.0f}, 등락 {chg * 100:.1f}%)", flush=True)
    return fixed


def _find_rows(j):
    """Nasdaq 응답 안에서 symbol·marketCap이 있는 행 목록을 찾음 (응답 모양이 조금 바뀌어도 견디게)"""
    if isinstance(j, list):
        if j and isinstance(j[0], dict) and "symbol" in j[0] and "marketCap" in j[0]:
            return j
        for x in j:
            r = _find_rows(x)
            if r:
                return r
    elif isinstance(j, dict):
        for x in j.values():
            r = _find_rows(x)
            if r:
                return r
    return None


def fetch_ndx_weights():
    """나스닥100 구성종목 시가총액 비중(%) {symbol: 비중}. 실패하면 None"""
    try:
        j = get_json("https://api.nasdaq.com/api/quote/list-type/nasdaq100", NQ_HEADERS, timeout=20)
        rows = _find_rows(j) or []
        caps = {}
        for row in rows:
            c = re.sub(r"[^0-9.]", "", str(row.get("marketCap", "")))
            if c:
                caps[str(row["symbol"]).upper().replace(".", "-")] = float(c)
        total = sum(caps.values())
        if len(caps) < 90 or total <= 0:
            print(f"  나스닥100 비중: 종목 수가 이상함({len(caps)}) — 전날 값 유지", flush=True)
            return None
        print(f"  나스닥100 비중: {len(caps)}종목", flush=True)
        return {s: round(c / total * 100, 4) for s, c in caps.items()}
    except Exception as e:
        print(f"  나스닥100 비중: 실패 - {e}", flush=True)
        return None


AV_KEY = os.environ.get("ALPHAVANTAGE_KEY", "").strip()
_AV_LAST = [0.0]


def av_get(params, as_text=False):
    """Alpha Vantage 요청: 무료 키는 1초에 1번까지라 요청 사이를 3초 띄움(2026-11-12 연속 요청이 막힌 일 이후)"""
    time.sleep(max(0.0, 3.0 - (time.time() - _AV_LAST[0])))
    url = "https://www.alphavantage.co/query?" + urllib.parse.urlencode(dict(params, apikey=AV_KEY))
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "trend-dashboard"}), timeout=40) as r:
            text = r.read().decode("utf-8", "replace")
    finally:
        _AV_LAST[0] = time.time()
    return text if as_text else json.loads(text)


def fetch_qqq_holdings_av():
    """Alpha Vantage ETF_PROFILE: QQQ 보유 종목 비중(%) {symbol: 비중}. 실패하면 None"""
    if not AV_KEY:
        return None
    try:
        j = av_get({"function": "ETF_PROFILE", "symbol": "QQQ"})
        rows = j.get("holdings") or []
        w, unnamed = {}, []
        for h in rows:
            sym = str(h.get("symbol", "")).upper().replace(".", "-")
            try:
                v = float(h.get("weight"))
            except (TypeError, ValueError):
                continue
            if re.fullmatch(r"[A-Z][A-Z0-9-]{0,6}", sym) and v > 0:
                w[sym] = round(v * 100, 4)
            elif v > 0:
                unnamed.append((str(h.get("description", "")).upper(), round(v * 100, 4)))
        # 티커가 "n/a"로 오는 보유 종목(해외 상장 등, 예: FERROVIAL SE)은 회사 이름 첫 단어로 우리 목록과 맞춤. 현금·선물은 버림
        for desc, v in unnamed:
            for t, nm in NAMES.items():
                key = re.sub(r"[^A-Z0-9 ]", "", nm.upper()).split()
                if t not in w and key and len(key[0]) >= 4 and re.search(r"\b" + re.escape(key[0]) + r"\b", desc):
                    w[t] = v
                    print(f"  QQQ 보유 종목: 티커 없는 '{desc}' → {t}", flush=True)
                    break
        if len(w) < 90:
            print(f"  QQQ 보유 종목: 개수가 이상함({len(w)}) - {str(j)[:120]!r}", flush=True)
            return None
        print(f"  QQQ 보유 종목: {len(w)}개 (합 {sum(w.values()):.1f}%)", flush=True)
        return w
    except Exception as e:
        print(f"  QQQ 보유 종목: 실패 - {e}", flush=True)
        return None


NDX_NEWS_RSS = "https://ir.nasdaq.com/rss/news-releases.xml"


def fetch_ndx_announcements():
    """Nasdaq IR 보도자료 RSS에서 나스닥100 편입·교체·정기 변경 발표만 골라 [{id, date, title, url}]. 실패하면 None"""
    try:
        req = urllib.request.Request(NDX_NEWS_RSS, headers={"User-Agent": "trend-dashboard (RSS reader)"})
        with urllib.request.urlopen(req, timeout=30) as r:
            xml = r.read().decode("utf-8", "replace")
        import xml.etree.ElementTree as ET
        from email.utils import parsedate_to_datetime
        out = []
        for it in ET.fromstring(xml).iter("item"):
            title = (it.findtext("title") or "").strip()
            if not NDX_NEWS_RE[0].search(title) or not NDX_NEWS_RE[1].search(title):
                continue
            link = (it.findtext("link") or "").strip()
            try:
                d = parsedate_to_datetime(it.findtext("pubDate")).date().isoformat()
            except Exception:
                d = ""
            out.append({"id": "press-" + re.sub(r"\W+", "", title.lower())[:80], "date": d, "kind": "press", "title": title, "url": link, "source": "Nasdaq"})
        print(f"  나스닥100 발표: RSS에서 {len(out)}건", flush=True)
        return out
    except Exception as e:
        print(f"  나스닥100 발표: 실패 - {e}", flush=True)
        return None


def fetch_ndx_news_av(days=8):
    """Alpha Vantage 뉴스(NDAQ·QQQ 관련, 최근 days일)에서 나스닥100 편입·교체·정기 변경 기사만. 실패하면 None
    (Nasdaq IR RSS가 GitHub에서 막힐 때를 대비한 두 번째 출처. 주 1회 2번 요청)"""
    if not AV_KEY:
        return None
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).strftime("%Y%m%dT0000")
    out, ok = [], False
    for tk in ("NDAQ", "QQQ"):
        try:
            j = av_get({"function": "NEWS_SENTIMENT", "tickers": tk, "time_from": since, "limit": 200, "sort": "LATEST"})
            feed = j.get("feed")
            if feed is None:
                print(f"  나스닥100 기사({tk}): 응답이 이상함 - {str(j)[:120]!r}", flush=True)
                continue
            ok = True
            for it in feed:
                title = (it.get("title") or "").strip()
                if not NDX_NEWS_RE[0].search(title) or not NDX_NEWS_RE[1].search(title):
                    continue
                tp = it.get("time_published") or ""
                d = f"{tp[:4]}-{tp[4:6]}-{tp[6:8]}" if len(tp) >= 8 else ""
                out.append({"id": "press-" + re.sub(r"\W+", "", title.lower())[:80], "date": d, "kind": "press", "title": title,
                            "url": it.get("url", ""), "source": it.get("source", "")})
        except Exception as e:
            print(f"  나스닥100 기사({tk}): 실패 - {e}", flush=True)
    if not ok:
        return None
    print(f"  나스닥100 기사: Alpha Vantage에서 {len(out)}건", flush=True)
    return out


NDX_NEWS_RE = (re.compile(r"nasdaq-?\s?100", re.I), re.compile(r"join|replac|change|reconstitut|rebalanc|added|removed|to be added|to be removed", re.I))


def first_trading_day_of_week(rows):
    """마지막 거래일이 그 주의 첫 거래일인가(바로 전 거래일이 다른 주)"""
    if len(rows) < 2:
        return False
    a, b = dt.date.fromisoformat(rows[-2][0]), dt.date.fromisoformat(rows[-1][0])
    return a.isocalendar()[:2] != b.isocalendar()[:2]


def fetch_earnings_av(symbols):
    """Alpha Vantage 실적 달력(앞으로 3개월, CSV 한 번) → {symbol: [{date, time}]}. 실패하면 None"""
    if not AV_KEY:
        return None
    try:
        text = av_get({"function": "EARNINGS_CALENDAR", "horizon": "3month"}, as_text=True)
        import csv, io
        rows = list(csv.DictReader(io.StringIO(text)))
        # 정상이면 미국 전체 3개월치 수천 건. 수십 건도 안 되면 한도 안내문 등으로 보고 실패 처리(전날 일정 유지)
        if len(rows) < 100 or "reportDate" not in rows[0]:
            print(f"  Alpha Vantage 실적: 응답이 이상함 - {text[:120]!r}", flush=True)
            return None
        want, found = set(symbols), {}
        for row in rows:
            s = row.get("symbol", "").upper()
            if s in want and row.get("reportDate"):
                found.setdefault(s, []).append({"date": row["reportDate"], "time": row.get("timeOfTheDay", "")})
        for v in found.values():
            v.sort(key=lambda x: x["date"])
        print(f"  Alpha Vantage 실적: 전체 {len(rows)}건 중 우리 종목 {len(found)}개", flush=True)
        return found
    except Exception as e:
        print(f"  Alpha Vantage 실적: 실패 - {e}", flush=True)
        return None


def earnings_nasdaq(prev, today):
    """(예전 방식) Nasdaq 실적 캘린더: 지난 발표일은 전에 받은 것을 이어 쓰고, 그 뒤 날짜와 앞으로 60일만 새로 받음"""
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
    return hist, earnings, upto_new


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
    wait_for_settle()

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

    # 거래량 확정 확인: 시장 지표를 다시 받아 마지막 날 거래량 비교. 안 맞는 것만 15분 간격으로 최대 4번
    pending = [s for s in MARKET if s not in failed and s in series]
    partial = {}
    for rnd in range(1, RECHECK_ROUNDS + 1):
        t_round = time.time()
        partial, still = {}, []
        for s in pending:
            again = fetch_series(s, DAYS_MARKET)
            time.sleep(GAP)
            first = series[s]
            if again:
                series[s] = again
            rows = series[s]
            last = rows[-1]
            avg = sum(r[4] for r in rows[-21:-1]) / 20 if len(rows) > 21 else 0
            changed = (not again) or (first[-1][0] == last[0] and abs(first[-1][4] - last[4]) > max(1, last[4]) * 0.01)
            tiny = avg > 0 and last[4] < avg * 0.25
            if changed or tiny:
                partial[s] = last[0]
                still.append(s)
                print(f"  [{rnd}차] {s} {last[0]} 거래량 아직 안 맞음: {first[-1][4]:,} → {last[4]:,} (20일 평균 {avg:,.0f})", flush=True)
        if not still:
            print(f"  거래량 확정 ({rnd}차 확인)", flush=True)
            break
        pending = still
        if rnd < RECHECK_ROUNDS:
            time.sleep(max(0.0, RECHECK_GAP - (time.time() - t_round)))

    partial = {s: [d] for s, d in partial.items()}      # 날짜 목록으로 (여러 날이 잠정일 수 있음)
    print("거래량 교차 확인 (Nasdaq)", flush=True)
    fixed = crosscheck_volumes(series, partial)
    # QQQ 비중: Alpha Vantage 보유 종목 → (막히면) Nasdaq → 전날 값
    print("QQQ 보유 종목 받기 (Alpha Vantage)", flush=True)
    hold = fetch_qqq_holdings_av()
    ndxw = hold or fetch_ndx_weights()
    ndxw_at = dt.date.today().isoformat() if ndxw else prev.get("ndxwAt")
    ndxw = ndxw or prev.get("ndxw") or {}

    # 알림: 전에 적힌 것 + 새로 생긴 것(같은 id는 한 번만), 최근 30건
    notices = list(prev.get("notices") or [])
    have = {n["id"] for n in notices}
    def add_notice(n):
        if n["id"] not in have:
            notices.append(n); have.add(n["id"])
    today_s = dt.date.today().isoformat()
    if hold:
        # 구성 차이는 '지금 상태'라서 예전 차이 알림은 지우고 지금 것만 남김(맞으면 알림 없음)
        notices = [n for n in notices if n.get("kind") != "holdings"]
        have = {n["id"] for n in notices}
        mine = set(STOCKS)
        held = {s for s in hold if not (s == "GOOG" and "GOOGL" in mine)}
        added, removed = sorted(held - mine), sorted(mine - held)
        if added or removed:
            add_notice({"id": "hold-" + ",".join(added) + "|" + ",".join(removed), "date": today_s, "kind": "holdings",
                        "title": "QQQ 보유 종목이 대시보드 목록과 다름",
                        "detail": ("새로 들어옴: " + ", ".join(added) if added else "") + (" · " if added and removed else "") + ("빠짐: " + ", ".join(removed) if removed else ""),
                        "added": added, "removed": removed})
            print(f"  QQQ 구성 차이: +{added} -{removed}", flush=True)
    news_checked = prev.get("newsCheckedAt")
    q = series.get("QQQ") or []
    # 매주 그 주 첫 거래일 자료를 받는 날 확인. 그날 실패했으면 그 주 안에 다음 실행에서 다시
    wk = lambda d: dt.date.fromisoformat(d).isocalendar()[:2]
    this_week = wk(q[-1][0]) if q else None
    if first_trading_day_of_week(q) or not news_checked or (this_week and wk(news_checked) < this_week):
        print("나스닥100 변경 발표 확인 (주 1회)", flush=True)
        got = [a for a in (fetch_ndx_announcements(), fetch_ndx_news_av()) if a is not None]
        if got:
            for ann in got:
                for n in ann:
                    add_notice(n)
            news_checked = today_s
    notices = sorted(notices, key=lambda n: n.get("date", ""), reverse=True)[:30]

    today = dt.date.today()
    print("실적 일정 받기 (Alpha Vantage)", flush=True)
    av = fetch_earnings_av(STOCKS)
    if av is not None:
        # 지난 발표일: 전에 받아 둔 것 + 전에 '다가오는 일정'이었는데 이제 지나간 날
        hist_from = (today - dt.timedelta(days=HIST_DAYS)).isoformat()
        hist = {s: list(v) for s, v in (prev.get("earnHist") or {}).items()}
        for s, e in (prev.get("earnings") or {}).items():
            if e.get("date") and e["date"] < today.isoformat():
                hist.setdefault(s, []).append(e["date"])
        hist = {s: sorted({x for x in v if x >= hist_from}) for s, v in hist.items()}
        hist = {s: v for s, v in hist.items() if v}
        earnings = {}
        for s, rows in av.items():
            nxt = [x for x in rows if x["date"] >= today.isoformat() and x["date"] <= (today + dt.timedelta(days=AHEAD_DAYS)).isoformat()]
            if nxt:
                earnings[s] = nxt[0]
        upto_new = (today - dt.timedelta(days=1)).isoformat()
        print(f"  다가오는 실적 {len(earnings)}종목, 지난 실적 {sum(len(v) for v in hist.values())}건", flush=True)
    else:
        hist, earnings, upto_new = earnings_nasdaq(prev, today)

    data = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "asOf": series["QQQ"][-1][0],
        "failed": failed,
        "partial": partial,
        "fixed": fixed,
        "ndxw": ndxw,
        "notices": notices,
        "newsCheckedAt": news_checked,
        "ndxwAt": ndxw_at,
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
