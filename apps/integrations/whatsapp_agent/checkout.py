"""Deterministic conversational checkout; all prices come from cart_service."""

import re
import uuid
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.billing.asaas_fields import clean_document
from apps.billing.online import online_payment_available
from apps.integrations.models import (
    WhatsAppCheckout,
    WhatsAppCheckoutReceipt,
    TenantWhatsAppConversation,
)
from apps.orders import cart_service as cart_rules
from apps.orders.models import Cart, OrderItem
from apps.orders.services import brl, build_item_message
from apps.stores.models import Product, CustomizationGroup
from apps.tenants.delivery import resolve_delivery
from .knowledge import normalize, _looks_like_human_request


@dataclass
class CheckoutReply:
    text: str
    choices: list = field(default_factory=list)
    intent: str = "checkout"
    context: dict = field(default_factory=dict)
    pause_minutes: int = 0
    pause_reason: str = ""
    pix_checkout_id: int = 0


def reply(text, choices=(), **kwargs):
    choices = list(choices)
    if choices:
        text += "\n\n" + "\n".join(
            f"{i}. {label}" for i, (_, label) in enumerate(choices, 1)
        )
        text += "\n\nPode tocar numa opção ou responder pelo número."
    return CheckoutReply(text, choices, **kwargs)


def menu():
    return reply(
        "O que você quer fazer agora?",
        [
            ("add", "Adicionar item"),
            ("review", "Ver carrinho"),
            ("finish", "Finalizar"),
        ],
    )


def parse_money(text):
    raw = re.sub(r"[^0-9,.]", "", text)
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        value = Decimal(raw)
        if not value.is_finite() or value < 0 or value > Decimal("9999999.99"):
            raise ValueError()
        return value.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise cart_rules.CartError(
            "Me diga um valor válido, por exemplo: 100,00."
        ) from None


def catalog(c, search=""):
    products = Product.objects.filter(tenant=c.cart.tenant, is_available=True).order_by(
        "name"
    )
    if search:
        products = products.filter(name__icontains=search)
    rows = []
    for p in products:
        if p.available_days and timezone.localdate().weekday() not in p.available_days:
            continue
        if p.stock is not None and p.stock <= 0:
            continue
        rows.append(
            (f"product:{p.pk}", f"{p.name} — {brl(cart_rules.product_price(p))}")
        )
    page = max(0, int(c.data.get("page", 0)))
    visible = rows[page * 8 : page * 8 + 8]
    if not visible and page:
        c.data["page"] = 0
        return catalog(c, search)
    if len(rows) > (page + 1) * 8:
        visible.append(("next", "Mais produtos"))
    if page:
        visible.append(("previous", "Voltar página"))
    c.step = "product"
    return reply(
        (
            "Vamos montar seu pedido 🙂\n\nEscolha um produto ou escreva o nome dele."
            if rows
            else "Não encontrei esse produto disponível. Tente outro nome."
        ),
        visible,
    )


def groups(c):
    p = cart_rules.available_product(c.cart.tenant, c.data["pending"]["product_id"])
    return list(
        CustomizationGroup.objects.filter(
            tenant=c.cart.tenant, category_id=p.category_id, is_active=True
        )
        .select_related("label")
        .prefetch_related("options")
        .order_by("pk")
    )


def ask_additions(c):
    available = groups(c)
    index = c.data.get("group_index", 0)
    if index >= len(available):
        c.step = "notes"
        if c.data.get("dialogue_note"):
            return reply(
                f"Anotei para este item: *{c.data['dialogue_note']}*.\n\nQuer manter ou escrever outra observação?",
                [
                    ("dialogue_keep_note", "Manter observação"),
                    ("none", "Sem observação"),
                ],
            )
        return reply(
            "Quer deixar alguma observação para esse item?\n\nPor exemplo: *retirar cebola* ou *bem passado*.",
            [("none", "Sem observação")],
        )
    g = available[index]
    c.step = "additions"
    selected = c.data["pending"].get("customizations", [])
    chosen = {str(x["option_id"]) for x in selected if str(x["group_id"]) == str(g.pk)}
    choices = [
        (
            f"option:{o.pk}",
            f"{'✓ ' if str(o.pk) in chosen else ''}{o.name} (+{brl(o.price)})",
        )
        for o in g.options.all()
        if o.is_available and o.tenant_id == c.cart.tenant_id
    ]
    choices.append(("done", "Continuar"))
    return reply(
        f"*{g.name or 'Adicionais'}*\n\nEscolha de {g.min_options} a {g.max_options} opção(ões).\nToque novamente para retirar uma opção.\nValores por unidade.",
        choices,
    )


