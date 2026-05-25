from django.urls import path
from .views import catalog, product_customizations

urlpatterns = [
    path('', catalog, name='catalog'),
    path('api/product/<int:product_id>/customizations/', product_customizations, name='product_customizations'),
]
