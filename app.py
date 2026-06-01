import streamlit as st
from chat import answer_question, generate_landscape_report

st.set_page_config(
    page_title="IR Research Agent",
    page_icon="📚",
    layout="wide"
)

st.title("📚 IR Research Agent")
st.caption("Ask questions against your processed IR literature database.")

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filter sources")
    st.caption("Narrow the database before searching. Leave blank to search everything.")

    year_min = st.number_input("Year from", min_value=2000, max_value=2026, value=2024, step=1)
    year_max = st.number_input("Year to", min_value=2000, max_value=2026, value=2026, step=1)
    journal_filter = st.text_input("Journal (partial match)", placeholder="e.g. International Security")
    geo_filter = st.text_input("Geographic focus (partial match)", placeholder="e.g. China")
    method_filter = st.text_input("Method (partial match)", placeholder="e.g. case study")

    filters_active = any([journal_filter, geo_filter, method_filter])
    year_filtered = year_min != 2024 or year_max != 2026

    if filters_active or year_filtered:
        st.info("Filters active — search is narrowed.")
    else:
        st.caption("No filters active — searching full database.")

    st.divider()

    st.subheader("Research Landscape")
    st.caption("Generate a detailed report on topics, methods, datasets, geographic coverage, and gaps across your entire database.")

    if st.button("Generate Research Landscape", use_container_width=True):
        st.session_state["generate_landscape"] = True

# Build filters dict
filters = {
    "year_min": year_min,
    "year_max": year_max,
    "journal": journal_filter or None,
    "geographic_focus": geo_filter or None,
    "method": method_filter or None,
}

# ── Landscape report ───────────────────────────────────────────────────────────
if st.session_state.get("generate_landscape"):
    st.session_state["generate_landscape"] = False

    with st.spinner("Analyzing your research database — this may take a moment..."):
        report = generate_landscape_report(filters=filters if (filters_active or year_filtered) else None)

    with st.expander("📊 Research Landscape Report", expanded=True):
        st.markdown(report)

    # Also add to chat history so it's scrollable later
    st.session_state.setdefault("messages", []).append({
        "role": "assistant",
        "content": report,
        "sources": [],
        "is_landscape": True,
    })

# ── Chat interface ─────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant" and message.get("sources") and not message.get("is_landscape"):
            with st.expander("Sources used"):
                for i, source in enumerate(message["sources"], start=1):
                    st.markdown(f"**Source {i}: {source['title']}**")
                    st.markdown(f"Year: {source['year']}")
                    st.markdown(f"Journal: {source['journal']}")
                    st.markdown(f"DOI: {source['doi']}")
                    if source.get("geographic_focus"):
                        st.markdown(f"Geographic focus: {source['geographic_focus']}")
                    if source.get("method"):
                        st.markdown(f"Method: {source['method']}")
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
            answer, sources = answer_question(question, return_sources=True, filters=filters)
            st.markdown(answer)
            with st.expander("Sources used"):
                for i, source in enumerate(sources, start=1):
                    st.markdown(f"**Source {i}: {source['title']}**")
                    st.markdown(f"Year: {source['year']}")
                    st.markdown(f"Journal: {source['journal']}")
                    st.markdown(f"DOI: {source['doi']}")
                    if source.get("geographic_focus"):
                        st.markdown(f"Geographic focus: {source['geographic_focus']}")
                    if source.get("method"):
                        st.markdown(f"Method: {source['method']}")
                    st.markdown(f"Similarity score: {source['score']}")
                    st.markdown(f"Chunk index: {source['chunk_index']}")
                    st.divider()

    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "sources": sources,
        "is_landscape": False,
    })
