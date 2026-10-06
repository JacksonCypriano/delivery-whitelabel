# Inventário técnico do painel do lojista

Escopo levantado antes da implementação a partir das rotas, registros de TenantAdminSite, ModelAdmins, modelos, formulários, templates, JavaScript, serviços, middlewares e scripts do ZIP original. O detalhamento abaixo relaciona as declarações de formulário preservadas no backend.

## Matriz de telas

| Tela | Rota anterior | View/controlador existente | Model | React | API | Situação |
|---|---|---|---|---|---|---|
| Minha loja | `/admin/tenants/tenant/` (lista, cadastro/edição, exclusão e histórico conforme permissão) | `apps.tenants.admin.StoreSettingsAdmin` | `tenants.tenant` | `/painel/store` e `/painel/store/:id` | `/api/merchant/resources/store/` | Implementada; aceite manual de homolog pendente |
| Identidade visual | `/admin/tenants/brandconfig/` (lista, cadastro/edição, exclusão e histórico conforme permissão) | `apps.tenants.admin.TenantBrandConfigAdmin` | `tenants.brandconfig` | `/painel/branding` e `/painel/branding/:id` | `/api/merchant/resources/branding/` | Implementada; aceite manual de homolog pendente |
| Horários | `/admin/tenants/businesshour/` (lista, cadastro/edição, exclusão e histórico conforme permissão) | `apps.tenants.admin.BusinessHourAdmin` | `tenants.businesshour` | `/painel/hours` e `/painel/hours/:id` | `/api/merchant/resources/hours/` | Implementada; aceite manual de homolog pendente |
| Áreas de entrega | `/admin/tenants/deliveryzone/` (lista, cadastro/edição, exclusão e histórico conforme permissão) | `apps.tenants.admin.DeliveryZoneAdmin` | `tenants.deliveryzone` | `/painel/delivery` e `/painel/delivery/:id` | `/api/merchant/resources/delivery/` | Implementada; aceite manual de homolog pendente |
| Perfil público | `/admin/marketplace/marketplaceprofile/` (lista, cadastro/edição, exclusão e histórico conforme permissão) | `apps.marketplace.admin.MarketplaceProfileTenantAdmin` | `marketplace.marketplaceprofile` | `/painel/profile` e `/painel/profile/:id` | `/api/merchant/resources/profile/` | Implementada; aceite manual de homolog pendente |
| Produtos | `/admin/stores/product/` (lista, cadastro/edição, exclusão e histórico conforme permissão) | `apps.stores.admin.ProductAdmin` | `stores.product` | `/painel/products` e `/painel/products/:id` | `/api/merchant/resources/products/` | Implementada; aceite manual de homolog pendente |
| Categorias | `/admin/stores/category/` (lista, cadastro/edição, exclusão e histórico conforme permissão) | `apps.stores.admin.CategoryAdmin` | `stores.category` | `/painel/categories` e `/painel/categories/:id` | `/api/merchant/resources/categories/` | Implementada; aceite manual de homolog pendente |
| Adicionais e opções | `/admin/stores/customizationgroup/` (lista, cadastro/edição, exclusão e histórico conforme permissão) | `apps.stores.admin.CustomizationGroupAdmin` | `stores.customizationgroup` | `/painel/groups` e `/painel/groups/:id` | `/api/merchant/resources/groups/` | Implementada; aceite manual de homolog pendente |
| Rótulos dos adicionais | `/admin/stores/customizationgrouplabel/` (lista, cadastro/edição, exclusão e histórico conforme permissão) | `apps.stores.admin.CustomizationGroupLabelAdmin` | `stores.customizationgrouplabel` | `/painel/labels` e `/painel/labels/:id` | `/api/merchant/resources/labels/` | Implementada; aceite manual de homolog pendente |
| Pedidos | `/admin/orders/order/` (lista, cadastro/edição, exclusão e histórico conforme permissão) | `apps.orders.admin.OrderAdmin` | `orders.order` | `/painel/orders` e `/painel/orders/:id` | `/api/merchant/resources/orders/` | Implementada; aceite manual de homolog pendente |
| Clientes | `/admin/customers/customer/` (lista, cadastro/edição, exclusão e histórico conforme permissão) | `apps.customers.admin.CustomerAdmin` | `customers.customer` | `/painel/customers` e `/painel/customers/:id` | `/api/merchant/resources/customers/` | Implementada; aceite manual de homolog pendente |
| Cupons e campanhas | `/admin/coupons/couponcampaign/` (lista, cadastro/edição, exclusão e histórico conforme permissão) | `apps.coupons.admin.CouponCampaignAdmin` | `coupons.couponcampaign` | `/painel/coupons` e `/painel/coupons/:id` | `/api/merchant/resources/coupons/` | Implementada; aceite manual de homolog pendente |
| Utilizações de cupons | `/admin/coupons/couponredemption/` (lista, cadastro/edição, exclusão e histórico conforme permissão) | `apps.coupons.admin.CouponRedemptionAdmin` | `coupons.couponredemption` | `/painel/redemptions` e `/painel/redemptions/:id` | `/api/merchant/resources/redemptions/` | Implementada; aceite manual de homolog pendente |

