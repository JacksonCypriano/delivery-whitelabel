from django.urls import path
from .views import order_report, create_checkout_session

urlpatterns = [
    path('report/', order_report, name='order_report'),
    path('checkout/', create_checkout_session, name='checkout'),
]
