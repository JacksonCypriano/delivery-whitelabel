from dataclasses import dataclass, field
from decimal import Decimal
from urllib.parse import urlencode
import re
import unicodedata
from difflib import SequenceMatcher

from django.utils import timezone

from apps.marketplace.services import build_tenant_url
from apps.stores.models import CustomizationGroup, CustomizationOption, Product
from apps.tenants.models import DeliveryZone


STOPWORDS = {
    "a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "da", "do",
    "das", "dos", "e", "em", "no", "na", "nos", "nas", "para", "por", "com",
    "tem", "temos", "ter", "voces", "voce", "qual", "quais", "quanto",
    "quantos", "valor", "preco", "me", "mostra", "mostrar", "algum", "alguma",
    "favor", "ai", "aqui", "queria", "quero", "pode", "poderia", "pra", "pro",
}

# Abreviações e escrita informal frequentes no WhatsApp. O objetivo não é "corrigir"
# a mensagem exibida ao cliente; é somente criar uma forma canônica para interpretar
# a intenção sem depender do LLM.
WHATSAPP_ABBREVIATIONS = {
    # pronomes / conversa
    "vc": "voce", "vce": "voce", "vç": "voce", "vcs": "voces",
    "vceis": "voces", "ceis": "voces", "ces": "voces",
    "q": "que", "qq": "qualquer", "ql": "qual", "qais": "quais",
    "qto": "quanto", "qnt": "quanto", "qt": "quanto", "qnto": "quanto",
    "qnts": "quantos", "qntos": "quantos", "qtd": "quantidade",
    "pq": "porque", "pqe": "porque", "pque": "porque", "pk": "porque",
    "tb": "tambem", "tbm": "tambem", "tmb": "tambem", "tbn": "tambem",
    "pf": "favor", "pfv": "favor", "pfvr": "favor", "pfr": "favor",
    "pls": "favor", "obg": "obrigado", "obgd": "obrigado",
    "obgdo": "obrigado", "vlw": "valeu", "flw": "falou", "blz": "beleza",
    "msg": "mensagem", "msgs": "mensagens", "resp": "resposta",
    "cmg": "comigo", "ctg": "contigo", "qnd": "quando", "qndo": "quando",
    "msm": "mesmo", "mto": "muito", "mt": "muito", "pouq": "pouco",
    "aq": "aqui", "aki": "aqui", "dnd": "de nada",
    "oii": "oi", "oiii": "oi", "olaa": "ola", "olaaa": "ola",
    "eae": "eai", "opa": "oi",

    # tempo / localização
    "hj": "hoje", "hje": "hoje", "amnh": "amanha", "amnha": "amanha",
    "dps": "depois", "agr": "agora", "hrs": "horario", "hr": "horario",
    "end": "endereco", "ender": "endereco", "loc": "localizacao",
    "kd": "cade", "ond": "onde", "fika": "fica", "fikam": "ficam",

    # comércio / delivery
    "tm": "tem", "ta": "esta", "tah": "esta", "tá": "esta",
    "preç": "preco", "vlr": "valor", "vl": "valor",
    "frt": "frete", "entrg": "entrega", "entg": "entrega",
    "tx": "taxa", "txa": "taxa",
    "pgto": "pagamento", "pagto": "pagamento", "pgt": "pagamento",
    "cred": "credito", "deb": "debito", "din": "dinheiro",
    "piks": "pix", "pics": "pix", "piz": "pix",
    "refri": "bebida", "refris": "bebida", "ref": "bebida",
    "card": "cardapio", "cardap": "cardapio", "prod": "produto",
    "prods": "produtos", "adic": "adicional", "add": "adicional",
    "adds": "adicionais", "promo": "promocao", "promos": "promocao",
    "ingr": "ingrediente", "ingred": "ingrediente", "ingrs": "ingredientes",
    "veg": "vegano", "cal": "caloria", "kcal": "caloria",
    "refrig": "bebida", "refriger": "bebida",
    "hamb": "hamburguer", "burguer": "hamburguer", "burger": "hamburguer",
    "burgers": "hamburguer", "burguers": "hamburguer",

    # negação / confirmação comuns
    "naum": "nao", "num": "nao", "nn": "nao", "n": "nao",
    "ss": "sim", "s": "sim",
}

# Equivalências semânticas do domínio. Elas aproximam a pergunta do cadastro, mas
# nunca criam um produto ou uma informação que não exista no tenant.
TERM_ALIASES = {
    "burger": "hamburguer",
    "burguer": "hamburguer",
    "burgers": "hamburguer",
    "burguers": "hamburguer",
    "hamburgueres": "hamburguer",
    "lanche": "hamburguer",
    "lanches": "hamburguer",
    "refri": "bebida",
    "refris": "bebida",
    "refrigerante": "bebida",
    "refrigerantes": "bebida",
    "bebidas": "bebida",
    "porcoes": "porcao",
    "combos": "combo",
    "sobremesas": "sobremesa",
    "pizzas": "pizza",
}

GENERIC_PRODUCT_TERMS = {
    "produto", "item", "cardapio", "hamburguer", "bebida", "pizza",
    "porcao", "combo", "sobremesa", "lanche", "refrigerante",
}


def _strip_accents(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in value if not unicodedata.combining(ch))


def normalize(value):
    value = _strip_accents(value).lower()
    value = re.sub(r"[^a-z0-9]+", " ", value).strip()
    raw_tokens = re.sub(r"\s+", " ", value).split()
    expanded = [WHATSAPP_ABBREVIATIONS.get(token, token) for token in raw_tokens]
    return " ".join(expanded)


def brl(value):
    try:
        number = Decimal(value)
    except Exception:
        number = Decimal("0")
    return f"R$ {number:.2f}".replace(".", ",")


def _term_variants(token):
    token = TERM_ALIASES.get(token, token)
    result = {token}
    if len(token) >= 5 and token.endswith("s"):
        result.add(token[:-1])
    if len(token) >= 6 and token.endswith("es"):
        result.add(token[:-2])
    if len(token) >= 7 and token.endswith("oes"):
        result.add(token[:-3] + "ao")
    return {TERM_ALIASES.get(item, item) for item in result if len(item) >= 2}


def _tokens(value, *, keep_stopwords=False):
    result = set()
    for token in normalize(value).split():
        if len(token) < 2:
            continue
        variants = _term_variants(token)
        if keep_stopwords or token not in STOPWORDS:
            result.update(variants)
    return result


