from django.urls import NoReverseMatch, reverse


def _admin_url(name, *args):
    try:
        return reverse(f"tenant_admin:{name}", args=args)
    except NoReverseMatch:
        return ""


def _has_value(value):
    return bool(str(value or "").strip())


def get_store_setup(tenant, marketplace_data=None):
    if not tenant:
        return {"complete": False, "percent": 0, "completed": 0, "total": 0, "steps": []}

    from apps.marketplace.models import MarketplaceProfile
    from apps.stores.models import Category, Product
    from apps.tenants.models import BrandConfig, BusinessHour, DeliveryZone

    profile = MarketplaceProfile.objects.filter(tenant=tenant).first()
    brand = BrandConfig.objects.filter(tenant=tenant).first()

    store_ok = all((_has_value(tenant.name), _has_value(tenant.whatsapp_number), _has_value(tenant.fulfillment_mode)))

    pickup_ok = True
    if tenant.accepts_pickup:
        pickup_ok = all((
            _has_value(tenant.pickup_address),
            _has_value(tenant.pickup_number),
            _has_value(tenant.pickup_neighborhood),
            _has_value(tenant.pickup_city),
            _has_value(tenant.pickup_zip_code),
        ))

    if marketplace_data is None:
        marketplace_ok = bool(
            profile
            and _has_value(profile.short_description)
            and profile.categories.exists()
        )
    else:
        categories = marketplace_data.get("categories")
        marketplace_ok = all((
            _has_value(marketplace_data.get("short_description")),
            bool(categories),
        ))

    branding_ok = bool(brand and brand.logo)
    hours_ok = BusinessHour.objects.filter(
        tenant=tenant,
        is_closed=False,
        opening_time__isnull=False,
        closing_time__isnull=False,
    ).exists()

    delivery_ok = True
    if tenant.accepts_delivery:
        delivery_ok = DeliveryZone.objects.filter(tenant=tenant, is_active=True).exists()

    category_ok = Category.objects.filter(tenant=tenant).exists()
    product_ok = Product.objects.filter(tenant=tenant, is_available=True).exists()
    catalog_ok = category_ok and product_ok

    profile_url = ""
    if profile:
        profile_url = _admin_url("marketplace_marketplaceprofile_change", profile.pk)
    else:
        profile_url = _admin_url("marketplace_marketplaceprofile_add")

    brand_url = ""
    if brand:
        brand_url = _admin_url("tenants_brandconfig_change", brand.pk)
    else:
        brand_url = _admin_url("tenants_brandconfig_add")

    steps = [
        {
            "key": "store",
            "title": "Informações da loja",
            "description": "Nome, WhatsApp e modo de atendimento.",
            "complete": store_ok,
            "required": True,
            "url": _admin_url("tenants_tenant_change", tenant.pk),
        },
        {
            "key": "pickup",
            "title": "Endereço para retirada",
            "description": "Endereço completo usado quando o cliente escolhe retirar.",
            "complete": pickup_ok,
            "required": tenant.accepts_pickup,
            "url": _admin_url("tenants_tenant_change", tenant.pk),
        },
        {
            "key": "brand",
            "title": "Identidade visual",
            "description": "Configure a identidade da loja e envie pelo menos o logotipo.",
            "complete": branding_ok,
            "required": True,
            "url": brand_url,
        },
        {
            "key": "hours",
            "title": "Horários de funcionamento",
            "description": "Configure pelo menos um período em que a loja atende.",
            "complete": hours_ok,
            "required": True,
            "url": _admin_url("tenants_businesshour_changelist"),
        },
        {
            "key": "delivery",
            "title": "Locais e taxas de entrega",
            "description": "Cadastre pelo menos uma região ativa com sua taxa de entrega.",
            "complete": delivery_ok,
            "required": tenant.accepts_delivery,
            "url": _admin_url("tenants_deliveryzone_changelist"),
        },
        {
            "key": "catalog",
            "title": "Cardápio",
            "description": "Crie uma categoria e deixe pelo menos um produto disponível.",
            "complete": catalog_ok,
            "required": True,
            "url": _admin_url("stores_product_changelist"),
        },
        {
            "key": "marketplace",
            "title": "Perfil público da loja",
            "description": "Finalize a descrição e as categorias públicas da loja e publique quando o checklist estiver concluído.",
            "complete": marketplace_ok,
            "required": True,
            "url": profile_url,
        },
    ]

    required_steps = [step for step in steps if step.get("required", True)]
    completed = sum(1 for step in required_steps if step["complete"])
    total = len(required_steps)
    complete = total > 0 and completed == total
    percent = round((completed / total) * 100) if total else 0

    return {
        "complete": complete,
        "percent": percent,
        "completed": completed,
        "total": total,
        "steps": steps,
        "profile": profile,
    }


def enforce_store_listing(tenant_id):
    from apps.marketplace.models import MarketplaceProfile
    from apps.tenants.models import Tenant

    tenant = Tenant.objects.filter(pk=tenant_id).first()
    if not tenant:
        return

    profile = MarketplaceProfile.objects.filter(tenant=tenant, is_listed=True).first()
    if not profile:
        return

    if not get_store_setup(tenant)["complete"]:
        MarketplaceProfile.objects.filter(pk=profile.pk).update(is_listed=False)
