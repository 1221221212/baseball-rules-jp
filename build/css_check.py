#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""折り返せない箇所・固定幅を監視する。

画面幅を決め打ちして「この長さなら収まる」と確かめるのはレスポンシブではない。
内容がどうであれ縮められることが必要で、それを妨げるのは次の2つに限られる。

    white-space:nowrap   折り返しを禁じる
    width:Npx            内容によらず幅を固定する

どちらも理由があって置く場合はあるので、理由つきで許可簿に載せる。
載っていないものが現れたら落とす。増えたことに気づけない仕組みでは意味がない。
"""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

# 選択子 -> なぜ内容に追随しなくてよいか
ALLOW = {
    "table": "横スクロールする入れ物（.tw）の中にある。表は縮めるより流す方がよい",
    ".src": "「定義／導出／私見」の3語しか入らない印。内容ではなくラベル",
    "#burger": "タップ領域として38px角を確保する。内容を持たない",
    ".navit .n": "条番号の桁を揃えるための最小幅。超えれば伸びる",
}


def rules(css):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)   # 注釈の中の記述は拾わない
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        yield m.group(1).strip().split("\n")[-1].strip(), m.group(2)


def main():
    css = open(os.path.join(ROOT, "app.css"), encoding="utf-8").read()
    found, bad = [], []
    for sel, body in rules(css):
        hits = []
        if re.search(r"white-space:\s*nowrap", body):
            hits.append("nowrap")
        if re.search(r"(?<!max-)(?<!min-)width:\s*\d+(px|em)", body):
            hits.append("固定幅")
        if not hits:
            continue
        key = next((k for k in ALLOW if k in sel), None)
        found.append((sel, hits, key))
        if not key:
            bad.append((sel, hits))
    print(f"  縮まない指定    : {len(found)}件")
    for sel, hits, key in found:
        mark = "  " if key else "✗ "
        why = ALLOW[key] if key else "許可簿にありません"
        print(f"    {mark}{sel[:34]:<36}{'・'.join(hits):<12}{why}")
    if bad:
        print("    内容に追随できない指定が増えています。理由を許可簿に書くか、直してください")
    return not bad


sys.exit(0 if main() else 1)