def _similarity(left, right):
    left = TERM_ALIASES.get(left, left)
    right = TERM_ALIASES.get(right, right)
    if left == right:
        return 1.0
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _fuzzy_threshold(left, right):
    size = min(len(left), len(right))
    if size <= 2:
        return 1.0
    if size == 3:
        return 0.84
    if size == 4:
        return 0.84
    if size <= 6:
        return 0.79
    return 0.75


def _tokens_match(left, right):
    left = TERM_ALIASES.get(left, left)
    right = TERM_ALIASES.get(right, right)
    return _similarity(left, right) >= _fuzzy_threshold(left, right)


def _phrase_matches(question, phrase):
    q_tokens = normalize(question).split()
    p_tokens = normalize(phrase).split()
    if not p_tokens:
        return False
    if len(p_tokens) == 1:
        target = p_tokens[0]
        return any(_tokens_match(token, target) for token in q_tokens)
    if len(q_tokens) < len(p_tokens):
        return False
    for index in range(len(q_tokens) - len(p_tokens) + 1):
        window = q_tokens[index:index + len(p_tokens)]
        if all(_tokens_match(actual, expected) for actual, expected in zip(window, p_tokens)):
            return True
    return False


def _has_any(question, terms):
    q = normalize(question)
    for term in terms:
        normalized = normalize(term)
        if normalized and normalized in q:
            return True
        if _phrase_matches(q, normalized):
            return True
    return False


def _best_token_similarity(query_tokens, target):
    return max((_similarity(token, target) for token in query_tokens), default=0.0)


def _matched_target_tokens(query_tokens, target_tokens):
    return {
        target
        for target in target_tokens
        if any(_tokens_match(query, target) for query in query_tokens)
    }


def store_address(tenant):
    first = ", ".join(
        part for part in (tenant.pickup_address, tenant.pickup_number) if part
    )
    if tenant.pickup_complement:
        first = f"{first} - {tenant.pickup_complement}" if first else tenant.pickup_complement
    second = " - ".join(
        part for part in (tenant.pickup_neighborhood, tenant.pickup_city) if part
    )
    parts = [part for part in (first, second) if part]
    if tenant.pickup_zip_code:
        parts.append(f"CEP {tenant.pickup_zip_code}")
    return " · ".join(parts)


def hours_text(tenant):
    rows = list(tenant.business_hours.all().order_by("weekday", "opening_time"))
    labels = dict(rows[0].WEEKDAYS) if rows else {
        0: "Segunda-feira", 1: "Terça-feira", 2: "Quarta-feira",
        3: "Quinta-feira", 4: "Sexta-feira", 5: "Sábado", 6: "Domingo",
    }
    grouped = {i: [] for i in range(7)}
    for row in rows:
        if not row.is_closed and row.opening_time and row.closing_time:
            grouped[row.weekday].append(
                f"{row.opening_time:%H:%M} às {row.closing_time:%H:%M}"
            )
    return "; ".join(
        f"{labels[weekday]}: {', '.join(intervals) if intervals else 'fechado'}"
        for weekday, intervals in grouped.items()
    )


def _hours_rows_for_day(tenant, weekday):
    return list(
        tenant.business_hours.filter(weekday=weekday).order_by("opening_time")
    )


def _target_weekday(question):
    q = normalize(question)
    today = timezone.localdate().weekday()
    if "amanha" in q:
        return (today + 1) % 7, "Amanhã"
    if "hoje" in q:
        return today, "Hoje"
    names = {
        0: ("segunda", "segunda feira"),
        1: ("terca", "terca feira"),
        2: ("quarta", "quarta feira"),
        3: ("quinta", "quinta feira"),
        4: ("sexta", "sexta feira"),
        5: ("sabado",),
        6: ("domingo",),
    }
    labels = {
        0: "Na segunda-feira", 1: "Na terça-feira", 2: "Na quarta-feira",
        3: "Na quinta-feira", 4: "Na sexta-feira", 5: "No sábado", 6: "No domingo",
    }
    for weekday, aliases in names.items():
        if any(alias in q for alias in aliases):
            return weekday, labels[weekday]
    return None, ""


def _specific_hours_answer(tenant, question):
    weekday, prefix = _target_weekday(question)
    q = normalize(question)
    if weekday is None and any(word in q for word in ("agora", "aberto agora", "aberta agora")):
        return (
            "A loja está aberta agora 😊" if tenant.is_open_now()
            else "A loja está fechada agora 😕"
        )
    if weekday is None:
        return None

    rows = [
        row for row in _hours_rows_for_day(tenant, weekday)
        if not row.is_closed and row.opening_time and row.closing_time
    ]
    if not rows:
        return f"{prefix}, a loja está fechada 😕"

    first = rows[0].opening_time.strftime("%H:%M")
    last = rows[-1].closing_time.strftime("%H:%M")
    if _has_any(question, ("fecha", "fecham")):
        return f"{prefix}, fechamos às *{last}* 🕒"
    if _has_any(question, ("abre", "abrem")):
        return f"{prefix}, abrimos às *{first}* 🕒"
    intervals = ", ".join(
        f"{row.opening_time:%H:%M} às {row.closing_time:%H:%M}" for row in rows
    )
    return f"{prefix}, funcionamos das *{intervals}* 🕒"


def payment_text(tenant):
    # As formas presenciais fazem parte do checkout padrão. O texto respeita o
    # modo de atendimento real da loja para não prometer retirada/entrega que
    # o tenant não oferece.
    if tenant.accepts_delivery and tenant.accepts_pickup:
        fulfillment = "na entrega ou retirada"
    elif tenant.accepts_delivery:
        fulfillment = "na entrega"
    else:
        fulfillment = "na retirada"

    parts = [
        f"{fulfillment.capitalize()}: Pix, cartão de crédito, cartão de débito ou dinheiro."
    ]

    # `online_payments_allowed` sozinho significa apenas que o VemDeDelivery
    # liberou a solicitação da subconta. Só anunciamos pagamento online quando
    # o checkout está efetivamente disponível para o cliente (subconta pronta,
    # aceita e aprovada), usando a mesma regra do checkout da aplicação.
    from apps.billing.online import online_payment_available

    if online_payment_available(tenant):
        parts.append("Online: Pix ou cartão de crédito pelo checkout da loja.")

    return "\n".join(parts)


