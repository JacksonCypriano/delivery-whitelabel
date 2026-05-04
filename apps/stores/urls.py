from django.urls import path
from .views import CatalogoView

app_name = 'stores'

urlpatterns = [
    path('', CatalogoView.as_view(), name='catalogo'),
]