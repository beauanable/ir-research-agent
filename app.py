import streamlit as st
from collections import Counter
from chat import answer_question, generate_landscape_report, generate_gap_analysis
from supabase import create_client
from openai import OpenAI
from pypdf import PdfReader
import hashlib
import tempfile
import os

supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"])
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

EMBEDDING_MODEL = "text-embedding-3-small"

st.set_page_config(
    page_title="IR Research Agent",
    page_icon="📚",
    layout="wide"
)

st.title("📚 IR Research Agent")
st.caption("Ask questions against your processed IR literature database.")

# ── Method normalisation ───────────────────────────────────────────────────────
METHOD_NORMALISATION = {
    "case study": "Case Study",
    "single case": "Case Study",
    "case-study": "Case Study",
    "comparative case": "Comparative Case Study",
    "comparative analysis": "Comparative Case Study",
    "cross-case": "Comparative Case Study",
    "process trac": "Process Tracing",
    "historical": "Historical Analysis",
    "archival": "Historical Analysis",
    "discourse": "Discourse Analysis",
    "framing analysis": "Discourse Analysis",
    "rhetorical": "Discourse Analysis",
    "content analysis": "Content Analysis",
    "interview": "Interview-Based Research",
    "ethnograph": "Interview-Based Research",
    "qualitative interview": "Interview-Based Research",
    "regression": "Regression Analysis",
    "econometric": "Regression Analysis",
    "quantitative analysis": "Regression Analysis",
    "statistical": "Regression Analysis",
    "time series": "Time Series Analysis",
    "panel data": "Time Series Analysis",
    "event study": "Event Study",
    "survey": "Survey / Experiment",
    "experiment": "Survey / Experiment",
    "game theory": "Formal Modeling / Game Theory",
    "formal model": "Formal Modeling / Game Theory",
    "rational choice": "Formal Modeling / Game Theory",
    "mixed method": "Mixed Methods",
    "systematic review": "Systematic Literature Review",
    "literature review": "Systematic Literature Review",
    "meta-analysis": "Meta-Analysis",
    "meta analysis": "Meta-Analysis",
    "conceptual": "Conceptual / Theoretical",
    "theoretical": "Conceptual / Theoretical",
    "theory": "Conceptual / Theoretical",
    "normative": "Conceptual / Theoretical",
    "analytical framework": "Conceptual / Theoretical",
    "policy analysis": "Policy Analysis",
    "policy review": "Policy Analysis",
    "policy assessment": "Policy Analysis",
}


def normalise_method(raw_method):
    if not raw_method:
        return "Other"
    lower = raw_method.lower()
    for keyword, canonical in METHOD_NORMALISATION.items():
        if keyword in lower:
            return canonical
    return "Other"


# ── PDF upload helpers ─────────────────────────────────────────────────────────
def extract_text_from_pdf(uploaded_file):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name

    reader = PdfReader(tmp_path)
    full_text = ""

    for page in reader.pages:
        try:
            text = page.extract_text()
            if text:
                full_text += text + "\n"
        except Exception:
            continue

    os.unlink(tmp_path)
    return full_text.strip()


def create_embedding(text):
    try:
        response = client.embeddings.create(model=EMBEDDING_MODEL, input=text)
        return response.data[0].embedding
    except Exception as e:
        print(f"Embedding failed: {e}")
        return None


