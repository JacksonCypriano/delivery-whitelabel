"""Conservative pt-BR matching adapted from the store-agent approach.

No imports from tenant/product code and no models, provider or network calls.
"""
import re
import unicodedata
from difflib import SequenceMatcher
from .commercial_smart_policy import ALIASES as COMMON_ALIASES, requested_period
from .commercial_local_knowledge import INTENTS, BUSINESSES

ALIASES = {**COMMON_ALIASES, 'qto': 'quanto', 'qnt': 'quanto', 'qt': 'quanto',
           'ql': 'qual', 'cmo': 'como', 'funsiona': 'funciona', 'precissu': 'preciso',
           'prorpio': 'proprio', 'digitao': 'digital', 'p': 'para', 'pra': 'para',
           'pro': 'para o', 'cum': 'com', 'c': 'com', 'wpp': 'whatsapp',
           'zap': 'whatsapp', 'whats': 'whatsapp', 'pgto': 'pagamento',
           'vlr': 'valor', 'naum': 'nao', 'nn': 'nao', 'n': 'nao',
           'ta': 'esta', 'eh': 'e', 'oq': 'o que', 'tm': 'tem'}
VOCAB = {word for item in INTENTS.values() for phrase in item.aliases for word in phrase.split()}
VOCAB |= set(BUSINESSES) | {'preco', 'mensalidade', 'contratar', 'demonstracao', 'anual', 'mensal', 'semestral', 'trimestral'}
# Negation/conditions are never fuzzy-normalized into feature vocabulary.
PROTECTED = {'nao', 'nunca', 'nem', 'sem', 'somente', 'apenas', 'exceto', 'salvo', 'se', 'quando'}
DECLINED_ACTION = re.compile(r'\bnao (?:quero|preciso|desejo)(?: (?:uma?|ver|a|o|de))* (?:demo|demonstracao|contratar|contratacao|assinar)\b')
DEMO_INVITE = 'Quer ver a demonstração do VemDeDelivery?'
JOINABLE = {'tem', 'quero', 'quanto', 'custa', 'preco', 'cardapio', 'cozinha', 'impressora', 'whatsapp', 'ifood', 'retirada', 'entrega'}


def fold(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value).casefold()) if not unicodedata.combining(c))


def variants(word):
    result = {word}
    if len(word) > 4 and word.endswith('s'):
        result.add(word[:-1])
    for ending, replacement in (('oes', 'ao'), ('ais', 'al'), ('eis', 'el')):
        if len(word) > 5 and word.endswith(ending):
            result.add(word[:-len(ending)] + replacement)
    return result


def normalize(value):
    def token(match):
        word = match[0]
        if word in ALIASES:
            return ALIASES[word]
        if word in PROTECTED or word in VOCAB:
            return word
        singular = variants(word) & VOCAB
        if len(singular) == 1:
            return next(iter(singular))
        # Joined words are segmented only when there is one exact domain split.
        splits = [(word[:i], word[i:]) for i in range(3, len(word)-2)
                  if word[:i] in JOINABLE and word[i:] in JOINABLE]
        if len(splits) == 1:
            return ' '.join(splits[0])
        if len(word) < 6:
            return word
        ranked = sorted(((SequenceMatcher(None, word, v).ratio(), v)
                         for v in VOCAB if len(v) >= 5), reverse=True)
        if ranked and ranked[0][0] >= .87 and (len(ranked) == 1 or ranked[0][0]-ranked[1][0] >= .06):
            return ranked[0][1]
        return word
    return re.sub(r'\b[a-z0-9]+\b', token, fold(value))


