from __future__ import annotations

import html
import re
from typing import List
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from .types import SourceRef


def retrieve_external_benchmarks(query: str, max_results: int = 5) -> List[SourceRef]:
    """Retrieve benchmark references via lightweight web search."""
    search_url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    req = Request(search_url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urlopen(req, timeout=12) as response:
            html_text = response.read().decode("utf-8", errors="ignore")
    except Exception:
        return []

    pattern = re.compile(r'class="result__a" href="(.*?)".*?>(.*?)</a>', re.DOTALL)
    sources: List[SourceRef] = []
    for match in pattern.finditer(html_text):
        if len(sources) >= max_results:
            break
        url = html.unescape(match.group(1))
        title = re.sub(r"<.*?>", "", html.unescape(match.group(2))).strip()
        if url and title:
            sources.append(SourceRef(title=title, url=url, quality_score=0.2))
    return sources


def rank_and_filter_sources(sources: List[SourceRef]) -> List[SourceRef]:
    """Apply minimal filtering and ranking by quality score."""
    filtered = [s for s in sources if s.url]
    return sorted(filtered, key=lambda s: s.quality_score, reverse=True)
