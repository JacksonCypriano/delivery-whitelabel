from decimal import Decimal


def to_decimal(value):
    try:
        return Decimal(str(value or "0"))
    except Exception:
        return Decimal("0.00")


def brl(value):
    return (
        f"R$ {to_decimal(value):.2f}"
        .replace(".", ",")
    )


def addition_label(value):
    amount = to_decimal(value)

    if amount <= 0:
        return ""

    return (
        f"+R$ {amount:.2f}"
        .replace(".", ",")
    )


def build_item_message(item):
    combo = item.combination_details or {}
    names = combo.get("names") or []

    lines = [
        f"*{item.quantity}x {item.name}*",
        f"   Produto: {brl(item.base_unit_price)}",
    ]

    if item.has_additions:
        lines.append(
            "   Adicionais: "
            f"+{brl(item.additions_unit_price)}"
        )
        lines.append(
            "   Unitário: "
            f"{brl(item.price)}"
        )

    lines.append(
        "   Subtotal: "
        f"{brl(item.get_total_price())}"
    )

    for customization in (
        combo.get("customizations_whole")
        or []
    ):
        price = addition_label(
            customization.get("price", 0)
        )
        suffix = f" ({price})" if price else ""

        lines.append(
            "   • "
            f"{customization.get('group_name') or 'Adicional'}: "
            f"{customization.get('option_name', '')}"
            f"{suffix}"
        )

    half1 = combo.get("customizations_half1") or []
    half2 = combo.get("customizations_half2") or []

    if half1 or combo.get("notes_half1"):
        name = names[0] if names else "Metade 1"
        lines.append(f"   ½ {name}")

        for customization in half1:
            price = addition_label(
                customization.get("price", 0)
            )
            suffix = f" ({price})" if price else ""

            lines.append(
                "      • "
                f"{customization.get('option_name', '')}"
                f"{suffix}"
            )

        if combo.get("notes_half1"):
            lines.append(
                "      Obs: "
                f"{combo['notes_half1']}"
            )

    if half2 or combo.get("notes_half2"):
        name = (
            names[1]
            if len(names) > 1
            else "Metade 2"
        )
        lines.append(f"   ½ {name}")

        for customization in half2:
            price = addition_label(
                customization.get("price", 0)
            )
            suffix = f" ({price})" if price else ""

            lines.append(
                "      • "
                f"{customization.get('option_name', '')}"
                f"{suffix}"
            )

        if combo.get("notes_half2"):
            lines.append(
                "      Obs: "
                f"{combo['notes_half2']}"
            )

    for customization in (
        combo.get("customizations")
        or []
    ):
        price = addition_label(
            customization.get("price", 0)
        )
        suffix = f" ({price})" if price else ""

        lines.append(
            "   • "
            f"{customization.get('group_name') or 'Adicional'}: "
            f"{customization.get('option_name', '')}"
            f"{suffix}"
        )

    if item.notes:
        lines.append(
            f"   Obs: {item.notes}"
        )

    return "\n".join(lines)


def build_whatsapp_message(order):
    separator = "━" * 22

    items_text = (
        f"\n{separator}\n"
    ).join(
        build_item_message(item)
        for item in order.items.all()
    )

    totals = [
        f"Subtotal: {brl(order.subtotal)}",
    ]

    if order.delivery_type == "delivery":
        totals.append(
            "Taxa de entrega: "
            f"{brl(order.delivery_fee)}"
        )

    if order.coupon_code:
        totals.append(
            f"Cupom {order.coupon_code}: "
            f"-{brl(order.discount_amount)}"
        )

    totals.append(
        f"*Total: {brl(order.total)}*"
    )

    if order.delivery_type == "pickup":
        delivery_block = "Retirada na loja"
    else:
        delivery_block = (
            order.delivery_address_label
            or "Endereço não informado"
        )

        if order.delivery_reference:
            delivery_block += (
                "\nPonto de referência: "
                f"{order.delivery_reference}"
            )

    return (
        f"*Novo Pedido #{order.id}*\n"
        f"{separator}\n\n"
        f"*Cliente*\n"
        f"Nome: {order.customer_name}\n"
        f"Telefone: {order.customer_phone}\n\n"
        f"*Itens*\n\n"
        f"{items_text}\n\n"
        f"{separator}\n"
        + "\n".join(totals)
        + "\n"
        f"*Pagamento: {order.payment_label}*\n\n"
        f"*{order.delivery_type_label}*\n"
        f"{delivery_block}\n"
        f"{separator}"
    )
