from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from apps.checkout.views import delivery_fee_api
from apps.core import health as health_views
from apps.marketplace import views as marketplace_views
from apps.tenants.admin_site import super_admin_site, tenant_admin_site


from apps.billing.views import webhook as billing_webhook

urlpatterns = [
    path("integracoes/asaas/webhook/", billing_webhook, name="billing_webhook"),
    # Health checks (sem dados sensíveis)
    path("health/live/", health_views.live, name="health_live"),
    path("health/ready/", health_views.ready, name="health_ready"),

    # Marketplace / catálogo
    path("", include("apps.marketplace.urls")),
    path("", include("apps.stores.urls")),

    # Autenticação / conta
    path("dashboard/auth/", include("apps.accounts.urls")),
    path("conta/", include("apps.accounts.customer_urls", namespace="customer_accounts")),

    # Admin
    path("superadmin/", super_admin_site.urls),
    path("admin/", tenant_admin_site.urls),

    # Checkout
    path("checkout/", include("apps.checkout.urls", namespace="checkout")),

    # Pedidos
    path("", include("apps.orders.urls")),

    # Localização global de entrega
    path("localizacao-entrega/", marketplace_views.set_delivery_address, name="marketplace_set_delivery_address"),
    path("localizacao-entrega/remover/", marketplace_views.clear_delivery_address, name="marketplace_clear_delivery_address"),

    # Favoritos
    path("favoritos/loja/<int:tenant_id>/", marketplace_views.toggle_favorite_store, name="marketplace_toggle_favorite_store"),

    # APIs
    path("api/", include("apps.stores.urls_api")),
    path("api/tenants/", include("apps.tenants.urls")),
    path("api/delivery-fee/", delivery_fee_api, name="delivery_fee_api"),
    path("api/cupons/", include("apps.coupons.urls", namespace="coupons")),
    path("api/cep/<str:cep>/", marketplace_views.cep_lookup_api, name="marketplace_cep_lookup"),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)