def find_delivery_zone(tenant, question):
    normalized_question = normalize(question)
    zones = list(
        DeliveryZone.objects.filter(tenant=tenant, is_active=True).order_by("city", "neighborhood")
    )
    best = None
    best_score = 0
    question_tokens = _tokens(question)
    for zone in zones:
        neighborhood = normalize(zone.neighborhood)
        city = normalize(zone.city)
        zone_tokens = _tokens(f"{zone.neighborhood} {zone.city}")

        if neighborhood and neighborhood in normalized_question:
            score = 130 + len(neighborhood)
        else:
            matched = _matched_target_tokens(question_tokens, zone_tokens)
            score = len(matched) * 18
            # Nomes de bairro com erro de digitação ainda podem ser reconhecidos, mas
            # exigem pelo menos um token suficientemente parecido.
            for target in zone_tokens:
                similarity = _best_token_similarity(question_tokens, target)
                if similarity >= _fuzzy_threshold(target, target):
                    score += int(similarity * 12)
            if city and city in normalized_question:
                score += 5

        if score > best_score:
            best = zone
            best_score = score
    return best if best_score >= 18 else None


def _product_available_today(product):
    if not product.is_available:
        return False
    if product.stock is not None and product.stock <= 0:
        return False
    days = product.available_days or []
    normalized_days = set()
    for day in days:
        try:
            normalized_days.add(int(day))
        except (TypeError, ValueError):
            continue
    return not normalized_days or timezone.localdate().weekday() in normalized_days


def _product_request_kind(question):
    if _has_any(question, ("link", "manda o link", "me manda", "me envia", "abrir produto")):
        return "link"
    if _has_any(question, ("o que vem", "ingrediente", "ingredientes", "descricao", "composicao", "leva o que", "vem o que")):
        return "description"
    if _has_any(question, ("adicional", "adicionais", "extra", "extras", "acrescimo", "complemento", "molho", "molhos", "borda", "bordas")):
        return "customization"
    if _has_any(question, ("vegano", "vegana", "picante", "apimentado", "apimentada", "alergeno", "alergenos", "alergia", "gluten", "lactose", "caloria", "calorias", "peso", "gramas", "tempo de preparo", "preparo")):
        return "details"
    if _has_any(question, ("quanto custa", "preco", "valor", "quanto e", "custa", "custo")):
        return "price"
    if _has_any(question, ("quais", "opcoes", "mostra", "listar", "lista")):
        return "list"
    return "availability"


def _rank_products(tenant, question, *, available_only=True):
    products = list(
        Product.objects.filter(tenant=tenant)
        .select_related("category")
        .order_by("name")[:300]
    )
    qnorm = normalize(question)
    qtokens = _tokens(question)
    ranked = []

    for product in products:
        if available_only and not _product_available_today(product):
            continue

        name_norm = normalize(product.name)
        category_name = product.category.name if product.category_id else ""
        name_tokens = _tokens(product.name)
        category_tokens = _tokens(category_name)
        description_tokens = _tokens(product.description or "")

        matched_name = _matched_target_tokens(qtokens, name_tokens)
        matched_category = _matched_target_tokens(qtokens, category_tokens)
        matched_description = _matched_target_tokens(qtokens, description_tokens)

        generic_tokens = category_tokens | GENERIC_PRODUCT_TERMS
        specific_matches = {
            token for token in matched_name
            if token not in generic_tokens and token not in GENERIC_PRODUCT_TERMS
        }

        score = 0.0
        exact_name = bool(name_norm and name_norm in qnorm)
        if exact_name:
            score = max(score, 260 + len(name_norm))

        if matched_name:
            name_coverage = len(matched_name) / max(1, len(name_tokens))
            score = max(score, 70 + name_coverage * 110)
            score += len(specific_matches) * 65

        if category_tokens and matched_category:
            category_coverage = len(matched_category) / max(1, len(category_tokens))
            score = max(score, 75 + category_coverage * 70)

        if matched_description:
            score = max(score, min(42, len(matched_description) * 12))

        # Fuzzy adicional para erros de digitação em tokens distintivos, como
        # "hanburguer", "bacom", "cocacola" ou "bebids".
        for target in name_tokens:
            best_similarity = _best_token_similarity(qtokens, target)
            if best_similarity >= _fuzzy_threshold(target, target):
                score += best_similarity * (38 if target in generic_tokens else 58)
        for target in category_tokens:
            best_similarity = _best_token_similarity(qtokens, target)
            if best_similarity >= _fuzzy_threshold(target, target):
                score += best_similarity * 26

        if score >= 55:
            ranked.append(
                {
                    "score": score,
                    "specificity": len(specific_matches),
                    "exact_name": exact_name,
                    "product": product,
                }
            )

    ranked.sort(
        key=lambda item: (
            -item["score"],
            -item["specificity"],
            item["product"].name.casefold(),
        )
    )
    return ranked


def find_products(tenant, question, limit=5):
    ranked = _rank_products(tenant, question)
    if not ranked:
        return []

    kind = _product_request_kind(question)
    top = ranked[0]
    second = ranked[1] if len(ranked) > 1 else None

    # Preço/link de um produto com termo distintivo deve responder só aquele item.
    # Também restringimos quando o nome completo foi citado ou o primeiro resultado
    # está claramente à frente do segundo.
    second_specificity = second["specificity"] if second else -1
    clearly_specific = (
        top["exact_name"]
        or second is None
        or top["specificity"] > second_specificity
        or top["score"] >= second["score"] + 55
    )
    if kind in {"price", "link", "description", "customization", "details"} and clearly_specific:
        return [top["product"]]

    # "Tem hambúrguer Bacon?" também é consulta de produto específico, enquanto
    # "Tem hambúrguer?" continua listando opções da categoria.
    if kind == "availability" and top["specificity"] > 0:
        if second is None or top["score"] >= second["score"] + 35:
            return [top["product"]]

    return [item["product"] for item in ranked[:limit]]


def catalog_url(tenant):
    return build_tenant_url(tenant)


def product_url(tenant, product):
    base = build_tenant_url(tenant).rstrip("/")
    query = urlencode({"source": "whatsapp-agent"})
    return f"{base}/produto/{product.slug}/?{query}"


def product_facts(tenant, products):
    facts = []
    for product in products:
        price = product.effective_price
        promo = product.sale_price is not None and product.sale_price < product.price
        text = f"{product.name}: {brl(price)}"
        if promo:
            text += f" (de {brl(product.price)})"
        if product.description:
            text += f" — {product.description[:180]}"
        text += f". Link direto: {product_url(tenant, product)}"
        facts.append(text)
    return facts


def _product_list_fallback(tenant, products, request_kind="availability"):
    visible = products[:3]
    intro = "Temos estas opções 😊" if request_kind == "list" else "Temos sim! 😊"
    blocks = [intro]
    for product in visible:
        emoji = " 🌶️" if getattr(product, "is_spicy", False) else ""
        blocks.append(
            f"*{product.name}* — {brl(product.effective_price)}{emoji}\n"
            f"👉 {product_url(tenant, product)}"
        )
    if len(products) > len(visible):
        blocks.append(
            f"Quer ver mais opções? 🍔\n👉 {catalog_url(tenant)}"
        )
    return "\n\n".join(blocks)


