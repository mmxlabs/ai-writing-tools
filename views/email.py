import streamlit as st

from core import prompts, ui

TOOL = "メール返信"

ui.page_header("📧", TOOL, "受信メールを貼り付け、伝えたいことを一言添えるだけで返信文ができます。")
ui.require_api_key()

received = st.text_area(
    "受信したメール本文",
    height=220,
    placeholder="お世話になっております。◯◯株式会社の△△です。先日ご相談いたしました件ですが……",
)

intent = st.text_area(
    "返信で伝えたいこと（箇条書きでOK）",
    height=100,
    placeholder="・日程は来週火曜の午後なら可能\n・資料は明日中に送る\n・見積もりは再検討が必要と伝える",
)

col1, col2, col3 = st.columns(3)
with col1:
    recipient = st.text_input("宛先（相手）", placeholder="◯◯株式会社 △△様")
with col2:
    sender = st.text_input("差出人（自分）", placeholder="山田 太郎")
with col3:
    tone = st.selectbox(
        "丁寧さ・トーン",
        ["ビジネス（標準）", "ビジネス（かなり丁寧・社外役員クラス）", "ビジネス（ややカジュアル・社内）", "友人・知人向け（カジュアル）"],
    )

col4, col5 = st.columns(2)
with col4:
    length = st.selectbox("長さ", ["標準（200〜300文字）", "簡潔（100文字前後）", "詳しめ（400文字以上）"])
with col5:
    extra = st.text_input("その他の指示（任意）", placeholder="例: 締め切り延長のお願いを丁寧に")

if ui.submit_button(TOOL, "✨ 返信文を作る"):
    if not received.strip() and not intent.strip():
        st.error("受信メール本文か、伝えたいことのどちらかは入力してください。", icon="⚠️")
    else:
        system, prompt = prompts.email_reply(received, intent, tone, sender, recipient, length, extra)
        ui.generate(TOOL, system, prompt, title=(intent or received).strip()[:60])

ui.result_area(TOOL, filename="email")
