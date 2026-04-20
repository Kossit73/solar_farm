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
    """Compose structured response with model-first reasoning in prose form."""
    npv = packet.internal_facts.get("project_npv")
    project_irr = packet.internal_facts.get("project_irr")
    equity_irr = packet.internal_facts.get("equity_irr")
    avg_dscr = packet.internal_facts.get("avg_dscr")
    min_dscr = packet.internal_facts.get("min_dscr")
    rev_delta = packet.driver_breakdown.get("revenue_delta_latest_vs_first")
    ebitda_delta = packet.driver_breakdown.get("ebitda_delta_latest_vs_first")

    direct = (
        f"This question is best handled as a **{plan.intent}** analysis. "
        "The answer below is grounded in the current model run first, then augmented "
        "with external context only when useful."
    )

    internal_lines = []
    if npv is not None:
        internal_lines.append(f"- Project NPV is approximately `{npv:,.0f}`.")
    if project_irr is not None:
        internal_lines.append(f"- Project IRR is approximately `{project_irr:.2%}`.")
    if equity_irr is not None:
        internal_lines.append(f"- Equity IRR is approximately `{equity_irr:.2%}`.")
    if avg_dscr is not None:
        internal_lines.append(f"- Average DSCR in the modeled horizon is around `{avg_dscr:.2f}x`.")
    if min_dscr is not None:
        internal_lines.append(f"- Minimum DSCR observed is around `{min_dscr:.2f}x`.")
    if not internal_lines:
        internal_lines = ["- No internal model facts were extracted for this specific query."]

    driver_lines = []
    if rev_delta is not None:
        driver_lines.append(
            f"- Revenue change from the first to latest modeled year is approximately `{rev_delta:,.0f}`."
        )
    if ebitda_delta is not None:
        driver_lines.append(
            f"- EBITDA change from the first to latest modeled year is approximately `{ebitda_delta:,.0f}`."
        )
    if not driver_lines:
        driver_lines = ["- No driver decomposition signals were available for this question."]

    sources_lines = [f"- {s.title}: {s.url}" for s in sources]
    if not sources_lines:
        sources_lines = ["- No external sources were required for this answer."]

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
            "- The interpretation prioritizes model-derived facts and uses external benchmarks as contextual checks.",
            "",
            "### 5) Recommendation / implication",
            "- Use this conclusion as a decision support signal and validate through targeted sensitivities on the key drivers above.",
        ]
    )
