from django.urls import path

from .views import order_report

app_name = 'orders'

urlpatterns = [
    path('report/', order_report, name='order_report'),
]
