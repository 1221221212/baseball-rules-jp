/* 年度間の差分。DOMには触れない純粋な処理なので、ブラウザからも Node からも使える。
   ここが「何を差分とみなすか」の唯一の定義。検査（build/check.py）もこれを使う。 */
const EDIT_MARKS = /《[新改削訂]》/g;
const tableText = n => n.table
  ? "\n" + [n.table.head].concat(n.table.rows).map(r => r.join("\t")).join("\n") : "";
const canon = n => ((n.title || "") + "\n" + (n.text || []).join("\n") + tableText(n))
  .replace(EDIT_MARKS, "").replace(/[\s\u3000]+/g, "");

function longestCommon(a, b) {
  let best = [0, 0, 0];
  let prev = new Int32Array(b.length + 1), cur = new Int32Array(b.length + 1);
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      cur[j] = a[i - 1] === b[j - 1] ? prev[j - 1] + 1 : 0;
      if (cur[j] > best[2]) best = [i - cur[j], j - cur[j], cur[j]];
    }
    [prev, cur] = [cur, prev];
    cur.fill(0);
  }
  return best;
}

function inlineOps(a, b) {
  const out = [];
  (function rec(a, b, depth) {
    if (!a.length && !b.length) return;
    if (!a.length) { out.push(["insert", b]); return; }
    if (!b.length) { out.push(["delete", a]); return; }
    let s = 0;
    while (s < a.length && s < b.length && a[s] === b[s]) s++;
    let e = 0;
    while (e < a.length - s && e < b.length - s && a[a.length - 1 - e] === b[b.length - 1 - e]) e++;
    if (s) out.push(["equal", a.slice(0, s)]);
    const ma = a.slice(s, a.length - e), mb = b.slice(s, b.length - e);
    if (ma.length && mb.length) {
      // 中間が長すぎるときは分割をあきらめて丸ごと置換（計算量を抑える）
      if (depth > 6 || ma.length * mb.length > 250000) {
        out.push(["delete", ma], ["insert", mb]);
      } else {
        const [i, j, n] = longestCommon(ma, mb);
        if (n < 3) out.push(["delete", ma], ["insert", mb]);
        else {
          rec(ma.slice(0, i), mb.slice(0, j), depth + 1);
          out.push(["equal", ma.slice(i, i + n)]);
          rec(ma.slice(i + n), mb.slice(j + n), depth + 1);
        }
      }
    } else if (ma.length) out.push(["delete", ma]);
    else if (mb.length) out.push(["insert", mb]);
    if (e) out.push(["equal", a.slice(a.length - e)]);
  })(a, b, 0);
  // 連続する同種を畳む
  const m = [];
  for (const [t, v] of out) {
    if (m.length && m[m.length - 1][0] === t) m[m.length - 1][1] += v;
    else m.push([t, v]);
  }
  return m.filter(x => x[1].length);
}

function similarity(a, b) {
  if (!a.length && !b.length) return 1;
  let n = 0;
  const ops = inlineOps(a.slice(0, 400), b.slice(0, 400));
  for (const [t, v] of ops) if (t === "equal") n += v.length;
  return (2 * n) / (Math.min(a.length, 400) + Math.min(b.length, 400) || 1);
}

const bodyOf = n => ((n.title || "") + "\n" + (n.text || []).join("\n") + tableText(n)).trim();