def has(text, phrase):
    return re.search(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', text) is not None


def intents_for(text, memory=''):
    q = DECLINED_ACTION.sub(' ', normalize(text))
    topics = {key for key, item in INTENTS.items() if any(has(q, p) for p in item.aliases)}
    period = requested_period(q)
    if period is not None or re.search(r'\b(?:preco|valor|custo|custa|plano|planos|mensalidade|quanto (?:fica|sai|custa))\b', q):
        topics.add('pricing')
    if re.search(r'\b(?:pix|boleto|cartao|formas? de pagamento|como (?:pago|pagar))\b', q):
        topics.add('payment')
    if re.search(r'\b(?:demo|demonstracao|quero conhecer|tenho interesse em conhecer)\b', q) and not re.search(r'\bnao (?:quero|preciso)\b', q):
        topics.add('demo')
    if re.search(r'\b(?:contratar|contratacao|assinar|como (?:faco para )?comecar)\b', q):
        topics.add('signup')
    channel_context = normalize((memory.splitlines()[-1] if memory else '') + '\n' + text)
    channel_objection = ('ifood' in channel_context and re.search(r'\b(?:so vendo|so recebo|ja vendo|vale a pena|me ajuda|compensa)\b', channel_context))
    if channel_objection and re.search(r'\b(?:vale a pena|me ajuda|compensa|para que|por que)\b', q):
        topics.add('objecao-canais')
    if 'objecao-canais' in topics:
        topics.discard('cardapio')
        topics.discard('objecao-valor')
        if not re.search(r'\bintegra\w*\b', q):
            topics.discard('integracoes')
    if 'linguagem' in topics:
        topics.discard('whatsapp')
    if 'mobile' in topics:
        topics.discard('cardapio')
    if 'gestao' in topics and re.search(r'\b(?:adicional|adicionais|meio a meio)\b', q):
        topics.discard('cardapio')
    # Apenas mencionar "pedidos" dentro de outra pergunta não caracteriza
    # uma intenção independente. Mas uma pergunta explícita sobre organizar,
    # acompanhar ou centralizar pedidos precisa manter o assunto "pedidos",
    # mesmo ao citar iFood, KDS ou impressão na mesma mensagem.
    explicit_order_management = bool(re.search(
        r'\b(?:organiz\w*|centraliz\w*|gerenci\w*|acompanh\w*|control\w*)\b.{0,55}\bpedidos?\b'
        r'|\b(?:painel|central|kanban)\b.{0,45}\bpedidos?\b'
        r'|\bpedidos?\b.{0,45}\b(?:painel|central|kanban)\b', q
    ))
    if (topics & {'integracoes', 'impressao', 'modalidades', 'objecao-valor', 'comissoes'}
            and not explicit_order_management
            and not re.search(r'\b(?:kanban|etapas|status|mesa|painel|mesma tela)\b', q)):
        topics.discard('pedidos')
    # Pedido + KDS sao assuntos distintos quando solicitados explicitamente.
    # 'pedidos da cozinha' por si so nao implica uma pergunta separada sobre KDS.
    kitchen_explicit = bool(re.search(
        r'\b(?:kds|tela (?:da |de )?cozinha|tem (?:uma? )?(?:tela (?:da |de )?)?cozinha)\b', q
    )) or (has(q, 'cozinha') and bool(re.search(r'\b(?:tem|possui|existe)\b.{0,45}\bcozinha\b', q)))
    if 'pedidos' in topics and not (kitchen_explicit or (has(q, 'kanban') and (has(q, 'cozinha') or has(q, 'kds')))):
        topics.discard('cozinha')
    # "Imprimir pedido na cozinha" é sobre comprovante, não sobre usar KDS.
    # Preservar KDS quando também for explicitamente pedido na mesma mensagem.
    if ('impressao' in topics and 'cozinha' in topics
            and not re.search(r'\b(?:kds|tela (?:da |de )?cozinha|tem (?:uma? )?cozinha)\b', q)
            and re.search(r'\b(?:impressao|impressora|imprimir|imprime|comprovante)\b.{0,80}\bcozinha\b', q)):
        topics.discard('cozinha')
    # Mencao ao canal de chegada nao equivale a solicitar o agente WhatsApp.
    if 'whatsapp' in topics and re.search(r'\b(?:recebo|recebe|recebemos|receber|vem|chegam|entram)\b.{0,85}\bpedidos?\b', q):
        if not re.search(r'\b(?:agente|robo|automatizad[oa]|atendimento|responde|responder|cliente)\b', q):
            topics.discard('whatsapp')
    if 'pedidos' in topics and has(q, 'mesma tela'):
        topics.discard('cardapio')
    if 'beneficios' in topics and re.search(r'\b(?:diferente|diferenca|diferenciais)\b', q):
        topics.add('comissoes')
    if 'impressao' in topics and re.search(r'\b(?:imprimir|imprime|impressao)\s+(?:de |os |o )?pedidos?\s+(?:da |de )?cozinha\b', q):
        topics.discard('cozinha')
    if 'objecao-valor' in topics and not re.search(r'\b(?:quanto|qual (?:o )?preco|qual (?:o )?valor)\b', q):
        topics.discard('pricing')
    return topics, period
