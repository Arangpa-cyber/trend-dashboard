// 추가 시험: ① 1·3·4단계의 베이스(26주 고점) 돌파에 F1 ② 1층 판정별 QQQ 앞날 ③ 2단계 돌파 뒤 '돌파 피벗 아래'
// node backtest/stages.js backtest/prices.json.gz   (run.js를 먼저 돌려 events.json이 있어야 ③을 봄)
const fs = require('fs'), zlib = require('zlib'), path = require('path');
const A = require('./app.js')(path.join(__dirname, '..', 'index.html'));
const src = process.argv[2], J = JSON.parse(src.endsWith('.gz') ? zlib.gunzipSync(fs.readFileSync(src)) : fs.readFileSync(src));
const toD = (rows) => rows.map((r) => ({ t: r[0], h: r[1], l: r[2], c: r[3], v: r[4] }));
const D = {}; for (const t of Object.keys(J.series)) D[t] = toD(J.series[t]);
const MK = new Set(A.MARKET), TK = Object.keys(D).filter((t) => !MK.has(t) && t !== 'FER');
const Q = D.QQQ, QE = D.QQQE, NS = A.DAYS_STOCK, NM = A.DAYS_MARKET, HOLD = 60;
const qIdx = {}; Q.forEach((r, i) => (qIdx[r.t] = i));
const idx = {}; for (const t of TK) { idx[t] = {}; D[t].forEach((r, i) => (idx[t][r.t] = i)); }
const med = (a) => { const s = [...a].sort((x, y) => x - y), n = s.length; return n ? (n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2) : NaN; };
const mean = (a) => (a.length ? a.reduce((s, x) => s + x, 0) / a.length : NaN);
const P = (x) => (isNaN(x) ? '  -  ' : (x >= 0 ? '+' : '') + (x * 100).toFixed(1) + '%');
function fwd(d, i, h) { if (i + h >= d.length) return null; const a = qIdx[d[i].t], b = qIdx[d[i + h].t]; if (a == null || b == null) return null; return d[i + h].c / d[i].c - 1 - (Q[b].c / Q[a].c - 1); }
function sim(d, i0) { const en = d[i0].c; for (let j = i0 + 1; j < d.length && j <= i0 + HOLD; j++) if (d[j].c < en * 0.9) return d[j].c / en - 1; return d[Math.min(d.length - 1, i0 + HOLD)].c / en - 1; }
function F1(dd, base) {
  const vp = A.volProfile(dd, Math.max(0, dd.length - 252)); if (!vp || !vp.bands[0]) return false;
  const b0 = vp.bands[0], a = vp.lo + b0.a * vp.st, z = vp.lo + (b0.b + 1) * vp.st;
  return Math.max(0, Math.min(z, base.top) - Math.max(a, base.bottom)) / (z - a) >= 0.5;
}
const EV = [], MKD = [], prev = {}, last = {};
for (let qi = NS; qi < Q.length; qi++) {
  const day = Q[qi].t;
  const qeEnd = QE.findIndex((r) => r.t > day); const mk = A.analyzeMarket(Q.slice(qi + 1 - NM, qi + 1), QE.slice(0, qeEnd < 0 ? QE.length : qeEnd).slice(-NM));
  const qf = (h) => (qi + h < Q.length ? Q[qi + h].c / Q[qi].c - 1 : null);
  MKD.push({ day, yr: day.slice(0, 4), mk: mk.cls, f20: qf(20), f60: qf(60) });
  const sc = {}, cut = {};
  for (const t of TK) { const i = idx[t][day]; if (i == null || i < 260) continue; const dd = D[t].slice(Math.max(0, i + 1 - NS), i + 1); cut[t] = [i, dd]; sc[t] = A.rsScore(dd, 0); }
  const RS = A.ratings(sc);
  for (const t of Object.keys(cut)) {
    const [i, dd] = cut[t]; const rg = A.regimeOf(dd), cls = A.classify(dd, RS[t]);
    const p = prev[t]; prev[t] = { cls, i, r: rg && rg.r };
    if (!p || p.i !== i - 1 || !rg || !p.cls.box || p.r == null) continue;
    const b = p.cls.box, c0 = dd[dd.length - 2].c, c = dd[dd.length - 1].c;
    if (!(c0 <= b.top && c > b.top)) continue;
    if (last[t] != null && i - last[t] < 10) continue; last[t] = i;
    EV.push({ t, day, yr: day.slice(0, 4), st: p.r, rs: RS[t], depth: (b.top - b.bottom) / b.top, F1: F1(dd.slice(0, -1), b), f20: fwd(D[t], i, 20), f60: fwd(D[t], i, 60), tr: sim(D[t], i), mk: mk.cls });
  }
}
function row(n, ev) { const f = ev.map((e) => e.f20).filter((x) => x != null), g = ev.map((e) => e.f60).filter((x) => x != null), tr = ev.map((e) => e.tr);
  console.log(n.padEnd(34), 'n=' + String(ev.length).padStart(4), '| 20일 평균', P(mean(f)), '중앙', P(med(f)), '| 60일 평균', P(mean(g)), '중앙', P(med(g)), '| 매매 평균', P(mean(tr)), '중앙', P(med(tr)), '이김', (tr.length ? Math.round(tr.filter((x) => x > 0).length / tr.length * 100) : '-') + '%'); }
