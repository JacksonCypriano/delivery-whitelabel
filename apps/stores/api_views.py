from django.http import JsonResponse
from django.views import View
from django.shortcuts import get_object_or_404

from .models import CustomizationGroup, Product


class ProductCustomizationsAPIView(View):
    def get(self, request, product_id):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return JsonResponse({'groups': []})

        product = get_object_or_404(Product, id=product_id, tenant=tenant, is_available=True)

        groups = (
            CustomizationGroup.objects
            .filter(category=product.category, tenant=tenant, is_active=True)
            .order_by('id')
            .prefetch_related('options__group')
            .select_related('label')
        )

        data = []
        for group in groups:
            options = []
            for opt in group.options.filter(tenant=tenant, is_available=True).order_by('id'):  # <-- order_by aqui
                options.append({
                    'id':          opt.id,
                    'name':        opt.name,
                    'description': opt.description or '',
                    'price':       str(opt.price),
                    'image':       opt.image.url if opt.image else '',
                })

            data.append({
                'id':          group.id,
                'name':        group.label.name if group.label else '',
                'min_options': group.min_options,
                'max_options': group.max_options,
                'apply_to':    group.apply_to,
                'options':     options,
            })

        return JsonResponse({'groups': data})
