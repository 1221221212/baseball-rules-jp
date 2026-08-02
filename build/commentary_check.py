#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解説の品質を測る。

絶対かつ唯一のソースは規則書であり条文である。したがって解説が主張することは、
（1）条文にそう書いてある、（2）他の条文から導ける、（3）どこにも書いていない私見、
のいずれかに分類できなければならない。分類のない主張は、根拠を偽っているに等しい。

    1. 参照した条文IDがすべて実在するか
    2. 解釈を主張している文のうち、根拠の身分を示していないものが何割か
    3. 規則書自身が持つ設例（問答・例題）を取り込んでいるか
    4. 判断の順序（決定木）を示しているか
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
YEAR = "2026"

# 理由・趣旨・評価を述べている文。事実の記述と区別する
CLAIM = re.compile(r"(からである|趣旨である|と解される|と解する|意味する|現れである|ためである|"
                   r"によるものである|考え方に立つ|ほかならない|べきである|に由来する|と考えられる)")


def load_rules():
    doc = json.load(open(os.path.join(ROOT, "years", YEAR, "data", "rules.json"), encoding="utf-8"))
    ids, cases = set(), []

    def walk(n):
        ids.add(n["id"])
        if (n.get("kind") or "") in ("問", "答", "例題", "解答"):
            cases.append(n["id"])
        for c in (n.get("children") or []):
            walk(c)
    for ch in doc["chapters"]:
        walk(ch)
    return ids, cases


def refs_of(e):
    """解説が指している条文IDをすべて集める"""
    out = [r["id"] for r in e.get("refs", []) + e.get("related", [])]
    for r in e.get("rules", []):
        if "ref" in r:
            out.append(r["ref"]["id"])
        for it in (r.get("elements") or []) + (r.get("exceptions") or []):
            if isinstance(it, dict) and it.get("ref"):
                out += [x.strip() for x in it["ref"].split(",")]
    for it in (e.get("points") or []):
        if isinstance(it, dict) and it.get("ref"):
            out += [x.strip() for x in it["ref"].split(",")]

    def tw(n):
        if n.get("ref"):
            out.extend(x.strip() for x in n["ref"].split(","))
        for k in (n.get("b") or []):
            tw(k)
    if e.get("tree"):
        tw(e["tree"])
    return [x for x in out if x]


def claims_of(e):
    """（主張の数, うち身分を示しているもの）"""
    n = s = 0

    def scan(txt, grounded):
        nonlocal n, s
        for sent in re.split(r"[。\n]", txt or ""):
            if CLAIM.search(sent):
                n += 1
                if grounded:
                    s += 1
    for f in ("purpose", "structure", "thesis"):
        scan(e.get(f), False)
    for r in e.get("rules", []):
        scan(r.get("note"), False)
        scan(r.get("effect"), False)
        for it in (r.get("elements") or []) + (r.get("exceptions") or []):
            if isinstance(it, dict):
                scan(it.get("note"), bool(it.get("ref")) or it.get("s") == "私見")
    for it in (e.get("points") or []):
        if isinstance(it, dict):
            scan((it.get("t") or "") + " " + (it.get("note") or ""),
                 bool(it.get("ref")) or it.get("s") == "私見")
        else:
            scan(it, False)
    return n, s


def main():
    ids, cases = load_rules()
    doc = json.load(open(os.path.join(ROOT, "commentary.json"), encoding="utf-8"))
    entries = doc["entries"]
    ok = True

    dangling = sorted({r for e in entries for r in refs_of(e) if r not in ids})
    if dangling:
        print(f"  ✗ 実在しない参照 {len(dangling)}件 {dangling[:6]}")
        ok = False
    else:
        print(f"  参照           : {sum(len(refs_of(e)) for e in entries)}件すべて実在")

    n = s = 0
    worst = []
    for e in entries:
        a, b = claims_of(e)
        n += a
        s += b
        if a - b:
            worst.append((a - b, e["title"][:30]))
    print(f"  解釈の主張      : {n}文  根拠あり {s}  根拠なし {n - s}"
          f"（{(n - s) * 100 // max(n, 1)}%）")
    for k, t in sorted(worst, reverse=True)[:5]:
        print(f"      根拠なし{k:>3}  {t}")

    used = {r for e in entries for r in refs_of(e)}
    got = [c for c in cases if c in used]
    print(f"  規則書の設例    : {len(got)} / {len(cases)}件を引用")

    trees = sum(1 for e in entries if e.get("tree"))
    print(f"  判断の順序      : {trees} / {len(entries)}件が決定木を持つ")

    art = [e for e in entries if not e.get("kind")]
    print(f"  条の解説        : {len(art)} / 76条")
    return ok


sys.exit(0 if main() else 1)
