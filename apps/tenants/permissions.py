from rest_framework.permissions import BasePermission


class IsSuperUser(BasePermission):
    message = "Apenas o superadministrador pode criar lojas."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_active and request.user.is_superuser)
