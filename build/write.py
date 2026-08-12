#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解説を書き足すための道具。commentary.json へ流し込む。

絶対かつ唯一のソースは規則書であり条文である。したがって主張には身分を付ける。
    D(...)  定義 ── 規則書にそう書いてある
    V(...)  導出 ── 他の条文から導ける
    O(...)  私見 ── どこにも書いていない
    印なし  読めばそのまま分かる

参照IDは rules.json と突き合わせる。存在しない条文は書けない。
"""
import json, os, re, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
Y = "2026"
_d = json.load(open(os.path.join(ROOT, "years", Y, "data", "rules.json"), encoding="utf-8"))
IDS = set()


def _w(n):
    IDS.add(n["id"])
    for c in (n.get("children") or []):
        _w(c)


for _c in _d["chapters"]:
    _w(_c)

# 規則書自身の用語の定義。「他の条文で定義されていないか」は記憶ではなく走査で答える
DEFS = {}
for _c in _d["chapters"]:
    if _c["id"] == "y":
        for _n in _c["children"]:
            for _m in re.findall(r"[「（]([^」）]+)[」）]", _n.get("title") or ""):
                _m = _m.strip()
                if _m and not re.match(r"^[A-Za-z\s\-'.]+$", _m):
                    DEFS.setdefault(_m, _n["id"])


def ref(i):
    return {"year": Y, "id": i}


def D(t, at):
    return {"t": t, "s": "定義", "ref": at}


def V(t, at, note=None):
    x = {"t": t, "s": "導出", "ref": at}
    if note:
        x["note"] = note
    return x


def O(t, note=None):
    x = {"t": t, "s": "私見"}
    if note:
        x["note"] = note
    return x


def Q(q, *branches):
    return {"q": q, "b": list(branches)}


def B(cond, result=None, at=None, note=None, sub=None):
    n = {"c": cond}
    if result:
        n["r"] = result
    if at:
        n["ref"] = at
    if note:
        n["note"] = note
    if sub:
        n.update({"q": sub.get("q"), "b": sub["b"]})
    return n


def rule(head, at=None, req=None, eff=None, exc=None, note=None):
    r = {"head": head}
    if at:
        r["ref"] = ref(at)
    if req:
        r["elements"] = req
    if eff:
        r["effect"] = eff
    if exc:
        r["exceptions"] = exc
    if note:
        r["note"] = note
    return r


use = rule


def entry(rid, title, at, tags, purpose=None, structure=None, rules=None,
          points=None, related=None, tree=None, kind=None, thesis=None):
    e = {"id": rid, "title": title,
         "refs": [ref(x) for x in (at if isinstance(at, list) else [at])], "tags": tags}
    if kind:
        e["kind"] = kind
    for k, v in (("purpose", purpose), ("structure", structure), ("rules", rules),
                 ("thesis", thesis), ("points", points), ("tree", tree)):
        if v:
            e[k] = v
    if related:
        e["related"] = [ref(x) for x in related]
    return e


def term(rid, title, at, tags, **kw):
    kw["rules"] = kw.pop("uses", None)
    return entry(rid, title, at, tags, kind="term", **kw)


def _refs(e):
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


def save(entries):
    p = os.path.join(ROOT, "commentary.json")
    doc = json.load(open(p, encoding="utf-8"))
    bad = [(e["id"], r) for e in entries for r in _refs(e) if r not in IDS]
    if bad:
        print("存在しない参照ID:")
        for a, b in bad:
            print("  ", a, "->", b)
        sys.exit(1)
    keep = [x for x in doc["entries"] if x["id"] not in {e["id"] for e in entries}]
    doc["entries"] = sorted(keep + entries, key=lambda x: x["id"])
    json.dump(doc, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(entries)}件を書き込み（全{len(doc['entries'])}件）")
