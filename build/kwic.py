#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ある語が規則全体のどこに現れるかを集める。

解釈は用例の総体から導くものであり、記憶から書けば必ず取りこぼす。
検索語を狭めると取りこぼしに気づけないので、広く取って人が仕分ける。

    python3 build/kwic.py デッド
    python3 build/kwic.py --count 故意 明らかに
"""
import json, os, re, sys, collections

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
YEAR = "2026"

_doc = json.load(open(os.path.join(ROOT, "years", YEAR, "data", "rules.json"), encoding="utf-8"))
NODES = []


def _walk(n):
    NODES.append((n["id"], n.get("cite") or n["id"], "\n".join(n.get("text") or [])))
    for c in (n.get("children") or []):
        _walk(c)


for _ch in _doc["chapters"]:
    _walk(_ch)


def find(word, width=34):
    out = []
    for nid, cite, txt in NODES:
        for m in re.finditer(re.escape(word), txt):
            s, e = max(0, m.start() - width), min(len(txt), m.end() + width)
            out.append((nid, cite, ("…" if s else "") + txt[s:e].replace("\n", "／") + ("…" if e < len(txt) else "")))
    return out


def main():
    args = sys.argv[1:]
    only_count = "--count" in args
    for word in [a for a in args if not a.startswith("--")]:
        hits = find(word)
        nodes = {h[0] for h in hits}
        print(f"### 「{word}」  {len(hits)}箇所 / {len(nodes)}ノード")
        sec = collections.Counter(c.split("（")[0].split("【")[0] for _, c, _ in hits)
        print("  条ごと:", dict(sec.most_common(30)))
        if not only_count:
            for _, cite, ctx in hits:
                print(f"  {cite:<24}{ctx}")
        print()


if __name__ == "__main__":
    main()
