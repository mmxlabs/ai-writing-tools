import streamlit as st

from core import prompts, ui

TOOL = "タイトル・コピー"

ui.page_header("💡", TOOL, "記事タイトルやキャッチコピーを、狙いの違う複数案で出します。")
ui.require_api_key()

content = st.text_area(
    "対象の内容（記事の要旨・商品の説明など）",
    height=180,
    placeholder="例: 在宅ワークで集中が続かない人向けに、ポモドーロ・テクニックの実践方法を紹介する記事。",
)

col1, col2, col3 = st.columns(3)
with col1:
    kind = st.selectbox(
        "作りたいもの",
        ["ブログ記事のタイトル", "YouTube動画のタイトル", "メールの件名", "キャッチコピー", "商品名・サービス名", "見出し（記事内の中見出し）", "プレゼンのタイトル"],
    )
with col2:
    tone = st.selectbox("トーン", ["王道・わかりやすく", "インパクト重視", "誠実・落ち着いた", "好奇心をくすぐる", "ベネフィット訴求"])
with col3:
    count = st.number_input("案の数", min_value=3, max_value=20, value=10)

extra = st.text_input("その他の指示（任意）", placeholder="例: 30文字以内 / 煽りすぎない / 数字を入れる")

if ui.submit_button(TOOL, "✨ 案を出す"):
    if not content.strip():
        st.error("対象の内容を入力してください。", icon="⚠️")
    else:
        system, prompt = prompts.headline(content, kind, int(count), tone, extra)
        ui.generate(TOOL, system, prompt, title=f"[{kind}] {content.strip()[:50]}")

ui.result_area(TOOL, filename="headline")
