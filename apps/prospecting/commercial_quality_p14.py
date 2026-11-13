"""Regras locais de qualidade comercial, sem modelos, rede ou fatos novos.

Não modifica preços nem artigos aprovados; apenas detecta perguntas que exigem
revisão e melhora a apresentação de respostas aprovadas.
"""
import re


# Os termos chegam normalizados (sem acentos) pelo motor comercial.
# Não confundir documento fiscal com comprovante NÃO fiscal da cozinha.
_FISCAL_DOCUMENT = re.compile(
    r'\b(?:notas? (?:fiscais|fiscal)|nf[- ]?e|nfe|nf[- ]?c[- ]?e|nfce|'
    r'nf[- ]?s[- ]?e|cupom fiscal|documentos? (?:fiscal|fiscais))\b'
)
# Scope is shared by classification and retrieval; it contains no public copy.
_FISCAL_SERVICE = re.compile(r'\b(?:assinatura|mensalidade|anual|contratacao|contratar|contrato|contratante|servicos?|plataforma|cnpj|valor que pago|nota do pagamento)\b')
_FISCAL_STORE = re.compile(r'\b(?:vendas?|vendo|pedidos?|clientes?|consumidor|caixa|emissor|pizzaria|hamburgueria|loja|nf-?e|nfc-?e|cupom fiscal)\b')
_FISCAL_SPECIFIC = re.compile(
    r'\b(?:icms|iss|cfop|ncm|aliquota|tribut\w*|imposto|simples nacional|'
    r'certificado|a1|contador|cnae|retencao|deducao|xml|danfe|segunda via|'
    r'enviar|envia|manda|mandar|prazo|corrigir|cancelar|nfs-?e)\b'
)


def fiscal_scope(q, memory=''):
    """Resolve only a fiscal request, with bounded caller-supplied chat memory.

    Unrelated pricing/integration clauses must not decide the invoice scope.
    A generic 'emitem?' follows only the immediately preceding fiscal topic.
    """
    document = bool(_FISCAL_DOCUMENT.search(q) or re.search(
        r'\b(?:nf|emissao fiscal|emissor fiscal|notafiscal|nota fisca[l]*|notas? (?:da|das|do|dos) '
        r'(?:venda|vendas|pedido|pedidos|mensalidade|assinatura|pagamento)|'
        r'(?:emite|emitir|emitem|gera|gerar|geram) (?:a |uma )?nota|automatiz\w* (?:as )?notas|faturam para cnpj)\b', q))
    history = memory.splitlines()[-20:]
    last = history[-1] if history else ''
    prior = fiscal_scope(last, '\n'.join(history[:-1])) if last else None
    if not document:
        if prior and re.fullmatch(r'(?:e )?(?:voces )?(?:emitem|emite|gera|geram|tem)[ ?!.]*', q):
            return prior
        if prior and re.fullmatch(r'(?:e |a |da |das |do |dos |sobre )*(?:assinatura|mensalidade|vendas|pedidos|loja)[ ?!.]*', q):
            return 'service' if _FISCAL_SERVICE.search(q) else 'store'
        return None
    if (_FISCAL_SPECIFIC.search(q)
            or re.search(r'\bquando (?:voces )?(?:emit\w*|envia\w*|receb\w*)\b', q)):
        # Ordinary "manda nota do pagamento" has an approved existence answer;
        # actual delivery, deadlines and document-type requests need verification.
        if not re.fullmatch(r'(?:voces )?manda nota do pagamento[ ?!.]*', q):
            return 'human'
    clauses = re.split(r'[,;?\n]+|\s+e\s+(?=(?:tem|emite|emitem|gera|geram|integra)\b)', q)
    scoped = [c for c in clauses if _FISCAL_DOCUMENT.search(c) or re.search(r'\b(?:nota|nf|fiscal|cnpj)\b', c)]
    target = ' '.join(scoped) or q
    service, store = bool(_FISCAL_SERVICE.search(target)), bool(_FISCAL_STORE.search(target))
    # "plataforma/sistema emite para meus clientes" is a store request.
    if store and not re.search(r'\b(?:assinatura|mensalidade|contratacao|servico)\b', target):
        service = False
    if service and re.search(r'\b(?:automatic\w*|prazo)\b', q):
        return 'human'
    if service and store:
        return 'both'
    if service:
        return 'service'
    if store:
        return 'store'
    if last:
        if prior in {'service', 'store'}:
            return prior
        if not prior:
            service, store = bool(_FISCAL_SERVICE.search(last) or re.search(r'\bplano\b', last)), bool(_FISCAL_STORE.search(last))
            if service != store:
                return 'service' if service else 'store'
    return 'ambiguous'


def fiscal_needs_human(q, memory=''):
    """Only undocumented fiscal procedures need human verification (P15)."""
    return fiscal_scope(q, memory) == 'human'


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
