"""Versioned retrieval vocabulary, NOT a second store of product claims.

Only aliases, article routes and factual anchors live here. Public prose is
read from the latest published CommercialArticle revisions on each request.
Review changes to this file like code; review factual changes through the
existing article draft/version/publication workflow.
"""
from dataclasses import dataclass

VERSION = 'contextual-p15'


@dataclass(frozen=True)
class Intent:
    sources: tuple
    aliases: tuple


INTENTS = {
    'fiscal': Intent(('notas-fiscais',), ()),
    'cardapio': Intent(('cardapio-proprio',), ('cardapio', 'site', 'catalogo digital')),
    'whatsapp': Intent(('whatsapp',), ('whatsapp', 'robo', 'atendimento automatico', 'atendimento automatizado', 'agente', 'atendente humano', 'intervencao humana')),
    'cozinha': Intent(('kds', 'pedidos'), ('cozinha', 'kds', 'preparo')),
    'pedidos': Intent(('pedidos',), ('pedido', 'pedidos', 'kanban', 'painel operacional', 'etapas', 'status', 'mesa', 'mesma tela', 'centralizar', 'centralizacao')),
    'impressao': Intent(('impressao',), ('impressao', 'impressora', 'imprimir', 'imprime', 'termica', 'comprovante')),
    'modalidades': Intent(('modalidades', 'pedidos'), ('entrega', 'retirada')),
    'entregadores': Intent(('entregadores', 'pedidos'), ('gestao de entregadores', 'gerenciar motoboys', 'gerenciar entregadores', 'gerencia entregadores', 'painel de motoboys')),
    'integracoes': Intent(('integracoes',), ('ifood', '99food', 'integracao', 'integra', 'marketplace')),
    'gestao': Intent(('gestao',), ('adicional', 'adicionais', 'categoria', 'produto', 'crm', 'estoque', 'fidelidade', 'automacao', 'cupom de desconto', 'meio a meio', 'identidade visual')),
    'mobile': Intent(('mobile',), ('celular', 'smartphone', 'responsivo')),
    'linguagem': Intent(('linguagem-informal',), ('erro de portugues', 'erros de portugues', 'erro de digitacao', 'abreviacao', 'linguagem informal', 'escreve errado')),
    'beneficios': Intent(('visao-geral',), ('o que oferece', 'o que faz', 'diferenca', 'diferente', 'diferencial', 'beneficio', 'ajudar minhas vendas', 'serve para', 'da para usar', 'funcionalidade')),
    'objecao-valor': Intent(('objecao-valor',), ('caro', 'compensa', 'vale a pena', 'poucos pedidos')),
    'objecao-canais': Intent(('objecao-canais',), ('instagram', 'canal proprio')),
    'objecao-cadastro': Intent(('objecao-cadastro',), ('sem tempo', 'nao tenho tempo')),
    'objecao-socio': Intent(('objecao-socio',), ('socio',)),
    'comissoes': Intent(('comissoes',), ('comissao', 'comissoes', 'taxa por pedido', 'taxa por venda')),
}

# Explicit details must occur in the selected published source, not just in
# its slug. No assertion of stock, CRM, couriers or payment capability by name.
DETAILS = {
    'estoque': ('estoque',), 'crm': ('crm', 'clientes', 'historico'),
    'fidelidade': ('fidelidade',), 'automacao': ('automacao', 'automacoes'),
    'adicional': ('adicional', 'adicionais', 'personalizacoes'),
    'meio a meio': ('meio a meio',), 'mesa': ('mesa',),
    'entregadores': ('motoboy', 'motoboys', 'entregadores', 'entregador'),
}
BUSINESSES = ('pizzaria', 'pizza', 'restaurante', 'hamburguer', 'hamburgueria',
              'lanchonete', 'lanche', 'acai', 'acaiteria', 'padaria', 'marmitaria',
              'cafeteria', 'bar', 'doceria', 'sorveteria')
CLARIFY = 'Você quer saber sobre os planos, os recursos do sistema ou a contratação?'
AMBIGUOUS = {
    'cupom': 'Você quer saber sobre cupom de desconto ou impressão de comprovantes?',
    'taxa': 'Você se refere à mensalidade, à comissão sobre pedidos ou às taxas de pagamento?',
}
