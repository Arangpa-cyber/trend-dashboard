// 매물대 백테스트: index.html 함수를 그대로 써서, 매일 그날까지의 일봉(앱과 같은 개수)으로만 판단
// node backtest/run.js backtest/prices.json.gz [시작 인덱스] → backtest/events.json, 그다음 node backtest/report.js
const fs = require('fs'), zlib = require('zlib');
const A = require('./app.js')(require('path').join(__dirname, '..', 'index.html'));
const src = process.argv[2], raw = src.endsWith('.gz') ? zlib.gunzipSync(fs.readFileSync(src)) : fs.readFileSync(src);
const J = JSON.parse(raw), SER = J.series;
const toD = (rows) => rows.map((r) => ({ t: r[0], h: r[1], l: r[2], c: r[3], v: r[4] }));
const MK = new Set(A.MARKET);
const TK = Object.keys(SER).filter((t) => !MK.has(t));
const D = {}; for (const t of Object.keys(SER)) D[t] = toD(SER[t]);
const Q = D.QQQ, QE = D.QQQE, dates = Q.map((r) => r.t);
const NS = A.DAYS_STOCK, NM = A.DAYS_MARKET;
const START = +(process.argv[3] || Math.max(NS, 300));
const HOLD = 60, HARD = 0.10, RS_MIN = A.BUY_RS_MIN ?? A.CHEAT_RS_MIN;
const idxOf = {}; for (const t of TK) { idxOf[t] = {}; D[t].forEach((r, i) => (idxOf[t][r.t] = i)); }
const qIdx = {}; Q.forEach((r, i) => (qIdx[r.t] = i));

