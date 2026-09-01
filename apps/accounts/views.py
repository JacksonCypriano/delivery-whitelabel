import logging
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordResetConfirmView
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.rate_limit import clear_rate_limit, distinct_identifier_rate_limit_exceeded, identifier_rate_limit_exceeded, rate_limit_exceeded
from apps.customers.forms import CustomerAddressForm
from apps.customers.models import Customer, CustomerAddress
from apps.orders.models import Order
from apps.integrations.whatsapp.service import normalize_br_phone

from .forms import (
    CustomerLoginForm,
    CustomerPasswordChangeForm,
    CustomerPasswordResetForm,
    CustomerProfileForm,
    CustomerRegisterForm,
)

from .audit import login_rejected, record_event

User = get_user_model()
logger = logging.getLogger("vemdedelivery.accounts")

class DashboardLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = str(request.data.get("username") or "").strip()
        password = request.data.get("password") or ""

        if rate_limit_exceeded(request, "dashboard-login", username, limit=8, window=300):
            record_event("rate_limited", scope="dashboard", request=request, identifier=username, reason="rate_limit")
            return Response({"error": "Muitas tentativas. Aguarde alguns minutos e tente novamente."}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        user = authenticate(request=request, username=username, password=password)
        if not user:
            return Response({"error": "Credenciais inválidas"}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.is_tenant_admin or user.tenant != getattr(request, "tenant", None):
            record_event("access_denied", scope="dashboard", request=request, user_id=user.pk, reason="not_allowed")
            return Response({"error": "Acesso não autorizado"}, status=status.HTTP_403_FORBIDDEN)

        clear_rate_limit(request, "dashboard-login", username)
        refresh = RefreshToken.for_user(user)
        record_event("login_succeeded", scope="dashboard", request=request, user_id=user.pk)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
            }
        })


class DashboardLogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            token = RefreshToken(refresh_token)
            if str(token.get("user_id")) != str(request.user.pk):
                record_event("access_denied", scope="dashboard", request=request, user_id=request.user.pk, reason="not_allowed")
                return Response({'error': 'Token inválido'}, status=status.HTTP_400_BAD_REQUEST)
            token.blacklist()
            record_event("logout", scope="dashboard", request=request, user_id=request.user.pk)
            return Response({'success': True})
        except Exception:
            record_event("access_denied", scope="dashboard", request=request, reason="rejected")
            return Response({'error': 'Token inválido'}, status=status.HTTP_400_BAD_REQUEST)


class DashboardRefreshView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            token = RefreshToken(refresh_token)
            user = User.objects.filter(pk=token.get("user_id"), is_active=True).select_related("tenant").first()
            if not user or not user.is_tenant_admin or user.tenant != getattr(request, "tenant", None):
                record_event("access_denied", scope="dashboard", request=request, reason="not_allowed")
                return Response({"error": "Token inválido"}, status=status.HTTP_401_UNAUTHORIZED)
            record_event("token_refreshed", scope="dashboard", request=request, user_id=user.pk)
            return Response({"access": str(token.access_token)})
        except Exception:
            record_event("access_denied", scope="dashboard", request=request, reason="rejected")
            return Response({"error": "Token inválido"}, status=status.HTTP_400_BAD_REQUEST)

def _safe_next_url(request):
    next_url = (
        request.POST.get("next")
        or request.GET.get("next")
        or ""
    )

    # Por enquanto usamos apenas caminhos internos.
    if next_url.startswith("/") and not next_url.startswith("//"):
        return next_url

    return "/"


@sensitive_post_parameters("password1", "password2")
@never_cache
@require_http_methods(["GET", "POST"])
def customer_register(request):
    if request.user.is_authenticated:
        return redirect(_safe_next_url(request))

    if request.method == "POST":
        form = CustomerRegisterForm(request.POST)

        if rate_limit_exceeded(request, "customer-register", limit=5, window=3600):
            record_event("rate_limited", scope="registration", request=request, reason="rate_limit")
            form.add_error(None, "Muitas tentativas de cadastro. Aguarde um pouco e tente novamente.")
        elif form.is_valid():
            pending = form.save()
            request.session.cycle_key()
            request.session['pending_registration'] = str(pending.pk)
            request.session['registration_next'] = _safe_next_url(request)
            from .otp import OTPError, client_ip, send_code
            try:
                send_code(pending.pk, client_ip(request), 'email')
            except OTPError as exc:
                messages.error(request, str(exc))
            return redirect('customer_accounts:verify-registration')

    else:
        form = CustomerRegisterForm()

    return render(
        request,
        "accounts/customer_register.html",
        {
            "form": form,
            "next": request.GET.get("next", "/"),
        },
    )


