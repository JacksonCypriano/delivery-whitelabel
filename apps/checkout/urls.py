# apps/checkout/urls.py

from django.urls import path
from . import views

app_name = 'checkout'

urlpatterns = [
    path('add/', views.add_to_cart, name='add_to_cart'),
    path('cart/', views.cart_view, name='cart'),
    path('remove/<int:product_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('update_quantity/<int:product_id>/', views.update_cart_quantity, name='update_quantity'),
    path('checkout/', views.checkout_step_one, name='checkout_step_one'),
    path('success/', views.order_success, name='order_success'),
]