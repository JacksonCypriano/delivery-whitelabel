"""Explicit public presentation contracts; business views retain ownership checks."""
import json
import logging
import os
from pathlib import Path

import requests
from django.conf import settings
from django.contrib.messages import get_messages
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse, JsonResponse
from django.core.serializers.json import DjangoJSONEncoder
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.html import strip_tags
from django.forms import CheckboxInput, PasswordInput, Textarea

logger = logging.getLogger(__name__)
PAGES = {
    'marketplace/home.html': ('marketplace', 'Peça nas lojas da sua região', ''),
    'marketplace/for_merchants.html': ('landing', 'VemDeDelivery para lojistas', ''),
    'marketplace/marketing_seo_page.html': ('seo', 'VemDeDelivery', ''),
    'stores/catalogo.html': ('catalog', 'Cardápio', ''),
    'sales/feedback': ('feedback', 'Sua opinião e preferências', ''),
    'checkout/cart.html': ('cart', 'Meu carrinho', ''),
    'checkout/checkout.html': ('checkout', 'Finalizar pedido', ''),
    'checkout/review.html': ('review', 'Revise seu pedido', ''),
    'checkout/payment_status.html': ('payment', 'Pagamento do pedido', ''),
    'checkout/order_success.html': ('success', 'Pedido registrado', ''),
    'accounts/customer_login.html': ('login', 'Entrar na sua conta', 'Entrar'),
    'accounts/customer_register.html': ('register', 'Criar conta', 'Criar conta'),
    'accounts/customer_password_reset.html': ('password-reset', 'Recuperar senha', 'Enviar link de recuperação'),
    'accounts/customer_password_reset_done.html': ('password-reset-done', 'Confira seu e-mail', ''),
    'accounts/customer_password_reset_confirm.html': ('password-reset-confirm', 'Redefinir senha', 'Salvar nova senha'),
    'accounts/customer_password_reset_complete.html': ('password-reset-complete', 'Senha redefinida', ''),
    'accounts/customer_account.html': ('account', 'Minha conta', ''),
    'accounts/customer_addresses.html': ('addresses', 'Meus endereços', ''),
    'accounts/customer_address_form.html': ('address-form', 'Endereço', 'Salvar endereço'),
    'accounts/customer_profile.html': ('profile', 'Meus dados', 'Salvar alterações'),
    'accounts/customer_change_password.html': ('change-password', 'Alterar senha', 'Alterar senha'),
    'accounts/customer_orders.html': ('orders', 'Meus pedidos', ''),
    'accounts/customer_order_detail.html': ('order', 'Detalhes do pedido', ''),
    'accounts/customer_verify_registration.html': ('verify-registration', 'Confirmar cadastro', ''),
    'accounts/customer_verify_contact.html': ('verify-contact', 'Confirmar novo contato', ''),
    'orders/history.html': ('orders', 'Meus pedidos', ''),
    'legal/terms.html': ('terms', 'Termos de Serviço', ''),
    'legal/privacy.html': ('privacy', 'Política de Privacidade', ''),
}


def form_payload(form):
    fields = []
    for bound in form:
        field, widget = bound.field, bound.field.widget
        kind = 'checkbox' if isinstance(widget, CheckboxInput) else 'textarea' if isinstance(widget, Textarea) else getattr(widget, 'input_type', 'text')
        fields.append({
            'name': bound.html_name, 'label': str(bound.label), 'kind': kind,
            'value': '' if isinstance(widget, PasswordInput) else (bound.value() if bound.value() is not None else ''),
            'required': field.required, 'max_length': getattr(field, 'max_length', None),
            'autocomplete': widget.attrs.get('autocomplete'),
            'choices': [{'value': str(v), 'label': str(label)} for v, label in getattr(field, 'choices', [])],
            'errors': [str(e) for e in bound.errors], 'help': strip_tags(str(field.help_text)),
        })
    return {'fields': fields, 'errors': [str(e) for e in form.non_field_errors()]}


