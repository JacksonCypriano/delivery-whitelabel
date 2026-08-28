// static/js/features/cart-delivery-summary.js

function money(value) {
  const n = Number(value || 0);

  return new Intl.NumberFormat(
    'pt-BR',
    {
      style: 'currency',
      currency: 'BRL',
    }
  ).format(n);
}

export function applyCartDeliverySummary(data) {
  if (!data) {
    return;
  }

  const subtotalEl =
    document.querySelector('[data-cart-subtotal]');

  const feeEl =
    document.querySelector('[data-cart-delivery-fee]');

  const totalEl =
    document.querySelector('[data-cart-total]');

  if (subtotalEl) {
    subtotalEl.textContent =
      data.subtotal_display
      || money(data.subtotal);
  }

  if (feeEl) {
    feeEl.textContent =
      data.delivery_fee_display
      || money(data.delivery_fee);
  }

  if (totalEl) {
    totalEl.textContent =
      data.total_display
      || money(data.total);
  }
}