As telas de models usam os templates compartilhados `admin/change_list.html`, `admin/change_form.html`, `admin/delete_confirmation.html`, `admin/delete_selected_confirmation.html` e `admin/object_history.html` fornecidos por Django/Unfold. Pedidos substituem a lista por `admin/orders/order/change_list.html` e o cancelamento por `admin/orders/order/confirm_cancel.html`.

| Tela especial | Rota anterior | View | Template | Models/serviços | React/API |
|---|---|---|---|---|---|
| Dashboard | `/admin/`, `/dashboard/` | `TenantAdminSite.index`, `DashboardHomeView.get` | `admin/tenant/index.html`, `dashboard/home.html` | onboarding, Subscription, Product, Category | `/painel/`, `dashboard/` |
| Assinatura/planos/adicionais | `/admin/minha-assinatura/` | `billing.views.dashboard`, `purchase` | `billing/dashboard.html`, `billing/setup_required.html` | PurchaseForm, Plan, AdditionalService, BillingSettings, Subscription, BillingCustomer, Invoice; cotações assinadas e serviços existentes | `/painel/assinatura`, `finance/`, `finance/purchase/` |
| Cobrança e consulta | `/admin/minha-assinatura/cobranca/:uuid/` | `invoice_detail`, `refresh` | `billing/invoice.html` | Invoice, FiscalInvoice, reconcile_invoice | `/painel/cobrancas/:uuid`, `finance/invoices/:uuid/` |
| Notas e arquivos | `/admin/notas-fiscais/`, cobrança/nota/pdf ou xml | `fiscal_list`, `fiscal_download` | `billing/fiscal_list.html` | FiscalInvoice, attachment_response e hash existente | `/painel/notas`, `finance/notes/`, download binário autenticado |
| Taxas online | `/admin/taxas-pagamentos-online/` | `online_fees` | `billing/online_fees.html` | TenantPaymentAccount, Asaas, parse_asaas_fees | `/painel/taxas`, `finance/fees/` |
| WhatsApp/agente | `/admin/atendimento-whatsapp/` | `tenant_whatsapp_agent_panel` | `admin/tenant/whatsapp_agent.html` | TenantWhatsAppAgent, eventos, connect/check/disconnect/toggle; Evolution existente | `/painel/whatsapp`, `whatsapp/` |
| Acesso e senha | `/admin/login/`, `/admin/logout/`, `/admin/password_change/` | TenantAdminSite e auth Django | templates de autenticação Django/Unfold | TenantAdminAuthenticationForm, PasswordChangeForm, User, sessões, rate limit, auditoria | `/painel/login`, `/painel/logout`, `/painel/senha`; `session/`, `password/` |

Os sufixos API da tabela especial têm prefixo `/api/merchant/`.

## Formulários e operações por recurso

### Minha loja

