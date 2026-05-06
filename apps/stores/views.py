from django.views.generic import ListView
from django.db.models import Prefetch
from apps.stores.models import Category, Product, HalfProduct


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
            products_qs = Product.objects.filter(tenant=tenant, is_available=True).order_by('name')

            categories = (
                Category.objects
                .filter(products__tenant=tenant)
                .distinct()
                .order_by('name')
                .prefetch_related(
                    Prefetch('products', queryset=products_qs, to_attr='prefetched_products')
                )
            )
        else:
            categories = Category.objects.none()

        context['categories'] = categories

        pizza_cat = None
        if tenant:
            pizza_cat = categories.filter(name__iexact='Pizzas').first()

        if tenant:
            if pizza_cat:
                half_qs = HalfProduct.objects.filter(
                    product__tenant=tenant,
                    product__category=pizza_cat,
                    is_active=True
                ).select_related('product')
            else:
                half_qs = HalfProduct.objects.filter(
                    product__tenant=tenant,
                    is_active=True
                ).select_related('product')
        else:
            half_qs = HalfProduct.objects.none()

        context['half_products'] = half_qs

        return context
