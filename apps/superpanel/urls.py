from django.urls import path

from .api import Dashboard, History, ListEdit, Password, ResourceAction, ResourceDetail, ResourceList, Session

from .operations import ManualCredit, FiscalDownload, Prospecting, Evolution, UserPassword

from .api import Selection, Relationships, Activity

from .free_days import FreeDays

urlpatterns = [
    path("tenants/<int:pk>/free-days/", FreeDays.as_view()),
    path("activity/", Activity.as_view()),
    path("resources/<slug:resource>/selection/", Selection.as_view()),
    path("resources/<slug:resource>/<str:pk>/relationships/", Relationships.as_view()),
    path("users/<int:pk>/password/", UserPassword.as_view()),
    path("prospecting/", Prospecting.as_view()),
    path("evolution/", Evolution.as_view()),
    path("subscriptions/<int:pk>/credit/", ManualCredit.as_view()),
    path("resources/<slug:resource>/<int:pk>/download/<str:kind>/", FiscalDownload.as_view()),
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
