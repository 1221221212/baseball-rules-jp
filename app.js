"use strict";
const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

/* ===== 状態 ===== */
const S = {
  manifest: null,
  year: null,
  cache: {},          // year -> {nodes, byId, byCite, kids, sections, sectionOf, chapters}
  diffs: {},          // "2025-2026" -> data
  changedIn: {},      // year -> Set(id)  その年に改正のあった条項
  mode: "read",
  section: null,
  onlyChanged: true,      // 差分モードは既定で改正箇所のみ
  uni: null,              // 差分の表示。null=画面幅で自動、true=インライン、false=並べて
};
const isNarrow = () => window.innerWidth < 820;
const WHOLE = new Set(["y", "s"]);   // 章まるごと表示する（用語の定義・一般指示）

/* ===== 読み込み ===== */
async function getJSON(path) {
  const r = await fetch(path, {cache: "no-cache"});
  if (!r.ok) throw new Error(path + " が読めません (" + r.status + ")");
  return r.json();
}

function indexYear(doc) {
  const nodes = [], kids = new Map(), byId = new Map(), byCite = new Map();
  function walk(n, parent) {
    n.parent = parent;
    nodes.push(n);
    byId.set(n.id, n);
    for (const a of (n.cite_ids || [])) if (!byCite.has(a)) byCite.set(a, n);
    if (!kids.has(parent)) kids.set(parent, []);
    kids.get(parent).push(n);
    for (const c of (n.children || [])) walk(c, n.id);
  }
  for (const ch of doc.chapters) walk(ch, null);

  const chapters = doc.chapters;
  const sections = [];
  for (const c of chapters) {
    if (WHOLE.has(c.id)) sections.push(c);
    else for (const s of (kids.get(c.id) || [])) sections.push(s);
  }
  const sectionOf = new Map();
  const mark = (n, sec) => { sectionOf.set(n.id, sec); for (const k of (kids.get(n.id) || [])) mark(k, sec); };
  for (const s of sections) mark(s, s.id);
  for (const c of chapters) if (!sectionOf.has(c.id)) sectionOf.set(c.id, c.id);
  return {doc, nodes, byId, byCite, kids, chapters, sections, sectionOf};
}

async function loadYear(y) {
  if (S.cache[y]) return S.cache[y];
  const info = S.manifest.years.find(x => x.year === y);
  S.cache[y] = indexYear(await getJSON(info.path));
  return S.cache[y];
}

/* 差分の計算は diff.js（DOMに触れない純粋な処理）にある。
   年度がN個あると組み合わせは N(N-1)/2 通りになるので事前計算はせず、
   選ばれた2年をその場で突き合わせる。1,300ノードで数msで終わる。 */
async function computeDiff(fromY, toY) {
  const key = fromY + "-" + toY;
  if (!S.diffs[key]) {
    S.diffs[key] = diffYears(await loadYear(fromY), await loadYear(toY));
  }
  return S.diffs[key];
}

const Y = () => S.cache[S.year];

/* ===== 注釈 ===== */
const LS = "obr.annotations";
let fileAnn = [], localAnn = [];
try { localAnn = JSON.parse(localStorage.getItem(LS) || "[]"); } catch (e) { localAnn = []; }
const TYPE_JA = {amendment: "改正", interpretation: "解釈", case: "事例", memo: "メモ"};
const allAnn = () => fileAnn.concat(localAnn);
const annFor = id => allAnn().filter(a => (a.target || []).includes(id));
const saveLocal = () => localStorage.setItem(LS, JSON.stringify(localAnn));

/* ===== 描画（条文） ===== */
// 参照の書き方は2通りある: 圧縮形 5.06b3 と 展開形 5.06（b）（3）
const REF_RE = /(?<![0-9.])([0-9]{1,2}\.[0-9]{2})((?:（[0-9a-zA-Z]{1,3}）)+|[a-z][0-9]{0,2})?(?![0-9])/g;

function resolveRef(id) {
  const y = Y();
  if (y.byId.has(id)) return id;
  if (y.byCite.has(id)) return y.byCite.get(id).id;
  // 英字の大小が原文で揺れている（6.01（G）など）
  const m = id.match(/^([0-9]+\.[0-9]{2})(.*)$/);
  if (m) {
    for (const v of [m[2].toLowerCase(), m[2].toUpperCase()]) {
      const c = m[1] + v;
      if (y.byId.has(c)) return c;
      if (y.byCite.has(c)) return y.byCite.get(c).id;
    }
  }
  return null;
}

