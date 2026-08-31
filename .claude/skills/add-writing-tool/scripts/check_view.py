"""追加・変更した画面を Streamlit の AppTest で実行し、登録漏れも含めて点検する。

使い方:
    .venv/bin/python .claude/skills/add-writing-tool/scripts/check_view.py views/minutes.py
    .venv/bin/python .claude/skills/add-writing-tool/scripts/check_view.py --all
    .venv/bin/python .claude/skills/add-writing-tool/scripts/check_view.py views/minutes.py --submit

点検する内容:
  1. 画面が例外なく描画できるか（AppTest）
  2. TOOL 文字列が他の画面と重複していないか（重複すると生成結果が混線する）
  3. app.py の PAGES に登録されているか
  4. views/home.py の TOOLS に登録されているか（忘れやすい）
  --submit を付けると生成ボタンまで押し、バリデーションとエラー処理の挙動も見る。
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]

# 本物のキーで実行して課金しないよう、ダミーを先に入れる（load_dotenv は既存の環境変数を上書きしない）。
# config._looks_like_key() を通す必要があるため 20 文字以上・半角・空白なしにしてある。
os.environ.setdefault("GEMINI_API_KEY", "dummy-key-for-apptest-0123456789")
os.environ["GEMINI_API_KEY"] = "dummy-key-for-apptest-0123456789"
sys.path.insert(0, str(ROOT))

TOOL_RE = re.compile(r'^TOOL\s*=\s*["\'](.+?)["\']', re.MULTILINE)
HOME_ENTRY_RE = re.compile(r'\(\s*"[^"]*"\s*,\s*"([^"]+)"\s*,\s*"')


def _quiet_loggers() -> None:
    """AppTest 実行中に大量に出る警告（missing ScriptRunContext など）を抑える。

    streamlit / google-genai は import 時に子ロガーへ個別にレベルを設定するので、
    親をまとめて下げるだけでは効かない。構成済みのロガーを走査して黙らせる。
    """
    for name in list(logging.root.manager.loggerDict):
        if name.startswith(("streamlit", "google", "google_genai")):
            logging.getLogger(name).setLevel(logging.ERROR)


def tool_name(path: Path) -> str:
    """view ファイルから TOOL 定数を取り出す。持たない画面（home / history）は空文字。"""
    match = TOOL_RE.search(path.read_text(encoding="utf-8"))
    return match.group(1) if match else ""


def all_views() -> list[Path]:
    return sorted(p for p in (ROOT / "views").glob("*.py") if not p.name.startswith("_"))


def check_registration(path: Path, problems: list[str]) -> None:
    """app.py / views/home.py への登録漏れを調べる。"""
    name = tool_name(path)
    app_src = (ROOT / "app.py").read_text(encoding="utf-8")
    if f"views/{path.name}" not in app_src:
        problems.append(f"app.py の PAGES に views/{path.name} が登録されていません。")

    if not name or path.name in ("home.py", "history_view.py"):
        return

    home_names = HOME_ENTRY_RE.findall((ROOT / "views" / "home.py").read_text(encoding="utf-8"))
    if name not in home_names:
        problems.append(
            f'views/home.py の TOOLS に "{name}" がありません。'
            "（ホーム画面のカード一覧から漏れます。登録漏れの定番です）"
        )


def check_tool_uniqueness(problems: list[str]) -> None:
    """TOOL 文字列の重複を全画面横断で調べる。"""
    seen: dict[str, list[str]] = {}
    for view in all_views():
        name = tool_name(view)
        if name:
            seen.setdefault(name, []).append(view.name)
    for name, files in seen.items():
        if len(files) > 1:
            problems.append(
                f'TOOL = "{name}" が重複しています（{", ".join(files)}）。'
                "session_state のキーが衝突し、片方の生成結果がもう片方の画面に出ます。"
            )


def run_view(path: Path, submit: bool) -> list[str]:
    """AppTest で 1 画面を実行し、見つかった問題を返す。"""
    from streamlit.testing.v1 import AppTest

    _quiet_loggers()

    problems: list[str] = []
    at = AppTest.from_file(str(path.resolve()), default_timeout=60)  # 相対パスは呼び出し元基準になるため絶対パスで渡す
    at.run()

    if at.exception:
        problems.append(f"描画中に例外が発生しました: {[e.value for e in at.exception]}")
        return problems

    errors = [e.value for e in at.error]
    if errors:
        problems.append(f"初期表示でエラーが出ています: {errors}")

    if submit and not problems:
        target = next((b for b in at.button if "submit::" in (b.key or "")), None)
        if target is None:
            print("    （生成ボタンが見つかりませんでした。定型どおりなら ui.submit_button() を使ってください）")
        else:
            target.click().run()
            if at.exception:
                problems.append(f"生成ボタン押下で例外が発生しました: {[e.value for e in at.exception]}")
            else:
                after = [e.value for e in at.error]
                if after:
                    print(f"    送信後のメッセージ: {after}")
                    print("    ↑ 入力が空のときのバリデーション、または API エラーの日本語表示なら正常です。")
                else:
                    problems.append(
                        "入力が空のまま生成ボタンを押してもエラーが出ませんでした。"
                        "必須項目のバリデーション（st.error）を追加してください。"
                    )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="views/ の画面を AppTest で点検する")
    parser.add_argument("views", nargs="*", help="点検する view ファイル（例: views/minutes.py）")
    parser.add_argument("--all", action="store_true", help="views/ 配下すべてを点検する")
    parser.add_argument("--submit", action="store_true", help="生成ボタンを押してエラー処理まで確認する")
    args = parser.parse_args()

    targets = all_views() if args.all else [Path(v) if Path(v).is_absolute() else ROOT / v for v in args.views]
    if not targets:
        parser.error("点検する view を指定するか、--all を付けてください。")

    all_problems: dict[str, list[str]] = {}
    check_tool_uniqueness_problems: list[str] = []
    check_tool_uniqueness(check_tool_uniqueness_problems)
    if check_tool_uniqueness_problems:
        all_problems["（全体）TOOL の重複"] = check_tool_uniqueness_problems

    for path in targets:
        if not path.exists():
            all_problems[str(path)] = ["ファイルが見つかりません。"]
            continue
        label = f"views/{path.name}"
        name = tool_name(path)
        print(f"▶ {label}" + (f'  TOOL = "{name}"' if name else "  （TOOL 定数なし）"))
        problems: list[str] = []
        check_registration(path, problems)
        problems += run_view(path, args.submit)
        if problems:
            all_problems[label] = problems
        else:
            print("    OK")

    print()
    if not all_problems:
        print("✅ 問題は見つかりませんでした。")
        return 0

    print("❌ 次の点を直してください:")
    for label, problems in all_problems.items():
        print(f"\n  [{label}]")
        for problem in problems:
            print(f"    - {problem}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
