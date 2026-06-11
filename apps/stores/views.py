from django.db.models import Prefetch
from django.shortcuts import render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import ListView

from apps.accounts.decorators import dashboard_auth_required
from apps.stores.models import Category, HalfProduct, Product

from .models import Category, Product


class CatalogoView(ListView):
    model = Product
    template_name = 'stores/catalogo.html'
    context_object_name = 'produtos'

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return Product.objects.none()
        
        today = timezone.localdate().weekday()
        qs = Product.objects.filter(tenant=tenant, is_available=True)

        filtered = [
            p for p in qs
            if not p.available_days or today in p.available_days
        ]

        return filtered

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tenant = getattr(self.request, 'tenant', None)
        context['tenant'] = tenant

        if tenant:
            today = timezone.localdate().weekday()

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

            pizza_cat = categories.filter(name__iexact='Pizzas').first()

            for cat in categories:
                cat.prefetched_products = [
                    p for p in cat.prefetched_products
                    if not p.available_days or today in p.available_days
                ]

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
            categories = Category.objects.none()
            half_qs = HalfProduct.objects.none()

        context['categories'] = categories
        context['half_products'] = half_qs

        return context


class DashboardHomeView(View):
    @method_decorator(dashboard_auth_required)
    def get(self, request):
        total_produtos = Product.objects.filter(tenant=request.tenant).count()
        total_categorias = Category.objects.filter(tenant=request.tenant).count()
        
        context = {
            'stats': {
                'produtos': total_produtos,
                'categorias': total_categorias,
            }
        }
        return render(request, 'dashboard/home.html', context)

def dashboard_login_page(request):
    return render(request, 'dashboard/login.html')