def totals(c):
    items, changes = cart_rules.refresh_cart(c.cart)
    if not items:
        raise cart_rules.CartError(
            "Seu carrinho está vazio. Adicione um produto primeiro."
        )
    subtotal = sum((i.get_total_price() for i in items), Decimal("0"))
    d = c.data
    delivery = resolve_delivery(
        c.cart.tenant,
        d.get("delivery_type", "pickup"),
        d.get("delivery_city", ""),
        d.get("delivery_neighborhood", ""),
    )
    if not delivery["available"]:
        raise cart_rules.CartError(delivery["message"])
    return items, subtotal, delivery["fee"], subtotal + delivery["fee"], changes


def cart_text(c):
    items = list(c.cart.items.order_by("pk"))
    if not items:
        return "Seu carrinho está vazio."
    items = [
        OrderItem(
            name=i.name,
            price=i.price,
            quantity=i.quantity,
            combination_details=i.combination_details,
            notes=i.notes or "",
        )
        for i in items
    ]
    return (
        "*Seu carrinho*\n\n"
        + "\n\n".join(
            f"*Item {i}*\n{build_item_message(item)}" for i, item in enumerate(items, 1)
        )
        + f"\n\nSubtotal: *{brl(sum((x.get_total_price() for x in items), Decimal('0')))}*"
    )


def review(c):
    from apps.checkout.views import get_pickup_address

    items, subtotal, fee, total, changes = totals(c)
    d = c.data
    if d["delivery_type"] == "pickup":
        address = get_pickup_address(c.cart.tenant)
        if not c.cart.tenant.accepts_pickup or not address:
            raise cart_rules.CartError(
                "A retirada não está disponível. Escolha entrega ou fale com a loja."
            )
    else:
        address = ", ".join(
            d.get(k, "")
            for k in (
                "delivery_street",
                "delivery_number",
                "delivery_complement",
                "delivery_neighborhood",
                "delivery_city",
                "delivery_state",
            )
            if d.get(k)
        )
        address += "\n" + " · ".join(
            d.get(k, "")
            for k in ("delivery_zip_code", "delivery_reference")
            if d.get(k)
        )
    method = {
        "cash": "Dinheiro",
        "pix": "Pix",
        "debit_card": "Débito",
        "credit_card": "Crédito",
    }[d["payment_method"]]
    payment = (
        "Pix online — aguardará confirmação do Asaas"
        if d["payment_flow"] == "online"
        else f"{method} na {'entrega' if d['delivery_type'] == 'delivery' else 'retirada'}"
    )
    if d["payment_method"] == "cash":
        change = d.get("payment_change_for", "")
        if change and Decimal(change) < total:
            c.step = "change"
            return reply(
                f"O total é {brl(total)}. Para qual valor você precisa de troco?",
                [("none", "Não preciso de troco")],
            )
        payment += (
            f"\nTroco para {brl(Decimal(change))}: {brl(Decimal(change) - total)}"
            if change
            else "\nSem troco"
        )
    fields = {
        k: v
        for k, v in d.items()
        if k.startswith("delivery_")
        or k
        in {"customer_name", "payment_method", "payment_flow", "payment_change_for"}
    }
    fields["customer_phone"] = c.conversation.phone_number
    c.snapshot = {
        "fields": fields,
        "subtotal": str(subtotal),
        "delivery_fee": str(fee),
        "total": str(total),
        "items": [
            {
                "product_id": i.product_id,
                "name": i.name,
                "price": str(i.price),
                "quantity": i.quantity,
                "combination_details": i.combination_details,
                "product_key": i.product_key,
                "notes": i.notes or "",
            }
            for i in items
        ],
    }
    c.step = "confirm"
    return reply(
        (
            "Os valores foram atualizados. Confira novamente.\n\n"
            if changes
            else "Confira se ficou tudo certinho 🙂\n\n"
        )
        + cart_text(c)
        + f"\n\nCliente: {d['customer_name']}\n{'Entrega' if d['delivery_type'] == 'delivery' else 'Retirada'}: {address}\n\nFrete: {brl(fee)}\n*Total: {brl(total)}*\n\n*Pagamento*\n{payment}",
        [
            ("confirm", "Confirmar pedido"),
            ("edit", "Alterar pedido"),
            ("cancel", "Cancelar carrinho"),
        ],
    )