def _single_product_fallback(tenant, product, request_kind="availability"):
    url = product_url(tenant, product)
    emoji = " 🌶️" if getattr(product, "is_spicy", False) else ""

    if request_kind == "link":
        return (
            f"Claro! 😊\n\n"
            f"Aqui está o *{product.name}*{emoji}:\n"
            f"👉 {url}"
        )

    if request_kind == "price":
        return (
            f"O *{product.name}* custa *{brl(product.effective_price)}*{emoji}\n\n"
            f"Quer escolher os adicionais e colocar no carrinho?\n"
            f"👉 {url}"
        )

    return (
        f"Temos sim! 😊\n\n"
        f"*{product.name}* — {brl(product.effective_price)}{emoji}\n"
        f"👉 {url}"
    )


def _context_products(tenant, context):
    ids = context.get("product_ids") if isinstance(context, dict) else None
    if not isinstance(ids, list) or not ids:
        return []
    products_by_id = {
        product.pk: product
        for product in Product.objects.filter(
            tenant=tenant, pk__in=ids, is_available=True
        ).select_related("category")
        if _product_available_today(product)
    }
    return [products_by_id[pk] for pk in ids if pk in products_by_id]




def _specific_product(tenant, question, context=None, *, include_unavailable=False):
    ranked = _rank_products(tenant, question, available_only=not include_unavailable)
    if ranked:
        top = ranked[0]
        second = ranked[1] if len(ranked) > 1 else None
        if (
            top["exact_name"]
            or top["specificity"] > 0
            or second is None
            or top["score"] >= second["score"] + 55
        ):
            return top["product"]
    previous = _context_products(tenant, context or {})
    return previous[0] if len(previous) == 1 else None


def _unavailable_product(tenant, question):
    ranked = _rank_products(tenant, question, available_only=False)
    for item in ranked[:4]:
        product = item["product"]
        if _product_available_today(product):
            continue
        # Require strong evidence before saying an unavailable product exists.
        if item["exact_name"] or item["specificity"] > 0:
            return product
    return None


def _promotion_price(product):
    if not product.has_discount:
        return brl(product.effective_price)
    return f"~{brl(product.price)}~ → *{brl(product.effective_price)}*"


def _active_public_coupons(tenant):
    from django.db.models import Q
    from apps.coupons.models import AudienceType, CouponCampaign

    now = timezone.now()
    rows = (
        CouponCampaign.objects.filter(
            tenant=tenant,
            is_active=True,
            audience_type=AudienceType.ALL,
            starts_at__lte=now,
        )
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
        .order_by("ends_at", "pk")[:30]
    )
    result = []
    for campaign in rows:
        if (
            campaign.usage_limit is not None
            and campaign.redemptions.count() >= campaign.usage_limit
        ):
            continue
        result.append(campaign)
    return result


def _coupon_description(campaign):
    from apps.coupons.models import DiscountType

    if campaign.discount_type == DiscountType.PERCENTAGE:
        pct = format(campaign.discount_value.normalize(), "f")
        discount = f"{pct}% de desconto"
    elif campaign.discount_type == DiscountType.FIXED_AMOUNT:
        discount = f"{brl(campaign.discount_value)} de desconto"
    elif campaign.discount_type == DiscountType.FREE_DELIVERY:
        discount = "frete grátis"
    else:
        discount = "desconto"
    minimum = ""
    if campaign.minimum_order_value and campaign.minimum_order_value > 0:
        minimum = f" em pedidos a partir de {brl(campaign.minimum_order_value)}"
    return f"*{campaign.code}* — {discount}{minimum}"


def _promotions_answer(tenant):
    products = [
        p for p in Product.objects.filter(tenant=tenant, is_available=True)
        .select_related("category").order_by("name")[:300]
        if _product_available_today(p) and p.has_discount
    ]
    coupons = _active_public_coupons(tenant)
    if not products and not coupons:
        return KnowledgeAnswer(
            "promotion",
            ("Não há promoções de produto nem cupons públicos ativos neste momento.",),
            "No momento não encontrei promoções públicas ativas no cadastro da loja 😊",
            context={"intent": "promotion"},
        )
    blocks = ["Temos estas ofertas ativas 🔥"]
    facts = []
    for product in products[:3]:
        blocks.append(
            f"*{product.name}* — {_promotion_price(product)}\n"
            f"👉 {product_url(tenant, product)}"
        )
        facts.append(
            f"{product.name}: de {brl(product.price)} por {brl(product.effective_price)}. "
            f"Link direto: {product_url(tenant, product)}"
        )
    if coupons:
        coupon_lines = [_coupon_description(c) for c in coupons[:3]]
        blocks.append("Cupons públicos disponíveis:\n" + "\n".join(coupon_lines))
        facts.extend(f"Cupom público ativo: {_coupon_description(c)}" for c in coupons[:3])
    return KnowledgeAnswer(
        "promotion", tuple(facts), "\n\n".join(blocks), context={"intent": "promotion"}
    )


def _fulfillment_answer(tenant, question):
    asks_pickup = _has_any(
        question,
        ("posso retirar", "faz retirada", "fazem retirada", "tem retirada", "retirar pedido", "buscar pedido", "posso buscar", "onde retiro", "onde busco", "retirada no local", "retirar ai"),
    )
    asks_delivery = _has_any(
        question,
        ("faz entrega", "fazem entrega", "tem entrega", "voces entregam", "vocês entregam", "entrega em casa", "trabalha com entrega"),
    )
    if asks_pickup:
        if not tenant.accepts_pickup:
            return KnowledgeAnswer(
                "fulfillment",
                ("A loja não oferece retirada; atende somente por entrega.",),
                "No momento trabalhamos somente com *entrega* 🚚 e não oferecemos retirada no local.",
                context={"intent": "fulfillment"},
            )
        address = store_address(tenant)
        suffix = f"\n\nA retirada é em *{address}* 📍" if address else ""
        return KnowledgeAnswer(
            "fulfillment",
            ("A loja oferece retirada no local.", f"Endereço: {address}." if address else "Endereço ainda não cadastrado."),
            f"Pode retirar sim 😊{suffix}",
            context={"intent": "fulfillment"},
        )
    if asks_delivery:
        if not tenant.accepts_delivery:
            return KnowledgeAnswer(
                "fulfillment",
                ("A loja não oferece entrega; atende somente por retirada.",),
                "No momento trabalhamos somente com *retirada no local* 📍 e não fazemos entrega.",
                context={"intent": "fulfillment"},
            )
        return KnowledgeAnswer(
            "fulfillment",
            ("A loja oferece entrega.",),
            "Fazemos entrega sim 🚚\n\nMe diga a *cidade* e o *bairro* que eu consulto a taxa para você.",
            context={"intent": "delivery"},
        )
    return None


