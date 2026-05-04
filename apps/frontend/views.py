from django.shortcuts import render
from stores.models import Product

def catalog(request):
    tenant = getattr(request, 'tenant', None)
    products = Product.objects.filter(tenant=tenant)
    return render(request, 'catalog.html', {'products': products})
