from __future__ import annotations

from typing import Any, Dict, List

from .types import IntentType, QuestionPlan


def classify_intent(question: str) -> IntentType:
    """Map user question to an intent category."""
    text = question.lower()
    if "why" in text and ("revenue" in text or "ebitda" in text):
        return "driver_analysis"
    if "compare" in text or "benchmark" in text or "reasonable" in text:
        return "benchmark_validation"
    if "scenario" in text or "what if" in text:
        return "scenario_impact"
    if any(k in text for k in ["valuation", "irr", "npv", "multiple"]):
        return "valuation"
    if any(k in text for k in ["dscr", "debt", "coverage", "covenant"]):
        return "leverage"
    if any(k in text for k in ["risk", "stress", "downside"]):
        return "risk"
    return "model_explainability"


def build_plan(
    question: str,
    memory_summary: Dict[str, Any],
    model_context: Dict[str, Any],
) -> QuestionPlan:
    """Build a structured reasoning plan for the assistant."""
    del model_context  # reserved for future richer planning

    intent = classify_intent(question)
    needs_web = intent in {"benchmark_validation", "valuation", "pricing", "risk"}
    web_query = f"utility scale solar {question}" if needs_web else None

    steps: List[str] = ["extract_internal_facts", "run_driver_analysis"]
    if needs_web:
        steps.append("fetch_external_benchmarks")
    steps.extend(["synthesize_interpretation", "compose_recommendation"])

    return QuestionPlan(
        raw_question=question,
        intent=intent,
        entities={"prior_turns": int(memory_summary.get("turn_count", 0))},
        time_scope={"latest_only": True},
        needs_web=needs_web,
        web_query=web_query,
        analysis_steps=steps,
        rationale="Plan generated from intent + model-aware heuristics.",
    )
