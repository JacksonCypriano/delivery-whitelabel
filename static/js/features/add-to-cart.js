import { postJSON } from '../core/http.js';
import { getConfig } from '../core/config.js';
import { EVENTS, emit } from '../core/events.js';
import { fetchCustomizations, renderCustomizationGroups, collectSelectedOptions, validateRequiredGroups } from './customizations.js';

let selectedProduct = null;
let currentGroups = [];

function getAddToCartUrl(trigger) {
  return (
    trigger?.dataset.addUrl ||
    getConfig('addToCartUrl') ||
    ''
  );
}

async function fillModal(product) {
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

  // Buscar e renderizar customizações
  const container = document.querySelector('[data-customizations-container]');
  if (container) {
    container.innerHTML = '<p class="text-sm text-gray-400">Carregando opções...</p>';
    currentGroups = await fetchCustomizations(product.id);
    renderCustomizationGroups(container, currentGroups, null);
  }
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

  // Validar grupos obrigatórios
  const container = document.querySelector('[data-customizations-container]');
  if (container && currentGroups.length) {
    const missing = validateRequiredGroups(container, currentGroups);
    if (missing) {
      emit(EVENTS.TOAST_SHOW, { message: `Escolha uma opção em: ${missing}`, type: 'warning' });
      return;
    }
  }

  // Coletar customizações selecionadas
  const customizations = container ? collectSelectedOptions(container) : [];

  // Calcular preço extra das customizações
  const extra = customizations.reduce((sum, c) => sum + parseFloat(c.price || 0), 0);
  const basePrice = parseFloat(String(selectedProduct.price).replace(',', '.')) || 0;
  const finalPrice = (basePrice + extra).toFixed(2);

  const payload = {
    product_id: String(selectedProduct.id),
    quantity: 1,
    customizations,
    ...(note ? { note } : {}),
  };

  await sendToCart(url, payload);
}

export function initAddToCart() {
  // Clique no botão de adicionar (abre modal)
  document.addEventListener('click', async (event) => {
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

    await fillModal(product);
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