from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.customers.forms import CustomerAddressForm
from apps.customers.models import Customer, CustomerAddress
from apps.orders.models import Order

from .forms import (
    CustomerLoginForm,
    CustomerPasswordChangeForm,
    CustomerProfileForm,
    CustomerRegisterForm,
)

User = get_user_model()

class DashboardLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return Response({'error': 'Credenciais inválidas'}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.check_password(password):
            return Response({'error': 'Credenciais inválidas'}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.is_tenant_admin:
            return Response({'error': 'Acesso não autorizado'}, status=status.HTTP_403_FORBIDDEN)

        if user.tenant != request.tenant:
            return Response({'error': 'Acesso não autorizado para este tenant'}, status=status.HTTP_403_FORBIDDEN)

        refresh = RefreshToken.for_user(user)
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
            token.blacklist()
            return Response({'success': True})
        except Exception:
            return Response({'error': 'Token inválido'}, status=status.HTTP_400_BAD_REQUEST)


class DashboardRefreshView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            token = RefreshToken(refresh_token)
            return Response({
                'access': str(token.access_token),
            })
        except Exception:
            return Response({'error': 'Token inválido'}, status=status.HTTP_400_BAD_REQUEST)

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


@require_http_methods(["GET", "POST"])
def customer_register(request):
    if request.user.is_authenticated:
        return redirect(_safe_next_url(request))

    if request.method == "POST":
        form = CustomerRegisterForm(request.POST)

        if form.is_valid():
            user = form.save()

            login(
                request,
                user,
                backend="django.contrib.auth.backends.ModelBackend",
            )

            return redirect(
                _safe_next_url(request)
            )

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


@require_http_methods(["GET", "POST"])
def customer_login(request):
    if request.user.is_authenticated:
        return redirect(_safe_next_url(request))

    if request.method == "POST":
        form = CustomerLoginForm(
            request.POST,
            request=request,
        )

        if form.is_valid():
            login(
                request,
                form.get_user(),
            )

            return redirect(
                _safe_next_url(request)
            )

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


@require_http_methods(["POST"])
def customer_logout(request):
    logout(request)

    return redirect(
        request.POST.get("next") or "/"
    )

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

@login_required
@require_http_methods(["GET", "POST"])
def customer_profile(request):
    customer = get_current_customer(request)

    if request.method == "POST":
        form = CustomerProfileForm(
            request.POST,
            user=request.user,
            customer=customer,
        )

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "Seus dados foram atualizados com sucesso.",
            )

            return redirect(
                "customer_accounts:profile"
            )

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
        },
    )


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
