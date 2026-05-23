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

question = st.chat_input("Ask a research question...")

if question:
    st.session_state.messages.append({"role": "user", "content": question})

    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Retrieving, reranking, and answering..."):
            answer = answer_question(question)
            st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
