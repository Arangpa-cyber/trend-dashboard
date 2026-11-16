// index.html 의 계산 함수를 node 에서 그대로 쓰기 위한 로더 (DOM 은 아무 일도 안 하는 가짜)
const fs = require('fs'), vm = require('vm');
module.exports = function load(htmlPath) {
  const html = fs.readFileSync(htmlPath, 'utf8');
  const i = html.indexOf('<script>', html.indexOf('lightweight-charts')) + 8, j = html.indexOf('</script>', i);
  let code = html.slice(i, j);
  const stub = new Proxy(function () {}, { get: (t, k) => k === Symbol.toPrimitive ? () => '' : k === 'then' ? undefined : stub, apply: () => stub, construct: () => stub, set: () => true });
  const ctx = { console, Math, JSON, Date, Intl, Number, String, Array, Object, Set, Map, Infinity, NaN, isFinite, parseFloat, parseInt, RegExp, Error, Promise,
    document: stub, window: stub, localStorage: { getItem: () => null, setItem() {} }, navigator: stub, location: { search: '', hash: '', href: '' },
    fetch: () => new Promise(() => {}), setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, requestAnimationFrame: () => 0,
    LightweightCharts: stub, ResizeObserver: function () { return stub; }, matchMedia: () => stub, addEventListener() {}, getComputedStyle: () => stub, performance: { now: () => 0 } };
  ctx.globalThis = ctx; ctx.self = ctx;
  // const/let 최상위 선언을 밖에서 읽으려면 var 로 바꿈
  code = code.replace(/^(const|let) /gm, 'var ');
  vm.createContext(ctx);
  try { vm.runInContext(code, ctx, { filename: 'index.js' }); } catch (e) { console.error('로드 중 오류(무시 가능 여부 확인):', e.message); }
  return ctx;
};
