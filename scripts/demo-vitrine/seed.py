"""Sincroniza a Vitrine Demo 2.0 sem apagar pedidos, clientes ou histórico."""

import os
import re
import uuid
from datetime import time, timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import CommandError
from django.db import transaction
from django.utils import timezone
from PIL import Image

from apps.coupons.models import CouponCampaign
from apps.marketplace.models import MarketplaceCategory, MarketplaceProfile
from apps.stores.models import (
    Category,
    CustomizationGroup,
    CustomizationGroupLabel,
    CustomizationOption,
    HalfProduct,
    Product,
)
from apps.tenants.models import BrandConfig, BusinessHour, DeliveryZone, Tenant
from apps.tenants.onboarding import get_store_setup


ASSETS = Path(__file__).resolve().parent / "assets"
USER = "admin_vitrine_demo"
NAME = "Bella Massa — Sabores & Delivery"
LEGACY_SKU_PREFIX = "VDD-VITRINE-"
SKU_PREFIX = "VDD-DEMO2-"

BRAND = dict(
    primary_color="#A82832",
    secondary_color="#19382F",
    accent_color="#E5A83B",
    background_color="#FAF5EA",
    card_background_color="#FFFFFF",
    text_color="#20201E",
    muted_text_color="#6C675F",
    border_color="#E8DED0",
    button_text_color="#FFFFFF",
    success_color="#237A4B",
    warning_color="#B86B08",
    danger_color="#C73737",
    font_family="Inter",
    base_font_size=16,
    border_radius=22,
    button_radius=16,
    card_shadow=True,
    hover_effect=True,
    header_style="gradient",
    show_search_bar=True,
    show_category_icons=True,
    show_product_description=True,
    show_product_image=True,
    compact_product_cards=False,
    dark_mode_enabled=True,
    dark_mode_primary="#D9525B",
    dark_mode_background="#171513",
    dark_mode_card_background="#25211D",
    dark_mode_text="#FFF9EF",
    dark_mode_muted_text="#C9BFB3",
    dark_mode_border_color="#433C35",
)

