"""One deterministic plan between semantic classification and public rendering.

Selections are hints. Facts remain verbatim and revision-bound; human decisions
and uncovered questions cannot be repaired into an affirmative sales response.
Legacy selections are accepted for callers from packages 01–09.
"""
from dataclasses import dataclass
import re

from .commercial_facts import fact_catalog
from .commercial_smart_policy import (
    enforce_safety, requested_topics, requested_period, price_question, normalized, demo_requested,
)


@dataclass(frozen=True)
class AnswerPlan:
    text: str
    intents: tuple
    questions: tuple
    facts: tuple
    available: tuple
    uncovered: tuple
    article_ids: tuple
    explicit: bool
    next_action: str


def compact_topics(topics, text=""):
    """Remove overlapping retrieval routes, not independent customer questions."""
    topics = set(topics)
    if 'gestao' in topics:
        topics.discard('cardapio-proprio')
    if 'objecao-canais' in topics:
        # A channel objection covers a mention of iFood, but an explicit
        # integration question remains independent.
        if not re.search(r'\bintegra\w*\b', normalized(text)):
            topics.discard('integracoes')
        topics.discard('cardapio-proprio')
    return topics


def build_plan(conversation, selection, knowledge):
    if not isinstance(selection, dict) or selection.get('human') is not False:
        raise ValueError('human_review_required')
    knowledge = tuple(knowledge)
    text = enforce_safety(conversation, knowledge)
    by_id = {a.pk: a for a in knowledge}
    by_slug = {a.slug: a for a in knowledge}
    if len(by_id) != len(knowledge) or len(by_slug) != len(knowledge):
        raise ValueError('ambiguous_article_revision')
    ids = selection.get('article_ids')
    # Transport bound, NOT a six-topic coverage limit. Duplicates are benign.
    if not isinstance(ids, list) or len(ids) > 128 or any(type(pk) is not int for pk in ids):
        raise ValueError('invalid_article_selection')
    if any(pk not in by_id for pk in ids):
        raise ValueError('unknown_article')
    if (selection.get('pricing_scope') not in {'none', 'monthly', 'all'}
            or selection.get('question') not in {'none', 'business', 'pain', 'channels', 'demo'}):
        raise ValueError('invalid_selection_options')

    catalog = fact_catalog(knowledge)
    facts_by_key = {f.key: f for values in catalog.values() for f in values}
    requests = {}
    anchors_needed = set()
    questions = []
    uncovered = set()
    semantic = selection.get('questions')
    explicit = False
    if semantic is not None:
        if not isinstance(semantic, list) or len(semantic) > 32:
            raise ValueError('invalid_question_plan')
        for row in semantic:
            if not isinstance(row, dict):
                raise ValueError('invalid_question_plan')
            intent, evidence, keys = (row.get(k) for k in ('intent', 'evidence', 'fact_ids'))
            if (not isinstance(intent, str) or not isinstance(evidence, str)
                    or not evidence.strip() or evidence not in text
                    or not isinstance(keys, list) or len(keys) > 128
                    or any(not isinstance(k, str) for k in keys)):
                raise ValueError('invalid_question_plan')
            anchors = compact_topics(requested_topics(evidence, set(by_slug)), evidence)
            anchors_needed.update(anchors)
            questions.append((intent, evidence))
            explicit = True
            if intent == 'unsupported':
                uncovered.add(intent)
                continue
            if intent in {'pricing', 'demo', 'signup'}:
                if keys:
                    raise ValueError('invalid_fact_selection')
                requests.setdefault(intent, set())
                continue
            if intent not in by_slug:
                uncovered.add(intent)
                continue
            if not keys:
                uncovered.add(intent)
                continue
            for key in keys:
                if key not in facts_by_key or facts_by_key[key].slug != intent:
                    raise ValueError('invalid_fact_selection')
            # Catch a plainly irrelevant intent even when the selected IDs exist.
            if anchors and intent not in anchors:
                uncovered.add(intent)
                continue
            requests.setdefault(intent, set()).update(keys)
        # Check unanswered question fragments, without promoting declarations
        # such as "uso iFood" to integration questions.
        residual = text
        for _, evidence in questions:
            residual = residual.replace(evidence, ' ')
        for fragment in re.split(r'[!;\n]', residual):
            folded = normalized(fragment).strip(' ,.')
            enquiry = '?' in folded or re.match(
                r'^(?:e\s+)?(?:tem|faz|como|qual|quais|quanto|qto|posso|consigo|'
                r'funciona|integra|imprime|aceita|oferece)\b', folded)
            if not enquiry:
                continue
            anchors = compact_topics(requested_topics(fragment, set(by_slug)), fragment)
            if anchors:
                anchors_needed.update(anchors)
                explicit = True
            elif not (price_question(fragment) or requested_period(fragment) is not None
                      or demo_requested(fragment) or 'contratacao' in requested_topics(fragment)):
                uncovered.add('unclassified_question')
        # An empty semantic plan cannot erase a plainly expressed enquiry.
        if not semantic:
            for topic in compact_topics(requested_topics(text, set(by_slug)), text):
                requests[topic] = {f.key for f in catalog.get(topic, ())}
                explicit = True
    else:
        # Compatibility path: dedicated question routes repair omissions, and
        # irrelevant/duplicate hints never enlarge the response.
        topics = compact_topics(requested_topics(text, set(by_slug)), text)
        explicit = bool(topics)
        if not topics and not (price_question(text) or requested_period(text) is not None):
            topics = {by_id[pk].slug for pk in ids}
        for topic in topics:
            requests[topic] = {f.key for f in catalog.get(topic, ())}
            questions.append((topic, text))

    # Repair clearly expressed omissions inside classified question spans.
    # Context-only mentions outside these spans do not impose extra articles.
    for topic in anchors_needed - set(requests):
        requests[topic] = {f.key for f in catalog.get(topic, ())}
    if price_question(text) or requested_period(text) is not None:
        requests.setdefault('pricing', set())
    chosen = []
    # Stable source order, independent of provider order, duplicates or DB order.
    for intent in sorted(requests, key=lambda slug: (by_slug[slug].pk if slug in by_slug else -1, slug)):
        if intent in {'pricing', 'demo', 'signup'}:
            continue
        facts = catalog.get(intent, ())
        if not facts or not requests[intent]:
            uncovered.add(intent)
            continue
        selected = requests[intent]
        # Every source condition accompanies excerpts, even if Gemini omitted it.
        chosen.extend(f for f in facts if f.key in selected or f.required)
    return AnswerPlan(
        text=text, intents=tuple(sorted(requests)), questions=tuple(questions),
        facts=tuple(chosen), available=tuple(sorted(k for k, v in catalog.items() if v)),
        uncovered=tuple(sorted(uncovered)),
        article_ids=tuple(dict.fromkeys(f.article_id for f in chosen)),
        explicit=explicit, next_action=selection['question'],
    )