@sensitive_post_parameters("password")
@never_cache
@require_http_methods(["GET", "POST"])
def customer_login(request):
    if request.user.is_authenticated:
        return redirect(_safe_next_url(request))

    if request.method == "POST":
        email = str(request.POST.get("email") or "").strip().lower()
        blocked = rate_limit_exceeded(request, "customer-login", email, limit=8, window=300)
        form = CustomerLoginForm(request.POST, request=request, authentication_blocked=blocked)
        if blocked:
            record_event("rate_limited", request=request, identifier=email, reason="rate_limit")
            form.is_valid()
        elif form.is_valid():
            clear_rate_limit(request, "customer-login", email)
            login(request, form.get_user())
            return redirect(_safe_next_url(request))
        else:
            login_rejected(request, email)

    else:
        form = CustomerLoginForm(
            request=request,
        )

    return render(
        request,
        "accounts/customer_login.html",
        {
            "form": form,
            "next": request.GET.get("next", "/"),
        },
    )


def _password_reset_domain():
    parsed = urlsplit(settings.CUSTOMER_PORTAL_URL)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("CUSTOMER_PORTAL_URL precisa conter esquema e domínio.")
    return parsed.scheme == "https", parsed.netloc


@require_http_methods(["GET", "POST"])
def customer_password_reset(request):
    if request.user.is_authenticated and hasattr(request.user, "customer_profile"):
        return redirect("customer_accounts:account")

    if request.method == "POST":
        form = CustomerPasswordResetForm(request.POST)

        if form.is_valid():
            email = form.cleaned_data["email"].strip().lower()

            ip_limited = rate_limit_exceeded(
                request,
                "customer-password-reset-ip",
                limit=10,
                window=3600,
            )
            email_limited = rate_limit_exceeded(
                request,
                "customer-password-reset-email",
                email,
                limit=5,
                window=3600,
            )

            # Sempre retorna a mesma tela para não revelar se a conta existe.
            if ip_limited or email_limited:
                record_event("rate_limited", request=request, identifier=email, reason="rate_limit")
            else:
                record_event("password_reset_requested", request=request, identifier=email)
            if not ip_limited and not email_limited:
                try:
                    use_https, domain = _password_reset_domain()
                    form.save(
                        domain_override=domain,
                        use_https=use_https,
                        request=request,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        subject_template_name="accounts/password_reset_subject.txt",
                        email_template_name="accounts/password_reset_email.txt",
                        extra_email_context={"site_name": "VemDeDelivery"},
                    )
                except Exception:
                    # Não expõe falha de SMTP ao visitante nem a existência da conta.
                    record_event("password_reset_failed", request=request, reason="delivery", identifier=email)
                    logger.error("Customer password reset email could not be sent")

            return redirect("customer_accounts:password-reset-done")

    else:
        form = CustomerPasswordResetForm()

    return render(
        request,
        "accounts/customer_password_reset.html",
        {"form": form},
    )


@require_http_methods(["GET"])
def customer_password_reset_done(request):
    return render(
        request,
        "accounts/customer_password_reset_done.html",
    )


class CustomerPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "accounts/customer_password_reset_confirm.html"
    success_url = reverse_lazy("customer_accounts:password-reset-complete")
    post_reset_login = False

    def get_user(self, uidb64):
        user = super().get_user(uidb64)

        if (
            user is None
            or not user.is_active
            or user.tenant_id is not None
            or user.is_tenant_admin
            or user.is_staff
            or user.is_superuser
            or not hasattr(user, "customer_profile")
        ):
            return None

        return user


@require_http_methods(["GET"])
def customer_password_reset_complete(request):
    return render(
        request,
        "accounts/customer_password_reset_complete.html",
    )


@require_http_methods(["POST"])
def customer_logout(request):
    logout(request)
    return redirect(_safe_next_url(request))

@login_required
def customer_account(request):
    customer = (
        Customer.objects
        .select_related("user")
        .filter(user=request.user)
        .first()
    )

    # Impede usuário administrativo de acessar a área do consumidor.
    if customer is None:
        return redirect(
            "customer_accounts:login"
        )

    orders = (
        customer.orders
        .select_related("tenant")
        .prefetch_related("items")
        .order_by("-created_at")
    )

    addresses = (
        customer.addresses
        .all()
        .order_by("-is_default", "-created_at")
    )

    orders_count = orders.count()
    addresses_count = addresses.count()

    last_order = orders.first()

    return render(
        request,
        "accounts/customer_account.html",
        {
            "customer": customer,
            "orders_count": orders_count,
            "addresses_count": addresses_count,
            "last_order": last_order,
        },
    )