def payment_choices(c):
    c.step = "payment"
    choices = [
        ("pix", "Pix na entrega/retirada"),
        ("debit_card", "Débito na entrega/retirada"),
        ("credit_card", "Crédito na entrega/retirada"),
        ("cash", "Dinheiro"),
    ]
    if online_payment_available(c.cart.tenant):
        choices.insert(0, ("online_pix", "Pix online agora"))
    return reply("Como você prefere pagar?", choices)


ADDRESS = [
    ("delivery_city", "Qual é a cidade da entrega?", 100),
    ("delivery_neighborhood", "E o bairro?", 100),
    ("delivery_street", "Qual é a rua ou avenida?", 255),
    ("delivery_number", "Qual é o número? Pode informar s/n.", 20),
    ("delivery_state", "Qual é a UF? Exemplo: SP.", 2),
    ("delivery_zip_code", "Qual é o CEP?", 9),
    ("delivery_complement", "Tem complemento, como bloco ou apartamento?", 100),
    ("delivery_reference", "Algum ponto de referência para facilitar a entrega?", 255),
]


def ask_address(c):
    idx = c.data.get("address_index", 0)
    if idx >= len(ADDRESS):
        return payment_choices(c)
    c.step = "address"
    key, prompt, _ = ADDRESS[idx]
    return reply(
        prompt,
        (
            [("none", "Não tem")]
            if key in {"delivery_complement", "delivery_reference"}
            else []
        ),
    )


