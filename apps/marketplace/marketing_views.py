"""Public merchant acquisition pages.

These endpoints deliberately avoid tenant/customer data. Marketing analytics are
loaded only on the canonical public host when explicitly configured; homologation,
DEBUG and tenant subdomains receive explicit noindex protection and no GTM snippet.
"""

import json
from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.urls import reverse
from django.utils.html import escape
from django.views.decorators.http import require_safe
from django.views.decorators.csrf import ensure_csrf_cookie

from .marketing_content import MARKETING_PAGES, PRICE, grouped_pages


def _origin():
    return getattr(settings, "MARKETING_PUBLIC_URL", "https://vemdedelivery.com.br").rstrip("/")


def _indexable(request):
    return (
        not settings.DEBUG
        and request.get_host().lower() == urlsplit(_origin()).netloc.lower()
        and getattr(request, "tenant", None) is None
    )


def _absolute_static(path):
    return _origin() + static(path)


def _whatsapp_url():
    number = getattr(settings, "MARKETING_WHATSAPP", "5511964059470")
    message = (
        "Olá! Conheci o VemDeDelivery pelo site e quero contratar para minha loja. "
        "Como começamos?"
    )
    return "https://wa.me/" + number + "?" + urlencode({"text": message})


def _safe_json(data):
    return (
        json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def _schema(*, canonical, title, description, faq=(), breadcrumb=()):
    origin = _origin()
    landing_url = origin + reverse("marketplace:for_merchants")
    organization_id = origin + "/#organization"
    website_id = origin + "/#website"
    software_id = landing_url + "#software"
    webpage_id = canonical + "#webpage"

    graph = [
        {
            "@type": "Organization",
            "@id": organization_id,
            "name": "VemDeDelivery",
            "legalName": "COBRADEV SOLUTIONS",
            "url": origin + "/",
            "logo": {
                "@type": "ImageObject",
                "url": _absolute_static("images/brand/logo-vemdedelivery-512.png"),
                "width": 512,
                "height": 512,
            },
        },
        {
            "@type": "WebSite",
            "@id": website_id,
            "url": origin + "/",
            "name": "VemDeDelivery",
            "inLanguage": "pt-BR",
            "publisher": {"@id": organization_id},
        },
        {
            "@type": "SoftwareApplication",
            "@id": software_id,
            "name": "VemDeDelivery",
            "applicationCategory": "BusinessApplication",
            "operatingSystem": "Web",
            "url": landing_url,
            "description": (
                "Plataforma de catálogo e pedidos online para comércio local, com painel "
                "de gestão, atendimento e pedidos pelo WhatsApp."
            ),
            "offers": {
                "@type": "Offer",
                "price": PRICE,
                "priceCurrency": "BRL",
                "url": landing_url,
            },
            "publisher": {"@id": organization_id},
        },
        {
            "@type": "WebPage",
            "@id": webpage_id,
            "url": canonical,
            "name": title,
            "description": description,
            "inLanguage": "pt-BR",
            "isPartOf": {"@id": website_id},
            "about": {"@id": software_id},
            "primaryImageOfPage": {
                "@type": "ImageObject",
                "url": _absolute_static("images/brand/og-vemdedelivery.png"),
                "width": 1200,
                "height": 630,
            },
        },
    ]

    if breadcrumb:
        graph.append(
            {
                "@type": "BreadcrumbList",
                "@id": canonical + "#breadcrumb",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": position,
                        "name": name,
                        "item": url,
                    }
                    for position, (name, url) in enumerate(breadcrumb, start=1)
                ],
            }
        )

    if faq:
        graph.append(
            {
                "@type": "FAQPage",
                "@id": canonical + "#faq",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": question,
                        "acceptedAnswer": {"@type": "Answer", "text": answer},
                    }
                    for question, answer in faq
                ],
            }
        )

    return _safe_json({"@context": "https://schema.org", "@graph": graph})


def _common_context(request, *, canonical, title, description, faq=(), breadcrumb=()):
    indexable = _indexable(request)
    google_tag_manager_id = (
        getattr(settings, "GOOGLE_TAG_MANAGER_ID", "").strip() if indexable else ""
    )
    tracking = indexable and getattr(settings, "MARKETING_LEAD_TRACKING_ENABLED", False)
    contact = None
    if tracking:
        from .acquisition import new_contact
        contact = new_contact(request)
    return {
        "marketing_contact_token": contact["token"] if contact else "",
        "marketing_contact_reference": contact["reference"] if contact else "",
        "marketing_consent_enabled": bool(google_tag_manager_id or tracking),
        "canonical": canonical,
        "indexable": indexable,
        "google_tag_manager_id": google_tag_manager_id,
        "whatsapp": contact["url"] if contact else _whatsapp_url(),
        "demo_url": getattr(
            settings,
            "MARKETING_DEMO_URL",
            "https://demo.vemdedelivery.com.br/",
        ),
        "og_image": _absolute_static("images/brand/og-vemdedelivery.png"),
        "schema_json": _schema(
            canonical=canonical,
            title=title,
            description=description,
            faq=faq,
            breadcrumb=breadcrumb,
        ),
    }


