"""Read-only local configuration review. No Evolution/LLM status calls."""
from urllib.parse import urlsplit
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Count
from apps.prospecting.commercial import articles, validate_instance
from apps.prospecting.commercial_models import CommercialControl, CommercialMessage
from apps.prospecting.commercial_catalog import published_catalog
from apps.prospecting.commercial_copy import units
from apps.billing.models import BillingSettings


def valid_url(url):
    p = urlsplit(url or '')
    return bool(p.scheme == 'https' and p.hostname and not p.username and not p.password
                and not any(c.isspace() for c in url))


class Command(BaseCommand):
    help = 'Revisão local sem rede/alterações; nunca autoriza ativação automaticamente.'
    requires_system_checks = []

    def handle(self, *args, **options):
        control = CommercialControl.objects.filter(pk=1).first()
        if not control:
            self.stdout.write('BLOQUEIO: controle não configurado; nada foi criado.')
            return
        self.stdout.write('Motor: contextual local; nenhuma cota/modelo necessário.')
        self.stdout.write('Chave global: ' + str(bool(getattr(settings, 'COMMERCIAL_AGENT_ENABLED', False))))
        self.stdout.write('Controle habilitado: ' + str(control.enabled))
        if BillingSettings.objects.filter(pk=1).exists():
            try:
                published_catalog(control)
                self.stdout.write('Catálogo: aprovado e correspondente.')
            except ValueError:
                self.stdout.write('BLOQUEIO: catálogo precisa de revisão.')
        else:
            self.stdout.write('BLOQUEIO: cobrança não configurada.')
        try:
            validate_instance(control.instance)
            self.stdout.write('Instância: identificador isolado e válido; conexão remota NÃO consultada.')
        except ValueError:
            self.stdout.write('BLOQUEIO: instância ausente, inválida ou reservada.')
        self.stdout.write('URLs comerciais HTTPS: ' + str(all(valid_url(v) for v in (control.demo_url, control.contact_url))))
        token = getattr(settings, 'COMMERCIAL_AGENT_WEBHOOK_TOKEN', '')
        self.stdout.write('Callback local configurado: ' + str(len(token) >= 32 and valid_url(getattr(settings, 'COMMERCIAL_AGENT_WEBHOOK_URL', ''))))
        knowledge = articles()
        modern = 0
        for article in knowledge:
            try:
                modern += units(article) is not None
            except (ValueError, TypeError):
                self.stdout.write('BLOQUEIO: unidades editoriais inválidas: ' + article.slug)
        self.stdout.write(f'Artigos publicados: {len(knowledge)}; com unidades concisas: {modern}.')
        required = {'visao-geral', 'cardapio-proprio', 'whatsapp', 'pedidos', 'kds', 'impressao', 'integracoes', 'comissoes', 'gestao', 'modalidades', 'objecao-valor', 'objecao-canais'}
        missing = sorted(required - {a.slug for a in knowledge})
        if missing:
            self.stdout.write('BLOQUEIO de cobertura: ' + ', '.join(missing))
        counts = dict(CommercialMessage.objects.values('state').annotate(n=Count('pk')).values_list('state', 'n'))
        self.stdout.write('Fila (contagens sem contatos): ' + str(counts))
        if counts.get('sending') or counts.get('uncertain'):
            self.stdout.write('BLOQUEIO: conciliar envios incertos; não recolocar em fila automaticamente.')
        self.stdout.write('Revisão editorial, teste real autorizado e autorização EXPRESSA do proprietário ainda são obrigatórios. Nada ativado.')
