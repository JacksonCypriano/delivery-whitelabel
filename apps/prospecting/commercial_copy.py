"""Optional self-contained factual units INSIDE existing versioned articles.

No runtime fact store: only the published article body is interpreted. Each
unit includes its own conditions; no model, summary generation or truncation.
Legacy prose remains supported by commercial_facts.
"""
import hashlib
import json
import re
from .commercial_facts import Fact

PREFIX = '@commercial-facts-v1\n'


def units(article):
    if not article.body.startswith(PREFIX):
        return None
    data = json.loads(article.body[len(PREFIX):])
    if not isinstance(data, list) or not data or len(data) > 16:
        raise ValueError('invalid_commercial_copy')
    result = []
    digest = hashlib.sha256(article.body.encode()).hexdigest()
    for i, row in enumerate(data):
        if not isinstance(row, dict) or set(row) != {'for', 'text'}:
            raise ValueError('invalid_commercial_copy')
        tags, text = row['for'], row['text']
        if (not isinstance(tags, list) or not tags or any(not isinstance(t, str) or not re.fullmatch(r'[a-z0-9:_-]+', t) for t in tags)
                or not isinstance(text, str) or not text.strip()
                or re.search(r'https?://|R\$|\d+[,.]\d{2}', text, re.I)):
            raise ValueError('invalid_commercial_copy')
        result.append((frozenset(tags), Fact(f'{article.pk}:unit:{i}', article.pk, article.slug,
                                           article.version, digest, text.strip(), False)))
    return result


def select_units(article, tags):
    data = units(article)
    if data is None:
        return None
    missing = set(tags) - set().union(*(t for t, _ in data))
    if missing:
        raise ValueError('commercial_detail_uncovered')
    return tuple(fact for targets, fact in data if targets & set(tags))
