"""Host-aware entry point for the React administrative panel."""

from django.http import Http404

from apps.merchant.views import shell as merchant_shell
from apps.superpanel.views import shell as superadmin_shell
from apps.tenants.domains import is_platform_host


def panel_shell(request, path=""):
    """
    Serve the same React application in two strictly separated scopes:

    * slug.dominio/painel/ -> merchant panel for that tenant
    * dominio/painel/      -> global platform administration
    """
    if getattr(request, "tenant", None) is not None:
        return merchant_shell(request, path=path)

    if is_platform_host(request):
        return superadmin_shell(request, path=path)

    raise Http404("Painel não disponível neste domínio.")
