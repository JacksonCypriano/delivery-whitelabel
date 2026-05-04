from django.views.generic import ListView
from apps.stores.models import Product
from django.shortcuts import get_object_or_404

class CatalogoView(ListView):
    model = Product
    template_name = 'stores/catalogo.html'
    context_object_name = 'produtos'

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if tenant:
            return Product.objects.filter(tenant=tenant, is_available=True)
        return Product.objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tenant'] = getattr(self.request, 'tenant', None)

        return context
