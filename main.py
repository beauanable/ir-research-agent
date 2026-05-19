import requests

url = "https://api.openalex.org/works"

params = {
    "search": "International Organization international relations",
    "sort": "publication_date:desc",
    "per-page": 5
}

response = requests.get(url, params=params)
data = response.json()

print("\nLatest International Relations Papers:\n")

if "results" not in data:
    print("OpenAlex returned an unexpected response:")
    print(data)
    raise SystemExit(1)

for paper in data["results"]:
    title = paper.get("title", "No title")
    year = paper.get("publication_year", "Unknown year")
    doi = paper.get("doi", "No DOI")

    print(f"Title: {title}")
    print(f"Year: {year}")
    print(f"DOI: {doi}")
    print("-" * 50)
