# 公認野球規則 年度版データベース
#
#   マスターは years/<年>/text/*.md（人が直接編集してよい）
#   差分はビューアがブラウザ側で計算するので、事前計算はしない

YEARS := $(notdir $(wildcard years/20*))
PORT  ?= 8000

.PHONY: all data serve add check sqlite clean

all: data

## text/*.md → data/rules.json, rules.jsonl と manifest.json
data:
	python3 build/2_md2data.py

## 全文検索用のSQLite（1年あたり2.8MBと重いので既定では作らない）
sqlite:
	python3 build/2_md2data.py --sqlite

## ローカルで開く（file:// では動かないため）
serve:
	@echo "→ http://localhost:$(PORT)/"
	@python3 -m http.server $(PORT)

## 新年度を取り込む:  make add YEAR=2027
add:
	@test -n "$(YEAR)" || (echo "YEAR= を指定してください" && exit 1)
	python3 build/1_import.py $(YEAR)
	python3 build/2_md2data.py
	@echo
	@echo "次に build/3_official.py の OFFICIAL へ公式改正文書を追記し、"
	@echo "  python3 build/verify_official.py <前年> $(YEAR)"
	@echo "を実行すると、公式との照合結果が差分に載ります。"

## 取りこぼし・文字化け・参照・公式照合をまとめて検査
check:
	python3 build/check.py

clean:
	rm -rf years/*/data official manifest.json

## 手元でgrep/jqしたいとき用（配布はしない）
jsonl:
	python3 build/2_md2data.py --jsonl
