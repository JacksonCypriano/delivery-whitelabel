from django.http import JsonResponse
from django.shortcuts import render

from apps.stores.models import CustomizationGroup, Product


def catalog(request):
    tenant = getattr(request, 'tenant', None)
    products = Product.objects.filter(tenant=tenant)
    return render(request, 'catalog.html', {'products': products})

def product_customizations(request, product_id):
    from apps.stores.models import Product
    try:
        product = Product.objects.select_related('category').get(
            id=product_id, tenant=request.tenant, is_available=True
        )
    except Product.DoesNotExist:
        return JsonResponse({'groups': []})

    groups = CustomizationGroup.objects.filter(
        category=product.category,
        tenant=request.tenant,
        is_active=True
    ).prefetch_related('options').order_by('order')

    data = []
    for group in groups:
        options = [
            {
                'id': opt.id,
                'name': opt.name,
                'description': opt.description,
                'price': str(opt.price),
                'image': opt.image.url if opt.image else '',
                'is_available': opt.is_available,
            }
            for opt in group.options.filter(is_available=True).order_by('order')
        ]
        data.append({
            'id': group.id,
            'name': group.name,
            'apply_to': group.apply_to,
            'min_options': group.min_options,
            'max_options': group.max_options,
            'options': options,
        })

    return JsonResponse({'groups': data})
