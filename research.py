# ============================================================
#  RESEARCH MODULE — SearXNG Web Research
#  Searches the web for information about a topic before
#  script generation, giving the LLM factual grounding.
#
#  Requires SearXNG running on localhost:8080
#  Start with: docker run -d --name searxng -p 8080:8080 searxng/searxng
# ============================================================

import re
import json
import time
import requests
from config import OLLAMA_MODEL, OLLAMA_BASE_URL

# SearXNG settings
SEARXNG_URL    = "http://localhost:8080"
NUM_QUERIES    = 8      # number of search queries to generate
MAX_RESULTS    = 5      # results per query
REQUEST_DELAY  = 1.0    # seconds between searches (be polite to SearXNG)
REQUEST_TIMEOUT = 10    # seconds per search request


# ------------------------------------------------------------
#  Step 1 — Generate smart search queries for the topic
# ------------------------------------------------------------

def _generate_queries(topic: str) -> list[str]:
    """
    Ask the LLM to generate targeted search queries for the topic.
    Returns a list of search query strings.
    """
    url = f"{OLLAMA_BASE_URL}/api/chat"

    system = """You are a research assistant helping to find information for a documentary video.
Generate specific, targeted search queries that will find:
- Key facts, dates, and timeline of events
- Controversies, scandals, and conflicts involved
- Key figures and their motivations
- Lesser-known or suppressed details
- Consequences and lasting impact

Return ONLY a JSON array of search query strings, nothing else, no markdown.
Example: ["query one", "query two", "query three"]"""

    user = (
        f"Generate {NUM_QUERIES} targeted search queries to research this topic "
        f"for an interesting youtube video:\n\n{topic}"
    )

    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user}
        ]
    }

    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json=payload,
        timeout=120
    )
    response.raise_for_status()
    raw = response.json()["message"]["content"].strip()

    # Parse JSON array
    cleaned = re.sub(r"```json|```", "", raw).strip()
    try:
        queries = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try line-by-line fallback
        queries = []
        for line in cleaned.splitlines():
            line = line.strip().strip('"').strip("'").strip(",")
            if line and len(line) > 5:
                queries.append(line)

    # Fallback if parsing completely fails
    if not queries:
        queries = [
            topic,
            f"{topic} history",
            f"{topic} controversy scandal",
            f"{topic} facts timeline",
        ]

    return queries[:NUM_QUERIES]


# ------------------------------------------------------------
#  Step 2 — Execute searches via SearXNG
# ------------------------------------------------------------

def _search(query: str) -> list[dict]:
    """
    Search SearXNG for a query.
    Returns a list of result dicts with title, url, content.
    """
    params = {
        "q":        query,
        "format":   "json",
        "language": "en",
        "categories": "general",
    }

    try:
        response = requests.get(
            f"{SEARXNG_URL}/search",
            params=params,
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        data    = response.json()
        results = data.get("results", [])

        # Extract useful fields only
        cleaned = []
        for r in results[:MAX_RESULTS]:
            content = r.get("content", "").strip()
            title   = r.get("title", "").strip()
            url     = r.get("url", "").strip()
            if content and title:
                cleaned.append({
                    "title":   title,
                    "url":     url,
                    "content": content,
                })
        return cleaned

    except requests.RequestException as e:
        print(f"   ⚠️  Search failed for '{query[:50]}': {e}")
        return []


# ------------------------------------------------------------
#  Step 3 — Summarise research into a usable brief
# ------------------------------------------------------------

def _summarise_research(topic: str, all_results: list[dict]) -> str:
    """
    Ask the LLM to synthesise all search results into a
    concise research brief for script writing.
    """
    if not all_results:
        return ""

    # Format results for the prompt
    results_text = ""
    for i, r in enumerate(all_results, 1):
        results_text += f"\n[{i}] {r['title']}\n{r['content']}\n"

    system = """You are a research analyst preparing a briefing for a documentary scriptwriter.
Synthesise the provided search results into a concise research brief covering:
- Key facts, dates, and verified timeline
- The most dramatic and controversial elements
- Key figures and their roles
- Lesser-known details that would surprise viewers
- Unresolved questions or ongoing debates

Be factual and specific. Include dates and names where available.
Write in clear prose, 3 to 5 paragraphs. Do not add commentary or opinions."""

    user = (
        f"Topic: {topic}\n\n"
        f"Search results:\n{results_text}\n\n"
        f"Write a research brief for the scriptwriter."
    )

    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user}
        ]
    }

    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json=payload,
        timeout=300
    )
    response.raise_for_status()
    return response.json()["message"]["content"].strip()


# ------------------------------------------------------------
#  Main function
# ------------------------------------------------------------

def research_topic(topic: str) -> str:
    """
    Research a topic using SearXNG and summarise findings.
    Returns a research brief string to be injected into the
    script generation prompt.
    """
    print(f"🔍 Researching: '{topic}'...")

    # Generate targeted queries
    print(f"   Generating search queries...")
    queries = _generate_queries(topic)
    print(f"   Generated {len(queries)} queries")

    # Execute all searches
    all_results = []
    for i, query in enumerate(queries, 1):
        print(f"   Searching ({i}/{len(queries)}): {query[:60]}...")
        results = _search(query)
        all_results.extend(results)
        if i < len(queries):
            time.sleep(REQUEST_DELAY)

    # Deduplicate by URL
    seen_urls = set()
    unique_results = []
    for r in all_results:
        if r["url"] not in seen_urls:
            seen_urls.add(r["url"])
            unique_results.append(r)

    print(f"   Found {len(unique_results)} unique sources")

    if not unique_results:
        print(f"   ⚠️  No search results found. Proceeding without research.")
        return ""

    # Summarise into a research brief
    print(f"   Synthesising research brief...")
    brief = _summarise_research(topic, unique_results)

    print(f"✅ Research complete ({len(brief.split())} words in brief)")
    return brief


# ------------------------------------------------------------
#  Entry point for isolated testing
# ------------------------------------------------------------

if __name__ == "__main__":
    test_topic = "The Avro Arrow — how Canada built the world's most advanced fighter jet"

    print("🧪 Testing research module...")
    brief = research_topic(test_topic)

    print(f"\n{'='*60}")
    print("RESEARCH BRIEF:")
    print("="*60)
    print(brief)
    print(f"\n✅ Research test complete. ({len(brief.split())} words)")