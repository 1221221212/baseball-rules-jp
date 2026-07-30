#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Markdown → 構造化データ（JSON / JSONL / SQLite）

    python3 2_md2data.py 2025 2026     # 年度を並べて指定。省略時は years/ 配下すべて

入力: years/<年>/text/*.md
出力: years/<年>/data/rules.json  rules.jsonl  rules.sqlite
"""
import re, json, os, sqlite3, sys, unicodedata, collections

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
DIR = OUT = ""     # main() で年度ごとに差し替える

FILES = [
    ("01-試合の目的.md",                    "1"),
    ("02-競技場.md",                        "2"),
    ("03-用具・ユニフォーム.md",             "3"),
    ("04-試合の準備.md",                    "4"),
    ("05-試合の進行.md",                    "5"),
    ("06-反則行為.md",                      "6"),
    ("07-試合の終了.md",                    "7"),
    ("08-補則_ボールデッドの際の走者の帰塁.md", "h"),
    ("09-審判員.md",                        "8"),
    ("10-審判員に対する一般指示.md",          "s"),
    ("12-記録に関する規則.md",               "9"),
    ("13-本規則における用語の定義.md",        "y"),
]

LEVEL_JA = {"chapter": "章", "rule": "条", "item": "項", "clause": "号",
            "subclause": "細目", "note": "注記", "term": "用語",
            "paragraph": "段落", "group": "区分"}
LEVEL_RANK = {"chapter": 0, "group": 1, "rule": 1, "item": 2, "clause": 3, "subclause": 4}

NOTE_KINDS = ["軟式注", "原注", "規則説明", "付記", "例外", "例題", "解答",
              "ペナルティ", "問", "答", "注"]

ROMAN_S = ["i","ii","iii","iv","v","vi","vii","viii","ix","x"]
ROMAN_L = ["I","II","III","IV","V","VI","VII","VIII","IX","X"]


def han(s):
    """全角英数字・記号を半角に"""
    return unicodedata.normalize("NFKC", s)


# 相互参照: 5.09 / 5.09b / 5.09b3 （寸法の 76.199 等は除外）
REF = re.compile(
    r"(?<![0-9.＝=×÷])([0-9]{1,2})\.([0-9]{2})(?![0-9])"
    r"([a-z])?([0-9]{1,2})?(?![0-9])"
    r"(?!\s*(メートル|センチ|ミリ|インチ|フィート|キロ|グラム|オンス|ポンド|ヤード|℃))")


# 展開形の参照: 6.02（c）（2）～（6） / 5.06（b）（3）（c） / 6.02（d）
EXPANDED = re.compile(
    r"([0-9]{1,2}\.[0-9]{2})((?:（[0-9a-zA-Z]{1,3}）)+)"
    r"(?:[～〜]（([0-9]{1,2})）)?")


def find_expanded(text):
    """「6.02（c）（2）～（6）」のような書き方をIDに展開する。
    範囲（～）は端から端まで並べる。"""
    out = []
    for m in EXPANDED.finditer(text):
        parts = re.findall(r"（([0-9a-zA-Z]{1,3})）", m.group(2))
        base = m.group(1) + "".join(parts)
        if m.group(3) and parts and parts[-1].isdigit():
            head = m.group(1) + "".join(parts[:-1])
            a, b = int(parts[-1]), int(m.group(3))
            if a <= b <= a + 30:
                for i in range(a, b + 1):
                    out.append(head + str(i))
                continue
        out.append(base)
    return out


def resolve_ref(r, ids):
    """英字の大小が原文で揺れている（6.01（G）など）ので、実在するIDに寄せる"""
    if r in ids:
        return r
    for cand in (r.lower(), r.upper(),
                 re.sub(r"[A-Za-z](?=[0-9]*$)", lambda m: m.group(0).swapcase(), r)):
        if cand in ids:
            return cand
    m = re.match(r"^([0-9]+\.[0-9]{2})(.*)$", r)
    if m:
        for swap in (m.group(2).lower(), m.group(2).upper()):
            if m.group(1) + swap in ids:
                return m.group(1) + swap
    return r


def find_refs(text):
    out = []
    for m in REF.finditer(text):
        r = han(m.group(1)) + "." + han(m.group(2))
        if m.group(3):
            r += han(m.group(3))
        if m.group(4):
            r += han(m.group(4))
        if r.endswith(".00"):
            r = r[:-3]
        # 旧表記 2.40 等は「用語の定義」への参照（2.00は現行では競技場=2.01〜2.05）
        m2 = re.fullmatch(r"2\.([0-9]{2})", r)
        if m2 and int(m2.group(1)) > 5:
            r = "y" + str(int(m2.group(1)))
        if r not in out:
            out.append(r)
    for r in find_expanded(text):
        if r not in out:
            out.append(r)
    return out


MARKER = re.compile(r"^[（(]([^）)]{1,4})[）)][　 ]*")


def marker_level(tok, chap_key="", rule_id=None, seen=(), prev=None):
    """マーカー文字列 → (level, key)。i/v/x はローマ数字と英字が衝突するので文脈で判定"""
    t = tok.strip()
    # 直前のマーカーがローマ数字で、これがその次なら細目（5.04の(iv)(v)(vi)など）
    if t in ROMAN_S and prev in ROMAN_S and ROMAN_S.index(prev) == ROMAN_S.index(t) - 1:
        return "subclause", t
    if chap_key == "h" and t in ROMAN_L:          # 補則は（I）（II）（III）が最上位区分
        return "group", t
    if re.fullmatch(r"[0-9]{1,2}", t):
        return "clause", t
    if re.fullmatch(r"[a-z]", t):
        # （i）: 同じ条に（h）があれば項の連番、なければローマ数字の細目
        if t == "i" and rule_id and (rule_id + "h") not in seen:
            return "subclause", "i"
        return "item", t
    if re.fullmatch(r"[A-Z]", t):
        return "subclause", t
    if t in ROMAN_S:
        return "subclause", t
    if t in ROMAN_L:
        return "subclause", t
    return None, None


NOTE_RE = re.compile(r"^【([^】]{1,14})】[　 ]*")
BOLD_NOTE_RE = re.compile(r"^(?:\*\*)?(ペナルティ|規則説明|付記|例外)(?:\*\*)?[　 ]")


def parse_note_label(inner):
    """【5.06b3付記】→ ('付記', '', '5.06b3') / 【注１】→ ('注','１','')"""
    for k in NOTE_KINDS:
        i = inner.rfind(k)
        if i < 0:
            continue
        target = inner[:i]
        rest = inner[i + len(k):]
        if re.fullmatch(r"[0-9A-Z]*", rest):
            return k, han(rest), target
    return inner, "", ""


class Node:
    _seq = collections.Counter()

    def __init__(self, level, nid, label="", title="", parent=None):
        self.level, self.id, self.label, self.title = level, nid, label, title
        self.text, self.children, self.refs = [], [], []
        self.parent = parent
        self.extra = {}
        self.cite = ""
        self.cite_ids = []
        self.pos = 0

    def add(self, child):
        # 本文の途中に注記が挟まることがある（3.01など）。並び順を保つために
        # 「親の本文を何段落読んだ時点で現れたか」を覚えておく
        child.pos = len(self.text)
        self.children.append(child)
        child.parent = self
        return child

    def breadcrumb(self):
        parts, n = [], self
        while n is not None and n.level != "document":
            head = (n.id if n.level in ("rule", "chapter") else n.label) or n.id
            if n.title:
                head = f"{head} {n.title}"
            parts.append(head.strip())
            n = n.parent
        return " ＞ ".join(reversed(parts))

    def to_dict(self):
        d = {"id": self.id, "level": self.level, "level_ja": LEVEL_JA.get(self.level, self.level)}
        if self.cite:
            d["cite"] = self.cite
            d["cite_ids"] = self.cite_ids
        if self.label:
            d["label"] = self.label
        if self.title:
            d["title"] = self.title
        d.update(self.extra)
        if self.pos:
            d["pos"] = self.pos
        if self.text:
            d["text"] = self.text
        if self.refs:
            d["refs"] = self.refs
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        return d


RULE_RE = re.compile(r"^([0-9]+\.[0-9]{2})(.*)$")
TOK_RE = re.compile(r"i+|I+|[a-z]|[A-Z]|[0-9]+")


def path_tokens(nid):
    """5.06b3E → ('5.06', ['b','3','E']) / 5.02iii → ('5.02', ['iii'])"""
    m = RULE_RE.match(nid.split("#")[0])
    if not m:
        return None, []
    return m.group(1), TOK_RE.findall(m.group(2))


def build_cite(node):
    """公式改正文書の引用形式と、その別名（エイリアス）を作る。

    公式は注記を指すとき引用の深さが揺れる（5.10(l)【原注】 / 9.22【注】 / 4.03(e)【注】）。
    そこで注記には条・項・号…と段階的に浅くしたIDを全部エイリアスとして持たせ、
    どの深さで書かれていても引けるようにする。曖昧になるエイリアスは後段で捨てる。
    """
    if node.level != "note":
        rule, toks = path_tokens(node.id)
        if not rule:
            return node.id, [node.id]
        disp = rule + "".join(f"（{t}）" for t in toks)
        return disp, [node.id.split("#")[0]]

    host = (node.extra.get("attached_to") or "").split("#")[0]
    kind = node.extra.get("kind", "注")
    no = node.extra.get("no", "")
    suffix = f"-{kind}{no}"
    rule, toks = path_tokens(host)
    if not rule:
        return host + suffix, [host + suffix]
    disp = rule + "".join(f"（{t}）" for t in toks) + f"【{kind}{no}】"
    aliases = [rule + "".join(toks[:k]) + suffix for k in range(len(toks), -1, -1)]
    return disp, aliases


def uniq(nid, seen):
    if nid not in seen:
        seen.add(nid)
        return nid
    i = 2
    while f"{nid}#{i}" in seen:
        i += 1
    seen.add(f"{nid}#{i}")
    return f"{nid}#{i}"


def parse_file(path, chap_key, seen):
    lines = open(os.path.join(DIR, path), encoding="utf-8").read().split("\n")
    chapter = None
    stack = {}          # level -> Node
    cur = None          # 直近に生成したノード（本文の追記先）
    last_note = {}      # kind -> Node（【ペナルティ原注】等の解決用）
    note_quoted = False
    note_stack = {}     # 引用の深さ -> その深さの直近の注記
    nodes_by_id = {}    # ラベルで名指しされた係り先を引くため
    prev_marker = [None]  # 直前のマーカー。ローマ数字の連番判定に使う
    term_no = 0

    struct = [None]      # 直近の構造ノード（条・項・号・細目）。本文の帰属先

    def anchor():
        """現在の 条 or 章 の ID"""
        return stack.get("rule").id if "rule" in stack else chapter.id

    def place(level, key, label, title="", roman=False):
        nonlocal cur
        base = stack.get("rule") or stack.get("group") or chapter
        if roman and "clause" not in stack:
            for lv in ("item", "clause", "subclause"):
                stack.pop(lv, None)
        for lv in ("subclause", "clause", "item", "group"):
            if LEVEL_RANK[lv] < LEVEL_RANK[level] and lv in stack:
                base = stack[lv]
                break
        nid = uniq(base.id + ("" if base.level in ("rule", "group") else "") + key, seen)
        n = base.add(Node(level, nid, label, title))
        for lv, r in LEVEL_RANK.items():
            if r >= LEVEL_RANK[level] and lv in stack:
                del stack[lv]
        stack[level] = n
        cur = struct[0] = n
        nodes_by_id[n.id] = n
        note_stack.clear()
        return n

    for raw in lines:
        s = raw.rstrip()
        if not s.strip():
            continue

        # ---- 見出し ----
        if s.startswith("# "):
            t = s[2:].strip()
            m = re.match(r"^([0-9]+)\.([0-9]+)[　 ]*(.*)$", t)
            if m:
                chapter = Node("chapter", han(m.group(1)), f"{han(m.group(1))}.00", m.group(3).strip())
            else:
                chapter = Node("chapter", chap_key, "", re.sub(r"[　 ]+", "", t))
            seen.add(chapter.id)
            nodes_by_id[chapter.id] = chapter
            stack, cur = {}, chapter
            struct[0] = chapter
            continue

        if s.startswith("## ") or s.startswith("### "):
            t = s.lstrip("#").strip()
            m = re.match(r"^([0-9]+)\.([0-9]+)[　 ]*(.*)$", t)
            if m and chap_key != "y":                      # 条
                nid = uniq(f"{han(m.group(1))}.{han(m.group(2))}", seen)
                n = chapter.add(Node("rule", nid, "", m.group(3).strip()))
                stack = {"rule": n}
                cur = struct[0] = n
                nodes_by_id[n.id] = n
                note_stack.clear()
                continue
            if chap_key == "y":                            # 用語
                term_no += 1
                mm = re.match(r"^([0-9]+)[　 ]+(.*)$", t)
                no = han(mm.group(1)) if mm else str(term_no)
                n = chapter.add(Node("term", uniq(f"y{no}", seen), no, (mm.group(2) if mm else t).strip()))
                stack, cur = {}, n
                struct[0] = n
                note_stack.clear()
                continue
            mk = MARKER.match(t)                           # 項/号 見出し
            if mk:
                lv, key = marker_level(mk.group(1), chap_key,
                                       stack.get("rule").id if "rule" in stack else None, seen,
                                       prev_marker[0])
                if lv:
                    prev_marker[0] = key
                    place(lv, key, f"（{mk.group(1)}）", MARKER.sub("", t).strip(),
                          roman=(key in ROMAN_S))
                    continue
            n = (stack.get("rule") or chapter).add(Node("paragraph", uniq(anchor() + "-p", seen), "", t.strip()))
            cur = struct[0] = n
            continue

        # ---- 本文行 ----
        # 元サイトは <ul> のクラスで本文と注記を書き分けている。取り込み時にそれを
        # 「> 」の引用行として持ち込んでいるので、ここで境界として使う。
        # これが無いと、注記のあとに再開する本文（3.01「ボールを故意に汚す」など）が
        # 注記の続きとして取り込まれてしまう。
        # 「> 」の深さで注記の係り先を変える。1段なら直近の構造ノード、
        # 2段以上なら直前の注記にぶら下げる（3.01【注2】がペナルティに係る等）
        raw = s.lstrip()
        depth = 0
        while raw.startswith("> "):
            depth += 1
            raw = raw[2:].lstrip()
        quoted = depth > 0
        body = (raw if quoted else s).lstrip("　 ")

        # Markdownの表（3.01のボール規格）。全角スペースの桁合わせでは揃わないため
        if body.startswith("|"):
            cells = [c.strip() for c in body.strip().strip("|").split("|")]
            host = cur if cur is not None else (struct[0] or chapter)
            if re.fullmatch(r"[-:| ]+", body):
                continue                                   # 区切り行は読み飛ばす
            tb = host.extra.get("table")
            if tb is None:
                tb = {"pos": len(host.text), "head": cells, "rows": []}
                host.extra["table"] = tb
            else:
                tb["rows"].append(cells)
            continue

        nm = NOTE_RE.match(body) or BOLD_NOTE_RE.match(body)
        if nm:
            inner = nm.group(1)
            bold = not body.startswith("【")
            if bold:
                kind, no, target = inner, "", ""
            else:
                kind, no, target = parse_note_label(inner)
            # 引用の深さ = 係り先の階層。同じ深さの注記どうしは兄弟。
            # （【注1】【注2】【注3】が数珠つなぎに入れ子にならないようにする）
            # ペナルティのように引用の外に置かれる注記もあるので、最低でも深さ1とみなす
            nd = max(depth, 1)
            host = note_stack.get(nd - 1) or struct[0] or chapter
            nid = uniq(f"{host.id}-{kind}{no}", seen)
            n = host.add(Node("note", nid, inner if bold else f"【{inner}】"))
            n.level = "note"
            n.extra["kind"] = kind
            if no:
                n.extra["no"] = no
            n.extra["attached_to"] = host.id
            nodes_by_id[n.id] = n
            # 係り先の解決
            tgt, scope = [], "inferred"
            if target:
                t2 = han(target).strip("・･ 　")
                if re.fullmatch(r"[0-9]+\.[0-9]{2}[a-z]?[0-9]*", t2):
                    tgt, scope = [t2], "explicit"
                elif t2 in NOTE_KINDS and t2 in last_note:
                    tgt, scope = [last_note[t2].id], "explicit"
                elif re.fullmatch(r"[A-Z]{2,}", t2):        # BCDE原注 → 同じ親の細目B〜E
                    base = host.parent if host.level == "note" or host.parent is None else host.parent
                    base = host.parent if host.parent is not None else stack.get("rule")
                    if base is not None:
                        tgt, scope = [base.id + c for c in t2], "explicit"
                elif re.fullmatch(r"[a-z0-9・･]+", t2):
                    r = stack.get("rule")
                    if r:
                        tgt = [r.id + x for x in re.split(r"[・･]", t2) if x]
                        scope = "explicit"
            # ラベルが係り先を1つだけ名指ししているなら、ツリーの位置もそこに合わせる
            # （【4.03原注】は4.03に、【3.02注】は3.02に）。字下げだけで係り先が分かる
            if scope == "explicit" and len(tgt) == 1 and tgt[0] in nodes_by_id:
                real = nodes_by_id[tgt[0]]
                if real is not n:
                    host.children.remove(n)
                    seen.discard(n.id)
                    del nodes_by_id[n.id]
                    real.add(n)
                    n.id = uniq(f"{real.id}-{kind}{no}", seen)
                    nodes_by_id[n.id] = n
                    note_stack[nd] = n
                    host = real
                    n.extra["attached_to"] = real.id
            n.extra["scope"] = scope
            n.extra["scope_target"] = tgt if tgt else [host.id]
            n.text.append((BOLD_NOTE_RE.sub("", body) if bold
                           else NOTE_RE.sub("", body)).strip())
            last_note[kind] = n
            note_stack[nd] = n
            for k in [k for k in note_stack if k > nd]:
                del note_stack[k]
            cur = n
            note_quoted = quoted
            continue

        mk = MARKER.match(body)
        if mk and chap_key != "y":
            lv, key = marker_level(mk.group(1), chap_key,
                                   stack.get("rule").id if "rule" in stack else None, seen,
                                   prev_marker[0])
            if lv:
                prev_marker[0] = key
                n = place(lv, key, f"（{mk.group(1)}）", roman=(key in ROMAN_S))
                n.text.append(MARKER.sub("", body).strip())
                continue

        bm = re.match(r"^\*\*([0-9]+\.[0-9]+)\*\*[　 ]*(.*)$", body)   # 1.01 形式
        if bm:
            nid = uniq(han(bm.group(1)), seen)
            n = chapter.add(Node("rule", nid, "", ""))
            n.text.append(bm.group(2).strip())
            stack = {"rule": n}
            cur = struct[0] = n
            continue

        # 引用行なら注記の続き。引用でない行は、引用ブロックの注記を打ち切って本文に戻る
        if quoted:
            target = cur if (cur is not None and cur.level == "note") else (struct[0] or chapter)
        elif cur is not None and cur.level == "note" and not note_quoted:
            target = cur                                   # 引用外の注記（ペナルティ等）の続き
        else:
            target = struct[0] or cur or chapter
        if target is chapter and chap_key == "s":          # 一般指示は独立段落
            n = chapter.add(Node("paragraph", uniq(f"s{len(chapter.children)+1}", seen), ""))
            n.text.append(body.strip())
            continue
        target.text.append(body.strip())

    return chapter


def collect(node, out):
    node.refs = find_refs(" ".join(node.text) + " " + (node.title or ""))
    node.cite, node.cite_ids = build_cite(node)
    out.append(node)
    for c in node.children:
        collect(c, out)


def build_year(year):
    global DIR, OUT
    DIR = os.path.join(ROOT, "years", year, "text")
    OUT = os.path.join(ROOT, "years", year, "data")
    os.makedirs(OUT, exist_ok=True)

    seen = set()
    root = Node("document", f"rules{year}", "", f"公認野球規則 {year} Official Baseball Rules")
    for fn, key in FILES:
        root.add(parse_file(fn, key, seen))

    flat = []
    for ch in root.children:
        collect(ch, flat)

    # 全ノードが揃ってから参照を実在IDへ寄せる（大小の揺れを吸収）
    ids = {n.id for n in flat} | {a for n in flat for a in n.cite_ids}
    for n in flat:
        n.refs = list(dict.fromkeys(resolve_ref(r, ids) for r in n.refs))

    # エイリアスの重複解消: 2つ以上のノードが同じ別名を主張したらその別名は捨てる
    owner = collections.Counter()
    for n in flat:
        for a in n.cite_ids:
            owner[a] += 1
    for n in flat:
        n.cite_ids = [a for a in n.cite_ids if owner[a] == 1 or a == n.id]

    doc = {
        "title": f"公認野球規則 {year} Official Baseball Rules",
        "edition": year,
        "id_scheme": ("条=5.02 / 項=5.02a / 号=5.02a1 / 細目=5.02a1A / 注記=<親ID>-<種別><番号>。"
                      "cite_id は公式改正文書の引用形式（5.10l-原注 など）"),
        "levels": LEVEL_JA,
        "chapters": [c.to_dict() for c in root.children],
    }
    # ビューアが fetch する本体。コンパクトに出す（人が読むのは text/*.md のほう）
    with open(os.path.join(OUT, "rules.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))

    if "--jsonl" not in sys.argv and "--sqlite" not in sys.argv:
        return summary_line(flat, year, seen)

    with open(os.path.join(OUT, "rules.jsonl"), "w", encoding="utf-8") as f:
        for n in flat:
            rec = {
                "id": n.id, "cite": n.cite, "cite_ids": n.cite_ids,
                "level": n.level, "level_ja": LEVEL_JA.get(n.level, n.level),
                "label": n.label, "title": n.title,
                "breadcrumb": n.breadcrumb(),
                "text": "\n".join(x.strip() for x in n.text),
                "refs": n.refs,
                "parent_id": n.parent.id if n.parent and n.parent.level != "document" else None,
            }
            rec.update({k: v for k, v in n.extra.items()})
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    if "--sqlite" not in sys.argv:
        return summary_line(flat, year, seen)

    db = os.path.join(OUT, "rules.sqlite")
    if os.path.exists(db):
        os.remove(db)
    con = sqlite3.connect(db)
    con.executescript("""
    CREATE TABLE nodes(
      id TEXT PRIMARY KEY, cite TEXT, parent_id TEXT, level TEXT, level_ja TEXT,
      label TEXT, title TEXT, breadcrumb TEXT, text TEXT,
      kind TEXT, no TEXT, attached_to TEXT, scope TEXT, ord INTEGER);
    CREATE TABLE refs(src TEXT, dst TEXT);
    CREATE TABLE note_scope(note_id TEXT, target_id TEXT);
    CREATE VIRTUAL TABLE fts USING fts5(id UNINDEXED, cite, breadcrumb, title, text, tokenize='trigram');
    CREATE INDEX i_parent ON nodes(parent_id);
    CREATE INDEX i_level  ON nodes(level);
    CREATE TABLE cite_alias(alias TEXT, id TEXT);
    CREATE INDEX i_cite   ON cite_alias(alias);
    CREATE INDEX i_refs   ON refs(dst);
    """)
    for i, n in enumerate(flat):
        txt = "\n".join(x.strip() for x in n.text)
        con.execute("INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            n.id, n.cite,
            n.parent.id if n.parent and n.parent.level != "document" else None,
            n.level, LEVEL_JA.get(n.level, n.level), n.label, n.title,
            n.breadcrumb(), txt, n.extra.get("kind"), n.extra.get("no"),
            n.extra.get("attached_to"), n.extra.get("scope"), i))
        con.execute("INSERT INTO fts VALUES(?,?,?,?,?)",
                    (n.id, n.cite, n.breadcrumb(), n.title or "", txt))
        for a in n.cite_ids:
            con.execute("INSERT INTO cite_alias VALUES(?,?)", (a, n.id))
        for r in n.refs:
            con.execute("INSERT INTO refs VALUES(?,?)", (n.id, r))
        for t in n.extra.get("scope_target", []) or []:
            con.execute("INSERT INTO note_scope VALUES(?,?)", (n.id, t))
    con.commit()
    con.close()

    return summary_line(flat, year, seen)


def summary_line(flat, year, seen):
    c = collections.Counter(n.level for n in flat)
    order = ["chapter", "rule", "item", "clause", "subclause", "note", "term", "paragraph", "group"]
    summary = "  ".join(f"{LEVEL_JA[k]}{c[k]}" for k in order if c[k])
    dangling = sorted({r for n in flat for r in n.refs if r not in seen})
    print(f"[{year}] {len(flat)}ノード  {summary}  "
          f"参照{sum(len(n.refs) for n in flat)}件(未解決{len(dangling)})")
    if dangling:
        print("        未解決:", dangling[:10])
    return flat


def write_manifest():
    """ビューアが最初に読む索引。静的配信ではディレクトリ一覧が取れないため、
    どの年度のルール本文があるかだけを示す。それ以外の事前生成データは持たない
    （差分・改正マーカー・検索索引はすべてブラウザ側で本文から計算する）。"""
    yd = os.path.join(ROOT, "years")
    years = sorted(d for d in os.listdir(yd) if d.isdigit())
    man = {
        "title": "公認野球規則",
        "years": [{"year": y, "path": f"years/{y}/data/rules.json"} for y in years],
        "latest": years[-1] if years else None,
        "annotations": "annotations.json",
    }
    with open(os.path.join(ROOT, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    print(f"manifest: 年度 {', '.join(years)}")


def main():
    years = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not years:
        yd = os.path.join(ROOT, "years")
        years = sorted(d for d in os.listdir(yd) if d.isdigit())
    for y in years:
        build_year(y)
    write_manifest()


main()