function diffYears(YA, YB) {
  const A = YA.byId, B = YB.byId;
  const fromY = YA.doc.edition, toY = YB.doc.edition;

  /* 条文の同一性は (ID・親・本文) の3つで見分けられる。改正はこのうち1つか2つを変える。
     そこで「2つが保たれている」ことを手がかりに対応づけ、残りを追加・削除とする。

       手がかり        変わったもの     導かれる差分
       親 ＋ 本文      ID              採番のずれ
       ID              本文 / 親        文言変更 / 係り先変更
       親 ＋ 似た本文   ID ＋ 本文       採番のずれ＋文言変更
       本文            ID ＋ 親         係り先変更

     3つとも変わったものは追加＋削除と区別できない。原理的にそうなる。 */
  const pairs = new Map(), doneA = new Set(), doneB = new Set();
  const SEP = "\u0000";
  // 親も対応づけ済みなら新年度側のIDに読み替える（親ごと採番替えされた場合）
  const mappedParent = n => pairs.get(n.parent) ?? n.parent;

  const KEY = {
    親と本文: (n, isOld) => (isOld ? mappedParent(n) : n.parent) + SEP + n.level + SEP + canon(n),
    ID: n => n.id,
    本文: n => n.level + SEP + canon(n),
  };

  /** 手がかりが一致する組を結ぶ。結んだ数を返す */
  function matchBy(keyOf) {
    const index = new Map();
    for (const n of YB.nodes) {
      if (doneB.has(n.id)) continue;
      const k = keyOf(n, false);
      if (!index.has(k)) index.set(k, []);
      index.get(k).push(n);
    }
    let found = 0;
    for (const n of YA.nodes) {
      if (doneA.has(n.id)) continue;
      const bucket = index.get(keyOf(n, true));
      const b = bucket && bucket.find(x => !doneB.has(x.id));
      if (!b) continue;
      pairs.set(n.id, b.id); doneA.add(n.id); doneB.add(b.id); found++;
    }
    return found;
  }

  /** 親が同じで本文が十分似ている組を結ぶ（ID と本文が同時に変わった場合） */
  function matchBySimilarity() {
    const rest = YB.nodes.filter(n => !doneB.has(n.id));
    for (const a of YA.nodes) {
      if (doneA.has(a.id)) continue;
      let best = null, score = 0.60;
      for (const b of rest) {
        if (doneB.has(b.id) || b.level !== a.level || b.parent !== mappedParent(a)) continue;
        const r = similarity(canon(a), canon(b));
        if (r > score) { best = b; score = r; }
      }
      if (best) { pairs.set(a.id, best.id); doneA.add(a.id); doneB.add(best.id); }
    }
  }

  // 手がかりの強い順に試す。親の対応が増えるたびに配下も結べるので、
  // 「親＋本文」は新しい対応が出なくなるまで繰り返す
  while (matchBy(KEY.親と本文)) {}
  matchBy(KEY.ID);
  matchBySimilarity();
  matchBy(KEY.本文);

  /* 対応づけができれば、4種の差分はそこから機械的に導ける */
  const entries = [];
  for (const [ka, kb] of pairs) {
    const a = A.get(ka), b = B.get(kb);
    const changes = [];
    if (canon(a) !== canon(b)) changes.push("text");
    if (ka !== kb) changes.push("number");
    if (mappedParent(a) !== b.parent) changes.push("parent");
    if (!changes.length) continue;
    // 変化は同時に起こりうるので、代表を1つ選ばず全部持つ
    const e = {id: kb, status: "modified", changes};
    if (ka !== kb) e.old_id = ka;
    if (changes.includes("parent")) e.reparent = {from: a.parent, to: b.parent};
    entries.push(e);
  }
  for (const n of YA.nodes) if (!doneA.has(n.id)) entries.push({id: n.id, status: "removed", changes: []});
  for (const n of YB.nodes) if (!doneB.has(n.id)) entries.push({id: n.id, status: "added", changes: []});

  const summary = {added: 0, removed: 0, text: 0, number: 0, parent: 0};
  for (const e of entries) {
    if (e.status !== "modified") summary[e.status]++;
    for (const c of e.changes) summary[c]++;
  }

  for (const e of entries) {
    const src = A.get(e.old_id || e.id), dst = B.get(e.id);
    const ref = dst || src;
    e.cite = ref.cite || ref.id;
    e.level = ref.level;
    e.before = src ? bodyOf(src) : "";
    e.after = dst ? bodyOf(dst) : "";
    if (e.changes.includes("text")) e.ops = inlineOps(e.before, e.after);
  }

  const d = {from: fromY, to: toY, summary, entries, pairs: [...pairs]};

  return d;
}

if (typeof module !== "undefined") module.exports = {diffYears, canon, inlineOps, similarity, bodyOf};