def create_chunk_id(title, chunk_index, chunk_text):
    base = f"{title}_{chunk_index}_{chunk_text[:200]}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def chunk_text(text, max_chars=3000, overlap_chars=300):
    if not text:
        return []

    text = text.strip()
    raw_paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    paragraphs = []
    for para in raw_paragraphs:
        if len(para) <= max_chars:
            paragraphs.append(para)
        else:
            current = ""
            for part in para.replace(". ", ".|").replace("? ", "?|").replace("! ", "!|").split("|"):
                if len(current) + len(part) + 1 <= max_chars:
                    current += (" " if current else "") + part
                else:
                    if current:
                        paragraphs.append(current)
                    current = part
            if current:
                paragraphs.append(current)

    chunks = []
    current_chunk = ""

    for para in paragraphs:
        if not current_chunk:
            current_chunk = para
        elif len(current_chunk) + len(para) + 2 <= max_chars:
            current_chunk += "\n\n" + para
        else:
            chunks.append(current_chunk)
            overlap = current_chunk[-overlap_chars:] if len(current_chunk) > overlap_chars else current_chunk
            current_chunk = overlap + "\n\n" + para

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def upload_pdf_to_supabase(text, metadata):
    chunks = chunk_text(text)

    if not chunks:
        return 0, 0

    saved = 0
    skipped = 0

    for index, chunk in enumerate(chunks):
        chunk_id = create_chunk_id(metadata["title"], index, chunk)

        # Check if chunk already exists
        try:
            existing = supabase.table("chunks").select("chunk_id").eq("chunk_id", chunk_id).execute()
            if existing.data:
                skipped += 1
                continue
        except Exception:
            pass

        embedding = create_embedding(chunk)

        record = {
            "chunk_id": chunk_id,
            "title": metadata["title"],
            "authors": metadata["authors"],
            "journal": None,
            "year": metadata["year"],
            "doi": metadata.get("doi") or None,
            "search_term": "manual upload",
            "analysis_source": "Full PDF",
            "source_type": metadata["source_type"],
            "research_design": metadata.get("research_design") or None,
            "method": metadata.get("method") or None,
            "dataset_or_evidence": None,
            "unit_of_analysis": None,
            "time_period_studied": None,
            "geographic_focus": metadata.get("geographic_focus") or None,
            "identification_strategy": None,
            "chunk_index": index,
            "chunk_text": chunk,
            "embedding": embedding,
        }

        try:
            supabase.table("chunks").upsert(record).execute()
            saved += 1
        except Exception as e:
            st.warning(f"Failed to save chunk {index}: {e}")

    return saved, skipped


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filter sources")
    st.caption("Narrow the database before searching. Leave blank to search everything.")

    year_min = st.number_input("Year from", min_value=1950, max_value=2026, value=2024, step=1)
    year_max = st.number_input("Year to", min_value=1950, max_value=2026, value=2026, step=1)
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
tab_chat, tab_dashboard, tab_upload = st.tabs(["💬 Chat", "📊 Methods & Datasets", "📥 Upload PDF"])

# ── Tab 1: Chat ────────────────────────────────────────────────────────────────
with tab_chat:

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
                "geographic_focus, research_design, unit_of_analysis, source_type"
            ).execute()

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
        # Split by source type
        journal_papers = [p for p in papers if p.get("source_type") not in ("textbook", "foundational")]
        textbooks = [p for p in papers if p.get("source_type") == "textbook"]
        foundational = [p for p in papers if p.get("source_type") == "foundational"]

        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Journal Articles", len(journal_papers))
        col_b.metric("Textbooks", len(textbooks))
        col_c.metric("Foundational Papers", len(foundational))

        st.divider()

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### Methods")
            raw_methods = [p.get("method") for p in papers if p.get("method") and p.get("method") != "Not clearly specified in available text."]
            if raw_methods:
                normalised = [normalise_method(m) for m in raw_methods]
                for method, count in Counter(normalised).most_common():
                    st.markdown(f"- **{method}** ({count})")
            else:
                st.caption("No method data available yet.")

        with col2:
            st.markdown("#### Datasets & Evidence Types")
            datasets = [p.get("dataset_or_evidence") for p in papers if p.get("dataset_or_evidence") and p.get("dataset_or_evidence") != "Not clearly specified in available text."]
            if datasets:
                for dataset, count in Counter(datasets).most_common(15):
                    st.markdown(f"- **{dataset}** ({count})")
            else:
                st.caption("No dataset data available yet.")

        st.divider()

        col3, col4 = st.columns(2)

        with col3:
            st.markdown("#### Geographic Focus")
            geos = [p.get("geographic_focus") for p in papers if p.get("geographic_focus") and p.get("geographic_focus") != "Not clearly specified in available text."]
            if geos:
                for geo, count in Counter(geos).most_common(15):
                    st.markdown(f"- **{geo}** ({count})")
            else:
                st.caption("No geographic focus data available yet.")

        with col4:
            st.markdown("#### Research Design")
            designs = [p.get("research_design") for p in papers if p.get("research_design") and p.get("research_design") != "Not clearly specified in available text."]
            if designs:
                for design, count in Counter(designs).most_common(15):
                    st.markdown(f"- **{design}** ({count})")
            else:
                st.caption("No research design data available yet.")

        st.divider()

        st.markdown("#### All Papers")
        table_search = st.text_input("Search papers", placeholder="Filter by title, method, journal...")

        rows = []
        for p in papers:
            rows.append({
                "Title": p.get("title") or "",
                "Year": p.get("year") or "",
                "Journal": p.get("journal") or "",
                "Source Type": p.get("source_type") or "",
                "Method (normalised)": normalise_method(p.get("method")),
                "Method (raw)": p.get("method") or "",
                "Dataset / Evidence": p.get("dataset_or_evidence") or "",
                "Geographic Focus": p.get("geographic_focus") or "",
                "Research Design": p.get("research_design") or "",
                "Unit of Analysis": p.get("unit_of_analysis") or "",
                "DOI": p.get("doi") or "",
            })

        if table_search:
            search_lower = table_search.lower()
            rows = [r for r in rows if any(search_lower in str(v).lower() for v in r.values())]

        st.markdown(f"*Showing {len(rows)} papers*")
        st.dataframe(rows, use_container_width=True, height=500)