# Arquivos específicos são opcionais nesta primeira etapa. Enquanto não existirem,
# cada produto usa a foto de fallback da categoria. Quando os novos assets forem
# adicionados à pasta e o instalador for executado novamente, o seed os adotará.
CATALOG = [
    {
        "category": "Pizzas",
        "order": 10,
        "fallback": "pizza.jpg",
        "products": [
            dict(name="Pizza Margherita", price="49.90", description="Molho de tomate, muçarela, tomate fresco, manjericão e azeite.", image="pizza_margherita.jpg", calories=980, weight="850", prep_time=30),
            dict(name="Pizza Calabresa Especial", price="54.90", description="Calabresa fatiada, muçarela, cebola roxa e orégano.", image="pizza_calabresa.jpg", calories=1180, weight="900", prep_time=30),
            dict(name="Pizza Frango com Catupiry", price="59.90", description="Frango temperado, muçarela, catupiry e orégano.", image="pizza_frango_catupiry.jpg", calories=1240, weight="920", prep_time=30),
            dict(name="Pizza Portuguesa", price="61.90", description="Presunto, muçarela, ovos, cebola, azeitonas e orégano.", image="pizza_portuguesa.jpg", calories=1270, weight="930", prep_time=30),
            dict(name="Pizza Quatro Queijos", price="63.90", description="Muçarela, provolone, parmesão e catupiry em uma combinação cremosa.", image="pizza_quatro_queijos.jpg", calories=1320, weight="900", prep_time=30),
            dict(name="Pizza Bella Massa", price="67.90", sale_price="62.90", description="Muçarela, pepperoni, tomate-cereja, cebola roxa e toque levemente picante da casa.", image="pizza_bella_massa.jpg", calories=1290, weight="930", prep_time=32, is_featured=True, is_spicy=True),
        ],
    },
    {
        "category": "Lanches",
        "order": 20,
        "fallback": "burger.jpg",
        "products": [
            dict(name="Smash Clássico", price="26.90", sale_price="23.90", description="Pão brioche, smash bovino, queijo, alface, tomate e molho da casa.", image="smash_classico.jpg", calories=690, weight="280", prep_time=20),
            dict(name="Bacon Supreme", price="34.90", description="Pão brioche, hambúrguer bovino, cheddar cremoso, bacon crocante e molho especial.", image="bacon_supreme.jpg", calories=890, weight="340", prep_time=22, is_featured=True),
            dict(name="Duplo Cheddar", price="38.90", description="Dois hambúrgueres, cheddar cremoso, cebola caramelizada e molho da casa.", image="duplo_cheddar.jpg", calories=1020, weight="390", prep_time=24),
            dict(name="Smash Salada", price="29.90", description="Hambúrguer bovino, queijo, alface, tomate, cebola roxa e maionese da casa.", image="smash_salada.jpg", calories=720, weight="310", prep_time=20),
        ],
    },
    {
        "category": "Pratos & Marmitas",
        "order": 30,
        "fallback": "meal.jpg",
        "products": [
            dict(name="Executiva de Frango", price="29.90", description="Filé de frango grelhado com acompanhamento escolhido por você.", image="executiva_frango.jpg", calories=610, weight="520", prep_time=25),
            dict(name="Executiva de Carne", price="34.90", description="Bife acebolado com acompanhamento escolhido por você.", image="executiva_carne.jpg", calories=690, weight="540", prep_time=25),
            dict(name="Parmegiana da Casa", price="39.90", description="Filé empanado, molho artesanal e queijo gratinado, com acompanhamento.", image="parmegiana.jpg", calories=890, weight="620", prep_time=30, is_featured=True),
            dict(name="Bowl Vegetariano", price="28.90", description="Arroz integral, legumes, grãos, folhas e proteína vegetal grelhada.", image="bowl_vegetariano.jpg", calories=520, weight="480", prep_time=20, is_vegan=True),
        ],
    },
    {
        "category": "Porções",
        "order": 40,
        "fallback": "fries.jpg",
        "products": [
            dict(name="Fritas Tradicionais", price="19.90", description="Batatas douradas e crocantes, ideais para compartilhar.", image="fritas_tradicionais.jpg", calories=690, weight="400", prep_time=15),
            dict(name="Fritas Cheddar & Bacon", price="31.90", description="Batatas crocantes cobertas com cheddar cremoso e bacon.", image="fritas_cheddar_bacon.jpg", calories=980, weight="520", prep_time=18, is_featured=True),
            dict(name="Onion Rings", price="24.90", description="Anéis de cebola empanados e crocantes.", image="onion_rings.jpg", calories=620, weight="350", prep_time=15),
            dict(name="Iscas de Frango", price="32.90", description="Iscas de frango empanadas e crocantes, servidas em porção generosa.", image="iscas_frango.jpg", calories=760, weight="450", prep_time=20),
        ],
    },
    {
        "category": "Combos",
        "order": 50,
        "fallback": "burger.jpg",
        "products": [
            dict(name="Combo Individual", price="39.90", description="Smash Clássico, fritas individuais e uma bebida à sua escolha.", image="combo_individual.jpg", prep_time=25),
            dict(name="Combo Casal", price="74.90", description="Dois Smash Clássicos, fritas para compartilhar e duas bebidas.", image="combo_casal.jpg", prep_time=30),
            dict(name="Combo Pizza", price="69.90", description="Uma pizza grande selecionada para demonstração e refrigerante de 1,5 L.", image="combo_pizza.jpg", prep_time=35),
            dict(name="Combo Família", price="109.90", sale_price="99.90", description="Duas pizzas grandes, porção de fritas e refrigerante de 1,5 L.", image="combo_familia.jpg", prep_time=40, is_featured=True),
        ],
    },
    {
        "category": "Sobremesas",
        "order": 60,
        "fallback": "cake.jpg",
        "products": [
            dict(name="Brownie de Chocolate", price="14.90", description="Brownie macio por dentro, com cobertura de chocolate.", image="brownie.jpg", calories=410, weight="120", prep_time=10),
            dict(name="Petit Gateau", price="19.90", description="Bolinho quente de chocolate com centro cremoso.", image="petit_gateau.jpg", calories=530, weight="180", prep_time=15, is_featured=True),
            dict(name="Bolo de Chocolate", price="13.90", description="Fatia generosa de bolo de chocolate com cobertura cremosa.", image="bolo_chocolate.jpg", calories=460, weight="160", prep_time=5),
            dict(name="Pudim Cremoso", price="11.90", description="Pudim tradicional com calda de caramelo.", image="pudim.jpg", calories=330, weight="150", prep_time=5),
        ],
    },
    {
        "category": "Bebidas",
        "order": 70,
        "fallback": "drink.jpg",
        "products": [
            dict(name="Coca-Cola 350 ml", price="7.90", description="Lata 350 ml, servida gelada.", image="coca_cola.jpg", weight="350", prep_time=2),
            dict(name="Coca-Cola Zero 350 ml", price="7.90", description="Lata 350 ml, sem açúcar, servida gelada.", image="coca_zero.jpg", weight="350", prep_time=2),
            dict(name="Guaraná 350 ml", price="7.50", description="Lata 350 ml, servida gelada.", image="guarana.jpg", weight="350", prep_time=2),
            dict(name="Água Mineral 500 ml", price="5.00", description="Água mineral sem gás, garrafa de 500 ml.", image="agua.jpg", weight="500", prep_time=2),
            dict(name="Suco Natural 500 ml", price="12.90", description="Suco natural preparado na hora. Consulte os sabores disponíveis.", image="suco_natural.jpg", weight="500", prep_time=8),
        ],
    },
]

