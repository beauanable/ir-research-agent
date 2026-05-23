import json
import math
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

CHUNKS_FILE = "processed_chunks.jsonl"


def load_chunks():
    chunks = []
    with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                chunks.append(json.loads(line))
    return chunks


def embed_query(query):
    response = client.embeddings.create(
        model="text-embedding-3-small",
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


def retrieve(query, top_k=5):
    query_embedding = embed_query(query)
    chunks = load_chunks()

    scored = []
    for chunk in chunks:
        if "embedding" not in chunk:
            continue
        score = cosine_similarity(query_embedding, chunk["embedding"])
        scored.append((score, chunk))

    scored.sort(reverse=True, key=lambda x: x[0])
    return scored[:top_k]


def answer_question(query):
    results = retrieve(query)

    context = "\n\n".join(
        [
            f"Source: {chunk.get('title', 'Untitled')}\n"
            f"Authors: {chunk.get('authors', 'Unknown')}\n"
            f"Year: {chunk.get('year', 'Unknown')}\n"
            f"Text: {chunk.get('text', '')}"
            for score, chunk in results
        ]
    )

    prompt = f"""
You are an international relations research assistant.

Answer the user's question using only the sources below.
If the sources are insufficient, say so clearly.
Cite papers by title and year when possible.

Sources:
{context}

Question:
{query}
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.2
    )

    return response.choices[0].message.content


if __name__ == "__main__":
    while True:
        question = input("\nAsk a question, or type 'quit': ")

        if question.lower() in ["quit", "exit"]:
            break

        print("\nThinking...\n")
        print(answer_question(question))
