"""Streamlit / LLM API アプリを、機械的に判定できる範囲で点検する。

使い方:
    python scan.py                 # カレントディレクトリを点検
    python scan.py <対象ディレクトリ>
    python scan.py --deps          # 依存ライブラリの既知の脆弱性も調べる（pip-audit が必要）

対象プロジェクトに依存しない。まず構成（フレームワーク・LLMプロバイダ・エージェント機能の有無）を
判定し、その構成に関係する項目だけを点検する。

秘密情報の実物は絶対に出力しない（見つけた場合も先頭数文字だけ伏せ字で示す）。
判定できるものだけを扱う。配置形態に応じた深刻度づけや、プロンプトインジェクションの
影響範囲といった判断は SKILL.md 側の担当。
"""

from __future__ import annotations

import argparse
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

CRITICAL, WARN, INFO = "重大", "要注意", "情報"

SKIP_DIRS = {
    ".venv", "venv", "env", ".git", "__pycache__", "node_modules",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "site-packages", ".tox", "dist", "build",
}

# コーディング支援ツールの設定・スキル置き場。アプリ本体ではないので、構成判定と
# コードの書き方の点検からは外す（ここを混ぜると、スキル定義に書かれた語をアプリの
# 実装と誤認して構成判定が丸ごと狂う）。秘密情報の走査からは外さない。
TOOLING_DIRS = {".claude", ".agents", ".cursor", ".aider", ".codex", ".gemini", ".github"}

