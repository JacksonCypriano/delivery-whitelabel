"""Bateria comercial P14: executar somente via python manage.py shell < arquivo.

Não usa receive/process_message; todas as inserções são revertidas.
Não chama APIs externas, não requer WhatsApp em homologação.
"""
import uuid
from unittest.mock import patch
from django.db import transaction

from apps.prospecting.commercial_models import (
    CommercialControl, CommercialConversation, CommercialMessage,
)
from apps.prospecting.commercial import articles
from apps.prospecting.commercial_catalog import published_catalog
from apps.prospecting.commercial_local import compose, HumanReview
from apps.prospecting.commercial_greetings import enhance_reply

# Formato: nome, mensagens em sequência, esperado da última mensagem, termos obrigatórios
# 'human' significa transferência legítima, sem alegação comercial não confirmada.
scenarios = [
    ('01 Primeiro contato', ['Oi, quanto custa o sistema?'], 'answer', ['149,90']),
    ('02 Linguagem informal', ['boa tarde vcs tem cardapio online e qto custa?'], 'answer', ['cardápio', '149,90']),
    ('03 Apresentação para pizzaria', ['Tenho uma pizzaria, o que o sistema faz?'], 'answer', ['cardápio', 'pedidos']),
    ('04 Perguntas combinadas', ['Integra com iFood? Tem KDS, impressão e painel de pedidos?'], 'answer', ['iFood', 'KDS', 'impressão', 'painel']),
    ('05 Plano anual', ['Quanto custa o plano anual?'], 'answer', ['1.528,98']),
    ('06 Plano trimestral', ['E o plano de 3 meses, quanto fica?'], 'answer', ['427,22']),
    ('07 Objeção de preço', ['Achei caro, por que vale a pena?'], 'answer', ['Entendo', 'custo']),
    ('08 Agente WhatsApp da loja', ['O sistema atende meus clientes pelo WhatsApp?'], 'answer', ['WhatsApp']),
    ('09 99Food', ['Vocês já têm integração com 99Food?'], 'answer', ['99Food', 'homologação']),
    ('10 Estoque desconhecido', ['Tem controle de estoque automático?'], 'human', []),
    ('11 Impressão de cozinha', ['Consigo imprimir os pedidos direto na impressora?'], 'answer', ['impressão']),
    ('12 Motoboy terceirizado', ['Vocês fornecem motoboy para fazer as entregas?'], 'human', []),
    ('13 Negociação especial', ['Consegue fazer 50% de desconto pra mim?'], 'human', []),
    ('14 Contratação', ['Gostei, quero contratar agora!'], 'human', []),
    ('15 Pedido humano', ['Quero falar com uma pessoa de verdade'], 'human', []),
    ('16 Memória do ramo', ['Tenho uma pizzaria e recebo pedidos pelo iFood.', 'Você lembra qual é meu tipo de estabelecimento?'], 'answer', ['pizzaria']),
    ('17 Memória do plano', ['Quanto custa o plano anual?', 'Qual foi o plano que eu perguntei anteriormente?'], 'answer', ['anual']),
    ('18 Continuidade', ['Tenho uma hamburgueria.', 'E quanto custa o sistema?'], 'answer', ['149,90']),
    ('19 Erros ortográficos', ['vcs tem cadapioo e impresora pra cosinha?'], 'answer', ['cardápio', 'impressão']),
    ('20 Nota fiscal eletrônica', ['O sistema faz emissão de nota fiscal eletrônica automaticamente?'], 'human', []),
    ('21 NFC-e', ['Emite NFC-e diretamente pelo sistema?'], 'human', []),
    ('22 Cupom não fiscal', ['Tem comprovante de cozinha para imprimir?'], 'answer', ['comprovantes']),
    ('23 Funcionalidades hamburgueria', ['Tenho hamburgueria. Como o sistema funciona?'], 'answer', ['pedidos']),
    ('24 Preço sem período', ['Quanto custa?'], 'answer', ['149,90']),
    ('25 Desconto anual', ['Qual o valor anual com desconto?'], 'answer', ['1.528,98']),
    ('26 Pizzas meio a meio', ['Consigo cadastrar pizza meio a meio?'], 'answer', ['meio a meio']),
    ('27 Retirada de pedidos', ['Consigo oferecer retirada no balcão?'], 'answer', ['retirada']),
    ('28 Cartão e Pix', ['Como funciona o pagamento por Pix e cartão?'], 'answer', ['Pix']),
    ('29 Sem comissão', ['Vocês cobram comissão por pedido direto?'], 'answer', ['comissão']),
    ('30 Centralização do iFood', ['Organiza pedidos do iFood com os do cardápio próprio?'], 'answer', ['pedidos']),
    ('31 WhatsApp + KDS', ['Tenho delivery, atende no whats e tem tela da cozinha?'], 'answer', ['WhatsApp', 'KDS']),
    ('32 Sem garantias', ['Vocês garantem que vou dobrar as vendas?'], 'human', []),
    ('33 Pedido de gratuidade', ['Posso testar 90 dias grátis?'], 'human', []),
    ('34 Histórico sem informação', ['Você lembra qual plano eu perguntei anteriormente?'], 'answer', ['Não encontrei']),
    ('35 Encaminhar serviço fiscal', ['Vocês geram nota fiscal automaticamente para minha pizzaria?'], 'human', []),
    ('36 Início e seguimento', ['Oi!', 'Tenho uma pizzaria, quero saber dos pedidos.'], 'answer', ['pedidos']),
]


