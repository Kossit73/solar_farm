from __future__ import annotations
from typing import Dict, List, Optional
from .types import QuestionPlan, IntentType

def classify_intent(question: str) -> IntentType:
    """Map user question to intent category."""
    text = question.lower()
    if "why" in text and ("revenue" in text or "ebitda" in text):
        return "driver_analysis"
    if "compare" in text or "benchmark" in text or "reasonable" in text:
        return "benchmark_validation"
    if "scenario" in text or "what if" in text:
        return "scenario_impact"
    # fallback map from current categories
    return "valuation"

def build_plan(
    question: str,
    memory_summary: Dict[str, object],
    model_context: Dict[str, object],
) -> QuestionPlan:
    """
    Build structured plan:
    - intent
    - entities/time scope
    - whether web is required
    - ordered analysis steps
    """
    intent = classify_intent(question)
    needs_web = intent in {"benchmark_validation", "pricing", "valuation", "risk"}
    web_query = None
    if needs_web:
        web_query = "utility scale solar benchmark " + question

    steps: List[str] = ["extract_internal_facts", "run_driver_analysis"]
    if needs_web:
        steps.append("fetch_external_benchmarks")
    steps += ["synthesize_interpretation", "compose_recommendation"]

    return QuestionPlan(
        raw_question=question,
        intent=intent,
        entities={},
        time_scope={},
        needs_web=needs_web,
        web_query=web_query,
        analysis_steps=steps,
        rationale="Plan generated from intent + model-aware heuristics."
    )
