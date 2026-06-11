import { postForm } from '../core/http.js';
import { getConfig } from '../core/config.js';
import { EVENTS, emit } from '../core/events.js';

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatCurrency(value) {
  return 'R$ ' + (Number(value) || 0).toFixed(2).replace('.', ',');
}

function parsePriceFromEl(el) {
  const dp = el?.dataset?.price;
  if (dp) return parseFloat(String(dp).replace(',', '.')) || 0;
  const txt = el?.textContent || '';
  return parseFloat(txt.replace(/[^\d,.-]/g, '').replace(',', '.')) || 0;
}

// ── DOM helpers ───────────────────────────────────────────────────────────────

function getCartItemRow(id) {
  return document.querySelector(`.cart-item[data-cart-item-id="${id}"]`);
}

function getQtyDisplay(row) {
  return row?.querySelector('[data-qty-display]');
}

function getPriceDisplay(row) {
  return row?.querySelector('[data-price-display]');
}

// ── Totals ────────────────────────────────────────────────────────────────────

function recalcTotals() {
  let total = 0;
  let count = 0;

  document.querySelectorAll('.cart-item').forEach((row) => {
    const qty = parseInt(getQtyDisplay(row)?.textContent || '0', 10) || 0;
    const price = parsePriceFromEl(getPriceDisplay(row));
    total += qty * price;
    count += qty;
  });

  const totalEl = document.getElementById('cart-total');
  if (totalEl) totalEl.textContent = formatCurrency(total);

  emit(EVENTS.CART_UPDATED, { count });
}

function applyServerTotals(data) {
  if (data.total !== undefined) {
    const totalEl = document.getElementById('cart-total');
    if (totalEl) {
      const raw = String(data.total);
      totalEl.textContent = raw.startsWith('R$')
        ? raw
        : formatCurrency(parseFloat(raw.replace(',', '.')) || 0);
    }
  }

  const count = data.cart_count ?? null;
  if (count !== null) {
    emit(EVENTS.CART_UPDATED, { count });
  } else {
    recalcTotals();
  }
}

// ── Empty state ───────────────────────────────────────────────────────────────

function showEmptyCart() {
  const container = document.getElementById('cart-items-container');
  if (!container) return;

  const catalogUrl = getConfig('catalogUrl') || '/';

  container.innerHTML = `
    <div class="text-center py-12">
      <div class="mx-auto w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mb-4">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
        </svg>
      </div>
      <p class="text-gray-500 mb-4">Seu carrinho está vazio.</p>
      <a href="${catalogUrl}" class="inline-block text-primary font-medium hover:underline">← Voltar ao cardápio</a>
    </div>`;
}

// ── Actions ───────────────────────────────────────────────────────────────────

async function updateQty(cartItemId, newQty) {
  const baseUrl = getConfig('updateQuantityBaseUrl') || '/checkout/update_quantity/';
  const url = `${baseUrl}${cartItemId}/`;

  const result = await postForm(url, { quantity: newQty });

  if (result.ok && result.data?.success) {
    const row = getCartItemRow(cartItemId);
    if (row) getQtyDisplay(row).textContent = newQty;

    applyServerTotals(result.data);

    emit(EVENTS.TOAST_SHOW, { message: 'Quantidade atualizada', type: 'success' });

    const sound = document.getElementById('notificationSound');
    if (sound) sound.play().catch(() => {});
    return;
  }

  emit(EVENTS.TOAST_SHOW, { message: 'Erro ao atualizar quantidade', type: 'error' });
}

async function removeItem(cartItemId) {
  if (!confirm('Remover este item do carrinho?')) return;

  const baseUrl = getConfig('removeItemBaseUrl') || '/checkout/remove/';
  const url = `${baseUrl}${cartItemId}/`;

  const result = await postForm(url, {});

  if (result.ok && result.data?.success) {
    const row = getCartItemRow(cartItemId);
    if (row) row.remove();

    applyServerTotals(result.data);

    emit(EVENTS.TOAST_SHOW, { message: 'Item removido do carrinho', type: 'success' });

    const sound = document.getElementById('notificationSound');
    if (sound) sound.play().catch(() => {});

    if (document.querySelectorAll('.cart-item').length === 0) {
      showEmptyCart();
    }
    return;
  }

  emit(EVENTS.TOAST_SHOW, { message: 'Erro ao remover item', type: 'error' });
}

// ── Init ──────────────────────────────────────────────────────────────────────

export function initCart() {
  // Aumentar quantidade
  document.addEventListener('click', async (event) => {
    console.log('clique detectado', event.target);
    const btn = event.target.closest('[data-action="increase-qty"]');
    console.log('botão remove:', btn);
    if (!btn) return;

    const id = btn.dataset.cartItemId;
    const row = getCartItemRow(id);
    if (!row) return;

    const current = parseInt(getQtyDisplay(row)?.textContent || '1', 10);
    await updateQty(id, current + 1);
  });

  // Diminuir quantidade
  document.addEventListener('click', async (event) => {
    const btn = event.target.closest('[data-action="decrease-qty"]');
    if (!btn) return;

    const id = btn.dataset.cartItemId;
    const row = getCartItemRow(id);
    if (!row) return;

    const current = parseInt(getQtyDisplay(row)?.textContent || '1', 10);
    if (current <= 1) return;

    await updateQty(id, current - 1);
  });

  // Remover item
  document.addEventListener('click', async (event) => {
    const btn = event.target.closest('[data-action="remove-item"]');
    if (!btn) return;

    await removeItem(btn.dataset.cartItemId);
  });

  // Calcula totais na carga inicial
  recalcTotals();
}