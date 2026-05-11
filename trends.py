# ============================================================
#  TRENDS MODULE — Fetch trending topics from Google Trends
#
#  Primary:  Google Trends RSS feed (no auth, no dependencies)
#  Fallback: pytrends library
#
#  Results cached per-region for 30 minutes to avoid
#  hammering Google and to make rapid button clicks instant.
# ============================================================

import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

# Cache: { region_code: {"topics": [...], "fetched_at": float} }
_cache: dict = {}
CACHE_TTL_SECONDS = 1800  # 30 minutes

# Supported regions
REGIONS = {
    "US":     {"label": "US",     "geo": "US", "pytrends_pn": "united_states"},
    "CA":     {"label": "Canada", "geo": "CA", "pytrends_pn": "canada"},
    "GLOBAL": {"label": "World",  "geo": "",   "pytrends_pn": "united_states"},
}

RSS_URL     = "https://trends.google.com/trending/rss?geo={geo}"
MAX_TOPICS  = 20

RSS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control":   "no-cache",
}


# ------------------------------------------------------------
#  RSS fetch (primary)
# ------------------------------------------------------------

def _fetch_via_rss(geo: str) -> list[str]:
    """
    Fetch trending topics from Google Trends RSS feed.
    Returns a list of topic strings, or raises on failure.
    """
    url = RSS_URL.format(geo=geo)
    response = requests.get(url, headers=RSS_HEADERS, timeout=15)
    response.raise_for_status()

    root   = ET.fromstring(response.content)
    topics = [
        item.find("title").text.strip()
        for item in root.findall(".//item")
        if item.find("title") is not None and item.find("title").text
    ]

    if not topics:
        raise ValueError("RSS feed returned no topics")

    return topics[:MAX_TOPICS]


# ------------------------------------------------------------
#  pytrends fetch (fallback)
# ------------------------------------------------------------

def _fetch_via_pytrends(pn: str) -> list[str]:
    """
    Fetch trending topics via pytrends.
    Returns a list of topic strings, or raises on failure.
    """
    try:
        from pytrends.request import TrendReq
    except ImportError:
        raise RuntimeError("pytrends not installed. Run: pip install pytrends")

    pytrends = TrendReq(hl="en-US", tz=300, timeout=(10, 30))
    df = pytrends.trending_searches(pn=pn)
    topics = df[0].dropna().tolist()

    if not topics:
        raise ValueError("pytrends returned no topics")

    return [str(t).strip() for t in topics[:MAX_TOPICS]]


# ------------------------------------------------------------
#  Public API
# ------------------------------------------------------------

def get_trending(region: str = "US") -> dict:
    """
    Return trending topics for the given region code.
    region: "US" | "CA" | "GLOBAL"

    Returns:
        {
            "region":    "US",
            "topics":    ["Topic 1", "Topic 2", ...],
            "cached":    True/False,
            "fetched_at": "HH:MM:SS",
            "source":    "rss" | "pytrends",
            "error":     None or error string,
        }
    """
    region = region.upper()
    if region not in REGIONS:
        region = "US"

    cfg = REGIONS[region]

    # Return cached result if still fresh
    if region in _cache:
        cached = _cache[region]
        age    = time.time() - cached["fetched_at"]
        if age < CACHE_TTL_SECONDS:
            return {
                "region":     region,
                "topics":     cached["topics"],
                "cached":     True,
                "fetched_at": cached["fetched_at_str"],
                "source":     cached["source"],
                "error":      None,
            }

    # Try RSS first, fall back to pytrends
    topics = []
    source = None
    error  = None

    try:
        topics = _fetch_via_rss(cfg["geo"])
        source = "rss"
        print(f"✅ Trends [{region}]: {len(topics)} topics via RSS")
    except Exception as e_rss:
        print(f"⚠️  Trends RSS failed [{region}]: {e_rss} — trying pytrends...")
        try:
            topics = _fetch_via_pytrends(cfg["pytrends_pn"])
            source = "pytrends"
            print(f"✅ Trends [{region}]: {len(topics)} topics via pytrends")
        except Exception as e_pt:
            error = f"RSS: {e_rss} | pytrends: {e_pt}"
            print(f"❌ Trends [{region}]: both sources failed — {error}")

    if topics:
        fetched_str = datetime.now().strftime("%H:%M:%S")
        _cache[region] = {
            "topics":       topics,
            "fetched_at":   time.time(),
            "fetched_at_str": fetched_str,
            "source":       source,
        }

    return {
        "region":     region,
        "topics":     topics,
        "cached":     False,
        "fetched_at": _cache.get(region, {}).get("fetched_at_str", ""),
        "source":     source,
        "error":      error,
    }


def clear_cache(region: str = None):
    """Clear cached trends. Pass region to clear one, or None to clear all."""
    if region:
        _cache.pop(region.upper(), None)
    else:
        _cache.clear()


# ------------------------------------------------------------
#  Entry point for isolated testing
# ------------------------------------------------------------

if __name__ == "__main__":
    for region in ["US", "CA", "GLOBAL"]:
        print(f"\n{'='*50}")
        print(f"Testing region: {region}")
        result = get_trending(region)
        if result["error"]:
            print(f"❌ Error: {result['error']}")
        else:
            print(f"Source : {result['source']} | Cached: {result['cached']}")
            for i, t in enumerate(result["topics"][:5], 1):
                print(f"  {i}. {t}")