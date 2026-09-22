from dataclasses import dataclass, field

from .knowledge import answer_from_store
from .ollama import naturalize, OllamaUnavailable


@dataclass(frozen=True)
class AgentReply:
    text: str
    intent: str
    pause_minutes: int = 0
    pause_reason: str = ""
    context: dict = field(default_factory=dict)


def answer(tenant, question, context=None):
    knowledge = answer_from_store(tenant, question, context=context or {})
    text = knowledge.fallback
    if knowledge.intent not in {"human"}:
        try:
            text = naturalize(
                question,
                tenant.name,
                knowledge.intent,
                knowledge.facts,
            )
        except OllamaUnavailable:
            pass
    return AgentReply(
        text=text,
        intent=knowledge.intent,
        pause_minutes=knowledge.pause_minutes,
        pause_reason=knowledge.pause_reason,
        context=knowledge.context,
    )