# --------------------------------------------------------------------------
# 秘密情報のパターン。プロバイダごとに形が違うので個別に持つ。
# --------------------------------------------------------------------------
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Google / Gemini", re.compile(r"AIza[0-9A-Za-z_\-]{30,}")),
    ("OpenAI", re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{32,}")),
    ("Anthropic", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("Hugging Face", re.compile(r"hf_[A-Za-z0-9]{30,}")),
    ("AWS アクセスキー", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Slack", re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("GitHub", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
]

# 引用符を必須にしている。引用符が無いものは `api_key=os.getenv(...)` のような
# 変数参照であって秘密情報ではない。誤検知でレポートが汚れると本物の指摘が埋もれる。
HARDCODED_RE = re.compile(
    r"""(?i)\b\w*(?:api[_-]?key|secret|token|password|passwd|credential)\w*\s*[=:]\s*["']([^"'\s]{16,})["']"""
)
PLACEHOLDER_RE = re.compile(
    r"(?i)^(?:dummy|test|fake|example|sample|your|here|xxx|placeholder|change|todo|none|null|\.{3}|\*{3}|<)"
)

SECRET_FILE_NAMES = {".env", ".env.local", ".env.production", "secrets.toml", "credentials.json", "service-account.json"}
# 配布される前提のサンプル。専用の検査があるので、直書き検査では二重に報告しない。
EXAMPLE_ENV_RE = re.compile(r"^\.?env[._-](?:example|sample|template|dist)$|^\.env\.example$", re.IGNORECASE)

findings: list[tuple[str, str, str, str]] = []  # (深刻度, 分類, 見出し, 対処)


def report(level: str, category: str, title: str, fix: str = "—") -> None:
    findings.append((level, category, title, fix))


def mask(secret: str) -> str:
    """場所を特定できるだけの最小限の形にする。レポート自体が漏洩経路にならないように。"""
    return f"{secret[:4]}…（{len(secret)}文字・以下伏せ字）"


# --------------------------------------------------------------------------
# 走査の下ごしらえ
# --------------------------------------------------------------------------
class Project:
    def __init__(self, root: Path, exclude: list[Path] | None = None) -> None:
        self.root = root
        # このスキル自身は走査対象から外す。検出パターン（プロバイダ名・危険な関数名）を
        # 文字列として持っているため、含めると構成判定も指摘もすべて汚染される。
        self.exclude = [e.resolve() for e in (exclude or [])]
        self.files = self._walk()
        self.py_files = [p for p in self.files if p.suffix == ".py"]
        self.source = {p: self._read(p) for p in self.py_files}
        # アプリ本体のソースだけを集めたもの。構成判定とコード点検はこちらを使う。
        self.app_source = {
            p: text for p, text in self.source.items()
            if not (set(self.rel(p).split(os.sep)) & TOOLING_DIRS)
        }
        self.is_git = (root / ".git").exists()
        self._ignore_cache: dict[Path, bool] = {}

    def _walk(self) -> list[Path]:
        found: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in filenames:
                path = Path(dirpath) / name
                if any(self._under(path, root) for root in self.exclude):
                    continue
                try:
                    if path.stat().st_size > 2_000_000:
                        continue
                except OSError:
                    continue
                found.append(path)
        return found

    @staticmethod
    def _under(path: Path, parent: Path) -> bool:
        try:
            path.resolve().relative_to(parent)
            return True
        except ValueError:
            return False

    @staticmethod
    def _read(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return ""

    def read(self, path: Path) -> str:
        return self._read(path)

    def rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)

    def grep(self, pattern: re.Pattern[str]) -> list[tuple[str, int, str]]:
        """自前の .py から該当行を拾う。コメント行は除く。"""
        hits: list[tuple[str, int, str]] = []
        for path, text in self.app_source.items():
            for lineno, line in enumerate(text.splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                if pattern.search(line):
                    hits.append((self.rel(path), lineno, line.strip()))
        return hits

    def is_ignored(self, path: Path) -> bool:
        """git 管理外になるか。git があれば git に聞き、無ければ .gitignore を素朴に照合する。"""
        if path in self._ignore_cache:
            return self._ignore_cache[path]
        result = self._compute_ignored(path)
        self._ignore_cache[path] = result
        return result

    def _compute_ignored(self, path: Path) -> bool:
        if self.is_git:
            try:
                proc = subprocess.run(
                    ["git", "check-ignore", "-q", str(path)],
                    cwd=self.root, capture_output=True, timeout=15,
                )
                return proc.returncode == 0
            except (OSError, subprocess.SubprocessError):
                pass
        gitignore = self.root / ".gitignore"
        if not gitignore.exists():
            return False
        rel = self.rel(path)
        for raw in self._read(gitignore).splitlines():
            entry = raw.strip().rstrip("/")
            if not entry or entry.startswith("#"):
                continue
            if entry == rel or rel.startswith(entry + "/") or Path(rel).name == entry:
                return True
            if entry.startswith("*") and rel.endswith(entry.lstrip("*")):
                return True
        return False


# --------------------------------------------------------------------------
# 構成の判定 — どの点検が関係するかを決める
# --------------------------------------------------------------------------
PROVIDER_HINTS = {
    "OpenAI": r"\bimport openai\b|from openai\b|OPENAI_API_KEY",
    "Anthropic": r"\bimport anthropic\b|from anthropic\b|ANTHROPIC_API_KEY",
    "Google Gemini": r"google\.genai|google\.generativeai|GEMINI_API_KEY|GOOGLE_API_KEY",
    "Azure OpenAI": r"AzureOpenAI|AZURE_OPENAI",
    "AWS Bedrock": r"bedrock-runtime|BedrockChat",
    "Cohere": r"\bimport cohere\b|COHERE_API_KEY",
    "Mistral": r"mistralai",
    "Groq": r"\bfrom groq\b|GROQ_API_KEY",
    "Ollama（ローカル）": r"\bollama\b",
    "LiteLLM": r"\blitellm\b",
}
FRAMEWORK_HINTS = {
    "Streamlit": r"\bimport streamlit\b|from streamlit\b",
    "Gradio": r"\bimport gradio\b",
    "FastAPI": r"\bfrom fastapi\b|\bimport fastapi\b",
    "Flask": r"\bfrom flask\b|\bimport flask\b",
    "LangChain": r"\blangchain\b",
    "LlamaIndex": r"llama_index",
}
# エージェント／ツール実行の痕跡。これがあるとプロンプトインジェクションの深刻度が跳ね上がる。
AGENT_HINTS = {
    "ツール定義": r"@tool\b|Tool\(|tools\s*=\s*\[|tool_choice|function_call|FunctionDeclaration",
    "エージェント実行": r"AgentExecutor|create_react_agent|initialize_agent|create_tool_calling_agent",
    "コード実行ツール": r"PythonREPL|python_repl|ShellTool|BashTool|CodeInterpreter|exec_python",
}


def detect_stack(project: Project) -> dict:
    blob = "\n".join(project.app_source.values())
    for name in ("requirements.txt", "pyproject.toml", "Pipfile", "environment.yml"):
        path = project.root / name
        if path.exists():
            blob += "\n" + project.read(path)

    def matched(hints: dict[str, str]) -> list[str]:
        return [label for label, pattern in hints.items() if re.search(pattern, blob)]

    return {
        "frameworks": matched(FRAMEWORK_HINTS),
        "providers": matched(PROVIDER_HINTS),
        "agents": matched(AGENT_HINTS),
        "uploads": bool(re.search(r"file_uploader|UploadFile|request\.files", blob)),
    }


# --------------------------------------------------------------------------
# A. 秘密情報の露出
# --------------------------------------------------------------------------
def check_secret_files(project: Project) -> None:
    for path in project.files:
        if path.name not in SECRET_FILE_NAMES:
            continue
        rel = project.rel(path)
        mode = path.stat().st_mode
        if mode & (stat.S_IRGRP | stat.S_IROTH):
            report(
                WARN, "秘密情報",
                f"`{rel}` が同一マシンの他ユーザーから読める権限です（{stat.filemode(mode)}）。"
                "秘密情報が平文で入っているファイルは、所有者だけが読める権限にしてください。",
                f"chmod 600 {rel}",
            )
        if not project.is_ignored(path):
            report(
                CRITICAL, "秘密情報",
                f"`{rel}` が git 管理から除外されていません。コミットすると秘密情報が履歴に残ります。",
                f'echo "{rel}" >> .gitignore',
            )

    for example in (p for p in project.files if EXAMPLE_ENV_RE.match(p.name)):
        body = project.read(example)
        for label, pattern in SECRET_PATTERNS:
            for match in pattern.findall(body):
                report(
                    CRITICAL, "秘密情報",
                    f"`{project.rel(example)}` に本物の {label} キーらしき文字列が入っています"
                    f"（{mask(match)}）。サンプルファイルは配布・コミットされる前提です。",
                    "プレースホルダに戻し、キーを再発行してください。",
                )


def check_hardcoded_secrets(project: Project) -> None:
    for path in project.files:
        if path.name in SECRET_FILE_NAMES:
            continue  # 秘密情報を置くためのファイルなので正常
        if EXAMPLE_ENV_RE.match(path.name):
            continue  # check_secret_files() で個別に見ている
        text = project.read(path)
        if not text:
            continue
        rel = project.rel(path)

        for label, pattern in SECRET_PATTERNS:
            for match in pattern.findall(text):
                report(
                    CRITICAL, "秘密情報",
                    f"`{rel}` に {label} のキーらしき文字列が入っています（{mask(match)}）。",
                    "該当箇所を削除し、キーを再発行したうえで環境変数から読む形に直してください。"
                    + ("なお git 管理下なので、履歴からも消す必要があります。" if project.is_git and not project.is_ignored(path) else ""),
                )

        if path.suffix in (".py", ".toml", ".yaml", ".yml", ".json", ".ipynb"):
            for match in HARDCODED_RE.findall(text):
                if PLACEHOLDER_RE.match(match) or any(p.match(match) for _, p in SECRET_PATTERNS):
                    continue  # プレースホルダと、上で報告済みのものは除く
                if match.startswith(("os.", "st.", "$", "{")) or "getenv" in match:
                    continue
                report(
                    CRITICAL, "秘密情報",
                    f"`{rel}` に秘密情報の直書きらしき箇所があります（{mask(match)}）。",
                    "環境変数（.env）から読む形に直し、値を再発行してください。",
                )


def check_git_tracking(project: Project) -> None:
    if not project.is_git:
        report(INFO, "秘密情報", "git リポジトリではないため、コミット済みの秘密情報の点検は省略しました。")
        return
    try:
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=project.root, capture_output=True, text=True, timeout=30
        ).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        return
    for entry in tracked:
        name = Path(entry).name
        if name in SECRET_FILE_NAMES:
            report(
                CRITICAL, "秘密情報",
                f"`{entry}` が git の管理下に入っています。履歴に残るため .gitignore に足すだけでは消えません。",
                f"git rm --cached '{entry}' を実行し、既に push 済みなら該当のキーを必ず再発行してください。",
            )


DATA_SUFFIXES = {".jsonl", ".db", ".sqlite", ".sqlite3", ".csv", ".log"}
DATA_DIR_HINTS = ("data", "history", "output", "outputs", "generated", "logs", "uploads", "生成", "出力")


def check_user_data_exposure(project: Project) -> None:
    """会話履歴・生成物・アップロードファイルが git に載る状態になっていないか。

    LLM アプリではここに利用者が貼り付けた文章がそのまま溜まる。
    設定ファイルより機微になりうるのに、.gitignore の設計から漏れやすい。
    """
    at_risk: list[str] = []
    for path in project.files:
        rel = project.rel(path)
        parts = {p.lower() for p in Path(rel).parts[:-1]}
        in_data_dir = any(hint in part for part in parts for hint in DATA_DIR_HINTS)
        if not (in_data_dir or path.suffix.lower() in DATA_SUFFIXES):
            continue
        if path.suffix in (".py", ".toml", ".cfg", ".ini", ".yaml", ".yml"):
            continue  # コードと設定は利用者データではない
        if path.suffix == ".md" and not in_data_dir:
            continue  # README 等の文書は除く。生成物ディレクトリ配下の .md は対象に残す
        if not project.is_ignored(path):
            at_risk.append(rel)

    if at_risk:
        shown = at_risk[:8]
        more = f"（ほか {len(at_risk) - len(shown)} 件）" if len(at_risk) > len(shown) else ""
        report(
            WARN, "利用者データ",
            "利用者が入力した文章や生成物が残るファイルが git 管理から除外されていません: "
            + ", ".join(f"`{p}`" for p in shown) + more
            + "。LLM アプリではここに機密文書がそのまま溜まります。",
            "該当するディレクトリを .gitignore に追加してください。",
        )


# --------------------------------------------------------------------------
# B. ネットワークへの露出（Streamlit 固有）
# --------------------------------------------------------------------------
def check_streamlit_exposure(project: Project) -> None:
    config = project.root / ".streamlit" / "config.toml"
    body = project.read(config) if config.exists() else ""

    address = re.search(r'^\s*address\s*=\s*["\']([^"\']*)["\']', body, re.MULTILINE)
    if address is None:
        report(
            WARN, "公開範囲",
            "`.streamlit/config.toml` に `server.address` の指定がありません。Streamlit は既定で"
            "全インターフェースに待ち受けるため、同一ネットワークの誰でもブラウザから開けます。"
            "アプリ側に認証が無い場合、APIキーの利用と保存済みデータの閲覧を許すことになります。",
            'ローカル利用のみなら .streamlit/config.toml に [server] address = "localhost" を追加してください。',
        )
    elif address.group(1) in ("0.0.0.0", "", "::"):
        report(
            WARN, "公開範囲",
            f'`server.address = "{address.group(1)}"` は外部からの接続を受け付ける設定です。'
            "意図的な公開ならば、認証の有無とあわせて評価してください。",
            'ローカル利用のみなら address = "localhost" に変更してください。',
        )

    for option, why in (
        ("enableXsrfProtection", "他サイトからの操作を防ぐ仕組み"),
        ("enableCORS", "他オリジンからのアクセス制限"),
    ):
        if re.search(rf"^\s*{option}\s*=\s*false", body, re.MULTILINE):
            report(WARN, "公開範囲", f"`{option} = false` になっています（{why}を無効化しています）。",
                   f"{option} を既定（true）に戻してください。")

    if re.search(r"^\s*enableStaticServing\s*=\s*true", body, re.MULTILINE):
        report(WARN, "公開範囲",
               "`enableStaticServing = true` により `static/` 以下が無認証で配信されます。",
               "配信対象に秘密情報や利用者データが含まれていないか確認してください。")

    secrets_toml = project.root / ".streamlit" / "secrets.toml"
    if secrets_toml.exists() and not project.is_ignored(secrets_toml):
        report(CRITICAL, "秘密情報", "`.streamlit/secrets.toml` が git 管理から除外されていません。",
               'echo ".streamlit/secrets.toml" >> .gitignore')


# --------------------------------------------------------------------------
# C. 危険なコードの書き方
# --------------------------------------------------------------------------
DANGEROUS: list[tuple[re.Pattern[str], str, str, str, str]] = [
    (re.compile(r"\bshell\s*=\s*True"), CRITICAL, "コード実行",
     "subprocess を shell=True で呼んでいます。文字列に入力が混ざるとコマンドを実行されます。",
     "引数をリストで渡し、shell=True を外してください。"),
    (re.compile(r"\b(?:os\.system|os\.popen)\s*\("), CRITICAL, "コード実行",
     "os.system / os.popen でシェルを起動しています。",
     "subprocess.run に引数リストで渡す形に置き換えてください。"),
    (re.compile(r"(?<![\w.])(?:eval|exec)\s*\("), CRITICAL, "コード実行",
     "eval / exec で文字列をコードとして実行しています。LLM の出力や利用者入力が届くと任意コード実行になります。",
     "辞書引きなど、実行を伴わない方法に置き換えてください。"),
    (re.compile(r"pickle\.loads?\s*\("), WARN, "コード実行",
     "pickle で読み込んでいます。ファイルを差し替えられると任意のコードが動きます。",
     "JSON など、実行を伴わない形式に置き換えてください。"),
    (re.compile(r"yaml\.load\((?!.*(?:SafeLoader|safe_load))"), WARN, "コード実行",
     "yaml.load を SafeLoader なしで使っています。", "yaml.safe_load を使ってください。"),
    (re.compile(r"allow_dangerous_deserialization\s*=\s*True"), CRITICAL, "コード実行",
     "ベクトルストア等の危険な逆シリアル化を明示的に許可しています。索引ファイルを差し替えられると任意コード実行になります。",
     "信頼できる索引のみを読む設計に変え、可能ならこの指定を外してください。"),
    (re.compile(r"\bverify\s*=\s*False"), WARN, "通信",
     "TLS 証明書の検証を無効化しています。通信内容（APIキーを含む）を傍受・改ざんされる恐れがあります。",
     "verify=False を外してください。社内 CA が理由なら証明書を指定してください。"),
    (re.compile(r"unsafe_allow_html\s*=\s*True"), WARN, "出力の扱い",
     "LLM の出力や読み込んだ文書を HTML として解釈させています。入力に仕込まれたタグが動きます。",
     "unsafe_allow_html を外すか、描画前にサニタイズしてください。"),
    (re.compile(r"st\.exception\s*\("), WARN, "情報漏洩",
     "st.exception でスタックトレースを画面に出しています。内部構造や、例外文に含まれる秘密情報が露出します。",
     "利用者向けの短いメッセージに置き換え、詳細はログに送ってください。"),
    (re.compile(r"st\.(?:write|json)\s*\(\s*(?:dict\()?st\.session_state"), CRITICAL, "情報漏洩",
     "session_state をそのまま画面に出しています。APIキーを保持していればそれも表示されます。",
     "必要な項目だけを個別に表示してください。"),
    (re.compile(r"(?i)(?:print|st\.(?:write|code|json|text)|logging\.\w+|logger\.\w+)\s*\([^)]*\b\w*(?:api[_-]?key|secret|token|password)\w*\b"),
     CRITICAL, "情報漏洩",
     "秘密情報を画面またはログに出力しています。",
     "出力対象から外してください。"),
]

# 例外の中身を画面に流している箇所。それ自体は正常なことが多いので、人が見る候補として挙げるだけ。
EXC_TO_UI_RE = re.compile(
    # 変数名の先頭から一致させる。これが無いと "True" の末尾の e を例外変数と誤認する。
    r"st\.(?:error|warning|info|success|write|markdown|toast)\s*\([^)]*(?<![\w.])(?:exc|e|err|error|ex)\b"
)


def check_code_patterns(project: Project) -> None:
    for pattern, level, category, why, fix in DANGEROUS:
        for rel, lineno, _ in project.grep(pattern):
            report(level, category, f"`{rel}:{lineno}` {why}", fix)

    hits = [(rel, lineno) for rel, lineno, _ in project.grep(EXC_TO_UI_RE)]
    if hits:
        shown = ", ".join(f"`{rel}:{lineno}`" for rel, lineno in hits[:10])
        more = f" ほか {len(hits) - 10} 件" if len(hits) > 10 else ""
        report(
            INFO, "情報漏洩",
            f"例外の内容を画面に表示している箇所があります: {shown}{more}。"
            "SDK の例外文にはリクエスト内容やAPIキーが含まれることがあるため、"
            "伏せ字処理を通しているか確認してください（機械判定では可否を決められません）。",
            "秘密情報を伏せる処理を挟むか、利用者向けの定型文に置き換えてください。",
        )


def check_agent_risk(project: Project, stack: dict) -> None:
    if not stack["agents"]:
        return
    report(
        WARN, "プロンプトインジェクション",
        "LLM にツール実行の権限を与えている痕跡があります（" + " / ".join(stack["agents"]) + "）。"
        "利用者が読み込ませた文書に指示が仕込まれていると、モデルがそれに従ってツールを実行しえます。"
        "ツールがファイル・シェル・ネットワークに触れる場合、影響は出力の改ざんに留まりません。",
        "各ツールの権限範囲を洗い出し、破壊的な操作は人の承認を挟む設計になっているか確認してください。",
    )


# --------------------------------------------------------------------------
# D. 依存関係
# --------------------------------------------------------------------------
def check_dependencies(project: Project) -> None:
    python = project.root / ".venv" / "bin" / "python"
    interpreter = str(python) if python.exists() else sys.executable
    try:
        result = subprocess.run(
            [interpreter, "-m", "pip_audit", "--progress-spinner", "off"],
            cwd=project.root, capture_output=True, text=True, timeout=300,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        report(INFO, "依存関係", f"pip-audit を実行できませんでした: {exc}")
        return
    if "No module named" in result.stderr:
        report(INFO, "依存関係", "pip-audit が未導入のため、依存ライブラリの既知の脆弱性は調べていません。",
               f"{interpreter} -m pip install pip-audit")
    elif result.returncode == 0:
        report(INFO, "依存関係", "依存ライブラリに既知の脆弱性は見つかりませんでした（pip-audit）。")
    else:
        report(WARN, "依存関係", "依存ライブラリに既知の脆弱性があります:\n" + (result.stdout or result.stderr).strip(),
               "報告されたバージョンまで引き上げてください。")


# --------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Streamlit / LLM API アプリの機械点検")
    parser.add_argument("path", nargs="?", default=".", help="点検対象のディレクトリ（既定: カレント）")
    parser.add_argument("--deps", action="store_true", help="依存ライブラリの既知の脆弱性も調べる")
    args = parser.parse_args()

    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"ディレクトリが見つかりません: {root}", file=sys.stderr)
        return 2

    # スキャナ自身が置かれているスキルディレクトリは、対象内にあっても除外する
    project = Project(root, exclude=[Path(__file__).resolve().parents[1]])
    stack = detect_stack(project)

    print(f"点検対象: {root}")
    print(f"  フレームワーク: {' / '.join(stack['frameworks']) or '判定できず'}")
    print(f"  LLM プロバイダ: {' / '.join(stack['providers']) or '判定できず'}")
    print(f"  エージェント機能: {' / '.join(stack['agents']) or 'なし'}")
    print(f"  ファイルアップロード: {'あり' if stack['uploads'] else 'なし'}")
    print(f"  git 管理: {'あり' if project.is_git else 'なし'}")
    print(f"  Python ファイル数: {len(project.app_source)}（アプリ本体）\n")

    check_secret_files(project)
    check_hardcoded_secrets(project)
    check_git_tracking(project)
    check_user_data_exposure(project)
    if "Streamlit" in stack["frameworks"]:
        check_streamlit_exposure(project)
    check_code_patterns(project)
    check_agent_risk(project, stack)
    if args.deps:
        check_dependencies(project)

    counts = {CRITICAL: 0, WARN: 0, INFO: 0}
    seen: set[tuple[str, str]] = set()
    for level in (CRITICAL, WARN, INFO):
        group = [f for f in findings if f[0] == level and not (
            (f[0], f[2]) in seen or seen.add((f[0], f[2]))
        )]
        counts[level] = len(group)
        if not group:
            continue
        icon = {CRITICAL: "🔴", WARN: "🟡", INFO: "🔵"}[level]
        print(f"{icon} {level}（{len(group)}件）")
        for _, category, title, fix in group:
            print(f"  - [{category}] {title}")
            if fix != "—":
                print(f"    → 対処: {fix}")
        print()

    print(f"合計: 重大 {counts[CRITICAL]} / 要注意 {counts[WARN]} / 情報 {counts[INFO]}")
    print("\n※ 機械判定の結果です。深刻度は配置形態によって変わります。")
    print("  SKILL.md の手順に従って配置形態を確定させ、人が判断する観点とあわせてレポートにまとめてください。")
    return 1 if (counts[CRITICAL] or counts[WARN]) else 0


if __name__ == "__main__":
    sys.exit(main())
