import os
import requests
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

url = "https://api.openalex.org/works"

params = {
    "search": "international relations",
    "sort": "publication_date:desc",
    "per-page": 3
}

response = requests.get(url, params=params)
data = response.json()

print("\nIR Research Digest\n")

if "results" not in data:
    print("Unexpected API response:")
    print(data)
    raise SystemExit(1)

for paper in data["results"]:

    title = paper.get("title", "No title")
    abstract = paper.get("abstract_inverted_index")

    if not abstract:
        continue

    # Convert OpenAlex abstract format into readable text
    ordered_words = sorted(
        abstract.items(),
        key=lambda x: x[1][0]
    )

    abstract_text = " ".join(
        [word for word, positions in ordered_words]
    )

    prompt = f"""
You are an international relations research assistant.

Summarize this paper and extract:

1. Main argument
2. Research method
3. Dataset or evidence used
4. Key findings
5. Why this matters for IR scholars

Paper title:
{title}

Abstract:
{abstract_text}
"""

    completion = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    summary = completion.choices[0].message.content

    print("=" * 80)
    print(f"TITLE: {title}")
    print("=" * 80)
    print(summary)
    print("\n\n")