function linkRefs(h) {
  return h.replace(REF_RE, (whole, rule, rest) => {
    const parts = rest ? (rest.startsWith("（")
      ? [...rest.matchAll(/（([0-9a-zA-Z]{1,3})）/g)].map(x => x[1])
      : [rest]) : [];
    const target = resolveRef(rule + parts.join(""));
    return target ? '<a class="xref" data-go="' + target + '">' + whole + "</a>" : whole;
  });
}

/* tail は本文の最後の段落の中に差し込む。右側に場所を確保すると本文が
   早く折り返し、上に浮かせるとホバー時に文字を覆ってしまうため */
function para(text, tail) {
  const arr = (Array.isArray(text) ? text : (text ? [text] : [])).filter(Boolean);
  if (!arr.length) return tail ? "<p>" + tail + "</p>" : "";
  return arr.map((p, i) => "<p>" + linkRefs(esc(p)) +
    (tail && i === arr.length - 1 ? tail : "") + "</p>").join("");
}
const noteCls = k => "k-" + String(k || "").replace(/[0-9A-Z]+$/, "");

function annHTML(id) {
  const list = annFor(id);
  if (!list.length) return "";
  return list.map(a => {
    const meta = [TYPE_JA[a.type] || a.type, a.effective ? a.effective + "年" : "", a.source || ""]
      .filter(Boolean).join(" ・ ");
    const mine = localAnn.includes(a);
    const others = (a.target || []).filter(t => t !== id);
    const also = others.length
      ? '<span class="meta">他: ' + others.map(t =>
          '<a class="xref" data-go="' + esc(t) + '">' + esc((Y().byId.get(t) || {}).cite || t) + "</a>"
        ).join("、") + "</span>"
      : "";
    return '<div class="amd"><div class="ah">' + esc(a.title || "（無題）") +
      '<span class="meta">' + esc(meta) + "</span>" + also + "</div>" +
      (a.body ? '<div class="body">' + para(a.body.split("\n")) + "</div>" : "") +
      (mine ? '<div class="acts"><button data-edit="' + esc(a.id) + '">編集</button>' +
              '<button data-del="' + esc(a.id) + '">削除</button></div>' : "") + "</div>";
  }).join("");
}

function renderNode(n) {
  const chg = S.changedIn[S.year] && S.changedIn[S.year].has(n.id) ? " chg" : "";
  if (n.level === "note") {
    return '<div class="note node ' + noteCls(n.kind) + chg + '" id="' + esc(n.id) + '">' +
      '<div class="nh">' + esc(n.label || "") + "</div>" +
      '<div class="body">' + para(headText(n)) + "</div>" + annHTML(n.id) + renderKids(n) + "</div>";
  }
  if (n.level === "term") {
    return '<div class="term node' + chg + '" id="' + esc(n.id) + '">' +
      '<h3><span class="n">' + esc(n.label || "") + "</span><span>" + esc(n.title || "") + "</span>" +
      "</h3>" +
      '<div class="body">' + para(headText(n)) + "</div>" + annHTML(n.id) + "</div>";
  }
  const head = '<div class="head">' +
    (n.label ? '<span class="lbl">' + esc(n.label) + "</span>" : "") +
    '<div class="body">' +
      (n.title ? '<span class="ttl">' + esc(n.title) + "</span>" + (n.text ? "　" : "") : "") +
      para(headText(n)) + "</div></div>";
  return '<div class="node ' + n.level + chg + '" id="' + esc(n.id) + '">' + head +
    annHTML(n.id) + renderKids(n) + "</div>";
}
// 本文の途中に注記が挟まることがある（3.01のボールを汚す禁止など）。
// 子ノードが持つ pos（親の本文を何段落読んだ時点で現れるか）で本文と交互に並べる。
function headText(n) {
  const ks = Y().kids.get(n.id) || [];
  const txt = n.text || [];
  const lim = ks.length ? (ks[0].pos || 0) : (n.table ? n.table.pos : txt.length);
  return txt.slice(0, lim);
}

function tableHTML(t) {
  if (!t) return "";
  const th = "<tr>" + t.head.map(c => "<th>" + esc(c) + "</th>").join("") + "</tr>";
  const tr = t.rows.map(r => "<tr>" + r.map(c => "<td>" + esc(c) + "</td>").join("") + "</tr>").join("");
  return '<div class="tw"><table>' + th + tr + "</table></div>";
}

// indent=false のときは字下げしない。字下げは「一段上のノードに係る」という意味を
// 持たせているので、条の直下（＝条そのものに係る）では付けない。
/* 狭い画面では左右に並べず、1本の流れに削除と追加を織り込む（unified表示）。
   GitHub なども狭い画面では split を無効にして unified にしている。
   同じ文を2回読まされないぶん、縦に積むより読みやすい。 */
