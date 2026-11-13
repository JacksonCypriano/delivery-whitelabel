"""Contextual commercial replies: local matching + published facts + catalog.

No model selection contract, provider calls, quotas or tenant-agent imports.
The public compose interface remains (text, article_ids).
"""
from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from urllib.parse import urlsplit

from .commercial_context import conversation_context
from .commercial_quality_p14 import fiscal_scope, business_overview_requested, soften_value_objection
from .commercial_facts import facts_for
from .commercial_copy import select_units
from .commercial_local_knowledge import INTENTS, DETAILS, BUSINESSES, CLARIFY, AMBIGUOUS, VERSION
from .commercial_local_nlu import normalize, fold, has, intents_for, DECLINED_ACTION, DEMO_INVITE
from .commercial_smart_policy import HUMAN_GUARDS, LEGACY_FISCAL_GUARD, human_requested, matches

RESET = re.compile(r'\b(?:mudando de assunto|outro assunto|esquece isso|esqueca isso|vamos recomecar)\b', re.I)


class HumanReview(ValueError):
    def __init__(self, code, explanation='Preciso que nossa equipe confirme essa informação antes de responder.'):
        super().__init__(code)
        self.explanation = explanation


def recent_memory(conversation, current):
    """Read-only, contact-scoped memory. Human intervention, reset and TTL expire it."""
    rows = list(conversation.messages.order_by('-pk').values('text', 'reply', 'from_me', 'created_at', 'state')[:20])
    if not rows or RESET.search(normalize(current)):
        return '', []
    newest = rows[0]['created_at']
    customer, replies = [], []
    for row in rows:
        if row['from_me'] or row.get('state') in {'held', 'human', 'uncertain', 'sending'}:
            break
        stamp = row['created_at']
        if newest is None or stamp is None:
            break
        try:
            if not timedelta(0) <= newest - stamp <= timedelta(minutes=30):
                break
        except TypeError:
            break
        if row.get('reply'):
            replies.append(row['reply'])
        text = row.get('text') or ''
        if RESET.search(normalize(text)):
            break
        if text and text not in current.splitlines():
            customer.append(text)
    return '\n'.join(reversed(customer)), replies