- Controlador: `apps.tenants.admin.StoreSettingsAdmin`.
- Formulário base declarado: `apps.tenants.admin.TenantChangeForm`. `get_form()` e seus wrappers de tenant/request são reutilizados.
- Campos de formulário: `name`, `whatsapp_number`, `whatsapp_order_number`, `fulfillment_mode`, `pickup_zip_code`, `pickup_address`, `pickup_number`, `pickup_complement`, `pickup_neighborhood`, `pickup_city`, `marketing_lead_reference`.
- Somente leitura: `slug`, `is_active`, `created_at`.
- Busca: não declarada.
- Filtros: `()`.
- Ações: nenhuma.
- Formulário auxiliar `tenants.BusinessHour`: `apps.tenants.admin_ux.BusinessHourAdminForm`; campos: weekday, is_open, opening_time, closing_time. Reutiliza formset, permissões e salvamento do controlador existente.
- Formulário auxiliar `billing.TenantPaymentAccount`: `apps.tenants.admin.TenantPaymentAccountForm`; campos: terms_accepted, enabled, legal_name, document, email, mobile_phone, phone, birth_date, company_type, income_value, postal_code, address, address_number, complement, province. Reutiliza formset, permissões e salvamento do controlador existente.
- Formulário auxiliar `tenants.DeliveryZone`: `apps.tenants.admin_ux.DeliveryZoneAdminForm`; campos: city, neighborhood, fee, is_active. Reutiliza formset, permissões e salvamento do controlador existente.
- Validação definitiva: formulários Django acima (`clean`, `_post_clean`, validadores de campo/model e constraints) e os mesmos hooks `save_form`, `save_model`, `save_related`, `save_formset`. Alteração de comportamento não faz parte deste pacote.

### Identidade visual

- Controlador: `apps.tenants.admin.TenantBrandConfigAdmin`.
- Formulário base declarado: `apps.tenants.admin_ux.BrandConfigAdminForm`. `get_form()` e seus wrappers de tenant/request são reutilizados.
- Campos de formulário: `primary_color`, `secondary_color`, `accent_color`, `background_color`, `card_background_color`, `text_color`, `muted_text_color`, `border_color`, `button_text_color`, `success_color`, `warning_color`, `danger_color`, `font_family`, `base_font_size`, `border_radius`, `button_radius`, `card_shadow`, `hover_effect`, `header_style`, `show_search_bar`, `show_category_icons`, `show_product_description`, `show_product_image`, `compact_product_cards`, `dark_mode_enabled`, `dark_mode_primary`, `dark_mode_background`, `dark_mode_card_background`, `dark_mode_text`, `dark_mode_muted_text`, `dark_mode_border_color`, `logo`, `favicon`, `banner`.
- Somente leitura: `tenant`.
- Busca: não declarada.
- Filtros: `()`.
- Ações: delete_selected.
- Validação definitiva: formulários Django acima (`clean`, `_post_clean`, validadores de campo/model e constraints) e os mesmos hooks `save_form`, `save_model`, `save_related`, `save_formset`. Alteração de comportamento não faz parte deste pacote.

### Horários

- Controlador: `apps.tenants.admin.BusinessHourAdmin`.
- Formulário base declarado: `apps.tenants.admin_ux.BusinessHourAdminForm`. `get_form()` e seus wrappers de tenant/request são reutilizados.
- Campos de formulário: `weekday`, `opening_time`, `closing_time`, `is_open`.
- Somente leitura: `tenant`.
- Busca: não declarada.
- Filtros: `('weekday', <class 'apps.tenants.admin.BusinessHourOpenFilter'>)`.
- Ações: delete_selected.
- Validação definitiva: formulários Django acima (`clean`, `_post_clean`, validadores de campo/model e constraints) e os mesmos hooks `save_form`, `save_model`, `save_related`, `save_formset`. Alteração de comportamento não faz parte deste pacote.

### Áreas de entrega

