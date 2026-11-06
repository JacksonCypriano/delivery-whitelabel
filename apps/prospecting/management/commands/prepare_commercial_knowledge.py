"""Prepare reviewable drafts from implemented modules; never publishes claims."""
from django.core.management.base import BaseCommand
from apps.prospecting.commercial_models import CommercialArticle

ARTICLES = [
    ('visao-geral','O que é o VemDeDelivery','O VemDeDelivery é uma plataforma para organizar a operação do seu estabelecimento: cardápio online, pedidos diretos, acompanhamento do preparo e gestão da loja. Qual parte da sua operação você quer melhorar primeiro?'),
    ('pedidos','Pedidos e cozinha','O painel reúne os pedidos elegíveis, identifica a origem e permite acompanhar as etapas de preparo. A cozinha usa o KDS sobre os mesmos pedidos. Entrega e retirada têm ações próprias.'),
    ('whatsapp','Atendimento da loja','O agente de atendimento do restaurante usa uma conexão WhatsApp própria da loja. Ele é diferente de mim: sou o assistente comercial do VemDeDelivery. A disponibilidade do agente da loja depende da configuração e habilitação da conta.'),
    ('integracoes','iFood e 99Food','Há integração de pedidos com iFood e implementação de integração com a 99Food. A liberação depende da configuração, do ambiente e da homologação de cada canal. Nossa equipe precisa conferir a disponibilidade para o seu estabelecimento antes de confirmar a ativação.'),
    ('impressao','Impressão térmica','O sistema possui fila de impressão e comprovantes de cozinha, entrega e pedido completo. Impressão direta depende de configurar o agente no computador da loja e validar a compatibilidade da impressora; não posso garantir seu equipamento sem esse teste.'),
    ('gestao','Gestão do estabelecimento','O painel reúne gestão de produtos, categorias e preços, clientes, cupons, automações e informações financeiras. As funcionalidades disponíveis respeitam as permissões e habilitações da loja.'),
    ('comissoes','Vendas diretas','O VemDeDelivery não cobra comissão sobre pedidos diretos. Taxas de meios de pagamento e de marketplaces terceiros são independentes. Serviços de cadastro ou alteração de produtos são opcionais e contratados à parte.'),
    ('contratacao','Contratação e demonstração','Posso ajudar você a conhecer o produto e encaminhar uma demonstração com nossa equipe. Demonstração não significa assinatura gratuita. Condições excepcionais, prazos e disponibilidade de integrações precisam de confirmação humana.'),
]

class Command(BaseCommand):
    help='Prepara artigos comerciais como rascunhos, sem publicar, enviar mensagens ou alterar planos.'
    def add_arguments(self,parser): parser.add_argument('--apply',action='store_true')
    def handle(self,*args,**options):
        for slug,title,body in ARTICLES:
            if CommercialArticle.objects.filter(slug=slug).exists():
                self.stdout.write(f'Preservado: {slug}');continue
            if options['apply']:
                CommercialArticle.objects.create(slug=slug,version=1,title=title,body=body,published=False)
            self.stdout.write(('Rascunho criado: ' if options['apply'] else 'Prévia: ')+slug)
