"use strict";
/* 条文の解説。
   条文とは独立した読み物だが、参照は年度をまたいで条文に解決される（refs.js）。 */
const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

const WRITTEN_YEAR = "2026";   // 解説を書いた年度。参照はここを起点に読み替える
const S = {manifest: null, com: null, years: [], year: null, cache: {}, chain: null,
           q: "", tag: null, past: false};

async function getJSON(p) {
  const r = await fetch(p, {cache: "no-cache"});
  if (!r.ok) throw new Error(p + " が読めません (" + r.status + ")");
  return r.json();
}

function indexYear(doc) {
  const nodes = [], byId = new Map();
  const walk = (n, parent) => {
    n.parent = parent; nodes.push(n); byId.set(n.id, n);
    for (const c of (n.children || [])) walk(c, n.id);
  };
  for (const ch of doc.chapters) walk(ch, null);
  return {doc, nodes, byId};
}
async function loadYear(y) {
  if (!S.cache[y]) {
    const info = S.manifest.years.find(x => x.year === y);
    S.cache[y] = indexYear(await getJSON(info.path));
  }
  return S.cache[y];
}

/* 参照を解決するには、書かれた年度と表示中の年度の間の差分が要る。
   必要な区間だけ計算する（全年度を読み込まない） */
async function ensureChain(fromY, toY) {
  const ys = S.years;
  let i = ys.indexOf(fromY), j = ys.indexOf(toY);
  if (i < 0 || j < 0) return;
  if (i > j) [i, j] = [j, i];
  const diffs = [];
  for (let k = i; k < j; k++) {
    const key = ys[k] + "-" + ys[k + 1];
    if (!S.diffCache) S.diffCache = {};
    if (!S.diffCache[key]) {
      S.diffCache[key] = diffYears(await loadYear(ys[k]), await loadYear(ys[k + 1]));
    }
    diffs.push(S.diffCache[key]);
  }
  const all = Object.values(S.diffCache || {});
  S.chain = makeChain(all);
}

async function resolve1(r) {
  await ensureChain(r.year, S.year);
  const id = resolveAcrossYears(r, S.year, S.years, S.chain);
  const n = id && (await loadYear(S.year)).byId.get(id);
  return {ref: r, id, node: n || null};
}
/* 添字を保ちたいので、参照が無い要素は null のまま残す */
async function resolveAll(list) {
  const out = [];
  for (const r of (list || [])) out.push(r ? await resolve1(r) : null);
  return out;
}

/* ===== 描画 ===== */
const TERM = v => {
  if (!v || (!v.from && !v.to)) return "";
  return (v.from || "") + "〜" + (v.to || "現行");
};

/* 表示中の年度に効いているか。効いていないものは既定で隠すが、
   廃止された規則の解説も記録なので、辿れなくはしない */
const inTerm = e => isValid(e.valid, S.year);
const shown = e => S.past || inTerm(e);

function refHTML(r, cls) {
  const {ref, id, node} = r;
  if (!id || !node) {
    return '<span class="' + cls + ' gone"><b>' + esc(ref.id) + "</b>" +
      '<span class="t">' + esc(ref.year) + "年時点・" + esc(S.year) + "年には無い</span></span>";
  }
  const moved = id !== ref.id ? '<span class="t">' + esc(ref.year) + "年は " + esc(ref.id) + "</span>" : "";
  return '<a class="' + cls + '" href="index.html#' + encodeURIComponent(id) + '">' +
    "<b>" + esc(node.cite || id) + "</b>" +
    '<span class="t">' + esc(node.title || "") + "</span>" + moved + "</a>";
}

const paras = t => (t || "").split("\n").filter(x => x.trim())
  .map(p => "<p>" + esc(p) + "</p>").join("");
/* 要素ごとに根拠の身分を示す。条文に書いてあるのか、規則全体から導いたのか、
   どこにも書いていない私見なのかを、読み手が区別できなければ解説の意味がない。
   文字列だけの要素は「読めばそのまま分かる」ものとして印を付けない。 */
const SRC = {定義: "src-def", 導出: "src-drv", 私見: "src-own"};

