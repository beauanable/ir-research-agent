import os
import json
import tempfile
import math
import hashlib

import requests
from openai import OpenAI
from pypdf import PdfReader
from supabase import create_client

# Validate required environment variables
def validate_env():
    required = ["OPENAI_API_KEY", "SUPABASE_URL", "SUPABASE_SECRET_KEY"]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")

validate_env()

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"])

EMBEDDING_MODEL = "text-embedding-3-small"
OPENALEX_URL = "https://api.openalex.org/works"
UNPAYWALL_URL = "https://api.unpaywall.org/v2"
UNPAYWALL_EMAIL = os.environ.get("EMAIL_ADDRESS", "research@example.com")

TOP_IR_JOURNALS = [
    "International Organization",
    "International Security",
    "World Politics",
    "International Studies Quarterly",
    "European Journal of International Relations",
    "Review of International Political Economy",
    "Security Studies",
    "Journal of Conflict Resolution",
    "International Affairs",
    "Journal of Strategic Studies",
]

TOP_PAPERS_TO_PULL = 50
YEAR_MIN = 2010
YEAR_MAX = 2025

METHOD_CATEGORIES = [
    "Case Study", "Comparative Case Study", "Process Tracing",
    "Historical Analysis", "Discourse Analysis", "Content Analysis",
    "Interview-Based Research", "Regression Analysis", "Time Series Analysis",
    "Event Study", "Survey / Experiment", "Formal Modeling / Game Theory",
    "Mixed Methods", "Systematic Literature Review", "Meta-Analysis",
    "Conceptual / Theoretical", "Policy Analysis", "Other",
]


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
    return [u for u in candidates if u and not (u in seen or seen.add(u))]


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
        return [u for u in candidates if u and not (u in seen or seen.add(u))]
    except Exception as e:
        print(f"Unpaywall lookup failed for {doi}: {e}")
        return []


def extract_pdf_text(pdf_url):
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/pdf,text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://scholar.google.com/",
        }
        response = requests.get(pdf_url, headers=headers, timeout=30, allow_redirects=True)
        if response.status_code != 200:
            print(f"PDF download failed {response.status_code}: {pdf_url}")
            return None
        content_type = response.headers.get("Content-Type", "").lower()
        if "pdf" not in content_type:
            print(f"Not a PDF ({content_type}): {pdf_url}")
            return None
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(response.content)
            pdf_path = tmp.name
        reader = PdfReader(pdf_path)
        full_text = ""
        for page in reader.pages[:20]:
            try:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"
            except Exception:
                continue
        if len(full_text.strip()) < 1000:
            return None
        return full_text[:20000]
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
    return " ".join(word for _, word in word_positions)


def create_embedding(text):
    try:
        response = client.embeddings.create(model=EMBEDDING_MODEL, input=text)
        return response.data[0].embedding
    except Exception as e:
        print(f"Embedding failed: {e}")
        return None


def create_chunk_id(title, doi, chunk_index, chunk_text):
    base = f"{doi or title}_{chunk_index}_{chunk_text[:200]}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def chunk_text(text, is_abstract=False, max_chars=3000, overlap_chars=300):
    if not text:
        return []
    text = text.strip()
    if is_abstract:
        return [text]

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


def load_existing_chunk_ids():
    try:
        result = supabase.table("chunks").select("chunk_id").execute()
        return set(row["chunk_id"] for row in result.data)
    except Exception as e:
        print(f"Failed to load existing chunk IDs: {e}")
        return set()


