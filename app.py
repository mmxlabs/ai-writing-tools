"""AI ライティングツール — Streamlit エントリーポイント。

起動:  streamlit run app.py
"""

import streamlit as st

from core import config

st.set_page_config(
    page_title="AI ライティングツール",
    page_icon="✍️",
    layout="centered",
    initial_sidebar_state="expanded",
)

PAGES = {
    "ホーム": [
        st.Page("views/home.py", title="ホーム", icon="🏠", default=True),
    ],
    "書く": [
        st.Page("views/blog.py", title="ブログ記事", icon="📝"),
        st.Page("views/email.py", title="メール返信", icon="📧"),
        st.Page("views/social.py", title="SNS投稿", icon="📱"),
        st.Page("views/headline.py", title="タイトル・コピー", icon="💡"),
    ],
    "整える": [
        st.Page("views/summarize.py", title="要約", icon="📄"),
        st.Page("views/proofread.py", title="校正・リライト", icon="🔍"),
        st.Page("views/translate.py", title="翻訳", icon="🌐"),
    ],
    "考える": [
        st.Page("views/ideas.py", title="アイデア出し", icon="🧠"),
        st.Page("views/chat.py", title="チャット", icon="💬"),
    ],
    "記録": [
        st.Page("views/history_view.py", title="履歴", icon="🕘"),
    ],
}

page = st.navigation(PAGES)
config.render_sidebar()
page.run()
