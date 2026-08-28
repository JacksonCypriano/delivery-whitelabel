from django.urls import path

from .views import validate_coupon_api


app_name = "coupons"


urlpatterns = [
    path(
        "validar/",
        validate_coupon_api,
        name="validate",
    ),
]