# Casos adicionais P14.1: positivos e negativos, sem modificar os 36 originais.
# Opcional 5o campo: trechos que NAO podem aparecer na resposta.
scenarios += [
    ('37 Nota fiscal plural', ['Vocês geram nota fiscal pra pizzaria?'], 'human', []),
    ('38 Nota fiscal singular', ['Vcs gera nota fiscal automaticamente?'], 'human', []),
    ('39 Emissão NF-e', ['O sistema emite NF-e?'], 'human', []),
    ('40 NFC-e', ['É possível emitir NFC-e?'], 'human', []),
    ('41 Cupom fiscal', ['Consegue gerar cupom fiscal?'], 'human', []),
    ('42 Documento fiscal', ['Tem emissão de documento fiscal?'], 'human', []),
    ('43 Nota fiscal sem verbo de emissão', ['Vocês têm nota fiscal eletrônica?'], 'human', []),
    ('44 Nota fiscal junto de preço', ['Quanto custa e voces geram nota fiscal?'], 'human', []),
    ('45 Visão geral restaurante', ['Tenho restaurante. Quais as funcionalidades?'], 'answer',
     ['cardápio', 'painel', 'KDS'], ['O VemDeDelivery atende restaurantes, pizzarias']),
    ('46 Visão geral lanchonete', ['Tenho uma lanchonete, como o sistema funciona?'], 'answer',
     ['cardápio', 'painel', 'KDS'], ['O VemDeDelivery atende restaurantes, pizzarias']),
    ('47 Visão geral alternativa', ['Sou pizzaria, o que esse sistema oferece?'], 'answer',
     ['cardápio', 'painel', 'KDS'], ['O VemDeDelivery atende restaurantes, pizzarias']),
    ('48 Visão geral sem ramo', ['O que o VemDeDelivery faz?'], 'answer', ['cardápio', 'painel', 'KDS']),
    ('49 Visão geral informal', ['tenho hamburgueria, me explica o sistema'], 'answer',
     ['cardápio', 'painel', 'KDS']),
    ('50 Pergunta específica de KDS', ['Como funciona o KDS?'], 'answer', ['KDS'],
     ['O VemDeDelivery atende restaurantes']),
    ('51 Impressão de cozinha sem KDS', ['Imprime pedidos da cozinha?'], 'answer',
     ['impressão'], ['KDS é a tela', 'O painel operacional organiza']),
    ('52 Comprovante não fiscal', ['Tem comprovante de cozinha para imprimir?'], 'answer',
     ['não fiscais'], ['KDS é a tela']),
    ('53 Impressão sem painel', ['Tem impressão dos comprovantes de cozinha?'], 'answer',
     ['impressão'], ['O painel operacional organiza', 'KDS é a tela']),
    ('54 Comissão sem painel', ['Cobram comissão por pedido direto?'], 'answer',
     ['comissão'], ['O painel operacional organiza', 'KDS é a tela']),
    ('55 Taxa em pedidos sem painel', ['Existe comissão sobre pedidos diretos?'], 'answer',
     ['comissão'], ['O painel operacional organiza']),
    ('56 Pedido + impressão explícitos', ['Tem painel de pedidos e impressão?'], 'answer',
     ['painel', 'impressão']),
    ('57 KDS + impressão explícitos', ['Tem KDS e impressão de cozinha?'], 'answer',
     ['KDS', 'impressão']),
    ('58 Visão geral + preço', ['Tenho hamburgueria. Como o sistema funciona e quanto custa?'],
     'answer', ['cardápio', 'painel', 'KDS', '149,90']),
    ('59 Visão geral + iFood', ['Tenho pizzaria. O que o sistema faz? Integra iFood?'],
     'answer', ['cardápio', 'painel', 'KDS', 'iFood']),
    ('60 Visão geral + nota fiscal', ['Tenho pizzaria. O que o sistema faz e emite nota fiscal?'],
     'human', []),
    ('61 Preço anual + comissão', ['Qual o preço anual e tem comissão sobre pedidos diretos?'],
     'answer', ['1.528,98', 'comissão'], ['O painel operacional organiza']),
    ('62 Somente ramo', ['Tenho uma pizzaria.'], 'answer',
     ['Qual é a maior dificuldade'], ['KDS é a tela']),
    ('63 Continuidade após ramo', ['Tenho uma pizzaria.', 'Como o sistema funciona?'],
     'answer', ['cardápio', 'painel', 'KDS']),
    ('64 Semestral', ['Quanto fica o semestral?'], 'answer', ['809,46'], ['KDS é a tela']),
    ('65 Fiscal informal', ['vcs fazem emissao de nfe?'], 'human', []),
    ('66 Fiscal e comprovante', ['Tem comprovantes e vocês emitem NF-e?'], 'human', []),
    ('67 Nota fiscal isolada', ['Nota fiscal?'], 'human', []),
    ('68 Nota fiscal de serviço', ['Vocês emitem NFS-e?'], 'human', []),
    ('69 Regressão funcionalidades restaurante', ['Tenho restaurante, quais as funcionalidades?'],
     'answer', ['cardápio', 'painel', 'KDS'], ['O VemDeDelivery atende restaurantes, pizzarias']),
    ('70 Funcionalidades normalizadas', ['Quais são as funcionalidades do sistema?'],
     'answer', ['cardápio', 'painel', 'KDS']),
    ('71 Recursos gerais', ['Quais os recursos do VemDeDelivery?'],
     'answer', ['cardápio', 'painel', 'KDS']),
    # P14.1 - fechamento da lacuna de documentos fiscais no singular/plural.
    ('72 Documento fiscal singular', ['O sistema emite documento fiscal?'], 'human', []),
    ('73 Documentos fiscais plural', ['Vocês geram documentos fiscais?'], 'human', []),
    ('74 Documento fiscal combinado', ['Quanto custa e tem emissão de documento fiscal?'], 'human', []),
]


