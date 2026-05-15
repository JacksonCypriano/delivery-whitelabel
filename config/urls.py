from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.tenants.admin_site import tenant_admin_site, super_admin_site

urlpatterns = [
    path('', include('apps.stores.urls')),
    path('dashboard/auth/', include('apps.accounts.urls')),
    path('superadmin/', super_admin_site.urls),
    path('admin/', tenant_admin_site.urls),
    path('checkout/', include('apps.checkout.urls', namespace='checkout')),
    path('webhooks/whatsapp/', include('apps.whatsapp.urls')),
    path('api/tenants/', include('apps.tenants.urls')),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