def _delivery_areas_question(question):
    return _has_any(
        question,
        (
            "quais bairros", "bairros atendidos", "bairros voces entregam",
            "onde entrega", "onde voces entregam", "areas de entrega",
            "regioes de entrega", "quais regioes", "onde faz entrega",
        ),
    )


def _delivery_areas_answer(tenant, question):
    if not tenant.accepts_delivery:
        return KnowledgeAnswer(
            "delivery_areas",
            ("A loja não oferece entrega.",),
            "No momento a loja trabalha somente com retirada no local 📍",
            context={"intent": "delivery_areas"},
        )
    zones = list(
        DeliveryZone.objects.filter(tenant=tenant, is_active=True)
        .order_by("city", "neighborhood")
    )
    if not zones:
        return KnowledgeAnswer(
            "delivery_areas",
            ("Não há zonas de entrega ativas cadastradas.",),
            "Ainda não encontrei bairros de entrega cadastrados para esta loja 😕",
            context={"intent": "delivery_areas"},
        )
    explicit_city = _delivery_city(tenant, question)
    cities = sorted({z.city for z in zones}, key=str.casefold)
    if not explicit_city and len(cities) > 1:
        city_list = ", ".join(cities[:8])
        return KnowledgeAnswer(
            "delivery_areas",
            tuple(f"Cidade atendida: {city}." for city in cities),
            f"Atendemos mais de uma cidade 🚚\n\n*{city_list}*\n\nQual cidade você quer consultar?",
            context={"intent": "delivery_areas"},
        )
    city = explicit_city or cities[0]
    selected = [z for z in zones if normalize(z.city) == normalize(city)]
    visible = selected[:12]
    lines = [f"• *{z.neighborhood}* — {brl(z.fee)}" for z in visible]
    if len(selected) > len(visible):
        lines.append(f"• e mais {len(selected) - len(visible)} bairro(s)")
    return KnowledgeAnswer(
        "delivery_areas",
        tuple(f"{z.neighborhood}, {z.city}: {brl(z.fee)}" for z in selected),
        f"Em *{city}*, entregamos nestes bairros 🚚\n\n" + "\n".join(lines),
        context={"intent": "delivery_areas", "city": city},
    )


def _product_description_answer(tenant, product):
    if product.description.strip():
        text = product.description.strip()
        return KnowledgeAnswer(
            "product_description",
            (f"Descrição de {product.name}: {text}", f"Link direto: {product_url(tenant, product)}"),
            f"O *{product.name}* vem assim 😊\n\n{text}\n\n👉 {product_url(tenant, product)}",
            context={"intent": "product", "product_ids": [product.pk]},
        )
    return KnowledgeAnswer(
        "product_description",
        (f"{product.name} não possui descrição cadastrada.", f"Link direto: {product_url(tenant, product)}"),
        f"A loja ainda não cadastrou os ingredientes/descrição do *{product.name}* 😕\n\n👉 {product_url(tenant, product)}",
        context={"intent": "product", "product_ids": [product.pk]},
    )


def _customization_groups(product):
    return list(
        CustomizationGroup.objects.filter(
            tenant=product.tenant, category=product.category, is_active=True
        )
        .select_related("label")
        .prefetch_related("options")
        .order_by("pk")
    )


def _find_customization_options(tenant, question, product=None):
    qs = CustomizationOption.objects.filter(tenant=tenant, is_available=True).select_related(
        "group", "group__label", "group__category"
    )
    if product is not None:
        qs = qs.filter(group__category=product.category, group__is_active=True)
    qtokens = _tokens(question)
    ranked = []
    for option in qs[:500]:
        target_tokens = _tokens(option.name)
        matched = _matched_target_tokens(qtokens, target_tokens)
        if not matched:
            best = max((_best_token_similarity(qtokens, t) for t in target_tokens), default=0)
            if best < 0.82:
                continue
            score = best
        else:
            score = 1 + len(matched)
        ranked.append((score, option))
    ranked.sort(key=lambda item: (-item[0], item[1].name.casefold()))
    return [item[1] for item in ranked[:5]]


def _customization_answer(tenant, question, product=None):
    matched_options = _find_customization_options(tenant, question, product=product)
    option_specific = (
        _has_any(question, ("quanto custa", "preco", "valor", "adicionar", "colocar"))
        or (product is None and bool(matched_options))
    )
    if matched_options and option_specific:
        lines = []
        facts = []
        for option in matched_options[:3]:
            group_name = option.group.label.name if option.group.label_id else "Adicionais"
            lines.append(f"*{option.name}* — +{brl(option.price)} ({group_name})")
            facts.append(
                f"{option.name}: adicional de {brl(option.price)} no grupo {group_name}, categoria {option.group.category.name}."
            )
        suffix = f"\n\n👉 {product_url(tenant, product)}" if product else ""
        if product:
            facts.append(f"Link direto: {product_url(tenant, product)}")
        return KnowledgeAnswer(
            "customization", tuple(facts), "Encontrei estas opções 😊\n\n" + "\n".join(lines) + suffix,
            context={"intent": "product", "product_ids": [product.pk]} if product else {"intent": "customization"},
        )
    if product is None:
        return KnowledgeAnswer(
            "customization",
            ("É necessário identificar o produto para listar todos os adicionais aplicáveis.",),
            "Claro 😊 Me diga *qual produto* você quer personalizar que eu mostro os adicionais disponíveis.",
            context={"intent": "customization"},
        )
    groups = _customization_groups(product)
    blocks = []
    facts = []
    for group in groups:
        options = [o for o in group.options.all() if o.is_available and o.tenant_id == tenant.pk]
        if not options:
            continue
        name = group.label.name if group.label_id else "Adicionais"
        option_lines = [f"• {o.name} — +{brl(o.price)}" for o in options[:8]]
        if len(options) > 8:
            option_lines.append(f"• e mais {len(options) - 8} opção(ões)")
        required = "obrigatório" if group.min_options > 0 else "opcional"
        blocks.append(f"*{name}* ({required})\n" + "\n".join(option_lines))
        facts.extend(f"{name}: {o.name} +{brl(o.price)}" for o in options)
    if not blocks:
        return KnowledgeAnswer(
            "customization",
            (f"{product.name} não possui adicionais ativos cadastrados.",),
            f"O *{product.name}* não tem adicionais cadastrados no momento 😊\n\n👉 {product_url(tenant, product)}",
            context={"intent": "product", "product_ids": [product.pk]},
        )
    facts.append(f"Link direto: {product_url(tenant, product)}")
    return KnowledgeAnswer(
        "customization", tuple(facts),
        f"Para o *{product.name}*, temos estas opções:\n\n" + "\n\n".join(blocks) + f"\n\n👉 {product_url(tenant, product)}",
        context={"intent": "product", "product_ids": [product.pk]},
    )


