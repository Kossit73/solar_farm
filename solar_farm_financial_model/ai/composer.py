from __future__ import annotations

from typing import List

from .types import ConfidenceLevel, EvidencePacket, QuestionPlan, SourceRef


def infer_confidence(plan: QuestionPlan, packet: EvidencePacket, sources: List[SourceRef]) -> ConfidenceLevel:
    if plan.needs_web and not sources:
        return "low"
    if packet.internal_facts:
        return "medium" if plan.needs_web else "high"
    return "low"


def compose_markdown_answer(
    plan: QuestionPlan,
    packet: EvidencePacket,
    sources: List[SourceRef],
) -> str:
    """Compose structured response with model-first reasoning."""
    direct = f"Based on the current run, this is primarily a **{plan.intent}** question."

    internal_lines = [f"- {k}: `{v}`" for k, v in packet.internal_facts.items()]
    driver_lines = [f"- {k}: `{v}`" for k, v in packet.driver_breakdown.items()]
    sources_lines = [f"- {s.title}: {s.url}" for s in sources]

    if not internal_lines:
        internal_lines = ["- No internal model facts were extracted."]
    if not driver_lines:
        driver_lines = ["- No driver decomposition available for this question."]
    if not sources_lines:
        sources_lines = ["- No external sources used for this answer."]

    return "\n".join(
        [
            "### 1) Direct answer",
            direct,
            "",
            "### 2) Internal model analysis",
            *internal_lines,
            *driver_lines,
            "",
            "### 3) External benchmark/validation",
            *sources_lines,
            "",
            "### 4) Interpretation",
            "- Interpret internal outputs first; use external refs as directional context.",
            "",
            "### 5) Recommendation / implication",
            "- Stress-test the highest-impact assumptions before making decisions.",
        ]
    )
