"""Consulta factual, limitada e somente leitura ao histórico comercial do contato.

Não utiliza modelo, rede, cache global ou mensagens de outro contato.
Perguntas sobre histórico são respondidas apenas com evidência do próprio chat.
"""
from datetime import timedelta
import re

from django.utils import timezone

from .commercial_local_nlu import normalize

_HISTORY_STATES = frozenset({'submitted', 'sent', 'delivered', 'read'})
_BUSINESS = (
    ('pizzaria', r'\bpizzaria\b'),
    ('hamburgueria', r'\bhamburgueria\b'),
    ('restaurante', r'\brestaurante\b'),
    ('marmitaria', r'\bmarmitaria\b'),
    ('açaiteria', r'\bacaiteria\b'),
    ('lanchonete', r'\blanchonete\b'),
    ('confeitaria', r'\bconfeitaria\b'),
    ('padaria', r'\bpadaria\b'),
)
_PERIOD = (
    ('anual', r'\b(?:anual|12 meses|um ano)\b'),
    ('semestral', r'\b(?:semestral|6 meses)\b'),
    ('trimestral', r'\b(?:trimestral|3 meses)\b'),
    ('mensal', r'\b(?:mensal|mensalidade|1 mes)\b'),
)
# Uma pergunta sobre o passado nao é uma solicitação nova de orçamento.
_PAST_CUE = re.compile(r'\b(?:lembra|lembrar|recorda|recordar|antes|anteriormente|ja (?:te )?(?:falei|disse|comentei|perguntei)|eu (?:te )?(?:falei|disse|comentei|perguntei))\b')
_BUSINESS_QUERY = re.compile(r'\b(?:tipo de estabelecimento|ramo|meu negocio|minha loja|que estabelecimento|qual (?:e|era) (?:o )?meu tipo)\b')
_PERIOD_QUERY = re.compile(r'\b(?:plano|periodo|mensal|trimestral|semestral|anual)\b')


def requested_history_topics(current):
    """Identifica perguntas explicitas sobre o passado; nao consultas normais de preco."""
    q = normalize(current)
    if not _PAST_CUE.search(q):
        return set()
    topics = set()
    if _BUSINESS_QUERY.search(q) or re.search(r'\b(?:que|qual)\b.{0,30}\b(?:estabelecimento|negocio|ramo)\b', q):
        topics.add('business')
    if _PERIOD_QUERY.search(q):
        topics.add('period')
    return topics


def _business_from(text):
    # Reconhecer somente afirmacoes do próprio lead sobre sua operação.
    if not re.search(r'\b(?:tenho|sou|meu|minha|trabalho|possuo|gerencio|abri|abrindo|nosso|nossa)\b', text):
        return None
    for label, expression in _BUSINESS:
        if re.search(expression, text):
            return label
    return None


def _period_from(text):
    # Desconsiderar pergunta genérica "quais sao os planos?".
    for label, expression in _PERIOD:
        if re.search(expression, text) and re.search(r'\b(?:plano|valor|preco|custa|quanto|assinatura|mensalidade|periodo|pagar)\b', text):
            return label
    return None


def historical_facts(conversation, *, now=None, max_messages=100, days=90):
    """Dados comprovaveis de mensagens anteriores processadas do MESMO contato.

    Não mistura respostas do agente, mensagens humanas, held ou envios incertos.
    A janela protege contra ressurreição ilimitada de dados antigos.
    """
    now = now or timezone.now()
    cutoff = now - timedelta(days=days)
    rows = conversation.messages.filter(
        from_me=False,
        state__in=_HISTORY_STATES,
        created_at__gte=cutoff,
    ).order_by('-pk').values('text', 'created_at')[:max_messages]
    business = period = None
    for row in rows:
        text = normalize(row['text'] or '')
        if not text:
            continue
        # A mensagem mais recente com uma informação explícita prevalece.
        if business is None:
            business = _business_from(text)
        if period is None:
            period = _period_from(text)
        if business is not None and period is not None:
            break
    return {'business': business, 'period': period}


def answer_history_question(conversation, current, *, now=None):
    """Retorna resposta e marcadores; None deixa o motor regular decidir."""
    requested = requested_history_topics(current)
    if not requested:
        return None
    known = historical_facts(conversation, now=now)
    parts = []
    if 'business' in requested:
        if known['business']:
            parts.append(f'Você me contou que tem uma {known["business"]}.')
        else:
            parts.append('Não encontrei no nosso histórico uma confirmação do tipo de estabelecimento.')
    if 'period' in requested:
        if known['period']:
            parts.append(f'O último plano específico que você mencionou foi o {known["period"]}.')
        else:
            parts.append('Não encontrei no nosso histórico um plano específico que você tenha mencionado.')
    return ' '.join(parts), requested
