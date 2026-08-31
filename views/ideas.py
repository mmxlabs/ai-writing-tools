import streamlit as st

from core import prompts, ui

TOOL = "アイデア出し"

ui.page_header("🧠", TOOL, "書くネタが浮かばないときの、構成案・企画のブレスト相手です。")
ui.require_api_key()

theme = st.text_area(
    "テーマ・分野",
    height=120,
    placeholder="例: フリーランスエンジニア向けの、確定申告まわりで役立つ情報",
)

col1, col2, col3 = st.columns(3)
with col1:
    kind = st.selectbox(
        "欲しいもの",
        ["ブログ記事のネタ", "記事の構成案（アウトライン）", "動画の企画", "SNS投稿のネタ", "メルマガの企画", "読者の疑問リスト（Q&Aネタ）"],
    )
with col2:
    count = st.number_input("案の数", min_value=3, max_value=15, value=6)
with col3:
    audience = st.text_input("想定読者", value="このテーマに関心のある人")

extra = st.text_input("その他の指示（任意）", placeholder="例: 初心者向けに寄せる / 競合が書いていない切り口で")

if ui.submit_button(TOOL, "✨ アイデアを出す"):
    if not theme.strip():
        st.error("テーマを入力してください。", icon="⚠️")
    else:
        system, prompt = prompts.ideas(theme, kind, int(count), audience, extra)
        ui.generate(TOOL, system, prompt, title=f"[{kind}] {theme.strip()[:50]}")

ui.result_area(TOOL, filename="ideas")