- Controlador: `apps.tenants.admin.DeliveryZoneAdmin`.
- Formulário base declarado: `apps.tenants.admin_ux.DeliveryZoneAdminForm`. `get_form()` e seus wrappers de tenant/request são reutilizados.
- Campos de formulário: `city`, `neighborhood`, `fee`, `is_active`.
- Somente leitura: nenhum.
- Busca: city, neighborhood.
- Filtros: `('city', 'is_active')`.
- Ações: delete_selected.
- Validação definitiva: formulários Django acima (`clean`, `_post_clean`, validadores de campo/model e constraints) e os mesmos hooks `save_form`, `save_model`, `save_related`, `save_formset`. Alteração de comportamento não faz parte deste pacote.

### Perfil público

- Controlador: `apps.marketplace.admin.MarketplaceProfileTenantAdmin`.
- Formulário base declarado: `apps.marketplace.admin.MarketplaceProfileTenantForm`. `get_form()` e seus wrappers de tenant/request são reutilizados.
- Campos de formulário: `is_listed`, `short_description`, `search_keywords`, `categories`.
- Somente leitura: `tenant`, `created_at`, `updated_at`.
- Busca: não declarada.
- Filtros: `()`.
- Ações: nenhuma.
- Validação definitiva: formulários Django acima (`clean`, `_post_clean`, validadores de campo/model e constraints) e os mesmos hooks `save_form`, `save_model`, `save_related`, `save_formset`. Alteração de comportamento não faz parte deste pacote.

### Produtos

- Controlador: `apps.stores.admin.ProductAdmin`.
- Formulário base declarado: `apps.stores.admin.ProductAdminForm`. `get_form()` e seus wrappers de tenant/request são reutilizados.
- Campos de formulário: `category`, `sku`, `name`, `slug`, `description`, `price`, `sale_price`, `is_available`, `is_featured`, `is_vegan`, `is_spicy`, `allergens`, `calories`, `prep_time`, `weight`, `stock`, `min_order_qty`, `max_order_qty`, `primary_image`, `available_days`.
- Somente leitura: `created_at`, `updated_at`, `reserved_stock`.
- Busca: name, description, sku.
- Filtros: `(('category', <class 'django.contrib.admin.filters.RelatedOnlyFieldListFilter'>), 'is_available', 'is_featured')`.
- Ações: delete_selected, create_half_for_selected, mark_as_available, mark_as_unavailable.
- Formulário auxiliar `stores.ProductImage`: `django.forms.models.ModelForm`; campos: image, alt_text, is_primary, order. Reutiliza formset, permissões e salvamento do controlador existente.
- Validação definitiva: formulários Django acima (`clean`, `_post_clean`, validadores de campo/model e constraints) e os mesmos hooks `save_form`, `save_model`, `save_related`, `save_formset`. Alteração de comportamento não faz parte deste pacote.

### Categorias

- Controlador: `apps.stores.admin.CategoryAdmin`.
- Formulário base declarado: `apps.stores.admin.CategoryAdminForm`. `get_form()` e seus wrappers de tenant/request são reutilizados.
- Campos de formulário: `name`, `slug`, `display_order`.
- Somente leitura: nenhum.
- Busca: name.
- Filtros: `()`.
- Ações: delete_selected.
- Validação definitiva: formulários Django acima (`clean`, `_post_clean`, validadores de campo/model e constraints) e os mesmos hooks `save_form`, `save_model`, `save_related`, `save_formset`. Alteração de comportamento não faz parte deste pacote.

### Adicionais e opções

- Controlador: `apps.stores.admin.CustomizationGroupAdmin`.
- Formulário base declarado: `django.forms.models.ModelForm`. `get_form()` e seus wrappers de tenant/request são reutilizados.
- Campos de formulário: `category`, `label`, `apply_to`, `is_active`, `min_options`, `max_options`.
- Somente leitura: nenhum.
- Busca: label__name, category__name.
- Filtros: `(('category', <class 'django.contrib.admin.filters.RelatedOnlyFieldListFilter'>), 'apply_to', 'is_active')`.
- Ações: delete_selected.
- Formulário auxiliar `stores.CustomizationOption`: `django.forms.models.ModelForm`; campos: name, description, price, image, is_available. Reutiliza formset, permissões e salvamento do controlador existente.
- Validação definitiva: formulários Django acima (`clean`, `_post_clean`, validadores de campo/model e constraints) e os mesmos hooks `save_form`, `save_model`, `save_related`, `save_formset`. Alteração de comportamento não faz parte deste pacote.

