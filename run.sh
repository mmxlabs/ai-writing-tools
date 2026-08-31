#!/bin/bash
# AI ライティングツールを起動する
cd "$(dirname "$0")" || exit 1

if [ ! -d .venv ]; then
  echo "初回セットアップ: 仮想環境を作成します..."
  python3 -m venv .venv || exit 1
  .venv/bin/python -m pip install --upgrade pip -q
  .venv/bin/python -m pip install -r requirements.txt || exit 1
fi

exec .venv/bin/python -m streamlit run app.py