function unifiedCell(a, b, ops, status) {
  const n = b || a;
  const lead = n.level === "note" ? '<span class="kd">' + esc(n.label || "") + "</span>"
    : n.label ? '<span class="lb">' + esc(n.label) + "</span>"
    : (n.level === "rule" || n.level === "chapter") ? '<span class="lb">' + esc(n.id) + "</span>" : "";
  let body;
  if (ops) {
    body = ops.map(([t, v]) => t === "equal" ? esc(v)
      : t === "delete" ? "<del>" + esc(v) + "</del>" : "<ins>" + esc(v) + "</ins>").join("");
  } else if (status === "added") {
    body = "<ins>" + esc(bodyOf(b)) + "</ins>";
  } else if (status === "removed") {
    body = "<del>" + esc(bodyOf(a)) + "</del>";
  } else {
    body = esc(bodyOf(n));
  }
  return '<div class="cell u">' + lead + body + "</div>";
}

function renderKids(n, indent = true) {
  const ks = Y().kids.get(n.id) || [];
  const tb = n.table;
  if (!ks.length) return tb ? tableHTML(tb) : "";
  const txt = n.text || [];
  let ti = ks[0].pos || 0, out = "", buf = [];
  const flush = () => {
    if (!buf.length) return;
    out += indent ? '<div class="kids">' + buf.join("") + "</div>" : buf.join("");
    buf = [];
  };
  for (const k of ks) {
    const p = k.pos || 0;
    if (p > ti) { flush(); out += '<div class="body cont">' + para(txt.slice(ti, p)) + "</div>"; ti = p; }
    buf.push(renderNode(k));
  }
  flush();
  if (ti < txt.length) out += '<div class="body cont">' + para(txt.slice(ti)) + "</div>";
  return out + (tb ? tableHTML(tb) : "");
}

/* 条文は全部つなげて1ページに出す。章・条の切れ目で区切り、
   サイドバーは今どこを読んでいるかをスクロールに追従して示す。 */
function renderAll() {
  const y = Y();
  if (y.html == null) {
    const parts = [];
    for (const ch of y.chapters) {
      parts.push('<h1 class="chap" id="ch-' + esc(ch.id) + '">' +
        (ch.label ? '<span class="num">' + esc(ch.label) + "</span>" : "") +
        "<span>" + esc(ch.title || "") + "</span></h1>");
      const list = WHOLE.has(ch.id) ? [ch] : (y.kids.get(ch.id) || []);
      for (const sec of list) parts.push(sectionHTML(sec, y));
    }
    y.html = parts.join("");
  }
  $("#doc").innerHTML = y.html;
  show("doc");
  observeSections();
}

function sectionHTML(s, y) {
  const head = s.level === "chapter"
    ? '<h2 class="rule">' + esc(s.title || "") + "</h2>"
    : '<h2 class="rule"><span class="num">' + esc(s.id) + "</span><span>" +
      esc(s.title || "") + "</span></h2>";
  return '<section class="sect" data-sec="' + esc(s.id) + '">' + head +
    '<div class="body">' + para(headText(s)) + "</div>" +
    annHTML(s.id) + renderKids(s, false) + "</section>";
}

/* サイドバーの現在位置。画面上端に一番近い条を選ぶ */
let secObserver = null;
function observeSections() {
  if (secObserver) secObserver.disconnect();
  const seen = new Map();
  secObserver = new IntersectionObserver(entries => {
    for (const e of entries) seen.set(e.target.dataset.sec, e);
    let best = null;
    for (const [, e] of seen) {
      if (!e.isIntersecting) continue;
      if (!best || e.boundingClientRect.top < best.boundingClientRect.top) best = e;
    }
    if (best) highlightNav(best.target.dataset.sec);
  }, {root: $("#main"), rootMargin: "-8% 0px -80% 0px", threshold: 0});
  document.querySelectorAll(".sect").forEach(el => secObserver.observe(el));
}

function highlightNav(id) {
  if (S.section === id) return;
  S.section = id;
  document.querySelectorAll(".navit").forEach(b => b.classList.toggle("on", b.dataset.sec === id));
  const on = document.querySelector(".navit.on");
  if (on) on.scrollIntoView({block: "nearest"});
}

function scrollToSection(id) {
  const el = document.querySelector('.sect[data-sec="' + CSS.escape(id) + '"]');
  if (el) { el.scrollIntoView({block: "start"}); highlightNav(id); }
}

function show(which) {
  for (const k of ["doc", "results", "diffview"]) $("#" + k).hidden = (k !== which);
}

