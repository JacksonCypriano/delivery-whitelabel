"""Short reviewed-copy candidates in the existing versioned catalog, never auto-published."""
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.prospecting.commercial_models import CommercialArticle

# The renderer has no parallel fact store: only published DB revisions are sent.
ARTICLES = (
    ('pedidos', 'Pedidos e cozinha', 'O painel organiza os pedidos por origem e etapa de preparo. O KDS acompanha esses pedidos na cozinha.'),
    ('impressao', 'Impressão de pedidos', 'Sim, há impressão de comprovantes de cozinha e entrega. A impressão direta exige agente no computador e validação da compatibilidade da impressora.'),
    ('whatsapp', 'Atendimento WhatsApp', 'O agente atende pelo WhatsApp da loja conforme as funções habilitadas. A equipe pode assumir a conversa quando necessário.'),
    ('integracoes', 'Integrações de pedidos', 'Há integração com iFood e implementação para 99Food. A ativação depende de configuração e homologação; a equipe confirma a disponibilidade para sua loja.'),
    ('objecao-valor', 'Vale a pena para a loja?', 'Pode valer a pena para reunir cardápio próprio, pedidos e cozinha em um só sistema. Avalie quais tarefas isso simplifica na sua loja; não há garantia de vendas ou economia.'),
    ('objecao-canais', 'Canal próprio e canais atuais', 'O cardápio próprio complementa Instagram e iFood: organiza produtos e pedidos diretos para a operação da loja. A integração do iFood depende de configuração e liberação para sua conta.'),
    ('kds', 'O que é KDS?', 'KDS é a tela da cozinha para acompanhar os pedidos e suas etapas de preparo.'),
    ('mobile', 'Cardápio no celular', 'Sim, o cardápio online se adapta à tela do celular, permitindo consultar produtos e fazer pedidos pelo navegador.'),
    ('linguagem-informal', 'Linguagem informal', 'O agente trata abreviações e erros comuns de digitação. Pode pedir esclarecimentos ou encaminhar à equipe quando não entender; a compreensão não é perfeita.'),
    ('cardapio-proprio', 'Cardápio online próprio', 'Sim, sua loja tem um cardápio online próprio para apresentar produtos e receber pedidos diretos, conforme a configuração da loja.'),
    ('modalidades', 'Entrega e retirada', 'Sim, a loja pode configurar entrega e retirada, com etapas próprias no painel. O VemDeDelivery gerencia a operação, mas não fornece motoboys próprios.'),
)


class Command(BaseCommand):
    help = 'Prévia do pacote 08. --apply cria rascunhos; --revise-existing autoriza novas revisões de artigos existentes.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--revise-existing', action='store_true')

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write('Nada será publicado. Pela governança atual, uma nova revisão em rascunho suspende a anterior até aprovação.')
        for slug, title, body in ARTICLES:
            rows = CommercialArticle.objects.select_for_update().filter(slug=slug).order_by('-version')
            latest = rows.first()
            if latest and latest.body == body and latest.title == title:
                self.stdout.write('Preservado (já preparado): ' + slug)
                continue
            self.stdout.write('\n' + slug + ': ' + body)
            if latest and not options['revise_existing']:
                self.stdout.write('Existente preservado; revisar manualmente ou usar --revise-existing.')
                continue
            if options['apply']:
                CommercialArticle.objects.create(slug=slug, title=title, body=body,
                    version=latest.version + 1 if latest else 1, published=False)
                self.stdout.write('Rascunho criado: ' + slug)
