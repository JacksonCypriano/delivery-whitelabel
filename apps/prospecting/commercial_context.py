"""Conservative context window for inbound platform sales messages.

No network access, database mutations, or model invocation. The function accepts
newest-first rows and stops at the previous answer/human intervention boundary.
"""
from datetime import timedelta


def recent_context(rows, *, max_messages=6, window_seconds=180, max_chars=1200):
    """Return newest contiguous inbound text, in original chronological order.

    Rows: dicts with text, from_me, reply, created_at.
    A previous answered message is a hard boundary, preventing repeated answers.
    """
    chosen = []
    most_recent_at = None
    for row in rows:
        # A mensagem mais recente pode estar 'held' enquanto aguarda o agente;
        # isso nao autoriza reutilizar mensagens 'held' mais antigas.
        if (row.get('from_me') or row.get('reply')
                or row.get('state') in {'human', 'uncertain', 'sending'}
                or (row.get('state') == 'held' and chosen)):
            break
        text = str(row.get('text') or '').strip()
        if not text:
            break
        created_at = row.get('created_at')
        if most_recent_at is not None and created_at is not None:
            try:
                if created_at > most_recent_at or most_recent_at - created_at > timedelta(seconds=window_seconds):
                    break
            except TypeError:
                break
        if not chosen:
            most_recent_at = created_at
        chosen.append(text)
        if len(chosen) > max_messages:
            raise ValueError('context_requires_human')
    if not chosen:
        raise ValueError('empty_inbound')
    result = '\n'.join(reversed(chosen))
    if len(result) > max_chars:
        raise ValueError('context_requires_human')
    return result


def conversation_context(conversation):
    rows = conversation.messages.order_by('-pk').values(
        'text', 'from_me', 'reply', 'created_at', 'state'
    )[:12]
    return recent_context(rows)
