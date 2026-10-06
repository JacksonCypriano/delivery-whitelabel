from django.urls import path
from .api import (
    Session,
    Password,
    Dashboard,
    ResourceList,
    ResourceDetail,
    ResourceAction,
    History,
)
from .integrations import Finance, Whatsapp
from .api import ListEdit

urlpatterns = [
    path("session/", Session.as_view()),
    path("password/", Password.as_view()),
    path("dashboard/", Dashboard.as_view()),
    path("resources/<slug:resource>/", ResourceList.as_view()),
    path("resources/<slug:resource>/new/", ResourceDetail.as_view()),
    path("resources/<slug:resource>/list-edit/", ListEdit.as_view()),
    path("resources/<slug:resource>/actions/", ResourceAction.as_view()),
    path("resources/<slug:resource>/<int:pk>/history/", History.as_view()),
    path("resources/<slug:resource>/<int:pk>/", ResourceDetail.as_view()),
    path("finance/", Finance.as_view()),
    path("finance/purchase/", Finance.as_view(), {"action": "purchase"}),
    path("finance/notes/", Finance.as_view(), {"action": "notes"}),
    path("finance/fees/", Finance.as_view(), {"action": "fees"}),
    path(
        "finance/invoices/<uuid:invoice_id>/", Finance.as_view(), {"action": "invoice"}
    ),
    path(
        "finance/invoices/<uuid:invoice_id>/refresh/",
        Finance.as_view(),
        {"action": "refresh"},
    ),
    path(
        "finance/invoices/<uuid:invoice_id>/notes/<str:kind>/",
        Finance.as_view(),
        {"action": "download"},
    ),
    path("whatsapp/", Whatsapp.as_view()),
]
