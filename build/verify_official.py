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
    """比較対象。表の中身も含める（3.01のボール規格のように表だけが変わることがある）"""
    t = n.get("table")
    tbl = ("\n" + "\n".join("\t".join(r) for r in [t["head"]] + t["rows"])) if t else ""
    return ((n.get("title") or "") + "\n" + (n.get("text") or "") + tbl).strip()


# ---------------------------------------------------------------------------
# 公式改正文書。新しい年度を足したら、公式文書を読んでここに追記する
# ---------------------------------------------------------------------------
OFFICIAL = {
    ("2024", "2025"): {
        "source": "NPB「2025年度 野球規則改正」日本野球規則委員会",
        "items": [
            ("(1)", "2.01 グラスライン", ["2.01", "2.01-注", "2.01a", "2.01b", "2.01b-注"]),
            ("(2)", "3.01【軟式注】H号の反発", ["3.01-軟式注"]),
            ("(3)", "3.08 ヘルメット（(b)削除・繰り上げ）",
             ["3.08b", "3.08b-注", "3.08c", "3.08d", "3.08e", "3.08-注"]),
            ("(4)", "5.04(b) 打者の義務", ["5.04b2-原注", "5.04b4ix"]),
            ("(5)", "5.09(a)(11)【原注】スリーフットレーン", ["5.09a11-原注", "5.09a11-注"]),
            ("(6)", "5.10(g) 最小限必要とする打者への投球",
             ["5.10g", "5.10g-注", "5.10g1", "5.10g1-注", "5.10g2"]),
            ("(7)", "5.10(m) マウンドに行く回数", ["5.10m", "5.10m1"]),
            ("(8)", "6.02(d) ペナルティ", ["6.02d", "6.02d1"]),
            ("(9)", "7.01(a)(2) コールドゲームの宣告", ["7.01a2", "7.01a2-例外"]),
            ("(10)", "7.01(c) 延期・中止", ["7.01c", "7.01c-注"]),
            ("(11)", "7.01(c)(d)を統合し(d)へ",
             ["7.01d", "7.01d1", "7.01d2", "7.01d3", "7.01d3-注", "7.01d3-注#2", "7.01c3"]),
            ("(12)", "7.01(e)(f)削除", ["7.01e", "7.01f"]),
            ("(13)", "7.01(g)を(e)へ",
             ["7.01e", "7.01e1", "7.01e2", "7.01e3", "7.01e3-例外",
              "7.01e3-規則説明", "7.01e3-規則説明-注", "7.01e4", "7.01e4-注",
              "7.01g4", "7.01g4-注"]),
            ("(14)", "7.02 サスペンデッドゲーム全面改正",
             ["7.02a", "7.02a1", "7.02a2", "7.02a3", "7.02a4", "7.02a5", "7.02a6",
              "7.02a6-付記", "7.02b", "7.02b1", "7.02b2", "7.02b3", "7.02b3A", "7.02b3B",
              "7.02b4", "7.02b4A", "7.02b4B", "7.02b4C", "7.02c", "7.02d", "7.02d1",
              "7.02d2", "7.02e"]),
            ("(15)", "7.02(c)を(f)へ・継続試合",
             ["7.02f", "7.02f-原注", "7.02-注", "7.02c-原注", "7.02c-注"]),
            ("(16)", "9.01 リーグ事務局", ["9.01a", "9.01b", "9.01c"]),
            ("(17)", "【9.22注】", ["9.22-注"]),
            ("(18)", "定義14 コールドゲーム", ["y14"]),
            ("(19)", "定義63 ポストポンドゲーム追加・以下繰り下げ",
             ["y63", "y64", "y65", "y66", "y66-注", "y67", "y68", "y69", "y70", "y71",
              "y72", "y73", "y73-注", "y74", "y74-注", "y75", "y76", "y77", "y78",
              "y79", "y80", "y81", "y82", "y83"]),
        ],
        # 公式に記載がないが、調べたうえで説明がついたもの。黙って無視しないため理由を残す
        "known": {
            "2.01b-軟式注":
                "係り先の変化は改正ではなく推定の限界。元サイトは【注】（(a)(b)に係る）と"
                "【軟式注】（学童部の塁間距離＝2.01全体に係る）を同じブロック・同じ字下げで"
                "(b)の直後に置いており、両者を区別する手がかりがない。"
                "2025年に(a)(b)が新設された結果、【軟式注】の推定係り先が2.01→2.01(b)へ動いた",
        },
    },
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

    def match_by_content(parent_of):
        """親を対応づけたうえで、その配下を本文一致で結ぶ"""
        found = 0
        for pa, la in ga.items():
            pb = parent_of(pa)
            if pb is None or pb not in gb:
                continue
            rest = [k for k in gb[pb] if k not in done_b]
            for ka in la:
                if ka in done_a:
                    continue
                ca = canon(body(A[ka]))
                for kb in rest:
                    if B[kb]["level"] == A[ka]["level"] and canon(body(B[kb])) == ca:
                        pairs[ka] = kb
                        done_a.add(ka); done_b.add(kb); rest.remove(kb)
                        found += 1
                        break
        return found

    # 1. 同じ親・同じlevel・本文一致
    match_by_content(lambda pa: pa)
    # 1b. 親が採番替えされた場合。親の対応が決まるたびに配下も結べるので、
    #     新しい対応が出なくなるまで繰り返す（定義が1つ増えて以降が繰り下がる等）
    while match_by_content(lambda pa: pairs.get(pa)):
        pass
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
    known = o.get("known", {})
    extra = [e["id"] for e in entries
             if e["id"] not in tagged and (e.get("old_id") or e["id"]) not in tagged]
    explained = [x for x in extra if x in known]
    extra = [x for x in extra if x not in known]

    summary = {}
    for e in entries:
        summary[e["status"]] = summary.get(e["status"], 0) + 1

    print(f"[{old_y} → {new_y}] " + "  ".join(f"{k}{v}" for k, v in summary.items()))
    print(f"  公式{len(o['items'])}項目: 検出 {len(o['items']) - len(miss)}"
          f" / 拾い漏れ {len(miss)} / 公式外 {len(extra)}")
    for x in extra:
        print(f"    公式外: {x}")
    for x in explained:
        print(f"    公式外（説明済み）: {x}")
        print(f"      {known[x]}")



main()
