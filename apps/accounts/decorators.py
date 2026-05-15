from functools import wraps
from django.http import JsonResponse
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

def dashboard_auth_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        auth = JWTAuthentication()
        try:
            result = auth.authenticate(request)
            if result is None:
                return JsonResponse({'error': 'Token ausente'}, status=401)
            
            user, token = result

            if not user.is_tenant_admin:
                return JsonResponse({'error': 'Acesso não autorizado'}, status=403)

            if user.tenant != request.tenant:
                return JsonResponse({'error': 'Tenant inválido'}, status=403)

            request.user = user
        except (InvalidToken, TokenError):
            return JsonResponse({'error': 'Token inválido ou expirado'}, status=401)

        return view_func(request, *args, **kwargs)
    return wrapper