/* ===== 目次 ===== */
function buildNav() {
  const y = Y();
  const chg = S.changedIn[S.year] || new Set();
  const annSet = new Set(allAnn().flatMap(a => a.target || []));
  let h = "";
  for (const c of y.chapters) {
    h += '<div class="navch">' + esc((c.label ? c.label + "　" : "") + (c.title || "")) + "</div>";
    for (const s of (WHOLE.has(c.id) ? [c] : (y.kids.get(c.id) || []))) {
      let cnt = 0;
      for (const id of chg) if (y.sectionOf.get(id) === s.id) cnt++;
      const hasAnn = [...annSet].some(id => y.sectionOf.get(id) === s.id);
      // 1.00 の各条のように表題を持たない条は、番号だけを出して表題欄は空にする
      const num = s.level === "chapter" ? "" : s.level === "group" ? (s.label || s.id) : s.id;
      h += '<button class="navit" data-sec="' + esc(s.id) + '">' +
        '<span class="n">' + esc(num) + "</span>" +
        '<span class="t">' + esc(s.title || "") + (hasAnn ? " ✎" : "") + "</span>" +
        (cnt ? '<span class="badge b-chg">' + cnt + "</span>" : "") + "</button>";
    }
  }
  $("#nav").innerHTML = h;
}

/* ===== 検索 ===== */
function search(qs) {
  const q = qs.trim();
  if (!q) { renderAll(); return; }
  const y = Y(), lower = q.toLowerCase(), hits = [];
  const direct = y.byId.get(q) || y.byCite.get(q);
  for (const n of y.nodes) {
    const hay = n.id + " " + (n.cite || "") + " " + (n.label || "") + " " + (n.title || "") +
      " " + (n.text || []).join(" ");
    if (hay.toLowerCase().includes(lower)) hits.push(n);
    if (hits.length > 500) break;
  }
  const re = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "ig");
  let h = '<div class="cnt">「' + esc(q) + "」 " + hits.length + " 件" +
    (direct ? '　<a class="xref" data-go="' + esc(direct.id) + '">' + esc(direct.cite || direct.id) + " を開く</a>" : "") +
    "</div>";
  for (const n of hits) {
    const src = (n.title ? n.title + "　" : "") + (n.text || []).join(" ");
    const at = src.toLowerCase().indexOf(lower);
    const from = Math.max(0, at - 32);
    const sn = (from ? "…" : "") + src.slice(from, from + 145) + (src.length > from + 145 ? "…" : "");
    h += '<button class="hit" data-go="' + esc(n.id) + '"><div class="bc">' + esc(n.breadcrumb || bc(n)) +
      '</div><div class="sn">' + esc(sn).replace(re, m => "<mark>" + m + "</mark>") + "</div></button>";
  }
  $("#results").innerHTML = h;
  show("results");
}
function bc(n) {
  const p = []; let c = n;
  while (c) {
    p.push(((c.level === "rule" || c.level === "chapter") ? c.id + " " : (c.label ? c.label + " " : "")) + (c.title || ""));
    c = c.parent ? Y().byId.get(c.parent) : null;
  }
  return p.reverse().join(" ＞ ").replace(/\s+/g, " ").trim();
}

/* ===== 差分（左右2カラム比較） ===== */
const ST_JA = {added: "追加", removed: "削除"};
const CHANGE_JA = {text: "文言", number: "採番", parent: "係り先"};

function flatten(Yc, rootId) {
  const out = [];
  (function rec(id) {
    const n = Yc.byId.get(id);
    if (!n) return;
    out.push(n);
    for (const k of (Yc.kids.get(id) || [])) rec(k.id);
  })(rootId);
  return out;
}

function cellHTML(n, ops, side, idTag) {
  const y = side === "l" ? S.curDiff.from : S.curDiff.to;
  if (!n) return '<div class="cell ' + side + ' empty" data-y="' + y + '"></div>';
  const chip = idTag ? '<span class="idchip">' + esc(idTag) + "</span>" : "";
  const lead = n.level === "note" ? '<span class="kd">' + esc(n.label || "") + "</span>"
    : n.label ? '<span class="lb">' + esc(n.label) + "</span>"
    : (n.level === "rule" || n.level === "chapter") ? '<span class="lb">' + esc(n.id) + "</span>" : "";
  let bodyTxt;
  if (ops) {
    const want = side === "l" ? "delete" : "insert";
    bodyTxt = ops.map(([t, s]) => t === "equal" ? esc(s)
      : t === want ? (want === "delete" ? "<del>" : "<ins>") + esc(s) + (want === "delete" ? "</del>" : "</ins>")
      : "").join("");
  } else {
    bodyTxt = (n.title ? '<span class="tt">' + esc(n.title) + "</span>" + (n.text ? "　" : "") : "") +
      esc((n.text || []).join(" ")) + (n.table ? tableHTML(n.table) : "");
  }
  return '<div class="cell ' + side + '" data-y="' + y + '">' + chip + lead + bodyTxt + "</div>";
}

