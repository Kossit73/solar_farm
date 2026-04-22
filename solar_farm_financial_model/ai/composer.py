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
    """Return response in required structure with concise reasoning prose."""
    npv = packet.internal_facts.get("project_npv", float("nan"))
    proj_irr = packet.internal_facts.get("project_irr", float("nan"))
    eq_irr = packet.internal_facts.get("equity_irr", float("nan"))
    min_dscr = packet.internal_facts.get("min_dscr", float("nan"))
    avg_dscr = packet.internal_facts.get("avg_dscr", float("nan"))
    margin = packet.driver_breakdown.get("ebitda_margin_latest", float("nan"))
    rev_delta = packet.driver_breakdown.get("revenue_delta_latest_vs_first", float("nan"))
    ebitda_delta = packet.driver_breakdown.get("ebitda_delta_latest_vs_first", float("nan"))
    breaches = packet.driver_breakdown.get("dscr_breach_months", 0)

    src_md = "\n".join([f"- {s.title}: {s.url}" for s in sources]) or "- No external sources used."
    benchmark_section = (
        "No external benchmark was required for this question."
        if not sources
        else "External references were used as directional context (model facts remain primary)."
    )
    interp = "balanced"
    if isinstance(min_dscr, (int, float)) and min_dscr == min_dscr and min_dscr < 1.20:
        interp = "aggressive/risk-leaning on debt coverage"
    elif isinstance(npv, (int, float)) and npv == npv and npv < 0:
        interp = "weak economics under current assumptions"
    elif isinstance(proj_irr, (int, float)) and proj_irr == proj_irr and proj_irr > 0.15:
        interp = "strong returns but potentially optimistic assumptions"

    return (
        "### 1) Direct answer\n"
        f"- This is a **{plan.intent}** question. Based on the current model run, key outcomes are NPV `{npv:,.0f}`, "
        f"project IRR `{proj_irr:.2%}`, equity IRR `{eq_irr:.2%}`.\n\n"
        "### 2) Internal model analysis\n"
        f"- Model facts: latest EBITDA margin is `{margin:.2%}`, revenue delta vs first year is `{rev_delta:,.0f}`, "
        f"and EBITDA delta is `{ebitda_delta:,.0f}`.\n"
        f"- Financing facts: average DSCR `{avg_dscr:.2f}x`, minimum DSCR `{min_dscr:.2f}x`, "
        f"covenant breach months (`<1.20x`) `{breaches}`.\n"
        f"- Assumption anchor: focus metric is `{packet.internal_facts.get('focus_metric', 'n/a')}`.\n\n"
        "### 3) External benchmark validation\n"
        f"- {benchmark_section}\n"
        f"{src_md}\n\n"
        "### 4) Interpretation\n"
        f"- Overall profile looks **{interp}** based on coverage, return, and trend signals.\n"
        "- Uncertainty note: benchmark confidence is lower if sources are sparse or non-primary.\n\n"
        "### 5) Recommendation / implication\n"
        "- Validate top sensitivities next (price, capacity factor, opex, leverage) and compare one base and one downside case before decision.\n"
        "\n### 6) Sources\n"
        "- Internal model: assumptions + outputs from this run.\n"
        f"{src_md}\n"
    )
