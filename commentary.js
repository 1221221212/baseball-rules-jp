"use strict";
/* コンメンタール野球規則。
   条文とは独立した読み物だが、参照は年度をまたいで条文に解決される（refs.js）。 */
const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

const S = {manifest: null, com: null, years: [], year: null, cache: {}, chain: null, q: "", tag: null};

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

async function resolveAll(entry) {
  const out = [];
  for (const r of entry.refs) {
    await ensureChain(r.year, S.year);
    const id = resolveAcrossYears(r, S.year, S.years, S.chain);
    const n = id && (await loadYear(S.year)).byId.get(id);
    out.push({ref: r, id, node: n || null});
  }
  return out;
}

/* ===== 描画 ===== */
const TERM = v => {
  if (!v || (!v.from && !v.to)) return "";
  return (v.from || "") + "〜" + (v.to || "現行");
};

function entryHTML(e, refs) {
  const outOfTerm = !isValid(e.valid, S.year);
  const term = TERM(e.valid);
  const meta = [
    term ? '<span class="term' + (outOfTerm ? " out" : "") + '">' + esc(term) +
      (outOfTerm ? "・" + esc(S.year) + "年は期間外" : "") + "</span>" : "",
    ...(e.tags || []).map(t => '<span class="tag">' + esc(t) + "</span>"),
  ].filter(Boolean).join("");

  const refHTML = refs.map(({ref, id, node}) => {
    if (!id || !node) {
      return '<span class="ref gone"><b>' + esc(ref.id) + "</b>" +
        '<span class="t">' + esc(ref.year) + "年時点・" + esc(S.year) + "年には無い</span></span>";
    }
    const moved = id !== ref.id ? '<span class="t">' + esc(ref.year) + "年は " + esc(ref.id) + "</span>" : "";
    return '<a class="ref" href="index.html#' + encodeURIComponent(id) + '">' +
      "<b>" + esc(node.cite || id) + "</b>" +
      '<span class="t">' + esc(node.title || "") + "</span>" + moved + "</a>";
  }).join("");

  const body = (e.body || "").split("\n").filter(x => x.trim())
    .map(p => "<p>" + esc(p) + "</p>").join("");

  return '<article class="com" id="' + esc(e.id) + '">' +
    "<h2>" + esc(e.title) + "</h2>" +
    (meta ? '<div class="meta">' + meta + "</div>" : "") +
    '<div class="refs">' + refHTML + "</div>" +
    '<div class="body">' + body + "</div>" + "</article>";
}

function match(e) {
  const q = S.q.trim().toLowerCase();
  if (S.tag && !(e.tags || []).includes(S.tag)) return false;
  if (!q) return true;
  return (e.title + " " + (e.body || "") + " " + (e.tags || []).join(" ") +
          " " + e.refs.map(r => r.id).join(" ")).toLowerCase().includes(q);
}

async function render() {
  const list = S.com.entries.filter(match);
  const parts = ['<div class="lead">条文への参照は書いた年度のまま保存され、' +
    '表示中の年度（' + esc(S.year) + '）に読み替えて示します。採番が変わっても書き直す必要はありません。</div>'];
  for (const e of list) parts.push(entryHTML(e, await resolveAll(e)));
  if (!list.length) parts.push("<p>該当する解説がありません。</p>");
  $("#doc").innerHTML = parts.join("");
}

function buildNav() {
  const tags = new Map();
  for (const e of S.com.entries) for (const t of (e.tags || [])) tags.set(t, (tags.get(t) || 0) + 1);
  let h = '<div class="navch">解説</div>';
  for (const e of S.com.entries) {
    h += '<button class="navit" data-jump="' + esc(e.id) + '">' +
      '<span class="t">' + esc(e.title) + "</span></button>";
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
  const t = e.target.closest("[data-tag]");
  if (t) { S.tag = t.dataset.tag || null; buildNav(); await render(); return; }
  if (e.target.closest("[data-go-rules]")) { location.href = "index.html"; return; }
});
$("#yearsel").addEventListener("change", async e => { S.year = e.target.value; await render(); });
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
const THEME_LABEL = {"": "◐ 自動", dark: "● ダーク", light: "○ ライト"};
function applyTheme(v) {
  if (v) document.documentElement.setAttribute("data-theme", v);
  else document.documentElement.removeAttribute("data-theme");
  localStorage.setItem("obr.theme", v);
  $("#btheme").textContent = THEME_LABEL[v];
}
$("#btheme").onclick = () => {
  const cur = document.documentElement.getAttribute("data-theme") || "";
  applyTheme(cur === "" ? "dark" : cur === "dark" ? "light" : "");
};
$("#bnew").onclick = () => alert(
  "解説の作成画面はこれから作ります。\n\n" +
  "いまは commentary.json を直接編集してください。\n" +
  "参照は {\"year\":\"2026\",\"id\":\"5.02\"} のように、書いた時点の年度とIDで書きます。");
$("#bexport").onclick = () => {
  const b = new Blob([JSON.stringify(S.com, null, 1)], {type: "application/json"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(b); a.download = "commentary.json"; a.click();
  URL.revokeObjectURL(a.href);
};

/* ===== 起動 ===== */
(async function boot() {
  applyTheme(localStorage.getItem("obr.theme") || "");
  try {
    S.manifest = await getJSON("manifest.json");
    S.com = await getJSON("commentary.json");
    S.years = S.manifest.years.map(x => x.year);
    S.year = S.manifest.latest;
    $("#yearsel").innerHTML = S.years
      .map(y => '<option' + (y === S.year ? " selected" : "") + ">" + y + "</option>").join("");
    document.title = S.com.title || "コンメンタール";
    $("#brand h1").textContent = S.com.title || "コンメンタール";
    buildNav();
    await render();
    $("#msg").hidden = true;
    $("#app").hidden = false;
    const hash = decodeURIComponent(location.hash.slice(1));
    if (hash) document.getElementById(hash)?.scrollIntoView({block: "start"});
  } catch (e) {
    $("#msg").innerHTML = "<div><p><b>読み込めませんでした</b></p>" +
      "<p style='color:var(--fg3)'>" + esc(e.message) + "</p>" +
      "<p>このフォルダで <code>make serve</code> を実行し、" +
      "<code>http://localhost:8000/commentary.html</code> を開いてください。</p></div>";
  }
})();
