from django.urls import path
from .api_views import ProductCustomizationsAPIView

urlpatterns = [
    path('product/<int:product_id>/customizations/', ProductCustomizationsAPIView.as_view(), name='product_customizations'),
]