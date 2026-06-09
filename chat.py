import json
import math
import os
from openai import OpenAI
from supabase import create_client

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"])

EMBEDDING_MODEL = "text-embedding-3-small"
RERANK_MODEL = "gpt-4.1-mini"
ANSWER_MODEL = "gpt-4.1-mini"

METADATA_BOOST_FIELDS = ["geographic_focus", "method", "research_design"]
METADATA_BOOST_AMOUNT = 0.05

_cached_chunks = None


def load_chunks(filters=None):
    global _cached_chunks

    if not filters:
        if _cached_chunks is not None:
            return _cached_chunks

    try:
        query = supabase.table("chunks").select(
            "chunk_id, title, authors, journal, year, doi, chunk_index, chunk_text, "
            "embedding, geographic_focus, method, research_design, source_type, "
            "dataset_or_evidence, unit_of_analysis, identification_strategy"
        )

        if filters:
            if filters.get("year_min"):
                query = query.gte("year", filters["year_min"])
            if filters.get("year_max"):
                query = query.lte("year", filters["year_max"])
            if filters.get("journal"):
                query = query.ilike("journal", f"%{filters['journal']}%")
            if filters.get("geographic_focus"):
                query = query.ilike("geographic_focus", f"%{filters['geographic_focus']}%")
            if filters.get("method"):
                query = query.ilike("method", f"%{filters['method']}%")

        result = query.execute()

        if not filters:
            _cached_chunks = result.data
            print(f"Loaded {len(_cached_chunks)} chunks from Supabase")

        return result.data

    except Exception as e:
        print(f"Failed to load chunks from Supabase: {e}")
        return []


def embed_query(query):
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=query)
    return response.data[0].embedding


def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0
    return dot / (norm_a * norm_b)


def metadata_boost(query, chunk):
    boost = 0
    query_lower = query.lower()
    for field in METADATA_BOOST_FIELDS:
        value = chunk.get(field) or ""
        if value and any(word in value.lower() for word in query_lower.split() if len(word) > 3):
            boost += METADATA_BOOST_AMOUNT
    return boost


def retrieve(query, top_k=20, filters=None):
    query_embedding = embed_query(query)
    chunks = load_chunks(filters=filters)

    if not chunks:
        return []

    scored = []
    for chunk in chunks:
        embedding = chunk.get("embedding")
        if not embedding:
            continue
        score = cosine_similarity(query_embedding, embedding)
        score += metadata_boost(query, chunk)
        scored.append((score, chunk))

    scored.sort(reverse=True, key=lambda x: x[0])
    return scored[:top_k]


