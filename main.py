import os
import smtplib
import json
import tempfile
from email.mime.text import MIMEText

import requests
from openai import OpenAI
from pypdf import PdfReader


client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

OPENALEX_URL = "https://api.openalex.org/works"
UNPAYWALL_URL = "https://api.unpaywall.org/v2"
UNPAYWALL_EMAIL = os.environ["EMAIL_ADDRESS"]

SEARCH_TERMS = [
    "AI geopolitics",
    "technology governance international relations",
    "international political economy infrastructure",
    "energy security geopolitics",
    "deterrence theory",
    "state capacity international relations",
    "great power competition",
    "critical infrastructure security",
    "compute power geopolitics",
    "data center geopolitics",
    "semiconductor supply chains",
    "AI infrastructure geopolitics",
    "energy infrastructure great power competition",
    "electric grid security geopolitics",
    "critical minerals geopolitics",
    "industrial policy semiconductors",
    "cloud computing national security",
    "strategic autonomy technology",
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

TIER_1_JOURNALS = [
    "International Organization",
    "International Security",
    "World Politics",
    "International Studies Quarterly",
]

TIER_2_JOURNALS = [
    "European Journal of International Relations",
    "Review of International Political Economy",
    "Security Studies",
    "Journal of Conflict Resolution",
    "International Affairs",
    "Journal of Strategic Studies",
]

TIER_3_JOURNALS = [
    "Foreign Affairs",
    "Foreign Policy",
    "Foreign Policy Analysis",
    "Survival",
    "The Washington Quarterly",
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
    "compute power",
    "data center",
    "data centers",
    "semiconductor",
    "semiconductors",
    "chip supply chain",
    "semiconductor supply chain",
    "critical minerals",
    "electric grid",
    "grid resilience",
    "grid security",
    "cloud infrastructure",
    "cloud computing",
    "technology competition",
    "technology strategy",
    "dual-use technology",
    "strategic technology",
    "energy geopolitics",
    "energy statecraft",
    "infrastructure geopolitics",
]

TECHNICAL_PENALTY_KEYWORDS = [
    "algorithm",
    "neural network",
    "machine learning model",
    "deep learning",
    "cloud architecture",
    "database",
    "data management",
    "software engineering",
    "edge computing",
    "internet of things",
    "iot",
    "smart city",
    "digital twin",
    "healthcare",
    "medical",
    "clinical",
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


SEEN_PAPERS_FILE = "seen_papers.json"
PROCESSED_PAPERS_FILE = "processed_papers.jsonl"


def dedupe_urls(urls):
    seen = set()
    clean = []

    for url in urls:
        if url and url not in seen:
            seen.add(url)
            clean.append(url)

    return clean


def get_pdf_urls(work):
    candidates = []

    best = work.get("best_oa_location") or {}
    primary = work.get("primary_location") or {}
    open_access = work.get("open_access") or {}

    if best.get("pdf_url"):
        candidates.append(best["pdf_url"])

    if primary.get("pdf_url"):
        candidates.append(primary["pdf_url"])

    for loc in work.get("locations", []) or []:
        if loc.get("pdf_url"):
            candidates.append(loc["pdf_url"])

    if open_access.get("oa_url"):
        candidates.append(open_access["oa_url"])

    seen = set()
    clean = []

    for url in candidates:
        if url and url not in seen:
            seen.add(url)
            clean.append(url)

    return clean


def get_unpaywall_pdf_urls(doi):
    if not doi:
        return []

    clean_doi = doi.replace("https://doi.org/", "").strip()

    if not clean_doi:
        return []

    try:
        response = requests.get(
            f"{UNPAYWALL_URL}/{clean_doi}",
            params={"email": UNPAYWALL_EMAIL},
            timeout=20,
        )

        if response.status_code != 200:
            print(f"Unpaywall lookup failed with status {response.status_code}: {doi}")
            return []

        data = response.json()
        candidates = []

        best = data.get("best_oa_location") or {}

        if best.get("url_for_pdf"):
            candidates.append(best["url_for_pdf"])

        for loc in data.get("oa_locations", []) or []:
            if loc.get("url_for_pdf"):
                candidates.append(loc["url_for_pdf"])

        seen = set()
        clean = []

        for url in candidates:
            if url and url not in seen:
                seen.add(url)
                clean.append(url)

        return clean

    except Exception as e:
        print(f"Unpaywall lookup failed for {doi}: {e}")
        return []


def resolve_doi_to_pdf(doi_url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/pdf",
        }

        response = requests.get(
            doi_url,
            headers=headers,
            timeout=20,
            allow_redirects=True,
        )

        final_url = response.url

        if final_url and final_url != doi_url:
            return final_url

        return None

    except Exception as e:
        print(f"DOI resolution failed for {doi_url}: {e}")
        return None


def extract_pdf_text(pdf_url):
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/pdf,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://scholar.google.com/",
        }

        response = requests.get(
            pdf_url,
            headers=headers,
            timeout=30,
            allow_redirects=True,
        )

        if response.status_code != 200:
            print(f"PDF download failed with status {response.status_code}: {pdf_url}")
            return None

        content_type = response.headers.get("Content-Type", "").lower()

        if "pdf" not in content_type:
            print(f"URL was not a PDF. Content-Type was {content_type}: {pdf_url}")
            return None

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(response.content)
            pdf_path = tmp_file.name

        reader = PdfReader(pdf_path)
        full_text = ""

        for page in reader.pages[:20]:
            try:
                text = page.extract_text()

                if text:
                    full_text += text + "\n"

            except Exception as page_error:
                print(f"Skipping unreadable PDF page: {page_error}")
                continue

        if len(full_text.strip()) < 1000:
            print(f"PDF text too short after extraction: {pdf_url}")
            return None

        return full_text[:50000]

    except Exception as e:
        print(f"PDF extraction failed for {pdf_url}: {e}")
        return None


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


def get_paper_id(paper):
    paper_id = paper.get("doi") or paper.get("id") or paper.get("title")

    if not paper_id:
        return None

    return paper_id.strip().lower()


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
    abstract_text = reconstruct_abstract(paper.get("abstract_inverted_index"))
    journal = get_journal(paper)
    cited_by_count = paper.get("cited_by_count") or 0
    year = paper.get("publication_year") or 0

    combined_text = f"{title} {abstract_text}"

    strategic_score = calculate_strategic_score(combined_text)
    ir_score = calculate_ir_score(combined_text)

    if journal in TIER_1_JOURNALS:
        score += 60
    elif journal in TIER_2_JOURNALS:
        score += 45
    elif journal in TIER_3_JOURNALS:
        score += 30
    elif journal in CORE_IR_JOURNALS:
        score += 20

    if year >= 2026:
        score += 20
    elif year == 2025:
        score += 15
    elif year == 2024:
        score += 8

    score += min(cited_by_count, 100) / 5
    score += strategic_score
    score += ir_score

    for keyword in TECHNICAL_PENALTY_KEYWORDS:
        if keyword in combined_text.lower():
            score -= 15

    for term_word in search_term.lower().split():
        if term_word in combined_text.lower():
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
    ir_score = paper.get("ir_score", 0)

    title = paper.get("title") or ""
    abstract_text = reconstruct_abstract(paper.get("abstract_inverted_index"))
    combined_text = f"{title} {abstract_text}".lower()

    if journal in CORE_IR_JOURNALS:
        return True

    if strategic_score >= 20 and ir_score >= 6:
        return True

    geopolitical_terms = [
        "geopolitics",
        "geopolitical",
        "great power",
        "national security",
        "state capacity",
        "industrial policy",
        "strategic competition",
        "supply chain security",
        "technological sovereignty",
        "economic statecraft",
        "international relations",
        "foreign policy",
    ]

    if strategic_score >= 20:
        for term in geopolitical_terms:
            if term in combined_text:
                return True

    return False


def fetch_papers_for_search(search_term):
    papers = []
    cursor = "*"
    pages_to_fetch = 3

    for page_number in range(pages_to_fetch):
        params = {
            "filter": "from_publication_date:2024-01-01",
            "search": search_term,
            "sort": "cited_by_count:desc",
            "per-page": 200,
            "cursor": cursor,
        }

        response = requests.get(OPENALEX_URL, params=params)
        data = response.json()

        if "results" not in data:
            print("Unexpected OpenAlex response:")
            print(data)
            break

        for paper in data["results"]:
            paper["search_term"] = search_term
            paper["score"] = score_paper(paper, search_term)

            if should_include_paper(paper):
                papers.append(paper)

        cursor = data.get("meta", {}).get("next_cursor")

        if not cursor:
            break

    return papers

def load_seen_papers():
    if not os.path.exists(SEEN_PAPERS_FILE):
        return set()

    with open(SEEN_PAPERS_FILE, "r", encoding="utf-8") as file:
        return set(item.strip().lower() for item in json.load(file))


def save_seen_papers(seen_papers):
    with open(SEEN_PAPERS_FILE, "w", encoding="utf-8") as file:
        json.dump(sorted(list(seen_papers)), file, indent=2)


def save_processed_paper(record):
    with open(PROCESSED_PAPERS_FILE, "a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


print("\nCollecting papers...\n")

all_papers = []

for search_term in SEARCH_TERMS:
    print(f"Searching: {search_term}")
    all_papers.extend(fetch_papers_for_search(search_term))


deduped_papers = {}

for paper in all_papers:
    unique_id = get_paper_id(paper)

    if not unique_id:
        continue

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

seen_papers = load_seen_papers()
new_ranked_papers = []

for paper in ranked_papers:
    unique_id = get_paper_id(paper)

    if unique_id and unique_id not in seen_papers:
        new_ranked_papers.append(paper)

print(f"Total papers found: {len(all_papers)}")
print(f"Deduped papers: {len(deduped_papers)}")
print(f"Seen papers loaded: {len(seen_papers)}")
print(f"New papers after seen filter: {len(new_ranked_papers)}")

selected_papers = new_ranked_papers[:30]
MAX_PAPERS_TO_EMAIL = 8

email_content = """
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.5; font-size: 14px;">

<h2>Weekly IR Research Digest</h2>

<p><b>Selection Logic:</b><br>
High-impact core IR journals are always prioritized.<br>
Adjacent disciplines are included only if strongly related to great power strategy,
energy infrastructure, compute power, state capacity, strategic technology,
or geopolitical competition.
</p>

<hr>
"""

papers_processed = 0

for paper in selected_papers:
    if papers_processed >= MAX_PAPERS_TO_EMAIL:
        break

    title = paper.get("title", "No title")
    abstract_text = reconstruct_abstract(paper.get("abstract_inverted_index"))
    doi = paper.get("doi", "No DOI")

    pdf_urls = get_pdf_urls(paper)

    if doi and doi != "No DOI":
        pdf_urls.extend(get_unpaywall_pdf_urls(doi))

    resolved_urls = []

    for url in pdf_urls:
        if "doi.org" in url:
            resolved = resolve_doi_to_pdf(url)

            if resolved:
                resolved_urls.append(resolved)

        resolved_urls.append(url)

    pdf_urls.extend(resolved_urls)

    seen_pdf_urls = set()
    pdf_urls = [
        url for url in pdf_urls
        if url and not (url in seen_pdf_urls or seen_pdf_urls.add(url))
    ]

    full_text = None

    for pdf_url in pdf_urls:
        print(f"Attempting PDF extraction: {pdf_url}")

        full_text = extract_pdf_text(pdf_url)

        if full_text:
            print(f"PDF extraction succeeded: {pdf_url}")
            break

    analysis_source = (
        "Full PDF"
        if full_text
        else "Abstract Only"
    )

    publication_year = paper.get("publication_year", "Unknown year")
    journal = get_journal(paper)

    authors = []

    for authorship in paper.get("authorships", []):
        author = authorship.get("author") or {}
        author_name = author.get("display_name")

        if author_name:
            authors.append(author_name)

    authors_text = ", ".join(authors[:6])

    if len(authors) > 6:
        authors_text += ", et al."

    cited_by_count = paper.get("cited_by_count", 0)
    search_term = paper.get("search_term", "Unknown")
    total_score = round(paper.get("score", 0), 2)
    strategic_score = paper.get("strategic_score", 0)
    ir_score = paper.get("ir_score", 0)

    if not abstract_text and not full_text:
        continue

    is_core_ir = journal in CORE_IR_JOURNALS

    analysis_text = (
        full_text
        if full_text
        else abstract_text
    )

    prompt = f"""
You are an elite international relations research assistant.

Provide the following sections using HTML formatting only.

Each section should be concise, analytical, and specific.

Use this exact structure:

<p><b>Main argument:</b> ...</p>

<p><b>Research design:</b> ...</p>

<p><b>Method:</b> ...</p>

<p><b>Dataset or evidence:</b> ...</p>

<p><b>Unit of analysis:</b> ...</p>

<p><b>Time period studied:</b> ...</p>

<p><b>Geographic focus:</b> ...</p>

<p><b>Identification strategy:</b> ...</p>

<p><b>Key findings:</b> ...</p>

<p><b>Main limitations:</b> ...</p>

<p><b>Why this matters for IR scholars:</b> ...</p>

Only include this final section if the paper is strategically relevant to great power competition,
energy infrastructure, compute power, AI governance, state capacity,
industrial policy, technological competition, or geopolitical strategy:

<p><b>Why this matters for strategic infrastructure research:</b> ...</p>

If the abstract or paper text does not clearly specify a category,
explicitly say "Not clearly specified in available text."

Do not invent methods or datasets.
Do not use markdown.
Do not use asterisks.
Do not number sections.
Use short readable paragraphs.

Paper title:
{title}

Journal:
{journal}

Is this a core IR journal?
{is_core_ir}

Year:
{publication_year}

DOI:
{doi}

Citation count:
{cited_by_count}

Search topic:
{search_term}

Paper Text:
{analysis_text}
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
<h3>{title}</h3>

<p>
<b>Authors:</b> {authors_text}<br>
<b>Journal:</b> {journal}<br>
<b>Year:</b> {publication_year}<br>
<b>DOI:</b> <a href="{doi}">{doi}</a><br>
<b>Citations:</b> {cited_by_count}<br>
<b>Search Topic:</b> {search_term}<br>
<b>Analysis Source:</b> {analysis_source}<br>
<b>Total Score:</b> {total_score}<br>
<b>Strategic Score:</b> {strategic_score}<br>
<b>IR Score:</b> {ir_score}
</p>

{summary}

<hr>
"""

    processed_record = {
        "title": title,
        "authors": authors,
        "journal": journal,
        "year": publication_year,
        "doi": doi,
        "cited_by_count": cited_by_count,
        "search_term": search_term,
        "analysis_source": analysis_source,
        "total_score": total_score,
        "strategic_score": strategic_score,
        "ir_score": ir_score,
        "abstract": abstract_text,
        "full_text": full_text,
        "summary_html": summary,
        "pdf_urls_checked": pdf_urls,
    }

    save_processed_paper(processed_record)

    print(paper_text)
    email_content += paper_text
    papers_processed += 1

    unique_id = get_paper_id(paper)

    if unique_id:
        seen_papers.add(unique_id)


if papers_processed == 0:
    email_content += """
<p>No matching papers were found.</p>

<p>You may want to broaden search terms, add journals, or lower the strategic relevance threshold.</p>
"""


email_content += """
</body>
</html>
"""

save_seen_papers(seen_papers)

sender = os.environ["EMAIL_ADDRESS"]
password = os.environ["EMAIL_PASSWORD"]

msg = MIMEText(email_content, "html")
msg["Subject"] = "Weekly IR Research Digest"
msg["From"] = sender
msg["To"] = sender

with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
    server.login(sender, password)
    server.send_message(msg)

print("Email sent successfully.")