def order_payload(order):
    if order is None:
        return None
    from apps.marketplace.services import build_tenant_url
    from django.urls import reverse
    def details(item):
        combo = item.combination_details or {}
        result = []
        if combo.get('names'): result.append('Meio a meio: ' + ' / '.join(combo['names']))
        for key, prefix in [('customizations', ''), ('customizations_whole', 'Inteira: '), ('customizations_half1', '1ª metade: '), ('customizations_half2', '2ª metade: ')]:
            for row in combo.get(key, []): result.append(prefix + str(row.get('option_name', 'Opção')))
        for key, prefix in [('notes_half1', '1ª metade: '), ('notes_half2', '2ª metade: ')]:
            if combo.get(key): result.append(prefix + str(combo[key]))
        return result
    return {
        'scheduled_for': order.scheduled_for.isoformat() if order.scheduled_for else None,
        'id': order.pk, 'store_name': order.tenant.name, 'public_token': str(order.public_token),
        'created_label': timezone.localtime(order.created_at).strftime('%d/%m/%Y %H:%M'),
        'status': order.status, 'status_label': order.get_status_display(),
        'total': str(order.total), 'subtotal': str(order.subtotal), 'delivery_fee': str(order.delivery_fee),
        'discount_amount': str(order.discount_amount), 'coupon_code': order.coupon_code,
        'delivery_label': order.delivery_type_label, 'delivery_address': order.delivery_address_label,
        'payment_label': order.payment_label, 'payment_flow': order.payment_flow,
        'detail_url': reverse('customer_accounts:order-detail', args=[order.pk]),
        'repeat_url': build_tenant_url(order.tenant) + reverse('orders:repeat_order', args=[order.public_token]),
        'items': [{'id': i.pk, 'name': i.name, 'quantity': i.quantity, 'price': str(i.price), 'total': str(i.get_total_price()), 'notes': i.notes, 'details': details(i)} for i in order.items.all()],
    }


def assets():
    manifest = settings.BASE_DIR / 'static/public/.vite/manifest.json'
    if not manifest.exists():
        raise RuntimeError('Execute o build do frontend público.')
    entry = json.loads(manifest.read_text())['src/public/client.tsx']
    return {'js': '/static/public/' + entry['file'], 'css': ['/static/css/customer-brand.css'] + ['/static/public/' + css for css in entry.get('css', [])]}


