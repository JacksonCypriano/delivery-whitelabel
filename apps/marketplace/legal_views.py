"""Public information pages; never require a customer or admin session."""
from django.shortcuts import render
from django.views.decorators.http import require_safe


@require_safe
def privacy(request):
    return render(request, 'legal/privacy.html')


@require_safe
def terms(request):
    return render(request, 'legal/terms.html')