def save_chunks_to_supabase(paper_record, existing_chunk_ids):
    abstract = paper_record.get("abstract") or ""
    full_text = paper_record.get("full_text") or ""

    chunks_to_embed = []
    if abstract:
        for chunk in chunk_text(abstract, is_abstract=True):
            chunks_to_embed.append(("abstract", chunk))
    if full_text:
        for chunk in chunk_text(full_text, is_abstract=False):
            chunks_to_embed.append(("foundational", chunk))

    if not chunks_to_embed:
        print(f"No text to chunk for: {paper_record.get('title')}")
        return 0

    saved = 0
    for index, (source_type, chunk) in enumerate(chunks_to_embed):
        chunk_id = create_chunk_id(
            paper_record.get("title"),
            paper_record.get("doi"),
            index,
            chunk
        )

        if chunk_id in existing_chunk_ids:
            print(f"Skipping existing chunk: {chunk_id}")
            continue

        embedding = create_embedding(chunk)

        record = {
            "chunk_id": chunk_id,
            "title": paper_record.get("title"),
            "authors": paper_record.get("authors"),
            "journal": paper_record.get("journal"),
            "year": paper_record.get("year"),
            "doi": paper_record.get("doi"),
            "search_term": "foundational pull",
            "analysis_source": paper_record.get("analysis_source"),
            "source_type": source_type,
            "research_design": paper_record.get("research_design"),
            "method": paper_record.get("method"),
            "dataset_or_evidence": paper_record.get("dataset_or_evidence"),
            "unit_of_analysis": paper_record.get("unit_of_analysis"),
            "time_period_studied": paper_record.get("time_period_studied"),
            "geographic_focus": paper_record.get("geographic_focus"),
            "identification_strategy": paper_record.get("identification_strategy"),
            "chunk_index": index,
            "chunk_text": chunk,
            "embedding": embedding,
        }

        try:
            supabase.table("chunks").upsert(record).execute()
            existing_chunk_ids.add(chunk_id)
            saved += 1
            print(f"Saved {source_type} chunk {index}")
        except Exception as e:
            print(f"Failed to save chunk {index}: {e}")

    return saved


def fetch_top_papers():
    """
    Fetch the top cited papers from top IR journals between YEAR_MIN and YEAR_MAX.
    Pulls from each journal separately then merges and sorts by citation count.
    """
    all_papers = []

    for journal in TOP_IR_JOURNALS:
        print(f"\nFetching from: {journal}")
        try:
            params = {
                "filter": (
                    f"primary_location.source.display_name.search:{journal},"
                    f"from_publication_date:{YEAR_MIN}-01-01,"
                    f"to_publication_date:{YEAR_MAX}-12-31"
                ),
                "sort": "cited_by_count:desc",
                "per-page": 50,
            }
            response = requests.get(OPENALEX_URL, params=params, timeout=30)

            if response.status_code != 200:
                print(f"OpenAlex returned {response.status_code} for {journal}")
                continue

            data = response.json()

            if "results" not in data:
                print(f"No results for {journal}")
                continue

            for paper in data["results"]:
                paper["_source_journal"] = journal
                all_papers.append(paper)

            print(f"Found {len(data['results'])} papers from {journal}")

        except Exception as e:
            print(f"Failed to fetch {journal}: {e}")
            continue

    # Deduplicate by DOI or title, keep highest citation count
    deduped = {}
    for paper in all_papers:
        key = (paper.get("doi") or paper.get("title") or "").strip().lower()
        if not key:
            continue
        if key not in deduped or paper.get("cited_by_count", 0) > deduped[key].get("cited_by_count", 0):
            deduped[key] = paper

    # Sort by citation count and take top N
    sorted_papers = sorted(
        deduped.values(),
        key=lambda p: p.get("cited_by_count", 0),
        reverse=True
    )

    print(f"\nTotal unique papers found: {len(sorted_papers)}")
    print(f"Taking top {TOP_PAPERS_TO_PULL}")

    return sorted_papers[:TOP_PAPERS_TO_PULL]


def analyze_paper(title, journal, year, doi, cited_by_count, analysis_text, is_abstract_only):
    prompt = f"""
You are an elite international relations research assistant.

Return ONLY valid JSON with this exact structure:

{{
  "main_argument": "",
  "research_design": "",
  "method": "",
  "dataset_or_evidence": "",
  "unit_of_analysis": "",
  "time_period_studied": "",
  "geographic_focus": "",
  "identification_strategy": "",
  "key_findings": "",
  "main_limitations": "",
  "ir_scholars_relevance": "",
  "strategic_infrastructure_relevance": "",
  "summary_html": ""
}}

For the "method" field, you MUST choose exactly one category from this list:
Case Study, Comparative Case Study, Process Tracing, Historical Analysis, Discourse Analysis,
Content Analysis, Interview-Based Research, Regression Analysis, Time Series Analysis,
Event Study, Survey / Experiment, Formal Modeling / Game Theory, Systematic Literature Review,
Meta-Analysis, Mixed Methods, Conceptual / Theoretical, Policy Analysis, Other.

Use "Mixed Methods" ONLY if the paper explicitly and deliberately combines two distinct
methodological approaches. Use "Other" only if the method genuinely fits no category above.

In summary_html, use HTML paragraph formatting with bold labels.
If a field is not clearly specified, say "Not clearly specified in available text."
Do not invent methods or datasets.
Do not use markdown, asterisks, or numbered sections.

Paper title: {title}
Journal: {journal}
Year: {year}
DOI: {doi}
Citation count: {cited_by_count}
Analysis source: {"Abstract only" if is_abstract_only else "Full PDF"}

Paper text:
{analysis_text}
"""

    completion = client.chat.completions.create(
        model="gpt-4.1-mini",
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )

    try:
        return json.loads(completion.choices[0].message.content)
    except json.JSONDecodeError:
        return {k: "Not clearly specified in available text." for k in [
            "main_argument", "research_design", "method", "dataset_or_evidence",
            "unit_of_analysis", "time_period_studied", "geographic_focus",
            "identification_strategy", "key_findings", "main_limitations",
            "ir_scholars_relevance", "strategic_infrastructure_relevance", "summary_html",
        ]}


