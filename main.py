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

CORE_IR_JOURNALS = [
    "International Organization",
    "International Security",
    "International Studies Quarterly",
    "World Politics",
    "European Journal of International Relations",
    "Review of International Political Economy",
    "Security Studies",
    "Journal of Conflict Resolution",
    "Foreign Affairs",
    "Foreign Policy",
    "Foreign Policy Analysis",
    "International Affairs",
    "Survival",
    "The Washington Quarterly",
    "Journal of Strategic Studies",
]

STRATEGIC_KEYWORDS = [
    "great power competition",
    "strategic competition",
    "industrial policy",
    "compute infrastructure",
    "data centers",
    "semiconductors",
    "energy infrastructure",
    "critical infrastructure",
    "ai governance",
    "state capacity",
    "technological sovereignty",
    "supply chains",
    "rare earths",
    "grid security",
    "energy transition",
    "geoeconomics",
    "techno-nationalism",
    "strategic autonomy",
    "digital infrastructure",
    "cloud computing",
    "ai race",
    "national security",
    "energy security",
    "infrastructure resilience",
]

GENERAL_IR_KEYWORDS = [
    "alliance",
    "war",
    "deterrence",
    "security",
    "foreign policy",
    "international organization",
    "trade",
    "geopolitics",
    "international relations",
    "conflict",
    "sanctions",
    "military",
]


def reconstruct_abstract(abstract_inverted_index):
    if not abstract_inverted_index:
        return ""

    word_positions = []

    for word, positions in abstract_inverted_index.items():
        for position in positions:
            word_positions.append((position, word))

    word_positions.sort()

    return " ".join(
        word for position, word in word_positions
    )


def get_journal(paper):
    primary_location = paper.get("primary_location") or {}
    source = primary_location.get("source") or {}

    return source.get("display_name", "")


def calculate_strategic_score(text):
    score = 0

    lower_text = text.lower()

    for keyword in STRATEGIC_KEYWORDS:
        if keyword in lower_text:
            score += 10

    return score


def calculate_ir_score(text):
    score = 0

    lower_text = text.lower()

    for keyword in GENERAL_IR_KEYWORDS:
        if keyword in lower_text:
            score += 3

    return score


def score_paper(paper, search_term):
    score = 0

    title = paper.get("title") or ""

    abstract_text = reconstruct_abstract(
        paper.get("abstract_inverted_index")
    )

    journal = get_journal(paper)

    cited_by_count = paper.get("cited_by_count") or 0

    year = paper.get("publication_year") or 0

    combined_text = f"{title} {abstract_text}"

    strategic_score = calculate_strategic_score(combined_text)

    ir_score = calculate_ir_score(combined_text)

    if journal in CORE_IR_JOURNALS:
        score += 40

    if year >= 2026:
        score += 20
    elif year == 2025:
        score += 15
    elif year == 2024:
        score += 8

    score += min(cited_by_count, 100) / 5

    score += strategic_score

    score += ir_score

    for term_word in search_term.lower().split():
        if term_word.lower() in combined_text.lower():
            score += 2

    if abstract_text:
        score += 10
    else:
        score -= 20

    paper["strategic_score"] = strategic_score
    paper["ir_score"] = ir_score

    return score


def should_include_paper(paper):
    journal = get_journal(paper)

    strategic_score = paper.get("strategic_score", 0)

    if journal in CORE_IR_JOURNALS:
        return True

    if strategic_score >= 20:
        return True

    return False


def fetch_papers_for_search(search_term):
    params = {
        "filter": "from_publication_date:2024-01-01",
        "search": search_term,
        "sort": "cited_by_count:desc",
        "per-page": 25,
    }

    response = requests.get(
        OPENALEX_URL,
        params=params
    )

    data = response.json()

    if "results" not in data:
        print("Unexpected OpenAlex response:")
        print(data)
        return []

    papers = []

    for paper in data["results"]:

        paper["search_term"] = search_term

        paper["score"] = score_paper(
            paper,
            search_term
        )

        if should_include_paper(paper):
            papers.append(paper)

    return papers


print("\nCollecting papers...\n")

all_papers = []

for search_term in SEARCH_TERMS:

    print(f"Searching: {search_term}")

    papers = fetch_papers_for_search(search_term)

    all_papers.extend(papers)


deduped_papers = {}

for paper in all_papers:

    unique_id = (
        paper.get("doi")
        or paper.get("id")
        or paper.get("title")
    )

    if unique_id not in deduped_papers:
        deduped_papers[unique_id] = paper

    else:
        existing_score = deduped_papers[unique_id]["score"]

        if paper["score"] > existing_score:
            deduped_papers[unique_id] = paper


ranked_papers = sorted(
    deduped_papers.values(),
    key=lambda paper: paper["score"],
    reverse=True,
)

selected_papers = ranked_papers[:10]

email_content = """
Weekly IR Research Digest

Selection Logic:
- High-impact core IR journals always prioritized
- Adjacent disciplines only included if strongly related to:
  great power strategy, energy infrastructure, compute power,
  state capacity, strategic technology, or geopolitical competition

"""

papers_processed = 0

for paper in selected_papers:

    title = paper.get("title", "No title")

    abstract_text = reconstruct_abstract(
        paper.get("abstract_inverted_index")
    )

    doi = paper.get("doi", "No DOI")

    publication_year = paper.get(
        "publication_year",
        "Unknown year"
    )

    journal = get_journal(paper)

    cited_by_count = paper.get(
        "cited_by_count",
        0
    )

    search_term = paper.get(
        "search_term",
        "Unknown"
    )

    total_score = round(
        paper.get("score", 0),
        2
    )

    strategic_score = paper.get(
        "strategic_score",
        0
    )

    ir_score = paper.get(
        "ir_score",
        0
    )

    if not abstract_text:
        continue

    prompt = f"""
You are an elite international relations research assistant.

Provide:

1. Main argument
2. Research method
3. Dataset or evidence used
4. Key findings
5. Why this matters for IR scholars
6. Why this matters for research on:
   - great power competition
   - energy infrastructure
   - compute power
   - AI governance
   - state capacity
   - geopolitical strategy

Be concise but analytically useful.

If the abstract does not clearly specify the method or dataset,
explicitly say that.

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
TOTAL SCORE: {total_score}
STRATEGIC SCORE: {strategic_score}
IR SCORE: {ir_score}
================================================================================

{summary}

"""

    print(paper_text)

    email_content += paper_text

    papers_processed += 1


if papers_processed == 0:

    email_content += """
No matching papers were found.

You may want to:
- broaden search terms
- add journals
- lower strategic relevance threshold
"""


sender = os.environ["EMAIL_ADDRESS"]

password = os.environ["EMAIL_PASSWORD"]

msg = MIMEText(email_content)

msg["Subject"] = "Weekly IR Research Digest"

msg["From"] = sender

msg["To"] = sender


with smtplib.SMTP_SSL(
    "smtp.gmail.com",
    465
) as server:

    server.login(sender, password)

    server.send_message(msg)


print("Email sent successfully.")
