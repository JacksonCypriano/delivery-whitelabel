"""Rate limits for the HTML admin forms, after CSRF validation."""
import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.cache import never_cache
from unfold.forms import AuthenticationForm

from apps.accounts.audit import record_event
from apps.core.rate_limit import rate_limit_exceeded, identifier_rate_limit_exceeded

logger = logging.getLogger(__name__)


class ProtectedAdminAuthenticationForm(AuthenticationForm):
    login_scope = "admin"

    def clean(self):
        tenant_id = getattr(getattr(self.request, "tenant", None), "pk", "root")
        scope = f"admin-login:{self.login_scope}:{tenant_id}"
        identifier = str(self.cleaned_data.get("username") or self.data.get("username", ""))[:254]
        window = getattr(settings, "ADMIN_LOGIN_WINDOW", 900)
        try:
            ip_blocked = rate_limit_exceeded(
                self.request, scope + ":ip", limit=getattr(settings, "ADMIN_LOGIN_IP_LIMIT", 50), window=window,
            )
            account_blocked = identifier_rate_limit_exceeded(
                scope + ":account", identifier,
                limit=getattr(settings, "ADMIN_LOGIN_ACCOUNT_LIMIT", 10), window=window,
            )
        except Exception:
            logger.error("Proteção de login administrativo indisponível.")
            self.request.admin_login_status = 503
            raise ValidationError("Login temporariamente indisponível. Tente novamente em alguns minutos.", code="security_unavailable") from None
        if ip_blocked or account_blocked:
            self.request.admin_login_status = 429
            record_event("rate_limited", request=self.request, scope="dashboard", reason="rate_limit", identifier=identifier)
            minutes = max(1, (window + 59) // 60)
            raise ValidationError(
                f"Muitas tentativas de acesso. Aguarde até {minutes} minutos e tente novamente.",
                code="rate_limited",
            )
        return super().clean()


class SuperAdminAuthenticationForm(ProtectedAdminAuthenticationForm):
    login_scope = "superadmin"

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_superuser:
            record_event("access_denied", request=self.request, user_id=user.pk, reason="not_allowed")
            raise ValidationError("Credenciais inválidas para este painel.", code="invalid_admin_login")


class ProtectedAdminSiteMixin:
    @method_decorator(csrf_protect)
    @method_decorator(never_cache)
    def login(self, request, extra_context=None):
        response = super().login(request, extra_context=extra_context)
        status = getattr(request, "admin_login_status", None)
        if status:
            response.status_code = status
            response["Retry-After"] = str(getattr(settings, "ADMIN_LOGIN_WINDOW", 900) if status == 429 else 60)
        return response