### Rótulos dos adicionais

- Controlador: `apps.stores.admin.CustomizationGroupLabelAdmin`.
- Formulário base declarado: `django.forms.models.ModelForm`. `get_form()` e seus wrappers de tenant/request são reutilizados.
- Campos de formulário: `name`.
- Somente leitura: nenhum.
- Busca: name.
- Filtros: `()`.
- Ações: delete_selected.
- Validação definitiva: formulários Django acima (`clean`, `_post_clean`, validadores de campo/model e constraints) e os mesmos hooks `save_form`, `save_model`, `save_related`, `save_formset`. Alteração de comportamento não faz parte deste pacote.

### Pedidos

- Controlador: `apps.orders.admin.OrderAdmin`.
- Formulário base declarado: `django.forms.models.ModelForm`. `get_form()` e seus wrappers de tenant/request são reutilizados.
- Campos de formulário: nenhum (consulta).
- Somente leitura: `status`, `customer`, `customer_name`, `customer_phone`, `subtotal`, `delivery_fee`, `coupon_code`, `discount_amount`, `total`, `delivery_type`, `payment_flow`, `payment_method`, `payment_change_for`, `payment_confirmation`, `whatsapp_opened_at`, `created_at`, `delivery_zip_code`, `delivery_street`, `delivery_number`, `delivery_complement`, `delivery_neighborhood`, `delivery_city`, `delivery_state`, `delivery_reference`.
- Busca: id, customer_name, customer_phone, coupon_code, delivery_street, delivery_neighborhood, delivery_city.
- Filtros: `('delivery_type', 'payment_flow', 'payment_method', 'created_at', 'delivery_city', 'delivery_neighborhood')`.
- Ações: cancel_orders.
- Formulário auxiliar `orders.OrderItem`: `django.forms.models.ModelForm`; campos: . Reutiliza formset, permissões e salvamento do controlador existente.
- Validação definitiva: formulários Django acima (`clean`, `_post_clean`, validadores de campo/model e constraints) e os mesmos hooks `save_form`, `save_model`, `save_related`, `save_formset`. Alteração de comportamento não faz parte deste pacote.

### Clientes

- Controlador: `apps.customers.admin.CustomerAdmin`.
- Formulário base declarado: `django.forms.models.ModelForm`. `get_form()` e seus wrappers de tenant/request são reutilizados.
- Campos de formulário: nenhum (consulta).
- Somente leitura: `customer_name_detail`, `email_detail`, `phone`, `orders_count_detail`, `total_spent_detail`, `last_order_detail`, `created_at`, `updated_at`.
- Busca: user__username, user__first_name, user__last_name, user__email, phone.
- Filtros: `()`.
- Ações: nenhuma.
- Validação definitiva: formulários Django acima (`clean`, `_post_clean`, validadores de campo/model e constraints) e os mesmos hooks `save_form`, `save_model`, `save_related`, `save_formset`. Alteração de comportamento não faz parte deste pacote.

### Cupons e campanhas

- Controlador: `apps.coupons.admin.CouponCampaignAdmin`.
- Formulário base declarado: `apps.coupons.admin.CouponCampaignAdminForm`. `get_form()` e seus wrappers de tenant/request são reutilizados.
- Campos de formulário: `name`, `code`, `is_active`, `discount_type`, `discount_value`, `minimum_order_value`, `audience_type`, `inactive_days`, `minimum_orders`, `minimum_spent`, `starts_at`, `ends_at`, `usage_limit`, `usage_limit_per_customer`.
- Somente leitura: `created_at`, `updated_at`, `total_redemptions`, `total_discount_given`.
- Busca: name, code.
- Filtros: `('is_active', 'discount_type', 'audience_type', 'starts_at', 'ends_at')`.
- Ações: delete_selected, activate_campaigns, deactivate_campaigns.
- Formulário auxiliar `coupons.CouponAssignment`: `django.forms.models.ModelForm`; campos: customer. Reutiliza formset, permissões e salvamento do controlador existente.
- Validação definitiva: formulários Django acima (`clean`, `_post_clean`, validadores de campo/model e constraints) e os mesmos hooks `save_form`, `save_model`, `save_related`, `save_formset`. Alteração de comportamento não faz parte deste pacote.