def money(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0:
            raise ValueError
    except (ValueError, InvalidOperation, TypeError) as exc:
        raise HumanReview('invalid_catalog_price') from exc
    return f'{amount:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def price_lines(publication, period, *, equivalent=False):
    plans = publication['data']['plans']
    selected = sorted((p for p in plans if period == 0 or p['months'] == (period or 1)), key=lambda p: p['months'])
    if not selected:
        raise HumanReview('catalog_missing_plan')
    result = []
    for plan in selected:
        months, total = plan['months'], money(plan['total'])
        if months == 1:
            result.append(f"{plan['name']}: R$ {total} por mês, com pagamento antecipado.")
        elif months in {3, 6, 12}:
            discount = money(plan['discount']).rstrip('0').rstrip(',')
            result.append(f"{plan['name']}: R$ {total} por {months} meses, com {discount}% de desconto e pagamento antecipado.")
            if equivalent:
                monthly = (Decimal(str(plan['total'])) / months).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                result[-1] += f' Equivale a R$ {money(monthly)} por mês; o pagamento é antecipado pelo período completo, não uma cobrança mensal.'
        else:
            raise HumanReview('unapproved_plan_duration')
    return result


def published_sources(knowledge):
    latest = {}
    for article in knowledge:
        previous = latest.get(article.slug)
        if previous is None or article.version > previous.version:
            latest[article.slug] = article
        elif article.version == previous.version and article.pk != previous.pk:
            raise HumanReview('ambiguous_article_revision')
    return {slug: a for slug, a in latest.items() if a.published}


def retrieve(intent, q, sources, *, fiscal=None):
    candidates = ('pagamento', 'comissoes') if intent == 'payment' else INTENTS[intent].sources
    article = next((sources[s] for s in candidates if s in sources), None)
    if article is None:
        raise HumanReview('commercial_topics_uncovered')
    tags = {intent}
    if intent == 'fiscal':
        scope = fiscal or fiscal_scope(q)
        if scope not in {'service', 'store', 'both', 'ambiguous'}:
            raise HumanReview('commercial_fiscal_review_required')
        # No prose fallback for fiscal: only the reviewed scoped units qualify.
        compact = select_units(article, {'fiscal:' + scope})
        if compact is None:
            raise HumanReview('commercial_topics_uncovered')
        return compact
    if intent == 'gestao':
        facets = {'adicional': ('adicional', 'adicionais', 'personalizacoes'),
                  'meio': ('meio a meio',), 'crm': ('crm', 'clientes', 'historico'),
                  'automacao': ('automacao', 'automacoes'), 'identidade': ('identidade visual',),
                  'estoque': ('estoque',), 'fidelidade': ('fidelidade',)}
        specific = {f'gestao:{key}' for key, words in facets.items() if any(has(q, w) for w in words)}
        tags = specific or tags
    elif intent == 'pedidos':
        if has(q, 'mesa'):
            tags = {'pedidos:mesa'}
        elif has(q, 'mesma tela') or has(q, 'centralizar'):
            tags = {'pedidos:centralizacao'}
    elif intent == 'integracoes':
        channels = {channel for channel in ('ifood', '99food') if has(q, channel)}
        if len(channels) == 1:
            tags = {'integracoes:' + next(iter(channels))}
    elif intent == 'whatsapp' and re.search(r'\b(?:humano|assumir|equipe)\b', q):
        tags = {'whatsapp:humano'}
    elif intent == 'beneficios' and any(has(q, b) for b in BUSINESSES) and not business_overview_requested(q) and not re.search(r'\b(?:diferente|diferenca|diferenciais|oferece)\b', q):
        tags = {'beneficios:ramo'}
    elif intent == 'impressao':
        if has(q, 'motoboy') or has(q, 'motoboys'):
            tags = {'impressao:motoboy'}
        elif re.search(r'\b(?:dados|endereco|itens|pagamento)\b', q):
            tags = {'impressao:detalhes'}
    compact = select_units(article, tags)
    if compact is not None:
        return compact
    facts = facts_for(article)
    body = normalize(' '.join(f.text for f in facts))
    requirements = []
    if intent == 'gestao':
        requirements = [v for k, v in DETAILS.items() if k != 'entregadores'
                        and any(has(q, term) for term in (k, *v))]
    if intent == 'impressao' and re.search(r'\bmotoboys?\b', q):
        requirements = [('motoboy', 'motoboys')]
    if intent == 'entregadores':
        requirements = [DETAILS['entregadores']]
    if intent == 'pedidos' and has(q, 'mesa'):
        requirements = [DETAILS['mesa']]
    if intent == 'payment':
        requirements = [(term,) for term in ('pix', 'boleto', 'cartao') if has(q, term)]
        if not requirements:
            requirements = [('pagamento', 'pagamentos')]
    if any(not any(has(body, term) for term in group) for group in requirements):
        raise HumanReview('commercial_detail_uncovered')
    # Sentence selection is local. Preserve ALL conditions from the source,
    # alongside every sentence needed by a specific requested detail.
    selected = {0}
    for group in requirements:
        selected.update(i for i, f in enumerate(facts) if any(has(normalize(f.text), term) for term in group))
    if intent == 'beneficios':
        selected.update(i for i, f in enumerate(facts) if any(has(normalize(f.text), term) for term in ('cardapio', 'pedidos', 'operacao')))
    if intent == 'whatsapp' and re.search(r'\b(?:humano|assumir|equipe)\b', q):
        selected.update(i for i, f in enumerate(facts) if re.search(r'\b(?:humano|assumir|equipe)\b', normalize(f.text)))
        if not any(re.search(r'\b(?:humano|assumir|equipe)\b', normalize(f.text)) for f in facts):
            raise HumanReview('commercial_detail_uncovered')
    if intent == 'impressao' and re.search(r'\b(?:dados|endereco|itens|pagamento)\b', q):
        # Keep the approved document detail rather than inventing printed fields.
        selected.update(range(len(facts)))
    return tuple(f for i, f in enumerate(facts) if i in selected or f.required)


def compose(conversation, publication, knowledge, *, links=None, trace=None, handoff_signup=False):
    trace = trace if trace is not None else {}
    trace.update(engine=VERSION, intents=[], facts=[], uncovered=[], clarification=False, stage='discovery', fulfilled=[], catalog=[], links=[])
    current = conversation_context(conversation)
    memory, previous = recent_memory(conversation, current)
    q = normalize(current)
    if RESET.search(q):
        q = RESET.split(q)[-1].strip(' ,.!\n')
        memory, previous = '', []
    safety = normalize(current)
    scope = fiscal_scope(q, normalize(memory))
    detected, _ = intents_for(q, memory)
    trace['intents'] = sorted(detected)
    if scope == 'human':
        raise HumanReview('commercial_fiscal_review_required')
    # Only referential follow-ups reuse a previous integration for safety.
    if re.search(r'\b(?:liberado|homologado|disponivel)\b', q) and not has(q, '99food'):
        if has(normalize(memory.splitlines()[-1] if memory else ''), '99food'):
            safety = '99food ' + q
    if human_requested(safety) or any(matches(pattern, candidate) for pattern in HUMAN_GUARDS if pattern != LEGACY_FISCAL_GUARD for candidate in (safety, fold(current))):
        raise HumanReview('commercial_human_review_required')
    if re.search(r'\b(?:contador|advogado|cancelamento|estorno)\b', q):
        raise HumanReview('commercial_out_of_scope')
    # Perguntas sobre PRESTAÇÃO de serviços (motoboys próprios, entregas
    # feitas pela plataforma e disparos promocionais) precisam de validação
    # humana. Mera menção à logística/WhatsApp permanece respondível.
    if (re.search(r'\b(?:entrega|entregar|entregam)\s+(?:por\s+)?motoboys?\b', q)
            or re.search(r'\b(?:entrega|entregar|entregam)\s+(?:por\s+)?motoboys?\b', fold(current))
            or re.search(r'\b(?:voces|voc[eê]s)\s+(?:fazem|realizam|entregam|entrega)\b.{0,65}\b(?:marmita|pedido|comida|lanche|aqui)\b', q)
            or re.search(r'\b(?:manda|envia|dispara|faz)\b.{0,90}\b(?:promocao|promocoes)\b.{0,100}\b(?:todos|lista|massa|contatos)\b', q)):
        raise HumanReview('commercial_service_or_broadcast_review_required')
    if re.search(r'\bdesconto\b', q) and (re.search(r'\d+\s*%', q) or re.search(r'\b(?:extra|especial|negocia|negociar)\b', q)):
        raise HumanReview('commercial_negotiation_required')
    # Perguntas sobre o que foi dito ANTES nao sao pedidos novos de preco.
    # Consulta apenas mensagens processadas deste contato, nunca OTP/held/humano.
    from .commercial_history import answer_history_question
    historical = answer_history_question(conversation, current)
    if historical is not None:
        answer, history_topics = historical
        trace['intents'] = sorted('history_' + topic for topic in history_topics)
        trace['fulfilled'] = trace['intents'][:]
        trace['stage'] = 'discovery'
        return answer, []
    topics, period = intents_for(q, memory)
    overview = business_overview_requested(q) or bool(re.fullmatch(r'como funciona[ ?!.]*', q))
    if overview:
        topics.add('beneficios')
    # Contratação é assumida por uma pessoa NESTA conversa. Nunca enviar
    # o cliente de volta ao próprio número por um link wa.me.
    # A recusa ('não quero contratar') já é removida por intents_for.
    if handoff_signup and 'signup' in topics:
        trace['stage'] = 'contract'
        raise HumanReview('commercial_signup_handoff')
    if 'pricing' in topics and period is None and re.search(r'\b(?:esse|este|nesse|deste|mesmo) plano\b', q) and memory:
        _, prior_period = intents_for(memory.splitlines()[-1])
        if prior_period == 0:
            trace['clarification'] = True
            return 'Você se refere ao plano mensal, trimestral, semestral ou anual?', []
        period = prior_period
    if re.fullmatch(r'(?:sim|quero|pode|pode mandar)[!. ]*', q) and previous and DEMO_INVITE in previous[0]:
        topics.add('demo')
    if DECLINED_ACTION.search(q) and not topics:
        return 'Tudo bem. Se surgir outra dúvida sobre o sistema, pode me chamar.', []
    # Resolve a bare continuation only from the most recent customer topic.
    if not topics and re.search(r'\b(?:isso|esse|essa|ele|ela|tambem)\b', q) and memory:
        topics, period = intents_for(memory.splitlines()[-1])
    trace['intents'] = sorted(topics)
    sources = published_sources(knowledge)
    for word, question in AMBIGUOUS.items():
        if has(q, word) and not topics:
            trace['clarification'] = True
            if question in previous:
                raise HumanReview('commercial_ambiguity_unresolved')
            return question, []
    # Inspect independent clauses: never disguise an unknown extra question
    # with a complete-looking answer to the known first question.
    unknown = []
    for clause in re.split(r'[?;\n]+|\s+e\s+(?=(?:tem|faz|emite|aceita|oferece|integra)\b)', q):
        clause = clause.strip(' ,.')
        found, _ = intents_for(clause, memory)
        if not found and not business_overview_requested(clause) and not re.fullmatch(r'como funciona', clause) and re.search(r'^(?:e )?(?:tem|faz|emite|aceita|oferece|integra|como funciona)\b', clause):
            unknown.append(clause)
    if topics:
        for extra in re.split(r'\s+e\s+', q)[1:]:
            extra = extra.strip(' ,.?')
            found, _ = intents_for(extra, memory)
            # A bare, unmatched noun after conjunction can be a second feature.
            # 'é quanto?' vira 'e quanto?' na normalização de acentos.
            # O advérbio interrogativo não é um segundo recurso desconhecido.
            if (not found and re.fullmatch(r'[a-z]{5,}', extra)
                    and extra not in {'proprio', 'tambem', 'pronto', 'prontos',
                                      'endereco', 'pagamento', 'quanto'}
                    and not ('impressao' in topics and extra in {'itens', 'observacoes'})):
                unknown.append(extra)
    if unknown:
        trace['uncovered'] = ['unknown_question']
        trace['clarification'] = True
        if CLARIFY in previous:
            raise HumanReview('commercial_ambiguity_unresolved')
        return 'Ainda preciso esclarecer parte da sua pergunta. ' + CLARIFY, []
    if not topics:
        business_known = any(has(normalize(memory + '\n' + current), b) for b in BUSINESSES)
        greeting = re.search(r'\b(?:oi|ola|bom dia|boa tarde|boa noite)\b', q)
        business_statement = business_known and re.search(r'\b(?:tenho|sou|vendo|trabalho)\b', q)
        if greeting or business_statement:
            trace['stage'] = 'first_contact' if not previous else 'discovery'
            question = 'Qual é a maior dificuldade hoje na sua operação?' if business_known else 'Qual é o tipo do seu estabelecimento?'
            if question in previous:
                question = 'Sobre qual recurso você quer conversar?'
            return (('Olá! Sou o assistente comercial do VemDeDelivery. ' if greeting and not previous else '') + question), []
        if re.fullmatch(r'(?:obrigado|obrigada|valeu|vlw|ok|blz|beleza)[!. ]*', q):
            return 'Por nada! Se surgir outra dúvida, pode me chamar.', []
        trace['clarification'] = True
        if CLARIFY in previous:
            raise HumanReview('commercial_ambiguity_unresolved')
        return CLARIFY, []

    lines, used, seen = [], [], set()
    overview_covered = set()
    if 'pricing' in topics:
        lines.extend(price_lines(publication, period, equivalent=bool(re.search(r'\bpor mes\b', q))))
        trace['catalog_fingerprint'] = publication.get('fingerprint', '')
        trace['fulfilled'].append('pricing')
        trace['catalog'].extend(lines)
    for intent in sorted(topics - {'pricing', 'demo', 'signup'}):
        if intent in overview_covered:
            trace['fulfilled'].append(intent)
            continue
        if intent == 'payment' and re.search(r'\b(?:pagar|pago|assinatura|mensalidade|plano)\b', q):
            methods = publication['data'].get('payments', [])
            names = {'pix': 'Pix', 'boleto': 'boleto', 'card': 'cartão'}
            if not methods or any(m not in names for m in methods):
                raise HumanReview('catalog_payment_uncovered')
            lines.append('Para a assinatura, o catálogo aprovado informa: ' + ', '.join(names[m] for m in methods) + '.')
            trace['catalog_fingerprint'] = publication.get('fingerprint', '')
            trace['fulfilled'].append('payment')
            trace['catalog'].append(lines[-1])
            continue
        try:
            if intent == 'beneficios' and overview:
                # Um resumo de produto requer fatos concretos de fontes publicadas;
                # a unidade "ramo" isolada nunca responde "o que o sistema faz?".
                overview_article = sources.get('visao-geral')
                try:
                    facts = select_units(overview_article, {'beneficios:overview'}) if overview_article else None
                except ValueError:
                    facts = None
                if facts is not None:
                    overview_covered = {'cardapio', 'cozinha'}
                    if not re.search(r'\b(?:mesa|centraliz\w*|mesma tela|status|etapas|kanban)\b', q):
                        overview_covered.add('pedidos')
                if facts is None:
                    # Old publications remain usable until editorial review.
                    facts = tuple(fact for topic in ('beneficios', 'cardapio', 'pedidos', 'cozinha')
                                  for fact in retrieve(topic, q if topic == 'beneficios' else '', sources))
            else:
                facts = retrieve(intent, q, sources, fiscal=scope)
        except (HumanReview, ValueError):
            trace['uncovered'].append(intent)
            raise HumanReview('commercial_topics_uncovered')
        trace['fulfilled'].append(intent)
        if intent == 'fiscal' and scope == 'ambiguous':
            trace['clarification'] = True
        fragments = []
        for fact in facts:
            if fact.text not in seen:
                seen.add(fact.text)
                fragments.append(fact.text)
                trace['facts'].append(dict(key=fact.key, article_id=fact.article_id,
                                           version=fact.version, sha256=fact.body_sha256, text=fact.text, intent=intent))
                if fact.article_id not in used:
                    used.append(fact.article_id)
        if fragments:
            lines.append(' '.join(fragments))
    if topics & {'demo', 'signup'}:
        if links is None:
            from .commercial_models import CommercialControl
            control = CommercialControl.objects.filter(pk=1).first()
            links = {'demo': control.demo_url, 'signup': control.contact_url} if control else {}
        # Both independently requested actions retain their approved links.
        for action in ('demo', 'signup'):
            if action not in topics:
                continue
            url = links.get(action, '')
            parsed = urlsplit(url)
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or any(c.isspace() for c in url):
                raise HumanReview('commercial_' + action + '_human_required')
            line = ('Acesse a demonstração: ' if action == 'demo' else 'Para contratar, fale com nossa equipe: ') + url
            lines.append(line)
            trace['fulfilled'].append(action)
            trace['links'].append(line)
    # Qualificação somente na apresentação global, sem repetir perguntas anteriores.
    if (overview and topics == {'beneficios'}
            and not re.search(r'\b(?:problema|dificuldade)\b', normalize(memory + '\n' + current))
            and 'Qual é a maior dificuldade hoje na sua operação?' not in previous
            and sum(map(len, lines)) < 650):
        lines.append('Qual é a maior dificuldade hoje na sua operação?')
    # Qualification follows an objection only once, never every feature/price reply.
    if topics & {'objecao-valor', 'objecao-canais'}:
        question = 'Qual é a maior dificuldade hoje na sua operação?'
        if question not in previous and not re.search(r'\b(?:problema|dificuldade)\b', normalize(memory + q)) and sum(map(len, lines)) < 400:
            lines.append(question)
    if (topics & {'beneficios', 'objecao-canais'} and not topics & {'demo', 'signup', 'pricing'}
            and re.search(r'\b(?:interesse|gostei|me ajuda|conhecer)\b', q)
            and not DECLINED_ACTION.search(normalize(memory + '\n' + current))
            and not any(DEMO_INVITE in reply or 'Acesse a demonstra' in reply for reply in previous)
            and not any(line.endswith('?') for line in lines)
            and sum(map(len, lines)) + len(DEMO_INVITE) < 500):
        lines.append(DEMO_INVITE)
    trace['stage'] = ('contract' if 'signup' in topics else 'demo' if 'demo' in topics else
                      'objection' if any(t.startswith('objecao') for t in topics) else
                      'pricing' if 'pricing' in topics else 'discovery')
    if not lines:
        raise HumanReview('commercial_topics_uncovered')
    if 'objecao-valor' in topics:
        lines = [soften_value_objection(line) for line in lines]
    return '\n\n'.join(lines), used
