// static/js/add_to_cart_with_notes.js
(function () {
  // util: recuperar cookie CSRF
  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
      const cookies = document.cookie.split(';');
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === (name + '=')) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  function getCsrf() {
    const el = document.querySelector('[name=csrfmiddlewaretoken]');
    if (el && el.value) return el.value;
    return getCookie('csrftoken');
  }

  async function sendAjaxRequest(url, data = {}) {
    const formData = new FormData();
    for (let key in data) {
      if (Object.prototype.hasOwnProperty.call(data, key)) {
        formData.append(key, data[key]);
      }
    }
    const csrf = getCsrf();
    if (csrf) formData.append('csrfmiddlewaretoken', csrf);

    try {
      const resp = await fetch(url, {
        method: 'POST',
        body: formData,
        headers: csrf ? { 'X-CSRFToken': csrf } : {},
        credentials: 'same-origin'
      });
      if (!resp.ok) {
        const txt = await resp.text().catch(()=>null);
        return { success: false, status: resp.status, detail: txt };
      }
      const json = await resp.json().catch(()=>null);
      return json || { success: false, error: 'invalid_json' };
    } catch (err) {
      console.error('Erro AJAX', err);
      return { success: false, error: 'network' };
    }
  }

  // elementos do modal
  const modal = document.getElementById('addToCartModal');
  const modalProductName = document.getElementById('modalProductName');
  const modalProductPrice = document.getElementById('modalProductPrice');
  const modalNoteTextarea = document.getElementById('modalNoteTextarea');
  const modalCloseBtn = document.getElementById('modalCloseBtn');
  const modalCancel = document.getElementById('modalCancel');
  const modalAddWithNote = document.getElementById('modalAddWithNote');
  const modalAddNoNote = document.getElementById('modalAddNoNote');

  let activeProductId = null;
  let activeQuantity = 1;

  function openModal(productId, productName, productPrice, quantity = 1) {
    activeProductId = productId;
    activeQuantity = quantity || 1;
    modalProductName.textContent = productName || '';
    modalProductPrice.textContent = productPrice ? `R$ ${String(productPrice).replace('.', ',')}` : '';
    modalNoteTextarea.value = '';
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    setTimeout(()=> modalNoteTextarea.focus(), 40);
  }

  function closeModal() {
    modal.classList.add('hidden');
    modal.classList.remove('flex');
  }

  if (modalCloseBtn) modalCloseBtn.addEventListener('click', closeModal);
  if (modalCancel) modalCancel.addEventListener('click', closeModal);

  if (modalAddNoNote) modalAddNoNote.addEventListener('click', async function (e) {
    e.preventDefault();
    const notes = '';
    await addSimpleProduct(activeProductId, activeQuantity, notes);
    closeModal();
  });

  if (modalAddWithNote) modalAddWithNote.addEventListener('click', async function (e) {
    e.preventDefault();
    const notes = modalNoteTextarea.value.trim();
    if (notes.length > 1000) {
      showToast('Observação muito longa (máx. 1000 caracteres)', 'error');
      return;
    }
    await addSimpleProduct(activeProductId, activeQuantity, notes);
    closeModal();
  });

  async function addSimpleProduct(productId, quantity, notes) {
    if (!productId) {
      showToast('Produto inválido', 'error');
      return;
    }
    const payload = {
      product_id: productId,
      quantity: quantity || 1,
      notes: notes || ''
    };
    const resp = await sendAjaxRequest('/checkout/add/', payload);
    if (resp && resp.success) {
      // atualizar badge
      if (typeof resp.cart_count !== 'undefined') {
        const badge = document.getElementById('cart-count');
        if (badge) {
          badge.textContent = resp.cart_count;
          if (resp.cart_count > 0) badge.classList.remove('hidden');
          else badge.classList.add('hidden');
        }
      }
      // som
      const sound = document.getElementById('notificationSound');
      if (sound) try { sound.play().catch(()=>{}); } catch(e) {}
      // toast
      showToast(resp.message || 'Adicionado ao carrinho', 'success');
    } else {
      console.error('Erro add to cart', resp);
      showToast((resp && (resp.error || resp.detail)) || 'Erro ao adicionar', 'error');
    }
  }

  // abrir modal ao clicar no botão .add-to-cart-btn
  document.addEventListener('click', function (e) {
    const btn = e.target.closest('.add-to-cart-btn');
    if (!btn) return;
    e.preventDefault();

    // procurar atributos (prioridade no botão, senão no ancestor .product-card)
    let pid = btn.dataset.productId || btn.getAttribute('data-product-id');
    let pname = btn.dataset.productName || btn.getAttribute('data-product-name');
    let pprice = btn.dataset.productPrice || btn.getAttribute('data-product-price');

    if (!pid) {
      const card = btn.closest('.product-card');
      if (card) {
        pid = card.dataset.productId;
        pname = pname || card.dataset.productName;
        pprice = pprice || card.dataset.productPrice;
      }
    }

    openModal(pid, pname, pprice, 1);
  });

  // helper toast
  function showToast(message, type = 'success') {
    document.querySelectorAll('.toast-notification').forEach(el => el.remove());
    const toast = document.createElement('div');
    toast.className = 'fixed bottom-6 right-6 px-4 py-3 rounded-lg shadow-lg text-white font-medium z-50 animate-fade-in-up toast-notification';
    toast.style.zIndex = '9999';

    toast.style.display = 'flex';
    toast.style.alignItems = 'center';
    toast.style.justifyContent = 'space-between';
    toast.style.minWidth = '220px';

    if (type === 'error') {
      toast.classList.add('bg-red-500');
    } else {
      toast.classList.add('bg-green-500');
    }

    toast.innerHTML = `
      <div class="flex items-center gap-3">
        <span>${message}</span>
      </div>
      <button class="ml-4 text-white opacity-70 hover:opacity-100">&times;</button>
    `;
    document.body.appendChild(toast);
    setTimeout(() => {
      if (toast.parentNode) {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s ease-out';
        setTimeout(() => { if (toast.parentNode) toast.remove(); }, 300);
      }
    }, 3000);
    toast.querySelector('button').addEventListener('click', () => {
      if (toast.parentNode) toast.remove();
    });
  }

})();