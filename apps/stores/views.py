from django.views.generic import ListView
from django.db.models import Prefetch
from apps.stores.models import Category, Product

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
        tenant = getattr(self.request, 'tenant', None)
        context['tenant'] = tenant

        if tenant:
            categories = Category.objects.filter(tenant=tenant).prefetch_related(
                Prefetch(
                    'products',
                    queryset=Product.objects.filter(tenant=tenant, is_available=True),
                    to_attr='prefetched_products'
                )
            )
        else:
            categories = Category.objects.none()

        context['categories'] = categories
        return context