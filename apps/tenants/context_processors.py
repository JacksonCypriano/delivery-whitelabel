def tenant_brand(request):
    return {
        'tenant': getattr(request, 'tenant', None),
        'tenant_brand': getattr(request.tenant, 'brandconfig', None) if getattr(request, 'tenant', None) else None
    }
