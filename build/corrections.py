#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""元サイトの転記ミスを直す（何度実行しても同じ結果になる）

    python3 corrections.py            # 全年度
    python3 corrections.py 2026       # 年度を指定

1_import.py の最後から呼ばれるので、通常は直接叩かなくてよい。
補正の根拠は ../CORRECTIONS.md に書く。ここに足したら向こうも更新すること。

対象の文が無ければ黙って飛ばす。年度によって存在しない補正があるため
（例: 4.03(e)の【注】は2026年の新設で、2025年版には無い）。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")

MOVE_NOTE = "> 【注】　我が国では、天候状況によっては、30分を待つことなく試合を打ち切ることができる。"
MOVE_ANCHOR = ("　　　　　球審はプレイを中断した後、少なくとも30分を経過するまでは、打ち切りを命じては"
               "ならない。また球審はプレイ再開の可能性があると確信すれば、一時停止の状態を延長しても"
               "さしつかえない。")
DROP_NOTE = "> 【注】　アマチュア野球では、次の試合に出場するプレーヤーがスタンドで観戦することを許す場合もある。"


# 3.01【軟式注】のボール規格。元サイトは全角スペースで桁を合わせているだけなので、
# プロポーショナルフォントでは桁が揃わない。表として持ち直す。
BALL_TABLE_OLD = [
    "> 直　径　　　　　　　　　重　量　　　　　　　　　反　発　　　20％圧縮荷重",
    "> M号　71.5ミリ～72.5ミリ　136.2グラム～139.8グラム　70センチ～90センチ　32キログラム～40キログラム",
    "> J号　68.5ミリ～69.5ミリ　127.2グラム～130.8グラム　60センチ～80センチ　27キログラム～37キログラム",
    "> D号　64.0ミリ～65.0ミリ　105.0グラム～110.0グラム　65センチ～85センチ",
    "> H号　71.5ミリ～72，５ミリ　141.2グラム～144.8グラム　70センチ～90センチ",
]
BALL_TABLE_NEW = [
    "> | | 直径 | 重量 | 反発 | 20％圧縮荷重 |",
    "> |---|---|---|---|---|",
    "> | M号 | 71.5ミリ～72.5ミリ | 136.2グラム～139.8グラム | 70センチ～90センチ | 32キログラム～40キログラム |",
    "> | J号 | 68.5ミリ～69.5ミリ | 127.2グラム～130.8グラム | 60センチ～80センチ | 27キログラム～37キログラム |",
    "> | D号 | 64.0ミリ～65.0ミリ | 105.0グラム～110.0グラム | 65センチ～85センチ | |",
    "> | H号 | 71.5ミリ～72.5ミリ | 141.2グラム～144.8グラム | 70センチ～90センチ | |",
]

# 元サイトが項のラベルを大文字で書いてしまっている箇所。(a)(b)[C](d) のように
# 小文字の連番に混ざっており、そのままだと細目とみなされて一段深く入る
UPPER_LABEL = [
    ("03-用具・ユニフォーム.md", "3.02（c）バットの握りの部分",
     "　　（C）　バットの握りの部分"),
    ("12-記録に関する規則.md", "9.17（c）救援投手",
     "　　（C）　救援投手が少しの間投げただけで"),
]

# 元サイトが注記を一段深く置いている箇所。引用の深さだけを直す。
# 条文の文字（ラベルを含む）には一切手を触れない
NOTE_DEDENT = [
    ("03-用具・ユニフォーム.md", "3.02(c)の原注", "【原注】　パインタール"),
]

