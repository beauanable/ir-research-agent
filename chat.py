import json
import math
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

CHUNKS_FILE = "processed_chunks.jsonl"
EMBEDDING_MODEL = "text-embedding-3-small"
RERANK_MODEL = "gpt-4.1-mini"
ANSWER_MODEL = "gpt-4.1-mini"


def load_chunks():
    chunks = []
    with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                chunks.append(json.loads(line))
    return chunks


def embed_query(query):
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=query
    )
    return response.data[0].embedding


def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))

    if norm_a == 0 or norm_b == 0:
        return 0

    return dot / (norm_a * norm_b)


def retrieve(query, top_k=20):
    query_embedding = embed_query(query)
    chunks = load_chunks()

    scored = []

    for chunk in chunks:
        embedding = chunk.get("embedding")

        if not embedding:
            continue

        score = cosine_similarity(query_embedding, embedding)
        scored.append((score, chunk))

    scored.sort(reverse=True, key=lambda x: x[0])
    return scored[:top_k]


def rerank_chunks(query, retrieved_results, top_k=5):
    chunk_list = []

    for i, (score, chunk) in enumerate(retrieved_results):
        chunk_list.append({
            "id": i,
            "title": chunk.get("title", "Untitled"),
            "year": chunk.get("year", "Unknown"),
            "journal": chunk.get("journal", "Unknown"),
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
        return retrieved_results[:top_k]

    return reranked[:top_k]


def answer_question(query):
    retrieved = retrieve(query, top_k=20)
    reranked = rerank_chunks(query, retrieved, top_k=5)

    context = "\n\n".join(
        [
            f"Source {i + 1}\n"
            f"Title: {chunk.get('title', 'Untitled')}\n"
            f"Authors: {chunk.get('authors', 'Unknown')}\n"
            f"Journal: {chunk.get('journal', 'Unknown')}\n"
            f"Year: {chunk.get('year', 'Unknown')}\n"
            f"DOI: {chunk.get('doi', 'Unknown')}\n"
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

    return response.choices[0].message.content


if __name__ == "__main__":
    while True:
        question = input("\nAsk a question, or type 'quit': ")

        if question.lower() in ["quit", "exit"]:
            break

        print("\nRetrieving and reranking sources...\n")
        print(answer_question(question))