async function renderDiff() {
  const ys = S.manifest.years.map(x => x.year);
  if (ys.length < 2) { $("#diffview").innerHTML = "<p>比較できる年度が1つしかありません。</p>"; show("diffview"); return; }
  const cur = S.curDiff || {from: ys[ys.length - 2], to: ys[ys.length - 1]};
  S.curDiff = cur;
  $("#diffview").innerHTML = '<p style="color:var(--fg3)">' + cur.from + " と " + cur.to + " を比較中…</p>";
  show("diffview");
  if (S.uni === null) S.uni = isNarrow();
  const d = await computeDiff(cur.from, cur.to);
  const [YA, YB] = [await loadYear(cur.from), await loadYear(cur.to)];

  const byNew = new Map(), byOld = new Map();
  for (const e of d.entries) {
    if (e.status === "removed") byOld.set(e.id, e);            // idは旧年度のもの
    else if (e.status === "added") byNew.set(e.id, e);
    else { byNew.set(e.id, e); byOld.set(e.old_id || e.id, e); }
  }
  const pairAB = new Map(d.pairs), pairBA = new Map(d.pairs.map(([a, b]) => [b, a]));

  const yearOpts = y => S.manifest.years
    .map(x => '<option' + (x.year === y ? " selected" : "") + ">" + x.year + "</option>").join("");
  const n = d.summary;
  let h = '<div id="diffbar">' +
    '<div class="opts">' +
      '<label><input type="checkbox" id="onlychg"' + (S.onlyChanged ? " checked" : "") +
        ">改正箇所のみ表示</label>" +
      '<span class="seg"><button data-uni="0"' + (S.uni ? "" : ' class="on"') + ">並べて</button>" +
      '<button data-uni="1"' + (S.uni ? ' class="on"' : "") + ">インライン</button></span>" +
      '<span class="stat">' +
        '<span class="s-add">追加 <b>' + n.added + "</b></span>" +
        '<span class="s-chg">文言 <b>' + n.text + "</b></span>" +
        '<span class="s-ren">採番 <b>' + n.number + "</b></span>" +
        '<span class="s-rep">係り先 <b>' + n.parent + "</b></span>" +
        '<span class="s-del">削除 <b>' + n.removed + "</b></span>" +
      "</span></div>" +
    '<div class="yrs' + (S.uni ? " uni" : "") + '"><div><select id="dfrom">' + yearOpts(cur.from) +
    "</select></div>" +
    '<div><select id="dto">' + yearOpts(cur.to) + "</select></div></div></div>";

  // 表示対象の条（改正のみ表示なら、変更のある条だけ）
  const secIds = [];
  for (const s of YB.sections) {
    if (!S.onlyChanged) { secIds.push(s.id); continue; }
    const hit = d.entries.some(e =>
      YB.sectionOf.get(e.id) === s.id || YA.sectionOf.get(e.old_id || e.id) === s.id);
    if (hit) secIds.push(s.id);
  }
  // 旧年にしか無い条も拾う
  for (const s of YA.sections) {
    if (!YB.byId.has(s.id) && !secIds.includes(s.id)) secIds.push(s.id);
  }

  for (const sid of secIds) h += compareSection(sid, YA, YB, d, byNew, byOld, pairAB, pairBA);
  if (!secIds.length) h += "<p>この年度間に改正はありません。</p>";
  $("#diffview").innerHTML = h;
  show("diffview");
  if (S.section) {
    const el = document.getElementById("cmp-" + S.section);
    if (el) el.scrollIntoView({block: "start"});
  }
}