CORRECTIONS = [
    {
        "id": "3.01-ball-table",
        "file": "03-用具・ユニフォーム.md",
        "kind": "block",
        "old": BALL_TABLE_OLD,
        "new": BALL_TABLE_NEW,
        "why": "全角スペースによる桁合わせを表に置き換える。あわせてH号の「72，５ミリ」を"
               "「72.5ミリ」に直す（元サイトの誤記。H号の寸法はM号と同一）",
    },
    {
        "id": "note-dedent",
        "kind": "dedent",
        "targets": NOTE_DEDENT,
        "why": "元サイトが【付記】の下に置いているが、係り先は3.02(c)で付記と並列。"
               "引用の深さを一段戻す（文字は変えない）",
    },
    {
        "id": "upper-item-label",
        "kind": "relabel",
        "targets": UPPER_LABEL,
        "why": "元サイトが項のラベルを大文字（Ｃ）で書いている。前後は小文字の連番なので誤記",
    },
    {
        "id": "4.03e-note-move",
        "file": "04-試合の準備.md",
        "kind": "move",
        "line": MOVE_NOTE,
        "after": MOVE_ANCHOR,
        "why": "NPB「2026年度 野球規則改正」(16)は4.03(e)への追加と明記。元サイトは4.01(e)配下に置いている",
    },
    {
        "id": "4.03-stand-note-drop",
        "file": "04-試合の準備.md",
        "kind": "drop",
        "line": DROP_NOTE,
        "why": "4.06(2)と6.04(b)(2)にある同趣旨の注（「特に許す」）の重複。打順表の交換とは無関係",
    },
]


def dedent(c):
    """注記の引用の深さを一段戻す。条文の文字は変えない"""
    done = []
    for y in sorted(d for d in os.listdir(os.path.join(ROOT, "years")) if d.isdigit()):
        for fn, where, needle in c["targets"]:
            path = os.path.join(ROOT, "years", y, "text", fn)
            if not os.path.exists(path):
                continue
            lines = open(path, encoding="utf-8").read().split("\n")
            hit = False
            for i, ln in enumerate(lines):
                if needle in ln and ln.startswith("> > "):
                    lines[i] = ln[2:]          # 「> 」を1つ外す
                    hit = True
                elif hit and ln.startswith("> > "):
                    lines[i] = ln[2:]          # 続きの行も揃える
                elif hit:
                    break
            if hit:
                open(path, "w", encoding="utf-8").write("\n".join(lines))
                done.append(f"  [{y}] {c['id']}: {where}")
    return done


def relabel(c):
    """項ラベルの大文字を小文字に直す"""
    done = []
    for y in sorted(d for d in os.listdir(os.path.join(ROOT, "years")) if d.isdigit()):
        for fn, where, prefix in c["targets"]:
            path = os.path.join(ROOT, "years", y, "text", fn)
            if not os.path.exists(path):
                continue
            lines = open(path, encoding="utf-8").read().split("\n")
            for i, ln in enumerate(lines):
                if ln.startswith(prefix):
                    lines[i] = ln.replace("（C）", "（c）", 1)
                    open(path, "w", encoding="utf-8").write("\n".join(lines))
                    done.append(f"  [{y}] {c['id']}: {where}")
                    break
    return done


def apply_to(path, c):
    lines = open(path, encoding="utf-8").read().split("\n")
    if c["kind"] != "block" and c["line"] not in lines:
        return None                                  # 対象が無い年度
    if c["kind"] == "block":
        n = len(c["old"])
        for i in range(len(lines) - n + 1):
            if lines[i:i + n] == c["old"]:
                lines[i:i + n] = c["new"]
                open(path, "w", encoding="utf-8").write("\n".join(lines))
                return "表に整形"
        return None
    if c["kind"] == "drop":
        i = lines.index(c["line"])
        del lines[i]
        if i < len(lines) and lines[i] == "":
            del lines[i]
        out = "削除"
    else:
        if c["after"] not in lines:
            return f"! 挿入位置「{c['after'][:20]}…」が見つかりません"
        i = lines.index(c["line"])
        del lines[i]
        if i < len(lines) and lines[i] == "":
            del lines[i]
        j = lines.index(c["after"]) + 1
        lines[j:j] = ["", c["line"]]
        out = "移動"
    open(path, "w", encoding="utf-8").write("\n".join(lines))
    return out


def run(years=None):
    yd = os.path.join(ROOT, "years")
    years = years or sorted(d for d in os.listdir(yd) if d.isdigit())
    for c in CORRECTIONS:
        if c["kind"] == "relabel":
            for line in relabel(c):
                print(line)
        elif c["kind"] == "dedent":
            for line in dedent(c):
                print(line)
    for y in years:
        for c in CORRECTIONS:
            if c["kind"] in ("relabel", "dedent"):
                continue
            path = os.path.join(yd, y, "text", c["file"])
            if not os.path.exists(path):
                continue
            r = apply_to(path, c)
            if r:
                print(f"  [{y}] {c['id']}: {r}")


if __name__ == "__main__":
    run([a for a in sys.argv[1:] if a.isdigit()] or None)
