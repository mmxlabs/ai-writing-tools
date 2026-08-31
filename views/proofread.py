import streamlit as st

from core import prompts, ui

TOOL = "校正・リライト"

ui.page_header("🔍", TOOL, "誤字脱字のチェックから、文体を変える書き換えまで対応します。")
ui.require_api_key()

text = ui.text_input_with_file(
    "チェック・書き換えしたい文章",
    key="proofread",
    height=280,
    placeholder="ここに文章を貼り付けてください。",
)

col1, col2 = st.columns(2)
with col1:
    mode = st.selectbox(
        "処理内容",
        [
            "誤字脱字・文法チェック（意味は変えない）",
            "読みやすさ改善（冗長な表現を整理）",
            "文体変換（指定のトーンに書き換え）",
            "簡潔化（意味を保ったまま短く）",
            "肉付け（具体例を足して詳しく）",
            "ビジネス文書として適切に整える",
        ],
    )
with col2:
    tone = st.selectbox(
        "目指す文体",
        ["元の文体を維持", "です・ます調（丁寧）", "だ・である調", "カジュアル・親しみやすく", "フォーマル・硬め", "簡潔・端的"],
    )

extra = st.text_input("その他の指示（任意）", placeholder="例: 専門用語は残す / 1文を40文字以内に")

if ui.submit_button(TOOL, "✨ 校正する"):
    if not text.strip():
        st.error("対象の文章を入力してください。", icon="⚠️")
    else:
        system, prompt = prompts.proofread(text, mode, tone, extra)
        ui.generate(TOOL, system, prompt, title=text.strip()[:60])

ui.result_area(TOOL, filename="proofread")
