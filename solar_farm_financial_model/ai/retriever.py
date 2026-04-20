from __future__ import annotations

from typing import List
from .types import SourceRef

def retrieve_external_benchmarks(query: str, max_results: int = 5) -> List[SourceRef]:
    """
    Retrieve benchmark references.
    Swap internals with your current web-search helper or a more robust backend.
    """
    # TODO: integrate existing web-search function from streamlit_app.py
    # Return empty list safely on failure.
    return []

def rank_and_filter_sources(sources: List[SourceRef]) -> List[SourceRef]:
    """Apply quality/relevance filtering and return sorted sources."""
    # Minimal placeholder: keep non-empty URLs
    filtered = [s for s in sources if s.url]
    return sorted(filtered, key=lambda s: s.quality_score, reverse=True)
