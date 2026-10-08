from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase, Client, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.tenants.models import Tenant, BrandConfig, BusinessHour
from apps.stores.models import Category, Product, ProductImage
from apps.orders.models import Order
from apps.merchant.registry import RESOURCES


class MerchantAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = Tenant.objects.create(
            name="Loja A", slug="loja-a", whatsapp_number="5511999991111"
        )
        cls.b = Tenant.objects.create(
            name="Loja B", slug="loja-b", whatsapp_number="5511999992222"
        )
        cls.user = get_user_model().objects.create_user(
            username="merchant",
            email="merchant@example.com",
            password="Strong-Test-Password123!",
            tenant=cls.a,
            is_staff=True,
            is_tenant_admin=True,
        )
        cls.category = Category.objects.create(
            tenant=cls.a, name="Lanches", slug="lanches"
        )
        cls.other_category = Category.objects.create(
            tenant=cls.b, name="Segredo", slug="segredo"
        )
        cls.product = Product.objects.create(
            tenant=cls.a,
            category=cls.category,
            name="Produto",
            slug="produto",
            price="12.50",
            stock=10,
        )
        cls.other_product = Product.objects.create(
            tenant=cls.b,
            category=cls.other_category,
            name="Segredo B",
            slug="secreto",
            price="99",
        )
        cls.order = Order.objects.create(
            tenant=cls.a, total="12.50", subtotal="12.50", customer_name="Cliente A"
        )

    def setUp(self):
        self.client = Client(HTTP_HOST="loja-a.lvh.me")
        self.client.force_login(self.user)

    def url(self, key, suffix=""):
        return "/api/merchant/resources/" + key + "/" + suffix

    def payload(self, doc):
        result = {}

        def fields(items):
            for f in items:
                if f["disabled"] or f["kind"] == "file":
                    continue
                v = f["value"]
                if f["kind"] == "checkbox":
                    if v:
                        result[f["html_name"]] = "on"
                elif f["split"]:
                    pieces = str(v).split("T")
                    result[f["html_name"] + "_0"] = pieces[0]
                    result[f["html_name"] + "_1"] = (
                        pieces[1][:8] if len(pieces) > 1 else ""
                    )
                else:
                    result[f["html_name"]] = v

        fields(doc["fields"])
        for g in doc["inlines"]:
            fields(g["management"])
            for row in g["forms"]:
                fields(row["fields"])
        return result

    def test_all_list_schemas(self):
        for key in RESOURCES:
            with self.subTest(key=key):
                response = self.client.get(self.url(key))
                self.assertEqual(response.status_code, 200, response.content[:600])
                self.assertIn("rows", response.json())
                self.assertNotIn("Segredo", str(response.json()))

    def test_all_existing_detail_schemas_and_allowed_forms_roundtrip(self):
        for key in RESOURCES:
            with self.subTest(key=key):
                listing = self.client.get(self.url(key)).json()
                for row in listing["rows"]:
                    response = self.client.get(self.url(key, str(row["id"]) + "/"))
                    self.assertEqual(response.status_code, 200, response.content[:600])
                    doc = response.json()
                    if doc["can_save"]:
                        result = self.client.post(
                            self.url(key, str(row["id"]) + "/"), self.payload(doc)
                        )
                        self.assertEqual(result.status_code, 200, result.content[:1500])

    def test_tenant_host_mismatch_and_superadmin_rejected(self):
        self.assertEqual(
            self.client.get(
                "/api/merchant/dashboard/", HTTP_HOST="loja-b.lvh.me"
            ).status_code,
            403,
        )
        superuser = get_user_model().objects.create_superuser(
            "platform", "platform@example.com", "SuperTest123!"
        )
        self.client.force_login(superuser)
        self.assertEqual(self.client.get("/api/merchant/dashboard/").status_code, 403)

    def test_anonymous_session(self):
        self.client.logout()
        self.assertEqual(self.client.get("/api/merchant/dashboard/").status_code, 401)

    def test_foreign_ids_and_relations(self):
        self.assertEqual(
            self.client.get(
                self.url("products", str(self.other_product.pk) + "/")
            ).status_code,
            404,
        )
        doc = self.client.get(self.url("products", str(self.product.pk) + "/")).json()
        data = self.payload(doc)
        data["category"] = self.other_category.pk
        response = self.client.post(
            self.url("products", str(self.product.pk) + "/"), data
        )
        self.assertEqual(response.status_code, 400)
        self.product.refresh_from_db()
        self.assertEqual(self.product.category_id, self.category.pk)

    def test_category_crud_validation_and_delete_confirmation(self):
        url = self.url("categories", "new/")
        doc = self.client.get(url).json()
        data = self.payload(doc)
        data.update(name="Bebidas", slug="bebidas", display_order="2")
        r = self.client.post(url, data)
        self.assertEqual(r.status_code, 200, r.content)
        pk = r.json()["id"]
        self.assertTrue(Category.objects.filter(pk=pk, tenant=self.a).exists())
        r = self.client.delete(self.url("categories", f"{pk}/"))
        self.assertTrue(r.json()["confirmation_required"])
        self.assertTrue(Category.objects.filter(pk=pk).exists())
        r = self.client.delete(self.url("categories", f"{pk}/?confirm=yes"))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Category.objects.filter(pk=pk).exists())
        data["name"] = ""
        r = self.client.post(url, data)
        self.assertEqual(r.status_code, 400)
        self.assertTrue(
            next(f for f in r.json()["fields"] if f["name"] == "name")["errors"]
        )

    def test_actions_are_scoped_and_orders_require_confirmation(self):
        r = self.client.post(
            self.url("products", "actions/"),
            {"action": "mark_as_unavailable", "ids": [self.other_product.pk]},
        )
        self.assertEqual(r.status_code, 404)
        r = self.client.post(
            self.url("products", "actions/"),
            {"action": "mark_as_unavailable", "ids": [self.product.pk]},
        )
        self.assertEqual(r.status_code, 200)
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_available)
        r = self.client.post(
            self.url("orders", "actions/"),
            {"action": "cancel_orders", "ids": [self.order.pk]},
        )
        self.assertTrue(r.json()["confirmation_required"])
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.status, "cancelled")
        r = self.client.post(
            self.url("orders", "actions/"),
            {"action": "cancel_orders", "ids": [self.order.pk], "confirmed": "yes"},
        )
        self.assertEqual(r.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "cancelled")

    def test_customer_and_order_write_restrictions(self):
        self.assertEqual(
            self.client.get(self.url("customers", "new/")).status_code, 403
        )
        self.assertEqual(self.client.get(self.url("orders", "new/")).status_code, 403)
        self.assertEqual(
            self.client.delete(
                self.url("orders", str(self.order.pk) + "/")
            ).status_code,
            403,
        )

    def test_csrf_login_and_session_write(self):
        c = Client(enforce_csrf_checks=True, HTTP_HOST="loja-a.lvh.me")
        self.assertEqual(
            c.post(
                "/api/merchant/session/",
                {"username": "merchant", "password": "Strong-Test-Password123!"},
            ).status_code,
            403,
        )
        csrf = c.get("/api/merchant/session/").json()["csrf"]
        r = c.post(
            "/api/merchant/session/",
            {"username": "merchant", "password": "Strong-Test-Password123!"},
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(
            c.post(self.url("categories", "new/"), {"name": "X"}).status_code, 403
        )
        self.assertEqual(c.get("/api/merchant/dashboard/").status_code, 200)

    def test_temporary_password_blocks_every_business_endpoint(self):
        self.user.must_change_password = True
        self.user.save(update_fields=["must_change_password"])
        self.assertEqual(self.client.get("/api/merchant/dashboard/").status_code, 403)
        self.assertEqual(self.client.get("/api/merchant/finance/").status_code, 403)
        response = self.client.post(
            "/api/merchant/password/",
            {
                "old_password": "Strong-Test-Password123!",
                "new_password1": "New-Strong-Unrelated123!",
                "new_password2": "New-Strong-Unrelated123!",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.client.get("/api/merchant/dashboard/").status_code, 200)

    def test_empty_fiscal_structure_and_bounded_pagination(self):
        response = self.client.get("/api/merchant/finance/notes/?page_size=10")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["notes"], [])
        self.assertEqual(response.json()["total"], 0)
        for number in range(15):
            Category.objects.create(tenant=self.a, name=f"Extra {number}", slug=f"extra-{number}")
        for size, expected in [("10", 10), ("25", 16), ("100000", 10), ("invalid", 10)]:
            response = self.client.get("/api/merchant/resources/categories/", {"page_size": size})
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(len(response.json()["rows"]), expected)
            self.assertNotIn("Segredo", str(response.json()))

    def test_finance_and_whatsapp_json_and_no_secrets(self):
        for path in ["finance/", "finance/notes/", "whatsapp/"]:
            response = self.client.get("/api/merchant/" + path)
            self.assertEqual(response.status_code, 200, response.content[:500])
            data = response.json()
            self.assertNotIn("encrypted_api_key", str(data))
            self.assertNotIn("<html", str(data))
        self.assertEqual(
            self.client.get("/api/merchant/finance/fees/").status_code, 404
        )

    @override_settings(MERCHANT_REACT_ENABLED=True)
    def test_cutover_keeps_platform_and_public_routes(self):
        self.assertRedirects(
            self.client.get("/admin/stores/product/"),
            "/painel/products",
            fetch_redirect_response=False,
        )
        self.assertEqual(
            self.client.post("/admin/stores/product/add/", {}).status_code, 409
        )
        self.assertEqual(self.client.get("/superadmin/").status_code, 404)
        self.assertEqual(self.client.get("/painel/products").status_code, 200)

    def test_all_add_forms_and_stock_price_validation(self):
        for key in RESOURCES:
            listing = self.client.get(self.url(key)).json()
            if listing["can_add"]:
                response = self.client.get(self.url(key, "new/"))
                self.assertEqual(response.status_code, 200, response.content[:800])
        doc = self.client.get(self.url("products", f"{self.product.pk}/")).json()
        data = self.payload(doc)
        data["stock"] = "-1"
        data["price"] = "invalid"
        r = self.client.post(self.url("products", f"{self.product.pk}/"), data)
        self.assertEqual(r.status_code, 400)
        self.product.refresh_from_db()
        self.assertEqual(self.product.price, Decimal("12.50"))
        self.assertEqual(self.product.stock, 10)

    def test_hours_can_have_two_intervals_and_closed_clears_times(self):
        for opening, closing in [("08:00", "12:00"), ("14:00", "18:00")]:
            r = self.client.post(
                self.url("hours", "new/"),
                {
                    "weekday": "0",
                    "is_open": "on",
                    "opening_time": opening,
                    "closing_time": closing,
                },
            )
            self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(
            BusinessHour.objects.filter(
                tenant=self.a, weekday=0, is_closed=False
            ).count(),
            2,
        )
        hour = BusinessHour.objects.filter(
            tenant=self.a, weekday=0, is_closed=False
        ).first()
        doc = self.client.get(self.url("hours", f"{hour.pk}/")).json()
        data = self.payload(doc)
        data.pop("is_open", None)
        r = self.client.post(self.url("hours", f"{hour.pk}/"), data)
        self.assertEqual(r.status_code, 200, r.content)
        hour.refresh_from_db()
        self.assertTrue(hour.is_closed)
        self.assertIsNone(hour.opening_time)

    def test_option_inline_creation_and_foreign_inline_attack(self):
        from apps.stores.models import (
            CustomizationGroupLabel,
            CustomizationGroup,
            CustomizationOption,
        )

        label = CustomizationGroupLabel.objects.create(tenant=self.a, name="Adicionais")
        doc = self.client.get(self.url("groups", "new/")).json()
        data = self.payload(doc)
        data.update(
            category=self.category.pk,
            label=label.pk,
            apply_to="both",
            min_options="0",
            max_options="3",
            is_active="on",
        )
        group = doc["inlines"][0]
        prefix = group["prefix"]
        data.update(
            {
                f"{prefix}-0-name": "Queijo",
                f"{prefix}-0-description": "Extra",
                f"{prefix}-0-price": "3.50",
                f"{prefix}-0-is_available": "on",
            }
        )
        r = self.client.post(self.url("groups", "new/"), data)
        self.assertEqual(r.status_code, 200, str(r.json())[-4500:])
        option = CustomizationOption.objects.get(group_id=r.json()["id"])
        self.assertEqual(option.tenant_id, self.a.pk)
        other_label = CustomizationGroupLabel.objects.create(
            tenant=self.b, name="Privado"
        )
        other_group = CustomizationGroup.objects.create(
            tenant=self.b, label=other_label, category=self.other_category
        )
        other_option = CustomizationOption.objects.create(
            tenant=self.b, group=other_group, name="Segredo", price="9"
        )
        doc = self.client.get(self.url("groups", f"{option.group_id}/")).json()
        data = self.payload(doc)
        data[f"{prefix}-0-id"] = str(other_option.pk)
        r = self.client.post(self.url("groups", f"{option.group_id}/"), data)
        self.assertEqual(r.status_code, 403)
        other_option.refresh_from_db()
        self.assertEqual(other_option.name, "Segredo")

    def test_image_upload_and_half_half_action(self):
        import io, tempfile
        from PIL import Image
        from apps.stores.models import HalfProduct

        file = io.BytesIO()
        Image.new("RGB", (800, 800), "red").save(file, "PNG")
        doc = self.client.get(self.url("products", f"{self.product.pk}/")).json()
        data = self.payload(doc)
        prefix = doc["inlines"][0]["prefix"]
        data[f"{prefix}-0-image"] = SimpleUploadedFile(
            "test.png", file.getvalue(), content_type="image/png"
        )
        data[f"{prefix}-0-is_primary"] = "on"
        with tempfile.TemporaryDirectory() as media, override_settings(
            MEDIA_ROOT=media
        ):
            r = self.client.post(self.url("products", f"{self.product.pk}/"), data)
            self.assertEqual(r.status_code, 200, str(r.json())[-4500:])
            self.assertTrue(
                ProductImage.objects.filter(
                    product=self.product, tenant=self.a
                ).exists()
            )
        r = self.client.post(
            self.url("products", "actions/"),
            {"action": "create_half_for_selected", "ids": [self.product.pk]},
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(HalfProduct.objects.filter(product=self.product).exists())

    def test_online_account_form_preserves_status_and_hides_keys(self):
        from apps.billing.models import TenantPaymentAccount

        self.a.online_payments_allowed = True
        self.a.save()
        account = TenantPaymentAccount.objects.create(
            tenant=self.a, encrypted_api_key="SECRET-DO-NOT-RETURN", enabled=False
        )
        doc = self.client.get(self.url("store", f"{self.a.pk}/")).json()
        self.assertNotIn("SECRET-DO-NOT-RETURN", str(doc))
        self.assertNotIn("encrypted_api_key", str(doc))
        self.assertTrue(
            any(
                "terms_accepted"
                in [f["name"] for row in g["forms"] for f in row["fields"]]
                for g in doc["inlines"]
            )
        )
        data = self.payload(doc)
        r = self.client.post(self.url("store", f"{self.a.pk}/"), data)
        self.assertEqual(
            r.status_code,
            200,
            [
                (
                    g["prefix"],
                    g["errors"],
                    [
                        (f["html_name"], f["errors"])
                        for row in g["forms"]
                        for f in row["fields"]
                        if f["errors"]
                    ],
                )
                for g in r.json().get("inlines", [])
            ],
        )
        account.refresh_from_db()
        self.assertEqual(account.encrypted_api_key, "SECRET-DO-NOT-RETURN")

    def test_coupons_target_only_customers_of_this_store(self):
        from apps.customers.models import Customer
        from apps.coupons.models import CouponCampaign, CouponAssignment
        from django.utils import timezone

        user = get_user_model().objects.create_user(
            username="customer1", password="NotUsed123!"
        )
        customer, _ = Customer.objects.get_or_create(
            user=user, defaults={"phone": "5511988881111"}
        )
        self.order.customer = customer
        self.order.save()
        foreign_user = get_user_model().objects.create_user(
            username="customer2", password="NotUsed123!"
        )
        foreign, _ = Customer.objects.get_or_create(
            user=foreign_user, defaults={"phone": "5511988882222"}
        )
        Order.objects.create(tenant=self.b, customer=foreign, total="10")
        campaign = CouponCampaign.objects.create(
            tenant=self.a,
            name="Teste",
            code="TESTE10",
            discount_type="percentage",
            discount_value="10",
            audience_type="specific",
            starts_at=timezone.now(),
        )
        doc = self.client.get(self.url("coupons", f"{campaign.pk}/")).json()
        data = self.payload(doc)
        g = doc["inlines"][0]
        prefix = g["prefix"]
        choices = next(f for f in g["empty"]["fields"] if f["name"] == "customer")[
            "choices"
        ]
        self.assertIn(str(customer.pk), [x["value"] for x in choices])
        self.assertNotIn(str(foreign.pk), [x["value"] for x in choices])
        data[f"{prefix}-TOTAL_FORMS"] = "1"
        data[f"{prefix}-0-customer"] = str(customer.pk)
        data[f"{prefix}-0-campaign"] = str(campaign.pk)
        data[f"{prefix}-0-id"] = ""
        r = self.client.post(self.url("coupons", f"{campaign.pk}/"), data)
        self.assertEqual(r.status_code, 200, str(r.json())[-6500:])
        self.assertTrue(
            CouponAssignment.objects.filter(
                campaign=campaign, customer=customer
            ).exists()
        )

    def test_invoice_scope_notes_and_financial_actions(self):
        from unittest.mock import patch
        from apps.billing.models import Invoice

        bill = Invoice.objects.create(
            tenant=self.a,
            plan_name="Mensal",
            months=1,
            amount="149",
            method="PIX",
            environment="sandbox",
            due_date=__import__("datetime").date(2026, 10, 12),
        )
        other = Invoice.objects.create(
            tenant=self.b,
            plan_name="Privado",
            months=1,
            amount="149",
            method="PIX",
            environment="sandbox",
            due_date=__import__("datetime").date(2026, 10, 12),
        )
        r = self.client.get(f"/api/merchant/finance/invoices/{bill.pk}/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["invoice"]["amount"], "149.00")
        self.assertEqual(
            self.client.get(f"/api/merchant/finance/invoices/{other.pk}/").status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/merchant/finance/invoices/{other.pk}/refresh/"
            ).status_code,
            404,
        )
        with patch(
            "apps.billing.views.reconcile_invoice", return_value=bill
        ) as refresh:
            r = self.client.post(f"/api/merchant/finance/invoices/{bill.pk}/refresh/")
            self.assertEqual(r.status_code, 200)
            refresh.assert_called_once_with(bill.pk)
            self.assertTrue(r.json()["redirect"].startswith("/painel/cobrancas/"))

    @override_settings(WHATSAPP_AGENT_ENABLED=True)
    def test_whatsapp_actions_reuse_service_and_do_not_return_html(self):
        from unittest.mock import patch

        with patch(
            "apps.integrations.tenant_views.connect_agent",
            return_value="data:image/png;base64,AAAA",
        ) as connect:
            r = self.client.post("/api/merchant/whatsapp/", {"action": "connect"})
            self.assertEqual(r.status_code, 200, r.content)
            self.assertEqual(r.json()["qr"], "data:image/png;base64,AAAA")
            self.assertEqual(connect.call_args.args[0].tenant_id, self.a.pk)

    def test_quick_edit_keeps_hooks_and_rejects_foreign_ids(self):
        url = self.url("products", "list-edit/")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, response.content)
        doc = response.json()
        data = {}
        for f in doc["management"] + [f for row in doc["rows"] for f in row["fields"]]:
            if f["kind"] == "checkbox":
                if f["value"]:
                    data[f["html_name"]] = "on"
            else:
                data[f["html_name"]] = f["value"]
        data.pop("form-0-is_available", None)
        result = self.client.post(url, data)
        self.assertEqual(result.status_code, 200, result.content)
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_available)
        self.assertEqual(self.product.stock, 10)
        data["form-0-id"] = str(self.other_product.pk)
        self.assertEqual(self.client.post(url, data).status_code, 403)
        self.assertEqual(
            self.client.get(self.url("customers", "list-edit/")).status_code, 403
        )
