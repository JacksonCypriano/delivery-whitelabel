import math
import re
from django.core.paginator import Paginator
from django.db.models import Q, Subquery
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.customers.models import Customer, CustomerAddress
from apps.stores.models import Product
from apps.tenants.delivery import resolve_delivery
from apps.tenants.models import DeliveryZone

from .cep import CepLookupError, CepNotFound, lookup_cep, normalize_cep
from .geocoding import reverse_geocode
from .location import (
    clear_global_delivery_location,
    get_global_delivery_location,
    serialize_customer_address,
    serialize_manual_address,
    set_global_delivery_location,
)
from .models import MarketplaceCategory, MarketplaceFavoriteStore, MarketplaceProfile
from .services import build_tenant_url, get_brand_logo_url


def _customer_default_location(request):
    if not request.user.is_authenticated:
        return "", ""

    try:
        customer = request.user.customer_profile
    except Exception:
        return "", ""

    address = (
        customer.addresses.filter(is_default=True).first()
        or customer.addresses.first()
    )

    if not address:
        return "", ""

    return (
        (address.city or "").strip(),
        (address.state or "").strip().upper(),
    )


def _available_cities():
    profile_cities = MarketplaceProfile.objects.filter(
        is_listed=True,
        tenant__is_active=True,
    ).exclude(city="").values_list("city", flat=True)

    delivery_cities = DeliveryZone.objects.filter(
        is_active=True,
        tenant__is_active=True,
        tenant__marketplace_profile__is_listed=True,
    ).exclude(city="").values_list("city", flat=True)

    cities = {
        city.strip()
        for city in list(profile_cities) + list(delivery_cities)
        if city and city.strip()
    }

    return sorted(cities, key=str.casefold)


def _matching_products(tenant, search, limit=3):
    if not search:
        return []

    return list(
        Product.objects
        .filter(tenant=tenant, is_available=True)
        .filter(
            Q(name__icontains=search)
            | Q(description__icontains=search)
            | Q(category__name__icontains=search)
        )
        .select_related("category")
        .order_by("-is_featured", "name")[:limit]
    )


def _parse_coordinate(value, minimum, maximum):
    if value in (None, ""):
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if number < minimum or number > maximum:
        return None

    return number