function itemHTML(x) {
  if (typeof x === "string") return "<li>" + esc(x) + "</li>";
  const mark = x.s
    ? '<span class="src ' + (SRC[x.s] || "") + '" data-at="' + esc(x.ref || "") + '">' +
      esc(x.s) + "</span>" : "";
  return "<li>" + mark + esc(x.t) + (x.note ? '<span class="sn">' + esc(x.note) + "</span>" : "") + "</li>";
}
const listHTML = (cls, label, items) => (items && items.length)
  ? '<div class="' + cls + '"><span class="lb">' + label + "</span><ol>" +
    items.map(itemHTML).join("") + "</ol></div>" : "";

/* 規則は「要件を満たせば効果が生じる」という形をしている。
   条の中に要件と効果の組が複数あることも多いので、組ごとに区切って示す。 */
function ruleHTML(r, head) {
  return '<section class="rl">' +
    '<div class="rh">' + esc(r.head || "") + (head ? '<span class="at">' + head + "</span>" : "") + "</div>" +
    listHTML("req", "要件", r.elements) +
    (r.effect ? '<div class="eff"><span class="lb">効果</span><div>' + paras(r.effect) + "</div></div>" : "") +
    listHTML("exc", "例外", r.exceptions) +
    (r.note ? '<div class="rn">' + paras(r.note) + "</div>" : "") + "</section>";
}

/* 判断の順序を示す。条文は要件を並列に並べるが、実際の場面では
   どれを先に確かめるかで到達する結論が変わる。分岐は網羅的でなければ意味がない。 */
function treeHTML(t, top) {
  if (!t) return "";
  const kids = (t.b || []).map(n => {
    const cond = '<span class="tc">' + esc(n.c || "") + "</span>";
    const at = n.ref ? '<span class="src src-def" data-at="' + esc(n.ref) + '"></span>' : "";
    const leaf = n.r ? '<span class="tr">' + esc(n.r) + "</span>" : "";
    const sub = n.b ? treeHTML(n, false) : "";
    return "<li>" + cond + leaf + at + (n.note ? '<span class="sn">' + esc(n.note) + "</span>" : "") + sub + "</li>";
  }).join("");
  const q = t.q ? '<div class="tq">' + esc(t.q) + "</div>" : "";
  const body = q + "<ul>" + kids + "</ul>";
  return top ? '<div class="tree"><span class="lb">判断</span><div>' + body + "</div></div>" : body;
}

function entryHTML(e, res) {
  const outOfTerm = !inTerm(e);
  const term = TERM(e.valid);
  const meta = [
    term ? '<span class="valid' + (outOfTerm ? " out" : "") + '">' + esc(term) +
      (outOfTerm ? "・" + esc(S.year) + "年は期間外" : "") + "</span>" : "",
    ...(e.tags || []).map(t => '<span class="tag">' + esc(t) + "</span>"),
  ].filter(Boolean).join("");

  const rules = (e.rules || []).map((r, i) => ruleHTML(r, res.rules[i] ? refHTML(res.rules[i], "at") : "")).join("");
  const rel = res.related.filter(Boolean);
  const related = rel.length
    ? '<div class="rel"><span class="lb">関連</span>' +
      rel.map(r => refHTML(r, "ref")).join("") + "</div>" : "";

  return '<article class="com' + (outOfTerm ? " out" : "") + '" id="' + esc(e.id) + '">' +
    "<h2>" + esc(e.title) + "</h2>" +
    (meta ? '<div class="meta">' + meta + "</div>" : "") +
    '<div class="refs">' + res.refs.filter(Boolean).map(r => refHTML(r, "ref")).join("") + "</div>" +
    (e.purpose ? '<div class="pur"><span class="lb">趣旨</span><div>' + paras(e.purpose) + "</div></div>" : "") +
    (e.structure ? '<div class="pur"><span class="lb">構成</span><div>' + paras(e.structure) + "</div></div>" : "") +
    treeHTML(e.tree, true) +
    rules +
    (e.thesis ? '<div class="thesis"><span class="lb">総合</span><div>' + paras(e.thesis) + "</div></div>" : "") +
    listHTML("pts", "論点", e.points) +
    related + historyHTML(res.history) +
    (e.body ? '<div class="body">' + paras(e.body) + "</div>" : "") + "</article>";
}

/* 沿革は差分から導く。書き手が改正履歴を書き写す必要はないし、
   書き写せば条文と食い違う余地が生まれる。 */
