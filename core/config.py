"""アプリ全体の設定（APIキー・モデル・生成パラメータ）を扱うモジュール。"""

from __future__ import annotations

import os
from dataclasses import dataclass

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# 選択肢。ここに無いモデルを使いたいときは「カスタム」で直接入力できる。
MODEL_CHOICES = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.5-flash-lite",
    "カスタム（手入力）",
]

DEFAULT_MODEL = "gemini-2.5-flash"
CFG_KEY = "_app_config"


@dataclass(frozen=True)
class AppConfig:
    api_key: str
    model: str
    temperature: float
    fast_mode: bool  # 思考(thinking)を抑制して高速・低コストにする

    @property
    def has_key(self) -> bool:
        return bool(self.api_key.strip())


def key_problem(value: str) -> str:
    """APIキーとして不正な点を日本語で返す。問題なければ空文字。"""
    value = value.strip()
    if not value:
        return "APIキーが入力されていません。"
    if not value.isascii():
        return (
            "全角文字（日本語など）が含まれています。"
            "`GEMINI_API_KEY=` のような変数名ごと貼り付けていないか、"
            "`.env` のテンプレ文字列をそのまま入れていないか確認してください。"
        )
    if any(c.isspace() for c in value):
        return "空白や改行が含まれています。キー部分だけを貼り付けてください。"
    if len(value) < 20:
        return f"文字数が足りません（入力 {len(value)} 文字 / 通常は39文字程度）。途中で切れていないか確認してください。"
    return ""


def _looks_like_key(value: str) -> bool:
    """`.env` がテンプレのまま（例: 「ここにAPIキー」）の場合を未設定として扱う。"""
    return not key_problem(value)


def _key_from_environment() -> str:
    """.env / 環境変数 / secrets.toml の順にAPIキーを探す。"""
    candidates = [os.getenv("GEMINI_API_KEY", ""), os.getenv("GOOGLE_API_KEY", "")]
    try:
        candidates.append(str(st.secrets.get("GEMINI_API_KEY", "")))
    except Exception:
        pass
    for candidate in candidates:
        if _looks_like_key(candidate):
            return candidate.strip()
    return ""


def supports_thinking_off(model: str) -> bool:
    """thinking_budget=0 を指定できるのは flash 系のみ。"""
    return "flash" in model


CUSTOM_LABEL = "カスタム（手入力）"


def _model_picker(api_key: str) -> str:
    """APIから取得した実在モデルを選択肢にする。取得できなければ既定リストを使う。"""
    from core import gemini  # 循環インポートを避けるため関数内で読み込む

    available, error = gemini.list_models(api_key)
    if available:
        options = available + [CUSTOM_LABEL]
        index = options.index(DEFAULT_MODEL) if DEFAULT_MODEL in options else 0
    else:
        options = MODEL_CHOICES
        index = 0

    selected = st.selectbox("モデル", options, index=index)

    col1, col2 = st.columns([3, 1])
    if available:
        col1.caption(f"APIから取得した {len(available)} 件を表示中")
    elif api_key.strip():
        col1.caption("⚠️ 一覧を取得できませんでした（既定の候補を表示中）")
    if col2.button("🔄", help="モデル一覧を再取得する"):
        gemini.list_models.clear()
        st.rerun()

    if error and api_key.strip():
        with st.expander("エラーの詳細"):
            st.code(error, language=None)

    if selected == CUSTOM_LABEL:
        return st.text_input("モデル名", value=DEFAULT_MODEL).strip() or DEFAULT_MODEL
    return selected


def render_sidebar() -> AppConfig:
    """サイドバーに設定UIを描画し、確定した設定を返す。"""
    with st.sidebar:
        st.divider()
        st.subheader("⚙️ 設定")

        env_key = _key_from_environment()
        if env_key:
            api_key = env_key
            st.caption("APIキー: `.env` から読み込み済み ✅")
        else:
            entered = st.text_input(
                "Gemini APIキー",
                type="password",
                placeholder="AIza...",
                help="Google AI Studio (aistudio.google.com/app/apikey) で無料取得できます。"
                " `.env` に GEMINI_API_KEY を書いておけば毎回の入力は不要です。",
            ).strip()

            problem = key_problem(entered) if entered else ""
            if problem:
                # 不正なキーはAPIに送らない（全角文字だとヘッダー生成の段階で落ちるため）
                st.error(problem, icon="🔑")
                api_key = ""
            else:
                api_key = entered

        model = _model_picker(api_key)

        temperature = st.slider(
            "創造性 (temperature)",
            min_value=0.0,
            max_value=2.0,
            value=0.8,
            step=0.1,
            help="低いほど堅実・事実寄り、高いほど発想が広がります。",
        )

        if supports_thinking_off(model):
            fast_mode = st.toggle(
                "高速モード",
                value=False,
                help="内部の思考プロセスを省いて素早く出力します。短文向き。",
            )
        else:
            fast_mode = False

        st.divider()
        st.caption("個人利用向け・ローカル実行（DB / 認証なし）")

    cfg = AppConfig(
        api_key=api_key or "",
        model=model,
        temperature=temperature,
        fast_mode=fast_mode,
    )
    st.session_state[CFG_KEY] = cfg
    return cfg


def current() -> AppConfig:
    """各ページから現在の設定を取得する。"""
    cfg = st.session_state.get(CFG_KEY)
    if cfg is None:
        cfg = AppConfig(
            api_key=_key_from_environment(),
            model=DEFAULT_MODEL,
            temperature=0.8,
            fast_mode=False,
        )
    return cfg
