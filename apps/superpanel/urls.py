from django.urls import path

from .api import Dashboard, History, ListEdit, Password, ResourceAction, ResourceDetail, ResourceList, Session

urlpatterns = [
    path("session/", Session.as_view()),
    path("password/", Password.as_view()),
    path("dashboard/", Dashboard.as_view()),
    path("resources/<slug:resource>/", ResourceList.as_view()),
    path("resources/<slug:resource>/new/", ResourceDetail.as_view()),
    path("resources/<slug:resource>/list-edit/", ListEdit.as_view()),
    path("resources/<slug:resource>/actions/", ResourceAction.as_view()),
    path("resources/<slug:resource>/<str:pk>/history/", History.as_view()),
    path("resources/<slug:resource>/<str:pk>/", ResourceDetail.as_view()),
]