function compareSection(sid, YA, YB, d, byNew, byOld, pairAB, pairBA) {
  const listA = YA.byId.has(sid) ? flatten(YA, sid) : [];
  const listB = YB.byId.has(sid) ? flatten(YB, sid) : [];

  // 新年度の並び順を骨格にし、旧年度にしか無いノードを元の位置へ差し込む。
  // （対応表があるので順序をなぞる必要がなく、ズレない）
  const rows = [], posOfA = new Map();
  for (const b of listB) {
    const aid = pairBA.get(b.id);
    const a = aid ? YA.byId.get(aid) : null;
    rows.push([a, b]);
    if (a) posOfA.set(a.id, rows.length - 1);
  }
  const inserts = new Map();
  let last = -1;
  for (const a of listA) {
    if (pairAB.has(a.id) && posOfA.has(a.id)) { last = posOfA.get(a.id); continue; }
    if (!inserts.has(last)) inserts.set(last, []);
    inserts.get(last).push(a);
  }
  const merged = [];
  for (const a of (inserts.get(-1) || [])) merged.push([a, null]);
  rows.forEach((r, i) => {
    merged.push(r);
    for (const a of (inserts.get(i) || [])) merged.push([a, null]);
  });

  const out = [];
  let changed = 0;
  for (const [a, b] of merged) {
    const e = b ? byNew.get(b.id) : byOld.get(a.id);
    let status = "same";
    if (!a) status = "added";
    else if (!b) status = "removed";
    else if (e) status = e.status;
    if (status !== "same") changed++;
    if (S.onlyChanged && status === "same") continue;
    const ops = (e && e.ops) ? e.ops : null;
    const ref = b || a;
    const badges = e && e.changes && e.changes.length
      ? e.changes.map(c => '<span class="st st-' + c + '">' + CHANGE_JA[c] + "</span>").join("")
      : '<span class="st st-' + status + '">' + (ST_JA[status] || status) + "</span>";
    const tag = status === "same" ? "" :
      '<div class="rowtag">' + badges +
      '<span class="cite-l" data-go="' + esc(ref.id) + '">' + esc((e && e.cite) || ref.cite || ref.id) + "</span>" +
      (e && e.reparent
        ? '<span class="ofc">係り先 ' + esc(e.reparent.from || "—") + " → " + esc(e.reparent.to || "—") + "</span>"
        : "") + "</div>";
    const renamed = !!(e && e.old_id);
    out.push('<div class="row r-' + status + '">' + tag +
      (S.uni
        ? unifiedCell(a, b, ops, status)
        : cellHTML(a, ops, "l", renamed && a ? a.id : "") +
          cellHTML(b, ops, "r", renamed && b ? b.id : "")) + "</div>");
  }
  if (!out.length) return "";
  const s = YB.byId.get(sid) || YA.byId.get(sid);
  return '<div class="secttl" id="cmp-' + esc(sid) + '">' +
    (s.level === "chapter" ? "" : '<span class="num">' + esc(sid) + "</span>") +
    "<span>" + esc(s.title || "") + "</span>" +
    (changed ? '<span class="cnt">改正 ' + changed + "</span>" : "") + "</div>" +
    '<div class="cols' + (S.uni ? " uni" : "") + '">' + out.join("") + "</div>";
}

/* ===== 遷移 ===== */
function go(id) {
  const y = Y();
  const n = y.byId.get(id) || y.byCite.get(id);
  if (!n) return;
  setMode("read");
  $("#q").value = ""; $("#qclear").style.display = "none";
  history.replaceState(null, "", "#" + n.id);
  const el = document.getElementById(n.id);
  if (el) {
    // 中央寄せだと画面上端が前の条に残り、サイドバーが1つ手前を指してしまう
    el.scrollIntoView({block: "start"});
    el.classList.add("flash");
    setTimeout(() => el.classList.remove("flash"), 1500);
  } else $("#main").scrollTop = 0;
  highlightNav(y.sectionOf.get(n.id) || n.id);
  toggleNav(false);
}

function setMode(m) {
  S.mode = m;
  document.querySelectorAll("#modes button").forEach(b => b.classList.toggle("on", b.dataset.mode === m));
  if (m === "diff") renderDiff();
  else renderAll();
}

/* ===== 注釈ダイアログ ===== */
let editing = null;
let dlgTargets = [];      // 注釈の対象。複数の条文にまたがることがある

function chipHTML(id) {
  const n = Y().byId.get(id);
  const label = n ? (n.cite || n.id) : id;
  let title = n ? (n.title || (n.text || []).join("")) : "";
  if (title.length > 14) title = title.slice(0, 14) + "…";
  return '<span class="chip2"><b>' + esc(label) + "</b>" + (title ? esc(title) : "") +
    '<button type="button" data-drop="' + esc(id) + '">✕</button></span>';
}
function renderChips() {
  $("#chips").innerHTML = dlgTargets.map(chipHTML).join("");
}
function addTarget(id) {
  if (!dlgTargets.includes(id)) dlgTargets.push(id);
  renderChips();
  $("#f_pick").value = "";
  $("#picklist").hidden = true;
}
function searchTargets(q) {
  const list = $("#picklist");
  const s = q.trim().toLowerCase();
  if (!s) { list.hidden = true; return; }
  const y = Y();
  const hits = [];
  for (const n of y.nodes) {
    if (dlgTargets.includes(n.id)) continue;
    const hay = (n.id + " " + (n.cite || "") + " " + (n.title || "") + " " +
                 (n.text || []).join(" ")).toLowerCase();
    if (hay.includes(s)) hits.push(n);
    if (hits.length >= 12) break;
  }
  list.innerHTML = hits.length
    ? hits.map(n => '<button type="button" data-pick="' + esc(n.id) + '">' +
        '<span class="id">' + esc(n.cite || n.id) + "</span>" +
        esc((n.title || (n.text || []).join("")).slice(0, 40)) + "</button>").join("")
    : '<button type="button" disabled style="color:var(--fg3)">該当なし</button>';
  list.hidden = false;
}