GROUPS = [
    ("Pizzas", "Borda da pizza", "whole", 1, 1, [("Tradicional", "0"), ("Catupiry", "8"), ("Cheddar", "8")]),
    ("Pizzas", "Adicionais de cada metade", "half", 0, 3, [("Muçarela extra", "4"), ("Bacon", "5"), ("Tomate", "2"), ("Azeitonas", "2")]),
    ("Lanches", "Ponto do hambúrguer", "whole", 1, 1, [("Ao ponto", "0"), ("Bem passado", "0")]),
    ("Lanches", "Adicionais do lanche", "whole", 0, 4, [("Queijo extra", "3"), ("Bacon", "5"), ("Hambúrguer extra", "8"), ("Ovo", "2"), ("Catupiry", "4")]),
    ("Pratos & Marmitas", "Escolha o acompanhamento", "whole", 1, 1, [("Arroz branco", "0"), ("Arroz integral", "2"), ("Legumes", "0"), ("Fritas", "4")]),
    ("Porções", "Molhos", "whole", 0, 3, [("Maionese da casa", "2"), ("Barbecue", "2"), ("Cheddar", "4"), ("Catupiry", "4")]),
    ("Combos", "Escolha sua bebida", "whole", 1, 1, [("Coca-Cola", "0"), ("Coca-Cola Zero", "0"), ("Guaraná", "0")]),
    ("Sobremesas", "Complementos", "whole", 0, 2, [("Calda de chocolate", "3"), ("Creme extra", "3"), ("Sorvete", "5")]),
]


def summary(tenant):
    scheme = getattr(settings, "TENANT_PUBLIC_SCHEME", "https")
    domain = getattr(settings, "TENANT_BASE_DOMAIN", "vemdedelivery.com.br")
    url = f"{scheme}://{tenant.slug}.{domain}"
    active = Product.objects.filter(tenant=tenant, is_available=True).count()
    legacy = Product.objects.filter(tenant=tenant, sku__startswith=LEGACY_SKU_PREFIX).count()
    print(f"Loja: {tenant.name} | id={tenant.pk}")
    print(f"Catálogo: {url}/")
    print(f"Admin: {url}/admin/")
    print(f"Usuário privado: {USER}")
    print("Defina a senha pelo comando changepassword. Não compartilhe este admin com os visitantes.")
    print(f"Produtos ativos: {active} | Legado preservado: {legacy} | Configuração: {get_store_setup(tenant)['percent']}%")