def _characteristic_kind(question):
    if _has_any(question, ("vegano", "vegana", "vegan")):
        return "vegan"
    if _has_any(question, ("picante", "apimentado", "apimentada", "pimenta")):
        return "spicy"
    if _has_any(question, ("alergeno", "alergenos", "alergia", "gluten", "lactose", "leite", "ovo", "amendoim", "castanha", "soja")):
        return "allergens"
    if _has_any(question, ("caloria", "calorias", "kcal")):
        return "calories"
    if _has_any(question, ("tempo de preparo", "preparo", "fica pronto", "pronto em", "demora para preparar")):
        return "prep_time"
    if _has_any(question, ("peso", "gramas", "grama")):
        return "weight"
    return None


def _generic_characteristic_answer(tenant, kind):
    products = [
        p for p in Product.objects.filter(tenant=tenant, is_available=True)
        .select_related("category").order_by("name")[:300]
        if _product_available_today(p)
    ]
    if kind == "vegan":
        matches = [p for p in products if p.is_vegan]
        label = "opções veganas 🌱"
    elif kind == "spicy":
        matches = [p for p in products if p.is_spicy]
        label = "opções picantes 🌶️"
    else:
        return None
    if not matches:
        return KnowledgeAnswer(
            "product_details", (f"Não há {label} marcadas no cadastro.",),
            f"Não encontrei {label} cadastradas no momento 😕",
            context={"intent": "product_details"},
        )
    blocks = [f"Temos estas {label}:"]
    for product in matches[:3]:
        blocks.append(f"*{product.name}* — {brl(product.effective_price)}\n👉 {product_url(tenant, product)}")
    return KnowledgeAnswer(
        "product_details", tuple(
            f"{p.name} está marcado como {label}. Link direto: {product_url(tenant, p)}"
            for p in matches
        ),
        "\n\n".join(blocks),
        context={"intent": "product", "product_ids": [p.pk for p in matches[:5]]},
    )


def _product_characteristic_answer(tenant, product, kind):
    url = product_url(tenant, product)
    context = {"intent": "product", "product_ids": [product.pk]}
    if kind == "vegan":
        if product.is_vegan:
            text = f"Sim 🌱 O *{product.name}* está cadastrado como vegano."
        else:
            text = f"O *{product.name}* não está marcado como vegano no cadastro da loja."
        return KnowledgeAnswer("product_details", (text, f"Link direto: {url}"), f"{text}\n\n👉 {url}", context=context)
    if kind == "spicy":
        text = (
            f"Sim 🌶️ O *{product.name}* está marcado como picante."
            if product.is_spicy else
            f"O *{product.name}* não está marcado como picante no cadastro da loja."
        )
        return KnowledgeAnswer("product_details", (text, f"Link direto: {url}"), f"{text}\n\n👉 {url}", context=context)
    if kind == "allergens":
        if product.allergens.strip():
            text = f"Alérgenos cadastrados para *{product.name}*: *{product.allergens.strip()}* ⚠️"
        else:
            text = f"A loja ainda não cadastrou informações de alérgenos para *{product.name}* ⚠️"
        warning = "Em caso de alergia grave, confirme diretamente com a loja, pois o sistema não informa risco de contaminação cruzada."
        return KnowledgeAnswer(
            "product_allergens", (text, warning), f"{text}\n\n{warning}\n\n👉 {url}", context=context
        )
    if kind == "calories":
        text = (
            f"O *{product.name}* tem *{product.calories} kcal* por porção no cadastro."
            if product.calories is not None else
            f"A loja ainda não cadastrou as calorias do *{product.name}*."
        )
        return KnowledgeAnswer("product_details", (text, f"Link direto: {url}"), f"{text}\n\n👉 {url}", context=context)
    if kind == "prep_time":
        if product.prep_time is not None:
            text = f"O tempo de preparo cadastrado do *{product.name}* é de aproximadamente *{product.prep_time} min* ⏱️"
            note = "Esse tempo é apenas de preparo e não inclui o tempo total de entrega."
            return KnowledgeAnswer("product_details", (text, note, f"Link direto: {url}"), f"{text}\n\n{note}\n\n👉 {url}", context=context)
        text = f"A loja ainda não cadastrou o tempo de preparo do *{product.name}*."
        return KnowledgeAnswer("product_details", (text, f"Link direto: {url}"), f"{text}\n\n👉 {url}", context=context)
    if kind == "weight":
        text = (
            f"O peso cadastrado do *{product.name}* é de *{format(product.weight.normalize(), 'f')} g*."
            if product.weight is not None else
            f"A loja ainda não cadastrou o peso do *{product.name}*."
        )
        return KnowledgeAnswer("product_details", (text, f"Link direto: {url}"), f"{text}\n\n👉 {url}", context=context)
    return None


def _unavailable_answer(tenant, product):
    return KnowledgeAnswer(
        "product_unavailable",
        (
            f"{product.name} existe no cadastro, mas não está disponível neste momento.",
            f"Catálogo: {catalog_url(tenant)}",
        ),
        f"O *{product.name}* está cadastrado, mas não está disponível no momento 😕\n\nVeja outras opções no cardápio:\n👉 {catalog_url(tenant)}",
        context={"intent": "product_unavailable"},
    )

@dataclass(frozen=True)
class KnowledgeAnswer:
    intent: str
    facts: tuple[str, ...]
    fallback: str
    pause_minutes: int = 0
    pause_reason: str = ""
    context: dict = field(default_factory=dict)



def _delivery_city(tenant, question):
    """Return a canonical active delivery city explicitly mentioned in the message."""
    qnorm = normalize(question)
    qtokens = _tokens(question, keep_stopwords=True)
    cities = sorted(
        {
            zone.city.strip()
            for zone in DeliveryZone.objects.filter(tenant=tenant, is_active=True)
            if (zone.city or "").strip()
        },
        key=lambda value: (-len(normalize(value)), value.casefold()),
    )
    best = None
    best_score = 0.0
    for city in cities:
        cnorm = normalize(city)
        if cnorm and cnorm in qnorm:
            return city
        ctokens = _tokens(city, keep_stopwords=True)
        if not ctokens:
            continue
        matched = _matched_target_tokens(qtokens, ctokens)
        score = len(matched) / max(1, len(ctokens))
        if score > best_score and score >= 0.8:
            best = city
            best_score = score
    return best