### Utilizações de cupons

- Controlador: `apps.coupons.admin.CouponRedemptionAdmin`.
- Formulário base declarado: `django.forms.models.ModelForm`. `get_form()` e seus wrappers de tenant/request são reutilizados.
- Campos de formulário: nenhum (consulta).
- Somente leitura: `campaign`, `customer`, `order`, `discount_amount`, `redeemed_at`.
- Busca: campaign__code, campaign__name, customer__user__first_name, customer__user__last_name, customer__user__email, order__id.
- Filtros: `(('campaign', <class 'django.contrib.admin.filters.RelatedOnlyFieldListFilter'>), 'redeemed_at')`.
- Ações: nenhuma.
- Validação definitiva: formulários Django acima (`clean`, `_post_clean`, validadores de campo/model e constraints) e os mesmos hooks `save_form`, `save_model`, `save_related`, `save_formset`. Alteração de comportamento não faz parte deste pacote.

## JavaScript anterior e APIs preexistentes

- `static/js/admin/store-settings.js`: normalização de telefone, CEP/ViaCEP, horários e controles de formulário. O React assume a apresentação; validações definitivas permanecem em `admin_ux.py` e nos modelos.
- `static/js/admin/payment-account.js`: aceite das condições, dados Asaas, CEP e status persistido. Novo formulário React mostra as condições, aceite explícito, controles e status; não expõe chave técnica.
- Scripts de Django/Unfold: formsets, seletores, slug, filtros e ações. React renderiza campos nativos, formulários auxiliares, confirmação de ações, seletores múltiplos, busca e paginação.
- Script embutido do WhatsApp: leitura periódica do status e expiração visual do QR. React conserva consulta de status em 10 segundos e oculta QR após 60 segundos.
- As APIs anteriores `api/product/.../customizations/`, `api/delivery-fee/`, `api/cupons/`, `api/tenants/create/` e o JWT em `dashboard/auth/` não constituíam um CRUD administrativo completo. Foram preservadas. ViaCEP reutiliza `api/cep/:cep/`.

## Permissões e diferenças importantes

- MerchantPermission exige tenant resolvido pelo host, usuário autenticado, ativo, staff, is_tenant_admin, não superusuário e user.tenant_id igual ao tenant. As permissões de cada ModelAdmin/Inline continuam aplicadas.
- Clientes e utilizações de cupons são consulta: não foi inventado cadastro, edição ou exclusão para o lojista.
- Pedidos não podem ser criados ou excluídos pelo lojista. O cancelamento chama a ação existente e exige confirmação. Não foram acrescentados status.
- Entrega só aparece quando o modo de atendimento aceita entrega; subconta e tarifas dependem de online_payments_allowed, controlado pela plataforma.
- Autenticação JWT antiga é preservada para compatibilidade. O React usa a sessão do próprio Django, sem localStorage com tokens.
- Inlines preservam vínculos ao objeto pai, tenant e validação. IDs forjados de outra loja ou outro pai são recusados.
- Imagens, descontos, estoque, combinações meio a meio, adicionais, publicação do perfil e aceite de subconta seguem os mesmos modelos/serviços.

## Matriz de validação manual pendente em homologação

Para cada recurso da matriz: leitura com e sem registros; criar/editar/excluir somente quando permitido; obrigatórios e erros; filtros e histórico; duas lojas com IDs cruzados; mobile 390px, tablet 768px, desktop 1440px. Para inlines: inclusão, remoção, alteração e envio de ID forjado. Para integrações: sandbox Asaas, arquivos fiscais reais de homolog e QR de instância Evolution de teste. Testes locais automatizados estão em `react-migration.md`; não substituem este aceite.
