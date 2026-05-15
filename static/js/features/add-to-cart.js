import { postJSON } from '../core/http.js';
import { getConfig } from '../core/config.js';
import { EVENTS, emit } from '../core/events.js';

let selectedProduct = null;

function getAddToCartUrl(trigger) {
  return (
    trigger?.dataset.addUrl ||
    getConfig('addToCartUrl') ||
    ''
  );
}

function fillModal(product) {
  selectedProduct = product;

  const nameEl = document.querySelector('[data-modal-product-name]');
  const priceEl = document.querySelector('[data-modal-product-price]');
  const idInput = document.querySelector('[data-modal-product-id]');
  const noteInput = document.querySelector('[data-modal-note]');
  const quantityInput = document.querySelector('[data-modal-quantity]');

  if (nameEl) nameEl.textContent = product.name || '';
  
  if (priceEl) {
    const rawPrice = String(product.price).replace(',', '.');
    const priceNum = parseFloat(rawPrice);
    
    if (!isNaN(priceNum)) {
      priceEl.textContent = `R$ ${priceNum.toFixed(2).replace('.', ',')}`;
    } else {
      priceEl.textContent = '';
    }
  }

  if (idInput) idInput.value = product.id || '';
  if (noteInput) noteInput.value = '';
  if (quantityInput) quantityInput.value = 1;
}

async function sendToCart(url, payload) {
  const result = await postJSON(url, payload);

  if (result.ok && result.data?.success) {
    emit(EVENTS.CART_UPDATED, {
      count: result.data.cart_count ?? 0,
      total: result.data.cart_total ?? null,
    });
    emit(EVENTS.TOAST_SHOW, {
      message: result.data.message || 'Produto adicionado ao carrinho!',
      type: 'success',
    });
    emit(EVENTS.MODAL_CLOSE, { name: 'add-to-cart' });

    // Som de notificação
    const sound = document.getElementById('notificationSound');
    if (sound) sound.play().catch(() => {});

    return;
  }

  emit(EVENTS.TOAST_SHOW, {
    message: result.data?.error || result.data?.message || 'Erro ao adicionar ao carrinho.',
    type: 'error',
  });
}

async function submitModal(note = '') {
  if (!selectedProduct) {
    emit(EVENTS.TOAST_SHOW, { message: 'Nenhum produto selecionado.', type: 'error' });
    return;
  }

  const url = selectedProduct.addUrl || getConfig('addToCartUrl') || '';
  if (!url) {
    emit(EVENTS.TOAST_SHOW, { message: 'URL do carrinho não configurada.', type: 'error' });
    return;
  }

  const payload = {
    product_id: String(selectedProduct.id),
    quantity: 1,
    ...(note ? { note } : {}),
  };

  await sendToCart(url, payload);
}

export function initAddToCart() {
  // Clique no botão de adicionar (abre modal)
  document.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-action="add-to-cart"]');
    if (!trigger) return;

    event.preventDefault();

    const product = {
      id: trigger.dataset.productId,
      name: trigger.dataset.productName,
      price: trigger.dataset.productPrice,
      image: trigger.dataset.productImage || '',
      addUrl: trigger.dataset.addUrl || getConfig('addToCartUrl') || '',
    };

    fillModal(product);
    emit(EVENTS.MODAL_OPEN, { name: 'add-to-cart' });
  });

  // Submit do form (botão "Adicionar" — com nota)
  document.addEventListener('submit', async (event) => {
    const form = event.target.closest('[data-add-to-cart-form]');
    if (!form) return;

    event.preventDefault();
    const note = form.querySelector('[data-modal-note]')?.value?.trim() || '';
    await submitModal(note);
  });

  // Botão "Adicionar sem observação"
  document.addEventListener('click', async (event) => {
    const btn = event.target.closest('[data-modal-submit-no-note]');
    if (!btn) return;

    event.preventDefault();
    await submitModal('');
  });
}