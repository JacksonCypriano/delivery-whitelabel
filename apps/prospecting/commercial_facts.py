"""Ephemeral, verbatim facts from the published revision; no parallel catalog."""
import hashlib
import re
from dataclasses import dataclass

# Instructions in approved knowledge are for the agent, not WhatsApp recipients.
_POLICY_START = (
    'não prometer', 'nao prometer', 'não afirmar', 'nao afirmar',
    'nunca prometer', 'não confundir', 'nao confundir',
    'não é correto afirmar', 'nao e correto afirmar',
    'os preços devem', 'os precos devem', 'não oferecer', 'nao oferecer',
    'evitar prometer', 'não garantir', 'nao garantir',
    'a demonstração pública pode', 'a demonstracao publica pode',
)
def _normalize(value):
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold())
                   if not unicodedata.combining(c))


def _public_summary(article, *, price_requested=False):
    """Extract approved factual sentences; never reproduce operational instructions.

    A filtered article with no safe factual sentence requires human review.
    No AI output is used as unverified prose.
    """
    if price_requested and article.slug in {'contratacao'}:
        return ''
    body = article.body.strip()
    if not body:
        raise ValueError('unreviewed_article')
    fragments = re.split(r'(?<=[.!?])\s+', body)
    approved = []
    for fragment in fragments:
        sentence = fragment.strip()
        folded = _normalize(sentence)
        if sentence.endswith('?'):
            continue  # Qualification belongs to the single contextual CTA below.
        if not sentence or any(folded.startswith(_normalize(bad)) for bad in _POLICY_START):
            continue
        if re.search(r'https?://|R\$|(?<!\w)\d+[,.]\d{2}(?!\w)', sentence, re.I):
            # Links and prices come only from approved structured config/catalog.
            continue
        approved.append(sentence)
    if not approved:
        raise ValueError('article_has_no_public_facts')
    return ' '.join(approved)



@dataclass(frozen=True)
class Fact:
    key: str
    article_id: int
    slug: str
    version: int
    body_sha256: str
    text: str
    required: bool


# Conditions/limitations accompany every selected fact from the same source.
# Never shorten a clause, strip a negation or let the model remove a caveat.
_CONDITION = re.compile(
    r'\b(?:nao|nem|sem|somente|apenas|depende|dependem|conforme|exceto|salvo|'
    r'exige|exigem|precisa|precisam|necessari\w*|compatib\w*|habilita\w*|'
    r'homologa\w*|permiss\w*|aprova\w*|configura\w*|condic\w*|'
    r'independente\w*|opciona\w*|parte|resultado\w*|limit\w*|'
    r'isso|esses|essas|estes|estas|ele|ela|eles|elas)\b', re.I)


def facts_for(article):
    summary = _public_summary(article)
    digest = hashlib.sha256(article.body.encode()).hexdigest()
    facts = []
    seen = set()
    for index, sentence in enumerate(re.split(r'(?<=[.!?])\s+', summary)):
        if sentence in seen:
            continue
        seen.add(sentence)
        facts.append(Fact(
            key=f'{article.pk}:{index}', article_id=article.pk, slug=article.slug,
            version=getattr(article, 'version', 0), body_sha256=digest,
            text=sentence, required=bool(_CONDITION.search(_normalize(sentence))),
        ))
    return tuple(facts)


def fact_catalog(knowledge):
    result = {}
    for article in knowledge:
        try:
            result[article.slug] = facts_for(article)
        except ValueError:
            # An unusable article must not disable unrelated, covered questions.
            result[article.slug] = ()
    return result