# P15: a regra oficial substitui o handoff genérico fiscal dos P14/14.1.
# Preservamos cada entrada original; NFS-e (68) continua exigindo confirmação
# de tipo documental específico. A negativa da emissão das vendas é obrigatória.
_fiscal_corrected = {20, 21, 35, 37, 38, 39, 40, 41, 42, 43, 44, 60, 65, 66, 67, 72, 73, 74}
scenarios = [
    (name, messages, 'answer',
     ['não possui integração', 'não fiscais'] + (['149,90'] if int(name[:2]) in {44, 74} else []),
     ['emitimos automaticamente', 'emissão fiscal disponível'])
    if int(name[:2]) in _fiscal_corrected else (name, messages, expected, terms, *extra)
    for name, messages, expected, terms, *extra in scenarios
]
scenarios += [
    ('75 NF mensalidade', ['Preciso da nota fiscal da mensalidade.'], 'answer', ['emite nota fiscal', 'assinatura'], ['não possui integração']),
    ('76 NF anual', ['Consigo nota fiscal da assinatura anual?'], 'answer', ['assinatura'], ['R$']),
    ('77 NF contratação', ['Quero contratar, mas preciso de nota fiscal.'], 'human', []),
    ('78 NF CNPJ', ['Vocês faturam para CNPJ?'], 'answer', ['emite nota fiscal']),
    ('79 NF pedidos', ['Preciso da nota fiscal dos pedidos.'], 'answer', ['não possui integração', 'não fiscais']),
    ('80 NF contexto assinatura', ['Quanto custa o plano anual?', 'E a nota fiscal?'], 'answer', ['assinatura'], ['não possui integração']),
    ('81 NF contexto vendas', ['Como organizo as vendas da minha loja?', 'E a nota fiscal?'], 'answer', ['não possui integração']),
    ('82 NF informal', ['vcs emite notafisca da mensalidade'], 'answer', ['assinatura']),
    ('83 Fiscal combinado', ['Quanto custa, integra com iFood, tem KDS e emite nota?'], 'answer', ['149,90', 'iFood', 'KDS', 'não possui integração']),
    ('84 Tributação específica', ['Qual CFOP da nota fiscal?'], 'human', []),
    ('85 Equivalência anual', ['Quanto sai por mês no plano anual?'], 'answer', ['127,42', '1.528,98', 'não uma cobrança mensal']),
    ('86 Contratação informal', ['blz quero fecha'], 'human', []),
    ('87 Emissão contextual', ['Preciso da nota fiscal da mensalidade.', 'Vocês emitem?'], 'answer', ['assinatura']),
    ('88 Diferença fiscal', ['Qual a diferença entre comprovante e nota fiscal?'], 'answer', ['não substituem', 'não fiscais']),
    ('89 Impressora informal', ['tem impreçora'], 'answer', ['compatibilidade', 'não fiscais']),
    ('90 Menor plano', ['Qual o plano mais barato?'], 'answer', ['149,90', 'antecipado']),
    ('91 Documento específico', ['Pode enviar XML da nota fiscal?'], 'human', []),
    ('92 Mudar escopo', ['Preciso da nota fiscal da mensalidade.', 'E das vendas?'], 'answer', ['não possui integração'], ['Sim!']),
    ('93 Prazo não inventado', ['Quando emitem a nota fiscal da assinatura?'], 'human', []),
    ('94 Automação fiscal assinatura', ['A nota fiscal da mensalidade é automática?'], 'human', []),
    ('95 Confirmação informal', ['como funsiona'], 'answer', ['cardápio', 'KDS']),
]


