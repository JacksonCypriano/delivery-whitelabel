from dataclasses import dataclass, field
import re

from .knowledge import answer_from_store
from .ollama import naturalize, OllamaUnavailable


@dataclass(frozen=True)
class AgentReply:
    text: str
    intent: str
    pause_minutes: int = 0
    pause_reason: str = ""
    context: dict = field(default_factory=dict)


_NATURALIZE_INTENTS = {
    "greeting", "product", "product_description", "customization",
    "product_details", "promotion", "fulfillment", "delivery_areas",
    "delivery_fee", "delivery", "address", "hours", "payment",
}



def format_whatsapp_text(text):
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    value = "\n".join(line.rstrip() for line in value.split("\n"))
    value = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", value)
    return value.strip()

def _safe_naturalized(candidate, fallback, facts):
    """Reject LLM output that changes deterministic prices, times or URLs."""
    facts_text = "\n".join(str(fact) for fact in facts)
    allowed_urls = set(re.findall(r"https?://[^\s)]+", facts_text))
    candidate_urls = set(re.findall(r"https?://[^\s)]+", candidate))
    if not candidate_urls.issubset(allowed_urls):
        return False

    allowed_prices = set(re.findall(r"R\$\s*\d+[\.,]\d{2}", facts_text))
    candidate_prices = set(re.findall(r"R\$\s*\d+[\.,]\d{2}", candidate))
    if not candidate_prices.issubset(allowed_prices):
        return False

    allowed_times = set(re.findall(r"\b(?:[01]\d|2[0-3]):[0-5]\d\b", facts_text))
    candidate_times = set(re.findall(r"\b(?:[01]\d|2[0-3]):[0-5]\d\b", candidate))
    if not candidate_times.issubset(allowed_times):
        return False

    fallback_urls = set(re.findall(r"https?://[^\s)]+", fallback))
    if fallback_urls and not fallback_urls.issubset(candidate_urls):
        return False
    return True


def answer(tenant, question, context=None):
    knowledge = answer_from_store(tenant, question, context=context or {})
    text = knowledge.fallback
    if knowledge.intent in _NATURALIZE_INTENTS:
        try:
            candidate = naturalize(
                question,
                tenant.name,
                knowledge.intent,
                knowledge.facts,
            )
            if _safe_naturalized(candidate, knowledge.fallback, knowledge.facts):
                text = candidate
        except OllamaUnavailable:
            pass
    return AgentReply(
        text=format_whatsapp_text(text),
        intent=knowledge.intent,
        pause_minutes=knowledge.pause_minutes,
        pause_reason=knowledge.pause_reason,
        context=knowledge.context,
    )
