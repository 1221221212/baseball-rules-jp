#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""データの健全性をまとめて検査する

    python3 build/check.py        （または make check）

1. Markdown本文とデータの文字を1文字単位で突き合わせ、取りこぼしゼロを確認
2. 相互参照がすべて解決するか
3. 公式引用形式（cite_id）が重複なく引けるか
4. 差分がNPB公式改正文書の全項目を捉えているか
"""
import collections
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
SKIP = ("00-目次", "11-記録に関する規則_目次", "_全文")
ok = True


def bad(msg):
    global ok
    ok = False
    print("  ✗ " + msg)


def load_nodes(year):
    """rules.json（ルール本文）を平坦化して読む。派生ファイルには依存しない。"""
    p = os.path.join(ROOT, "years", year, "data", "rules.json")
    doc = json.load(open(p, encoding="utf-8"))
    out = []

    def walk(n, parent):
        n["parent_id"] = parent
        n["text"] = "\n".join(n.get("text") or [])
        out.append(n)
        for c in (n.get("children") or []):
            walk(c, n["id"])
    for ch in doc["chapters"]:
        walk(ch, None)
    return out

def norm(t):
    return re.sub(r"[\s　*#>|\-─【】（）()]", "", t)


def check_year(year):
    print(f"[{year}]")
    tdir = os.path.join(ROOT, "years", year, "text")
    md = "".join(open(f, encoding="utf-8").read()
                 for f in sorted(glob.glob(os.path.join(tdir, "*.md")))
                 if not any(s in os.path.basename(f) for s in SKIP))
    nodes = load_nodes(year)

    def tbl(n):
        t = n.get("table")
        if not t:
            return ""
        return "".join(t["head"]) + "".join("".join(r) for r in t["rows"])

    db = "".join(n["id"] + (n.get("title") or "") + (n.get("label") or "")
                 + (n.get("text") or "") + tbl(n) for n in nodes)
    ca, cb = collections.Counter(norm(md)), collections.Counter(norm(db))
    lost = {c: ca[c] - cb[c] for c in ca if cb[c] < ca[c]}
    print(f"  本文の取りこぼし : {'なし' if not lost else lost}") if not lost else bad(f"取りこぼし {lost}")

    pua = [n["id"] for n in nodes
           if re.search("[\ue000-\uf8ff]", n["id"] + (n.get("text") or "") + (n.get("label") or ""))]
    if pua:
        bad(f"私用領域文字の混入 {len(pua)}件 {pua[:5]}")
    else:
        print("  文字化け         : なし")

    ids = {n["id"] for n in nodes}
    dup = len(nodes) - len(ids)
    if dup:
        bad(f"ID重複 {dup}件")

    dangling = sorted({r for n in nodes for r in n.get("refs", []) if r not in ids})
    if dangling:
        bad(f"未解決の相互参照 {len(dangling)}件 {dangling[:8]}")
    else:
        print(f"  相互参照         : {sum(len(n.get('refs', [])) for n in nodes)}件すべて解決")

    alias = collections.Counter(a for n in nodes for a in n.get("cite_ids", []))
    col = [a for a, c in alias.items() if c > 1]
    if col:
        bad(f"cite_id が重複 {col[:5]}")
    else:
        print(f"  公式引用形式      : {len(alias)}種（重複なし）")

    # 項のラベル取り違え（大文字混入・ローマ数字の誤判定）は連番の欠けとして現れる
    import string
    by_parent = {}
    for n in nodes:
        by_parent.setdefault(n.get("parent_id"), []).append(n)
    gaps = []
    for pid, kids in by_parent.items():
        ls = [k["id"][len(pid):] for k in kids if k["level"] == "item"] if pid else []
        ls = [l for l in ls if len(l) == 1 and l in string.ascii_lowercase]
        if ls and ls != list(string.ascii_lowercase[:len(ls)]):
            gaps.append((pid, ls))
    if gaps:
        bad(f"項の連番に欠け {gaps}")
    else:
        print("  項の連番         : 欠けなし")

    counts = collections.Counter(n["level"] for n in nodes)
    print("  ノード           : " + "  ".join(f"{k}{v}" for k, v in counts.most_common()))
    return nodes


def check_official(old_y, new_y):
    """差分がNPB公式の改正文書を漏れなく捉えているか。
    公式文書はこちらが手で書き写したもので、対応表のある年度ペアだけ検査できる。
    成果物には含めない（任意の年度ペアでは作れないため）。"""
    import subprocess
    r = subprocess.run([sys.executable, os.path.join(HERE, "verify_official.py"), old_y, new_y],
                       capture_output=True, text=True)
    if r.returncode != 0:
        # 対応表が無い年度ペア。黙って飛ばすと「検証済み」と誤解されるので明示する
        print(f"[{old_y} → {new_y}]")
        print("  公式照合         : 未実施（build/verify_official.py に対応表がありません）")
        return False
    print(f"[{old_y} → {new_y}]")
    for line in r.stdout.strip().splitlines():
        print("  " + line.strip())
    if "拾い漏れ 0" not in r.stdout or "公式外 0" not in r.stdout:
        bad("公式照合が合っていません")
    return True


def main():
    years = sorted(d for d in os.listdir(os.path.join(ROOT, "years")) if d.isdigit())
    for y in years:
        check_year(y)
    for a, b in zip(years, years[1:]):
        check_official(a, b)
    print()
    print("すべて問題なし" if ok else "問題あり")
    sys.exit(0 if ok else 1)


main()