# ── Tab 3: Upload PDF ──────────────────────────────────────────────────────────
with tab_upload:
    st.subheader("Upload PDF")
    st.caption("Upload a textbook or foundational paper directly into your research database.")

    uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")

    if uploaded_file:
        st.success(f"File loaded: {uploaded_file.name}")
        st.divider()
        st.markdown("#### Document metadata")
        st.caption("Fill in the details below before uploading to the database.")

        col1, col2 = st.columns(2)

        with col1:
            title = st.text_input("Title *", placeholder="e.g. Theory of International Politics")
            authors_raw = st.text_input("Authors *", placeholder="e.g. Kenneth Waltz, John Mearsheimer")
            year = st.number_input("Year *", min_value=1900, max_value=2026, value=2000, step=1)
            doi = st.text_input("DOI (optional)", placeholder="e.g. https://doi.org/10.xxxx")

        with col2:
            source_type = st.selectbox(
                "Source type *",
                options=["textbook", "foundational"],
                format_func=lambda x: "Textbook" if x == "textbook" else "Foundational Paper",
            )
            geographic_focus = st.text_input("Geographic focus (optional)", placeholder="e.g. Global, United States, China")
            research_design = st.text_input("Research design (optional)", placeholder="e.g. Theoretical framework")
            method = st.selectbox(
                "Method (optional)",
                options=[""] + [
                    "Case Study", "Comparative Case Study", "Process Tracing",
                    "Historical Analysis", "Discourse Analysis", "Content Analysis",
                    "Interview-Based Research", "Regression Analysis", "Time Series Analysis",
                    "Event Study", "Survey / Experiment", "Formal Modeling / Game Theory",
                    "Mixed Methods", "Systematic Literature Review", "Meta-Analysis",
                    "Conceptual / Theoretical", "Policy Analysis", "Other",
                ],
            )

        st.divider()

        if st.button("Upload to database", type="primary", use_container_width=True):
            if not title.strip():
                st.error("Title is required.")
            elif not authors_raw.strip():
                st.error("Authors are required.")
            else:
                authors_list = [a.strip() for a in authors_raw.split(",") if a.strip()]

                metadata = {
                    "title": title.strip(),
                    "authors": authors_list,
                    "year": int(year),
                    "doi": doi.strip() or None,
                    "source_type": source_type,
                    "geographic_focus": geographic_focus.strip() or None,
                    "research_design": research_design.strip() or None,
                    "method": method or None,
                }

                with st.spinner("Extracting text and creating embeddings — this may take several minutes for large PDFs..."):
                    text = extract_text_from_pdf(uploaded_file)

                    if not text or len(text) < 500:
                        st.error("Could not extract readable text from this PDF. It may be scanned or image-based.")
                    else:
                        st.info(f"Extracted {len(text):,} characters from PDF. Creating chunks and embeddings...")
                        saved, skipped = upload_pdf_to_supabase(text, metadata)

                        if saved > 0:
                            st.success(f"✅ Successfully uploaded **{saved} chunks** to the database. ({skipped} already existed and were skipped.)")
                            st.balloons()
                        else:
                            st.warning("No new chunks were saved. The document may already be in the database.")
