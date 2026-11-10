"""Objective report properties, never an automatic editorial approval."""
import hashlib
import re
from .commercial_copy import units
from .commercial_facts import facts_for
from .commercial_local import price_lines


def quality(row, publication, knowledge, links):
    trace, answer = row['trace'], row['answer']
    topics, covered = set(trace.get('intents', [])), set(trace.get('fulfilled', []))
    source_map = {a.pk: a for a in knowledge}
    grounded = True
    for used in trace.get('facts', []):
        article = source_map.get(used['article_id'])
        if article is None or not article.published or article.version != used['version']:
            grounded = False
            continue
        if hashlib.sha256(article.body.encode()).hexdigest() != used['sha256']:
            grounded = False
        try:
            structured = units(article)
            available = [f for _, f in structured] if structured is not None else facts_for(article)
            if not any(f.key == used['key'] and f.text == used.get('text') for f in available):
                grounded = False
        except (ValueError, TypeError):
            grounded = False
        if used.get('text', '') not in answer:
            grounded = False
    # Prices are compared with the current catalog; article prose cannot supply them.
    catalog_valid = True
    try:
        allowed_prices = set(re.findall(r'R\$\s*[\d.,]+', '\n'.join(price_lines(publication, 0))))
    except (ValueError, TypeError, KeyError):
        allowed_prices = set()
        catalog_valid = False
    output_prices = set(re.findall(r'R\$\s*[\d.,]+', answer))
    output_urls = set(re.findall(r'https?://\S+', answer))
    source_intents = {f.get('intent') for f in trace.get('facts', [])}
    answered = row['outcome'] == 'answer' and not trace.get('clarification')
    limit = 300 if len(topics) <= 1 else 500
    return {
        'outcome_compatible': row['outcome_compatible'],
        'factual_completeness': {'interpreted': sorted(topics), 'covered': sorted(covered),
                                 'missing': sorted(topics - covered),
                                 'status': 'mapped' if answered and topics <= covered else 'review'},
        'commercial_safety': {'facts_match_published_revision': grounded,
                              'catalog_valid': catalog_valid,
                              'prices_from_catalog': output_prices <= allowed_prices,
                              'urls_from_configuration': output_urls <= set(links.values()),
                              'handoff_reason': row['error']},
        'concision': {'characters': len(answer), 'target': limit, 'within_target': len(answer) <= limit},
        'relevance': {'sources_match_interpreted_topics': source_intents <= topics,
                      'semantic_relevance': 'manual_review_required'},
        'manual_review_required': True,
        'editorial_quality': 'pending',
    }
