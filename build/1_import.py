#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""元HTML → Markdown（年度別）

    python3 1_import.py 2025 [--force]

出力: years/<年>/text/*.md      ← これがマスター。以後は人が直接編集してよい
      build/cache/<年>/*.html   ← 取得した原本（Shift_JIS）。再取得を避けるためのキャッシュ

新しい年度を追加するときだけ実行する。既存年度のMarkdownを勝手に上書きしないよう、
すでに text/ がある場合は --force を付けない限り中断する。

正規化ルールは年度間で必ず同一でなければならない。ここがズレると差分が汚れる。
"""
import html
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
BASE = "http://yokouchibaseballclub.web.fc2.com/rules{y}/"

# (元ページの接尾辞, 出力ファイル名)
PAGES = [
    ("mokuji", "00-目次"),
    ("1", "01-試合の目的"),
    ("2", "02-競技場"),
    ("3", "03-用具・ユニフォーム"),
    ("4", "04-試合の準備"),
    ("5", "05-試合の進行"),
    ("6", "06-反則行為"),
    ("7", "07-試合の終了"),
    ("h", "08-補則_ボールデッドの際の走者の帰塁"),
    ("8", "09-審判員"),
    ("s", "10-審判員に対する一般指示"),
    ("9m", "11-記録に関する規則_目次"),
    ("9", "12-記録に関する規則"),
    ("y", "13-本規則における用語の定義"),
]

# CJK互換文字（㌳など）を読める語に開く
UNIT = {
    "㌅": "インチ", "㌉": "オンス", "㌕": "キログラム", "㌖": "キロメートル",
    "㌘": "グラム", "㌢": "センチ", "㌳": "フィート", "㍍": "メートル",
    "㍉": "ミリ", "㌔": "キロ", "㌍": "カロリー", "㎖": "ml",
}

ROMAN_MAP = {}
for _i, _c in enumerate("ⅰⅱⅲⅳⅴⅵⅶⅷⅸⅹ"):
    ROMAN_MAP[_c] = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"][_i]
for _i, _c in enumerate("ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ"):
    ROMAN_MAP[_c] = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"][_i]

_FW = ("０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
       "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ")
_HW = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_TBL = str.maketrans(_FW + "()", _HW + "（）")


def normalize(s):
    """英数字は半角、括弧は全角、ローマ数字はラテン文字に統一"""
    for k, v in ROMAN_MAP.items():
        s = s.replace(k, v)
    s = s.translate(_TBL)
    s = re.sub(r"(?<=[0-9])．(?=[0-9])", ".", s)   # 5．02 / 38．795 → 5.02 / 38.795
    return s


def digit_width(s):
    """本文の数字: 1桁=全角 / 2桁以上=半角。識別子は半角のまま保護"""
    holes = []

    def stash(m):
        holes.append(m.group(0))
        return "\ue000" + chr(0xE100 + len(holes) - 1) + "\ue001"

    s = re.sub(r"[0-9]+\.[0-9]+[a-zA-Z]?[0-9]*", stash, s)     # 5.02 / 5.06b3 / 38.795
    s = re.sub(r"（[0-9a-zA-Z]{1,4}）", stash, s)                # （1）（a）（10）（A）
    s = re.sub(r"【[^】]{1,14}】", stash, s)                      # 【注1】【原注2】
    s = re.sub(r"(?m)^(#{1,6} [0-9]+)(?=[　 ])", stash, s)       # 用語見出しの通し番号
    s = re.sub(r"(?<![0-9])([0-9])(?![0-9])",
               lambda m: chr(ord(m.group(1)) - 48 + 0xFF10), s)  # 1桁 → 全角
    # 【5.06a・c原注】のようにプレースホルダが入れ子になるので、無くなるまで繰り返す
    for _ in range(8):
        s2 = re.sub("\ue000(.)\ue001", lambda m: holes[ord(m.group(1)) - 0xE100], s)
        if s2 == s:
            break
        s = s2
    if re.search("[\ue000-\uf8ff]", s):
        raise RuntimeError("プレースホルダを復元しきれませんでした")
    return s


def block_styles(year, page, cache):
    """そのページのCSSを読み、<ul>のクラスごとに (注記か, 字下げ量em) を返す。

    元サイトは <ul> のクラスで本文と注記を書き分けており、注記系だけ font-size が
    90% になっている。クラス名の割り当てはページごとに違うのでCSSを見るしかない。
    この境界を落とすと、注記のあとに本文が再開する箇所（3.01のボールを汚す禁止など）が
    注記の続きとして取り込まれてしまう。

    字下げ量（padding-left）は注記の係り先を示す。注記は「自分より浅い直近のブロック」に
    係る。3.01では【注2】(7em)の直前でより浅いのがペナルティ(5em)なのでペナルティに係り、
    【原注】(5em)の直前でより浅いのは本文(3em)なので条に係る。"""
    fn = f"str{page}.css"
    dst = os.path.join(cache, fn)
    if not os.path.exists(dst):
        try:
            with urllib.request.urlopen(BASE.format(y=year) + fn, timeout=30) as r:
                open(dst, "wb").write(r.read())
        except Exception:
            open(dst, "wb").write(b"")
    css = open(dst, "rb").read().decode("cp932", errors="replace")
    out = {}
    for m in re.finditer(r"\.(tab[0-9]+)\s+li\s*\{(.*?)\}", css, re.S):
        d = m.group(2)
        fs = re.search(r"font-size:\s*([0-9]+)%", d)
        pl = re.search(r"padding-left:\s*([0-9.]+)em", d)
        out[m.group(1)] = (bool(fs) and int(fs.group(1)) < 100,
                           float(pl.group(1)) if pl else 3.0)
    return out


def clean_inline(s, bold=True):
    s = re.sub(r"(?is)<br\s*/?>", "", s)
    s = re.sub(r"(?is)</?(font|a|span|div|p|u|i)\b[^>]*>", "", s)
    if bold:
        s = re.sub(r"(?is)<b\b[^>]*>(.*?)</b>",
                   lambda m: "**" + m.group(1).strip() + "**" if m.group(1).strip() else "", s)
    s = re.sub(r"(?is)</?b\b[^>]*>", "", s)
    s = re.sub(r"(?is)<[^>]+>", "", s)
    s = html.unescape(s)
    for k, v in UNIT.items():
        s = s.replace(k, v)
    s = s.replace("\r", "").replace("\n", "")
    s = re.sub(r"[ \t]+", " ", s)
    return normalize(s).rstrip()


