from django.utils import timezone


class ActivityScopeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = timezone.now()
        response = self.get_response(request)
        if (
            request.method in ("POST", "PUT", "PATCH", "DELETE")
            and getattr(request, "user", None)
            and request.user.is_authenticated
        ):
            from apps.core.admin import tenant_admin_allowed
            from apps.tenants.domains import is_platform_host

            tenant = getattr(request, "tenant", None)
            if tenant_admin_allowed(request) or (
                is_platform_host(request) and request.user.is_superuser
            ):
                from django.contrib.admin.models import LogEntry
                from apps.core.models import AdminActivityScope

                entries = LogEntry.objects.filter(
                    user=request.user,
                    action_time__gte=started,
                    react_scope__isnull=True,
                )
                AdminActivityScope.objects.bulk_create(
                    [
                        AdminActivityScope(entry_id=pk, tenant=tenant)
                        for pk in entries.values_list("pk", flat=True)
                    ],
                    ignore_conflicts=True,
                )
        return response
