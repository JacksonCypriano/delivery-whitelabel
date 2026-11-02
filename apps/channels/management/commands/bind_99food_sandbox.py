"""Bind a verified sandbox 99Food shop to a tenant without enabling orders.

Only a pre-verified mapping should be supplied by an operator.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction, IntegrityError

from apps.channels.models import Connection
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = 'Vincula uma loja sandbox 99Food ao tenant, mantendo operações remotas bloqueadas.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant-slug', required=True)
        parser.add_argument('--app-shop-id', required=True)
        parser.add_argument('--shop-id', required=True)
        parser.add_argument('--apply', action='store_true', help='Confirma a gravação; sem isto, apenas verifica.')

    def handle(self, *args, **options):
        slug = options['tenant_slug'].strip()
        shop_id = options['shop_id'].strip()
        app_shop_id = options['app_shop_id'].strip()
        if not slug or not shop_id or not app_shop_id:
            raise CommandError('Identificadores não podem estar vazios.')
        if app_shop_id != 'vdd-' + slug:
            raise CommandError('AppShopID não corresponde ao tenant informado.')
        tenant = Tenant.objects.filter(slug=slug).first()
        if tenant is None:
            raise CommandError('Tenant não encontrado.')
        if not shop_id.isdecimal():
            raise CommandError('ID da loja 99Food inválido.')
        with transaction.atomic():
            existing = (Connection.objects.select_for_update()
                        .filter(provider='99food', mode='test', merchant_id=shop_id).first())
            if existing and existing.tenant_id != tenant.pk:
                raise CommandError('Esta loja 99Food já pertence a outro tenant.')
            # Existing connections for this tenant must not be silently repointed.
            other = (Connection.objects.select_for_update()
                     .filter(provider='99food', mode='test', tenant=tenant)
                     .exclude(merchant_id=shop_id))
            # A previously created placeholder should be handled explicitly, not modified.
            if other.exists():
                raise CommandError('Tenant já possui outra conexão 99Food de teste. Revise manualmente.')
            if not options['apply']:
                self.stdout.write('VALIDADO_SEM_GRAVAR: tenant=%s; shop_id=%s; existente=%s' % (
                    slug, shop_id, 'sim' if existing else 'não'))
                return
            if existing:
                # Never change enabled or status of an existing connection.
                self.stdout.write('JA_VINCULADA: tenant=%s; shop_id=%s; enabled=%s' % (
                    slug, shop_id, existing.enabled))
                return
            try:
                connection = Connection.objects.create(
                    tenant=tenant, provider='99food', mode='test',
                    merchant_id=shop_id, merchant_name='VemDeDelivery - Loja Teste',
                    enabled=False, status='awaiting_authorization',
                )
            except IntegrityError as exc:
                raise CommandError('Conflito ao vincular loja. Verifique a associação atual.') from exc
            self.stdout.write('VINCULADA: connection_id=%s; tenant=%s; shop_id=%s; enabled=false' % (
                connection.pk, slug, shop_id))
