import streamlit as st
from collections import Counter
from chat import answer_question, generate_landscape_report, generate_gap_analysis
from supabase import create_client
import os

supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"])

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

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_chat, tab_dashboard = st.tabs(["💬 Chat", "📊 Methods & Datasets"])

# ── Tab 1: Chat ────────────────────────────────────────────────────────────────
with tab_chat:

    # Landscape report
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

    # Gap analysis
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

    # Chat history
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

# ── Tab 2: Methods & Datasets Dashboard ───────────────────────────────────────
with tab_dashboard:
    st.subheader("Methods & Datasets Dashboard")
    st.caption("Aggregated view of research methods and datasets across all papers in your database.")

    @st.cache_data(ttl=300)
    def load_dashboard_data():
        try:
            result = supabase.table("chunks").select(
                "title, authors, journal, year, doi, method, dataset_or_evidence, "
                "geographic_focus, research_design, unit_of_analysis"
            ).execute()

            # Deduplicate by title
            seen = set()
            papers = []
            for row in result.data:
                title = row.get("title") or ""
                if title and title not in seen:
                    seen.add(title)
                    papers.append(row)

            return papers
        except Exception as e:
            st.error(f"Failed to load dashboard data: {e}")
            return []

    papers = load_dashboard_data()

    if not papers:
        st.info("No papers in the database yet. Run the research agent first.")
    else:
        st.markdown(f"**{len(papers)} papers in database**")

        # ── Summary counts ─────────────────────────────────────────────────────
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### Methods")
            methods = [p.get("method") for p in papers if p.get("method") and p.get("method") != "Not clearly specified in available text."]
            if methods:
                method_counts = Counter(methods)
                for method, count in method_counts.most_common(15):
                    st.markdown(f"- **{method}** ({count})")
            else:
                st.caption("No method data available yet.")

        with col2:
            st.markdown("#### Datasets & Evidence Types")
            datasets = [p.get("dataset_or_evidence") for p in papers if p.get("dataset_or_evidence") and p.get("dataset_or_evidence") != "Not clearly specified in available text."]
            if datasets:
                dataset_counts = Counter(datasets)
                for dataset, count in dataset_counts.most_common(15):
                    st.markdown(f"- **{dataset}** ({count})")
            else:
                st.caption("No dataset data available yet.")

        st.divider()

        col3, col4 = st.columns(2)

        with col3:
            st.markdown("#### Geographic Focus")
            geos = [p.get("geographic_focus") for p in papers if p.get("geographic_focus") and p.get("geographic_focus") != "Not clearly specified in available text."]
            if geos:
                geo_counts = Counter(geos)
                for geo, count in geo_counts.most_common(15):
                    st.markdown(f"- **{geo}** ({count})")
            else:
                st.caption("No geographic focus data available yet.")

        with col4:
            st.markdown("#### Research Design")
            designs = [p.get("research_design") for p in papers if p.get("research_design") and p.get("research_design") != "Not clearly specified in available text."]
            if designs:
                design_counts = Counter(designs)
                for design, count in design_counts.most_common(15):
                    st.markdown(f"- **{design}** ({count})")
            else:
                st.caption("No research design data available yet.")

        st.divider()

        # ── Full paper table ───────────────────────────────────────────────────
        st.markdown("#### All Papers")

        # Table search
        table_search = st.text_input("Search papers", placeholder="Filter by title, method, journal...")

        # Build display rows
        rows = []
        for p in papers:
            rows.append({
                "Title": p.get("title") or "",
                "Year": p.get("year") or "",
                "Journal": p.get("journal") or "",
                "Method": p.get("method") or "",
                "Dataset / Evidence": p.get("dataset_or_evidence") or "",
                "Geographic Focus": p.get("geographic_focus") or "",
                "Research Design": p.get("research_design") or "",
                "Unit of Analysis": p.get("unit_of_analysis") or "",
                "DOI": p.get("doi") or "",
            })

        # Apply search filter
        if table_search:
            search_lower = table_search.lower()
            rows = [
                r for r in rows
                if any(search_lower in str(v).lower() for v in r.values())
            ]

        st.markdown(f"*Showing {len(rows)} papers*")
        st.dataframe(rows, use_container_width=True, height=500)
