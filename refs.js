/* 条文への参照を、年度をまたいで解決する。

   コンメンタールの参照は「2026年の 5.02」のように、書いた時点の年度とIDで持つ。
   採番が変われば別の年度では別のIDになるが、差分が年度間の対応関係を
   持っているので、隣り合う年度へ1つずつ写していけば辿り着ける。
   これにより、改正のたびに解説を書き直す必要がなくなる。

   diff.js に依存する（ブラウザ・Node どちらでも動く）。 */

/** 隣り合う年度の対応表を作る。older→newer と newer→older の両方向 */
function makeChain(diffs) {
  const fwd = new Map(), back = new Map();
  for (const d of diffs) {
    const f = new Map(), b = new Map();
    for (const [a, bb] of d.pairs) { f.set(a, bb); b.set(bb, a); }
    fwd.set(d.from + "→" + d.to, f);
    back.set(d.to + "→" + d.from, b);
  }
  return {fwd, back};
}

/** ref（{year,id}）を toYear のIDに読み替える。辿れなければ null */
function resolveAcrossYears(ref, toYear, years, chain) {
  if (ref.year === toYear) return ref.id;
  const from = years.indexOf(ref.year), to = years.indexOf(toYear);
  if (from < 0 || to < 0) return null;
  let id = ref.id;
  const step = from < to ? 1 : -1;
  for (let i = from; i !== to; i += step) {
    const a = years[i], b = years[i + step];
    const m = step > 0 ? chain.fwd.get(a + "→" + b) : chain.back.get(a + "→" + b);
    if (!m) return null;
    id = m.get(id);
    if (id === undefined) return null;   // その年度には存在しない（新設前・廃止後）
  }
  return id;
}

/** 有効期間の判定。from/to は null で開いた区間 */
function isValid(valid, year) {
  if (!valid) return true;
  if (valid.from && year < valid.from) return false;
  if (valid.to && year > valid.to) return false;
  return true;
}

if (typeof module !== "undefined") module.exports = {makeChain, resolveAcrossYears, isValid};
