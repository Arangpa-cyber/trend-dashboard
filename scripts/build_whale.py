#!/usr/bin/env python3
"""큰손 13F 보유 종목 파일 만들기 (분기마다 공시가 나오면 손으로 한 번 실행 · 반자동)

    python3 scripts/build_whale.py duquesne

- whales/index.json 의 큰손(cik)으로 SEC EDGAR에서 최근 13F-HR 12개 분기를 받아
  whales/<id>/<분기>.json 을 만들고 index.json 의 latest 를 바꿉니다.
- 13F에는 티커가 없고 CUSIP만 있어 whales/cusip.json 으로 티커·종류(stock/etf)를 맞춥니다.
  상위 종목 중 cusip.json에 없는 것이 있으면 멈추고 목록을 보여 줍니다 → cusip.json에 적고 다시 실행.
- 비중 = 그 종목 보통주 평가액 ÷ 13F 전체 평가액(옵션 포함, 공시 기준과 같음). ETF는 빼고 상위 N개.
- 변화 = 직전 분기 대비 보통주 주식 수(±1% 안은 유지), 콜·풋 = 같은 종목 옵션이 있으면 표시
- 보유 = 지금까지 끊기지 않고 보통주를 들고 있던 분기 수(받은 12개 분기 안에서, qMax와 같으면 그 이상)
- SEC는 User-Agent에 연락처를 요구합니다: 환경변수 SEC_UA 에 "이름 이메일"을 넣고 실행하세요.
"""
import json, os, re, sys, time, urllib.request, xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = os.path.join(ROOT, "whales")
UA = {"User-Agent": os.environ.get("SEC_UA", "trend-dashboard research bot")}
TOP_N = 10


def get(u):
    time.sleep(0.2)
    return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30).read()


def filings(cik, n=12):
    sub = json.loads(get(f"https://data.sec.gov/submissions/CIK{str(cik).zfill(10)}.json"))
    r = sub["filings"]["recent"]
    out, seen = [], set()
    for i, form in enumerate(r["form"]):
        if form not in ("13F-HR", "13F-HR/A") or r["reportDate"][i] in seen:
            continue
        seen.add(r["reportDate"][i])                 # 같은 분기 정정본은 최신(목록 앞) 것만
        acc = r["accessionNumber"][i]
        a = acc.replace("-", "")
        idx = json.loads(get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{a}/index.json"))
        rows = []
        for it in idx["directory"]["item"]:
            nm = it["name"]
            if not nm.lower().endswith(".xml") or "primary_doc" in nm.lower():
                continue
            t = get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{a}/{nm}").decode("utf8", "ignore")
            t = re.sub(r'\sxmlns(:\w+)?="[^"]+"', "", t)
            t = re.sub(r'\s\w+:\w+="[^"]*"', "", t)
            t = re.sub(r"<(/?)\w+:", r"<\1", t)
            try:
                root = ET.fromstring(t)
            except Exception:
                continue
            for e in root.iter("infoTable"):
                g = lambda k: (e.findtext(k) or "").strip()
                rows.append({"name": g("nameOfIssuer"), "cusip": g("cusip").upper(), "value": float(g("value") or 0),
                             "sh": float(e.findtext("shrsOrPrnAmt/sshPrnamt") or 0), "pc": g("putCall").lower()})
            if rows:
                break
        out.append({"filed": r["filingDate"][i], "period": r["reportDate"][i], "acc": acc, "rows": rows})
        print(f"  {r['reportDate'][i]} 공시 {r['filingDate'][i]} · {len(rows)}줄", flush=True)
        if len(out) >= n:
            break
    return out


def main():
    wid = sys.argv[1]
    idx = json.load(open(os.path.join(W, "index.json"), encoding="utf-8"))
    inv = next(x for x in idx["investors"] if x["id"] == wid)
    cmap = json.load(open(os.path.join(W, "cusip.json"), encoding="utf-8"))
    fs = filings(inv["cik"])
    cur, prev = fs[0], fs[1] if len(fs) > 1 else {"rows": []}
    total = sum(r["value"] for r in cur["rows"])

    def stock_sh(f):
        d = {}
        for r in f["rows"]:
            if not r["pc"]:
                d[r["cusip"]] = d.get(r["cusip"], 0) + r["sh"]
        return d

    cs, ps = stock_sh(cur), stock_sh(prev)
    held = [stock_sh(f) for f in fs]
    val = {}
    for r in cur["rows"]:
        if not r["pc"]:
            val[r["cusip"]] = val.get(r["cusip"], 0) + r["value"]
    names = {r["cusip"]: r["name"] for r in cur["rows"]}
    ranked = sorted(val, key=lambda c: -val[c])
    miss = [c for c in ranked[:TOP_N + 6] if c not in cmap]
    if miss:
        print("cusip.json에 없는 상위 종목:", ", ".join(f"{c} {names[c]}" for c in miss))
        sys.exit(1)
    top, skipped = [], []
    for c in ranked:
        tk, kind = cmap[c]["t"], cmap[c].get("kind", "stock")
        if kind != "stock":
            skipped.append(tk)
            continue
        q = 0
        for h in held:
            if c in h:
                q += 1
            else:
                break
        if c not in ps:
            chg, pct = "new", None
        else:
            pct = cs[c] / ps[c] - 1
            chg = "same" if abs(pct) <= 0.01 else "add" if pct > 0 else "trim"
        opt = {r["pc"] for r in cur["rows"] if r["cusip"] == c and r["pc"]}
        top.append({"t": tk, "name": cmap[c].get("name") or names[c].title(), "w": round(val[c] / total * 100, 2), "chg": chg,
                    "pct": None if pct is None else round(pct * 100, 1), "call": "call" in opt, "put": "put" in opt, "q": q,
                    "sh": int(cs[c])})
        if len(top) >= TOP_N:
            break
    y, m = cur["period"][:4], int(cur["period"][5:7])
    name = f"{y}Q{(m - 1) // 3 + 1}"
    out = {"id": wid, "period": cur["period"], "filed": cur["filed"], "acc": cur["acc"], "positions": len(cur["rows"]),
           "total": round(total), "qMax": len(fs), "skipped": skipped, "top": top}
    os.makedirs(os.path.join(W, wid), exist_ok=True)
    json.dump(out, open(os.path.join(W, wid, name + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    inv["latest"] = f"{wid}/{name}.json"
    json.dump(idx, open(os.path.join(W, "index.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{wid}/{name}.json · 상위 {len(top)}종목 · ETF 제외 {skipped}")
    for x in top:
        print(f"  {x['t']:6} {x['w']:5.2f}% {x['chg']:5} {x['pct']} 콜{x['call']} {x['q']}분기")


if __name__ == "__main__":
    main()