def _distance_km(lat1, lon1, lat2, lon2):
    earth_radius_km = 6371.0088

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1)
        * math.cos(phi2)
        * math.sin(delta_lambda / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius_km * c


def _delivery_preview(tenant):
    """
    GPS is used only for marketplace discovery.

    Delivery availability and fee must be validated later using an
    address explicitly selected/confirmed by the customer. Reverse
    geocoding is intentionally not used as a commercial delivery rule.
    """
    if not tenant.accepts_delivery:
        return {
            "status": "pickup_only",
            "available": False,
            "fee": None,
            "source": None,
        }

    return {
        "status": "address_required",
        "available": None,
        "fee": None,
        "source": "confirmed_address",
    }



def _marketplace_next(request):
    next_url = (request.POST.get("next") or "/").strip()

    if (
        not next_url.startswith("/")
        or next_url.startswith("//")
    ):
        return "/"

    return next_url


def _customer_addresses(request):
    if not request.user.is_authenticated:
        return CustomerAddress.objects.none()

    try:
        customer = request.user.customer_profile
    except Exception:
        return CustomerAddress.objects.none()

    return (
        customer.addresses
        .all()
        .order_by("-is_default", "-created_at")
    )


def _save_manual_address_for_customer(request, location):
    if not request.user.is_authenticated:
        return None

    customer = (
        Customer.objects
        .filter(user=request.user)
        .first()
    )

    if customer is None:
        return None

    label = (
        request.POST.get("label", "").strip()
        or "Endereço"
    )

    address = (
        customer.addresses
        .filter(
            zip_code=location["zip_code"],
            street__iexact=location["street"],
            number__iexact=location["number"],
        )
        .first()
    )

    fields = {
        "label": label,
        "zip_code": location["zip_code"],
        "street": location["street"],
        "number": location["number"],
        "complement": location["complement"],
        "neighborhood": location["neighborhood"],
        "city": location["city"],
        "state": location["state"],
        "reference": location["reference"],
    }

    if address is None:
        fields["is_default"] = not (
            customer.addresses
            .filter(is_default=True)
            .exists()
        )

        address = customer.addresses.create(
            **fields
        )
    else:
        for field, value in fields.items():
            setattr(address, field, value)

        address.save(
            update_fields=list(fields.keys())
        )

    return address


@require_GET
def cep_lookup_api(request, cep):
    normalized = normalize_cep(cep)

    if not re.fullmatch(r"\d{8}", normalized):
        return JsonResponse(
            {
                "success": False,
                "error": "CEP deve conter exatamente 8 dígitos.",
            },
            status=400,
        )

    try:
        data = lookup_cep(normalized)
    except CepNotFound:
        return JsonResponse(
            {
                "success": False,
                "error": "CEP não encontrado.",
            },
            status=404,
        )
    except CepLookupError:
        return JsonResponse(
            {
                "success": False,
                "error": "Não foi possível consultar o CEP agora.",
            },
            status=502,
        )

    return JsonResponse(
        {
            "success": True,
            **data,
        }
    )


@require_POST
def set_delivery_address(request):
    mode = request.POST.get("mode", "manual").strip()

    if mode == "saved":
        if not request.user.is_authenticated:
            messages.error(
                request,
                "Entre na sua conta para usar um endereço salvo.",
            )
            return redirect(_marketplace_next(request))

        address_id = request.POST.get("customer_address_id", "").strip()

        address = (
            _customer_addresses(request)
            .filter(pk=address_id)
            .first()
        )

        if address is None:
            messages.error(
                request,
                "O endereço selecionado não é válido.",
            )
            return redirect(_marketplace_next(request))

        location = serialize_customer_address(address)

    else:
        location = serialize_manual_address(
            request.POST
        )

        required_fields = {
            "zip_code": "CEP",
            "street": "rua",
            "number": "número",
            "neighborhood": "bairro",
            "city": "cidade",
            "state": "UF",
        }

        missing = [
            label
            for field, label in required_fields.items()
            if not location.get(field)
        ]

        if missing:
            messages.error(
                request,
                "Informe "
                + ", ".join(missing)
                + " para confirmar o endereço.",
            )
            return redirect(
                _marketplace_next(request)
            )

        normalized_cep = normalize_cep(
            location["zip_code"]
        )

        if not re.fullmatch(
            r"\d{8}",
            normalized_cep,
        ):
            messages.error(
                request,
                "Informe um CEP válido com 8 dígitos.",
            )
            return redirect(
                _marketplace_next(request)
            )

        location["zip_code"] = normalized_cep

        if (
            request.POST.get("save_address") == "1"
            and request.user.is_authenticated
        ):
            saved_address = (
                _save_manual_address_for_customer(
                    request,
                    location,
                )
            )

            if saved_address is not None:
                location = serialize_customer_address(
                    saved_address
                )

    set_global_delivery_location(
        request,
        location,
    )

    messages.success(
        request,
        "Endereço de entrega atualizado.",
    )

    return redirect(_marketplace_next(request))


@require_POST
def clear_delivery_address(request):
    clear_global_delivery_location(request)

    messages.success(
        request,
        "Endereço de entrega removido.",
    )

    return redirect(_marketplace_next(request))


@login_required
@require_POST
def toggle_favorite_store(request, tenant_id):
    customer = (
        Customer.objects
        .filter(user=request.user)
        .first()
    )

    next_url = _marketplace_next(request)

    if customer is None:
        messages.error(
            request,
            "Não foi possível localizar seu cadastro.",
        )
        return redirect(next_url)

    favorite = (
        MarketplaceFavoriteStore.objects
        .filter(
            customer=customer,
            tenant_id=tenant_id,
        )
        .first()
    )

    if favorite is not None:
        favorite.delete()
        messages.success(
            request,
            "Loja removida dos favoritos.",
        )
    else:
        MarketplaceFavoriteStore.objects.create(
            customer=customer,
            tenant_id=tenant_id,
        )
        messages.success(
            request,
            "Loja adicionada aos favoritos.",
        )

    return redirect(next_url)

def home(request):
    if getattr(request, "tenant", None):
        from django.urls import resolve

        match = resolve("/", urlconf="apps.stores.urls")
        return match.func(request, *match.args, **match.kwargs)

    search = request.GET.get("q", "").strip()
    city = request.GET.get("cidade", "").strip()
    state = request.GET.get("uf", "").strip().upper()
    category_slug = request.GET.get("categoria", "").strip()
    open_only = request.GET.get("abertas") == "1"
    favorites_only = request.GET.get("favoritas") == "1"
    global_delivery_location = get_global_delivery_location(request)
    customer_addresses = _customer_addresses(request)

    user_latitude = _parse_coordinate(
        request.GET.get("lat"),
        -90,
        90,
    )
    user_longitude = _parse_coordinate(
        request.GET.get("lng"),
        -180,
        180,
    )
    user_accuracy = _parse_coordinate(
        request.GET.get("accuracy"),
        0,
        100000,
    )

    location_active = (
        user_latitude is not None
        and user_longitude is not None
    )

    geocoded_location = None

    if location_active:
        geocoded_location = reverse_geocode(
            user_latitude,
            user_longitude,
        )

    if not location_active and not city:
        if global_delivery_location:
            city = (
                global_delivery_location.get("city", "")
                or ""
            ).strip()

            if not state:
                state = (
                    global_delivery_location.get("state", "")
                    or ""
                ).strip().upper()
        else:
            customer_city, customer_state = _customer_default_location(
                request
            )
            city = customer_city

            if not state:
                state = customer_state

    favorite_store_ids = set()

    if request.user.is_authenticated:
        customer = (
            Customer.objects
            .filter(user=request.user)
            .first()
        )

        if customer:
            favorite_store_ids = set(
                MarketplaceFavoriteStore.objects
                .filter(customer=customer)
                .values_list("tenant_id", flat=True)
            )

    profiles = (
        MarketplaceProfile.objects
        .filter(is_listed=True, tenant__is_active=True)
        .select_related("tenant", "tenant__brand_config")
        .prefetch_related("categories", "tenant__delivery_zones")
    )

    if city and not location_active:
        profiles = profiles.filter(
            Q(city__iexact=city)
            | Q(
                tenant__delivery_zones__city__iexact=city,
                tenant__delivery_zones__is_active=True,
            )
        )

    if state and not location_active:
        profiles = profiles.filter(
            Q(state__iexact=state)
            | Q(state="")
        )

    if favorites_only:
        if favorite_store_ids:
            profiles = profiles.filter(
                tenant_id__in=favorite_store_ids
            )
        else:
            profiles = profiles.none()

    if category_slug:
        profiles = profiles.filter(
            categories__slug=category_slug,
            categories__is_active=True,
        )

    if search:
        product_tenants = (
            Product.objects
            .filter(is_available=True)
            .filter(
                Q(name__icontains=search)
                | Q(description__icontains=search)
                | Q(category__name__icontains=search)
            )
            .values("tenant_id")
        )

        profiles = profiles.filter(
            Q(tenant__name__icontains=search)
            | Q(short_description__icontains=search)
            | Q(search_keywords__icontains=search)
            | Q(categories__name__icontains=search)
            | Q(tenant_id__in=Subquery(product_tenants))
        )

    profiles = profiles.distinct()
    stores = []

    for profile in profiles:
        tenant = profile.tenant
        is_open = tenant.is_open_now()

        if open_only and not is_open:
            continue

        distance_km = None

        if (
            location_active
            and profile.latitude is not None
            and profile.longitude is not None
        ):
            distance_km = _distance_km(
                user_latitude,
                user_longitude,
                float(profile.latitude),
                float(profile.longitude),
            )

        if global_delivery_location:
            delivery = resolve_delivery(
                tenant=tenant,
                delivery_type="delivery",
                city=global_delivery_location.get("city", ""),
                neighborhood=global_delivery_location.get(
                    "neighborhood",
                    "",
                ),
            )

            if not tenant.accepts_delivery:
                delivery["status"] = "pickup_only"
            elif delivery["available"]:
                delivery["status"] = "available"
            else:
                delivery["status"] = "unavailable"
        else:
            delivery = _delivery_preview(tenant)

        matched_products = _matching_products(
            tenant=tenant,
            search=search,
            limit=3,
        )

        stores.append({
            "profile": profile,
            "tenant": tenant,
            "is_open": is_open,
            "logo_url": get_brand_logo_url(tenant),
            "url": build_tenant_url(
                tenant,
                query={"q": search} if search else None,
            ),
            "matched_products": matched_products,
            "categories": list(
                profile.categories
                .filter(is_active=True)
                .order_by("order", "name")
            ),
            "distance_km": distance_km,
            "delivery": delivery,
            "is_favorite": tenant.id in favorite_store_ids,
        })

    if location_active:
        stores.sort(
            key=lambda item: (
                (
                    0
                    if item["delivery"].get("available") is True
                    else 1
                )
                if global_delivery_location
                else 0,
                item["distance_km"] is None,
                (
                    item["distance_km"]
                    if item["distance_km"] is not None
                    else float("inf")
                ),
                not item["is_open"],
                not item["profile"].is_featured,
                -item["profile"].priority,
                item["tenant"].name.casefold(),
            )
        )
    else:
        stores.sort(
            key=lambda item: (
                (
                    0
                    if item["delivery"].get("available") is True
                    else 1
                )
                if global_delivery_location
                else 0,
                not item["profile"].is_featured,
                not item["is_open"],
                -item["profile"].priority,
                item["tenant"].name.casefold(),
            )
        )

    paginator = Paginator(stores, 12)
    page_obj = paginator.get_page(request.GET.get("page"))

    categories = MarketplaceCategory.objects.filter(
        is_active=True,
    ).order_by("order", "name")

    context = {
        "page_obj": page_obj,
        "stores": page_obj.object_list,
        "categories": categories,
        "cities": _available_cities(),
        "search": search,
        "selected_city": city,
        "selected_state": state,
        "selected_category": category_slug,
        "open_only": open_only,
        "favorites_only": favorites_only,
        "favorite_count": len(favorite_store_ids),
        "result_count": paginator.count,
        "location_active": location_active,
        "user_latitude": user_latitude,
        "user_longitude": user_longitude,
        "user_accuracy": user_accuracy,
        "geocoded_location": geocoded_location,
        "global_delivery_location": global_delivery_location,
        "customer_addresses": customer_addresses,
    }

    return render(request, "marketplace/home.html", context)