function openDlg(ex) {
  editing = ex || null;
  dlgTargets = ex ? (ex.target || []).slice() : (S.section ? [S.section] : []);
  $("#dlgtitle").textContent = ex ? "注釈を編集" : "注釈を作成";
  renderChips();
  $("#f_pick").value = "";
  $("#picklist").hidden = true;
  $("#f_type").value = (ex && ex.type) || "amendment";
  $("#f_effective").value = (ex && ex.effective) || "";
  $("#f_title").value = (ex && ex.title) || "";
  $("#f_body").value = (ex && ex.body) || "";
  $("#f_source").value = (ex && ex.source) || "";
  $("#dlg").showModal();
  setTimeout(() => $("#f_title").focus(), 30);
}

$("#dlg").addEventListener("close", () => {
  if ($("#dlg").returnValue !== "save") return;
  if (!dlgTargets.length) { alert("対象の条文を1つ以上選んでください。"); return; }
  const rec = {
    id: (editing && editing.id) || "loc-" + Date.now().toString(36),
    target: dlgTargets.slice(), type: $("#f_type").value,
    effective: $("#f_effective").value.trim(), title: $("#f_title").value.trim(),
    body: $("#f_body").value.trim(), source: $("#f_source").value.trim(),
    year: S.year, created: (editing && editing.created) || new Date().toISOString().slice(0, 10),
  };
  if (editing) localAnn[localAnn.indexOf(editing)] = rec; else localAnn.push(rec);
  saveLocal(); Y().html = null; buildNav(); renderAll();
});

$("#f_pick").addEventListener("input", e => searchTargets(e.target.value));
$("#pick").addEventListener("click", e => {
  const pick = e.target.closest("[data-pick]");
  if (pick) { addTarget(pick.dataset.pick); return; }
  const drop = e.target.closest("[data-drop]");
  if (drop) { dlgTargets = dlgTargets.filter(x => x !== drop.dataset.drop); renderChips(); }
});
$("#bnew").onclick = () => openDlg(null);

/* ===== イベント ===== */
document.addEventListener("click", async e => {
  const g = e.target.closest("[data-go]");
  if (g) { e.preventDefault(); go(g.dataset.go); return; }
  const s = e.target.closest(".navit");
  if (s) {
    toggleNav(false);
    if (S.mode === "diff") {
      const el = document.getElementById("cmp-" + s.dataset.sec);
      if (el) el.scrollIntoView({block: "start"});
      else { S.onlyChanged = false; renderDiff(); }
    } else { renderAll(); scrollToSection(s.dataset.sec); }
    return;
  }
  const m = e.target.closest("#modes button");
  if (m) { setMode(m.dataset.mode); return; }
  const u = e.target.closest("[data-uni]");
  if (u) { S.uni = u.dataset.uni === "1"; renderDiff(); return; }
  const ed = e.target.closest("[data-edit]");
  if (ed) { openDlg(localAnn.find(a => a.id === ed.dataset.edit)); return; }
  const del = e.target.closest("[data-del]");
  if (del) {
    if (!confirm("この注釈を削除しますか？")) return;
    localAnn = localAnn.filter(a => a.id !== del.dataset.del);
    saveLocal(); Y().html = null; buildNav(); renderAll(); return;
  }
});
$("#diffview").addEventListener("change", e => {
  if (e.target.id === "onlychg") { S.onlyChanged = e.target.checked; renderDiff(); return; }
  if (e.target.id !== "dfrom" && e.target.id !== "dto") return;
  let f = $("#dfrom").value, t = $("#dto").value;
  if (f === t) { alert("違う年度を選んでください。"); renderDiff(); return; }
  if (f > t) [f, t] = [t, f];
  S.curDiff = {from: f, to: t};
  renderDiff();
});
$("#yearsel").addEventListener("change", async e => {
  S.year = e.target.value;
  await loadYear(S.year);
  await computeChanged();
  buildNav();
  const keep = S.section;
  if (S.mode === "read") { renderAll(); if (keep) scrollToSection(keep); }
  else renderDiff();
});
/* ドロワーの開閉。開いている間はバーガーを閉じるボタンにし、
   背後のスクリムをタップしても閉じられるようにする */
