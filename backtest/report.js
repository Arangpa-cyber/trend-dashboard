const EV = JSON.parse(require('fs').readFileSync(__dirname + '/events.json'));
const pct = (x) => (x == null ? '   -  ' : (x >= 0 ? '+' : '') + (x * 100).toFixed(2) + '%');
const med = (a) => { const s = [...a].sort((x, y) => x - y), n = s.length; return n ? (n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2) : null; };
const mean = (a) => (a.length ? a.reduce((s, x) => s + x, 0) / a.length : null);
function row(name, ev) {
  const g = (k) => ev.map((e) => e[k]).filter((x) => x != null);
  const f20 = g('f20'), f60 = g('f60');
  const s = (k) => ev.map((e) => e.sim[k][0]);
  console.log(`${name.padEnd(30)} n=${String(ev.length).padStart(4)} | 20일 평균 ${pct(mean(f20))} 중앙 ${pct(med(f20))} 이김 ${f20.length ? Math.round(f20.filter((x) => x > 0).length / f20.length * 100) : '-'}% | 60일 평균 ${pct(mean(f60))} 중앙 ${pct(med(f60))} | 매매(손절만) ${pct(mean(s('X1')))} 피벗아래 ${pct(mean(s('X2')))} VAH복귀 ${pct(mean(s('X3')))} 50일선 ${pct(mean(s('X4')))}`);
}
const by = (f) => EV.filter(f);
console.log('== 매수 자리 ==');
for (const [k, n] of [['E1', '① 피벗 돌파'], ['E2', '② 치트 발동'], ['E3', '③ VAH 넘기'], ['E4', '④ 치트 중 피벗 ≥ VAH']]) row(n, by((e) => e.type === k));
console.log('\n== ① 피벗 돌파를 필터로 나눔 ==');
const E1 = by((e) => e.type === 'E1');
for (const [k, n] of [['F1', 'F1 1년 최대 띠가 베이스 안'], ['F2', 'F2 1년 POC가 베이스 안'], ['F3', 'F3 베이스 거래량 > 1년 평균'], ['H', 'H VAH가 피벗 5% 안']]) { row(n + ' 예', E1.filter((e) => e[k] === true)); row(n + ' 아니오', E1.filter((e) => e[k] === false)); }
console.log('\n== 1층 판정 ==');
for (const k of ['go', 'wait', 'stop']) row('① 판정 ' + k, E1.filter((e) => e.mk === k));
for (const k of ['go']) { row('② 판정 ' + k, by((e) => e.type === 'E2' && e.mk === k)); row('③ 판정 ' + k, by((e) => e.type === 'E3' && e.mk === k)); }
console.log('\n== 연도별 ==');
const yrs = [...new Set(EV.map((e) => e.yr))].sort();
for (const y of yrs) { for (const [k, n] of [['E1', '①'], ['E2', '②'], ['E3', '③']]) row(`${y} ${n}`, by((e) => e.yr === y && e.type === k)); }
for (const y of yrs) for (const k of ['F1', 'F2', 'F3', 'H']) row(`${y} ① ${k} 예`, E1.filter((e) => e.yr === y && e[k] === true));
const dv = E1.map((e) => e.distVAH).filter((x) => x != null).sort((a, b) => a - b);
if (dv.length) console.log('\n① 돌파 종가에서 VAH까지 거리 사분위', [0.25, 0.5, 0.75].map((q) => pct(dv[Math.floor(q * (dv.length - 1))])).join(' '));
