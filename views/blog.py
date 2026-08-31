import streamlit as st

from core import prompts, ui

TOOL = "ブログ記事"

ui.page_header("📝", TOOL, "テーマとキーワードを入れるだけで、構成込みの記事を書き上げます。")
ui.require_api_key()

topic = st.text_area(
    "記事のテーマ・書きたいこと",
    height=120,
    placeholder="例: 在宅ワークで集中力を保つための時間管理術。ポモドーロ・タイマーの実体験を交えたい。",
)

col1, col2 = st.columns(2)
with col1:
    keywords = st.text_input("狙うキーワード（任意・カンマ区切り）", placeholder="在宅ワーク, 集中力, 時間管理")
    audience = st.text_input("想定読者", value="このテーマに興味のある一般の読者")
with col2:
    tone = st.selectbox(
        "文体・トーン",
        ["です・ます調（親しみやすく）", "です・ます調（丁寧・落ち着いた）", "だ・である調（硬め）", "カジュアル・口語寄り", "専門的・解説寄り"],
    )
    length = st.select_slider("目標文字数", options=[800, 1200, 1600, 2000, 3000, 4000, 5000], value=2000)

structure = st.text_area(
    "構成の希望（任意）",
    height=80,
    placeholder="例: 導入 → 課題 → 解決策3つ → 実践のコツ → まとめ",
)
extra = st.text_input("その他の指示（任意）", placeholder="例: 体験談ベースで。専門用語は使わない。")

if ui.submit_button(TOOL, "✨ 記事を書く"):
    if not topic.strip():
        st.error("記事のテーマを入力してください。", icon="⚠️")
    else:
        system, prompt = prompts.blog(topic, keywords, audience, tone, length, structure, extra)
        ui.generate(TOOL, system, prompt, title=topic.strip()[:60])

ui.result_area(TOOL, filename="blog")
