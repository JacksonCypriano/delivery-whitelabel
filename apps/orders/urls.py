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
        "pedido/<uuid:public_token>/pagar/",
        views.start_payment,
        name="start_payment",
    ),
    path(
        "pedido/<uuid:public_token>/pagamento/",
        views.payment_status,
        name="payment_status",
    ),
    path(
        "pedido/<uuid:public_token>/pagamento/atualizar/",
        views.refresh_payment,
        name="refresh_payment",
    ),
    path(
        "pedido/<uuid:public_token>/pagamento/retorno/",
        views.payment_return,
        name="payment_return",
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
