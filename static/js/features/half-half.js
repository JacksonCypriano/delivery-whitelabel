import { postJSON } from '../core/http.js';
import { getConfig } from '../core/config.js';
import { EVENTS, emit, on } from '../core/events.js';

// Estado interno
let selected = [null, null]; // [metade1, metade2]
let cachedOptions = [];
let searchTimeout = null;
const OPEN_GUARD_MS = 220;
let lastOpenAt = 0;

// Helpers de preço
function parsePrice(raw) {
  if (raw == null || raw === '') return 0;
  if (typeof raw === 'number') return raw;
  let v = String(raw).trim().replace(/[^\d.,-]/g, '');
  if (v.includes('.') && v.includes(',')) v = v.replace(/\./g, '').replace(',', '.');
  else if (v.includes(',')) v = v.replace(',', '.');
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : 0;
}

function formatPrice(value) {
  return 'R$ ' + (Number(value) || 0).toFixed(2).replace('.', ',');
}

// Seletores do modal
function getModal() { return document.querySelector('[data-modal="half-half"]'); }
function getDropdownBtn() { return document.querySelector('[data-half-half-dropdown-btn]'); }
function getDropdownList() { return document.querySelector('[data-half-half-dropdown-list]'); }
function getDropdownText() { return document.querySelector('[data-half-half-dropdown-text]'); }
function getDropdownItems() { return document.querySelector('[data-half-half-items]'); }
function getSearchInput() { return document.querySelector('[data-half-half-search]'); }
function getSubmitBtn() { return document.querySelector('[data-half-half-submit]'); }

// Atualiza preview visual
function updatePreview() {
  const leftName = document.querySelector('[data-half-left-name]');
  const rightName = document.querySelector('[data-half-right-name]');
  const leftThumb = document.querySelector('[data-half-left-thumb]');
  const rightThumb = document.querySelector('[data-half-right-thumb]');
  const priceEl = document.querySelector('[data-half-price]');

  if (leftName) leftName.textContent = selected[0]?.name || 'Escolha...';
  if (rightName) rightName.textContent = selected[1]?.name || 'Selecione...';

  if (leftThumb) {
    if (selected[0]?.image) { leftThumb.src = selected[0].image; leftThumb.classList.remove('hidden'); }
    else leftThumb.classList.add('hidden');
  }
  if (rightThumb) {
    if (selected[1]?.image) { rightThumb.src = selected[1].image; rightThumb.classList.remove('hidden'); }
    else rightThumb.classList.add('hidden');
  }

  if (priceEl) {
    if (selected[0] && selected[1]) {
      const max = Math.max(parsePrice(selected[0].price), parsePrice(selected[1].price));
      priceEl.textContent = formatPrice(max);
    } else {
      priceEl.textContent = 'R$ 0,00';
    }
  }

  const submitBtn = getSubmitBtn();
  if (submitBtn) submitBtn.disabled = !(selected[0] && selected[1]);
}

// Constrói cache de opções a partir do DOM
function buildCache() {
  cachedOptions = [];
  document.querySelectorAll('#pizzas-meio-a-meio .product-card').forEach((card) => {
    const id = String(card.dataset.productId || '');
    if (!id) return;
    cachedOptions.push({
      id,
      name: card.dataset.productName || card.querySelector('.product-title')?.textContent?.trim() || 'Produto',
      price: String(parsePrice(card.dataset.productPrice || '0')),
      image: card.dataset.productImage || card.querySelector('img')?.src || '',
    });
  });
}

// Renderiza itens no dropdown
function renderDropdownItems(excludeId = null, filter = '') {
  const wrapper = getDropdownItems();
  if (!wrapper) return;

  wrapper.innerHTML = '';
  const f = filter.trim().toLowerCase();

  const list = cachedOptions.filter((opt) => {
    if (excludeId && String(opt.id) === String(excludeId)) return false;
    if (f) return opt.name.toLowerCase().includes(f);
    return true;
  });

  if (!list.length) {
    wrapper.innerHTML = '<div class="dropdown-empty">Nenhum sabor encontrado.</div>';
    return;
  }

  list.forEach((opt) => {
    const item = document.createElement('div');
    item.className = 'dropdown-item';
    item.setAttribute('role', 'option');
    item.tabIndex = 0;
    item.dataset.productId = opt.id;
    item.innerHTML = `
      <img src="${opt.image || ''}" class="dropdown-thumb" alt="${opt.name}">
      <div class="flex-1">
        <div class="text-sm text-gray-700">${opt.name}</div>
        <div class="text-xs text-primary font-semibold">${formatPrice(opt.price)}</div>
      </div>`;

    item.addEventListener('click', () => selectSecond(opt));
    item.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectSecond(opt); }
    });

    wrapper.appendChild(item);
  });
}

// Seleciona segundo sabor
function selectSecond(product) {
  if (selected[0] && String(selected[0].id) === String(product.id)) {
    emit(EVENTS.TOAST_SHOW, { message: 'Escolha um sabor diferente para a segunda metade.', type: 'warning' });
    return;
  }

  selected[1] = { ...product };

  const text = getDropdownText();
  if (text) text.textContent = product.name;

  const btn = getDropdownBtn();
  if (btn) btn.setAttribute('aria-expanded', 'false');

  const list = getDropdownList();
  if (list) list.classList.add('hidden');

  // Marca item selecionado
  getDropdownItems()?.querySelectorAll('[data-product-id]').forEach((el) => {
    el.setAttribute('aria-selected', el.dataset.productId === String(product.id) ? 'true' : 'false');
  });

  updatePreview();
}

