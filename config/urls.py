from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.tenants.admin_site import tenant_admin_site

urlpatterns = [
    path('admin/', tenant_admin_site.urls),
    path('whatsapp/', include('apps.whatsapp.urls')),
    path('', include('apps.stores.urls')),
    path('api/tenants/', include('apps.tenants.urls')),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
