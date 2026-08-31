import json

import streamlit as st

from core import history, ui

ui.page_header("🕘", "履歴", "生成した文章はローカルの `data/history.jsonl` に保存されます（最新300件）。")

entries = history.load()

if not entries:
    st.info("まだ履歴がありません。いずれかのツールで文章を生成すると、ここに残ります。", icon="📭")
    st.stop()

tools = sorted({e["tool"] for e in entries})

col1, col2, col3 = st.columns([2, 3, 1])
with col1:
    selected_tools = st.multiselect("ツールで絞り込み", tools, default=[])
with col2:
    query = st.text_input("キーワード検索", placeholder="本文・タイトルを検索")
with col3:
    st.write("")
    st.write("")
    with st.popover("🗑️ 全削除", use_container_width=True):
        st.warning("履歴をすべて削除します。元に戻せません。")
        if st.button("本当に削除する", type="primary"):
            history.clear()
            st.rerun()

filtered = entries
if selected_tools:
    filtered = [e for e in filtered if e["tool"] in selected_tools]
if query.strip():
    q = query.strip().lower()
    filtered = [e for e in filtered if q in e["title"].lower() or q in e["output"].lower()]

st.caption(f"{len(filtered)} / {len(entries)} 件")

st.download_button(
    "⬇️ 全履歴を JSON でエクスポート",
    data=json.dumps(entries, ensure_ascii=False, indent=2),
    file_name="writing_history.json",
    mime="application/json",
)

st.divider()

for entry in filtered[:100]:
    label = f"**{entry['tool']}** — {entry['title'] or '(無題)'}　`{entry['created_at']}`"
    with st.expander(label):
        st.markdown(entry["output"])
        st.caption(f"モデル: `{entry.get('model', '-')}`")
        col_a, col_b = st.columns([1, 1])
        with col_a:
            st.download_button(
                "⬇️ この結果を保存",
                data=entry["output"],
                file_name=f"{entry['tool']}_{entry['id']}.md",
                mime="text/markdown",
                key=f"dl::{entry['id']}",
                use_container_width=True,
            )
        with col_b:
            if st.button("🗑️ この履歴を削除", key=f"del::{entry['id']}", use_container_width=True):
                history.delete(entry["id"])
                st.rerun()

if len(filtered) > 100:
    st.caption("※ 表示は100件までです。絞り込みを使ってください。")