const KIND_JA = {text: "文言", number: "採番", parent: "係り先", added: "追加", removed: "削除"};

async function historyOf(e) {
  const base = (e.refs || [])[0];
  const ys = S.years;
  if (!base || ys.length < 2) return [];
  const out = [];
  for (let k = 0; k + 1 < ys.length; k++) {
    await ensureChain(ys[k], ys[k + 1]);
    const d = (S.diffCache || {})[ys[k] + "-" + ys[k + 1]];
    if (!d) continue;
    const oi = resolveAcrossYears(base, ys[k], ys, S.chain);
    const ni = resolveAcrossYears(base, ys[k + 1], ys, S.chain);
    // removed は旧年度のID、added は新年度のIDしか持たない
    const under = (id, pre) => !!(id && pre && (id === pre || id.startsWith(pre)));
    const hits = d.entries.filter(x =>
      under(x.status === "removed" ? null : x.id, ni) ||
      under(x.status === "added" ? null : (x.old_id || x.id), oi));
    if (!hits.length) continue;
    const c = {};
    for (const x of hits) {
      for (const k2 of (x.changes.length ? x.changes : [x.status])) c[k2] = (c[k2] || 0) + 1;
    }
    out.push({from: ys[k], to: ys[k + 1], counts: c});
  }
  return out;
}

function historyHTML(h) {
  if (!h.length) return "";
  const rows = h.map(x => '<span class="hv"><b>' + esc(x.from) + "→" + esc(x.to) + "</b>" +
    Object.entries(x.counts).map(([k, n]) => (KIND_JA[k] || k) + n).join("・") + "</span>").join("");
  return '<div class="hist"><span class="lb">沿革</span><div>' + rows + "</div></div>";
}

/* 解説1件の参照をまとめて解決する。条そのもの・各要件が指す項・関連条文 */
async function resolveEntry(e) {
  return {
    refs: await resolveAll(e.refs),
    rules: await resolveAll((e.rules || []).map(r => r.ref)),
    related: await resolveAll(e.related),
    history: await historyOf(e),
  };
}

function match(e) {
  const q = S.q.trim().toLowerCase();
  if (!shown(e)) return false;
  if (S.tag && !(e.tags || []).includes(S.tag)) return false;
  if (!q) return true;
  const hay = [e.title, e.purpose, e.structure, e.thesis, e.body, (e.tags || []).join(" "),
    e.refs.map(r => r.id).join(" "),
    (e.rules || []).map(r => [r.head, (r.elements || []).join(" "), r.effect,
      (r.exceptions || []).join(" "), r.note, r.ref && r.ref.id].join(" ")).join(" "),
  ].join(" ").toLowerCase();
  return hay.includes(q);
}

async function render() {
  const list = S.com.entries.filter(match);
  const parts = [];
  for (const e of list) parts.push(entryHTML(e, await resolveEntry(e)));
  if (!list.length) parts.push("<p>該当する解説がありません。</p>");
  $("#doc").innerHTML = parts.join("");
  await linkSources();
}

/* 根拠に挙げた条文IDを、表示中の年度へ読み替えてリンクにする */
async function linkSources() {
  for (const el of $("#doc").querySelectorAll(".src[data-at]")) {
    const ids = el.dataset.at.split(",").map(x => x.trim()).filter(Boolean);
    if (!ids.length) continue;
    const parts = [];
    for (const id of ids) {
      const r = await resolve1({year: WRITTEN_YEAR, id});
      if (r.id && r.node) parts.push('<a href="index.html#' + encodeURIComponent(r.id) + '">' +
        esc(r.node.cite || r.id) + "</a>");
    }
    if (!parts.length) continue;
    const at = document.createElement("span");
    at.className = "sat";
    at.innerHTML = parts.join("・");
    el.after(at);          // 印の中に入れると折り返せず、狭い画面ではみ出す
    el.removeAttribute("data-at");
  }
}