def _delivery_neighborhood(tenant, question):
    """Return the best active neighborhood mentioned, without mistaking a city for it."""
    qnorm = normalize(question)
    qtokens = _tokens(question, keep_stopwords=True)
    neighborhoods = sorted(
        {
            zone.neighborhood.strip()
            for zone in DeliveryZone.objects.filter(tenant=tenant, is_active=True)
            if (zone.neighborhood or "").strip()
        },
        key=lambda value: (-len(normalize(value)), value.casefold()),
    )
    best = None
    best_score = 0.0
    for neighborhood in neighborhoods:
        nnorm = normalize(neighborhood)
        if nnorm and nnorm in qnorm:
            return neighborhood
        ntokens = _tokens(neighborhood, keep_stopwords=True)
        if not ntokens:
            continue
        matched = _matched_target_tokens(qtokens, ntokens)
        coverage = len(matched) / max(1, len(ntokens))
        if coverage < 0.8:
            continue
        similarity_bonus = sum(
            _best_token_similarity(qtokens, target) for target in ntokens
        ) / max(1, len(ntokens))
        score = coverage + similarity_bonus
        if score > best_score:
            best = neighborhood
            best_score = score
    return best


def _delivery_zone_for_city_and_neighborhood(tenant, city, neighborhood):
    city_norm = normalize(city)
    neighborhood_norm = normalize(neighborhood)
    zones = list(
        DeliveryZone.objects.filter(tenant=tenant, is_active=True)
        .order_by("city", "neighborhood")
    )
    best = None
    best_score = 0.0
    for zone in zones:
        city_score = _similarity(normalize(zone.city), city_norm)
        neighborhood_score = _similarity(normalize(zone.neighborhood), neighborhood_norm)
        if city_score < 0.88 or neighborhood_score < 0.82:
            continue
        score = city_score + neighborhood_score
        if score > best_score:
            best = zone
            best_score = score
    return best


def _delivery_followup(question, context, tenant):
    """Use delivery context only for genuinely elliptical follow-ups.

    Explicit new intents (address, hours, payment, product, etc.) must never be
    swallowed just because the previous turn was about delivery.
    """
    if context.get("intent") not in {"delivery", "delivery_fee"}:
        return False
    q = normalize(question)
    if not q:
        return False
    if _delivery_city(tenant, question) or _delivery_neighborhood(tenant, question):
        return True
    tokens = q.split()
    if len(tokens) > 6:
        return False
    return (
        q == "quanto"
        or q.startswith("quanto ")
        or q.startswith("e ")
        or q.startswith("para ")
        or q.startswith("pro ")
        or q.startswith("pra ")
        or q.startswith("no ")
        or q.startswith("na ")
    )

