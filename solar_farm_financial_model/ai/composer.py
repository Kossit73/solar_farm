from __future__ import annotations
from typing import List
from .types import AssistantTurn, ConfidenceLevel, EvidencePacket, QuestionPlan, SourceRef

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
    """Return response in required structure."""
    src_md = "\n".join([f"- {s.title}: {s.url}" for s in sources]) or "- No external sources used."
    return (
        "### 1) Direct answer\n"
        f"- Intent: **{plan.intent}**\n\n"
        "### 2) Internal model analysis\n"
        f"- Key facts: `{packet.internal_facts}`\n"
        f"- Driver breakdown: `{packet.driver_breakdown}`\n\n"
        "### 3) External benchmark validation\n"
        f"{src_md}\n\n"
        "### 4) Interpretation\n"
        "- Explain what this means for the model profile (conservative vs aggressive).\n\n"
        "### 5) Recommendation / implication\n"
        "- Provide a decision-oriented next step.\n"
    )
