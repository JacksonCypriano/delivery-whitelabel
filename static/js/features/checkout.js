import { getConfig } from '../core/config.js';
import { EVENTS, emit } from '../core/events.js';

// ────────────────────────────────────────────────────────────────────────────
// Checkout (finalização do pedido)
//
// IMPORTANTE: o envio do pedido é feito 100% no servidor (view
// `checkout_step_one`). É lá que o pedido (Order) é criado, a mensagem completa
// do WhatsApp é montada (com itens, valores, endereço e observações) e o
// cliente é redirecionado para `wa.me`.
//
// Este módulo NÃO intercepta mais o submit do formulário (isso causava o envio
// de uma mensagem vazia). Ele apenas cuida da parte visual: seleção da forma de
// pagamento, campo de troco e feedback ao clicar em finalizar.
// ────────────────────────────────────────────────────────────────────────────

function initPaymentOptions() {
  const options = document.querySelectorAll('.payment-option');
  const trocoField = document.getElementById('troco-field');

  function refreshTroco() {
    if (!trocoField) return;
    const selected = document.querySelector('input[name="payment_method"]:checked');
    trocoField.classList.toggle('hidden', !selected || selected.value !== 'cash');
  }

  options.forEach((option) => {
    option.addEventListener('click', () => {
      options.forEach((opt) => {
        opt.classList.remove('border-primary', 'bg-primary/5', 'text-primary');
        opt.classList.add('border-gray-200');
      });
      option.classList.remove('border-gray-200');
      option.classList.add('border-primary', 'bg-primary/5', 'text-primary');

      const radio = option.querySelector('input[type="radio"]');
      if (radio) radio.checked = true;

      refreshTroco();
    });
  });

  refreshTroco();
}

function initSubmitFeedback() {
  const form = document.getElementById('checkout-form');
  const button = document.getElementById('submit-button');
  if (!form || !button) return;

  form.addEventListener('submit', () => {
    // Não usamos preventDefault: deixamos o formulário seguir para o servidor,
    // que cria o pedido e redireciona para o WhatsApp com a mensagem completa.
    button.disabled = true;
    button.dataset.originalText = button.innerHTML;
    button.innerHTML = 'Enviando pedido...';

    emit(EVENTS.TOAST_SHOW, {
      message: 'Preparando seu pedido no WhatsApp...',
      type: 'success',
    });
  });
}

export function initCheckout() {
  initPaymentOptions();
  initSubmitFeedback();
}
