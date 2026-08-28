from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path(
        "pedido/<uuid:public_token>/whatsapp/",
        views.open_whatsapp,
        name="open_whatsapp",
    ),
    path(
        "pedido/<uuid:public_token>/editar/",
        views.edit_generated_order,
        name="edit_generated_order",
    ),
    path(
        "meus-pedidos/",
        views.order_history,
        name="history",
    ),
    path(
        "meus-pedidos/<uuid:public_token>/repetir/",
        views.repeat_order,
        name="repeat_order",
    ),
]
