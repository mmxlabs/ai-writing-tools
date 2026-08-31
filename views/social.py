import streamlit as st

from core import prompts, ui

TOOL = "SNS投稿"

ui.page_header("📱", TOOL, "プラットフォームの作法に合わせた投稿文を、複数案まとめて作ります。")
ui.require_api_key()

topic = st.text_area(
    "投稿したい内容",
    height=140,
    placeholder="例: 新しく書いたブログ記事（在宅ワークの時間管理術）の告知をしたい。読んでほしいのは同じ悩みを持つ人。",
)

col1, col2, col3 = st.columns(3)
with col1:
    platform = st.selectbox(
        "プラットフォーム",
        ["X (Twitter)", "Instagram", "LinkedIn", "Facebook", "note / ブログ告知"],
    )
with col2:
    tone = st.selectbox("トーン", ["カジュアル", "丁寧・落ち着いた", "熱量高め", "ユーモアあり", "ビジネスライク"])
with col3:
    count = st.number_input("案の数", min_value=1, max_value=8, value=3)

col4, col5 = st.columns([1, 3])
with col4:
    hashtags = st.checkbox("ハッシュタグを付ける", value=True)
with col5:
    extra = st.text_input("その他の指示（任意）", placeholder="例: 絵文字なし / リンクを最後に置く")

if ui.submit_button(TOOL, "✨ 投稿文を作る"):
    if not topic.strip():
        st.error("投稿したい内容を入力してください。", icon="⚠️")
    else:
        system, prompt = prompts.social(platform, topic, tone, int(count), hashtags, extra)
        ui.generate(TOOL, system, prompt, title=f"[{platform}] {topic.strip()[:50]}")

ui.result_area(TOOL, filename="social")
