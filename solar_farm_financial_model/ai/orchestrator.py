from __future__ import annotations

from datetime import datetime, timezone
from typing import Tuple

from solar_farm_financial_model.model import ModelOutputs
from solar_farm_financial_model.schemas import Assumptions

from .analyzers import analyze_internal, build_model_context
from .composer import compose_markdown_answer, infer_confidence
from .llm_reasoner import generate_reasoned_answer
from .memory import ConversationMemory, memory_to_prompt_context, update_memory
from .planner import build_plan
from .providers import LLMProviderConfig, env_api_key
from .retriever import rank_and_filter_sources, retrieve_external_benchmarks
from .types import AssistantTurn


def run_assistant_turn(
    question: str,
    outputs: ModelOutputs,
    assumptions: Assumptions,
    memory: ConversationMemory,
    llm_config: dict | None = None,
) -> Tuple[AssistantTurn, ConversationMemory]:
    """Execute one reasoning turn using model-first analysis and optional web validation."""
    model_context = build_model_context(outputs, assumptions)
    plan = build_plan(question, memory_to_prompt_context(memory), model_context)

    packet = analyze_internal(plan, outputs, assumptions)

    sources = []
    if plan.needs_web and plan.web_query:
        sources = rank_and_filter_sources(retrieve_external_benchmarks(plan.web_query))

    cfg = LLMProviderConfig(**(llm_config or {}))
    if not cfg.api_key:
        cfg.api_key = env_api_key(cfg.provider_name)
    use_llm = bool(cfg.api_key)
    if use_llm:
        try:
            answer = generate_reasoned_answer(
                question=question,
                plan=plan,
                packet=packet,
                memory_turns=memory.turns,
                preloaded_sources=sources,
                config=cfg,
            )
        except Exception as exc:
            answer = (
                f"LLM provider call failed (`{cfg.provider_name}`): {exc}\n\n"
                "Falling back to local model-grounded response.\n\n"
                + compose_markdown_answer(plan, packet, sources)
            )
    else:
        answer = compose_markdown_answer(plan, packet, sources)
    confidence = infer_confidence(plan, packet, sources)

    turn = AssistantTurn(
        question=question,
        answer_markdown=answer,
        plan=plan,
        confidence=confidence,
        sources=sources,
        timestamp_iso=datetime.now(timezone.utc).isoformat(),
    )
    memory = update_memory(memory, turn)
    return turn, memory
