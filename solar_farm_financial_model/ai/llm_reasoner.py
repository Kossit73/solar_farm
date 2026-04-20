from __future__ import annotations

import os
from typing import List

from openai import OpenAI

from .types import AssistantTurn, EvidencePacket, QuestionPlan, SourceRef

SYSTEM_PROMPT = """You are an intelligent reasoning chatbot for financial and operating models.

Your job is to answer user questions about the model with high accuracy, clear logic, and practical insight.

Core behavior
- Always analyze the model first before using external information.
- Use web search only when external context would improve the answer, such as for benchmarking, market validation, comparable metrics, industry norms, or recent developments.
- Do not give generic summaries.
- Give answers that are grounded in the model’s assumptions, calculations, outputs, and dependencies.
- Explain both what the result is and why it happens.

Answer method
For each question, follow this sequence:
1. Identify the question type, such as valuation, profitability, revenue drivers, OPEX, CAPEX, cash flow, financing, returns, risk, or scenario impact.
2. Pull the relevant model outputs and assumptions.
3. Explain the internal model result clearly.
4. If useful, perform web search to find credible benchmark or market reference points.
5. Compare the model result against those external benchmarks.
6. Interpret whether the model looks strong, weak, conservative, aggressive, realistic, or inconsistent.
7. Give a practical recommendation, implication, or next validation step.

Required response structure
- Direct answer
- Internal model analysis
- External benchmark comparison when relevant
- Interpretation
- Recommendation
- Sources

Reasoning standards
- Be analytical, not generic.
- Be concise but complete.
- Distinguish clearly between:
  - model facts,
  - model assumptions,
  - external benchmark evidence,
  - uncertainty or limitations.
- If benchmark evidence is weak, say so.
- Do not invent facts.
- Build on previous user questions in the same session and maintain continuity.

Conversation memory
- Remember previous questions and answers in the same conversation.
- Use prior context, assumptions, edits, and conclusions in follow-up answers.
- Avoid repeating the same explanation if it was already established earlier.

Web search policy
- Use web search selectively, not automatically for every question.
- Prefer strong, relevant, domain-specific sources.
- Cite sources clearly when using web information.
- When answering time-sensitive or benchmark questions, prioritize current sources.

Tone
- Sound like a sharp analytical copilot.
- Be precise, commercially useful, and decision-oriented.
"""


def _memory_to_messages(turns: List[AssistantTurn], max_turns: int = 6) -> List[dict]:
    messages: List[dict] = []
    for turn in turns[-max_turns:]:
        messages.append({"role": "user", "content": turn.question})
        messages.append({"role": "assistant", "content": turn.answer_markdown})
    return messages


def generate_reasoned_answer(
    question: str,
    plan: QuestionPlan,
    packet: EvidencePacket,
    memory_turns: List[AssistantTurn],
    preloaded_sources: List[SourceRef],
) -> str:
    """Generate reasoning-first answer with optional web_search tool access."""
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    source_md = "\n".join(f"- {s.title}: {s.url}" for s in preloaded_sources) or "- None preloaded"
    user_context = (
        f"Question: {question}\n\n"
        f"Plan intent: {plan.intent}\n"
        f"Needs web: {plan.needs_web}\n"
        f"Analysis steps: {plan.analysis_steps}\n\n"
        f"Internal facts:\n{packet.internal_facts}\n\n"
        f"Driver breakdown:\n{packet.driver_breakdown}\n\n"
        f"Preloaded sources:\n{source_md}\n\n"
        "Respond in the required structure and keep the answer concise but complete."
    )

    response = client.responses.create(
        model="gpt-5",
        reasoning={"effort": "medium"},
        tools=[{"type": "web_search"}],
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            *_memory_to_messages(memory_turns),
            {"role": "user", "content": user_context},
        ],
    )
    return response.output_text
