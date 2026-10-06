"""Explicit React surface for the platform SuperAdmin."""

from django.apps import apps
from django.http import Http404

from apps.tenants.admin_site import super_admin_site

# key -> (model label, title, group)
# Keep this explicit: registering a model in Django Admin must not silently expose it in the API.
RESOURCES = {
    "tenants-tenant": ("tenants.tenant", "Lojas", "tenants"),
    "accounts-user": ("accounts.user", "Usuários", "accounts"),
    "accounts-securityevent": ("accounts.securityevent", "Eventos de segurança", "accounts"),
    "billing-subscription": ("billing.subscription", "Assinaturas", "billing"),
    "billing-invoice": ("billing.invoice", "Cobranças", "billing"),
    "billing-credit": ("billing.credit", "Créditos", "billing"),
    "billing-plan": ("billing.plan", "Planos", "billing"),
    "billing-additionalservice": ("billing.additionalservice", "Serviços adicionais", "billing"),
    "billing-tenantpaymentaccount": ("billing.tenantpaymentaccount", "Contas de pagamento", "billing"),
    "billing-billingsettings": ("billing.billingsettings", "Configurações de cobrança", "billing"),
    "billing-asaasfeesnapshot": ("billing.asaasfeesnapshot", "Tarifas Asaas", "billing"),
    "billing-billingevent": ("billing.billingevent", "Eventos de cobrança", "billing"),
    "billing-billingaudit": ("billing.billingaudit", "Auditoria de cobrança", "billing"),
    "billing-fiscalinvoice": ("billing.fiscalinvoice", "Notas fiscais", "fiscal"),
    "billing-fiscalsettings": ("billing.fiscalsettings", "Configurações fiscais", "fiscal"),
    "billing-fiscalcustomerrule": ("billing.fiscalcustomerrule", "Regras fiscais por cliente", "fiscal"),
    "billing-taxrate": ("billing.taxrate", "Alíquotas", "fiscal"),
    "billing-taxratewhatsappreminder": ("billing.taxratewhatsappreminder", "Lembretes de alíquota", "fiscal"),
    "billing-municipalexport": ("billing.municipalexport", "Exportações municipais", "fiscal"),
    "integrations-whatsappintegrationstate": ("integrations.whatsappintegrationstate", "Estado das integrações WhatsApp", "integrations"),
    "integrations-whatsappintegrationevent": ("integrations.whatsappintegrationevent", "Eventos de integração WhatsApp", "integrations"),
    "integrations-whatsappalert": ("integrations.whatsappalert", "Alertas WhatsApp", "integrations"),
    "integrations-tenantwhatsappagent": ("integrations.tenantwhatsappagent", "Agentes WhatsApp", "integrations"),
    "integrations-tenantwhatsappagentevent": ("integrations.tenantwhatsappagentevent", "Eventos do agente", "integrations"),
    "integrations-tenantwhatsappconversation": ("integrations.tenantwhatsappconversation", "Conversas WhatsApp", "integrations"),
    "integrations-whatsappcheckout": ("integrations.whatsappcheckout", "Checkouts WhatsApp", "integrations"),
    "integrations-whatsappordernotice": ("integrations.whatsappordernotice", "Avisos de pedido WhatsApp", "integrations"),
    "marketplace-marketplacecategory": ("marketplace.marketplacecategory", "Categorias do marketplace", "marketplace"),
    "marketplace-marketinglead": ("marketplace.marketinglead", "Leads", "marketing"),
    "marketplace-marketingmilestone": ("marketplace.marketingmilestone", "Marcos de marketing", "marketing"),
    "marketplace-marketingpaidconversion": ("marketplace.marketingpaidconversion", "Conversões pagas", "marketing"),
    "prospecting-prospectingbatch": ("prospecting.prospectingbatch", "Lotes de prospecção", "prospecting"),
}


def resource_admin(key):
    if key not in RESOURCES:
        raise Http404
    model = apps.get_model(RESOURCES[key][0])
    try:
        return super_admin_site._registry[model]
    except KeyError as exc:
        raise Http404 from exc
