from datetime import datetime

import streamlit as st

from core import gemini, history, prompts, ui

TOOL = "チャット"
MESSAGES_KEY = "chat_messages"

ui.page_header("💬", TOOL, "他のツールに当てはまらない相談は、ここで自由にやり取りできます。")
cfg = ui.require_api_key()

st.session_state.setdefault(MESSAGES_KEY, [])
messages: list[dict] = st.session_state[MESSAGES_KEY]

with st.sidebar:
    st.divider()
    st.subheader("💬 チャット")
    if st.button("🗑️ 会話をリセット", use_container_width=True):
        st.session_state[MESSAGES_KEY] = []
        st.rerun()
    if messages:
        transcript = "\n\n".join(
            f"### {'あなた' if m['role'] == 'user' else 'AI'}\n{m['content']}" for m in messages
        )
        st.download_button(
            "⬇️ 会話を保存",
            data=transcript,
            file_name=f"chat_{datetime.now():%Y%m%d_%H%M}.md",
            mime="text/markdown",
            use_container_width=True,
        )

if not messages:
    st.info(
        "例：「この文章のタイトルを一緒に考えて」「取引先への謝罪文、どこまで謝るべき？」など、"
        "壁打ち相手として使えます。",
        icon="💡",
    )

for message in messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if user_input := st.chat_input("メッセージを入力（Shift+Enter で改行）"):
    messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        try:
            reply = st.write_stream(gemini.stream_chat(cfg, prompts.CHAT_SYSTEM, messages))
        except gemini.GeminiError as exc:
            st.error(str(exc), icon="⚠️")
            messages.pop()
            reply = ""

    if reply:
        messages.append({"role": "assistant", "content": reply})
        history.add(TOOL, user_input[:60], reply, cfg.model)
