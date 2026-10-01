from django.urls import path

from . import acquisition_views, legal_views, marketing_views, views
from .marketing_content import MARKETING_PAGES

app_name = "marketplace"

urlpatterns = [
    path("para-lojistas/", marketing_views.landing, name="for_merchants"),
    path("marketing/registrar-clique/", acquisition_views.record_whatsapp_click, name="marketing_click"),
    path("sitemap.xml", marketing_views.sitemap_index, name="sitemap"),
    # Compatibilidade com o sitemap publicado na primeira versão da landing.
    path("sitemap-lojistas.xml", marketing_views.marketing_sitemap, name="marketing_sitemap"),
    path("robots.txt", marketing_views.robots_txt, name="robots_txt"),
]

# Rotas editoriais explícitas: não existe catch-all de SEO que possa capturar o
# slug de uma loja. Cada URL indexável tem conteúdo próprio em marketing_content.
for page_key, page in MARKETING_PAGES.items():
    urlpatterns.append(
        path(
            page["path"],
            marketing_views.seo_page,
            {"page_key": page_key},
            name=page["name"],
        )
    )

urlpatterns += [
    path("privacidade/", legal_views.privacy, name="privacy"),
    path("termos/", legal_views.terms, name="terms"),
    path("", views.home, name="home"),
]
