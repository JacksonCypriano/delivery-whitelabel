"""Bounded pagination shared by both panels."""
from copy import copy

def page_size(request):
    try:
        size = int(request.GET.get("page_size", 10))
    except (TypeError, ValueError):
        size = 10
    return size if size in (10, 25, 50, 100) else 10

def paged_admin(admin, request):
    admin = copy(admin)
    admin.list_per_page = page_size(request)
    admin.list_max_show_all = 0
    request.GET = request.GET.copy()
    request.GET.pop("page_size", None)
    request.GET.pop("all", None)
    return admin

def paginate(queryset, request, key="page"):
    from django.core.paginator import Paginator
    return Paginator(queryset, page_size(request)).get_page(request.GET.get(key))

def metadata(page):
    return {"page": page.number, "pages": page.paginator.num_pages, "count": page.paginator.count}
