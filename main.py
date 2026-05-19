import os
import smtplib
from email.mime.text import MIMEText

import requests
from openai import OpenAI


client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

OPENALEX_URL = "https://api.openalex.org/works"

SEARCH_TERMS = [
    "AI geopolitics",
    "technology governance international relations",
    "international political economy infrastructure",
    "energy security geopolitics",
    "deterrence theory",
    "state capacity international relations",
    "great power competition",
    "critical infrastructure security",
]

TOP_JOURNALS = [
    "International Organization",
    "International Security",
    "International Studies Quarterly",
    "World Politics",
    "European Journal of International Relations",
    "Review of International Political Economy",
    "Security Studies",
    "Journal of Conflict Resolution",
]

PRIORITY_KEYWORDS = [
    "artificial intelligence",
    "ai",
    "geopolitics",
    "political economy",
    "security",
    "deterrence",
    "infrastructure",
    "state capacity",
    "energy",
    "technology",
    "great power",
    "competition",
    "governance",
]


def reconstruct_abstract(abstract_inverted_index):
    if not abstract_inverted_index:
        return ""

    word_positions = []

    for word, positions in abstract_inverted_index.items():
        for position in positions:
            word_positions.append((position, word))

    word_positions.sort()
    return " ".join(word for position, word in word_positions)


def get_journal(paper):
    primary_location = paper.get("primary_location") or {}
    source = primary_location.get("source") or {}
    return source.get("display_name", "")


def score_paper(paper, search_term):
    score = 0

    title = paper.get("title") or ""
    abstract_text = reconstruct_abstract(paper.get("abstract_inverted_index"))
    journal = get_journal(paper)
    cited_by_count = paper.get("cited_by_count") or 0
    year = paper.get("publication_year") or 0

    combined_text = f"{title} {abstract_text}".lower()

    if journal in TOP_JOURNALS:
        score += 30

    if year >= 2026:
        score += 20
    elif year == 2025:
        score += 15
    elif year == 2024:
        score += 8

    score += min(cited_by_count, 100) / 5

    for keyword in PRIORITY_KEYWORDS:
        if keyword.lower() in combined_text:
            score += 5

    for term_word in search_term.lower().split():
        if term_word in combined_text:
            score += 3

    if abstract_text:
        score += 10
    else:
        score -= 20

    return score


def fetch_papers_for_search(search_term):
    params = {
        "filter": "from_publication_date:2024-01-01",
        "search": search_term,
        "sort": "cited_by_count:desc",
        "per-page": 25,
    }

    response = requests.get(OPENALEX_URL, params=params)
    data = response.json()

    if "results" not in data:
        print("Unexpected OpenAlex response:")
        print(data)
        return []

    papers = []

    for paper in data["results"]:
        paper["search_term"] = search_term
        paper["score"] = score_paper(paper, search_term)
        papers.append(paper)

    return papers


print("\nCollecting papers...\n")

all_papers = []

for search_term in SEARCH_TERMS:
    print(f"Searching: {search_term}")
    all_papers.extend(fetch_papers_for_search(search_term))


deduped_papers = {}

for paper in all_papers:
    unique_id = paper.get("doi") or paper.get("id") or paper.get("title")

    if unique_id not in deduped_papers:
        deduped_papers[unique_id] = paper
    else:
        if paper["score"] > deduped_papers[unique_id]["score"]:
            deduped_papers[unique_id] = paper


ranked_papers = sorted(
    deduped_papers.values(),
    key=lambda paper: paper["score"],
    reverse=True,
)

selected_papers = ranked_papers[:8]

email_content = "Weekly IR Research Digest\n\n"
email_content += "Selected using multiple topic searches, deduplication, and relevance scoring.\n\n"

papers_processed = 0

for paper in selected_papers:
    title = paper.get("title", "No title")
    abstract_text = reconstruct_abstract(paper.get("abstract_inverted_index"))
    doi = paper.get("doi", "No DOI")
    publication_year = paper.get("publication_year", "Unknown year")
    journal = get_journal(paper)
    cited_by_count = paper.get("cited_by_count", 0)
    search_term = paper.get("search_term", "Unknown")
    score = round(paper.get("score", 0), 2)

    if not abstract_text:
        continue

    prompt = f"""
You are an international relations research assistant.

Summarize this paper and extract:

1. Main argument
2. Research method
3. Dataset or evidence used
4. Key findings
5. Why this matters for IR scholars
6. Why this is relevant to research on AI, infrastructure, political economy, security, state capacity, or great power competition

Be concise but useful. If the method or dataset is not clear from the abstract, say that clearly.

Paper title:
{title}

Journal:
{journal}

Year:
{publication_year}

DOI:
{doi}

Citation count:
{cited_by_count}

Search topic:
{search_term}

Abstract:
{abstract_text}
"""

    completion = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )

    summary = completion.choices[0].message.content

    paper_text = f"""
================================================================================
TITLE: {title}
JOURNAL: {journal}
YEAR: {publication_year}
DOI: {doi}
CITATIONS: {cited_by_count}
SEARCH TOPIC: {search_term}
RELEVANCE SCORE: {score}
================================================================================

{summary}

"""

    print(paper_text)
    email_content += paper_text
    papers_processed += 1


if papers_processed == 0:
    email_content += """
No matching papers were found this week using the current filters.

You may want to broaden the search terms, journal list, or publication date filter.
"""


sender = os.environ["EMAIL_ADDRESS"]
password = os.environ["EMAIL_PASSWORD"]

msg = MIMEText(email_content)
msg["Subject"] = "Weekly IR Research Digest"
msg["From"] = sender
msg["To"] = sender

with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
    server.login(sender, password)
    server.send_message(msg)

print("Email sent successfully.")
