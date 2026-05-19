import os
import smtplib
from email.mime.text import MIMEText

import requests
from openai import OpenAI


client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

url = "https://api.openalex.org/works"

params = {
    "filter": "from_publication_date:2026-01-01",
    "search": "international relations AI geopolitics political economy security deterrence infrastructure state capacity",
    "sort": "cited_by_count:desc",
    "per-page": 25
}

response = requests.get(url, params=params)
data = response.json()

print("\nIR Research Digest\n")

if "results" not in data:
    print("Unexpected API response:")
    print(data)
    raise SystemExit(1)

TOP_JOURNALS = [
    "International Organization",
    "International Security",
    "International Studies Quarterly",
    "World Politics",
    "European Journal of International Relations",
    "Review of International Political Economy",
    "Security Studies",
    "Journal of Conflict Resolution"
]

email_content = "Weekly IR Research Digest\n\n"
papers_processed = 0

for paper in data["results"]:

    journal = (
        paper.get("primary_location", {})
        .get("source", {})
        .get("display_name", "")
    )

    if journal not in TOP_JOURNALS:
        continue

    title = paper.get("title", "No title")
    abstract = paper.get("abstract_inverted_index")
    doi = paper.get("doi", "No DOI")
    publication_year = paper.get("publication_year", "Unknown year")

    if not abstract:
        continue

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

Be concise but useful. If the method or dataset is not clear from the abstract, say that clearly.

Paper title:
{title}

Journal:
{journal}

Year:
{publication_year}

DOI:
{doi}

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

    paper_text = f"""
================================================================================
TITLE: {title}
JOURNAL: {journal}
YEAR: {publication_year}
DOI: {doi}
================================================================================

{summary}

"""

    print(paper_text)

    email_content += paper_text
    papers_processed += 1

if papers_processed == 0:
    email_content += """
No matching papers were found this week using the current filters.

You may want to broaden the journal list, search terms, or publication date filter.
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
