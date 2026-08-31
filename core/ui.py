"""各ツール画面で使い回す共通UI部品。"""

from __future__ import annotations

import re
from datetime import datetime

import streamlit as st

from core import config, gemini, history, prompts

RESULT_PREFIX = "result::"


# --------------------------------------------------------------------------
# ページ共通
# --------------------------------------------------------------------------
def page_header(icon: str, title: str, description: str) -> None:
    st.title(f"{icon} {title}")
    st.caption(description)


def require_api_key() -> config.AppConfig:
    """APIキーが無ければ案内を出して以降の処理を止める。"""
    cfg = config.current()
    if not cfg.has_key:
        st.warning(
            "Gemini APIキーが未設定です。サイドバーの「設定」から入力するか、"
            "プロジェクト直下の `.env` に `GEMINI_API_KEY=...` を記述してください。",
            icon="🔑",
        )
        st.stop()
    return cfg


# --------------------------------------------------------------------------
# 生成 & 結果表示
# --------------------------------------------------------------------------
def generate(tool: str, system: str, prompt: str, *, title: str = "") -> None:
    """ストリーミング生成し、結果をセッションと履歴に保存する。"""
    cfg = config.current()
    st.subheader("生成結果")
    try:
        with st.container(border=True):
            text = st.write_stream(gemini.stream(cfg, system, prompt))
    except gemini.GeminiError as exc:
        st.error(str(exc), icon="⚠️")
        return

    text = (text or "").strip()
    if not text:
        st.error("空の応答が返ってきました。入力内容を変えて再試行してください。", icon="⚠️")
        return

    st.session_state[RESULT_PREFIX + tool] = text
    history.add(tool, title or prompt[:80], text, cfg.model)
    st.rerun()


def get_result(tool: str) -> str:
    return st.session_state.get(RESULT_PREFIX + tool, "")


def result_area(tool: str, *, filename: str = "output", allow_refine: bool = True) -> None:
    """保存済みの生成結果と、コピー / ダウンロード / 再生成のUIを描画する。"""
    text = get_result(tool)
    if not text:
        return

    st.subheader("生成結果")
    with st.container(border=True):
        st.markdown(text)

    st.caption(f"{len(text):,} 文字 ／ 約 {len(text.split())} 語")

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        st.download_button(
            "⬇️ .md で保存",
            data=text,
            file_name=f"{filename}_{datetime.now():%Y%m%d_%H%M}.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with col2:
        st.download_button(
            "⬇️ .txt で保存",
            data=text,
            file_name=f"{filename}_{datetime.now():%Y%m%d_%H%M}.txt",
            mime="text/plain",
            use_container_width=True,
        )
    with col3:
        if st.button("🗑️ 結果をクリア", use_container_width=True, key=f"clear::{tool}"):
            st.session_state.pop(RESULT_PREFIX + tool, None)
            st.rerun()

    with st.expander("📋 コピー用テキスト（右上のアイコンでコピー）"):
        st.code(text, language=None)

    if allow_refine:
        _refine_box(tool)


def _refine_box(tool: str) -> None:
    with st.expander("✏️ 修正指示を出して書き直す"):
        instruction = st.text_input(
            "どう直したいですか？",
            placeholder="例: もっとカジュアルに / 3割短く / 具体例を1つ足して",
            key=f"refine_input::{tool}",
        )
        if st.button("書き直す", key=f"refine_btn::{tool}", type="primary"):
            if not instruction.strip():
                st.warning("修正指示を入力してください。")
                return
            system, prompt = prompts.refine(get_result(tool), instruction.strip())
            generate(tool, system, prompt, title=f"[書き直し] {instruction.strip()}")


# --------------------------------------------------------------------------
# 入力補助
# --------------------------------------------------------------------------
def text_input_with_file(
    label: str,
    *,
    key: str,
    height: int = 260,
    placeholder: str = "",
) -> str:
    """テキスト直接入力 / ファイル読み込み を切り替えられる入力欄。"""
    tab_text, tab_file = st.tabs(["✍️ 直接入力", "📄 ファイルから読み込み"])

    with tab_file:
        uploaded = st.file_uploader(
            "txt / md / pdf",
            type=["txt", "md", "pdf"],
            key=f"upload::{key}",
        )
        marker = f"loaded::{key}"
        if uploaded is not None:
            # 同じファイルを毎回読み直して手入力を上書きしないようにする
            if st.session_state.get(marker) != uploaded.file_id:
                extracted = _extract_text(uploaded)
                if extracted:
                    st.session_state[f"text::{key}"] = extracted
                    st.session_state[marker] = uploaded.file_id
            if st.session_state.get(marker) == uploaded.file_id:
                st.success(f"{uploaded.name} を「直接入力」タブに読み込みました。")
        else:
            st.session_state.pop(marker, None)

    with tab_text:
        value = st.text_area(
            label,
            height=height,
            placeholder=placeholder,
            key=f"text::{key}",
        )
        if value:
            st.caption(f"入力: {len(value):,} 文字")

    return value or ""


def _extract_text(uploaded) -> str:
    name = uploaded.name.lower()
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError:
            st.error("PDFを読むには `pip install pypdf` が必要です。", icon="⚠️")
            return ""
        try:
            reader = PdfReader(uploaded)
            pages = [page.extract_text() or "" for page in reader.pages]
        except Exception as exc:
            st.error(f"PDFを読み込めませんでした: {exc}", icon="⚠️")
            return ""
        text = "\n\n".join(pages)
        if not text.strip():
            st.warning("テキストを抽出できませんでした（画像ベースのPDFの可能性があります）。", icon="⚠️")
        return _tidy(text)

    try:
        return _tidy(uploaded.getvalue().decode("utf-8"))
    except UnicodeDecodeError:
        st.error("UTF-8 のテキストファイルとして読めませんでした。", icon="⚠️")
        return ""


def _tidy(text: str) -> str:
    """余分な空行を詰める。"""
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def submit_button(tool: str, label: str = "✨ 生成する") -> bool:
    return st.button(label, type="primary", use_container_width=True, key=f"submit::{tool}")
