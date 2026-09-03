"""Execute pelo instalar.sh: carga transacional, sem alterações no código do app."""
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

from apps.tenants.models import Tenant, BrandConfig, BusinessHour, DeliveryZone
from apps.tenants.onboarding import get_store_setup
from apps.marketplace.models import MarketplaceCategory, MarketplaceProfile
from apps.stores.models import Category, Product, HalfProduct, CustomizationGroupLabel, CustomizationGroup, CustomizationOption
from apps.coupons.models import CouponCampaign

ASSETS = Path(__file__).resolve().parent / 'assets'
USER = 'admin_vitrine_demo'
NAME = 'Vitrine Demo - sem vendas reais'
MARKER = 'VDD-VITRINE-001'
# Fotos ilustrativas compartilhadas entre variações da mesma categoria.
CATALOG = [
 ('Lanches', 'burger.jpg', [
  ('Burger Clássico', '24.90', 'Pão macio, hambúrguer bovino, queijo, alface, tomate e molho da casa.'),
  ('Burger Cheddar', '29.90', 'Hambúrguer bovino com cheddar cremoso, salada e molho da casa.'),
  ('Burger Duplo', '36.90', 'Dois hambúrgueres, queijo e salada no pão macio. Escolha seus adicionais.'),
  ('Burger da Vitrine', '32.90', 'Hambúrguer especial com queijo, cebola e molho da casa. Um exemplo de destaque do catálogo.')]),
 ('Pizzas', 'pizza.jpg', [
  ('Pizza Margherita', '45.90', 'Pizza grande de 8 fatias com molho de tomate, muçarela, manjericão e azeite.'),
  ('Pizza Calabresa', '49.90', 'Pizza grande de 8 fatias com calabresa, cebola, muçarela e orégano.'),
  ('Pizza Quatro Queijos', '59.90', 'Pizza grande de 8 fatias com muçarela, provolone, parmesão e requeijão.'),
  ('Pizza Especial da Casa', '64.90', 'Pizza grande de 8 fatias com muçarela, tomate, cogumelos e manjericão.')]),
 ('Marmitas', 'meal.jpg', [
  ('Marmita Bowl Colorido', '27.90', 'Bowl com folhas, legumes variados e proteína grelhada. Escolha o acompanhamento.'),
  ('Marmita Bowl Vegetariano', '26.90', 'Bowl com folhas, legumes, grãos e tofu grelhado.'),
  ('Marmita Salmão com Legumes', '39.90', 'Salmão grelhado com legumes e acompanhamento de grãos. Porção individual.'),
  ('Marmita Salmão Especial', '46.90', 'Salmão grelhado com legumes e porção generosa de acompanhamento.')]),
 ('Porções', 'fries.jpg', [
  ('Batata Frita Individual', '14.90', 'Batatas douradas e crocantes. Porção individual de aproximadamente 200 g.'),
  ('Batata Frita para Compartilhar', '24.90', 'Porção de aproximadamente 400 g de batatas fritas para compartilhar.'),
  ('Batata com Cheddar', '29.90', 'Porção de batatas fritas acompanhada de cheddar cremoso.'),
  ('Batata Especial da Casa', '34.90', 'Porção de batatas com cheddar e adicionais escolhidos por você.')]),
 ('Sobremesas', 'cake.jpg', [
  ('Bolo de Chocolate - Fatia', '13.90', 'Fatia de bolo de chocolate com cobertura cremosa.'),
  ('Bolo de Chocolate - Dupla', '24.90', 'Duas fatias de bolo de chocolate para dividir.'),
  ('Bolo de Chocolate com Calda', '17.90', 'Fatia de bolo de chocolate acompanhada de calda extra.'),
  ('Bolo de Chocolate - Inteiro', '89.90', 'Bolo de chocolate inteiro, com cobertura cremosa. Exemplo para encomendas pelo catálogo.')]),
 ('Bebidas', 'drink.jpg', [
  ('Refresco de Morango - 300 ml', '9.90', 'Bebida sem álcool com morango, limão, hortelã e gelo.'),
  ('Refresco de Morango - 500 ml', '13.90', 'Bebida sem álcool com morango, limão, hortelã e gelo, em copo maior.'),
  ('Café Espresso', '6.90', 'Café espresso preparado na hora. Porção de 60 ml.'),
  ('Cappuccino Cremoso', '12.90', 'Café com leite vaporizado e espuma cremosa. Porção de 180 ml.')]),
]
BRAND = dict(
 primary_color='#BD441D', secondary_color='#173B32', accent_color='#F2BB58',
 background_color='#FBF8F1', card_background_color='#FFFFFF', text_color='#173B32',
 muted_text_color='#53675D', border_color='#DEDCD2', button_text_color='#FFFFFF',
 success_color='#237A4B', warning_color='#B86B08', danger_color='#C73737',
 font_family='Inter', base_font_size=16, border_radius=22, button_radius=16,
 card_shadow=True, hover_effect=True, header_style='gradient', show_search_bar=True,
 show_category_icons=True, show_product_description=True, show_product_image=True,
 compact_product_cards=False, dark_mode_enabled=True, dark_mode_primary='#C44823',
 dark_mode_background='#0F1F1A', dark_mode_card_background='#1A3028',
 dark_mode_text='#FFF9EB', dark_mode_muted_text='#B9C8BD', dark_mode_border_color='#365044',
)


