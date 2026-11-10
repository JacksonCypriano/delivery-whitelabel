"""Regras locais de qualidade comercial, sem modelos, rede ou fatos novos.

Não modifica preços nem artigos aprovados; apenas detecta perguntas que exigem
revisão e melhora a apresentação de respostas aprovadas.
"""
import re


def fiscal_needs_human(q):
    """Escopo fiscal explícito precisa de especialista, não de clarificação genérica."""
    return bool(
        re.search(r'\b(?:nota[s]? fiscal|nf[- ]?e|nfce|nf[- ]?c[- ]?e|cupom fiscal)\b', q)
        and re.search(
            r'\b(?:emitir|emite|emitem|emissao|gerar|gera|faz|fazem|automatic[ao]|integr(?:a|acao)|tem|possui)\b',
            q,
        )
    )


def business_overview_requested(q):
    """Pedido explícito para explicar o produto; não basta citar o ramo."""
    return bool(re.search(
        r'\b(?:o que (?:o |esse |este )?(?:sistema|vemdedelivery|software|app|aplicativo|plataforma) (?:faz|oferece)|'
        r'(?:sistema|vemdedelivery|software|plataforma) (?:faz o que|serve para que)|'
        r'como (?:o |esse |este )?(?:sistema|vemdedelivery|software|plataforma) funciona|'
        r'quais (?:sao )?(?:as )?(?:funcoes|funcionalidades|recursos)|'
        r'o que (?:voces|a plataforma) oferecem)\b', q
    ))


def soften_value_objection(line):
    """Empatia sem promessas de retorno, prazo ou desconto."""
    line = str(line or '').strip()
    if line.startswith('Para avaliar o custo,'):
        return 'Entendo sua preocupação com o investimento. ' + line
    return line
