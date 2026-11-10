"""Add new reviewable content only. Never supersede published revisions."""
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.prospecting.commercial_models import CommercialArticle

ARTICLES = (
    ('objecao-valor', 'Avaliar o investimento', 'Para avaliar se compensa, considere o trabalho de organizar pedidos, cardápio e cozinha em um só sistema. O VemDeDelivery oferece esses recursos; o resultado depende da operação da sua loja. Qual dessas tarefas mais toma seu tempo hoje?'),
    ('objecao-canais', 'Instagram e iFood', 'O cardápio próprio complementa seus canais de venda e permite receber pedidos diretos. A integração de pedidos do iFood depende da configuração e liberação para a loja. Você pretende manter os canais atuais e conhecer o canal próprio?'),
    ('objecao-cadastro', 'Tempo para cadastrar produtos', 'O painel permite gerenciar produtos, categorias e preços. Serviços de cadastro ou alteração de produtos são opcionais e contratados à parte. Nossa equipe pode conferir o serviço adequado e as condições publicadas para você.'),
    ('objecao-socio', 'Decisão com sócio', 'Você pode avaliar com seu sócio os recursos e as condições do catálogo. Quais dúvidas vocês precisam esclarecer antes de decidir?'),
)

class Command(BaseCommand):
    help = 'Prévia de artigos do pacote 07; --apply cria somente rascunhos ausentes.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')

    @transaction.atomic
    def handle(self, *args, **options):
        for slug, title, body in ARTICLES:
            if CommercialArticle.objects.filter(slug=slug).exists():
                self.stdout.write('Preservado: ' + slug)
                continue
            if options['apply']:
                CommercialArticle.objects.create(slug=slug, version=1, title=title, body=body)
            self.stdout.write(('Rascunho: ' if options['apply'] else 'Prévia: ') + slug + '\n' + body)
