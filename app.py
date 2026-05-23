import streamlit as st
from chat import answer_question

st.set_page_config(
    page_title="IR Research Agent",
    page_icon="📚",
    layout="wide"
)

st.title("📚 IR Research Agent")
st.caption("Ask questions against your processed IR literature database.")

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

        if message["role"] == "assistant" and message.get("sources"):
            with st.expander("Sources used"):
                for i, source in enumerate(message["sources"], start=1):
                    st.markdown(f"**Source {i}: {source['title']}**")
                    st.markdown(f"Year: {source['year']}")
                    st.markdown(f"Journal: {source['journal']}")
                    st.markdown(f"DOI: {source['doi']}")
                    st.markdown(f"Similarity score: {source['score']}")
                    st.markdown(f"Chunk index: {source['chunk_index']}")
                    st.divider()

question = st.chat_input("Ask a research question...")

if question:
    st.session_state.messages.append({"role": "user", "content": question})

    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Retrieving, reranking, and answering..."):
            answer, sources = answer_question(question, return_sources=True)
            st.markdown(answer)

            with st.expander("Sources used"):
                for i, source in enumerate(sources, start=1):
                    st.markdown(f"**Source {i}: {source['title']}**")
                    st.markdown(f"Year: {source['year']}")
                    st.markdown(f"Journal: {source['journal']}")
                    st.markdown(f"DOI: {source['doi']}")
                    st.markdown(f"Similarity score: {source['score']}")
                    st.markdown(f"Chunk index: {source['chunk_index']}")
                    st.divider()

    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "sources": sources
    })