def _protect_non_public(response, request):
    if not _indexable(request):
        response["X-Robots-Tag"] = "noindex, follow"
    elif getattr(settings, "MARKETING_LEAD_TRACKING_ENABLED", False):
        # CSRF token and signed lead reference are unique per visitor/render.
        response["Cache-Control"] = "private, no-store"
    return response


@ensure_csrf_cookie
@require_safe
def landing(request):
    origin = _origin()
    canonical = origin + reverse("marketplace:for_merchants")
    title = "Loja online, cardápio e pedidos pelo WhatsApp | VemDeDelivery"
    description = (
        "Crie sua loja, cardápio ou catálogo online, receba pedidos e conte com agente no "
        "WhatsApp. Para delivery e comércio local, por R$ 149/mês e sem comissão por pedido."
    )
    faq = (
        (
            "O que é o VemDeDelivery?",
            "É uma plataforma para comércio local ter catálogo ou cardápio online, pedidos, painel de gestão e atendimento pelo WhatsApp em um canal próprio.",
        ),
        (
            "O VemDeDelivery é só para restaurantes?",
            "Não. Alimentação é um dos focos, mas a plataforma também atende mercados, mercearias, pet shops, casas de ração, floriculturas e outros negócios locais com produtos e pedidos.",
        ),
        (
            "Existe comissão sobre cada pedido?",
            "O VemDeDelivery não cobra comissão percentual sobre os pedidos. Serviços de pagamento online, quando utilizados, podem ter tarifas próprias do provedor.",
        ),
        (
            "O agente do WhatsApp consegue montar pedidos?",
            "Sim. O fluxo pode responder dúvidas com base nos dados da loja, trabalhar com carrinho, opções, entrega ou retirada e encaminhar para atendimento humano quando necessário.",
        ),
        (
            "Posso configurar a loja sozinho?",
            "Sim. O lojista gerencia a operação pelo painel. Se preferir, também existem serviços opcionais de implantação e cadastro cobrados à parte da assinatura.",
        ),
    )
    context = _common_context(
        request,
        canonical=canonical,
        title=title,
        description=description,
        faq=faq,
        breadcrumb=(("VemDeDelivery", origin + "/"), ("Para lojistas", canonical)),
    )
    page_groups = []
    for group_name, pages in grouped_pages():
        page_groups.append(
            (
                group_name,
                [
                    {**page, "url": reverse("marketplace:" + page["name"])}
                    for _key, page in pages
                ],
            )
        )

    context.update(
        {
            "title": title,
            "description": description,
            "landing_faq": faq,
            "page_groups": page_groups,
        }
    )
    response = render(request, "marketplace/for_merchants.html", context)
    return _protect_non_public(response, request)


@ensure_csrf_cookie
@require_safe
def seo_page(request, page_key):
    page = MARKETING_PAGES.get(page_key)
    if page is None:
        raise Http404

    origin = _origin()
    canonical = origin + reverse("marketplace:" + page["name"])
    landing_url = origin + reverse("marketplace:for_merchants")
    context = _common_context(
        request,
        canonical=canonical,
        title=page["title"],
        description=page["description"],
        faq=page["faq"],
        breadcrumb=(("VemDeDelivery", origin + "/"), ("Para lojistas", landing_url), (page["eyebrow"].title(), canonical)),
    )

    related = []
    for key in page["related"]:
        target = MARKETING_PAGES.get(key)
        if target:
            related.append(
                {
                    "title": target["title"].split(" | ")[0],
                    "description": target["description"],
                    "url": reverse("marketplace:" + target["name"]),
                }
            )

    context.update(
        {
            "page": page,
            "related_pages": related,
            "landing_url": reverse("marketplace:for_merchants"),
        }
    )
    response = render(request, "marketplace/marketing_seo_page.html", context)
    return _protect_non_public(response, request)


def _sitemap_urls():
    urls = [_origin() + reverse("marketplace:for_merchants")]
    urls.extend(
        _origin() + reverse("marketplace:" + page["name"])
        for page in MARKETING_PAGES.values()
    )
    return urls


@require_safe
def sitemap_index(request):
    if not _indexable(request):
        response = HttpResponse(status=404)
        response["X-Robots-Tag"] = "noindex"
        return response

    marketing_url = escape(_origin() + reverse("marketplace:marketing_sitemap"))
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f'<sitemap><loc>{marketing_url}</loc></sitemap>'
        '</sitemapindex>'
    )
    return HttpResponse(body, content_type="application/xml")


@require_safe
def marketing_sitemap(request):
    if not _indexable(request):
        response = HttpResponse(status=404)
        response["X-Robots-Tag"] = "noindex"
        return response

    body = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for url in _sitemap_urls():
        body.append(f"<url><loc>{escape(url)}</loc></url>")
    body.append("</urlset>")
    return HttpResponse("".join(body), content_type="application/xml")


@require_safe
def robots_txt(request):
    if not _indexable(request):
        return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain; charset=utf-8")

    sitemap = _origin() + reverse("marketplace:sitemap")
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /superadmin/",
        "Disallow: /dashboard/",
        "Disallow: /conta/",
        "Disallow: /checkout/",
        "Disallow: /api/",
        f"Sitemap: {sitemap}",
        "",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")