// 베이스 거래량 분포(40칸) → POC·VAL·VAH
function va(rows) {
  const N = 40, lo = Math.min(...rows.map((r) => r.l)), hi = Math.max(...rows.map((r) => r.h)), st = (hi - lo) / N;
  if (!(st > 0)) return null;
  const b = new Array(N).fill(0);
  for (const r of rows) { const i0 = Math.min(N - 1, Math.floor((r.l - lo) / st)), i1 = Math.min(N - 1, Math.floor((r.h - lo) / st)); for (let i = i0; i <= i1; i++) b[i] += r.v / (i1 - i0 + 1); }
  let poc = 0; b.forEach((v, i) => { if (v > b[poc]) poc = i; });
  const tot = b.reduce((a, v) => a + v, 0); let a = poc, z = poc, s = b[poc];
  while (s < tot * 0.7) { const up = z + 1 < N ? b[z + 1] : -1, dn = a > 0 ? b[a - 1] : -1; if (up >= dn) { z++; s += up; } else { a--; s += dn; } }
  return { POC: lo + (poc + 0.5) * st, VAL: lo + a * st, VAH: lo + (z + 1) * st, lo, hi };
}
// 1년 매물대 필터(앱 volProfile 그대로)
function filters(dd, base) {
  const n = dd.length, vp = A.volProfile(dd, Math.max(0, n - 252));
  const out = { F1: false, F2: false, F3: false };
  if (!vp || !base) return out;
  const b0 = vp.bands[0];
  if (b0) { const a = vp.lo + b0.a * vp.st, z = vp.lo + (b0.b + 1) * vp.st; out.F1 = Math.max(0, Math.min(z, base.top) - Math.max(a, base.bottom)) / (z - a) >= 0.5; }
  let pk = 0; vp.ratio.forEach((v, i) => { if (v > vp.ratio[pk]) pk = i; });
  const poc = vp.lo + (pk + 0.5) * vp.st; out.F2 = poc >= base.bottom && poc <= base.top;
  const bi = dd.findIndex((r) => r.t === base.from);
  if (bi >= 0) { const bv = dd.slice(bi).reduce((s, r) => s + r.v, 0) / (n - bi), yv = dd.slice(-252).reduce((s, r) => s + r.v, 0) / Math.min(252, n); out.F3 = bv > yv; }
  return out;
}
const sma = (d, i, k) => { if (i < k - 1) return null; let s = 0; for (let j = i - k + 1; j <= i; j++) s += d[j].c; return s / k; };
// 모의 매매: 진입 종가에서 최대 HOLD일, 모든 규칙에 -10% 손절 포함
function sim(d, i0, lv) {
  const en = d[i0].c, res = {};
  const rules = { X1: () => false, X2: (j) => d[j].c < lv.trig, X3: (j) => lv.VAH != null && d[j].c < lv.VAH, X4: (j) => { const m = sma(d, j, 50); return m != null && d[j].c < m; } };
  for (const [k, f] of Object.entries(rules)) {
    let out = null;
    for (let j = i0 + 1; j < d.length && j <= i0 + HOLD; j++) if (d[j].c < en * (1 - HARD) || f(j)) { out = [d[j].c / en - 1, j - i0, 1]; break; }
    if (!out) { const j = Math.min(d.length - 1, i0 + HOLD); out = [d[j].c / en - 1, j - i0, 0]; }
    res[k] = out;
  }
  return res;
}
function fwd(t, i0, h) {
  const d = D[t]; if (i0 + h >= d.length) return null;
  const qa = qIdx[d[i0].t], qb = qIdx[d[i0 + h].t]; if (qa == null || qb == null) return null;
  return d[i0 + h].c / d[i0].c - 1 - (Q[qb].c / Q[qa].c - 1);
}
const EV = []; const prev = {}; const lastE = {};
const t0 = Date.now();
for (let qi = START; qi < Q.length; qi++) {
  const day = dates[qi];
  const mk = A.analyzeMarket(Q.slice(Math.max(0, qi + 1 - NM), qi + 1), QE ? QE.slice(0, (QE.findIndex((r) => r.t > day) + 1 || QE.length + 1) - 1).slice(-NM) : null);
  // RS 순위
  const sc = {}, cut = {};
  for (const t of TK) { const i = idxOf[t][day]; if (i == null || i < 260) continue; const dd = D[t].slice(Math.max(0, i + 1 - NS), i + 1); cut[t] = [i, dd]; sc[t] = A.rsScore(dd, 0); }
  const RS = A.ratings(sc);
  for (const t of Object.keys(cut)) {
    const [i, dd] = cut[t], rs = RS[t];
    const rg = A.regimeOf(dd), cls = A.classify(dd, rs), ch = rs != null && A.cheatOf ? A.cheatOf(dd, rs) : null;   // 치트는 2026-11-16 앱에서 삭제됨(이전 커밋의 index.html로만 시험 가능)
    const p = prev[t]; prev[t] = { cls, ch, i };
    if (!p || p.i !== i - 1 || !rg || rg.r !== 2 || rs < RS_MIN) continue;
    const base = p.cls.box;   // 어제 기준 베이스
    const baseRows = base ? dd.slice(dd.findIndex((r) => r.t === base.from), dd.length - 1) : null;
    const v = baseRows && baseRows.length >= A.BASE_MIN_DAYS ? va(baseRows) : null;
    const push = (type, trig, extra) => {
      const key = t + type; if (lastE[key] != null && i - lastE[key] < 10) return; lastE[key] = i;
      const f = filters(dd.slice(0, -1), base);
      EV.push({ t, day, yr: day.slice(0, 4), type, mk: mk.cls, rs, ...f, H: v && base ? v.VAH >= base.top * 0.95 : null,
        f20: fwd(t, i, 20), f40: fwd(t, i, 40), f60: fwd(t, i, 60), sim: sim(D[t], i, { trig, VAH: v ? v.VAH : null }), ...extra });
    };
    // E1 피벗 돌파(매수 범위 첫날)
    if (cls.pos === 'break' && !cls.chase && p.cls.pos !== 'break' && base) push('E1', base.top, { distVAH: v ? 1 - v.VAH / dd[dd.length - 1].c : null });
    // E2 치트 발동 첫날 / E4 그중 치트 피벗 >= VAH
    if (p.ch && dd[dd.length - 2].c <= p.ch.pivot && dd[dd.length - 1].c > p.ch.pivot) { push('E2', p.ch.pivot, { kind: p.ch.kind }); if (v && p.ch.pivot >= v.VAH) push('E4', p.ch.pivot, { kind: p.ch.kind }); }   // 앱 ch.trig 는 오늘 고가가 구간에 들어가 늘 거짓 → 어제 치트 피벗을 오늘 종가가 넘으면 발동
    // E3 VAH 넘기(베이스 안, 피벗 아래)
    if (v && base && dd[dd.length - 2].c <= v.VAH && dd[dd.length - 1].c > v.VAH && dd[dd.length - 1].c < base.top && p.cls.pos !== 'out') push('E3', v.VAH, {});
  }
  if (qi % 50 === 0) process.stderr.write(`${day} 사건 ${EV.length} (${((Date.now() - t0) / 1000).toFixed(0)}초)\n`);
}
fs.writeFileSync(__dirname + '/events.json', JSON.stringify(EV));
console.log('사건', EV.length, '기간', dates[START], '-', dates[Q.length - 1]);