function toggleNav(open) {
  const on = open === undefined ? !document.body.classList.contains("nav") : open;
  document.body.classList.toggle("nav", on);
  $("#burger").textContent = on ? "✕" : "☰";
  $("#burger").setAttribute("aria-label", on ? "目次を閉じる" : "目次");
}
$("#burger").onclick = () => toggleNav();
$("#scrim").onclick = () => toggleNav(false);
let tmr;
$("#q").addEventListener("input", () => {
  $("#qclear").style.display = $("#q").value ? "block" : "none";
  clearTimeout(tmr); tmr = setTimeout(() => search($("#q").value), 110);
});
$("#qclear").onclick = () => { $("#q").value = ""; $("#qclear").style.display = "none"; search(""); $("#q").focus(); };
/* 「/」で検索へ。入力中の欄からは奪わない */
const inField = el => el && (/^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName) || el.isContentEditable);
document.addEventListener("keydown", e => {
  if (e.key === "/" && !inField(document.activeElement)) {
    e.preventDefault(); $("#q").focus(); $("#q").select();
  }
  if (e.key === "Escape" && document.activeElement === $("#q")) { $("#q").value = ""; search(""); $("#q").blur(); }
});
/* 既定はOSの設定に従う。ボタンで 自動 → ダーク → ライト と切り替えられる。
   今どれなのかが分からないと困るので、ボタン自身に状態を出す */
const THEME_LABEL = {"": "◐ 自動", dark: "● ダーク", light: "○ ライト"};
function applyTheme(v) {
  if (v) document.documentElement.setAttribute("data-theme", v);
  else document.documentElement.removeAttribute("data-theme");
  localStorage.setItem("obr.theme", v);
  const b = $("#btheme");
  if (b) {
    b.textContent = THEME_LABEL[v];
    b.title = v ? "表示: " + THEME_LABEL[v].slice(2) : "表示: OSの設定に従う";
  }
}
$("#btheme").onclick = () => {
  const cur = document.documentElement.getAttribute("data-theme") || "";
  applyTheme(cur === "" ? "dark" : cur === "dark" ? "light" : "");
};
$("#bexport").onclick = () => {
  const out = {version: 1, updated: new Date().toISOString().slice(0, 10), annotations: allAnn()};
  const b = new Blob([JSON.stringify(out, null, 1)], {type: "application/json"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(b); a.download = "annotations.json"; a.click();
  URL.revokeObjectURL(a.href);
};
$("#bimport").onclick = () => $("#fileinput").click();
$("#fileinput").onchange = () => {
  const f = $("#fileinput").files[0]; if (!f) return;
  const r = new FileReader();
  r.onload = () => {
    try {
      const inc = (JSON.parse(r.result).annotations) || [];
      const known = new Set(allAnn().map(a => a.id));
      let k = 0;
      for (const a of inc) if (!known.has(a.id)) { localAnn.push(a); k++; }
      saveLocal(); Y().html = null; buildNav(); renderAll();
      alert(k + " 件を読み込みました。");
    } catch (err) { alert("読み込めませんでした: " + err.message); }
  };
  r.readAsText(f); $("#fileinput").value = "";
};

/* ===== その年に改正のあった条項 ===== */
async function computeChanged() {
  if (S.changedIn[S.year]) return;
  const ys = S.manifest.years.map(x => x.year);
  const i = ys.indexOf(S.year);
  const set = new Set();
  if (i > 0) {
    const d = await computeDiff(ys[i - 1], S.year);
    for (const e of d.entries) if (e.status !== "removed") set.add(e.id);
  }
  S.changedIn[S.year] = set;
}

/* ===== 起動 ===== */
(async function boot() {
  applyTheme(localStorage.getItem("obr.theme") || "");
  try {
    S.manifest = await getJSON("manifest.json");
    try { fileAnn = (await getJSON(S.manifest.annotations)).annotations || []; } catch (e) { fileAnn = []; }
    S.year = S.manifest.latest;
    $("#yearsel").innerHTML = S.manifest.years
      .map(x => '<option' + (x.year === S.year ? " selected" : "") + ">" + x.year + "</option>").join("");
    await loadYear(S.year);
    await computeChanged();
    buildNav();
    $("#msg").hidden = true;
    $("#app").hidden = false;
    const hash = decodeURIComponent(location.hash.slice(1));
    renderAll();
    if (hash && (Y().byId.has(hash) || Y().byCite.has(hash))) go(hash);
  } catch (e) {
    $("#msg").innerHTML = "<div><p><b>データを読み込めませんでした</b></p>" +
      "<p style='color:var(--fg3)'>" + esc(e.message) + "</p>" +
      "<p>このページはデータを外部ファイルから読み込みます。<br>" +
      "ブラウザの制約で <code>file://</code> では動きません。<br><br>" +
      "このフォルダで<br><code>python3 -m http.server 8000</code><br>を実行し、<br>" +
      "<code>http://localhost:8000/</code> を開いてください。</p></div>";
  }
})();
