from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory

from apps.accounts.admin import CustomUserAdmin
from apps.customers.models import Customer
from apps.coupons.models import CouponCampaign, CouponAssignment
from apps.orders.models import Order, StockReservation
from apps.stores.models import Category, CustomizationGroup, CustomizationGroupLabel, CustomizationOption, Product
from apps.tenants.admin import TenantPaymentAccountForm
from apps.tenants.admin_site import tenant_admin_site, super_admin_site
from apps.tenants.models import Tenant, BrandConfig
from .base import CriticalTestCase


class FinalAdminTests(CriticalTestCase):
    def setUp(self):
        self.client.force_login(self.admin_a)
        self.host_a = self.host(self.tenant_a)
        self.request = RequestFactory().get('/admin/')
        self.request.tenant = self.tenant_a
        self.request.user = self.admin_a

    def test_category_cannot_be_transferred_or_created_in_another_store(self):
        for index, url in enumerate([f'/admin/stores/category/{self.category_a.pk}/change/', '/admin/stores/category/add/']):
            response = self.client.post(url, {'tenant': self.tenant_b.pk, 'name': 'Nova', 'slug': f'nova-{index}', '_save': 'Salvar'}, HTTP_HOST=self.host_a)
            self.assertEqual(response.status_code, 302)
        self.category_a.refresh_from_db()
        self.assertEqual(self.category_a.tenant_id, self.tenant_a.pk)
        self.assertFalse(Category.objects.filter(tenant=self.tenant_b, name='Nova').exists())

    def test_delivery_zone_cannot_be_transferred(self):
        response = self.client.post(f'/admin/tenants/deliveryzone/{self.zone_a.pk}/change/', {
            'tenant': self.tenant_b.pk, 'city': 'São Paulo', 'neighborhood': 'Outro bairro', 'fee': '0', 'is_active': 'on', '_save': 'Salvar',
        }, HTTP_HOST=self.host_a)
        self.assertEqual(response.status_code, 302)
        self.zone_a.refresh_from_db()
        self.assertEqual(self.zone_a.tenant_id, self.tenant_a.pk)

    def test_foreign_category_direct_edit_does_not_change_it(self):
        response = self.client.post(f'/admin/stores/category/{self.category_b.pk}/change/', {
            'tenant': self.tenant_a.pk, 'name': 'Invadida', 'slug': 'invadida',
        }, HTTP_HOST=self.host_a)
        self.category_b.refresh_from_db()
        self.assertNotEqual(self.category_b.name, 'Invadida')
        self.assertIn(response.status_code, (302, 403, 404))

    def test_labels_are_tenant_bound_and_product_categories_are_scoped(self):
        response = self.client.post('/admin/stores/customizationgrouplabel/add/', {'tenant': self.tenant_b.pk, 'name': 'Extras'}, HTTP_HOST=self.host_a)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CustomizationGroupLabel.objects.get(name='Extras').tenant_id, self.tenant_a.pk)
        form = tenant_admin_site._registry[Product].get_form(self.request)
        self.assertNotIn('tenant', form.base_fields)
        self.assertNotIn(self.category_b, form.base_fields['category'].queryset)

    def test_duplicate_tenant_category_has_form_error_not_500(self):
        response = self.client.post('/admin/stores/category/add/', {'name': 'Duplicada', 'slug': self.category_a.slug}, HTTP_HOST=self.host_a)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['adminform'].form.errors)

    def test_newly_provisioned_admin_can_create_inline_options(self):
        user = get_user_model()(username='new_owner', tenant=self.tenant_a)
        user.set_password(self.password)
        request = RequestFactory().post('/superadmin/accounts/user/add/')
        request.user = self.superuser
        CustomUserAdmin(get_user_model(), super_admin_site).save_model(request, user, None, False)
        self.assertTrue(user.is_tenant_admin)
        self.assertFalse(user.user_permissions.exists())
        self.client.force_login(user)
        label = CustomizationGroupLabel.objects.create(tenant=self.tenant_a, name='Complementos')
        response = self.client.post('/admin/stores/customizationgroup/add/', {
            'category': self.category_a.pk, 'label': label.pk, 'apply_to': 'whole', 'is_active': 'on', 'min_options': '0', 'max_options': '1',
            'options-TOTAL_FORMS': '1', 'options-INITIAL_FORMS': '0', 'options-MIN_NUM_FORMS': '0', 'options-MAX_NUM_FORMS': '1000',
            'options-0-name': 'Extra', 'options-0-price': '5.00', 'options-0-is_available': 'on', '_save': 'Salvar',
        }, HTTP_HOST=self.host_a)
        self.assertEqual(response.status_code, 302, getattr(response, 'context', None) and str(response.context['adminform'].form.errors))
        option = CustomizationOption.objects.get(name='Extra')
        self.assertEqual(option.tenant_id, self.tenant_a.pk)
        self.assertEqual(option.group.tenant_id, self.tenant_a.pk)

    def test_product_images_inline_present_for_regular_store_admin(self):
        admin = tenant_admin_site._registry[Product]
        self.assertEqual(len(admin.get_inline_instances(self.request, self.product_a)), 1)
        inline = admin.get_inline_instances(self.request, self.product_a)[0]
        self.assertFalse(inline.has_add_permission(self.request, self.product_b))

    def test_customers_and_coupon_inline_only_show_store_customers(self):
        u1 = get_user_model().objects.create_user(username='buyer_a')
        u2 = get_user_model().objects.create_user(username='buyer_b')
        c1 = Customer.objects.create(user=u1, phone='11999990001')
        c2 = Customer.objects.create(user=u2, phone='11999990002')
        Order.objects.create(tenant=self.tenant_a, customer=c1, customer_phone=c1.phone, total=1)
        Order.objects.create(tenant=self.tenant_b, customer=c2, customer_phone=c2.phone, total=1)
        admin = tenant_admin_site._registry[Customer]
        self.assertTrue(admin.has_view_permission(self.request))
        self.assertFalse(admin.has_view_permission(self.request, c2))
        self.assertFalse(admin.has_change_permission(self.request, c1))
        response = self.client.get('/admin/customers/customer/', HTTP_HOST=self.host_a)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'buyer_b')
        campaign = CouponCampaign.objects.create(tenant=self.tenant_a, name='Oferta', code='TESTE', discount_type='fixed_amount', discount_value=1)
        inline = tenant_admin_site._registry[CouponCampaign].get_inline_instances(self.request, campaign)[0]
        formset = inline.get_formset(self.request, campaign)
        field = formset.form.base_fields['customer']
        self.assertIn(c1, field.queryset)
        self.assertNotIn(c2, field.queryset)
        form = formset.form(data={'customer': c2.pk})
        self.assertFalse(form.is_valid())

    def test_inactive_or_other_store_user_has_no_base_permissions(self):
        admin = tenant_admin_site._registry[Category]
        self.request.user = self.admin_b
        self.assertFalse(admin.has_add_permission(self.request))
        self.assertFalse(admin.get_queryset(self.request).exists())

    def test_editing_product_name_preserves_concurrent_stock_change(self):
        Product.objects.filter(pk=self.product_a.pk).update(stock=3)
        self.product_a.name = 'Novo nome'
        tenant_admin_site._registry[Product].save_model(self.request, self.product_a, SimpleNamespace(changed_data=['name']), True)
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.stock, Decimal('3'))

    def test_create_api_success_current_fields_and_brand(self):
        self.client.force_login(self.superuser)
        response = self.client.post('/api/tenants/create/', {
            'name': 'API Loja', 'slug': 'api-loja', 'whatsapp_number': '5511988880001',
            'pickup_address': 'Rua Teste', 'pickup_number': '10',
            'brand': {'primary_color': '#123456'},
            'business_hours': [{'weekday': 0, 'is_closed': False, 'opening_time': '10:00', 'closing_time': '18:00'}],
        }, content_type='application/json', HTTP_HOST='vemdedelivery.com.br')
        self.assertEqual(response.status_code, 201, response.content)
        tenant = Tenant.objects.get(slug='api-loja')
        self.assertEqual(tenant.brand_config.primary_color, '#123456')
        self.assertEqual(tenant.business_hours.count(), 1)
        self.assertEqual(response.json()['brand']['primary_color'], '#123456')

    def test_create_api_invalid_and_obsolete_fields_are_rejected(self):
        self.client.force_login(self.superuser)
        for extra in [{'address': 'obsolete'}, {'business_hours': [{'weekday': 0, 'is_closed': False, 'opening_time': '10:00', 'closing_time': '10:00'}]}]:
            response = self.client.post('/api/tenants/create/', {'name': 'API', 'slug': 'api-invalid', 'whatsapp_number': '5511988880002', **extra}, content_type='application/json', HTTP_HOST='vemdedelivery.com.br')
            self.assertEqual(response.status_code, 400)
            self.assertFalse(Tenant.objects.filter(slug='api-invalid').exists())

    def test_create_api_rolls_back_tenant_if_brand_fails(self):
        self.client.force_login(self.superuser)
        before = Tenant.objects.count()
        with patch('apps.tenants.serializers.BrandConfig.objects.create', side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):
                self.client.post('/api/tenants/create/', {'name': 'API', 'slug': 'api-failure', 'whatsapp_number': '5511988880003'}, content_type='application/json', HTTP_HOST='vemdedelivery.com.br')
        self.assertEqual(Tenant.objects.count(), before)

    def test_inline_cannot_edit_or_delete_foreign_option(self):
        label = CustomizationGroupLabel.objects.create(tenant=self.tenant_a, name='Alpha Extras')
        group = CustomizationGroup.objects.create(tenant=self.tenant_a, category=self.category_a, label=label)
        other_label = CustomizationGroupLabel.objects.create(tenant=self.tenant_b, name='Beta Extras')
        other_group = CustomizationGroup.objects.create(tenant=self.tenant_b, category=self.category_b, label=other_label)
        other = CustomizationOption.objects.create(tenant=self.tenant_b, group=other_group, name='Protegida', price=10)
        for delete in ['', 'on']:
            self.client.post(f'/admin/stores/customizationgroup/{group.pk}/change/', {
                'category': self.category_a.pk, 'label': label.pk, 'apply_to': 'whole', 'is_active': 'on', 'min_options': '0', 'max_options': '1',
                'options-TOTAL_FORMS': '1', 'options-INITIAL_FORMS': '1', 'options-MIN_NUM_FORMS': '0', 'options-MAX_NUM_FORMS': '1000',
                'options-0-id': other.pk, 'options-0-name': 'Invadida', 'options-0-price': '0', 'options-0-is_available': 'on', 'options-0-DELETE': delete,
            }, HTTP_HOST=self.host_a)
            other.refresh_from_db()
            self.assertEqual(other.name, 'Protegida')
            self.assertEqual(other.tenant_id, self.tenant_b.pk)
            self.assertEqual(other.price, 10)

    def test_new_product_and_extra_image_can_be_saved(self):
        import io
        import tempfile
        from PIL import Image
        image = io.BytesIO()
        Image.new('RGB', (500, 500), 'white').save(image, format='PNG')
        upload = SimpleUploadedFile('image.png', image.getvalue(), content_type='image/png')
        with tempfile.TemporaryDirectory() as media, self.settings(MEDIA_ROOT=media):
            response = self.client.post('/admin/stores/product/add/', {
                'tenant': self.tenant_b.pk, 'name': 'Novo produto', 'category': self.category_a.pk, 'price': '20', 'min_order_qty': '1', 'stock': '5', 'is_available': 'on',
                'images-TOTAL_FORMS': '1', 'images-INITIAL_FORMS': '0', 'images-MIN_NUM_FORMS': '0', 'images-MAX_NUM_FORMS': '1000',
                'images-0-image': upload, 'images-0-order': '0', '_save': 'Salvar',
            }, HTTP_HOST=self.host_a)
            self.assertEqual(response.status_code, 302, str(response.context and response.context['adminform'].form.errors))
            product = Product.objects.get(name='Novo produto')
            self.assertEqual(product.tenant_id, self.tenant_a.pk)
            self.assertEqual(product.images.get().tenant_id, self.tenant_a.pk)

    def test_store_settings_delivery_inline_available(self):
        parent = tenant_admin_site._registry[Tenant]
        inlines = parent.get_inline_instances(self.request, self.tenant_a)
        self.assertEqual(
            {inline.model._meta.model_name for inline in inlines},
            {'deliveryzone', 'businesshour', 'tenantpaymentaccount'},
        )
        self.assertTrue(all(not inline.has_change_permission(self.request, self.tenant_b) for inline in inlines))

    def test_online_payment_uses_stable_button_asset_and_hides_checkbox(self):
        form = TenantPaymentAccountForm()
        self.assertIn("display:none", form.fields["enabled"].widget.attrs["style"])
        self.assertEqual(form.media._js, ["js/admin/payment-account.js"])

    def test_coupon_redemptions_list_uses_related_tenant_scope(self):
        from apps.coupons.models import CouponRedemption
        user = get_user_model().objects.create_user(username='coupon_customer')
        customer = Customer.objects.create(user=user, phone='11999992222')
        for tenant in [self.tenant_a, self.tenant_b]:
            campaign = CouponCampaign.objects.create(tenant=tenant, code=f'COUPON{tenant.pk}', name='Oferta', discount_type='fixed_amount', discount_value=1)
            order = Order.objects.create(tenant=tenant, customer=customer, customer_phone=customer.phone, total=10)
            CouponRedemption.objects.create(campaign=campaign, order=order, customer=customer, discount_amount=1)
        response = self.client.get('/admin/coupons/couponredemption/', HTTP_HOST=self.host_a)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['cl'].result_count, 1)
        admin = tenant_admin_site._registry[CouponRedemption]
        self.assertFalse(admin.has_view_permission(self.request, CouponRedemption.objects.get(campaign__tenant=self.tenant_b)))

    def test_product_with_foreign_category_returns_form_error(self):
        response = self.client.post('/admin/stores/product/add/', {
            'name': 'Inválido', 'category': self.category_b.pk, 'price': '20', 'min_order_qty': '1',
            'images-TOTAL_FORMS': '0', 'images-INITIAL_FORMS': '0', 'images-MIN_NUM_FORMS': '0', 'images-MAX_NUM_FORMS': '1000',
        }, HTTP_HOST=self.host_a)
        self.assertEqual(response.status_code, 200)
        self.assertIn('category', response.context['adminform'].form.errors)
        self.assertFalse(Product.objects.filter(name='Inválido').exists())
