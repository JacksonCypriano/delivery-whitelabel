"""Non-PII schema probe for actual 99Food sandbox order details.

Never persist order payloads or return customer data. The OpenAPI amounts are
integer minor units; conversion and status handling require explicit tests.
"""
from .connectors import ProviderError

EXPECTED = ('order_id', 'status', 'shop', 'price', 'order_items', 'delivery_type', 'pay_type', 'create_time')
PRICE_FIELDS = ('order_price', 'real_price', 'real_pay_price', 'delivery_price', 'currency', 'items_discount', 'delivery_discount')
ITEM_FIELDS = ('app_item_id', 'name', 'amount', 'sku_price', 'total_price', 'remark', 'sub_item_list')


def inspect_order(detail: dict, *, order_id: str, app_shop_id: str, shop_id: str) -> dict:
    if not isinstance(detail, dict):
        raise ProviderError('Resposta do pedido inválida.')
    shop = detail.get('shop')
    if not isinstance(shop, dict):
        raise ProviderError('Identificação da loja ausente na resposta.')
    if str(detail.get('order_id', '')) != str(order_id):
        raise ProviderError('ID do pedido retornado é diferente do solicitado.')
    if str(shop.get('app_shop_id', '')) != str(app_shop_id) or str(shop.get('shop_id', '')) != str(shop_id):
        raise ProviderError('Pedido pertence a outro estabelecimento 99Food.')
    prices = detail.get('price')
    items = detail.get('order_items')
    if not isinstance(prices, dict) or not isinstance(items, list) or not items:
        raise ProviderError('Valores ou itens ausentes; importação impedida.')
    for field in ('order_price', 'real_pay_price'):
        value = prices.get(field)
        if type(value) is not int or value < 0:
            raise ProviderError('Valor de pedido incompatível com a especificação em centavos.')
    summary = {
        'ids_match': True,
        'shop_match': True,
        'fields_present': sorted(k for k in EXPECTED if k in detail),
        'fields_missing': sorted(k for k in EXPECTED if k not in detail),
        'status_type': type(detail.get('status')).__name__,
        'status_code': detail.get('status') if type(detail.get('status')) is int else None,
        'delivery_type_code': detail.get('delivery_type') if type(detail.get('delivery_type')) is int else None,
        'payment_type_code': detail.get('pay_type') if type(detail.get('pay_type')) is int else None,
        'price_fields': sorted(k for k in PRICE_FIELDS if k in prices),
        'currency': prices.get('currency') if prices.get('currency') in ('BRL', 'R$') else 'não confirmado',
        'price_minor_units': True,
        'item_count': len(items),
        'item_fields': sorted({k for item in items if isinstance(item, dict) for k in ITEM_FIELDS if k in item}),
        'items_have_nested_options': any(isinstance(item, dict) and bool(item.get('sub_item_list')) for item in items),
        'address_present': isinstance(detail.get('receive_address'), dict),
    }
    return summary