def answer_from_store(tenant, question, context=None):
    context = context if isinstance(context, dict) else {}
    q = normalize(question)

    human_terms = (
        "falar com atendente", "falar com uma pessoa", "falar com pessoa",
        "atendimento humano", "quero atendente", "chamar atendente",
        "falar com a loja", "quero falar com alguem", "quero falar com alguém",
    )
    if _has_any(question, human_terms):
        return KnowledgeAnswer(
            "human",
            ("O cliente pediu atendimento humano.",),
            "Claro 😊 Vou deixar a conversa livre para a equipe da loja continuar com você por aqui.",
            pause_minutes=60,
            pause_reason="human",
        )

    # Entrega/retirada como capacidade da operação, sem confundir com consulta de taxa.
    address_words = (
        "endereco", "onde fica", "onde voces fica", "onde voces ficam", "localizacao",
        "buscar ai", "buscar aqui", "cade endereco",
    )
    if not _has_any(question, address_words):
        fulfillment = _fulfillment_answer(tenant, question)
        has_location = bool(_delivery_city(tenant, question) or _delivery_neighborhood(tenant, question))
        asks_fee = _has_any(question, ("taxa", "frete", "valor da entrega", "quanto fica entrega", "quanto entrega"))
        if fulfillment and not has_location and not asks_fee and not _delivery_areas_question(question):
            return fulfillment

    # Intenções explícitas sempre vencem o contexto anterior.
    if _has_any(question, address_words):
        address = store_address(tenant)
        if address:
            return KnowledgeAnswer(
                "address",
                (f"Endereço da loja: {address}.",),
                f"Claro! 📍\n\nFicamos em *{address}*.",
                context={"intent": "address"},
            )
        return KnowledgeAnswer(
            "address",
            ("O endereço ainda não foi preenchido no painel.",),
            "Ainda não encontrei o endereço da loja no cadastro 😕",
        )

    hours_words = (
        "horario", "abre", "aberto", "aberta", "fecha", "fechado",
        "fechada", "funciona", "funcionamento", "que horas",
    )
    if _has_any(question, hours_words):
        schedule = hours_text(tenant)
        open_now = tenant.is_open_now()
        specific = _specific_hours_answer(tenant, question)
        return KnowledgeAnswer(
            "hours",
            (f"Horários cadastrados: {schedule}.", f"A loja está {'aberta' if open_now else 'fechada'} neste momento."),
            specific or f"🕒 Estes são os horários da loja:\n{schedule}",
            context={"intent": "hours"},
        )

    payment_words = (
        "pagamento", "pagar", "pix", "cartao", "dinheiro", "debito",
        "credito", "troco", "forma de pagamento", "formas de pagamento",
    )
    if _has_any(question, payment_words):
        text = payment_text(tenant)
        if _has_any(question, ("quais", "forma de pagamento", "formas de pagamento")):
            fallback = f"As formas de pagamento disponíveis são 😊💳\n\n{text}"
        else:
            fallback = f"Aceitamos sim 😊💳\n\n{text}"
        return KnowledgeAnswer(
            "payment", (text,), fallback, context={"intent": "payment"}
        )

    promotion_words = (
        "promocao", "promocoes", "oferta", "ofertas", "desconto", "descontos",
        "cupom", "cupons", "em promocao",
    )
    if _has_any(question, promotion_words):
        return _promotions_answer(tenant)

    if _delivery_areas_question(question):
        return _delivery_areas_answer(tenant, question)

    delivery_words = (
        "entrega", "taxa", "frete", "bairro", "entregam", "entregar",
        "delivery", "valor da entrega", "quanto fica entrega",
    )
    explicit_delivery = _has_any(question, delivery_words)
    delivery_question = explicit_delivery or _delivery_followup(question, context, tenant)

    if delivery_question:
        if not tenant.accepts_delivery:
            return KnowledgeAnswer(
                "delivery",
                ("A loja não oferece entrega.",),
                "No momento trabalhamos somente com *retirada no local* 📍 e não fazemos entrega.",
                context={"intent": "delivery"},
            )
        city = _delivery_city(tenant, question) or context.get("city")
        neighborhood = _delivery_neighborhood(tenant, question) or context.get("neighborhood")

        if neighborhood and not city:
            return KnowledgeAnswer(
                "delivery",
                (f"Bairro informado: {neighborhood}. Falta a cidade para consultar a zona de entrega.",),
                f"Claro 😊 Para consultar a taxa de *{neighborhood}*, me diga também a *cidade*.",
                context={"intent": "delivery", "neighborhood": neighborhood},
            )

        if city and not neighborhood:
            # Se a pergunta é sobre bairros atendidos, listamos em vez de pedir bairro.
            if _delivery_areas_question(question):
                return _delivery_areas_answer(tenant, question)
            return KnowledgeAnswer(
                "delivery",
                (f"Cidade informada: {city}. Falta o bairro para consultar a zona de entrega.",),
                f"Perfeito 😊 Agora me diga o *bairro* da entrega em *{city}*.",
                context={"intent": "delivery", "city": city},
            )

        if city and neighborhood:
            zone = _delivery_zone_for_city_and_neighborhood(
                tenant, city=city, neighborhood=neighborhood
            )
            if zone:
                fact = (
                    f"A loja entrega em {zone.neighborhood}, {zone.city}, "
                    f"com taxa de {brl(zone.fee)}."
                )
                return KnowledgeAnswer(
                    "delivery_fee",
                    (fact,),
                    f"A entrega para *{zone.neighborhood}, {zone.city}* fica *{brl(zone.fee)}* 🚚",
                    context={
                        "intent": "delivery_fee", "zone_id": zone.pk,
                        "city": zone.city, "neighborhood": zone.neighborhood,
                    },
                )
            return KnowledgeAnswer(
                "delivery",
                (f"Não existe zona ativa cadastrada para {neighborhood}, {city}.",),
                f"Não encontrei entrega cadastrada para *{neighborhood}, {city}* 😕",
                context={"intent": "delivery", "city": city, "neighborhood": neighborhood},
            )

        zones = list(
            DeliveryZone.objects.filter(tenant=tenant, is_active=True)
            .order_by("city", "neighborhood")[:80]
        )
        if zones:
            facts = tuple(
                f"{zone.neighborhood}, {zone.city}: {brl(zone.fee)}" for zone in zones
            )
            return KnowledgeAnswer(
                "delivery", facts,
                "Claro 😊 Me diga a *cidade* e o *bairro* da entrega que eu consulto a taxa para você.",
                context={"intent": "delivery"},
            )
        return KnowledgeAnswer(
            "delivery", ("A loja não possui zonas de entrega ativas cadastradas.",),
            "Ainda não encontrei áreas de entrega cadastradas para esta loja 😕",
        )

    description_intent = _has_any(
        question, ("o que vem", "ingrediente", "ingredientes", "descricao", "composicao", "leva o que", "vem o que")
    )
    customization_intent = _has_any(
        question, ("adicional", "adicionais", "extra", "extras", "acrescimo", "complemento", "molho", "molhos", "borda", "bordas")
    )
    characteristic = _characteristic_kind(question)

    if description_intent:
        product = _specific_product(tenant, question, context)
        if product:
            return _product_description_answer(tenant, product)
        return KnowledgeAnswer(
            "product_description", ("Não foi possível identificar um único produto.",),
            "Claro 😊 Me diga *qual produto* você quer saber os ingredientes/descrição.",
            context={"intent": "product_description"},
        )

    if customization_intent:
        product = _specific_product(tenant, question, context)
        return _customization_answer(tenant, question, product=product)

    if characteristic:
        product = _specific_product(tenant, question, context)
        if product:
            return _product_characteristic_answer(tenant, product, characteristic)
        generic = _generic_characteristic_answer(tenant, characteristic)
        if generic:
            return generic
        return KnowledgeAnswer(
            "product_details", ("A informação solicitada depende de um produto específico.",),
            "Claro 😊 Me diga *qual produto* você quer consultar.",
            context={"intent": "product_details"},
        )

    products = find_products(tenant, question)
    if products:
        request_kind = _product_request_kind(question)
        facts = tuple(product_facts(tenant, products)) + (f"Catálogo: {catalog_url(tenant)}",)
        product_context = {"intent": "product", "product_ids": [p.pk for p in products[:5]]}
        if len(products) == 1:
            return KnowledgeAnswer(
                "product", facts,
                _single_product_fallback(tenant, products[0], request_kind=request_kind),
                context=product_context,
            )
        return KnowledgeAnswer(
            "product", facts,
            _product_list_fallback(tenant, products, request_kind=request_kind),
            context=product_context,
        )

    unavailable = _unavailable_product(tenant, question)
    if unavailable:
        return _unavailable_answer(tenant, unavailable)

    previous_products = _context_products(tenant, context)
    followup_words = {"quanto", "preco", "valor", "esse", "essa", "dele", "dela"}
    raw_words = set(q.split())
    if previous_products and (raw_words & followup_words):
        if len(previous_products) == 1:
            product = previous_products[0]
            return KnowledgeAnswer(
                "product", tuple(product_facts(tenant, [product])),
                _single_product_fallback(
                    tenant, product, request_kind=_product_request_kind(question)
                ),
                context={"intent": "product", "product_ids": [product.pk]},
            )

    greeting_words = ("oi", "ola", "bom dia", "boa tarde", "boa noite", "e ai", "eai")
    if q in greeting_words or any(q.startswith(word + " ") for word in greeting_words):
        return KnowledgeAnswer(
            "greeting",
            (f"Nome da loja: {tenant.name}.", f"Catálogo: {catalog_url(tenant)}"),
            f"Oi! 😊 Sou o assistente da *{tenant.name}*. Posso te ajudar com o cardápio, entrega, retirada, endereço, horários, promoções e formas de pagamento.",
        )

    return KnowledgeAnswer(
        "unknown",
        (
            f"Nome da loja: {tenant.name}.", f"Catálogo: {catalog_url(tenant)}",
            "O assistente pode responder sobre produtos, adicionais, promoções, entrega, retirada, endereço, horários e pagamento.",
        ),
        f"Posso te ajudar 😊 Me pergunte sobre produtos, adicionais, promoções, entrega, retirada, endereço, horários ou pagamento.\nCardápio: {catalog_url(tenant)}",
    )
