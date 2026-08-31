import streamlit as st

from core import prompts, ui

TOOL = "翻訳"

ui.page_header("🌐", TOOL, "直訳ではなく、その言語として自然な文章に訳します。")
ui.require_api_key()

text = ui.text_input_with_file(
    "翻訳したい文章",
    key="translate",
    height=240,
    placeholder="ここに原文を貼り付けてください。",
)

col1, col2 = st.columns(2)
with col1:
    direction = st.selectbox(
        "翻訳方向",
        ["日本語 → 英語", "英語 → 日本語", "日本語 → 中国語（簡体字）", "中国語 → 日本語", "日本語 → 韓国語", "韓国語 → 日本語", "自動判定（相手言語へ）"],
    )
with col2:
    tone = st.selectbox(
        "文体・トーン",
        ["自然な標準表現", "ビジネスメール（フォーマル）", "カジュアル・口語", "技術文書・正確さ優先", "マーケティング・訴求重視"],
    )

glossary = st.text_area(
    "用語指定（任意）",
    height=80,
    placeholder="例: 弊社サービス名「HogeHoge」はそのまま / 「案件」は project と訳す",
)
with_notes = st.checkbox("訳注（判断が分かれた箇所の説明）を付ける", value=False)

if ui.submit_button(TOOL, "✨ 翻訳する"):
    if not text.strip():
        st.error("翻訳する文章を入力してください。", icon="⚠️")
    else:
        system, prompt = prompts.translate(text, direction, tone, glossary, with_notes)
        ui.generate(TOOL, system, prompt, title=f"[{direction}] {text.strip()[:50]}")

ui.result_area(TOOL, filename="translation")