console.log('== ① 단계별 베이스(26주 고점) 돌파, 어제 단계 기준 ==');
for (const st of [1, 2, 3, 4]) { const e = EV.filter((x) => x.st === st); row(st + '단계 전부', e); row(st + '단계 F1 예', e.filter((x) => x.F1)); row(st + '단계 F1 아니오', e.filter((x) => !x.F1)); row(st + '단계 깊이 35% 이하 · F1 예', e.filter((x) => x.F1 && x.depth <= 0.35)); row(st + '단계 깊이 35% 이하 · F1 아니오', e.filter((x) => !x.F1 && x.depth <= 0.35)); }
for (const st of [1, 3]) for (const y of ['2022', '2023', '2024', '2025', '2026']) { const e = EV.filter((x) => x.st === st && x.yr === y); row(`${y} ${st}단계 F1 예`, e.filter((x) => x.F1)); row(`${y} ${st}단계 F1 아니오`, e.filter((x) => !x.F1)); }
console.log('\n== ② 1층 판정별 QQQ 앞날(모든 거래일) ==');
for (const k of ['go', 'wait', 'stop']) { const m = MKD.filter((x) => x.mk === k); console.log(k.padEnd(5), '일수', m.length, '| QQQ 20일 평균', P(mean(m.map((x) => x.f20).filter((x) => x != null))), '중앙', P(med(m.map((x) => x.f20).filter((x) => x != null))), '| 60일 평균', P(mean(m.map((x) => x.f60).filter((x) => x != null))), '중앙', P(med(m.map((x) => x.f60).filter((x) => x != null)))); }
for (const y of ['2022', '2023', '2024', '2025', '2026']) console.log(y, ['go', 'wait', 'stop'].map((k) => k + ' ' + MKD.filter((x) => x.yr === y && x.mk === k).length + '일').join(' · '));
// wait 기간 구간(연속)
let runs = [], cur = null; MKD.forEach((x) => { if (x.mk === 'wait') { if (!cur) cur = { a: x.day, n: 0, f: x.f20 }; cur.n++; cur.b = x.day; } else if (cur) { runs.push(cur); cur = null; } }); if (cur) runs.push(cur);
console.log('매수 중지 구간:', runs.map((r) => `${r.a}부터 ${r.n}일(시작일 QQQ 20일 ${P(r.f)})`).join(' / '));
fs.writeFileSync(path.join(__dirname, 'stages.json'), JSON.stringify({ EV, MKD }));
