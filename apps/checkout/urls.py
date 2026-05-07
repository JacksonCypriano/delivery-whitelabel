from django.urls import path
from . import views

app_name = 'checkout'

urlpatterns = [
    path('add/', views.add_to_cart, name='add_to_cart'),
    path('cart/', views.cart_view, name='cart'),
    path('remove/<int:cart_item_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('update_quantity/<int:cart_item_id>/', views.update_cart_quantity, name='update_quantity'),
    path('checkout/', views.checkout_step_one, name='checkout_step_one'),
    path('success/', views.order_success, name='order_success'),
    path('checkout/add-half-half/', views.add_half_half, name='add_half_half'),
    path('update_notes/<int:cart_item_id>/', views.update_cart_item_notes, name='update_cart_item_notes'),
]
