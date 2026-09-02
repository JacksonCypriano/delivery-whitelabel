import ipaddress
from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.utils.crypto import get_random_string
from apps.tenants.admin_security import ProtectedAdminAuthenticationForm
from apps.tenants.admin_site import tenant_admin_site, super_admin_site


class Command(BaseCommand):
    help = "Verifica proteção dos admins, Redis e confiança no proxy sem expor credenciais."

    def handle(self, *args, **options):
        errors = []
        for site in (tenant_admin_site, super_admin_site):
            if not issubclass(site.login_form, ProtectedAdminAuthenticationForm):
                errors.append(f"Login sem proteção: {site.name}")
        if 'redis' not in settings.CACHES['default']['BACKEND'].lower():
            errors.append('O limite administrativo precisa de Redis compartilhado entre processos.')
        networks = getattr(settings, 'OTP_TRUSTED_PROXY_CIDRS', [])
        if not getattr(settings, 'OTP_TRUST_PROXY_HEADERS', False) or not networks:
            errors.append('Configure OTP_TRUST_PROXY_HEADERS=true e OTP_TRUSTED_PROXY_CIDRS com o proxy real.')
        for cidr in networks:
            try:
                if ipaddress.ip_network(cidr).prefixlen == 0:
                    errors.append('Não confie em toda a internet como proxy.')
            except ValueError:
                errors.append('Há um CIDR de proxy inválido.')
        key = 'security:check:' + get_random_string(24)
        try:
            if not cache.add(key, 1, timeout=30) or cache.incr(key) != 2:
                errors.append('O cache não confirmou incremento do contador.')
        except Exception:
            errors.append('Cache de segurança indisponível.')
        finally:
            try:
                cache.delete(key)
            except Exception:
                pass
        if errors:
            raise CommandError('\n'.join(errors))
        self.stdout.write(self.style.SUCCESS('Admins protegidos; cache e configuração de proxy verificados. Confira também o IP registrado no evento de login.'))
