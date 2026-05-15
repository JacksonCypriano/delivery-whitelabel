from django.urls import path
from .views import CatalogoView, DashboardHomeView, dashboard_login_page

app_name = 'stores'

urlpatterns = [
    path('', CatalogoView.as_view(), name='catalogo'),
    path('dashboard/login/', dashboard_login_page, name='dashboard-login'),
    path('dashboard/', DashboardHomeView.as_view(), name='dashboard-home'),
]
