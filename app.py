import streamlit as st
from chat import answer_question, generate_landscape_report, generate_gap_analysis

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

    st.divider()

    st.subheader("Gap Analysis")
    st.caption("Describe your research interest and get a structured analysis of topical, methodological, geographic, and theoretical gaps in the literature.")

    gap_input = st.text_area(
        "Your research interest",
        placeholder="e.g. How New Zealand might position itself in great power competition through green compute infrastructure...",
        height=120,
    )

    if st.button("Analyse Gaps", use_container_width=True):
        if gap_input.strip():
            st.session_state["run_gap_analysis"] = gap_input.strip()
        else:
            st.warning("Please describe your research interest before running the analysis.")

# Build filters dict
filters = {
    "year_min": year_min,
    "year_max": year_max,
    "journal": journal_filter or None,
    "geographic_focus": geo_filter or None,
    "method": method_filter or None,
}

active_filters = filters if (filters_active or year_filtered) else None

# ── Landscape report ───────────────────────────────────────────────────────────
if st.session_state.get("generate_landscape"):
    st.session_state["generate_landscape"] = False

    with st.spinner("Analysing your research database — this may take a moment..."):
        report = generate_landscape_report(filters=active_filters)

    with st.expander("📊 Research Landscape Report", expanded=True):
        st.markdown(report)

    st.session_state.setdefault("messages", []).append({
        "role": "assistant",
        "content": report,
        "sources": [],
        "is_landscape": True,
    })

# ── Gap analysis ───────────────────────────────────────────────────────────────
if st.session_state.get("run_gap_analysis"):
    research_interest = st.session_state.pop("run_gap_analysis")

    with st.spinner("Identifying gaps in the literature — this may take a moment..."):
        gap_report = generate_gap_analysis(research_interest, filters=active_filters)

    with st.expander("🔍 Gap Analysis Report", expanded=True):
        st.markdown(f"**Research interest:** {research_interest}")
        st.divider()
        st.markdown(gap_report)

    st.session_state.setdefault("messages", []).append({
        "role": "assistant",
        "content": f"**Gap analysis for:** {research_interest}\n\n{gap_report}",
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
