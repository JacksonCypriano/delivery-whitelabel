from django.urls import path

from . import views, legal_views

app_name = "marketplace"

urlpatterns = [
    path("privacidade/", legal_views.privacy, name="privacy"),
    path("termos/", legal_views.terms, name="terms"),
    path("", views.home, name="home"),
]
