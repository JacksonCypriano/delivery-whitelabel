from dataclasses import dataclass, field
from decimal import Decimal
from urllib.parse import urlencode
import re
import unicodedata
from difflib import SequenceMatcher

from django.utils import timezone

from apps.marketplace.services import build_tenant_url
from apps.stores.models import CustomizationGroup, CustomizationOption, HalfProduct, Product
from apps.tenants.models import DeliveryZone


STOPWORDS = {
    "a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "da", "do",
    "das", "dos", "e", "em", "no", "na", "nos", "nas", "para", "por", "com",
    "tem", "temos", "ter", "voces", "voce", "que", "qual", "quais", "quanto",
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
    "oq": "o que", "oque": "o que",
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
    "vr": "vale refeicao", "va": "vale alimentacao",
    "cred": "credito", "deb": "debito", "din": "dinheiro",
    "piks": "pix", "pics": "pix", "piz": "pix",
    "refri": "bebida", "refris": "bebida", "ref": "bebida",
    "card": "cardapio", "cardap": "cardapio", "prod": "produto",
    "prods": "produtos", "adic": "adicional", "add": "adicional",
    "adds": "adicionais", "promo": "promocao", "promos": "promocao",
    "ingr": "ingrediente", "ingred": "ingrediente", "ingrs": "ingredientes",
    "ingrd": "ingrediente", "ingreds": "ingredientes",
    "igrediente": "ingrediente", "igredientes": "ingredientes",
    "ingediente": "ingrediente", "ingedientes": "ingredientes",
    "veim": "vem", "ven": "vem", "eh": "e", "cmo": "como",
    "descrisao": "descricao", "descrissao": "descricao",
    "composisao": "composicao", "composissao": "composicao",
    "rexeio": "recheio",
    "glutem": "gluten", "lactoze": "lactose",
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
    "hamburger": "hamburguer",
    "hamburgeres": "hamburguer",
    "hambuger": "hamburguer",
    "burguer": "hamburguer",
    "burgers": "hamburguer",
    "burguers": "hamburguer",
    "hamburgueres": "hamburguer",
    "hamburgers": "hamburguer",
    "lanche": "hamburguer",
    "lanches": "hamburguer",
    "lanxe": "hamburguer",
    "lanxes": "hamburguer",
    "lache": "hamburguer",
    "laches": "hamburguer",
    "refri": "bebida",
    "refris": "bebida",
    "refrigerante": "bebida",
    "refrigerantes": "bebida",
    "bebidas": "bebida",
    "porcoes": "porcao",
    "combos": "combo",
    "sobremesas": "sobremesa",
    "pizzas": "pizza",

    # Erros muito comuns em ingredientes/sabores. A busca por ingrediente
    # continua genérica, mas estes atalhos evitam depender de fuzzy matching
    # agressivo em palavras semanticamente diferentes.
    "frngo": "frango",
    "catupiri": "catupiry",
    "chedar": "cheddar",
    "calabreza": "calabresa",
}

GENERIC_PRODUCT_TERMS = {
    "produto", "item", "cardapio", "hamburguer", "bebida", "pizza",
    "porcao", "combo", "sobremesa", "lanche", "refrigerante",
}

# Tokens de apoio/teste ou muito genéricos nunca podem, sozinhos, fazer um
# produto parecer correspondente a uma pergunta. Isso evita, por exemplo, que
# uma consulta por um item inexistente contendo "QA" acabe casando com outro
# produto do tenant apenas porque ambos possuem esse sufixo.
LOW_INFORMATION_PRODUCT_TERMS = {
    "qa", "teste", "test", "produto", "produtos", "item", "itens",
    "opcao", "opcoes",
}

PRODUCT_QUERY_NOISE_TERMS = {
    "hoje", "agora", "disponivel", "disponiveis", "cardapio", "loja",
    "vende", "vendem", "vender", "possui", "trabalha", "trabalham",
}

# Termos estruturais de personalização não identificam uma opção por si só.
# Ex.: "cebola extra" não pode casar com "bacon extra" apenas pela palavra extra.
GENERIC_CUSTOMIZATION_TERMS = {
    "adicional", "adicionais", "extra", "extras", "opcao", "opcoes",
    "acrescimo", "acrescimos", "complemento", "complementos",
    "molho", "molhos", "borda", "bordas",
}

# Palavras estruturais que aparecem em perguntas por ingrediente, mas não
# representam o ingrediente procurado. A busca por ingrediente usa somente
# nome/descrição reais dos produtos do tenant e nunca cria informação nova.
INGREDIENT_QUERY_NOISE_TERMS = {
    "algo", "coisa", "coisas", "produto", "produtos", "item", "itens",
    "opcao", "opcoes", "ingrediente", "ingredientes", "descricao",
    "composicao", "recheio", "recheios", "sabor", "sabores",
    "leva", "levam", "vai", "vao", "vem", "feito", "feita", "feitos",
    "feitas", "dentro", "contem", "possui", "possuir", "tipo", "tipos",
}

