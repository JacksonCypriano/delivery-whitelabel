import { getConfig } from '../core/config.js';
import { EVENTS, emit } from '../core/events.js';

// ── Helpers ───────────────────────────────────────────────────────────────────

const PAYMENT_LABELS = {
  pix: 'Pix (via WhatsApp)',
  card_delivery: 'Cartão na Entrega',
  card_credit: 'Cartão de Crédito',
  cash: 'Dinheiro',
  pix_entrega: 'Pix na Entrega',
};

function getOrderData() {
  try {
    const el = document.getElementById('checkout-order-data');
    return el ? JSON.parse(el.textContent) : null;
  } catch {
    return null;
  }
}

function buildWhatsAppMessage(formData, orderData) {
  const paymentLabel = PAYMENT_LABELS[formData.payment_method] || formData.payment_method;

  let msg = '*NOVO PEDIDO*\n\n';
  msg += '*ITENS DO PEDIDO*\n';

  (orderData?.items || []).forEach((item) => {
    msg += `- ${item.quantity}x ${item.name} - R$ ${item.price}\n`;
  });

  msg += `\n*TOTAL: R$ ${orderData?.total ?? '0,00'}*\n\n`;
  msg += '*DADOS DO CLIENTE*\n';
  msg += `Nome: ${formData.full_name}\n`;
  msg += `Telefone: ${formData.phone}\n\n`;
  msg += '*ENDEREÇO DE ENTREGA*\n';
  msg += `${formData.address}, ${formData.number}\n`;
  msg += `${formData.neighborhood}\n`;
  if (formData.complement) msg += `Complemento: ${formData.complement}\n`;
  msg += `CEP: ${formData.cep}\n\n`;
  msg += '*FORMA DE PAGAMENTO*\n';
  msg += `${paymentLabel}\n`;

  if (formData.change_amount && formData.payment_method === 'cash') {
    msg += `\n*TROCO*\nPrecisa de troco para: R$ ${formData.change_amount}\n`;
  }

  return msg;
}

// ── Payment options visual ────────────────────────────────────────────────────

function initPaymentOptions() {
  const options = document.querySelectorAll('.payment-option');

  options.forEach((option) => {
    option.addEventListener('click', () => {
      options.forEach((opt) => {
        opt.classList.remove('border-primary', 'bg-primary/5', 'text-primary');
        opt.classList.add('border-gray-200');
      });
      option.classList.remove('border-gray-200');
      option.classList.add('border-primary', 'bg-primary/5', 'text-primary');

      // Troco
      const selected = option.querySelector('input[type="radio"]')?.value;
      const trocoField = document.getElementById('troco-field');
      if (trocoField) {
        trocoField.classList.toggle('hidden', selected !== 'cash');
      }
    });
  });
}

// ── WhatsApp submit ───────────────────────────────────────────────────────────

function initWhatsAppSubmit() {
  const form = document.getElementById('checkout-form');
  if (!form) return;

  form.addEventListener('submit', (event) => {
    event.preventDefault();

    const raw = new FormData(form);
    const data = Object.fromEntries(raw.entries());

    const orderData = getOrderData();
    const message = buildWhatsAppMessage(data, orderData);
    const whatsappNumber = getConfig('tenantWhatsapp') || '5511999999999';

    window.open(
      `https://wa.me/${whatsappNumber}?text=${encodeURIComponent(message)}`,
      '_blank'
    );

    emit(EVENTS.TOAST_SHOW, {
      message: 'Pedido enviado! Aguarde o contato no WhatsApp.',
      type: 'success',
    });
  });
}

// ── Init ──────────────────────────────────────────────────────────────────────

export function initCheckout() {
  const saleMode = getConfig('saleMode') || 'online';

  initPaymentOptions();

  if (saleMode === 'whatsapp') {
    initWhatsAppSubmit();
  }
}