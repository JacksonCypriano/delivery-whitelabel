from django.urls import path

from .views import (
    customer_account,
    customer_address_create,
    customer_address_delete,
    customer_address_edit,
    customer_addresses,
    customer_address_set_default,
    customer_change_password,
    customer_login,
    customer_logout,
    customer_order_detail,
    customer_password_reset,
    customer_password_reset_complete,
    customer_password_reset_done,
    CustomerPasswordResetConfirmView,
    customer_orders,
    customer_profile,
    customer_register,
)


app_name = "customer_accounts"


urlpatterns = [
    path("", customer_account, name="account"),
    path("entrar/", customer_login, name="login"),
    path("recuperar-senha/", customer_password_reset, name="password-reset"),
    path("recuperar-senha/enviado/", customer_password_reset_done, name="password-reset-done"),
    path("redefinir-senha/<uidb64>/<token>/", CustomerPasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    path("redefinir-senha/concluido/", customer_password_reset_complete, name="password-reset-complete"),
    path("criar-conta/", customer_register, name="register"),
    path("sair/", customer_logout, name="logout"),
    path("enderecos/", customer_addresses, name="addresses"),
    path("enderecos/novo/", customer_address_create, name="address-create"),
    path("enderecos/<int:address_id>/editar/", customer_address_edit, name="address-edit"),
    path("enderecos/<int:address_id>/excluir/", customer_address_delete, name="address-delete"),
    path("enderecos/<int:address_id>/principal/", customer_address_set_default, name="address-default"),
    path("dados/", customer_profile, name="profile"),
    path("alterar-senha/", customer_change_password, name="change-password"),
    path("pedidos/", customer_orders, name="orders"),
    path("pedidos/<int:order_id>/", customer_order_detail, name="order-detail"),
]
