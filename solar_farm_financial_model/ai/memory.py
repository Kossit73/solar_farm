from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from .types import AssistantTurn


@dataclass
class ConversationMemory:
    turns: List[AssistantTurn] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)


def update_memory(memory: ConversationMemory, turn: AssistantTurn) -> ConversationMemory:
    memory.turns.append(turn)
    memory.summary["last_intent"] = turn.plan.intent
    memory.summary["last_question"] = turn.question
    memory.summary["turn_count"] = len(memory.turns)
    return memory


def memory_to_prompt_context(memory: ConversationMemory) -> Dict[str, Any]:
    return {
        "turn_count": len(memory.turns),
        "summary": dict(memory.summary),
    }