# ── Main pipeline ──────────────────────────────────────────────────────────────

print("\n=== Foundational Paper Pull ===\n")
print(f"Journals: {len(TOP_IR_JOURNALS)}")
print(f"Year range: {YEAR_MIN}-{YEAR_MAX}")
print(f"Target: top {TOP_PAPERS_TO_PULL} by citation count\n")

papers = fetch_top_papers()
existing_chunk_ids = load_existing_chunk_ids()
print(f"\nExisting chunks in Supabase: {len(existing_chunk_ids)}")

papers_processed = 0
papers_skipped = 0

for paper in papers:
    try:
        title = paper.get("title") or "No title"
        doi = paper.get("doi") or ""
        cited_by_count = paper.get("cited_by_count", 0)
        year = paper.get("publication_year")
        abstract_text = reconstruct_abstract(paper.get("abstract_inverted_index"))

        # Get journal from primary location
        primary = paper.get("primary_location") or {}
        source = primary.get("source") or {}
        journal = source.get("display_name") or paper.get("_source_journal") or ""

        authors = []
        for authorship in paper.get("authorships", []):
            author = authorship.get("author") or {}
            name = author.get("display_name")
            if name:
                authors.append(name)

        print(f"\n[{papers_processed + 1}] {title[:80]}")
        print(f"    Journal: {journal} | Year: {year} | Citations: {cited_by_count}")

        # Try PDF extraction
        pdf_urls = get_pdf_urls(paper)
        if doi:
            pdf_urls.extend(get_unpaywall_pdf_urls(doi))

        seen = set()
        pdf_urls = [u for u in pdf_urls if u and not (u in seen or seen.add(u))]

        full_text = None
        for pdf_url in pdf_urls:
            print(f"    Trying PDF: {pdf_url[:80]}")
            full_text = extract_pdf_text(pdf_url)
            if full_text:
                print(f"    PDF extraction succeeded")
                break

        if not abstract_text and not full_text:
            print(f"    No text available — skipping")
            papers_skipped += 1
            continue

        analysis_source = "Full PDF" if full_text else "Abstract Only"
        analysis_text = full_text if full_text else abstract_text
        is_abstract_only = not full_text

        # GPT analysis
        summary_data = analyze_paper(
            title, journal, year, doi,
            cited_by_count, analysis_text, is_abstract_only
        )

        paper_record = {
            "title": title,
            "authors": authors,
            "journal": journal,
            "year": year,
            "doi": doi,
            "cited_by_count": cited_by_count,
            "search_term": "foundational pull",
            "analysis_source": analysis_source,
            "abstract": abstract_text,
            "full_text": full_text,
            "main_argument": summary_data.get("main_argument"),
            "research_design": summary_data.get("research_design"),
            "method": summary_data.get("method"),
            "dataset_or_evidence": summary_data.get("dataset_or_evidence"),
            "unit_of_analysis": summary_data.get("unit_of_analysis"),
            "time_period_studied": summary_data.get("time_period_studied"),
            "geographic_focus": summary_data.get("geographic_focus"),
            "identification_strategy": summary_data.get("identification_strategy"),
            "key_findings": summary_data.get("key_findings"),
            "main_limitations": summary_data.get("main_limitations"),
        }

        saved = save_chunks_to_supabase(paper_record, existing_chunk_ids)
        print(f"    Saved {saved} chunks to Supabase")
        papers_processed += 1

    except Exception as e:
        print(f"    Error processing '{title}': {e}")
        continue

print(f"\n=== Done ===")
print(f"Papers processed: {papers_processed}")
print(f"Papers skipped (no text): {papers_skipped}")