def get_current_customer(request):
    return get_object_or_404(
        Customer,
        user=request.user,
    )


@login_required
def customer_addresses(request):
    customer = get_current_customer(request)

    addresses = (
        customer.addresses
        .all()
        .order_by(
            "-is_default",
            "-created_at",
        )
    )

    return render(
        request,
        "accounts/customer_addresses.html",
        {
            "customer": customer,
            "addresses": addresses,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def customer_address_create(request):
    customer = get_current_customer(request)

    if request.method == "POST":
        form = CustomerAddressForm(
            request.POST,
        )

        if form.is_valid():
            address = form.save(
                commit=False,
            )

            address.customer = customer

            # Primeiro endereço cadastrado:
            # automaticamente vira principal.
            if not customer.addresses.exists():
                address.is_default = True

            address.save()

            messages.success(
                request,
                "Endereço cadastrado com sucesso.",
            )

            return redirect(
                "customer_accounts:addresses"
            )

    else:
        form = CustomerAddressForm()

        # Se for o primeiro endereço,
        # já mostramos principal marcado.
        if not customer.addresses.exists():
            form.fields["is_default"].initial = True

    return render(
        request,
        "accounts/customer_address_form.html",
        {
            "form": form,
            "title": "Novo endereço",
            "submit_label": "Salvar endereço",
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def customer_address_edit(
    request,
    address_id,
):
    customer = get_current_customer(request)

    address = get_object_or_404(
        CustomerAddress,
        pk=address_id,
        customer=customer,
    )

    if request.method == "POST":
        form = CustomerAddressForm(
            request.POST,
            instance=address,
        )

        if form.is_valid():
            updated_address = form.save()

            # Não permitimos ficar sem nenhum endereço principal.
            if (
                not updated_address.is_default
                and not customer.addresses
                .filter(is_default=True)
                .exists()
            ):
                updated_address.is_default = True

                updated_address.save(
                    update_fields=[
                        "is_default",
                    ]
                )

            messages.success(
                request,
                "Endereço atualizado com sucesso.",
            )

            return redirect(
                "customer_accounts:addresses"
            )

    else:
        form = CustomerAddressForm(
            instance=address,
        )

    return render(
        request,
        "accounts/customer_address_form.html",
        {
            "form": form,
            "address": address,
            "title": "Editar endereço",
            "submit_label": "Salvar alterações",
        },
    )


@login_required
@require_http_methods(["POST"])
def customer_address_delete(
    request,
    address_id,
):
    customer = get_current_customer(request)

    address = get_object_or_404(
        CustomerAddress,
        pk=address_id,
        customer=customer,
    )

    was_default = address.is_default

    address.delete()

    # Se removeu o principal,
    # outro endereço vira principal.
    if was_default:
        next_address = (
            customer.addresses
            .order_by("-created_at")
            .first()
        )

        if next_address:
            next_address.is_default = True

            next_address.save(
                update_fields=[
                    "is_default",
                ]
            )

    messages.success(
        request,
        "Endereço excluído com sucesso.",
    )

    return redirect(
        "customer_accounts:addresses"
    )


@login_required
@require_http_methods(["POST"])
def customer_address_set_default(
    request,
    address_id,
):
    customer = get_current_customer(request)

    address = get_object_or_404(
        CustomerAddress,
        pk=address_id,
        customer=customer,
    )

    address.is_default = True
    address.save()

    messages.success(
        request,
        f"{address.label} definido como endereço principal.",
    )

    return redirect(
        "customer_accounts:addresses"
    )

@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def customer_profile(request):
    from .contact_otp import pending_changes
    from .contact_views import open_contact_change
    from .otp import OTPError

    customer = get_current_customer(request)

    if request.method == "POST":
        raw_phone = str(request.POST.get("phone") or "")
        try:
            normalized_phone = normalize_br_phone(raw_phone)[2:]
        except ValueError:
            normalized_phone = ""

        phone_changed = bool(normalized_phone and normalized_phone != customer.phone)
        phone_limited = False
        if phone_changed:
            user_key = str(request.user.pk)
            hourly_limited = identifier_rate_limit_exceeded("customer-profile-whatsapp-hour", user_key, limit=10, window=3600)
            distinct_limited = distinct_identifier_rate_limit_exceeded("customer-profile-whatsapp-distinct", user_key, normalized_phone, limit=5, window=900)
            phone_limited = hourly_limited or distinct_limited

        form = CustomerProfileForm(
            request.POST,
            user=request.user,
            customer=customer,
            skip_whatsapp_validation=phone_limited,
        )

        if form.is_valid():
            if phone_limited:
                record_event("rate_limited", scope="contact", request=request, user_id=request.user.pk, channel="whatsapp", reason="rate_limit")
                form.add_error("phone", "Muitas tentativas de alteração do WhatsApp. Aguarde alguns minutos e tente novamente.")
            else:
                try:
                    form.save()
                except OTPError as exc:
                    form.add_error(None, str(exc))
                else:
                    if form.pending_changes:
                        messages.info(request, "Nome e sobrenome salvos. Confirme os novos contatos para concluir a alteração.")
                        return open_contact_change(request, form.pending_changes[0])
                    messages.success(request, "Seus dados foram atualizados com sucesso.")
                    return redirect("customer_accounts:profile")

    else:
        form = CustomerProfileForm(
            user=request.user,
            customer=customer,
            initial={
                "first_name": request.user.first_name,
                "last_name": request.user.last_name,
                "email": request.user.email,
                "phone": customer.phone,
            },
        )

    return render(
        request,
        "accounts/customer_profile.html",
        {
            "customer": customer,
            "form": form,
            "pending_changes": pending_changes(request.user),
        },
    )


@sensitive_post_parameters("old_password", "new_password1", "new_password2")
@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def customer_change_password(request):
    customer = get_current_customer(request)

    if request.method == "POST":
        form = CustomerPasswordChangeForm(
            request.user,
            request.POST,
        )

        if form.is_valid():
            user = form.save()

            # Mantém a sessão ativa após trocar a senha.
            update_session_auth_hash(
                request,
                user,
            )

            messages.success(
                request,
                "Sua senha foi alterada com sucesso.",
            )

            return redirect(
                "customer_accounts:change-password"
            )

        else:
            record_event("access_denied", scope="account", request=request, user_id=request.user.pk, reason="invalid_input")

    else:
        form = CustomerPasswordChangeForm(
            request.user,
        )

    return render(
        request,
        "accounts/customer_change_password.html",
        {
            "customer": customer,
            "form": form,
        },
    )

@login_required
def customer_orders(request):
    customer = get_current_customer(request)

    orders = (
        customer.orders
        .select_related("tenant")
        .prefetch_related("items")
        .order_by("-created_at")
    )

    return render(
        request,
        "accounts/customer_orders.html",
        {
            "customer": customer,
            "orders": orders,
        },
    )


@login_required
def customer_order_detail(request, order_id):
    customer = get_current_customer(request)

    order = get_object_or_404(
        Order.objects
        .select_related("tenant", "customer")
        .prefetch_related("items"),
        pk=order_id,
        customer=customer,
    )

    return render(
        request,
        "accounts/customer_order_detail.html",
        {
            "customer": customer,
            "order": order,
        },
    )


@sensitive_post_parameters('code')
@never_cache
@require_http_methods(['GET', 'POST'])
def customer_verify_registration(request):
    from .models import PendingRegistration
    from .otp import OTPError, active, client_ip, send_code, verify_code
    from django.utils.http import url_has_allowed_host_and_scheme

    if request.user.is_authenticated:
        return redirect('customer_accounts:account')
    pending_id = request.session.get('pending_registration')
    pending = PendingRegistration.objects.filter(pk=pending_id).first() if pending_id else None
    if pending is None:
        return redirect('customer_accounts:register')
    try:
        active(pending)
    except OTPError as exc:
        request.session.pop('pending_registration', None)
        messages.error(request, str(exc))
        return redirect('customer_accounts:register')
    if request.method == 'POST':
        channel = request.POST.get('channel', '')
        try:
            if request.POST.get('action') == 'send':
                send_code(pending.pk, client_ip(request), channel)
                messages.success(request, 'Código enviado. Confira suas mensagens.')
            elif request.POST.get('action') == 'verify':
                user = verify_code(pending.pk, channel, request.POST.get('code', '').strip())
                if user:
                    next_url = request.session.pop('registration_next', '/')
                    request.session.pop('pending_registration', None)
                    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                        next_url = '/'
                    messages.success(request, 'Conta criada! E-mail e WhatsApp confirmados.')
                    return redirect(next_url)
                messages.success(request, 'E-mail confirmado. Agora confirme seu WhatsApp.')
                send_code(pending.pk, client_ip(request), 'whatsapp')
            else:
                raise OTPError('Ação inválida.')
        except OTPError as exc:
            messages.error(request, str(exc))
        return redirect('customer_accounts:verify-registration')
    destination = (pending.email[:1] + '***@' + pending.email.split('@')[-1]
                   if pending.channel == 'email' else '(**) *****-' + pending.phone[-4:])
    return render(request, 'accounts/customer_verify_registration.html', {
        'pending': pending, 'destination': destination,
    })
