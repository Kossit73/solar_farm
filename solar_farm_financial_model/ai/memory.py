from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List
from .types import AssistantTurn

@dataclass
class ConversationMemory:
    turns: List[AssistantTurn] = field(default_factory=list)
    summary: Dict[str, object] = field(default_factory=dict)

def update_memory(memory: ConversationMemory, turn: AssistantTurn) -> ConversationMemory:
    memory.turns.append(turn)
    memory.summary["last_intent"] = turn.plan.intent
    memory.summary["last_question"] = turn.question
    if isinstance(turn.plan.entities.get("metric"), str):
        memory.summary["last_metric"] = turn.plan.entities["metric"]
    return memory

def memory_to_prompt_context(memory: ConversationMemory) -> Dict[str, object]:
    return {
        "turn_count": len(memory.turns),
        "summary": memory.summary,
    }