def validate_assets():
    required = {
        "logo.png",
        "banner.png",
        "favicon.png",
        "burger.jpg",
        "pizza.jpg",
        "meal.jpg",
        "fries.jpg",
        "cake.jpg",
        "drink.jpg",
    }
    missing = sorted(name for name in required if not (ASSETS / name).is_file())
    if missing:
        raise CommandError("Arquivos obrigatórios ausentes: " + ", ".join(missing))

    for file in ASSETS.iterdir():
        if file.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            with Image.open(file) as image:
                image.verify()


def upload_assets(tenant, created_files):
    prefix = f"demo-vitrine/{tenant.pk}/v2/{uuid.uuid4().hex}"
    files = {}
    for file in sorted(ASSETS.iterdir()):
        if file.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
            continue
        stored = default_storage.save(f"{prefix}/{file.name}", ContentFile(file.read_bytes()))
        created_files.append(stored)
        files[file.name] = stored
    return files


def sync_group(tenant, category, label_name, apply_to, minimum, maximum, options):
    label, _ = CustomizationGroupLabel.objects.get_or_create(tenant=tenant, name=label_name)
    group = (
        CustomizationGroup.objects
        .filter(tenant=tenant, category=category, label=label, apply_to=apply_to)
        .order_by("pk")
        .first()
    )
    if group is None:
        group = CustomizationGroup(tenant=tenant, category=category, label=label, apply_to=apply_to)
    group.min_options = minimum
    group.max_options = maximum
    group.is_active = True
    group.save()

    active_names = []
    for option_name, option_price in options:
        active_names.append(option_name)
        option = CustomizationOption.objects.filter(tenant=tenant, group=group, name=option_name).first()
        if option is None:
            option = CustomizationOption(tenant=tenant, group=group, name=option_name)
        option.price = Decimal(option_price)
        option.is_available = True
        option.save()
    group.options.exclude(name__in=active_names).update(is_available=False)
    return group


