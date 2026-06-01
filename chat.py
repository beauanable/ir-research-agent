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

# Metadata fields we boost on if they match the query
METADATA_BOOST_FIELDS = ["geographic_focus", "method", "research_design"]
METADATA_BOOST_AMOUNT = 0.05

# Cache chunks in memory after first load
_cached_chunks = None


def load_chunks(filters=None):
    """
    Load chunks from Supabase.
    filters: dict of optional metadata filters e.g.
      {"year_min": 2024, "year_max": 2025, "journal": "...", "geographic_focus": "...", "method": "..."}
    Filtered queries bypass the cache since filters change the result set.
    """
    global _cached_chunks

    if not filters:
        if _cached_chunks is not None:
            return _cached_chunks

    try:
        query = supabase.table("chunks").select(
            "chunk_id, title, authors, journal, year, doi, chunk_index, chunk_text, "
            "embedding, geographic_focus, method, research_design, source_type"
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
    """
    Add a small boost to the similarity score if metadata fields
    contain terms from the query.
    """
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


def answer_question(query, return_sources=False, filters=None):
    try:
        retrieved = retrieve(query, top_k=20, filters=filters)

        if not retrieved:
            msg = "No relevant sources found. Try adjusting your filters or running the research agent to add more papers."
            return (msg, []) if return_sources else msg

        reranked = rerank_chunks(query, retrieved, top_k=5)

        context = "\n\n".join(
            [
                f"Source {i + 1}\n"
                f"Title: {chunk.get('title', 'Untitled')}\n"
                f"Authors: {chunk.get('authors', 'Unknown')}\n"
                f"Journal: {chunk.get('journal', 'Unknown')}\n"
                f"Year: {chunk.get('year', 'Unknown')}\n"
                f"DOI: {chunk.get('doi', 'Unknown')}\n"
                f"Geographic focus: {chunk.get('geographic_focus', 'Not specified')}\n"
                f"Method: {chunk.get('method', 'Not specified')}\n"
                f"Text: {chunk.get('chunk_text', '')}"
                for i, (score, chunk) in enumerate(reranked)
            ]
        )

        prompt = f"""
You are an international relations research assistant.

Answer the user's question using only the sources below.

Rules:
- Do not invent evidence.
- If the sources are insufficient, say so clearly.
- Cite paper titles and years when possible.
- Distinguish between strong evidence, partial evidence, and speculation.
- Keep the answer analytical and useful for graduate-level research.

Sources:
{context}

Question:
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