# Qualificadores comuns de nome/descrição exigem correspondência exata quando
# usados em busca por ingrediente. Ex.: ``espacial`` não pode casar por fuzzy
# com ``especial`` em "Lanche Especial" ou "molho especial", mas uma busca
# explícita por ``molho especial`` continua válida.
INGREDIENT_LOW_INFORMATION_TERMS = {
    "especial", "especiais", "tradicional", "tradicionais",
    "classico", "classica", "classicos", "classicas",
    "premium", "promo", "promocional", "promocionais",
    "artesanal", "artesanais", "casa", "qa", "teste", "test",
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
    """Return conservative singular/plural forms used only for matching.

    Portuguese plural morphology is irregular, so this deliberately produces
    *alternatives* instead of rewriting the user's text to one forced singular.
    That gives product/category matching tolerance for common forms such as
    ``pasteis``/``pastel``, ``adicionais``/``adicional``,
    ``porcoes``/``porcao`` and ordinary ``...s`` plurals without changing the
    original question or creating facts that are not in the tenant database.
    """
    raw = TERM_ALIASES.get(token, token)
    result = {raw}

    if len(raw) >= 4 and raw.endswith("oes"):
        result.add(raw[:-3] + "ao")
    if len(raw) >= 4 and raw.endswith("aes"):
        result.add(raw[:-3] + "ao")
    if len(raw) >= 5 and raw.endswith("ais"):
        result.add(raw[:-3] + "al")
    if len(raw) >= 5 and raw.endswith("eis"):
        result.add(raw[:-3] + "el")
    if len(raw) >= 5 and raw.endswith("ois"):
        result.add(raw[:-3] + "ol")
    if len(raw) >= 5 and raw.endswith("uis"):
        result.add(raw[:-3] + "ul")
    if len(raw) >= 4 and raw.endswith("ns"):
        result.add(raw[:-2] + "m")
    if len(raw) >= 4 and raw.endswith("zes"):
        result.add(raw[:-2])

    # Keep both common candidates. For example ``ingredientes`` should become
    # ``ingrediente`` by removing only ``s``, while ``sabores`` can also become
    # ``sabor`` by removing ``es``. Matching later chooses the best candidate.
    if len(raw) >= 5 and raw.endswith("s"):
        result.add(raw[:-1])
    if len(raw) >= 5 and raw.endswith("es"):
        result.add(raw[:-2])

    normalized = set()
    for item in result:
        if len(item) < 2:
            continue
        normalized.add(TERM_ALIASES.get(item, item))
    return normalized


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
    # Compare all conservative inflection variants on both sides. This makes
    # singular/plural handling generic instead of relying on one alias per word.
    left_forms = _term_variants(left)
    right_forms = _term_variants(right)
    for left_form in left_forms:
        for right_form in right_forms:
            if (
                _similarity(left_form, right_form)
                >= _fuzzy_threshold(left_form, right_form)
            ):
                return True
    return False


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


def _has_exact_phrase(question, terms):
    """Match normalized phrases without fuzzy expansion.

    Use this for intents whose vocabulary can collide phonetically with another
    domain term (for example ``dinheiro`` x ``banheiro``).
    """
    q = f" {normalize(question)} "
    for term in terms:
        normalized = normalize(term)
        if normalized and f" {normalized} " in q:
            return True
    return False


def _has_tokenwise_any(question, terms):
    """Fuzzy-match complete tokens/phrases without substring collisions.

    This preserves WhatsApp typo tolerance while preventing terms such as
    ``extra`` from matching inside unrelated words such as ``extraterrestre``.
    """
    q_tokens = normalize(question).split()
    for term in terms:
        normalized = normalize(term)
        if not normalized:
            continue
        term_tokens = normalized.split()
        if len(term_tokens) == 1:
            if any(_tokens_match(token, term_tokens[0]) for token in q_tokens):
                return True
        elif _phrase_matches(question, normalized):
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
    open_now_phrases = (
        "agora", "aberto agora", "aberta agora", "esta aberto", "esta aberta",
        "ta aberto", "ta aberta", "estao abertos", "estao abertas",
        "tao abertos", "tao abertas", "funcionando agora", "esta funcionando",
    )
    if weekday is None and any(phrase in q for phrase in open_now_phrases):
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
    if _has_tokenwise_any(question, ("fecha", "fecham")):
        return f"{prefix}, fechamos às *{last}* 🕒"
    if _has_tokenwise_any(question, ("abre", "abrem")):
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


def _looks_like_product_composition_question(question):
    """Recognize natural questions asking what a product contains.

    The intent is deliberately broad for normal WhatsApp language and common
    misspellings, but explicit customization/allergen vocabulary still wins.
    The returned answer always comes from the product description stored in the
    tenant database; this function only detects the intent.
    """
    q = normalize(question)
    q_tokens = set(q.split())

    strong_customization_terms = {
        "adicional", "adicionais", "extra", "extras",
        "acrescimo", "acrescimos", "complemento", "complementos",
        "borda", "bordas",
    }
    allergen_terms = {
        "alergeno", "alergenos", "alergia", "gluten", "lactose",
        "leite", "ovo", "amendoim", "castanha", "soja",
    }

    # These guards are intentionally exact after normalization. Fuzzy matching
    # here can create dangerous collisions (for example ``feito`` x ``leite``).
    # Common WhatsApp misspellings are normalized in WHATSAPP_ABBREVIATIONS.
    if q_tokens & strong_customization_terms:
        return False
    if q_tokens & allergen_terms:
        return False

    # Strong ways customers ask for ingredients/description. Matching is fuzzy
    # token-by-token, so common WhatsApp typos such as ``igredientes``,
    # ``composisao`` and ``veim`` are tolerated by normalization + aliases.
    description_phrases = (
        "o que vem", "que vem", "vem o que", "vem com o que",
        "o que leva", "que leva", "leva o que",
        "o que vai", "que vai", "vai o que",
        "o que tem dentro", "que tem dentro", "tem dentro",
        "do que e feito", "feito com o que", "feito de que",
        "e feito de que", "e feito com o que",
        "quais ingredientes", "qual ingrediente", "ingredientes",
        "qual descricao", "descricao",
        "qual composicao", "composicao",
        "qual recheio", "recheio",
        "me descreve", "descreve o", "descreve a",
        "o que acompanha", "que acompanha",
    )
    if (
        _has_exact_phrase(question, description_phrases)
        or _has_tokenwise_any(question, description_phrases)
    ):
        return True

    # Very common short form: ``o que tem no hamb bacon?`` / ``q tem na
    # pizza?``. Require product/category evidence so ``o que tem no cardápio?``
    # does not automatically become a description request.
    if re.search(r"^(?:o )?que tem (?:no|na|nesse|nessa)\s+.+", q):
        if bool(_tokens(question) & GENERIC_PRODUCT_TERMS):
            return True

    # ``o que esse lanche leva?`` / ``o que o hamb bacon tem?``. Require
    # either the explicit ``o que`` construction or a demonstrative form.
    # This is intentionally stricter than a bare ``que ... tem`` because
    # list questions such as ``q hamb vcs tem?`` normalize to
    # ``que hamburguer voces tem`` and must remain product listings.
    explicit_product_subject = bool(
        re.search(
            r"^(?:e\s+)?o\s+que\s+.+\s+(?:tem|leva|vai|vem com)(?:\s+.*)?$",
            q,
        )
        or re.search(
            r"^(?:e\s+)?que\s+(?:esse|essa|este|esta)\s+.+\s+"
            r"(?:tem|leva|vai|vem com)(?:\s+.*)?$",
            q,
        )
    )
    if explicit_product_subject and bool(_tokens(question) & GENERIC_PRODUCT_TERMS):
        return True

    # ``como é o hamb bacon?``, ``como eh a pizza portuguesa?``. Require
    # evidence of a product/category so generic questions such as
    # ``como é a entrega?`` are not treated as product description.
    if re.search(r"^(?:me fala )?como e (?:o|a|esse|essa)\s+.+", q):
        if bool(_tokens(question) & GENERIC_PRODUCT_TERMS):
            return True

    # Ingredient after the verb: ``tem cheddar no hamb bacon?``,
    # ``leva bacon no lanche?`` and contextual ``e tem bacon nele?``.
    if re.search(
        r"\b(?:tem|leva|vai|vem com)\b.+\b(?:no|na|nele|nela|nesse|nessa)\b",
        q,
    ):
        return True

    # Product first: ``o hamb bacon tem bacon?``, ``a pizza leva queijo?``.
    if re.search(
        r"^(?:o|a|esse|essa)\s+.+\s+(?:tem|leva|vai|vem com)\s+.+",
        q,
    ):
        return True

    # Pergunta contextual invertida: ``e o que ele leva?`` /
    # ``o que ela tem?``. O produto é resolvido pelo contexto da conversa.
    if re.search(
        r"^(?:e\s+)?o\s+que\s+(?:ele|ela|isso|esse|essa)\s+"
        r"(?:tem|leva|vai|vem com)(?:\s+.*)?$",
        q,
    ):
        return True

    # Explicit pronoun follow-ups after a product was established in context.
    return bool(
        re.search(
            r"^(?:e\s+)?(?:ele|ela|isso|esse|essa)\s+"
            r"(?:tem|leva|vai|vem com)\s+.+",
            q,
        )
    )


def _composition_product(tenant, question, context=None):
    """Resolve the product for an ingredient question without losing context.

    A pronoun such as ``nele`` must refer to the single product from the
    previous turn instead of being re-ranked against every product containing
    the ingredient token (for example every item containing ``bacon``).
    """
    q_tokens = set(normalize(question).split())
    pronouns = {"nele", "nela", "nesse", "nessa", "ele", "ela", "isso", "esse", "essa"}
    if q_tokens & pronouns:
        previous = _context_products(tenant, context or {})
        if len(previous) == 1:
            return previous[0]
    return _specific_product(tenant, question, context)


def _explicit_product_subject_product(tenant, question):
    """Return a product explicitly named before a composition verb.

    This handles natural forms such as ``Pizza Portuguesa leva frango?``
    without mistaking broad questions like ``quais pizzas têm frango?`` for
    one specific product. Only name/category evidence is used here; product
    descriptions are deliberately ignored.
    """
    q = normalize(question)
    match = re.match(
        r"^(?P<subject>.+?)\s+(?:tem|leva|vai|vem com)\s+.+$",
        q,
    )
    if not match:
        return None

    subject = match.group("subject").strip()
    if re.match(
        r"^(?:tem|quais?|que|algum|alguma|alguns|algumas|existe|ha)\b",
        subject,
    ):
        return None

    subject_tokens = _tokens(subject)
    if not subject_tokens:
        return None

    best = None
    best_score = 0
    for product in (
        Product.objects.filter(tenant=tenant)
        .select_related("category")
        .order_by("name")[:300]
    ):
        name_tokens = _tokens(product.name)
        category_tokens = _tokens(
            product.category.name if product.category_id else ""
        )
        informative_subject = (
            subject_tokens
            - category_tokens
            - GENERIC_PRODUCT_TERMS
            - LOW_INFORMATION_PRODUCT_TERMS
        )
        if not informative_subject:
            continue

        matched = sum(
            1
            for token in informative_subject
            if any(_tokens_match(token, target) for target in name_tokens)
        )
        if matched != len(informative_subject):
            continue

        score = matched * 10 + len(
            _matched_target_tokens(subject_tokens, name_tokens)
        )
        if score > best_score:
            best = product
            best_score = score

    return best


def _ingredient_query_parts(tenant, question):
    """Return ``(category, ingredient_tokens)`` for broad ingredient searches.

    Examples:
    - ``tem pizza de frango?``
    - ``quais pizzas tem calabresa?``
    - ``tem hamburguer que leva cebola?``
    - ``tem algo com catupiry?``

    A question about one explicit product (``a Pizza Portuguesa tem frango?``)
    is intentionally excluded so the normal product-description flow can answer
    from that product alone.
    """
    q = normalize(question)
    if not q:
        return None, []

    # Specific-product composition questions must remain product_description.
    if re.match(r"^(?:o|a|esse|essa|este|esta)\s+", q):
        return None, []
    if re.search(r"\b(?:nele|nela|nesse|nessa|ele|ela)\b", q):
        return None, []
    if _explicit_product_subject_product(tenant, question) is not None:
        return None, []

    # Direct WhatsApp forms that ask what ONE product contains must not be
    # reinterpreted as a broad ingredient search. Examples after normalization:
    # ``q vem no hamb bacon?`` -> ``que vem no hamburguer bacon``
    # ``que tem no hamb bacon?`` -> ``que tem no hamburguer bacon``
    # ``vem com oq o hamb bacon?`` -> ``vem com o que o hamburguer bacon``
    #
    # Keep this narrower than the generic composition detector because forms
    # such as ``quais pizzas tem frango?`` and ``tem hamburguer que leva cebola?``
    # ARE broad ingredient searches and must continue through this function.
    specific_composition_patterns = (
        r"^(?:o\s+)?que\s+(?:vem|tem|leva|vai)(?:\s+com)?\s+"
        r"(?:no|na|nesse|nessa|neste|nesta)\s+.+$",
        r"^(?:vem|tem|leva|vai)(?:\s+com)?\s+o\s+que\s+"
        r"(?:o|a|esse|essa|este|esta)\s+.+$",
    )
    if any(re.search(pattern, q) for pattern in specific_composition_patterns):
        return None, []

    # Explicit customization/allergen/characteristic vocabulary has a more
    # specific intent and must never be swallowed by ingredient search.
    if _has_tokenwise_any(
        question,
        (
            "adicional", "adicionais", "extra", "extras", "acrescimo",
            "acrescimos", "complemento", "complementos", "borda", "bordas",
        ),
    ):
        return None, []
    if _characteristic_kind(question):
        return None, []

    category = _category_for_question(tenant, question)
    generic_target = bool(
        re.search(
            r"\b(?:algo|alguma coisa|algum produto|alguma opcao|opcoes|"
            r"produtos?|itens?)\b",
            q,
        )
    )
    if category is None and not generic_target:
        return None, []

    # Require a relationship between the category/generic target and an
    # ingredient. This keeps plain catalog questions such as ``tem pizza?`` or
    # specific shorthand such as ``tem hamb bacon?`` on the normal product flow.
    # For ``quais pizzas tem frango?`` the category appears *before* the verb;
    # for ``tem pizza de frango?`` the explicit preposition carries the meaning.
    normalized_tokens = q.split()
    category_tokens = _tokens(category.name) if category is not None else set()
    category_before_verb = False
    if category_tokens:
        verb_tokens = {"tem", "leva", "levam", "vai", "vao", "vem", "contem", "possui"}
        category_positions = [
            index
            for index, token in enumerate(normalized_tokens)
            if any(_tokens_match(token, target) for target in category_tokens)
        ]
        verb_positions = [
            index for index, token in enumerate(normalized_tokens)
            if token in verb_tokens
        ]
        category_before_verb = any(
            category_index < verb_index < len(normalized_tokens) - 1
            for category_index in category_positions
            for verb_index in verb_positions
        )

    generic_before_verb = bool(
        re.search(
            r"\b(?:produtos?|itens?|opcoes?|coisas?)\s+"
            r"(?:tem|leva|levam|vai|vao|vem|contem|possui)\b",
            q,
        )
    )

    relationship = bool(
        re.search(r"\b(?:de|com)\s+[a-z0-9]", q)
        or re.search(r"\bque\s+(?:tem|leva|levam|vai|vao|vem|contem|possui)\b", q)
        or category_before_verb
        or generic_before_verb
    )
    if not relationship:
        return None, []

    noise = (
        category_tokens
        | GENERIC_PRODUCT_TERMS
        | LOW_INFORMATION_PRODUCT_TERMS
        | PRODUCT_QUERY_NOISE_TERMS
        | INGREDIENT_QUERY_NOISE_TERMS
    )

    ingredients = []
    seen = set()
    for raw in normalize(question).split():
        canonical = TERM_ALIASES.get(raw, raw)
        variants = _term_variants(canonical)
        if raw in STOPWORDS or canonical in STOPWORDS:
            continue
        if variants & noise:
            continue
        if canonical in seen or len(canonical) < 2:
            continue
        seen.add(canonical)
        ingredients.append(canonical)

    return category, ingredients


def _ingredient_tokens_match(query_token, target_token):
    """Ingredient-safe token matching.

    Generic qualifiers such as ``especial`` are valid when explicitly written,
    but are not allowed as fuzzy targets. This prevents semantically different
    words such as ``espacial`` from being treated as ingredient matches.
    """
    query = TERM_ALIASES.get(query_token, query_token)
    target = TERM_ALIASES.get(target_token, target_token)
    if target in INGREDIENT_LOW_INFORMATION_TERMS:
        return query == target
    return _tokens_match(query, target)


def _ingredient_catalog_products(tenant, ingredient_tokens, category=None):
    """Find available products whose name/description contains every ingredient.

    Matching is token based (with the same typo/singular/plural tolerance used
    elsewhere by the agent), so ``catupiri`` can match a registered
    ``catupiry`` without treating arbitrary substrings as ingredients.
    """
    if not ingredient_tokens:
        return []

    qs = (
        Product.objects.filter(tenant=tenant)
        .select_related("category")
        .order_by("name")
    )
    if category is not None:
        qs = qs.filter(category=category)

    ranked = []
    for product in qs[:300]:
        if not _product_available_today(product):
            continue

        name_tokens = _tokens(product.name)
        description_tokens = _tokens(product.description or "")
        searchable = name_tokens | description_tokens
        if not searchable:
            continue

        matches = []
        for ingredient in ingredient_tokens:
            matching_targets = [
                target for target in searchable
                if _ingredient_tokens_match(ingredient, target)
            ]
            if not matching_targets:
                break
            matches.append(matching_targets)
        else:
            # Prefer ingredients explicitly present in the name, then exact
            # token matches, while keeping stable alphabetical ordering.
            name_hits = sum(
                1
                for ingredient in ingredient_tokens
                if any(
                    _ingredient_tokens_match(ingredient, target)
                    for target in name_tokens
                )
            )
            exact_hits = sum(
                1
                for ingredient in ingredient_tokens
                if ingredient in searchable
            )
            ranked.append((name_hits, exact_hits, product.name.casefold(), product))

    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return [item[3] for item in ranked]


def _ingredient_catalog_answer(tenant, question):
    category, ingredients = _ingredient_query_parts(tenant, question)
    if not ingredients:
        return None

    products = _ingredient_catalog_products(
        tenant, ingredients, category=category
    )
    ingredient_label = " e ".join(ingredients)
    if not products:
        if category is not None:
            scope = f"opções de *{category.name}* com *{ingredient_label}*"
        else:
            scope = f"produtos com *{ingredient_label}*"
        return KnowledgeAnswer(
            "product_not_found",
            (
                f"Nenhum produto disponível do tenant corresponde a todos "
                f"os ingredientes consultados: {ingredient_label}.",
            ),
            f"Não encontrei {scope} no cardápio no momento 😕\n\n"
            f"Se quiser, você pode ver as opções disponíveis aqui:\n"
            f"👉 {catalog_url(tenant)}",
            context={"intent": "product_not_found"},
        )

    if category is not None:
        intro = (
            f"Encontrei estas opções de *{category.name}* com "
            f"*{ingredient_label}* 😊"
        )
    else:
        intro = f"Encontrei estas opções com *{ingredient_label}* 😊"

    blocks = [intro]
    # Ingredient searches are intentionally richer than generic catalog lists:
    # show the registered description so the customer can verify why each item
    # matched, plus the direct product link. Limit by message size rather than
    # an arbitrary count to avoid oversized WhatsApp messages.
    omitted = 0
    for index, product in enumerate(products):
        description = (product.description or "").strip()
        details = f"\n_{description[:180]}_" if description else ""
        block = (
            f"*{product.name}* — {_product_price_display(product)}"
            f"{details}\n👉 {product_url(tenant, product)}"
        )
        projected = "\n\n".join(blocks + [block])
        if len(projected) > 3400:
            omitted = len(products) - index
            break
        blocks.append(block)

    if omitted:
        blocks.append(
            f"Há mais *{omitted}* opção(ões) compatível(is). "
            f"Veja o cardápio completo:\n👉 {catalog_url(tenant)}"
        )

    return KnowledgeAnswer(
        "product",
        tuple(product_facts(tenant, products)) + (f"Catálogo: {catalog_url(tenant)}",),
        "\n\n".join(blocks),
        context={"intent": "product", "product_ids": [p.pk for p in products[:20]]},
    )


def _product_request_kind(question):
    raw = _strip_accents(str(question or "")).lower()
    if re.search(r"\+\s*barat", raw) or _has_any(question, ("mais barato", "mais em conta", "menor preco", "menor valor")):
        return "cheapest"
    if re.search(r"\+\s*caro", raw) or _has_any(question, ("mais caro", "maior preco", "maior valor")):
        return "expensive"
    if _has_any(question, ("link", "manda o link", "me manda", "me envia", "abrir produto")):
        return "link"
    if _looks_like_product_composition_question(question):
        return "description"
    if _has_tokenwise_any(
        question,
        (
            "adicional", "adicionais", "extra", "extras", "acrescimo",
            "acrescimos", "complemento", "complementos", "molho",
            "molhos", "borda", "bordas",
        ),
    ):
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

        generic_tokens = category_tokens | GENERIC_PRODUCT_TERMS | LOW_INFORMATION_PRODUCT_TERMS
        meaningful_name_tokens = name_tokens - generic_tokens
        specific_matches = matched_name & meaningful_name_tokens

        score = 0.0
        exact_name = bool(name_norm and name_norm in qnorm)
        if exact_name:
            score = max(score, 260 + len(name_norm))

        # Um token de baixa informação (ex.: "QA") não pode criar um match
        # de produto sozinho. Só pontuamos o nome quando há evidência
        # distintiva ou correspondência exata do nome completo.
        if matched_name and (specific_matches or exact_name):
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
            if target in LOW_INFORMATION_PRODUCT_TERMS:
                continue
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

    # Se a pergunta cita uma categoria conhecida + um termo distintivo que não
    # corresponde a nenhum produto (ex.: "tem hambúrguer de abacaxi?"), não
    # transformamos isso numa listagem genérica de hambúrgueres. É mais seguro
    # deixar o fluxo chegar ao product_not_found.
    if kind == "availability" and top["specificity"] == 0:
        category = _category_for_question(tenant, question)
        if category is not None:
            qtokens = _tokens(question)
            category_tokens = _tokens(category.name)
            extra = (
                qtokens
                - category_tokens
                - GENERIC_PRODUCT_TERMS
                - LOW_INFORMATION_PRODUCT_TERMS
                - PRODUCT_QUERY_NOISE_TERMS
            )
            if extra:
                return []

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
            f"*{product.name}* — {_product_price_display(product)}{emoji}\n"
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
            f"O *{product.name}* custa {_product_price_display(product)}{emoji}\n\n"
            f"Quer escolher os adicionais e colocar no carrinho?\n"
            f"👉 {url}"
        )

    return (
        f"Temos sim! 😊\n\n"
        f"*{product.name}* — {_product_price_display(product)}{emoji}\n"
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
    qtokens = _tokens(question) - GENERIC_PRODUCT_TERMS - LOW_INFORMATION_PRODUCT_TERMS
    for item in ranked[:6]:
        product = item["product"]
        if _product_available_today(product):
            continue

        if item["exact_name"]:
            return product

        name_tokens = _tokens(product.name)
        category_tokens = _tokens(product.category.name if product.category_id else "")
        meaningful = (name_tokens - category_tokens - GENERIC_PRODUCT_TERMS - LOW_INFORMATION_PRODUCT_TERMS)
        if not meaningful:
            continue
        matched = _matched_target_tokens(qtokens, meaningful)
        coverage = len(matched) / max(1, len(meaningful))
        # Produto indisponível só é anunciado com evidência distintiva real.
        # Isso evita um item aleatório por coincidências como "QA"/"produto".
        if matched and coverage >= 0.5:
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


def _promotions_answer(tenant, question=""):
    specific = _specific_product(tenant, question, context={}) if question else None
    if specific:
        if specific.has_discount and _product_available_today(specific):
            return KnowledgeAnswer(
                "promotion",
                (
                    f"{specific.name}: de {brl(specific.price)} por {brl(specific.effective_price)}.",
                    f"Link direto: {product_url(tenant, specific)}",
                ),
                f"Sim 🔥 O *{specific.name}* está de ~{brl(specific.price)}~ por *{brl(specific.effective_price)}*.\n\n👉 {product_url(tenant, specific)}",
                context={"intent": "product", "product_ids": [specific.pk]},
            )
        if _phrase_matches(question, specific.name) or _specificity_for_product(question, specific) > 0:
            return KnowledgeAnswer(
                "promotion",
                (f"{specific.name} não possui preço promocional ativo no cadastro.",),
                f"O *{specific.name}* não está com preço promocional ativo no momento 😊",
                context={"intent": "product", "product_ids": [specific.pk]},
            )

    category = _category_for_question(tenant, question) if question else None
    product_qs = Product.objects.filter(tenant=tenant, is_available=True)
    if category is not None:
        product_qs = product_qs.filter(category=category)
    products = [
        p for p in product_qs.select_related("category").order_by("name")[:300]
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


def _half_half_answer(tenant, question):
    if not _has_any(
        question,
        (
            "meio a meio", "meia a meia", "metade metade", "dois sabores",
            "2 sabores", "pizza meio", "sabores meio a meio",
        ),
    ):
        return None
    half_rows = list(
        HalfProduct.objects.filter(
            tenant=tenant, is_active=True, product__is_available=True
        ).select_related("product", "product__category").order_by("product__name")[:120]
    )

    # O signal legado cria HalfProduct para todo Product. Para o atendimento,
    # "meio a meio" é a regra de pizza do catálogo; portanto não podemos
    # anunciar bebida, sobremesa, porção etc. como "sabor" só porque existe
    # um HalfProduct automático.
    products = []
    for row in half_rows:
        product = row.product
        category_tokens = _tokens(product.category.name if product.category_id else "")
        product_tokens = _tokens(product.name)
        is_pizza = "pizza" in category_tokens or "pizza" in product_tokens
        if is_pizza and _product_available_today(product):
            products.append(product)
    if not products:
        return KnowledgeAnswer(
            "half_half",
            ("Não há produtos ativos habilitados para combinação meio a meio.",),
            "No momento não encontrei sabores habilitados para *meio a meio* no cardápio 😕",
            context={"intent": "half_half"},
        )
    visible = products[:6]
    lines = "\n".join(f"• {product.name}" for product in visible)
    if len(products) > len(visible):
        lines += f"\n• e mais {len(products) - len(visible)} sabor(es)"
    fallback = (
        "Fazemos *meio a meio* sim 🍕\n\n"
        "O valor base é o preço da opção mais cara entre os dois sabores; "
        "os adicionais escolhidos são somados normalmente.\n\n"
        f"Sabores habilitados:\n{lines}\n\n"
        f"👉 {catalog_url(tenant)}"
    )
    facts = tuple(
        ["Meio a meio está habilitado. O preço base é o da opção mais cara entre os dois produtos."]
        + [f"Sabor meio a meio disponível: {product.name}." for product in products]
        + [f"Catálogo: {catalog_url(tenant)}"]
    )
    return KnowledgeAnswer(
        "half_half", facts, fallback,
        context={"intent": "half_half", "product_ids": [p.pk for p in products[:5]]},
    )


def _fulfillment_answer(tenant, question):
    asks_pickup = _has_any(
        question,
        ("posso retirar", "faz retirada", "fazem retirada", "tem retirada", "retirar pedido", "buscar pedido", "posso buscar", "onde retiro", "onde busco", "retirada no local", "retirar ai", "posso pegar na loja", "pegar na loja", "pegar no local"),
    )
    asks_delivery = _has_any(
        question,
        ("faz entrega", "fazem entrega", "tem entrega", "voces entrega", "voces entregam", "vocês entregam", "entrega em casa", "trabalha com entrega", "faz delivery", "fazem delivery", "tem delivery", "trabalha com delivery"),
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
        all_target_tokens = _tokens(option.name)
        target_tokens = all_target_tokens - GENERIC_CUSTOMIZATION_TERMS
        # Se o nome for composto só por termo genérico, usamos o nome completo
        # apenas para correspondência exata; nunca aproximamos "extra" sozinho.
        matching_tokens = target_tokens or all_target_tokens
        matched = _matched_target_tokens(qtokens, matching_tokens)
        exact_name = bool(
            normalize(option.name) and normalize(option.name) in normalize(question)
        )

        if not matched and not exact_name:
            best = max(
                (_best_token_similarity(qtokens, token) for token in matching_tokens),
                default=0,
            )
            # Adicional específico exige evidência mais forte que busca de produto;
            # isso evita "cebola extra" retornar "bacon extra" por "extra".
            if best < 0.86:
                continue
            score = best
            match_count = 0
        else:
            match_count = len(matched)
            coverage = match_count / max(1, len(matching_tokens))
            score = (6 if exact_name else 0) + match_count * 3 + coverage

        ranked.append((score, match_count, exact_name, option))

    ranked.sort(
        key=lambda item: (-item[0], -item[1], not item[2], item[3].name.casefold())
    )
    if not ranked:
        return []

    top_score = ranked[0][0]
    # A pergunta por um adicional específico não deve trazer opções que só
    # coincidiram com palavras genéricas. Mantemos apenas empates reais do topo.
    return [item[3] for item in ranked if item[0] >= top_score - 0.05][:5]

def _customization_answer(tenant, question, product=None):
    matched_options = _find_customization_options(tenant, question, product=product)
    global_options = (
        matched_options
        if product is None
        else _find_customization_options(tenant, question, product=None)
    )
    q = normalize(question)
    q_tokens = set(q.split())

    # "Quais adicionais..." e frases como "tem extra pro hambúrguer X?"
    # pedem a lista do produto. Não devemos interpretar o nome do produto
    # (ex.: Bacon) como se fosse o nome do adicional "Bacon extra".
    list_request = any(
        phrase in q
        for phrase in (
            "quais adicionais", "que adicionais", "adicionais tem",
            "adicionais disponiveis", "opcoes de adicional",
            "opcoes adicionais", "quais extras", "extras tem",
            "tem extra pro", "tem extra para", "tem adicionais pro",
            "tem adicionais para", "extra pro", "extra para",
            "quais complementos", "que complementos", "complementos tem",
            "tem complementos", "quais acrescimos", "que acrescimos",
        )
    )
    price_request = any(
        phrase in q
        for phrase in (
            "quanto custa", "quanto e", "qual preco", "qual valor",
            "preco do", "preco de", "valor do", "valor de",
        )
    )
    action_request = bool(q_tokens & {"adicionar", "colocar", "acrescentar", "incluir"})

    product_tokens = _tokens(product.name) if product is not None else set()
    category_tokens = (
        _tokens(product.category.name)
        if product is not None and product.category_id
        else set()
    )
    meaningful_option_query = (
        _tokens(question)
        - GENERIC_CUSTOMIZATION_TERMS
        - GENERIC_PRODUCT_TERMS
        - LOW_INFORMATION_PRODUCT_TERMS
        - PRODUCT_QUERY_NOISE_TERMS
        - product_tokens
        - category_tokens
    )

    option_specific = (
        not list_request
        and (
            price_request
            or action_request
            or bool(global_options)
            or bool(meaningful_option_query)
        )
    )

    # A palavra da opção pode coincidir com o nome de outro produto (ex.:
    # "bacon extra" x "Combo Bacon"). Quando a pergunta identifica uma opção
    # de forma específica, a opção global tem prioridade sobre esse falso match
    # de produto. Nesse caso não anexamos link de um produto não solicitado.
    if option_specific and product is not None:
        if global_options and (not matched_options or matched_options[0].pk != global_options[0].pk):
            product = None
            matched_options = global_options

    if option_specific and not matched_options:
        suffix = f"\n\n👉 {product_url(tenant, product)}" if product else ""
        return KnowledgeAnswer(
            "customization",
            ("O adicional solicitado não foi encontrado entre as opções ativas cadastradas.",),
            "Não encontrei esse adicional entre as opções disponíveis no momento 😕" + suffix,
            context={"intent": "product", "product_ids": [product.pk]} if product else {"intent": "customization"},
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
        if len(matched_options) == 1:
            option = matched_options[0]
            fallback = f"O adicional *{option.name}* custa *+{brl(option.price)}* 😊{suffix}"
        else:
            fallback = "Encontrei estas opções 😊\n\n" + "\n".join(lines) + suffix
        return KnowledgeAnswer(
            "customization", tuple(facts), fallback,
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


def _specificity_for_product(question, product):
    qtokens = _tokens(question)
    name_tokens = _tokens(product.name)
    category_tokens = _tokens(product.category.name if product.category_id else "")
    generic_tokens = category_tokens | GENERIC_PRODUCT_TERMS | LOW_INFORMATION_PRODUCT_TERMS
    matched = _matched_target_tokens(qtokens, name_tokens)
    return len({token for token in matched if token not in generic_tokens})


def _category_for_question(tenant, question):
    qtokens = _tokens(question)
    categories = {}
    for product in Product.objects.filter(tenant=tenant).select_related("category").order_by().distinct():
        if product.category_id:
            categories[product.category_id] = product.category
    best = None
    best_score = 0.0
    for category in categories.values():
        tokens = _tokens(category.name)
        if not tokens:
            continue
        matched = _matched_target_tokens(qtokens, tokens)
        coverage = len(matched) / max(1, len(tokens))
        similarity = sum(_best_token_similarity(qtokens, t) for t in tokens) / max(1, len(tokens))
        score = coverage * 2 + similarity
        if coverage >= 0.8 and score > best_score:
            best, best_score = category, score
    return best


def _product_price_display(product):
    if product.has_discount:
        return f"~{brl(product.price)}~ → *{brl(product.effective_price)}* 🔥"
    return brl(product.effective_price)


def _product_comparison_answer(tenant, question, context=None):
    kind = _product_request_kind(question)
    if kind not in {"cheapest", "expensive"}:
        return None
    category = _category_for_question(tenant, question)
    previous = _context_products(tenant, context or {}) if category is None else []
    if previous:
        products = previous
    else:
        qs = Product.objects.filter(tenant=tenant, is_available=True).select_related("category")
        if category is not None:
            qs = qs.filter(category=category)
        products = [p for p in qs[:300] if _product_available_today(p)]
    if not products:
        return None
    reverse = kind == "expensive"
    product = sorted(products, key=lambda p: (p.effective_price, p.name.casefold()), reverse=reverse)[0]
    adjective = "mais caro" if reverse else "mais barato"
    scope = f" entre os produtos de *{category.name}*" if category is not None else " do cardápio"
    text = (
        f"O {adjective}{scope} é o *{product.name}* por *{brl(product.effective_price)}* 😊\n\n"
        f"👉 {product_url(tenant, product)}"
    )
    return KnowledgeAnswer(
        "product",
        (f"{product.name}: {brl(product.effective_price)}.", f"Link direto: {product_url(tenant, product)}"),
        text,
        context={"intent": "product", "product_ids": [product.pk]},
    )


def _generic_characteristic_answer(tenant, kind, question=""):
    category = _category_for_question(tenant, question) if question else None
    qs = Product.objects.filter(tenant=tenant, is_available=True)
    if category is not None:
        qs = qs.filter(category=category)
    products = [
        p for p in qs.select_related("category").order_by("name")[:300]
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
    if not product.is_available:
        reason = "não está disponível no momento"
        fact = "está marcado como indisponível"
    elif product.stock is not None and product.stock <= 0:
        reason = "está esgotado no momento"
        fact = "está sem estoque"
    else:
        reason = "não está disponível hoje"
        fact = "não está disponível no dia de hoje"
    return KnowledgeAnswer(
        "product_unavailable",
        (
            f"{product.name} existe no cadastro e {fact}.",
            f"Catálogo: {catalog_url(tenant)}",
        ),
        f"O *{product.name}* {reason} 😕\n\nSe quiser, posso te mostrar outras opções do cardápio:\n👉 {catalog_url(tenant)}",
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

    # Uma nova pergunta explícita de produto/preço deve encerrar o contexto
    # elíptico de entrega. Ex.: após consultar Centro/Itapevi,
    # "qnt custa o hamb bacon?" precisa consultar o produto, não repetir a taxa.
    product_kind = _product_request_kind(question)
    if product_kind in {"price", "link", "description", "customization", "details"}:
        if _category_for_question(tenant, question) is not None or _rank_products(tenant, question):
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

def _looks_like_order_status(question):
    return _has_any(
        question,
        (
            "status do pedido", "meu pedido", "cade meu pedido", "onde esta meu pedido",
            "pedido saiu", "pedido foi confirmado", "pedido confirmado", "pedido chegou",
            "acompanhar pedido", "rastrear pedido", "cancelar meu pedido",
            "alterar meu pedido", "mudar meu pedido", "vai demorar meu pedido",
            "pedido atrasado", "meu pedido atrasou", "quando chega meu pedido",
            "quanto falta meu pedido", "confirmou meu pedido", "confirmaram meu pedido",
        ),
    )


def _asks_delivery_eta(question, context=None):
    q = normalize(question)

    # Prazo total de entrega não é um dado modelado no VemDeDelivery.
    # Reconhecemos variações naturais da pergunta sem confundir com o
    # tempo de preparo de um produto.
    explicit = (
        _has_any(
            question,
            (
                "tempo de entrega", "prazo de entrega", "quanto tempo entrega",
                "quanto demora entrega", "quanto tempo demora a entrega",
                "quanto tempo demora entrega", "demora pra chegar",
                "demora para chegar", "chega em quanto", "tempo pra chegar",
                "tempo para chegar", "quando chega a entrega",
            ),
        )
        or (
            "entrega" in q
            and any(
                term in q
                for term in (
                    "quanto tempo", "quanto demora", "demora",
                    "prazo", "quando chega", "tempo pra chegar",
                    "tempo para chegar",
                )
            )
        )
    )
    if explicit:
        return True

    return bool(
        isinstance(context, dict)
        and context.get("intent") in {"delivery", "delivery_fee", "delivery_areas"}
        and any(term in q for term in ("quanto tempo", "demora", "quando chega", "prazo"))
    )


def _looks_like_human_request(question):
    terms = (
        "falar com atendente", "falar com uma pessoa", "falar com pessoa",
        "atendimento humano", "quero atendente", "chamar atendente",
        "falar com a loja", "quero falar com alguem", "quero falar com humano",
        "falar com humano", "quero humano", "atendente humano", "tem atendente",
        "preciso de atendente", "tem alguem ai", "alguem ai", "tem alguem",
        "quero falar com responsavel", "chama um atendente", "chame um atendente",
        "chama atendente", "quero uma pessoa", "quero uma pessoa de verdade",
    )
    # Atendimento humano é uma intenção de alto impacto porque pausa a IA.
    # Portanto não usamos fuzzy matching aqui: ``alguma`` não pode casar com
    # ``alguem`` em frases como "tem alguma coisa com bacon?".
    return _has_exact_phrase(question, terms)


def _looks_like_payment(question):
    q = normalize(question)
    payment_tokens = {
        "pagamento", "pagar", "pago", "paga", "pix", "cartao", "dinheiro",
        "debito", "credito", "troco", "checkout", "boleto", "alelo",
        "sodexo", "pluxee", "ticket",
    }
    if set(q.split()) & payment_tokens:
        return True
    return _has_exact_phrase(
        question,
        (
            "forma de pagamento", "formas de pagamento", "pelo site",
            "no site", "pagamento online", "vale refeicao",
            "vale alimentacao", "cartao refeicao", "cartao alimentacao",
            "ticket refeicao", "ticket alimentacao",
        ),
    )


def _business_info_unknown(question):
    terms = (
        "estacionamento", "tem mesa", "mesas", "comer no local", "comer ai",
        "wifi", "wi fi", "banheiro", "pet friendly", "aceita pet",
        "telefone do gerente", "numero do gerente", "tem brinquedoteca",
    )
    # Evita colisões fuzzy como "dinheiro" -> "banheiro".
    return _has_exact_phrase(question, terms)


def _courtesy_answer(question, context):
    q = normalize(question)
    thanks = {"obrigado", "obrigada", "valeu", "agradeco", "muito obrigado", "muito obrigada"}
    goodbye = {"tchau", "ate mais", "falou", "ate logo", "boa noite tchau"}
    ack = {"ok", "okay", "beleza", "show", "certo", "fechou", "entendi", "perfeito"}
    if q in thanks:
        return KnowledgeAnswer("thanks", (), "Por nada! 😊 Se precisar de mais alguma coisa, é só mandar uma mensagem.")
    if q in goodbye:
        return KnowledgeAnswer("goodbye", (), "Até mais! 😊")
    if q in ack:
        return KnowledgeAnswer("ack", (), "Perfeito 😊")
    if q == "nao":
        return KnowledgeAnswer("ack", (), "Tudo bem 😊")
    return None


def _payment_answer(tenant, question):
    from apps.billing.online import online_payment_available

    if tenant.accepts_delivery and tenant.accepts_pickup:
        location = "na entrega ou retirada"
    elif tenant.accepts_delivery:
        location = "na entrega"
    else:
        location = "na retirada"

    online = online_payment_available(tenant)
    asks_online = _has_any(question, ("online", "pelo site", "no site", "checkout", "pagamento no site"))
    unsupported = _has_exact_phrase(
        question,
        (
            "boleto", "vale refeicao", "vale alimentacao", "cartao refeicao",
            "cartao alimentacao", "vr", "va", "alelo", "sodexo", "pluxee",
            "ticket refeicao", "ticket alimentacao",
        ),
    )
    if unsupported:
        return KnowledgeAnswer(
            "payment",
            ("As opções padrão cadastradas são Pix, crédito, débito e dinheiro no atendimento presencial.",),
            "Essa forma de pagamento não aparece entre as opções padrão cadastradas aqui. Para confirmar se a loja aceita, fale diretamente com a equipe 😊",
            context={"intent": "payment"},
        )
    if _has_any(question, ("troco", "trocar dinheiro")):
        return KnowledgeAnswer(
            "payment",
            (f"Dinheiro é aceito {location}.",),
            f"Pagamento em dinheiro está disponível {location} 💵\n\nSe precisar de troco, combine o valor com a loja ao finalizar o pedido.",
            context={"intent": "payment"},
        )
    if asks_online:
        if online:
            return KnowledgeAnswer(
                "payment",
                ("Pagamento online disponível por Pix e cartão de crédito.",),
                "Sim 😊💳 No checkout da loja você pode pagar online por *Pix* ou *cartão de crédito*.",
                context={"intent": "payment"},
            )
        return KnowledgeAnswer(
            "payment",
            ("Pagamento online não está habilitado para esta loja.", f"Pix, crédito, débito e dinheiro estão disponíveis {location}."),
            f"No momento, o pagamento online não está habilitado para esta loja.\n\n{location.capitalize()}: Pix, cartão de crédito, cartão de débito ou dinheiro.",
            context={"intent": "payment"},
        )

    text = payment_text(tenant)
    if _has_any(question, ("quais", "forma de pagamento", "formas de pagamento", "como posso pagar", "como pagar")):
        fallback = f"As formas de pagamento disponíveis são 😊💳\n\n{text}"
    else:
        fallback = f"Aceitamos sim 😊💳\n\n{text}"
    return KnowledgeAnswer("payment", (text,), fallback, context={"intent": "payment"})


def _catalog_or_order_start_answer(tenant, question, context):
    q = normalize(question)
    catalog_terms = (
        "cardapio", "menu", "me manda o cardapio", "manda o cardapio",
        "ver cardapio", "ver menu", "ver produtos", "ver opcoes",
        "mais opcoes", "mostra mais", "quero ver mais",
    )
    order_terms = (
        "quero fazer um pedido", "fazer um pedido", "quero fazer pedido",
        "fazer pedido", "como fazer pedido",
        "como faco pedido", "como pedir", "quero pedir", "quero comprar",
        "onde faco pedido", "onde fazer pedido",
    )
    if _has_any(question, catalog_terms) or _has_any(question, order_terms):
        return KnowledgeAnswer(
            "catalog",
            (f"Catálogo: {catalog_url(tenant)}",),
            f"Claro! 😊 Você pode ver o cardápio e montar seu pedido por aqui:\n👉 {catalog_url(tenant)}",
            context={"intent": "catalog"},
        )
    if q == "sim" and context.get("intent") == "product":
        return KnowledgeAnswer(
            "catalog",
            (f"Catálogo: {catalog_url(tenant)}",),
            f"Claro 😊 Veja todas as opções no cardápio:\n👉 {catalog_url(tenant)}",
            context={"intent": "catalog"},
        )
    return None


def _looks_like_product_question(question):
    q = normalize(question)
    if _has_any(question, ("cardapio", "produto", "produtos", "item", "itens", "vende", "vendem", "tem", "possui", "trabalha com", "trabalham com")):
        leftovers = _tokens(question) - {
            "entrega", "retirada", "pagamento", "horario", "endereco",
            "promocao", "taxa", "frete", "bairro", "cidade",
        }
        return bool(leftovers)
    return False


def _requested_product_label(question):
    text = str(question or "").strip().strip("?.! ")
    text = re.sub(
        r"^(?:oi[, ]+)?(?:(?:vcs?|voc[eê]s?)\s+)?(?:tem|t[eê]m|vende|vendem|possui|tem algum[a]?|trabalha(?:m)? com)\s+",
        "", text, flags=re.IGNORECASE,
    )
    return text.strip().strip("?.! ")[:120] or "esse item"


def answer_from_store(tenant, question, context=None):
    context = context if isinstance(context, dict) else {}
    q = normalize(question)

    courtesy = _courtesy_answer(question, context)
    if courtesy:
        return courtesy

    # Saudações puras precisam ser resolvidas antes da busca fuzzy de produtos.
    # Sem isso, "Olá" pode se aproximar de "Cola" e retornar Coca-Cola.
    greeting_words = ("oi", "ola", "bom dia", "boa tarde", "boa noite", "e ai", "eai")
    if q in greeting_words:
        return KnowledgeAnswer(
            "greeting",
            (f"Nome da loja: {tenant.name}.", f"Catálogo: {catalog_url(tenant)}"),
            f"Oi! 😊 Sou o assistente da *{tenant.name}*. Posso te ajudar com o cardápio, entrega, retirada, endereço, horários, promoções e formas de pagamento.",
        )

    # Status/alteração/cancelamento de pedido precisa ter prioridade sobre
    # expressões genéricas como "pedido", que também aparecem na intenção de
    # iniciar uma compra/cardápio.
    if _looks_like_order_status(question):
        return KnowledgeAnswer(
            "order_status",
            ("O agente não acompanha status, alteração ou cancelamento de pedido.",),
            "Para acompanhar, alterar ou cancelar um pedido, a equipe da loja precisa continuar com você por aqui 😊",
            pause_minutes=60,
            pause_reason="human",
        )

    catalog_answer = _catalog_or_order_start_answer(tenant, question, context)
    if catalog_answer:
        return catalog_answer

    if _asks_delivery_eta(question, context):
        return KnowledgeAnswer(
            "delivery_eta",
            ("Não há prazo total de entrega confiável cadastrado no agente.",),
            "Não tenho um prazo total de entrega cadastrado para te informar com segurança 😕\n\nPosso consultar a *taxa de entrega*; para estimativa de chegada, confirme com a equipe da loja.",
            context={"intent": "delivery_eta"},
        )

    # Pagamento e atendimento humano ficam antes de informações genéricas da
    # loja. Assim, "dinheiro" não pode colidir com "banheiro" e expressões
    # como "tem alguém aí?" não viram busca de produto.
    if _looks_like_payment(question):
        return _payment_answer(tenant, question)

    if _looks_like_human_request(question):
        return KnowledgeAnswer(
            "human",
            ("O cliente pediu atendimento humano.",),
            "Claro 😊 Vou deixar a conversa livre para a equipe da loja continuar com você por aqui.",
            pause_minutes=60,
            pause_reason="human",
        )

    if _business_info_unknown(question):
        return KnowledgeAnswer(
            "business_info",
            ("A informação solicitada não é modelada no cadastro da loja.",),
            "Essa informação não está cadastrada por aqui no momento 😕 Para confirmar, fale diretamente com a equipe da loja.",
            context={"intent": "business_info"},
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

    # "Como funciona a pizza meio a meio?" contém "funciona", mas é uma
    # pergunta sobre a regra meio a meio, não sobre horário de funcionamento.
    half_half = _half_half_answer(tenant, question)
    if half_half:
        return half_half

    hours_words = (
        "horario", "abre", "aberto", "aberta", "fecha", "fechado",
        "fechada", "funciona", "funcionamento", "que horas",
    )
    if _has_tokenwise_any(question, hours_words):
        schedule = hours_text(tenant)
        open_now = tenant.is_open_now()
        specific = _specific_hours_answer(tenant, question)
        return KnowledgeAnswer(
            "hours",
            (f"Horários cadastrados: {schedule}.", f"A loja está {'aberta' if open_now else 'fechada'} neste momento."),
            specific or f"🕒 Estes são os horários da loja:\n{schedule}",
            context={"intent": "hours"},
        )

    if _looks_like_payment(question):
        return _payment_answer(tenant, question)

    promotion_words = (
        "promocao", "promocoes", "oferta", "ofertas", "desconto", "descontos",
        "cupom", "cupons", "em promocao",
    )
    if _has_any(question, promotion_words):
        return _promotions_answer(tenant, question)

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

    description_intent = _looks_like_product_composition_question(question)
    # Personalização usa correspondência por token/frase inteira. Isso evita
    # falso positivo como ``extraterrestre`` contendo a substring ``extra``.
    customization_intent = _has_tokenwise_any(
        question,
        (
            "adicional", "adicionais", "extra", "extras", "acrescimo",
            "acrescimos", "complemento", "complementos", "molho",
            "molhos", "borda", "bordas",
        ),
    )
    characteristic = _characteristic_kind(question)

    # Produto explicitamente citado antes do verbo: ``Pizza Portuguesa leva
    # frango?`` é pergunta sobre a composição daquele produto, não uma busca
    # ampla por todas as pizzas com frango. Intenções mais específicas
    # (alérgenos/características e personalização) continuam tendo prioridade.
    explicit_subject_product = _explicit_product_subject_product(
        tenant, question
    )
    if (
        explicit_subject_product is not None
        and not customization_intent
        and not characteristic
    ):
        return _product_description_answer(tenant, explicit_subject_product)

    # Busca ampla por ingrediente vem antes da descrição genérica porque
    # perguntas como ``tem hamburguer que leva cebola?`` também contêm vocabulário
    # de composição, mas querem uma lista de produtos, não um único item.
    ingredient_catalog = _ingredient_catalog_answer(tenant, question)
    if ingredient_catalog:
        return ingredient_catalog

    if description_intent:
        product = _composition_product(tenant, question, context)
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
        generic = _generic_characteristic_answer(tenant, characteristic, question)
        if generic:
            return generic
        return KnowledgeAnswer(
            "product_details", ("A informação solicitada depende de um produto específico.",),
            "Claro 😊 Me diga *qual produto* você quer consultar.",
            context={"intent": "product_details"},
        )

    comparison = _product_comparison_answer(tenant, question, context=context)
    if comparison:
        return comparison

    # Um produto explicitamente citado, mas indisponível, deve vencer sugestões
    # genéricas da mesma categoria. Ex.: "tem hambúrguer esgotado QA?".
    unavailable = _unavailable_product(tenant, question)
    if unavailable:
        return _unavailable_answer(tenant, unavailable)

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

    previous_products = _context_products(tenant, context)
    ordinal_map = {
        "primeiro": 0, "primeira": 0, "1": 0,
        "segundo": 1, "segunda": 1, "2": 1,
        "terceiro": 2, "terceira": 2, "3": 2,
    }
    ordinal_index = next(
        (index for token, index in ordinal_map.items() if token in q.split()),
        None,
    )
    if previous_products and ordinal_index is not None and ordinal_index < len(previous_products):
        product = previous_products[ordinal_index]
        return KnowledgeAnswer(
            "product", tuple(product_facts(tenant, [product])),
            _single_product_fallback(
                tenant, product, request_kind=_product_request_kind(question)
            ),
            context={"intent": "product", "product_ids": [product.pk]},
        )

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

    if _looks_like_product_question(question):
        label = _requested_product_label(question)
        return KnowledgeAnswer(
            "product_not_found",
            (f"Não foi encontrado produto correspondente a: {label}.", f"Catálogo: {catalog_url(tenant)}"),
            f"Não encontrei *{label}* no nosso cardápio no momento 😕\n\nSe quiser, você pode ver as opções disponíveis aqui:\n👉 {catalog_url(tenant)}",
            context={"intent": "product_not_found"},
        )

    if any(q.startswith(word + " ") for word in greeting_words):
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