def transition(c, text, action):
    from .checkout_payments import confirm_checkout, cancel_payment

    norm = normalize(text)
    if c.status in {"issuing", "pending", "uncertain"}:
        if action == "cancel" or norm in {
            "cancelar",
            "cancelar pedido",
            "cancelar carrinho",
        }:
            return cancel_payment(c)
        return reply(
            "Seu Pix está aguardando confirmação. Assim que o Asaas confirmar, envio o pedido para a loja.\n\nNão precisa enviar comprovante. Para tentar recuperar o código, responda *Pix*.",
            [("pix_retry", "Ver Pix"), ("cancel", "Cancelar Pix")],
            pix_checkout_id=c.pk,
        )
    if c.status == "paid_waiting":
        return reply(
            "Seu Pix foi confirmado pelo Asaas. A loja precisa revisar a disponibilidade dos itens antes de concluir o pedido. Não pague novamente. Escreva *atendente*. "
        )
    if c.status == "payment_review":
        return reply(
            "Seu pagamento precisa de revisão pela loja. Escreva *atendente* para continuar."
        )
    if c.status == "completed":
        return reply(
            f"Seu pedido #{c.order_id} já foi confirmado. Para começar outro, escreva *novo pedido*."
        )
    if action == "cancel" or norm in {"cancelar", "cancelar carrinho"}:
        c.status = "cancelled"
        c.cart.items.all().delete()
        return reply(
            "Carrinho cancelado. Quando quiser, é só escrever *novo pedido* 🙂"
        )
    if norm in {"carrinho", "ver carrinho", "meu carrinho"} or action == "review":
        c.step = "menu"
        return reply(
            cart_text(c),
            [
                ("add", "Adicionar item"),
                ("finish", "Finalizar"),
                ("edit", "Alterar pedido"),
            ],
        )
    match = re.fullmatch(r"(?:remover|tirar)\s+(?:item\s+)?(\d+)", norm)
    if match:
        items = list(c.cart.items.order_by("pk"))
        idx = int(match[1]) - 1
        if not 0 <= idx < len(items):
            raise cart_rules.CartError(
                "Esse item não está no carrinho. Escreva *carrinho* para ver os números."
            )
        items[idx].delete()
        c.step = "menu"
        return reply("Item removido.\n\n" + cart_text(c), menu().choices)
    if action == "edit" or norm == "alterar pedido":
        c.step = "menu"
        return reply(
            "Você pode adicionar itens, escrever *remover 2* para tirar o item 2, ou finalizar novamente para alterar entrega e pagamento.",
            menu().choices,
        )
    if action == "finish" or norm in {"finalizar", "fechar pedido", "finalizar pedido"}:
        if not c.cart.items.exists():
            return catalog(c)
        c.step = "name"
        return reply("Para quem será o pedido? Me diga seu nome.")
    if action == "add" or norm in {
        "adicionar",
        "adicionar item",
        "mais um",
        "novo pedido",
        "pedido",
        "pedir",
        "fazer pedido",
        "quero pedir",
        "quero fazer um pedido",
        "fazer um pedido",
        "quero fazer pedido",
        "quero comprar",
        "comprar",
    }:
        c.data["page"] = 0
        return catalog(c)
    if c.step == "product":
        if action in {"next", "previous"}:
            c.data["page"] = c.data.get("page", 0) + (1 if action == "next" else -1)
            return catalog(c)
        if action.startswith("product:"):
            p = cart_rules.available_product(c.cart.tenant, action.split(":")[1])
        else:
            search = re.sub(
                r"^(eu )?(quero|gostaria de|adicionar|me ve|me da|vou querer)\s+",
                "",
                norm,
            ).strip()
            count = 0
            m = re.match(r"^(\d+)\s*(?:x\s*)?(.+)$", search)
            if m:
                count, search = int(m[1]), m[2]
            candidates = [
                p
                for p in Product.objects.filter(tenant=c.cart.tenant, is_available=True)
                if normalize(p.name) == search or search in normalize(p.name)
            ]
            if len(candidates) != 1:
                c.data["page"] = 0
                return catalog(c, text if len(candidates) == 0 else "")
            p = cart_rules.available_product(c.cart.tenant, candidates[0].pk)
            if count:
                c.data["suggested_count"] = count
        c.data["pending"] = {"product_id": p.pk, "customizations": []}
        c.step = "quantity"
        suggested = c.data.pop("suggested_count", 0)
        if suggested:
            return transition(c, str(suggested), "")
        return reply(
            f"Boa! Quantas unidades de *{p.name}* você quer?",
            [("qty:1", "1 unidade"), ("qty:2", "2 unidades")],
        )
    if c.step == "quantity":
        raw = (
            action.split(":")[1]
            if action.startswith("qty:")
            else re.sub(r"^(quero |vai ser |pode ser )", "", norm)
            .replace(" unidades", "")
            .strip()
        )
        from .dialogue import NUMBERS

        raw = str(NUMBERS.get(raw, raw))
        if not raw.isdigit():
            raise cart_rules.CartError(
                "Me diga a quantidade em número, por exemplo: 2."
            )
        c.data["count"] = cart_rules.quantity(int(raw))
        c.data["group_index"] = 0
        return ask_additions(c)
    if c.step == "additions":
        g = groups(c)[c.data["group_index"]]
        selected = c.data["pending"]["customizations"]
        own = [x for x in selected if str(x["group_id"]) == str(g.pk)]
        if action == "done" or norm in {
            "continuar",
            "pronto",
            "sem adicionais",
            "nao",
            "nenhum",
        }:
            if not g.min_options <= len(own) <= g.max_options:
                raise cart_rules.CartError(
                    f"Escolha de {g.min_options} a {g.max_options} opções em {g.name}."
                )
            c.data["group_index"] += 1
            return ask_additions(c)
        opts = [
            o
            for o in g.options.all()
            if o.is_available and o.tenant_id == c.cart.tenant_id
        ]
        chosen = next(
            (
                o
                for o in opts
                if action == f"option:{o.pk}" or normalize(o.name) == norm
            ),
            None,
        )
        if not chosen:
            return ask_additions(c)
        found = next((x for x in own if str(x["option_id"]) == str(chosen.pk)), None)
        if found:
            selected.remove(found)
        elif len(own) < g.max_options:
            selected.append({"group_id": g.pk, "option_id": chosen.pk})
        else:
            raise cart_rules.CartError(
                f"Você já escolheu o máximo de {g.max_options}. Retire uma opção para trocar."
            )
        return ask_additions(c)
    if c.step == "notes":
        c.data["pending"]["notes"] = (
            c.data.get("dialogue_note", "")
            if action == "dialogue_keep_note"
            else (
                ""
                if action == "none"
                or norm in {"nao", "sem", "nenhuma", "sem observacao"}
                else text
            )
        )
        q = cart_rules.quote(c.cart.tenant, c.data["pending"])
        replace_id = c.data.get("dialogue_replace")
        if replace_id:
            replaced = c.cart.items.filter(pk=replace_id).first()
            if not replaced:
                raise cart_rules.CartError(
                    "O item a substituir mudou. Confira o carrinho novamente."
                )
            cart_rules.check_cart_candidate(c.cart, q, c.data["count"], [replace_id])
            replaced.delete()
        cart_rules.add_item(c.cart, q, c.data["count"])
        c.data.pop("dialogue_replace", None)
        c.data.pop("dialogue_note", None)
        c.data.pop("pending", None)
        from .dialogue import next_queued

        queued_reply = next_queued(c)
        if queued_reply:
            return queued_reply
        c.step = "menu"
        choices = menu().choices
        ending = "Quer mais alguma coisa?"
        if not c.data.get("dialogue_suggestions_offered") and not c.data.get(
            "dialogue_suggestions_declined"
        ):
            c.data["dialogue_suggestions_offered"] = True
            choices.append(("dialogue_suggest", "Ver complementos"))
        variants = ["Adicionei", "Pronto! Coloquei", "Certo, entrou"]
        intro = variants[c.cart.items.count() % len(variants)]
        return reply(
            f"{intro} *{c.data['count']}x {q.name}* no carrinho.\n\n{ending}", choices
        )
    if c.step == "menu":
        c.step = "product"
        return transition(c, text, action)
    if c.step == "name":
        if not 2 <= len(text) <= 150:
            raise cart_rules.CartError("Me diga um nome entre 2 e 150 caracteres.")
        c.data["customer_name"] = text
        c.step = "fulfillment"
        choices = []
        if c.cart.tenant.accepts_delivery:
            choices.append(("delivery", "Entrega"))
        if c.cart.tenant.accepts_pickup:
            choices.append(("pickup", "Retirada"))
        return reply("Você prefere receber em casa ou retirar na loja?", choices)
    if c.step == "fulfillment":
        method = action or {
            "entrega": "delivery",
            "retirada": "pickup",
            "retirar": "pickup",
        }.get(norm, "")
        if method not in {"delivery", "pickup"} or not getattr(
            c.cart.tenant, f"accepts_{method}"
        ):
            raise cart_rules.CartError(
                "Escolha uma das formas de recebimento disponíveis."
            )
        c.data["delivery_type"] = method
        for key, _, _ in ADDRESS:
            c.data.pop(key, None)
        if method == "delivery":
            c.data["address_index"] = 0
            return ask_address(c)
        return payment_choices(c)
    if c.step == "address":
        idx = c.data["address_index"]
        key, _, limit = ADDRESS[idx]
        value = (
            ""
            if action == "none" and key in {"delivery_complement", "delivery_reference"}
            else text.strip()
        )
        if len(value) > limit or (
            not value and key not in {"delivery_complement", "delivery_reference"}
        ):
            raise cart_rules.CartError(
                f"Confira essa informação; use até {limit} caracteres."
            )
        if key == "delivery_state":
            value = value.upper()
            if (
                value
                not in "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
            ):
                raise cart_rules.CartError("Informe uma UF válida, por exemplo: SP.")
        if key == "delivery_zip_code":
            value = re.sub(r"\D", "", value)
            if len(value) != 8:
                raise cart_rules.CartError("O CEP precisa ter 8 números.")
        c.data[key] = value
        if key == "delivery_neighborhood":
            result = resolve_delivery(
                c.cart.tenant, "delivery", c.data["delivery_city"], value
            )
            if not result["available"]:
                c.data["address_index"] = 0
                return reply(
                    result["message"]
                    + "\n\nVamos conferir o endereço: qual é a cidade? (Ou escreva finalizar para escolher retirada.)"
                )
        c.data["address_index"] += 1
        return ask_address(c)
    if c.step == "payment":
        method = action or {
            "pix online": "online_pix",
            "pix": "pix",
            "debito": "debit_card",
            "credito": "credit_card",
            "dinheiro": "cash",
            "cash": "cash",
            "debit_card": "debit_card",
            "credit_card": "credit_card",
        }.get(norm, "")
        if method not in {"online_pix", "pix", "debit_card", "credit_card", "cash"}:
            return payment_choices(c)
        if method == "online_pix" and not online_payment_available(c.cart.tenant):
            return payment_choices(c)
        c.data.update(
            payment_method="pix" if method == "online_pix" else method,
            payment_flow="online" if method == "online_pix" else "in_person",
            payment_change_for="",
        )
        if method == "online_pix":
            c.step = "document"
            return reply(
                "Para gerar o Pix na conta da loja, o Asaas precisa do CPF ou CNPJ do pagador.\n\nPode me informar? Ele não aparecerá no resumo do pedido."
            )
        if method == "cash":
            c.step = "change"
            return reply(
                "Vai precisar de troco? Se sim, me diga para qual valor. Exemplo: *100,00*.",
                [("none", "Não preciso de troco")],
            )
        return review(c)
    if c.step == "document":
        from apps.billing.secrets import encrypt_secret

        try:
            document = clean_document(text)
        except ValueError as exc:
            raise cart_rules.CartError(str(exc)) from None
        c.data["document_encrypted"] = encrypt_secret(document)
        return review(c)
    if c.step == "change":
        c.data["payment_change_for"] = (
            ""
            if action == "none" or norm in {"nao", "sem troco", "nao preciso"}
            else str(parse_money(text))
        )
        return review(c)
    if c.step == "confirm":
        if action == "confirm" or norm in {
            "confirmar",
            "confirmar pedido",
            "sim",
            "pode confirmar",
        }:
            old = c.snapshot
            result = review(c)
            if c.snapshot != old or c.step != "confirm":
                return result
            return confirm_checkout(c)
        return review(c)
    return menu()


