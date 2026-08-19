from django.urls import path

from apps.frontend.views import product_customizations

from .api_views import ProductCustomizationsAPIView
from .views import CatalogoView, DashboardHomeView, dashboard_login_page


app_name = 'stores'

urlpatterns = [
    path('', CatalogoView.as_view(), name='catalogo'),
    path('api/product/<int:product_id>/customizations/', product_customizations, name='product_customizations'),
    path('dashboard/login/', dashboard_login_page, name='dashboard-login'),
    path('dashboard/', DashboardHomeView.as_view(), name='dashboard-home'),
    path('api/product/<int:product_id>/customizations/', ProductCustomizationsAPIView.as_view(), name='product-customizations'),
]