def main():
    phone = re.sub(r"\D", "", os.environ.get("DEMO_PHONE", "11983491206"))
    if len(phone) in (10, 11):
        phone = "55" + phone
    from apps.tenants.utils import validate_whatsapp_number
    validate_whatsapp_number(phone)

    reuse = os.environ.get("DEMO_REUSE_SLUG", "").strip()
    slug = reuse or "vitrine-demo"
    existing = Tenant.objects.filter(slug=slug).first()

    if existing and not reuse:
        raise CommandError(
            "O slug vitrine-demo já existe. Para sincronizar a demonstração existente, "
            "use DEMO_REUSE_SLUG=vitrine-demo."
        )

    if reuse:
        if not existing:
            raise CommandError("A loja informada em DEMO_REUSE_SLUG não existe.")
        is_known_demo = (
            existing.slug == "vitrine-demo"
            or Product.objects.filter(tenant=existing, sku__startswith=LEGACY_SKU_PREFIX).exists()
            or Product.objects.filter(tenant=existing, sku__startswith=SKU_PREFIX).exists()
        )
        if not is_known_demo:
            raise CommandError("Reutilização recusada: a loja não foi identificada como Vitrine Demo.")
        if existing.whatsapp_number != phone:
            raise CommandError("O telefone informado difere do telefone da loja a reutilizar. Nada alterado.")

    owner = Tenant.objects.filter(whatsapp_number=phone).exclude(pk=existing.pk if existing else None).first()
    if owner:
        raise CommandError(
            f'O telefone já pertence à loja "{owner.name}" (slug: {owner.slug}). Nada alterado.'
        )

    validate_assets()
    created_files = []

    try:
        with transaction.atomic():
            if existing:
                tenant = Tenant.objects.select_for_update().get(pk=existing.pk)
            else:
                tenant = Tenant(slug=slug, whatsapp_number=phone)

            tenant.name = NAME
            tenant.is_active = True
            tenant.sale_mode = "whatsapp"
            tenant.fulfillment_mode = "delivery_and_pickup"
            tenant.pickup_address = "Rua da Demonstração"
            tenant.pickup_number = "199"
            tenant.pickup_complement = "Loja demonstrativa — pedidos e pagamentos não são processados"
            tenant.pickup_city = "Itapevi"
            tenant.pickup_neighborhood = "Centro"
            tenant.pickup_zip_code = "00000-000"
            tenant.full_clean()
            tenant.save()

            files = upload_assets(tenant, created_files)

            brand, _ = BrandConfig.objects.get_or_create(tenant=tenant)
            for key, value in BRAND.items():
                setattr(brand, key, value)
            brand.logo = files["logo.png"]
            brand.banner = files["banner.png"]
            brand.favicon = files["favicon.png"]
            brand.full_clean()
            brand.save()

            # A Vitrine fica navegável em qualquer horário, inclusive atravessando meia-noite.
            tenant.business_hours.all().delete()
            for day in range(7):
                BusinessHour.objects.create(
                    tenant=tenant, weekday=day, is_closed=False,
                    opening_time=time(0), closing_time=time(12),
                )
                BusinessHour.objects.create(
                    tenant=tenant, weekday=day, is_closed=False,
                    opening_time=time(11), closing_time=time(0),
                )

            for neighborhood, fee in [
                ("Centro", "4.90"),
                ("Jardim Rainha", "6.90"),
                ("Vila Dr. Cardoso", "7.90"),
                ("Jardim Vitápolis", "8.90"),
                ("Amador Bueno", "12.90"),
            ]:
                DeliveryZone.objects.update_or_create(
                    tenant=tenant,
                    city="Itapevi",
                    neighborhood=neighborhood,
                    defaults={"fee": Decimal(fee), "is_active": True},
                )

            # Preserva produtos históricos; apenas deixa a V1 fora do catálogo.
            Product.objects.filter(
                tenant=tenant, sku__startswith=LEGACY_SKU_PREFIX
            ).update(is_available=False, is_featured=False)

            # O seed controla os grupos desta loja demo, mas não os apaga.
            CustomizationGroup.objects.filter(tenant=tenant).update(is_active=False)
            HalfProduct.objects.filter(tenant=tenant).update(is_active=False)

            categories = {}
            active_skus = []
            index = 0
            for block in CATALOG:
                category = Category.objects.filter(tenant=tenant, name=block["category"]).first()
                if category is None:
                    category = Category(tenant=tenant, name=block["category"])
                category.display_order = block["order"]
                category.save()
                categories[block["category"]] = category

                for row in block["products"]:
                    index += 1
                    sku = f"{SKU_PREFIX}{index:03d}"
                    active_skus.append(sku)
                    product = Product.objects.filter(tenant=tenant, sku=sku).first()
                    if product is None:
                        product = Product(tenant=tenant, sku=sku)

                    image_name = row.get("image")
                    image_key = image_name if image_name in files else block["fallback"]
                    product.category = category
                    product.name = row["name"]
                    product.description = row["description"]
                    product.price = Decimal(row["price"])
                    product.sale_price = Decimal(row["sale_price"]) if row.get("sale_price") is not None else None
                    product.primary_image = files[image_key]
                    product.is_available = True
                    product.is_featured = bool(row.get("is_featured", False))
                    product.is_vegan = bool(row.get("is_vegan", False))
                    product.is_spicy = bool(row.get("is_spicy", False))
                    product.allergens = row.get("allergens", "")
                    product.calories = row.get("calories")
                    product.prep_time = row.get("prep_time", 25)
                    product.weight = Decimal(row["weight"]) if row.get("weight") is not None else None
                    product.stock = None
                    product.min_order_qty = 1
                    product.max_order_qty = 20
                    product.available_days = list(range(7))
                    product.save()

                    if block["category"] == "Pizzas":
                        half, _ = HalfProduct.objects.get_or_create(
                            tenant=tenant,
                            product=product,
                        )
                        half.is_active = True
                        half.save(update_fields=["is_active"])

            Product.objects.filter(
                tenant=tenant, sku__startswith=SKU_PREFIX
            ).exclude(sku__in=active_skus).update(is_available=False, is_featured=False)

            for cat, label_name, apply_to, minimum, maximum, options in GROUPS:
                sync_group(
                    tenant,
                    categories[cat],
                    label_name,
                    apply_to,
                    minimum,
                    maximum,
                    options,
                )

            CouponCampaign.objects.update_or_create(
                tenant=tenant,
                code="VITRINE10",
                defaults={
                    "name": "Demonstração: 10% de desconto",
                    "discount_type": "percentage",
                    "discount_value": 10,
                    "minimum_order_value": 20,
                    "starts_at": timezone.now() - timedelta(days=1),
                    "usage_limit": None,
                    "usage_limit_per_customer": 1000,
                    "ends_at": None,
                    "is_active": True,
                },
            )

            profile, _ = MarketplaceProfile.objects.get_or_create(tenant=tenant)
            profile.is_listed = False
            profile.is_featured = False
            profile.short_description = (
                "Loja demonstrativa da VemDeDelivery: pizzas, lanches, pratos, porções, "
                "combos, sobremesas e bebidas em um único cardápio."
            )
            profile.city = "Itapevi"
            profile.state = "SP"
            profile.neighborhood = "Centro"
            profile.search_keywords = (
                "demo, demonstração, delivery, pizzas, lanches, pratos, marmitas, porções, "
                "combos, sobremesas, bebidas"
            )
            profile.save()

            profile.categories.clear()
            for name, icon in [
                ("Restaurantes", "🍽️"),
                ("Pizzarias", "🍕"),
                ("Lanchonetes", "🍔"),
            ]:
                branch, _ = MarketplaceCategory.objects.get_or_create(
                    name=name,
                    defaults={"icon": icon, "is_active": True},
                )
                profile.categories.add(branch)

            User = get_user_model()
            admin = User.objects.filter(username=USER).first()
            if admin is None:
                admin = User(
                    username=USER,
                    tenant=tenant,
                    is_staff=True,
                    is_tenant_admin=True,
                    is_superuser=False,
                    is_active=True,
                )
                admin.set_unusable_password()
                admin.save()
            elif admin.tenant_id != tenant.pk:
                raise CommandError(f"O usuário {USER} já pertence a outra loja. Nada alterado.")
            else:
                changed = False
                for attr, value in (
                    ("is_staff", True),
                    ("is_tenant_admin", True),
                    ("is_active", True),
                ):
                    if getattr(admin, attr) != value:
                        setattr(admin, attr, value)
                        changed = True
                if changed:
                    admin.save(update_fields=["is_staff", "is_tenant_admin", "is_active"])

            readiness = get_store_setup(tenant)
            if not readiness["complete"]:
                missing = [s["key"] for s in readiness["steps"] if not s["complete"]]
                raise CommandError("Configuração incompleta: " + str(missing))

            profile.is_listed = True
            profile.save(update_fields=["is_listed", "updated_at"])

    except Exception:
        for name in created_files:
            try:
                default_storage.delete(name)
            except Exception:
                pass
        raise

    print("Vitrine Demo 2.0 sincronizada. Nenhum pedido, cliente ou histórico foi apagado.")
    print("Nenhuma mensagem de WhatsApp ou e-mail foi enviada.")
    summary(tenant)


if __name__ == "__main__":
    main()
