from django.conf import settings
from django.urls import NoReverseMatch, reverse

from apps.tenants.admin_site import super_admin_site

from .base import CriticalTestCase


class SuperAdminSidebarRegistryCriticalTests(CriticalTestCase):
    """Impede models registrados no Superadmin de ficarem acessíveis só por URL."""

    def _sidebar_links(self):
        return {
            str(item["link"])
            for group in settings.UNFOLD_SUPER["SIDEBAR"]["navigation"]
            for item in group.get("items", [])
        }

    def test_every_registered_superadmin_model_has_sidebar_entry(self):
        sidebar_links = self._sidebar_links()
        missing = []

        for model in super_admin_site._registry:
            opts = model._meta
            try:
                changelist = reverse(
                    f"super_admin:{opts.app_label}_{opts.model_name}_changelist"
                )
            except NoReverseMatch:
                # Um model registrado sem changelist é um erro de configuração
                # tão importante quanto um item oculto.
                missing.append(f"{opts.label}: sem rota changelist")
                continue

            if changelist not in sidebar_links:
                missing.append(f"{opts.label}: {changelist}")

        self.assertEqual(
            missing,
            [],
            "Models registrados no Superadmin sem item no menu lateral: "
            + ", ".join(missing),
        )

    def test_fiscal_group_exposes_every_fiscal_admin_screen(self):
        navigation = settings.UNFOLD_SUPER["SIDEBAR"]["navigation"]
        fiscal = next(
            group for group in navigation if str(group["title"]) == "Fiscal / NFS-e"
        )

        self.assertTrue(fiscal["collapsible"])
        self.assertEqual(
            [str(item["title"]) for item in fiscal["items"]],
            [
                "Configurações de NFS-e",
                "Alíquotas mensais de ISS",
                "Lembretes WhatsApp de ISS",
                "Notas fiscais de assinaturas",
                "Regras fiscais de clientes",
                "Exportações fiscais",
            ],
        )
