from django.urls import path
from .views import DashboardLoginView, DashboardLogoutView, DashboardRefreshView

urlpatterns = [
    path('login/', DashboardLoginView.as_view(), name='dashboard-login'),
    path('logout/', DashboardLogoutView.as_view(), name='dashboard-logout'),
    path('refresh/', DashboardRefreshView.as_view(), name='dashboard-refresh'),
]