// Abre modal com metade 1 já definida
function openHalfHalfModal(product) {
  selected = [{ ...product }, null];
  lastOpenAt = Date.now();

  buildCache();
  renderDropdownItems(product.id);

  const text = getDropdownText();
  if (text) text.textContent = 'Selecione o segundo sabor';

  const search = getSearchInput();
  if (search) search.value = '';

  const list = getDropdownList();
  if (list) list.classList.add('hidden');

  updatePreview();
  emit(EVENTS.MODAL_OPEN, { name: 'half-half' });
}

// Envia pedido meio a meio
async function submitHalfHalf() {
  if (!selected[0] || !selected[1]) {
    emit(EVENTS.TOAST_SHOW, { message: 'Selecione dois sabores.', type: 'warning' });
    return;
  }

  const url = getConfig('addHalfHalfUrl') || '';
  if (!url) {
    emit(EVENTS.TOAST_SHOW, { message: 'URL do meio a meio não configurada.', type: 'error' });
    return;
  }

  const submitBtn = getSubmitBtn();
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerHTML = `
      <svg class="animate-spin inline-block mr-2 w-5 h-5" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3" fill="none" stroke-linecap="round"/>
      </svg> Adicionando...`;
  }

  const result = await postJSON(url, {
    product_ids: [selected[0].id, selected[1].id],
    quantity: 1,
  });

  if (submitBtn) {
    submitBtn.disabled = false;
    submitBtn.textContent = 'Adicionar ao Carrinho';
  }

  if (result.ok && result.data && (result.data.success || result.data.added)) {
    emit(EVENTS.CART_UPDATED, { count: result.data.cart_count ?? 0 });
    emit(EVENTS.TOAST_SHOW, { message: result.data.message || 'Adicionado ao carrinho!', type: 'success' });
    emit(EVENTS.MODAL_CLOSE, { name: 'half-half' });

    const sound = document.getElementById('notificationSound');
    if (sound) sound.play().catch(() => {});
    return;
  }

  emit(EVENTS.TOAST_SHOW, {
    message: result.data?.error || result.data?.message || `Erro HTTP ${result.status}`,
    type: 'error',
  });
}

export function initHalfHalf() {
  // Botão "Montar" nos cards
  document.addEventListener('click', (event) => {
    const btn = event.target.closest('[data-action="start-half-half"]');
    if (!btn) return;

    event.preventDefault();

    const product = {
      id: String(btn.dataset.productId || ''),
      name: btn.dataset.productName || '',
      price: String(parsePrice(btn.dataset.productPrice || '0')),
      image: btn.dataset.productImage || '',
    };

    if (!product.id) {
      emit(EVENTS.TOAST_SHOW, { message: 'Produto inválido.', type: 'error' });
      return;
    }

    openHalfHalfModal(product);
  });

  // Botão submit do modal
  document.addEventListener('click', async (event) => {
    const btn = event.target.closest('[data-half-half-submit]');
    if (!btn) return;

    event.preventDefault();
    await submitHalfHalf();
  });

  // Toggle dropdown
  document.addEventListener('click', (event) => {
    const btn = event.target.closest('[data-half-half-dropdown-btn]');
    if (!btn) return;

    event.preventDefault();
    const list = getDropdownList();
    if (!list) return;

    if (list.classList.contains('hidden')) {
      renderDropdownItems(selected[0]?.id, getSearchInput()?.value || '');
      list.classList.remove('hidden');
      btn.setAttribute('aria-expanded', 'true');
      setTimeout(() => getSearchInput()?.focus(), 50);
    } else {
      list.classList.add('hidden');
      btn.setAttribute('aria-expanded', 'false');
    }
  });

  // Busca no dropdown
  document.addEventListener('input', (event) => {
    const input = event.target.closest('[data-half-half-search]');
    if (!input) return;

    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      renderDropdownItems(selected[0]?.id, input.value);
    }, 120);
  });

  // Fecha dropdown ao clicar fora
  document.addEventListener('click', (event) => {
    const list = getDropdownList();
    if (!list || list.classList.contains('hidden')) return;
    if (event.target.closest('[data-half-half-dropdown]')) return;
    list.classList.add('hidden');
    getDropdownBtn()?.setAttribute('aria-expanded', 'false');
  });

  // Navegação por teclado no dropdown
  document.addEventListener('keydown', (event) => {
    const list = getDropdownList();
    if (!list || list.classList.contains('hidden')) return;

    const items = Array.from(list.querySelectorAll('.dropdown-item'));
    if (!items.length) return;

    const idx = items.indexOf(document.activeElement);

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      items[idx < items.length - 1 ? idx + 1 : 0].focus();
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      items[idx > 0 ? idx - 1 : items.length - 1].focus();
    } else if (event.key === 'Escape') {
      list.classList.add('hidden');
      getDropdownBtn()?.focus();
    }
  });

  // Fecha modal → reseta estado
  on(EVENTS.MODAL_CLOSE, (event) => {
    if (event.detail?.name !== 'half-half') return;
    selected = [null, null];
    const text = getDropdownText();
    if (text) text.textContent = 'Selecione o segundo sabor';
    const search = getSearchInput();
    if (search) search.value = '';
    updatePreview();
  });
}