@transaction.atomic
def handle_checkout(tenant, phone, message_id, text):
    row, _ = TenantWhatsAppConversation.objects.get_or_create(
        tenant=tenant, phone_number=phone
    )
    row = TenantWhatsAppConversation.objects.select_for_update().get(pk=row.pk)
    receipt = WhatsAppCheckoutReceipt.objects.filter(
        conversation=row, message_id=message_id
    ).first()
    if receipt:
        return CheckoutReply(**receipt.reply)
    c = (
        WhatsAppCheckout.objects.select_for_update(of=("self",))
        .filter(conversation=row)
        .select_related("cart__tenant", "conversation")
        .order_by("-pk")
        .first()
    )
    norm = normalize(text)
    if _looks_like_human_request(text) or norm == "humano":
        return None
    from .dialogue import starts_order, is_question

    start = (
        starts_order(text)
        or norm
        in {
            "pedido",
            "pedir",
            "novo pedido",
            "fazer pedido",
            "quero pedir",
            "quero fazer um pedido",
            "fazer um pedido",
            "quero fazer pedido",
            "quero comprar",
            "carrinho",
            "comprar",
            "finalizar",
        }
        or (
            not is_question(text)
            and bool(re.match(r"^(eu )?(quero|adicionar|vou querer|me ve)\s+", norm))
        )
    )
    if not c or c.status in {"completed", "cancelled"}:
        if not start:
            return None
        cart = Cart.objects.create(tenant=tenant, session_key=f"wa:{uuid.uuid4().hex}")
        c = WhatsAppCheckout.objects.create(conversation=row, cart=cart)
    # Buttons are versioned per turn. Stale/replayed actions cannot confirm another cart.
    choices = c.data.get("choices", [])
    nonce = c.data.get("nonce", "")
    action = ""
    if text.startswith("wa:"):
        matched = next((x for x in choices if x[0] == text), None)
        if not matched:
            return reply(
                "Essa opção é de uma etapa anterior. Responda à última pergunta ou escreva *carrinho*."
            )
        action = text.split(":", 2)[2]
    elif text.isdigit() and choices:
        idx = int(text) - 1
        if 0 <= idx < len(choices):
            action = choices[idx][0].split(":", 2)[2]
    else:
        matched = next((x for x in choices if normalize(x[1]) == norm), None)
        if matched:
            action = matched[0].split(":", 2)[2]
    try:
        with transaction.atomic():
            from .dialogue import handle_dialogue

            result = handle_dialogue(c, text, action)
            if result is None:
                result = transition(c, text, action)
            c.save()
    except cart_rules.CartError as exc:
        c.refresh_from_db()
        result = reply(
            str(exc) + "\n\nPode tentar novamente ou escrever *carrinho*.",
            [(x[0].split(":", 2)[2], x[1]) for x in choices],
        )
    nonce = uuid.uuid4().hex[:12]
    result.choices = [(f"wa:{nonce}:{a}", label) for a, label in result.choices]
    c.data["choices"] = result.choices
    c.data["nonce"] = nonce
    if not result.context.get("dialogue_interruption"):
        c.data["dialogue_prompt"] = result.text.split("\n\n1.", 1)[0]
    c.save()
    WhatsAppCheckoutReceipt.objects.create(
        conversation=row, message_id=message_id, reply=asdict(result)
    )
    return result
