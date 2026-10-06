"""Explicit merchant surface. Never expose the platform admin registry."""

from apps.tenants.admin_site import tenant_admin_site

RESOURCES = {
    "store": ("tenants.tenant", "Minha loja", "settings"),
    "branding": ("tenants.brandconfig", "Identidade visual", "settings"),
    "hours": ("tenants.businesshour", "Horários", "settings"),
    "delivery": ("tenants.deliveryzone", "Áreas de entrega", "settings"),
    "profile": ("marketplace.marketplaceprofile", "Perfil público", "settings"),
    "products": ("stores.product", "Produtos", "catalog"),
    "categories": ("stores.category", "Categorias", "catalog"),
    "groups": ("stores.customizationgroup", "Adicionais e opções", "catalog"),
    "labels": ("stores.customizationgrouplabel", "Rótulos dos adicionais", "catalog"),
    "orders": ("orders.order", "Pedidos", "orders"),
    "customers": ("customers.customer", "Clientes", "customers"),
    "coupons": ("coupons.couponcampaign", "Cupons e campanhas", "marketing"),
    "redemptions": ("coupons.couponredemption", "Utilizações de cupons", "marketing"),
}


def resource_admin(key):
    from django.apps import apps
    from django.http import Http404

    if key not in RESOURCES:
        raise Http404
    return tenant_admin_site._registry[apps.get_model(RESOURCES[key][0])]