function buildNav() {
  const list = S.com.entries.filter(shown);
  const past = S.com.entries.filter(e => !inTerm(e)).length;
  const tags = new Map();
  for (const e of list) for (const t of (e.tags || [])) tags.set(t, (tags.get(t) || 0) + 1);
  let h = "";
  for (const [kind, label] of [[undefined, "条文"], ["term", "用語"]]) {
    const g = list.filter(e => (e.kind || undefined) === kind);
    if (!g.length) continue;
    h += '<div class="navch">' + label + "</div>";
    for (const e of g) {
      h += '<button class="navit' + (inTerm(e) ? "" : " dim") + '" data-jump="' + esc(e.id) + '">' +
        '<span class="t">' + esc(e.title) + "</span></button>";
    }
  }
  if (past) {
    h += '<button class="navit' + (S.past ? " on" : "") + '" data-past>' +
      '<span class="t">' + (S.past ? esc(S.year) + "年のものだけ" : "期間外も表示") +
      '</span><span class="badge b-chg">' + past + "</span></button>";
  }
  h += '<div class="navch">分類</div>';
  h += '<button class="navit' + (S.tag ? "" : " on") + '" data-tag=""><span class="t">すべて</span></button>';
  for (const [t, n] of tags) {
    h += '<button class="navit' + (S.tag === t ? " on" : "") + '" data-tag="' + esc(t) + '">' +
      '<span class="t">' + esc(t) + '</span><span class="badge b-chg">' + n + "</span></button>";
  }
  $("#nav").innerHTML = h;
}

/* ===== 操作 ===== */
document.addEventListener("click", async e => {
  const j = e.target.closest("[data-jump]");
  if (j) {
    document.getElementById(j.dataset.jump)?.scrollIntoView({block: "start"});
    document.body.classList.remove("nav"); return;
  }
  if (e.target.closest("[data-past]")) { S.past = !S.past; buildNav(); await render(); return; }
  const t = e.target.closest("[data-tag]");
  if (t) { S.tag = t.dataset.tag || null; buildNav(); await render(); return; }
  if (e.target.closest("[data-go-rules]")) { location.href = "index.html"; return; }
});
/* 年度が変われば、どれが効いているかも変わる。目次から作り直す */
$("#yearsel").addEventListener("change", async e => {
  S.year = e.target.value; buildNav(); await render();
});
let tmr;
$("#q").addEventListener("input", () => {
  $("#qclear").style.display = $("#q").value ? "block" : "none";
  clearTimeout(tmr); tmr = setTimeout(async () => { S.q = $("#q").value; await render(); }, 120);
});
$("#qclear").onclick = async () => { $("#q").value = ""; S.q = ""; $("#qclear").style.display = "none"; await render(); };
$("#burger").onclick = () => {
  const on = !document.body.classList.contains("nav");
  document.body.classList.toggle("nav", on);
  $("#burger").textContent = on ? "✕" : "☰";
};
$("#scrim").onclick = () => { document.body.classList.remove("nav"); $("#burger").textContent = "☰"; };
$("#bnew").onclick = () => alert(
  "解説の作成画面はこれから作ります。\n\n" +
  "いまは commentary.json を直接編集してください。\n" +
  "参照は {\"year\":\"2026\",\"id\":\"5.02\"} のように、書いた時点の年度とIDで書きます。");
/* ===== 起動 ===== */
(async function boot() {
  try {
    S.manifest = await getJSON("manifest.json");
    S.com = await getJSON("commentary.json");
    S.years = S.manifest.years.map(x => x.year);
    S.year = S.manifest.latest;
    $("#yearsel").innerHTML = S.years
      .map(y => '<option' + (y === S.year ? " selected" : "") + ">" + y + "</option>").join("");
    // 期間外の解説を名指しで開いた場合は、隠したままにしない
    const hash = decodeURIComponent(location.hash.slice(1));
    const target = S.com.entries.find(e => e.id === hash);
    if (target && !inTerm(target)) S.past = true;
    buildNav();
    await render();
    $("#msg").hidden = true;
    $("#app").hidden = false;
    if (hash) document.getElementById(hash)?.scrollIntoView({block: "start"});
  } catch (e) {
    $("#msg").innerHTML = "<div><p><b>読み込めませんでした</b></p>" +
      "<p style='color:var(--fg3)'>" + esc(e.message) + "</p>" +
      "<p>このフォルダで <code>make serve</code> を実行し、" +
      "<code>http://localhost:8000/commentary.html</code> を開いてください。</p></div>";
  }
})();
