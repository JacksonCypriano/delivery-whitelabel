"""Conservative pt-BR commercial intent selection; no pricing, URLs or prose generated.

Only returns identifiers from reviewed articles and an allowed question key.
Unclear and unsupported requests are escalated to human review.
"""
import re
import unicodedata
from difflib import get_close_matches

TOPICS = {
    'visao-geral': ('sistema', 'plataforma', 'solucao', 'funciona', 'conhecer', 'apresentacao', 'vemdedelivery'),
    'pedidos': ('pedido', 'cozinha', 'kds', 'preparo', 'kanban', 'comanda', 'retirada', 'entrega', 'motoboy', 'delivery'),
    'whatsapp': ('whatsapp', 'zap', 'wpp', 'atendimento', 'robo', 'agente', 'automacao', 'mensagem', 'responder'),
    'integracoes': ('ifood', '99food', 'integracao', 'marketplace', 'aplicativo', 'conectar'),
    'impressao': ('impressao', 'impressora', 'termica', 'cupom', 'imprimir', 'nota'),
    'gestao': ('gestao', 'cliente', 'crm', 'relatorio', 'produto', 'categoria', 'estoque', 'financeiro'),
    'comissoes': ('comissao', 'taxa', 'comissoes'),
    'contratacao': ('contratar', 'contratacao', 'demonstracao', 'demo', 'teste', 'assinar', 'implantacao'),
}
PRICING = ('preco', 'valor', 'custa', 'custo', 'mensalidade', 'plano', 'desconto', 'quanto', 'qto', 'qt', 'pagamento', 'reais')
SENSITIVE = ('reembolso', 'cancelamento', 'reclamacao', 'processo judicial', 'advogado', 'garantia de resultado', 'estorno', 'fraude')
HELLO = ('oi', 'ola', 'opa', 'bom dia', 'boa tarde', 'boa noite', 'quero conhecer', 'tenho interesse')
ALIASES = {
    'cardapioo':'cardapio', 'cadapio':'cardapio', 'cardapio':'produto',
    'entreaga':'entrega', 'impresora':'impressora', 'impresssora':'impressora',
    'integraçao':'integracao', 'integarcao':'integracao',
    'zap':'whatsapp', 'wpp':'whatsapp', 'whats':'whatsapp',
    'mensal':'mensalidade', 'mensalidad':'mensalidade',
    'cozinh':'cozinha', 'ifod':'ifood', 'ifoodi':'ifood',
}
VOCAB = set(PRICING) | {w for vals in TOPICS.values() for w in vals}


def fold(text):
    text = ''.join(char for char in unicodedata.normalize('NFKD', str(text).casefold()) if not unicodedata.combining(char))
    return text


def tokens_of(text):
    words = re.findall(r'[a-z0-9]+', fold(text))
    result = set()
    for word in words:
        word = ALIASES.get(word, word)
        if word.endswith('s') and word[:-1] in VOCAB:
            word = word[:-1]
        if word not in VOCAB and len(word) >= 5:
            matches = get_close_matches(word, VOCAB, n=1, cutoff=0.83)
            if matches:
                word = matches[0]
        result.add(word)
    return result


def choose(text, knowledge):
    """Select <=2 approved articles; raise ValueError when human care is safer."""
    raw = fold(text)
    if not raw.strip() or len(raw) > 1200:
        raise ValueError('empty_or_complex_inbound')
    if any(term in raw for term in SENSITIVE):
        raise ValueError('sensitive_request_requires_human')
    words = tokens_of(raw)
    pricing = bool(words.intersection(PRICING))
    scored = []
    for article in knowledge:
        matches = words.intersection(TOPICS.get(article.slug, ()))
        if matches:
            scored.append((-len(matches), article.slug, article.pk))
    scored.sort()
    # Two articles maximum is a deliberate approved-content limit. If a lead
    # asks for more than two distinct nonpricing topics, escalate instead of
    # silently ignoring questions.
    if len(scored) > 2:
        raise ValueError('multi_topic_requires_human')
    ids = [item[2] for item in scored]
    if not ids and not pricing:
        if raw.strip(' !?.') in HELLO:
            return {'article_ids': [], 'pricing': False, 'question':'business', 'human':False}
        raise ValueError('unknown_intent_requires_human')
    business_known = bool({'pizzaria', 'pizza', 'hamburgueria', 'lanchonete', 'restaurante', 'acaiteria', 'padaria', 'cafeteria'}.intersection(words))
    question = 'demo' if pricing else ('channels' if business_known else 'pain')
    return {'article_ids':ids, 'pricing':pricing, 'question':question, 'human':False}