def rerank_chunks(query, retrieved_results, top_k=5):
    if not retrieved_results:
        return []

    chunk_list = []
    for i, (score, chunk) in enumerate(retrieved_results):
        chunk_list.append({
            "id": i,
            "title": chunk.get("title", "Untitled"),
            "year": chunk.get("year", "Unknown"),
            "journal": chunk.get("journal", "Unknown"),
            "geographic_focus": chunk.get("geographic_focus", ""),
            "method": chunk.get("method", ""),
            "text": chunk.get("chunk_text", "")[:1200],
            "similarity_score": round(score, 4)
        })

    prompt = f"""
You are reranking research paper chunks for an international relations research assistant.

User question:
{query}

Candidate chunks:
{json.dumps(chunk_list, ensure_ascii=False, indent=2)}

Return only a JSON list of the {top_k} most relevant chunk ids, ordered from most relevant to least relevant.

Example:
[3, 7, 1, 12, 0]

Do not include explanations.
"""

    response = client.chat.completions.create(
        model=RERANK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    content = response.choices[0].message.content.strip()

    try:
        selected_ids = json.loads(content)
    except Exception:
        print("Reranking failed. Falling back to similarity ranking.")
        return retrieved_results[:top_k]

    reranked = []
    for selected_id in selected_ids:
        if isinstance(selected_id, int) and 0 <= selected_id < len(retrieved_results):
            reranked.append(retrieved_results[selected_id])

    if not reranked:
        print("Reranker returned no valid IDs. Falling back to similarity ranking.")
        return retrieved_results[:top_k]

    if len(reranked) < top_k:
        print(f"Warning: reranker returned {len(reranked)} results, expected {top_k}.")

    return reranked[:top_k]


def format_conversation_history(messages):
    """
    Format Streamlit message history into a conversation string for the LLM.
    Includes Q&A, landscape reports, and gap analyses.
    Truncates to last 6000 characters to stay within token limits.
    """
    if not messages:
        return ""

    lines = []
    for msg in messages:
        role = "User" if msg["role"] == "user" else "Assistant"
        content = msg.get("content", "")

        # Truncate very long individual messages (e.g. full landscape reports)
        if len(content) > 2000:
            content = content[:2000] + "... [truncated for brevity]"

        lines.append(f"{role}: {content}")

    history_text = "\n\n".join(lines)

    # Keep only the last 6000 characters if history is very long
    if len(history_text) > 6000:
        history_text = "...[earlier conversation truncated]...\n\n" + history_text[-6000:]

    return history_text


def answer_question(query, return_sources=False, filters=None, conversation_history=None):
    try:
        retrieved = retrieve(query, top_k=20, filters=filters)

        if not retrieved:
            msg = "No relevant sources found. Try adjusting your filters or running the research agent to add more papers."
            return (msg, []) if return_sources else msg

        reranked = rerank_chunks(query, retrieved, top_k=5)

        source_headers = []
        for i, (score, chunk) in enumerate(reranked):
            authors = chunk.get("authors") or []
            if isinstance(authors, list):
                if len(authors) == 0:
                    author_str = "Unknown"
                elif len(authors) == 1:
                    author_str = authors[0]
                elif len(authors) == 2:
                    author_str = f"{authors[0]} & {authors[1]}"
                else:
                    author_str = f"{authors[0]} et al."
            else:
                author_str = str(authors)

            source_headers.append(
                f"[{i+1}] {author_str}, \"{chunk.get('title', 'Untitled')}\", "
                f"{chunk.get('journal', 'Unknown journal')}, {chunk.get('year', 'n.d.')}"
            )

        context = "\n\n".join(
            [
                f"[{i+1}] {' | '.join(source_headers[i:i+1])}\n"
                f"Geographic focus: {chunk.get('geographic_focus', 'Not specified')}\n"
                f"Method: {chunk.get('method', 'Not specified')}\n"
                f"Text: {chunk.get('chunk_text', '')}"
                for i, (score, chunk) in enumerate(reranked)
            ]
        )

        # Build conversation history section
        history_section = ""
        if conversation_history:
            history_text = format_conversation_history(conversation_history)
            if history_text:
                history_section = f"""
Previous conversation:
{history_text}

---
"""

        prompt = f"""
You are an international relations research assistant writing for a graduate-level audience.

{history_section}
Answer the user's current question using the numbered sources below.
If the question refers to something discussed earlier in the conversation, 
use that context to give a more precise and relevant answer.

Citation rules:
- Cite sources inline using bracketed numbers, e.g. [1], [2], [1,3].
- Every factual claim must have at least one inline citation.
- Do not save all citations for the end — place them immediately after the claim they support.
- If two sources support the same claim, cite both: [1,2].
- If the sources are insufficient to answer the question, say so explicitly.
- Do not invent evidence or cite sources for claims they do not support.
- Distinguish between strong evidence, partial evidence, and speculation.

Sources:
{context}

Current question:
{query}
"""

        response = client.chat.completions.create(
            model=ANSWER_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )

        answer = response.choices[0].message.content

        sources = []
        for score, chunk in reranked:
            sources.append({
                "title": chunk.get("title", "Untitled"),
                "authors": chunk.get("authors", "Unknown"),
                "journal": chunk.get("journal", "Unknown"),
                "year": chunk.get("year", "Unknown"),
                "doi": chunk.get("doi", "Unknown"),
                "geographic_focus": chunk.get("geographic_focus", ""),
                "method": chunk.get("method", ""),
                "score": round(score, 4),
                "chunk_index": chunk.get("chunk_index", "Unknown"),
            })

        if return_sources:
            return answer, sources

        return answer

    except Exception as e:
        print(f"answer_question failed: {e}")
        error_msg = "Something went wrong while retrieving an answer. Please try again."
        return (error_msg, []) if return_sources else error_msg


def generate_landscape_report(filters=None):
    try:
        chunks = load_chunks(filters=filters)

        if not chunks:
            return "No papers in the database yet. Run the research agent first."

        seen_titles = set()
        papers = []
        for chunk in chunks:
            title = chunk.get("title") or ""
            if title and title not in seen_titles:
                seen_titles.add(title)
                papers.append({
                    "title": title,
                    "journal": chunk.get("journal") or "Unknown",
                    "year": chunk.get("year") or "Unknown",
                    "method": chunk.get("method") or "Not specified",
                    "research_design": chunk.get("research_design") or "Not specified",
                    "dataset_or_evidence": chunk.get("dataset_or_evidence") or "Not specified",
                    "geographic_focus": chunk.get("geographic_focus") or "Not specified",
                    "unit_of_analysis": chunk.get("unit_of_analysis") or "Not specified",
                    "identification_strategy": chunk.get("identification_strategy") or "Not specified",
                })

        paper_list = json.dumps(papers, ensure_ascii=False, indent=2)

        prompt = f"""
You are an elite international relations research analyst.

Below is a structured list of {len(papers)} research papers from a personal IR literature database.
Each entry includes the paper's title, journal, year, method, research design, dataset or evidence,
geographic focus, unit of analysis, and identification strategy.

Generate a detailed, analytical research landscape report with the following sections:

## 1. Dominant Topics and Themes
## 2. Research Methods in Use
## 3. Datasets and Evidence Types
## 4. Geographic Coverage
## 5. Theoretical Frameworks
## 6. Units of Analysis
## 7. Apparent Gaps in the Literature

Be specific and analytical throughout. Reference paper titles and journals where relevant.
Write for a graduate-level IR scholar.

Papers:
{paper_list}
"""

        response = client.chat.completions.create(
            model=ANSWER_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=3000,
        )

        return response.choices[0].message.content

    except Exception as e:
        print(f"generate_landscape_report failed: {e}")
        return "Something went wrong generating the landscape report. Please try again."


def generate_gap_analysis(research_interest, filters=None):
    try:
        chunks = load_chunks(filters=filters)

        if not chunks:
            return "No papers in the database yet. Run the research agent first."

        seen_titles = set()
        papers = []
        for chunk in chunks:
            title = chunk.get("title") or ""
            if title and title not in seen_titles:
                seen_titles.add(title)
                papers.append({
                    "title": title,
                    "journal": chunk.get("journal") or "Unknown",
                    "year": chunk.get("year") or "Unknown",
                    "method": chunk.get("method") or "Not specified",
                    "research_design": chunk.get("research_design") or "Not specified",
                    "dataset_or_evidence": chunk.get("dataset_or_evidence") or "Not specified",
                    "geographic_focus": chunk.get("geographic_focus") or "Not specified",
                    "unit_of_analysis": chunk.get("unit_of_analysis") or "Not specified",
                    "identification_strategy": chunk.get("identification_strategy") or "Not specified",
                })

        paper_list = json.dumps(papers, ensure_ascii=False, indent=2)

        prompt = f"""
You are an elite international relations research analyst helping a PhD student
identify gaps in the existing literature relative to their research interest.

The student's research interest is:
\"\"\"{research_interest}\"\"\"

Below is a structured list of {len(papers)} papers from their personal IR literature database.

Generate a detailed gap analysis with the following sections:

## 1. What the Existing Literature Covers
## 2. Topical Gaps
## 3. Methodological Gaps
## 4. Geographic Gaps
## 5. Theoretical Gaps
## 6. High-Value Research Opportunities

Be specific and actionable throughout. Write for a PhD student who needs concrete direction.

Papers:
{paper_list}
"""

        response = client.chat.completions.create(
            model=ANSWER_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=3000,
        )

        return response.choices[0].message.content

    except Exception as e:
        print(f"generate_gap_analysis failed: {e}")
        return "Something went wrong generating the gap analysis. Please try again."


if __name__ == "__main__":
    while True:
        question = input("\nAsk a question, or type 'quit': ")
        if question.lower() in ["quit", "exit"]:
            break
        print("\nRetrieving and reranking sources...\n")
        answer, sources = answer_question(question, return_sources=True)
        print(answer)
        print(f"\n--- {len(sources)} sources used ---")
        for i, s in enumerate(sources, 1):
            print(f"{i}. {s['title']} ({s['year']}) — score: {s['score']}")