def summary(tenant):
    scheme = getattr(settings, 'TENANT_PUBLIC_SCHEME', 'https')
    domain = getattr(settings, 'TENANT_BASE_DOMAIN', 'vemdedelivery.com.br')
    url = f'{scheme}://{tenant.slug}.{domain}'
    print(f'Loja: {tenant.name} | id={tenant.pk}')
    print(f'Catálogo: {url}/')
    print(f'Admin: {url}/admin/')
    print(f'Usuário privado: {USER}')
    print('Defina a senha pelo comando changepassword. Não compartilhe este admin com os visitantes.')
    print(f'Produtos: {Product.objects.filter(tenant=tenant).count()} | Configuração: {get_store_setup(tenant)["percent"]}%')


def main():
    phone = re.sub(r'\D', '', os.environ.get('DEMO_PHONE', '11983491206'))
    if len(phone) in (10, 11): phone = '55' + phone
    from apps.tenants.utils import validate_whatsapp_number
    validate_whatsapp_number(phone)
    reuse = os.environ.get('DEMO_REUSE_SLUG', '').strip()
    slug = reuse or 'vitrine-demo'
    existing = Tenant.objects.filter(slug=slug).first()
    if existing and Product.objects.filter(tenant=existing, sku=MARKER).exists():
        print('Esta carga já foi aplicada. Nenhum cadastro, senha ou imagem foi sobrescrito.')
        summary(existing)
        return
    if existing and not reuse:
        raise CommandError('O slug vitrine-demo já existe. Nada alterado. Use outra loja ou indique DEMO_REUSE_SLUG para uma loja de demonstração.')
    if reuse:
        if not existing or not any(s in existing.name.lower() for s in ('demo', 'vitrine', 'demonstra')):
            raise CommandError('Reutilização exige uma loja existente identificada no nome como demo, demonstração ou vitrine.')
        if existing.whatsapp_number != phone:
            raise CommandError('O telefone informado difere do telefone da loja a reutilizar. Nada alterado.')
    owner = Tenant.objects.filter(whatsapp_number=phone).exclude(pk=existing.pk if existing else None).first()
    if owner:
        raise CommandError(f'O telefone já pertence à loja "{owner.name}" (slug: {owner.slug}). Nada alterado. Se ela for sua demonstração, use DEMO_REUSE_SLUG={owner.slug}; consulte o guia.')
    User = get_user_model()
    admin = User.objects.filter(username=USER).first()
    if admin:
        raise CommandError(f'O usuário {USER} já existe. Nada alterado; não será reaproveitado automaticamente.')
    # Valida todos os arquivos antes de gravar no banco ou no armazenamento.
    for file in ASSETS.iterdir():
        if file.suffix.lower() in ('.jpg', '.png'):
            with Image.open(file) as image: image.verify()
    for name in ['logo.png', 'banner.png', 'favicon.png', 'burger.jpg', 'pizza.jpg', 'meal.jpg', 'meal2.jpg', 'fries.jpg', 'cake.jpg', 'drink.jpg', 'coffee.jpg']:
        if not (ASSETS/name).is_file(): raise CommandError(f'Arquivo obrigatório ausente: {name}')
    created_files = []
    try:
        with transaction.atomic():
            if existing:
                tenant = Tenant.objects.select_for_update().get(pk=existing.pk)
            else:
                tenant = Tenant(slug=slug, whatsapp_number=phone)
            tenant.name = NAME
            tenant.is_active = True
            tenant.sale_mode = 'whatsapp'
            tenant.fulfillment_mode = 'delivery_and_pickup'
            tenant.pickup_address = 'Ambiente virtual de demonstração - não há retirada física'
            tenant.pickup_number = 'S/N'
            tenant.pickup_complement = 'Pedidos fictícios. Não efetue pagamentos.'
            tenant.pickup_city = 'Itapevi'
            tenant.pickup_neighborhood = 'Centro'
            tenant.pickup_zip_code = '00000-000'
            tenant.full_clean(); tenant.save()
            prefix = f'demo-vitrine/{tenant.pk}/{uuid.uuid4().hex}'
            files = {}
            for file in sorted(ASSETS.iterdir()):
                if file.suffix.lower() not in ('.jpg', '.png'): continue
                name = default_storage.save(f'{prefix}/{file.name}', ContentFile(file.read_bytes()))
                created_files.append(name); files[file.name] = name
            brand, _ = BrandConfig.objects.get_or_create(tenant=tenant)
            for key,value in BRAND.items(): setattr(brand,key,value)
            brand.logo=files['logo.png']; brand.banner=files['banner.png']; brand.favicon=files['favicon.png']
            brand.full_clean(); brand.save()
            # Substitui somente os horários da loja explicitamente selecionada para demonstração.
            tenant.business_hours.all().delete()
            # Dois períodos sobrepostos garantem demonstração disponível também à meia-noite.
            for day in range(7):
                BusinessHour.objects.create(tenant=tenant,weekday=day,is_closed=False,opening_time=time(0),closing_time=time(12))
                BusinessHour.objects.create(tenant=tenant,weekday=day,is_closed=False,opening_time=time(11),closing_time=time(0))
            for neighborhood,fee in [('Centro','4.90'),('Jardim Rainha','6.90'),('Vila Dr. Cardoso','7.90'),('Jardim Vitápolis','8.90'),('Amador Bueno','12.90')]:
                DeliveryZone.objects.update_or_create(tenant=tenant,city='Itapevi',neighborhood=neighborhood,defaults={'fee':Decimal(fee),'is_active':True})
            categories={}; index=0
            for cat_name,photo,rows in CATALOG:
                category = Category.objects.filter(tenant=tenant,name=cat_name).first()
                if not category: category=Category.objects.create(tenant=tenant,name=cat_name)
                categories[cat_name]=category
                for j,(name,price,desc) in enumerate(rows):
                    index+=1
                    image=photo
                    if cat_name=='Marmitas' and j>=2:image='meal2.jpg'
                    if cat_name=='Bebidas' and j>=2:image='coffee.jpg'
                    p=Product(tenant=tenant,category=category,sku=f'VDD-VITRINE-{index:03d}',name=name,price=Decimal(price),
                        description=desc+' Demonstração sem venda real. Foto ilustrativa; variações podem compartilhar a mesma imagem.',
                        primary_image=files[image],is_available=True,is_featured=(j==0),stock=None,
                        min_order_qty=1,max_order_qty=20,available_days=list(range(7)),prep_time=25)
                    if cat_name=='Lanches' and j==0:p.sale_price=Decimal('22.90')
                    p.save()
                    if cat_name=='Pizzas':HalfProduct.objects.update_or_create(product=p,defaults={'tenant':tenant,'is_active':True})
            groups = [
                ('Lanches','Ponto do hambúrguer','whole',1,1,[('Ao ponto','0'),('Bem passado','0')]),
                ('Lanches','Adicionais do lanche','whole',0,3,[('Queijo extra','3'),('Bacon','5'),('Hambúrguer extra','8')]),
                ('Pizzas','Borda da pizza','whole',1,1,[('Tradicional','0'),('Requeijão','8'),('Cheddar','8')]),
                ('Pizzas','Adicionais de cada metade','half',0,2,[('Muçarela extra','4'),('Tomate','2'),('Azeitonas','2')]),
                ('Marmitas','Acompanhamento','whole',1,1,[('Arroz branco','0'),('Arroz integral','2'),('Legumes extras','3')]),
                ('Porções','Molhos','whole',0,2,[('Maionese da casa','2'),('Barbecue','2'),('Cheddar extra','4')]),
                ('Sobremesas','Complementos','whole',0,2,[('Calda de chocolate','3'),('Creme extra','3')]),
            ]
            for cat,label_name,apply_to,minimum,maximum,options in groups:
                label,_=CustomizationGroupLabel.objects.get_or_create(tenant=tenant,name=label_name)
                group=CustomizationGroup.objects.create(tenant=tenant,category=categories[cat],label=label,apply_to=apply_to,min_options=minimum,max_options=maximum,is_active=True)
                for name,price in options:CustomizationOption.objects.create(tenant=tenant,group=group,name=name,price=Decimal(price),is_available=True)
            CouponCampaign.objects.create(tenant=tenant,name='Demonstração: 10% de desconto',code='VITRINE10',discount_type='percentage',discount_value=10,
                minimum_order_value=20,starts_at=timezone.now()-timedelta(days=1),usage_limit=None,usage_limit_per_customer=1000)
            profile,_=MarketplaceProfile.objects.get_or_create(tenant=tenant)
            profile.is_listed=False;profile.is_featured=False
            profile.short_description='Loja de demonstração. Explore o catálogo e monte um pedido de teste. Sem vendas, entregas ou retiradas reais.'
            profile.city='Itapevi';profile.state='SP';profile.neighborhood='Centro'
            profile.search_keywords='demo, demonstração, vitrine, pizzas, lanches, bebidas, marmitas, sobremesas'
            profile.save()
            for name,icon in [('Restaurantes','🍽️'),('Pizzarias','🍕'),('Lanchonetes','🍔')]:
                branch,_=MarketplaceCategory.objects.get_or_create(name=name,defaults={'icon':icon,'is_active':True})
                profile.categories.add(branch)
            user=User(username=USER,tenant=tenant,is_staff=True,is_tenant_admin=True,is_superuser=False,is_active=True)
            user.set_unusable_password();user.save()
            readiness=get_store_setup(tenant)
            if not readiness['complete']:raise CommandError('Configuração incompleta: '+str([s['key'] for s in readiness['steps'] if not s['complete']]))
            profile.is_listed=True;profile.save()
    except Exception:
        for name in created_files:
            try: default_storage.delete(name)
            except Exception: pass
        raise
    print('Demonstração criada. Nenhuma mensagem de WhatsApp ou e-mail foi enviada.')
    summary(tenant)

if __name__=='__main__':main()
