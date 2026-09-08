from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.billing.models import AdditionalService, BillingSettings, Plan
from apps.marketplace.models import MarketplaceCategory


PLANS = (
    (1, "Mensal", Decimal("199.00"), Decimal("0.00")),
    (3, "Trimestral", Decimal("199.00"), Decimal("5.00")),
    (6, "Semestral", Decimal("199.00"), Decimal("10.00")),
    (12, "Anual", Decimal("199.00"), Decimal("15.00")),
)

SERVICES = (
    (
        "cadastro-ate-30-produtos",
        "Cadastro inicial — até 30 produtos",
        "Cadastro inicial de até 30 produtos.",
        Decimal("249.00"),
    ),
    (
        "cadastro-ate-60-produtos",
        "Cadastro inicial — até 60 produtos",
        "Cadastro inicial de até 60 produtos.",
        Decimal("399.00"),
    ),
    (
        "lote-10-produtos-extras",
        "Produtos extras — lote de até 10",
        "Inclusão de até 10 produtos extras.",
        Decimal("69.00"),
    ),
    (
        "atualizacao-20-alteracoes",
        "Atualização — até 20 alterações simples",
        "Atualização de até 20 alterações simples.",
        Decimal("59.00"),
    ),
)

MARKETPLACE_CATEGORIES = (
    (0, "Pizzaria", "🍕", "pizzaria"),
    (1, "Hamburgueria", "🍔", "hamburgueria"),
    (2, "Restaurante", "🍽️", "restaurante"),
    (3, "Marmitaria", "🍱", "marmitaria"),
    (4, "Comida japonesa", "🍣", "comida-japonesa"),
    (5, "Padaria", "🥖", "padaria"),
    (6, "Confeitaria", "🍰", "confeitaria"),
    (7, "Açaí e sorvetes", "🍨", "acai-e-sorvetes"),
    (8, "Adega", "🍷", "adega"),
    (9, "Bebidas", "🥤", "bebidas"),
    (10, "Lanches", "🍔", "lanches"),
    (11, "Mercado", "🛒", "mercado"),
    (12, "Hortifruti", "🥬", "hortifruti"),
    (13, "Açougue", "🥩", "acougue"),
    (14, "Pet shop", "🐾", "pet-shop"),
    (15, "Flores e presentes", "💐", "flores-e-presentes"),
    (16, "Conveniência", "🏪", "conveniencia"),
)

LEGACY_CATEGORIES = {
    "Pizzarias": "Pizzaria",
    "Restaurantes": "Restaurante",
    "Lanchonetes": "Lanches",
}


class Command(BaseCommand):
    help = "Popula/normaliza planos, serviços, categorias e meios de cobrança comerciais."

    @transaction.atomic
    def handle(self, *args, **options):
        policy = BillingSettings.current()
        policy.grace_days = 3
        policy.pix_enabled = True
        policy.boleto_enabled = False
        policy.card_enabled = False
        policy.save(update_fields=["grace_days", "pix_enabled", "boleto_enabled", "card_enabled"])

        for months, name, monthly_price, discount in PLANS:
            Plan.objects.update_or_create(
                months=months,
                defaults={
                    "name": name,
                    "monthly_price": monthly_price,
                    "discount": discount,
                    "active": True,
                },
            )

        for code, name, description, price in SERVICES:
            AdditionalService.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "description": description,
                    "price": price,
                    "active": True,
                },
            )

        official = {}
        for order, name, icon, slug in MARKETPLACE_CATEGORIES:
            category, _ = MarketplaceCategory.objects.update_or_create(
                name=name,
                defaults={
                    "slug": slug,
                    "icon": icon,
                    "order": order,
                    "is_active": True,
                },
            )
            official[name] = category

        # Normaliza somente duplicidades já conhecidas da homologação. Os
        # registros são desativados (não apagados) e vínculos existentes são
        # transferidos para a categoria canônica.
        for legacy_name, canonical_name in LEGACY_CATEGORIES.items():
            legacy = MarketplaceCategory.objects.filter(name=legacy_name).first()
            canonical = official.get(canonical_name)
            if not legacy or not canonical or legacy.pk == canonical.pk:
                continue
            for profile in legacy.stores.all().iterator():
                profile.categories.add(canonical)
                profile.categories.remove(legacy)
            legacy.is_active = False
            legacy.order = 999
            legacy.save(update_fields=["is_active", "order"])

        self.stdout.write(self.style.SUCCESS("Dados comerciais atualizados com sucesso."))
        self.stdout.write("Planos: Mensal, Trimestral, Semestral e Anual.")
        self.stdout.write("Serviços adicionais: 4 ativos.")
        self.stdout.write(f"Categorias oficiais: {len(MARKETPLACE_CATEGORIES)}.")
        self.stdout.write("Cobrança: Pix ativo; boleto e cartão desativados.")
        self.stdout.write("As tarifas do Asaas não foram sobrescritas: são consultadas pela API.")
