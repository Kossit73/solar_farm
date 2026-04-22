from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

IntentType = Literal[
    "valuation", "profitability", "liquidity", "leverage", "growth", "pricing", "efficiency", "risk",
    "driver_analysis", "scenario_impact", "benchmark_validation", "model_explainability"
]

ConfidenceLevel = Literal["low", "medium", "high"]

@dataclass
class QuestionPlan:
    raw_question: str
    intent: IntentType
    entities: Dict[str, Any] = field(default_factory=dict)   # e.g. {"metric": "ebitda", "year_from": 2026}
    time_scope: Dict[str, Any] = field(default_factory=dict) # e.g. {"latest_only": True}
    needs_web: bool = False
    web_query: Optional[str] = None
    analysis_steps: List[str] = field(default_factory=list)
    rationale: str = ""

@dataclass
class ModelContext:
    assumptions_snapshot: Dict[str, Any]
    metrics_snapshot: Dict[str, float]
    monthly_records: List[Dict[str, Any]]
    annual_records: List[Dict[str, Any]]

@dataclass
class EvidencePacket:
    internal_facts: Dict[str, Any] = field(default_factory=dict)
    driver_breakdown: Dict[str, Any] = field(default_factory=dict)
    benchmark_facts: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

@dataclass
class SourceRef:
    title: str
    url: str
    snippet: str = ""
    published_date: Optional[str] = None
    quality_score: float = 0.0

@dataclass
class AssistantTurn:
    question: str
    answer_markdown: str
    plan: QuestionPlan
    confidence: ConfidenceLevel
    sources: List[SourceRef] = field(default_factory=list)
    timestamp_iso: str = ""