def forbid(*args, **kwargs):
    raise RuntimeError('BATERIA: tentativa de acesso externo BLOQUEADA')


passed = 0
failed = 0
handoffs = 0
answers = 0
print('========== BATERIA P15 — VPS, SIMULAÇÃO LOCAL ==========', flush=True)
print('Cenários:', len(scenarios))
print('Envio WhatsApp: BLOQUEADO; transação: ROLLBACK')

with patch('requests.sessions.Session.request', side_effect=forbid), \
     patch('apps.integrations.whatsapp_agent.client.TenantEvolutionClient.send_text', side_effect=forbid), \
     patch('apps.integrations.whatsapp_agent.client.TenantEvolutionClient.status', side_effect=forbid):
    with transaction.atomic():
        control = CommercialControl.objects.get(pk=1)
        publication = published_catalog(control)
        knowledge = articles()
        assert publication['valid'] and knowledge
        for scenario in scenarios:
            name, messages, expected, terms, *extra = scenario
            forbidden_terms = extra[0] if extra else ()
            conversation = CommercialConversation.objects.create(
                instance='battery-p14-' + uuid.uuid4().hex[:12],
                phone='5500000000000', name='Bateria P14 temporária',
            )
            actual = None
            response = ''
            print('\n' + '-' * 65)
            print(name)
            for message in messages:
                row = CommercialMessage.objects.create(
                    conversation=conversation,
                    provider_id='test:' + uuid.uuid4().hex,
                    text=message, from_me=False, state='queued',
                )
                print('CLIENTE:', message)
                try:
                    reply, sources = compose(conversation, publication, knowledge, handoff_signup=True)
                    reply = enhance_reply(conversation, row, reply)
                    actual = 'answer'
                    response = reply
                    print('AGENTE:', reply[:1400])
                    row.reply, row.state = reply, 'submitted'
                    row.save(update_fields=['reply', 'state'])
                    answers += 1
                except HumanReview as exc:
                    actual = 'human'
                    response = str(exc)
                    print('TRANSFERÊNCIA HUMANA:', response)
                    handoffs += 1
                    break
                except Exception as exc:
                    actual = 'error'
                    response = type(exc).__name__ + ': ' + str(exc)[:150]
                    print('ERRO:', response)
                    break
            found_terms = all(term.casefold() in response.casefold() for term in terms)
            unwanted = [term for term in forbidden_terms if term.casefold() in response.casefold()]
            # Besides keywords, reject repeated sentences in any answer.
            import re
            sentences = [part.strip().casefold() for part in re.split(r'(?<=[.!?])\s+', response) if part.strip()]
            repeated = actual == 'answer' and len(sentences) != len(set(sentences))
            ok = actual == expected and found_terms and not unwanted and not repeated
            if ok:
                passed += 1
                print('AVALIAÇÃO AUTOMÁTICA: PASSOU')
            else:
                failed += 1
                print('AVALIAÇÃO AUTOMÁTICA: REVISAR; esperado=', expected,
                      'obtido=', actual, 'termos=', terms, 'indevidos=', unwanted, 'repeticao=', repeated)
        # Não altera a produção: linhas temporárias são revertidas; sequências PostgreSQL podem avançar.
        transaction.set_rollback(True)

print('\n' + '=' * 65)
print('TOTAL:', len(scenarios), '| PASSOU:', passed, '| REVISAR:', failed)
print('INTERAÇÕES RESPONDIDAS:', answers, '| TRANSFERÊNCIAS:', handoffs)
print('Nenhuma mensagem real enviada. Dados temporários revertidos.')
print('ATENÇÃO: aprovação automática por termos não substitui auditoria humana das respostas.')

if failed:
    raise SystemExit(1)
