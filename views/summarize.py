import streamlit as st

from core import prompts, ui

TOOL = "要約"

ui.page_header("📄", TOOL, "長文・議事録・PDF を、目的に合った粒度でまとめます。")
ui.require_api_key()

text = ui.text_input_with_file(
    "要約したい文章",
    key="summarize",
    height=280,
    placeholder="ここに記事・議事録・レポートなどを貼り付けてください。",
)

col1, col2 = st.columns(2)
with col1:
    style = st.selectbox(
        "要約スタイル",
        [
            "箇条書き（要点を並べる）",
            "文章（つながりのある短い文章）",
            "3行まとめ",
            "見出し付きの構造化サマリー",
            "議事録形式（決定事項・ToDo・論点）",
            "小学生にもわかる平易な説明",
        ],
    )
with col2:
    length = st.selectbox("分量", ["原文の10%程度", "原文の20%程度", "200文字以内", "500文字程度", "できるだけ短く"])

focus = st.text_input(
    "特に知りたい観点（任意）",
    placeholder="例: 費用に関する記述だけを重点的に / 反対意見の論拠",
)

if ui.submit_button(TOOL, "✨ 要約する"):
    if not text.strip():
        st.error("要約する文章を入力してください。", icon="⚠️")
    elif len(text) < 50:
        st.error("文章が短すぎます。50文字以上を目安に入力してください。", icon="⚠️")
    else:
        system, prompt = prompts.summarize(text, style, length, focus)
        ui.generate(TOOL, system, prompt, title=text.strip()[:60])

ui.result_area(TOOL, filename="summary")
