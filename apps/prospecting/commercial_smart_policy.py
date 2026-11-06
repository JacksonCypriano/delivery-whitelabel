"""Deterministic safeguards for commercial Gemini classification.

Only vetted article prose and live catalog values may be sent to buyers.
This module does not access WhatsApp, network, or persistence.
"""
import re
import unicodedata

from .commercial_context import conversation_context


def fold(value):
    return ''.join(char for char in unicodedata.normalize('NFKD', str(value).casefold())
                   if not unicodedata.combining(char))


def matches(pattern, text):
    return re.search(pattern, text, flags=re.I) is not None


# Requests requiring capabilities, exceptions or promises outside the approved
# product article facts must not receive a vague sales pitch as an answer.
HUMAN_GUARDS = (
    r'\b(?:gratis|gratuito|de graca|free|90 dias gratis|teste gratis)\b',
    r'\b(?:parcelar|parcelamento|em \d+ vezes|desconto extra|cobre (?:o )?preco|faz por \d+)\b',
    r'\b(?:motoboy|entregador(?:es)?)\s+(?:proprio|de voces|incluso|incluso|gratis|de graca)\b',
    r'\b(?:faz(?:em)?|realiza(?:m)?|voces fazem|vcs fazem)\s+(?:a )?entrega\s+(?:pra mim|da comida|dos pedidos|de marmita)\b',
    r'\b(?:voces entregam|vcs entregam|quero pedir|pedido \d+|status do pedido|reembolso)\b',
    r'\b(?:vende(?:m)?|fornece(?:m)?)\s+(?:uma?\s+)?impressora\b',
    r'\b(?:impressora|equipamento|motoboy)\s+(?:gratis|de graca|inclus[oa])\b',
    r'\b(?:emite|emitir|emissao)\s+(?:nota fiscal|nf-e|nfe|nfce|nf-c?e)\b',
    r'\b(?:garant[ea]|garantir|100%|nunca (?:cai|vai cair)|sem cair)\b',
    r'\b(?:api key|token secreto|chave (?:do )?gemini|prompt(?:s)? intern[oa]s?|regras internas)\b',
    r'\b(?:ignora (?:suas )?instrucoes|finge que voce|dados de cliente|cpf|laudo medico|qual remedio|marc[ae] como quitada)\b',
    r'\b(?:rappi|aiqfome|divisao de conta|bluetooth|certificado a1|revendedor|comissao por indicacao)\b',
    r'\b(?:ja (?:ta|esta) homologad[oa]|liberad[oa] pra todo mundo|homologad[oa] e liberad[oa])\b',
    r'\b(?:funciona 24 horas sem cair|marketing sozinho|promocao automatica pra todos|outro numero|whatsapp business que ja uso|evolution api)\b',
)

# Avoid misidentifying operational delivery-management questions as a request for
# physical courier dispatch. Only explicit outsourced delivery is guarded.


TOPIC_PATTERNS = {
    'integracoes': r'\b(?:ifood|ifod|ifudi|99\s?food|integrac(?:ao|oes)|intregacao|marketplace)\b',
    'impressao': r'\b(?:impress(?:ao|ora|oras)|impremir|imprimir|imprime|cupom|comprovante|termica)\b',
    'whatsapp': r'\b(?:whatsapp|whats|wpp|zap|robo|agente de atendimento|atendente automatizad[oa])\b',
    'gestao': r'\b(?:cardapio|cadapio|cartapio|catalogo|meio a meio|adicionais|crm|fidelidade|estoque|categorias)\b',
    'pedidos': r'\b(?:cozinha|cozina|kds|kanban|preparo|pedidos?|retirada|retiraada|entrega|entreaga|mesa)\b',
    'comissoes': r'\b(?:comiss(?:ao|oes)|comissao|comisoes|taxa por pedido|taxas por pedido|taxa por venda)\b',
}

# A same-message selection of multiple topics is allowed within the 3-article
# bound. If unsupported by selected *published* articles, escalate instead.


def requested_topics(text):
    folded = fold(text)
    return {slug for slug, pattern in TOPIC_PATTERNS.items() if matches(pattern, folded)}


def requested_period(text):
    """Resolve requested billing period without trusting the LLM's scope.

    Returns: None (no explicit period), 0 (compare all), or 1/3/6/12 months.
    Ambiguous multiple periods are treated as comparisons rather than guesses.
    """
    message = fold(text)
    all_requested = matches(r'\b(?:todos os planos|todos planos|4 planos|quatro planos|comparar planos|comparacao de planos|planos com descontos|tabela de planos)\b', message)
    if all_requested:
        return 0
    patterns = {
        12: r'\b(?:anual|ano|12\s?(?:m|meses)|doze meses|planu anual)\b',
        6: r'\b(?:semestral|semestre|6\s?(?:m|meses)|seis meses)\b',
        3: r'\b(?:trimestral|trimestre|3\s?(?:m|meses)|tres meses)\b',
        1: r'\b(?:mensal|mensalidade|por mes|ao mes|1\s?(?:m|mes)|um mes)\b',
    }
    found = {months for months, pattern in patterns.items() if matches(pattern, message)}
    if len(found) > 1:
        return 0
    if found:
        return next(iter(found))
    return None


def price_question(text):
    message = fold(text)
    return matches(r'\b(?:preco|precos|valor|valoor|custa|custam|custo|qto|quanto|qt|plano|planu|planos|mensalidade|desconto|pago|sai por)\b', message)


def enforce_selection(conversation, selection, knowledge):
    """Fail closed on unknown requirements or unverifiable classifier selection."""
    try:
        text = conversation_context(conversation)
    except ValueError as exc:
        # Unit-level render checks may have no pending inbound message. The
        # operational compose() path still requires a fresh inbound boundary.
        if str(exc) != 'empty_inbound':
            raise
        text = (conversation.messages.filter(from_me=False)
                .order_by('-pk').values_list('text', flat=True).first() or '')
    folded = fold(text)
    if any(matches(pattern, folded) for pattern in HUMAN_GUARDS):
        raise ValueError('commercial_human_review_required')

    articles = {article.slug: article for article in knowledge}
    ids = selection.get('article_ids', [])
    selected = {article.slug for article in knowledge if article.pk in ids}
    required = requested_topics(text)

    # Some catalog content covers more than one topic (a general overview, e.g.),
    # but explicit topics must be answered by their dedicated vetted article.
    # This refuses to send a confident partial answer.
    missing = required - selected
    if missing and not (missing <= {'gestao'} and 'visao-geral' in selected):
        raise ValueError('commercial_topics_uncovered')
    if len(required) > 3:
        raise ValueError('commercial_too_many_topics')

    # Semantically unsafe explicit enquiries that article excerpts cannot settle
    # cannot be answered by a loosely related article.
    if matches(r'\b(?:pix|cartao|boleto)\b', folded) and 'pagamento' not in articles:
        # The payment methods are in the structured catalog, but the current
        # renderer cannot give a payment-specific answer yet.
        raise ValueError('commercial_payment_detail_review_required')
    if matches(r'\b(?:kds)\b', folded) and 'pedidos' not in selected:
        raise ValueError('commercial_topics_uncovered')
    return text