def present(request, template, context):
    page, heading, submit = PAGES[template]
    user = getattr(request, 'user', AnonymousUser())
    c = context or {}
    props = {key: c[key] for key in ('orders_count', 'addresses_count', 'next', 'resend_seconds') if key in c}
    props['submit_label'] = c.get('submit_label', submit)
    if c.get('form') is not None: props['form'] = form_payload(c['form'])
    for key in ('order', 'last_order'):
        if c.get(key) is not None: props[key] = order_payload(c[key])
    if 'orders' in c: props['orders'] = [order_payload(order) for order in c['orders']]
    if c.get('page_obj') is not None:
        p = c['page_obj']
        props['pagination'] = {'page': p.number, 'previous': p.previous_page_number() if p.has_previous() else None, 'next': p.next_page_number() if p.has_next() else None}
    if 'addresses' in c:
        props['addresses'] = [{key: getattr(a, key) for key in ('id', 'label', 'street', 'number', 'complement', 'neighborhood', 'city', 'state', 'zip_code', 'reference', 'is_default')} for a in c['addresses']]
    if 'pending' in c:
        pending = c['pending']
        props['pending'] = {'channel': pending.channel, 'destination': c.get('destination') or getattr(pending, 'masked_destination', '')}
    if 'pending_changes' in c:
        props['pending_changes'] = [{'id': str(p.pk), 'label': p.get_channel_display(), 'destination': p.masked_destination, 'url': f'/conta/dados/validar/{p.pk}/'} for p in c['pending_changes']]
    if page == 'password-reset-done': props['message'] = 'Se existir uma conta com esse e-mail, você receberá as instruções para redefinir sua senha. Confira também a pasta de spam.'
    if page == 'password-reset-complete': props['message'] = 'Sua senha foi alterada com sucesso. Entre com sua nova senha.'
    if page == 'password-reset-confirm' and not c.get('validlink', True):
        props.pop('form', None)
        props['message'] = 'Link inválido ou expirado. Solicite um novo link de recuperação de senha.'
    from .storefront import commerce_props, store_payload
    if page in {'catalog', 'cart', 'checkout', 'review', 'payment', 'success'}:
        props = commerce_props(request, page, c)
    heading = c.get('title', heading)
    data = {'page': page, 'heading': heading, 'props': props, 'csrf': get_token(request),
            'assets': assets(), 'year': timezone.localdate().year,
            'home_url': getattr(settings, 'CUSTOMER_PORTAL_URL', '/') or '/',
            'user': {'authenticated': user.is_authenticated, 'name': user.get_full_name() or user.get_username() if user.is_authenticated else ''},
            'messages': [{'level': str(m.tags), 'text': str(m)} for m in get_messages(request)],
            'meta': {'title': f'{heading} | VemDeDelivery', 'robots': 'noindex,follow'}}
    if page == 'feedback':
        data['props'] = {'kind': c.get('feedback_kind'), 'done': c.get('done', False)}
    data['store'] = store_payload(request) if page not in {'landing', 'seo', 'terms', 'privacy'} else None
    if data['store']:
        data['home_url'] = '/'
    if page == 'catalog':
        data['heading'] = data['store']['name'] if data['store'] else 'Cardápio'
        data['meta'].update(title=data['heading'], robots='noindex,follow' if settings.DEBUG else 'index,follow', canonical=request.build_absolute_uri(request.path))
    if page == 'marketplace':
        from .marketplace import marketplace_props
        data['props'] = marketplace_props(request, c)
        data['meta'].update(title='VemDeDelivery — Lojas perto de você', robots='noindex,follow' if settings.DEBUG else 'index,follow', canonical=request.build_absolute_uri('/'))
    if page in {'landing', 'seo'}:
        data['props'] = c
        data['meta'] = {'title': c.get('title') or c['page']['title'], 'description': c.get('description') or c['page']['description'], 'robots': 'index, follow' if c['indexable'] else 'noindex, follow', 'canonical': c['canonical'], 'image': c['og_image'], 'schema': json.loads(c['schema_json'])}
        data['assets']['css'] = ['/static/css/for-merchants.css']
    if page in {'terms', 'privacy'}:
        data['meta']['description'] = 'Informações sobre o VemDeDelivery e a integração VemDeDelivery Backups.'
        data['meta']['robots'] = 'index,follow' if not settings.DEBUG and getattr(request, 'tenant', None) is None else 'noindex,follow'
    return data


def render_public(request, template_name, context=None, content_type=None, status=None, using=None):
    if isinstance(template_name, (tuple, list)): template_name = template_name[0]
    data = present(request, template_name, context)
    if request.headers.get('Accept') == 'application/json':
        response = JsonResponse(data, status=status or 200)
    else:
        try:
            with requests.Session() as client:
                # Internal renderer, distinct from provider/OTP requests.
                client.trust_env = False
                result = client.post(os.getenv('PUBLIC_REACT_SSR_URL', 'http://127.0.0.1:3001') + '/render', data=json.dumps(data, cls=DjangoJSONEncoder), headers={'Content-Type': 'application/json'}, timeout=(2, 8))
            result.raise_for_status()
            response = HttpResponse(result.content, content_type=content_type or 'text/html; charset=utf-8', status=status or 200)
        except (requests.RequestException, ValueError):
            logger.exception('Public React rendering unavailable')
            response = HttpResponse('Não foi possível carregar esta página. Tente novamente em instantes.', status=503)
    response['Cache-Control'] = 'private, no-store'
    response['Vary'] = 'Accept, Cookie'
    return response
