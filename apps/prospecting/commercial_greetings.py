"""Saudacoes contextuais para o agente comercial local (sem rede, sem estado extra).

Apenas respostas realmente submetidas ao provedor contam como apresentacao.
Mensagens held/human/uncertain nao sao evidencia de saudacao entregue.
"""
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from .commercial_local_nlu import normalize, has

_CONFIRMED = frozenset({'submitted', 'sent', 'delivered', 'read'})


def _hours_setting(name, default):
    try:
        value = int(getattr(settings, name, default))
    except (ValueError, TypeError):
        value = default
    return max(1, min(value, 72))


def _greeting_for(now, *, first):
    hour = timezone.localtime(now, timezone.get_default_timezone()).hour
    if hour < 12:
        greeting = 'Bom dia!'
    elif hour < 18:
        greeting = 'Boa tarde!'
    else:
        greeting = 'Boa noite!'
    if first:
        return f'{greeting} 👋 Sou o assistente virtual comercial do VemDeDelivery. Estou aqui para ajudar você a conhecer a plataforma.'
    return f'{greeting} 😊 Que bom falar com você novamente!'


def presentation_for(conversation, message, *, now=None):
    """Retorna saudacao apropriada, ou string vazia para conversa continua.

    Usa mensagens do proprio contato e somente envios confirmados pelo sistema.
    Nenhum texto de OTP e retornado ou registrado aqui.
    """
    now = now or message.created_at or timezone.now()
    prior = conversation.messages.exclude(pk=message.pk).order_by('-pk').values(
        'reply', 'state', 'created_at', 'from_me', 'text'
    )[:100]
    last_activity = None
    greeted = False
    human_contact = False
    for row in prior:
        state, stamp = row.get('state'), row.get('created_at')
        is_agent_sent = bool(row.get('reply')) and state in _CONFIRMED
        is_human_sent = bool(row.get('from_me')) and state in _CONFIRMED
        # Nao usar held/queued/human/uncertain como atividade, exceto que
        # uma resposta de humano confirmada ja inicia o relacionamento.
        if not (is_agent_sent or is_human_sent):
            continue
        if is_agent_sent:
            greeted = True
        if is_human_sent:
            human_contact = True
        if stamp and (last_activity is None or stamp > last_activity):
            last_activity = stamp
    if not greeted and not human_contact:
        return _greeting_for(now, first=True)
    if last_activity is None:
        return ''
    elapsed = now - last_activity
    if elapsed < timedelta(0):
        return ''
    tz = timezone.get_default_timezone()
    crossed_day = timezone.localtime(now, tz).date() != timezone.localtime(last_activity, tz).date()
    threshold = _hours_setting('COMMERCIAL_GREETING_NEW_DAY_HOURS', 6) if crossed_day else _hours_setting('COMMERCIAL_GREETING_SAME_DAY_HOURS', 8)
    return _greeting_for(now, first=False) if elapsed >= timedelta(hours=threshold) else ''


def enhance_reply(conversation, message, reply):
    """Humaniza a resposta ja aprovada, sem reescrever fatos/valores/condicoes."""
    greeting = presentation_for(conversation, message)
    if not greeting:
        return reply
    original = str(reply or '').strip()
    if not original:
        return original
    # Resposta de despedida nao deve ganhar uma apresentacao/saudacao.
    if original.startswith(('Por nada!', 'Tudo bem.')):
        return original
    # Nao duplicar a saudacao caso o motor base ja tenha uma abertura.
    if original.startswith(('Olá!', 'Bom dia!', 'Boa tarde!', 'Boa noite!')):
        original = original.removeprefix('Olá! Sou o assistente comercial do VemDeDelivery.').strip()
        if original.startswith(('Olá!', 'Bom dia!', 'Boa tarde!', 'Boa noite!')):
            return original
    result = greeting + '\n\n' + original
    # Apenas primeiro contato, preco isolado, sem convite ja presente.
    if ('Sou o assistente virtual' in greeting and 'R$' in original and len(original) < 245
            and '?' not in original and len(result) < 500):
        q = normalize(message.text or '')
        if any(has(q, term) for term in ('pizzaria', 'restaurante', 'hamburgueria', 'marmitaria', 'acaiteria')):
            result += '\n\nHoje, sua maior dificuldade é receber pedidos ou organizar a operação?'
        else:
            result += '\n\nQual é o tipo do seu estabelecimento?'
    return result
