"""Regras locais de qualidade comercial, sem modelos, rede ou fatos novos.

Não modifica preços nem artigos aprovados; apenas detecta perguntas que exigem
revisão e melhora a apresentação de respostas aprovadas.
"""
import re


# Os termos chegam normalizados (sem acentos) pelo motor comercial.
# Não confundir documento fiscal com comprovante NÃO fiscal da cozinha.
_FISCAL_DOCUMENT = re.compile(
    r'\b(?:notas? (?:fiscais|fiscal)|nf[- ]?e|nfe|nf[- ]?c[- ]?e|nfce|'
    r'nf[- ]?s[- ]?e|cupom fiscal|documentos? fiscais?)\b'
)
_FISCAL_REQUEST = re.compile(
    r'\b(?:emit\w*|emiss\w*|ger\w*|gerac\w*|faz|fazem|fazer|'
    r'automatic\w*|integr\w*|tem|ter|possui|possuem|oferec\w*|'
    r'consigo|consegue|conseguem|pode|podem|da para|sai|saem|'
    r'preciso|quero|existe|inclui|inclus\w*|disponiv\w*)\b'
)


def fiscal_needs_human(q):
    """Dúvida sobre documento fiscal requer confirmação humana, mesmo junto a outros assuntos."""
    return bool(_FISCAL_DOCUMENT.search(q) and (_FISCAL_REQUEST.search(q) or '?' in q))


def business_overview_requested(q):
    """Pergunta sobre a plataforma como um todo (não sobre uma função isolada)."""
    product = r'(?:sistema|vemdedelivery|software|app|aplicativo|plataforma)'
    reference = r'(?:o |esse |este |essa |esta |seu |sua |nosso |nossa )?'
    return bool(
        re.search(r'\bo que ' + reference + product + r' (?:faz|oferece|tem|entrega)\b', q)
        or re.search(r'\b' + reference + product + r' (?:faz o que|serve para que|serve pra que)\b', q)
        or re.search(r'\bcomo (?:que )?' + reference + product + r' funciona\b', q)
        or re.search(r'\bcomo funciona ' + reference + product + r'\b', q)
        or re.search(r'\b(?:quais (?:sao )?(?:(?:as|os) )?(?:funcao|funcoes|funcionalidades?|recursos?)|'
                     r'o que (?:voces|a plataforma) oferecem)\b', q)
        or re.search(r'\b(?:me explica|explica|explique|me conta) (?:como funciona |o que faz )?'
                     + reference + product + r'\b', q)
        or (re.search(r'\b(?:tenho|sou|meu|minha|trabalho)\b', q)
            and re.search(r'\bcomo funciona\s*(?:[?!.]|$)', q))
    )


def soften_value_objection(line):
    """Empatia sem promessas de retorno, prazo ou desconto."""
    line = str(line or '').strip()
    if line.startswith('Para avaliar o custo,'):
        return 'Entendo sua preocupação com o investimento. ' + line
    return line
