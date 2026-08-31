# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

Python + Streamlit + Gemini API による個人用ライティング支援ツール。**DB・認証は意図的に持たない**（ローカル単独実行が前提）ため、永続化が必要になっても DB を導入せず `data/*.jsonl` 方式を踏襲すること。

UI 文言・コード内コメント・プロンプトはすべて日本語。新規追加分も日本語で書く。

## コマンド

```bash
./run.sh                                  # 起動（.venv が無ければ自動作成＋依存インストール）
.venv/bin/python -m streamlit run app.py  # 起動（venv 作成済みの場合）
.venv/bin/python -m pip install -r requirements.txt
```

APIキーは `.env` の `GEMINI_API_KEY`（または起動後にサイドバーへ直接入力）。

### 動作確認

テストフレームワークは導入していない。検証は Streamlit の `AppTest` で行う:

```bash
.venv/bin/python -c "
import os, sys; sys.path.insert(0, os.getcwd())
os.environ['GEMINI_API_KEY'] = 'dummy'   # 未設定だと require_api_key() が st.stop() する
from streamlit.testing.v1 import AppTest
at = AppTest.from_file(os.path.join(os.getcwd(), 'views', 'blog.py'), default_timeout=60)
at.run(); print(at.exception or 'OK', [e.value for e in at.error])
"
```

`AppTest.from_file()` の相対パスは呼び出し元ファイル基準で解決されるため、**絶対パスを渡すこと**。ダミーキーでボタンを `.click().run()` すれば、API 呼び出しの異常系（`GeminiError` のハンドリング）まで確認できる。

## アーキテクチャ

4 層構成。1 画面 = `views/` の 1 ファイル。

```
views/<tool>.py   画面。入力ウィジェットを並べ、prompts で組み立て、ui に渡すだけ
  ↓
core/prompts.py   ツールごとに (system, prompt) のタプルを返す関数群
  ↓
core/ui.py        生成の実行・結果表示・履歴保存・ファイル読込の共通処理
  ↓
core/gemini.py    google-genai の薄いラッパー
```

`app.py` が `st.navigation` でページを登録し、`page.run()` の**前に** `config.render_sidebar()` を呼ぶ。サイドバーで確定した `AppConfig` は `st.session_state["_app_config"]` に入り、各 view は `config.current()` で読む（view 側が設定 UI を描画することはない）。

### ツールを追加する手順

1. `core/prompts.py` に関数を追加し、`(system, prompt)` を返す。`BASE_RULES` を必ず土台にする
2. `views/<name>.py` を作成（既存 view をテンプレートにするのが早い）
3. `app.py` の `PAGES` にカテゴリ付きで `st.Page` を登録

### view の定型

```python
TOOL = "ツール名"                      # ← このリポジトリの要。下記参照

ui.page_header("📝", TOOL, "説明")
ui.require_api_key()                   # 未設定なら st.stop()
# ... 入力ウィジェット（st.form は使わない。理由は後述）...
if ui.submit_button(TOOL, "✨ 生成する"):
    system, prompt = prompts.xxx(...)
    ui.generate(TOOL, system, prompt, title=...)
ui.result_area(TOOL, filename="xxx")
```

### 押さえるべき挙動

- **`TOOL` 文字列が識別子を兼ねる。** 生成結果の保存先 `st.session_state["result::<TOOL>"]`、各ウィジェットの `key`、履歴レコードの `tool` 欄すべてに使われる。view 間で重複させると結果が混線する。
- **`ui.generate()` は末尾で `st.rerun()` する。** そのため生成直後の実行では `ui.result_area()` に到達しない。結果は次の実行でセッションから復元されて描画される。この順序（`generate` → `result_area`）を入れ替えないこと。
- **`st.form` は使わない。** フォーム内の `st.file_uploader` は submit まで再実行を起こさず、`ui.text_input_with_file()`（アップロード内容を「直接入力」タブの `text::<key>` に流し込む方式）が機能しなくなるため、素のウィジェット + `st.button` で統一している。
- **`ui.result_area()` が書き直し機能を内包する。** `prompts.refine()` に前回結果と修正指示を渡して再生成する。view 側での実装は不要。
- **例外は `core/gemini.py` で吸収する。** SDK の例外は `_friendly()` で日本語メッセージに変換して `GeminiError` として送出し、`ui.generate()` が `st.error` で表示する。view で API 例外を握らないこと。
- **`fast_mode`（`thinking_budget=0`）は flash 系モデルのみ有効。** 判定は `config.supports_thinking_off()` に集約されており、pro 系では UI ごと出ない。
- **`config._looks_like_key()`** が `.env` のテンプレ値（`ここにAPIキー`）を未設定として弾く。20文字以上・ASCII・空白なし、という緩い判定なので、鍵の形式が変わったらここを見る。
- **履歴は追記型 JSONL。** `history.load()` は新しい順に返す。削除・上限超過時は全件書き直し（`_overwrite`）。最新 300 件で打ち切り。

### 出力品質を調整する場所

文体・構成・出力フォーマットの不満は、ほぼすべて `core/prompts.py` の `system` 文字列で解決する。`views/` や `ui.py` を触る必要はない。共通の禁止事項（前置きを書かない、事実を捏造しない等）は `BASE_RULES` にまとめてある。

## 他エージェント設定のインポート

`~/.codex/config.toml` と `~/.gemini/` が存在する。Claude Code に取り込みたい場合は `/import` と返信すると、取り込み可能な項目（MCP サーバー、スラッシュコマンド、サブエージェント、スキル、instructions）が一覧表示される。適用は一覧に表示される digest を使って `/import --yes=<digest>`。このコマンドが使えない環境では、ターミナルで `claude import` を実行する。
