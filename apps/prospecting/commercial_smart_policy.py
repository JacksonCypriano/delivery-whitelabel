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
    return re.search(pattern, text, flags=re.I | re.S) is not None


# Whole-token aliases: do not fuzzy-rewrite arbitrary customer words.
ALIASES = {'vc': 'voce', 'vcs': 'voces', 'tb': 'tambem', 'tbm': 'tambem',
           'cadapio': 'cardapio', 'cartapio': 'cardapio', 'cardapioo': 'cardapio',
           'ifod': 'ifood', 'ifudi': 'ifood', 'impremir': 'imprimir',
           'impresora': 'impressora', 'cozina': 'cozinha', 'coizinha': 'cozinha',
           'entreaga': 'entrega', 'retiraada': 'retirada', 'cistema': 'sistema',
           'intregacao': 'integracao', 'valoor': 'valor', 'planu': 'plano',
           'pedidu': 'pedido', 'pedidus': 'pedidos', 'lanxe': 'lanche',
           'mnh': 'minha', 'ce': 'voce', 'qq': 'o que', 'q': 'que'}


def normalized(text):
    return re.sub(r'\b\w+\b', lambda m: ALIASES.get(m[0], m[0]), fold(text))


def human_requested(text):
    text = normalized(text).strip(' !?.')
    clauses = re.split(r'[;.!?\n]|\b(?:mas|porem)\b', text)
    text = ' '.join(c for c in clauses if not matches(r'\bnao (?:quero|preciso|prefiro|desejo)\b', c))
    target = r'(?:um[ae]? |o |a |de |com |com um[ae]? )*(?:humano|atendente|pessoa|responsavel|alguem)'
    return (matches(r'^(?:humano|atendente(?: humano)?|pessoa|responsavel)$', text)
            or matches(r'\b(?:quero|preciso|prefiro|chame|chama|chamar|falar|conversar|transfira|transferir|me passa|me passe)\s+(?:falar com |conversar com |para |pra )?' + target + r'\b', text))


def demo_requested(text):
    text = normalized(text)
    return (matches(r'\b(?:demo|demonstracao)\b', text)
            and not matches(r'\bnao (?:quero|preciso|desejo)\b.{0,30}\b(?:demo|demonstracao)\b', text))


# Requests requiring capabilities, exceptions or promises outside the approved
# product article facts must not receive a vague sales pitch as an answer.
HUMAN_GUARDS = (
    r'\b(?:entrega\s+(?:com\s+)?motoboy|(?:fornece|fornecem|manda|mandam)\s+(?:um\s+)?motoboy)\b',
    r'\b(?:impressora|termica)\b.{0,65}\b(?:homologad[ao]s?|modelos?|marcas?|compativel)\b',
    r'\b(?:qual|quais)\b.{0,30}\b(?:modelo|marca)\b.{0,30}\bimpressora\b',
    r'\b(?:qual|quais)\b.{0,70}\bimpressoras?\b.{0,70}\bhomolog(?:aram|ad[ao]s?)\b',
    r'\b(?:audio|audios|transcreve|transcrever|transcricao|mensagem de voz)\b',
    r'\b(?:clinica|clinicas|consultorio|medico|medica|hospital|odontologico|dentista|agendamento de saude)\b',

    r'\b(?:contratar|contratacao|fornecer|fornecem)\b.{0,50}\b(?:motoboys?|entregadores?)\b',
    r'\btem\s+(?:(?:um|algum|seu)\s+)?(?:motoboys?|entregadores?)\b',
    r'\b(?:criar|cria|fazer|faz|fazem)\b.{0,45}\b(?:identidade visual|logo|logotipo)\b',
    r'\b(?:implantacao no mesmo dia|cancelar meu plano|cobre preco)\b',
    r'\b(?:sem confirm(?:ar|acao)|confirmacao automatica)\b',
    r'\b(?:99\s?food)\b.{0,50}\b(?:liberad[oa]|disponivel|homologad[oa])\b',
    r'\b(?:liberad[oa]|disponivel|homologad[oa])\b.{0,50}\b99\s?food\b',

    r'\b(?:gratis|gratuito|de graca|free|90 dias gratis|teste gratis)\b',
    r'\b(?:parcelar|parcelamento|em \d+ vezes|desconto extra|cobre (?:o )?preco|faz por \d+)\b',
    r'\b(?:motoboy|entregador(?:es)?)\s+(?:proprio|de voces|incluso|incluso|gratis|de graca)\b',
    r'\b(?:faz(?:em)?|realiza(?:m)?|voces fazem|vcs fazem)\s+(?:a )?entrega\s+(?:pra mim|da comida|dos pedidos|de marmita)\b',
    r'\b(?:voces entregam|vcs entregam|quero pedir|pedido \d+|status do pedido|reembolso)\b',
    r'\b(?:vende(?:m)?|fornece(?:m)?)\s+(?:uma?\s+)?impressora\b',
    r'\b(?:impressora|equipamento|motoboy)\s+(?:gratis|de graca|inclus[oa])\b',
    r'\b(?:emite|emitir|emissao)\s+(?:nota fiscal|nf-e|nfe|nfce|nf-c?e)\b',
    r'\b(?:garant(?:e|em|a|am|ir|ia|ias|id[oa]s?)|assegur(?:a|am|ar|ad[oa]s?)|nunca (?:cai|vai cair)|sem cair)\b',
    r'(?<!\w)100\s*%(?!\w)',
    r'\b(?:promet(?:e|em|er)|certeza|compromisso|direito)\b.{0,80}\b(?:vend(?:a|as|er)|faturamento|lucro|resultado|aumento|dobrar|triplicar)\b',
    r'\b(?:vend(?:a|as|er)|faturamento|lucro|resultado|aumento)\b.{0,80}\b(?:promet(?:e|em|er)|certeza|compromisso)\b',
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
    'whatsapp': r'\b(?:whatsapp|whats|wpp|zap|robo|agente de atendimento|atendente automatizad[oa]|atendimento automatizad[oa]|atendente humano|intervencao humana)\b',
    'gestao': r'\b(?:cardapio|cadapio|cartapio|catalogo|meio a meio|adicionais|crm|fidelidade|estoque|categorias)\b',
    'pedidos': r'\b(?:cozinha|cozina|kds|kanban|preparo|pedidos?|retirada|retiraada|entrega|entreaga|mesa)\b',
    'objecao-valor': r'\b(?:caro|compensa|vale a pena|poucos pedidos|muitos pedidos ainda)\b',
    'objecao-canais': r'\b(?:instagram|so (?:vendo|recebo|vendo pedidos) (?:por|pelo) ifood)\b',
    'objecao-cadastro': r'\b(?:sem tempo|nao tenho tempo)\b',
    'objecao-socio': r'\bsocio\b',
    'kds': r'\b(?:o que e|que e|oque e|que significa|como funciona)\s+(?:o\s+)?kds\b',
    'visao-geral': r'\b(?:diferenc(?:a|as)|diferente|diferenciais|o que (?:oferece|faz)|da (?:pra|para) usar|serve (?:pra|para)|atende (?:a |uma? )?(?:pizzaria|lanchonete|acaiteria))\b',
    'mobile': r'\b(?:celular|smartphone|mobile|responsivo)\b',
    'linguagem-informal': r'\b(?:erros? de portugues|erros? de digitacao|linguagem informal|abreviacoes|escrev[eo] errado)\b',
    'cardapio-proprio': r'\b(?:cardapio|cadapio|cartapio|site)\b',
    'modalidades': r'\b(?:entrega|retirada|entreaga|retiraada)\b',
    'contratacao': r'\b(?:quero contratar|como (?:faco (?:pra|para) )?(?:contratar|comecar))\b',
    'comissoes': r'\b(?:comiss(?:ao|oes)|comissao|comisoes|taxa por pedido|taxas por pedido|taxa por venda)\b',
}