def norm_head(s):
    """見出しの字間調整用スペースを詰める（例: 本　　　塁 → 本塁）"""
    s = s.strip()
    m = re.match(r"^([0-9]+\.[0-9]+)[　\s]+(.*)$", s)
    if m:
        return m.group(1) + "　" + re.sub(r"[　\s]+", "", m.group(2))
    segs = [x for x in re.split(r"[　\s]+", s) if x]
    if len(segs) >= 3 and max(len(x) for x in segs) == 1:
        return "".join(segs)
    return re.sub(r"[　\s]{2,}", "　", s)


def body_of(text):
    m = re.search(r"(?is)<body[^>]*>(.*?)</body>", text)
    b = m.group(1) if m else text
    b = re.sub(r"(?is)<script.*?</script>", "", b)
    b = re.sub(r'(?is)<div class="floating1".*?</div>', "", b)
    b = re.sub(r"(?is)<img[^>]*>", "", b)
    b = re.sub(r"(?is)<!--.*?-->", "", b)
    return b


def convert(raw, styles=None, is_index=False, glossary=False, bullets=False):
    tm = re.search(r"(?is)<title>(.*?)</title>", raw)
    title = clean_inline(tm.group(1), bold=False).strip() if tm else ""
    styles = styles or {}
    b = body_of(raw)
    out = []

    for m in re.finditer(r'(?is)<p class="hyoudai"[^>]*>(.*?)</p>', b):
        inner = m.group(1)
        bm = re.search(r"(?is)<b\b[^>]*>(.*?)</b>", inner)
        head = clean_inline(bm.group(1) if bm else inner, bold=False).strip()
        rest = clean_inline(re.sub(r"(?is)<b\b[^>]*>.*?</b>", "", inner), bold=False).strip()
        out.append("# " + norm_head(head))
        if rest:
            out.append(rest)
    if not out:
        out.append("# " + title)

    if is_index:
        for dm in re.finditer(r'(?is)<div id="(t[^"]*)"[^>]*>(.*?)</div>', b):
            for am in re.finditer(r"(?is)<a[^>]*>(.*?)</a>", dm.group(2)):
                t = clean_inline(am.group(1), bold=False)
                if not t.strip():
                    continue
                depth = len(t) - len(t.lstrip("　 "))
                out.append("  " * (depth // 2) + "- " + t.strip())
        return out

    # <ul> のクラスで本文ブロックと注記ブロックを見分けながら li を拾う。
    # あわせて字下げ量を見て、注記が何に係るか（引用の深さ）を決める。
    stack = []
    seen_lines = []      # (字下げ量, 注記か, 深さ)  … 係り先の判定に使う

    last_depth = [0]

    def note_depth(indent):
        """自分より浅い直近のブロックに係る。ただしそれが注記の場合、その注記自身が
        自分の文脈より深く置かれているときだけ、係り先として採用する。

        3.01 では ペナルティ(5em) が本文(3em)より深いので【注2】(7em)はペナルティに係る。
        5.03 では ペナルティ(4em) が項(a)(b)(c)(4em)と同じ深さなので、
        続く【注1】(7em)はペナルティではなく条に係る。"""
        for k in range(len(seen_lines) - 1, -1, -1):
            ind, is_note, dep = seen_lines[k]
            if ind >= indent:
                continue
            if not is_note:
                return 1
            for j in range(k - 1, -1, -1):
                ind2, is_note2, _ = seen_lines[j]
                if not is_note2:
                    return dep + 1 if ind2 < ind else 1
            return 1
        return 1
    for m in re.finditer(r"(?is)<ul([^>]*)>|</ul>|<li\b([^>]*)>(.*?)(?=<li\b|</ul>|<ul\b|</div>|$)", b):
        if m.group(0).lower().startswith("<ul"):
            cm = re.search(r'class="([^"]*)"', m.group(1) or "")
            stack.append(cm.group(1).strip() if cm else "")
            continue
        if m.group(0).lower().startswith("</ul"):
            if stack:
                stack.pop()
            continue
        attrs, inner = m.group(2), m.group(3)
        style = styles.get(stack[-1] if stack else "", (False, 3.0))
        in_note, indent = style
        idm = re.search(r'id="([^"]+)"', attrs)
        top = bool(idm) and re.fullmatch(r"[0-9]+\.[0-9]+", idm.group(1)) is not None
        has_b = re.match(r"(?is)\s*<b\b", inner) is not None
        txt = clean_inline(inner, bold=not (idm and has_b))
        if not txt.strip():
            continue
        # id付きの li は目次のアンカー = 見出し。ただし長文のものは本文のまま
        if idm and len(txt.strip()) <= 50:
            out.append(("## " if top else "### ") + norm_head(txt))
            seen_lines.clear()
            continue
        if glossary:
            t = txt.strip()
            gm = re.match(r"^([0-9]+)[　 ]+([^─]{1,90}?)──(.*)$", t)
            if gm:
                out.append("## " + gm.group(1) + "　" + gm.group(2).strip())
                if gm.group(3).strip():
                    out.append(gm.group(3).strip())
                continue
            gm = re.match(r"^([0-9]+)[　 ]+(.{1,90})$", t)
            if gm:
                out.append("## " + gm.group(1) + "　" + gm.group(2).strip())
                continue
        if bullets:
            out.append("- " + txt.strip())
            continue
        t = txt.strip()
        starts_note = bool(re.match(r"^(【|\*\*?ペナルティ|ペナルティ　)", t))
        if starts_note:
            dep = note_depth(indent)
            seen_lines.append((indent, True, dep))
            out.append("> " * dep + t if (in_note or dep > 1) else txt)
            last_depth[0] = dep if (in_note or dep > 1) else 0
        elif in_note:
            dep = last_depth[0] or note_depth(indent)
            out.append("> " * dep + t)          # 直前の注記の続き
        else:
            seen_lines.append((indent, False, 0))
            last_depth[0] = 0
            out.append(txt)
    return out


def join_blocks(lines):
    """箇条書き行どうしは1行改行、それ以外は空行で連結"""
    out, prev_bullet = "", False
    for i, ln in enumerate(lines):
        bullet = ln.lstrip().startswith(("- ", "> "))
        if i == 0:
            out = ln
        elif bullet and prev_bullet:
            out += "\n" + ln
        else:
            out += "\n\n" + ln
        prev_bullet = bullet
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv
    if not args:
        sys.exit("usage: 1_import.py <年> [--force]")
    year = args[0]

    text_dir = os.path.join(ROOT, "years", year, "text")
    cache = os.path.join(HERE, "cache", year)
    if os.path.isdir(text_dir) and os.listdir(text_dir) and not force:
        sys.exit(f"{text_dir} は既に存在します。上書きするなら --force")
    os.makedirs(text_dir, exist_ok=True)
    os.makedirs(cache, exist_ok=True)

    base = BASE.format(y=year)
    combined = [f"# 公認野球規則 {year} Official Baseball Rules\n\n出典: {base}"]
    for suffix, name in PAGES:
        fn = f"rules{year}-{suffix}.html"
        dst = os.path.join(cache, fn)
        if not os.path.exists(dst):
            with urllib.request.urlopen(base + fn, timeout=30) as r:
                open(dst, "wb").write(r.read())
        raw = open(dst, "rb").read().decode("cp932", errors="replace")
        lines = convert(raw,
                        styles=block_styles(year, suffix, cache),
                        is_index=(suffix == "mokuji"),
                        glossary=(suffix == "y"),
                        bullets=(suffix == "9m"))
        body = digit_width(join_blocks(lines))
        open(os.path.join(text_dir, name + ".md"), "w", encoding="utf-8").write(body + "\n")
        combined += ["---", body]
        print(f"  {name}: {len(lines)} blocks")

    open(os.path.join(text_dir, f"公認野球規則{year}_全文.md"), "w",
         encoding="utf-8").write("\n\n".join(combined) + "\n")

    # 元サイトの転記ミスを当て直す（再取り込みで消えないように）
    import corrections
    corrections.run([year])
    print(f"→ {text_dir}")


if __name__ == "__main__":
    main()
