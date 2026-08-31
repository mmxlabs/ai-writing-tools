import streamlit as st

from core import config, history

st.title("✍️ AI ライティングツール")
st.caption("Gemini API を使った、個人用の文章作成ツール集です。左のメニューから使いたい機能を選んでください。")

cfg = config.current()
if not cfg.has_key:
    st.warning(
        "はじめに Gemini APIキーを設定してください。\n\n"
        "1. https://aistudio.google.com/app/apikey でキーを取得\n"
        "2. プロジェクト直下の `.env` に `GEMINI_API_KEY=取得したキー` と記述（または左サイドバーに入力）",
        icon="🔑",
    )
else:
    st.success(f"準備完了 — 使用モデル: `{cfg.model}`", icon="✅")

st.divider()

TOOLS = [
    ("📝", "ブログ記事", "テーマとキーワードから、見出し付きの記事を丸ごと執筆します。"),
    ("📧", "メール返信", "受け取ったメールを貼り付けるだけで、返信文の下書きを作ります。"),
    ("📄", "要約", "長文・PDFを、目的に合わせた粒度で要約します。"),
    ("🔍", "校正・リライト", "誤字脱字の修正から、文体まるごとの書き換えまで。"),
    ("📱", "SNS投稿", "X / Instagram / LinkedIn 向けの投稿文を複数案作ります。"),
    ("💡", "タイトル・コピー", "記事タイトルやキャッチコピーを、狙い付きで一覧化します。"),
    ("🌐", "翻訳", "日英の自然な翻訳。文体指定と用語集に対応します。"),
    ("🧠", "アイデア出し", "記事構成やネタのブレインストーミング相手になります。"),
    ("💬", "チャット", "上のどれにも当てはまらない相談は、こちらで自由に。"),
]

cols = st.columns(3)
for i, (icon, name, desc) in enumerate(TOOLS):
    with cols[i % 3]:
        with st.container(border=True):
            st.markdown(f"### {icon} {name}")
            st.caption(desc)

st.divider()

entries = history.load()
st.subheader("🕘 最近の生成")
if not entries:
    st.caption("まだ履歴はありません。")
else:
    for entry in entries[:5]:
        st.markdown(f"- `{entry['created_at']}` **{entry['tool']}** — {entry['title']}")
    st.caption("すべての履歴は左メニューの「履歴」から見られます。")