# Compatibility anchors for callers without semantic question spans.
# The planner reconciles overlapping routes; this is not an article quota.


def requested_topics(text, available=None):
    folded = normalized(text)
    topics = {slug for slug, pattern in TOPIC_PATTERNS.items() if matches(pattern, folded)}
    # "Pedidos do iFood" describes the integration, not a second KDS question.
    operational = r'\b(?:cozinha|kds|kanban|preparo|retirada|entrega|mesa)\b'
    if 'integracoes' in topics and not matches(operational, folded):
        topics.discard('pedidos')
    if 'objecao-canais' in topics:
        topics.discard('gestao')
        topics.discard('cardapio-proprio')
    if 'cardapio-proprio' in topics and not matches(r'\b(?:crm|estoque|fidelidade|categorias|adicionais|meio a meio)\b', folded):
        topics.discard('gestao')
    if 'kds' in topics and not matches(r'\b(?:cozinha|preparo|pedidos|kanban)\b', folded):
        topics.discard('pedidos')
    if 'modalidades' in topics and not matches(r'\b(?:cozinha|kds|preparo|pedidos|kanban|mesa)\b', folded):
        topics.discard('pedidos')
    if 'mobile' in topics:
        topics.discard('cardapio-proprio')
    # A kitchen-only enquiry is covered by the specific KDS article when
    # published. Retain the operational article for workflow/board questions.
    if available is not None:
        if 'kds' not in available and 'kds' in topics:
            topics.discard('kds')
            topics.add('pedidos')
        elif ('kds' in available and 'pedidos' in topics
              and matches(r'\b(?:cozinha|kds)\b', folded)
              and not matches(r'\b(?:kanban|etapas|status|origem|mesa|retirada|entrega|preparo)\b', folded)):
            topics.discard('pedidos')
            topics.add('kds')
    return topics


def requested_period(text):
    """Resolve requested billing period without trusting the LLM's scope.

    Returns: None (no explicit period), 0 (compare all), or 1/3/6/12 months.
    Ambiguous multiple periods are treated as comparisons rather than guesses.
    """
    message = fold(text)
    all_requested = matches(r'\b(?:todos os planos|todos planos|4 planos|quatro planos|comparar planos|comparacao de planos|planos com descontos|tabela de planos|quais (?:sao os )?planos)\b', message)
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


def enforce_safety(conversation, knowledge):
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
    folded = normalized(text)
    if human_requested(text) or any(matches(pattern, folded) for pattern in HUMAN_GUARDS):
        raise ValueError('commercial_human_review_required')

    articles = {article.slug: article for article in knowledge}
    # Semantically unsafe explicit enquiries that article excerpts cannot settle
    # cannot be answered by a loosely related article.
    if matches(r'\b(?:pix|cartao|boleto)\b', folded) and 'pagamento' not in articles:
        # The payment methods are in the structured catalog, but the current
        # renderer cannot give a payment-specific answer yet.
        raise ValueError('commercial_payment_detail_review_required')
    return text


def enforce_selection(conversation, selection, knowledge):
    """Compatibility facade; the planner owns coverage, not a second topic pass."""
    from .commercial_plan import build_plan
    plan = build_plan(conversation, selection, knowledge)
    if plan.uncovered:
        raise ValueError('commercial_topics_uncovered')
    return plan.text
