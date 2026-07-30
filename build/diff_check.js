/* 公式改正文書との照合。差分の計算は ../diff.js（ビューアと同じもの）を使う。
   実装を二重に持たないため、検査もブラウザと同じコードを通す。

   使い方:  node build/diff_check.js 2024 2025
*/
const fs = require("fs");
const path = require("path");
const {diffYears} = require("../diff.js");

const ROOT = path.join(__dirname, "..");

/** rules.json をビューアと同じ形（byId / nodes / doc）に読み込む */
function loadYear(year) {
  const doc = JSON.parse(
    fs.readFileSync(path.join(ROOT, "years", year, "data", "rules.json"), "utf-8"));
  const nodes = [], byId = new Map();
  (function walk(n, parent) {
    n.parent = parent;
    nodes.push(n);
    byId.set(n.id, n);
    for (const c of (n.children || [])) walk(c, n.id);
  });
  const walk = (n, parent) => {
    n.parent = parent; nodes.push(n); byId.set(n.id, n);
    for (const c of (n.children || [])) walk(c, n.id);
  };
  for (const ch of doc.chapters) walk(ch, null);
  return {doc, nodes, byId};
}

const OFFICIAL = JSON.parse(fs.readFileSync(path.join(__dirname, "official.json"), "utf-8"));

function main() {
  const [from, to] = process.argv.slice(2);
  const o = OFFICIAL[`${from}-${to}`];
  const d = diffYears(loadYear(from), loadYear(to));
  const n = d.summary;
  console.log(`[${from} → ${to}] 追加${n.added} 文言${n.text} 採番${n.number} ` +
              `係り先${n.parent} 削除${n.removed}   ${d.entries.length}件`);
  if (!o) {
    console.log("  公式照合         : 未実施（build/official.json に対応表がありません）");
    return 0;
  }
  const ids = new Set();
  for (const e of d.entries) { ids.add(e.id); if (e.old_id) ids.add(e.old_id); }
  // 公式が指すIDは、構造の見直しで変わりうるので引用形式でも突き合わせる
  const alias = new Map();
  for (const y of [from, to])
    for (const nd of loadYear(y).nodes)
      for (const a of (nd.cite_ids || []))
        if (ids.has(nd.id)) alias.set(a, nd.id);

  const tagged = new Set();
  const miss = [];
  for (const it of o.items) {
    const hit = it.targets.filter(t => ids.has(t) || alias.has(t)).map(t => ids.has(t) ? t : alias.get(t));
    if (!hit.length) miss.push(`${it.no} ${it.title}`);
    hit.forEach(x => tagged.add(x));
  }
  const rest = d.entries
    .filter(e => !tagged.has(e.id) && !tagged.has(e.old_id || e.id))
    .map(e => e.id);
  const known = o.known || {};
  const explained = rest.filter(x => known[x]);
  const extra = rest.filter(x => !known[x]);

  console.log(`  公式${o.items.length}項目: 検出 ${o.items.length - miss.length} / ` +
              `拾い漏れ ${miss.length} / 公式外 ${extra.length}`);
  miss.forEach(x => console.log(`    ✗ 拾い漏れ: ${x}`));
  extra.forEach(x => console.log(`    ✗ 公式外: ${x}`));
  explained.forEach(x => {
    console.log(`    公式外（説明済み）: ${x}`);
    console.log(`      ${known[x]}`);
  });
  return miss.length + extra.length ? 1 : 0;
}

process.exit(main());
