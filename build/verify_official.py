#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""差分がNPB公式の改正文書を漏れなく捉えているか検査する（ビルド時のテスト）

    python3 verify_official.py 2025 2026

ファイルは何も書かない。結果は標準出力だけ。

公式改正文書はこちらが手で書き写したもので、特定の年度ペアにしか存在しない。
それをビューアに読ませると「2000年 vs 2026年」のような組み合わせで破綻するため、
成果物には一切含めず、パイプラインの検査だけに使う。

ここでの突き合わせは index.html の computeDiff と同じ3段階。
片方だけ直すとこの検査が意味を失うので、変更するときは両方を直すこと。
"""
import difflib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")

RENAME_THRESHOLD = 0.60
EDIT_MARKS = re.compile(r"《(新|改|削|訂)》")


def canon(s):
    return re.sub(r"[\s　]+", "", EDIT_MARKS.sub("", s or ""))


def load(year):
    """rules.json（ルール本文）を平坦化して読む。派生ファイルには依存しない。"""
    doc = json.load(open(os.path.join(ROOT, "years", year, "data", "rules.json"), encoding="utf-8"))
    out = {}

    def walk(n, parent):
        n["parent_id"] = parent
        n["text"] = "\n".join(n.get("text") or [])
        out[n["id"]] = n
        for c in (n.get("children") or []):
            walk(c, n["id"])
    for ch in doc["chapters"]:
        walk(ch, None)
    return out


def body(n):
    return ((n.get("title") or "") + "\n" + (n.get("text") or "")).strip()


# ---------------------------------------------------------------------------
# 公式改正文書。新しい年度を足したら、公式文書を読んでここに追記する
# ---------------------------------------------------------------------------
OFFICIAL = {
    ("2025", "2026"): {
        "source": "NPB「2026年度 野球規則改正」日本野球規則委員会",
        "items": [
            ("(1)", "5.02(c) 内野手の守備位置・ペナルティ",
             ["5.02i", "5.02ii", "5.02iii-ペナルティ", "5.02iii-ペナルティ-原注"]),
            ("(2)", "5.06(c)(7)【原注】ボールを隠す行為", ["5.06c7-原注"]),
            ("(3)", "5.07(a)(1) ワインドアップポジション", ["5.07a1", "5.07a1-注"]),
            ("(4)", "5.07(a)(2) セットポジション",
             ["5.07a2", "5.07a2-注1", "5.07a2-原注", "5.07a2-注6", "5.07a2-注7"]),
            ("(5)", "5.07(d) 塁に送球", ["5.07d"]),
            ("(6)", "5.09(b)(7) 走者が打球に触れた場合",
             ["5.09b7", "5.09b7-注2", "5.09b7-注3", "5.09b7-注4", "5.09b7-注5"]),
            ("(7)", "5.10(l)【原注】マウンドに行った回数", ["5.10-原注"]),
            ("(8)", "6.01(a)(8) ベースコーチの援助", ["6.01a8"]),
            ("(9)", "6.01(h)【付記】捕手の走路確保", ["6.01h-付記", "6.01h-原注"]),
            ("(10)", "6.02(a)(1) ボーク", ["6.02a1"]),
            ("(11)", "3.02(a) バット", ["3.02a-付記-注1", "3.02a-付記-注2"]),
            ("(12)", "3.02(d) 着色バット",
             ["3.02d", "3.02d-注", "3.02-注", "3.02d-注1", "3.02d-注2"]),
            ("(13)", "3.03(j)【注1】ユニフォーム", ["3.03j-注1"]),
            ("(14)", "3.08 ヘルメット", ["3.08", "3.08b"]),
            ("(15)", "3.09 商業的宣伝", ["3.09", "3.09-付記", "3.09-注4"]),
            ("(16)", "4.03(e)【注】天候による打ち切り", ["4.03e-注"]),
            ("(17)", "5.08(b)【注】得点の記録", ["5.08b-注"]),
            ("(18)", "5.10(e)【注】プレーヤーの交代", ["5.10e-注"]),
            ("(19)", "5.10(g)(2)【注】準備投球", ["5.10g2-注"]),
            ("(20)", "5.10(k)【注2】ベンチに入れる者", ["5.10k-注2"]),
            ("(21)", "5.10(l) マウンドに行ける回数", ["5.10l"]),
            ("(22)", "7.02【注】サスペンデッドゲーム", ["7.02f-注", "7.02-注1", "7.02-注2"]),
            ("(23)", "8.01(b) 審判員の権限", ["8.01b"]),
            ("(24)", "9.22【注】各最優秀プレーヤー", ["9.22-注"]),
            ("(25)", "定義38 イリーガルピッチ", ["y38"]),
            ("(26)", "定義64 クイックピッチ", ["y64"]),
            ("(27)", "「打者」→「打者走者」",
             ["5.06b4G-規則説明", "5.06b4I", "5.08b", "5.09b2-原注", "5.09b6-原注",
              "5.09c2B-原注", "9.05b4", "9.12f1", "y28", "y30-原注"]),
        ],
    },
}


def diff(A, B):
    """ビューア（JS）と同じ3段階の突き合わせ。
    ID一致だけだと注記の採番繰り上げを別物と誤判定するため、本文一致を先に見る。"""
    def by_parent(D):
        g = {}
        for k, n in D.items():
            g.setdefault(n.get("parent_id"), []).append(k)
        return g

    ga, gb = by_parent(A), by_parent(B)
    pairs, done_a, done_b = {}, set(), set()

    for p in set(ga) & set(gb):                       # 1. 同じ親・同じlevel・本文一致
        rest = list(gb[p])
        for ka in ga[p]:
            ca = canon(body(A[ka]))
            for kb in rest:
                if B[kb]["level"] == A[ka]["level"] and canon(body(B[kb])) == ca:
                    pairs[ka] = kb
                    done_a.add(ka); done_b.add(kb); rest.remove(kb)
                    break
    for ka in A:                                      # 2. ID一致
        if ka not in done_a and ka in B and ka not in done_b:
            pairs[ka] = ka
            done_a.add(ka); done_b.add(ka)
    for ka in sorted(set(A) - done_a):                # 3. 類似度（採番替え）
        na = A[ka]
        best, best_r = None, RENAME_THRESHOLD
        for kb in sorted(set(B) - done_b):
            nb = B[kb]
            if nb["level"] != na["level"] or nb.get("parent_id") != na.get("parent_id"):
                continue
            r = difflib.SequenceMatcher(None, canon(body(na)), canon(body(nb))).ratio()
            if r > best_r:
                best, best_r = kb, r
        if best:
            pairs[ka] = best
            done_a.add(ka); done_b.add(best)

    # 4. 親をまたいで本文が一致するもの＝係り先が変わった注記など
    by_text = {}
    for kb in sorted(set(B) - done_b):
        by_text.setdefault((B[kb]["level"], canon(body(B[kb]))), []).append(kb)
    for ka in sorted(set(A) - done_a):
        bucket = by_text.get((A[ka]["level"], canon(body(A[ka]))), [])
        for kb in bucket:
            if kb not in done_b:
                pairs[ka] = kb
                done_a.add(ka)
                done_b.add(kb)
                break

    def reparented(ka, kb):
        """係り先が変わったか。親自身が採番替えされている場合があるので対応付け後に見る"""
        pa, pb = A[ka].get("parent_id"), B[kb].get("parent_id")
        if pa is None and pb is None:
            return None
        mapped = pairs.get(pa, pa) if pa is not None else None
        return None if mapped == pb else {"from": pa, "to": pb}

    out = []
    for ka, kb in pairs.items():
        same = canon(body(A[ka])) == canon(body(B[kb]))
        rep = reparented(ka, kb)
        if same and not rep and ka == kb:
            continue
        e = {"id": kb}
        if ka != kb:
            e["old_id"] = ka
        e["status"] = ("reparented" if (rep and same)
                       else "changed" if (rep or ka == kb)
                       else "renamed" if same else "renamed_changed")
        if rep:
            e["reparent"] = rep
        out.append(e)
    for ka in sorted(set(A) - done_a):
        out.append({"id": ka, "status": "removed"})
    for kb in sorted(set(B) - done_b):
        out.append({"id": kb, "status": "added"})
    return out


def main():
    years = [a for a in sys.argv[1:] if a.isdigit()]
    if len(years) != 2:
        sys.exit("usage: 3_official.py <旧年> <新年>")
    old_y, new_y = sorted(years)
    A, B = load(old_y), load(new_y)
    entries = diff(A, B)

    o = OFFICIAL.get((old_y, new_y))
    if not o:
        sys.exit(f"{old_y}→{new_y} の公式改正文書が build/3_official.py の OFFICIAL にありません。"
                 "\n公式PDFを読んで追記してください。")

    # ノードIDは構造の見直しで変わりうるので、公式引用形式（cite_ids）でも突き合わせる
    alias = {}
    for D in (A, B):
        for nid, n in D.items():
            for a in n.get("cite_ids") or []:
                alias.setdefault(a, set()).add(nid)

    entry_ids = {e["id"] for e in entries} | {e["old_id"] for e in entries if e.get("old_id")}

    def resolve(i):
        """公式文書に書かれたIDを、実際のノードIDへ寄せる"""
        return ({i} | alias.get(i, set())) & entry_ids

    tagged, items, miss = set(), [], []
    for no, title, ids in o["items"]:
        hit = set()
        for i in ids:
            hit |= resolve(i)
        if not hit:
            miss.append(f"{no} {title}")
            print(f"  ✗ 拾い漏れ {no} {title}  期待:{ids}")
        tagged |= hit
        items.append({"no": no, "title": title, "targets": ids})
    extra = [e["id"] for e in entries
             if e["id"] not in tagged and (e.get("old_id") or e["id"]) not in tagged]

    summary = {}
    for e in entries:
        summary[e["status"]] = summary.get(e["status"], 0) + 1

    print(f"[{old_y} → {new_y}] " + "  ".join(f"{k}{v}" for k, v in summary.items()))
    print(f"  公式{len(o['items'])}項目: 検出 {len(o['items']) - len(miss)}"
          f" / 拾い漏れ {len(miss)} / 公式外 {len(extra)}")
    for x in extra:
        print(f"    公式外: {x}")



main()
