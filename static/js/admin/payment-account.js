(function () {
  var MODAL_ID = 'payment-account-terms-modal';

  function rowFor(input) {
    return input.closest('.inline-related, tr');
  }

  function wrapperFor(field) {
    return field.closest('.form-row, td, .fieldBox');
  }

  function toggleFields(row, enabled) {
    if (!row) return;
    row.querySelectorAll('.payment-onboarding-field').forEach(function (field) {
      var wrapper = wrapperFor(field);
      if (wrapper) wrapper.style.display = enabled ? '' : 'none';
    });
  }

  function findField(row, suffix) {
    return row && row.querySelector('input[name$="-' + suffix + '"], select[name$="-' + suffix + '"], textarea[name$="-' + suffix + '"]');
  }

  function closeModal() {
    var modal = document.getElementById(MODAL_ID);
    if (modal) modal.remove();
  }

  function showTermsModal(row, enabledInput, termsInput) {
    closeModal();

    var modal = document.createElement('div');
    modal.id = MODAL_ID;
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-labelledby', MODAL_ID + '-title');
    modal.style.cssText = 'position:fixed;inset:0;z-index:10000;display:flex;align-items:center;justify-content:center;padding:20px;background:rgba(15,23,42,.58);';

    modal.innerHTML = '' +
      '<div style="width:min(680px,100%);max-height:90vh;overflow:auto;border-radius:18px;background:#fff;color:#173f35;box-shadow:0 24px 80px rgba(15,23,42,.28);padding:28px;">' +
        '<h2 id="' + MODAL_ID + '-title" style="margin:0 0 14px;font-size:22px;font-weight:800;">Recebimento online pela subconta Asaas</h2>' +
        '<p style="margin:0 0 14px;line-height:1.55;">Antes de continuar, leia as condições para receber pagamentos online diretamente pela sua loja.</p>' +
        '<ul style="margin:0 0 18px;padding-left:22px;line-height:1.6;">' +
          '<li>Os pagamentos disponíveis serão Pix e cartão de crédito.</li>' +
          '<li>O dinheiro das vendas será direcionado para a subconta Asaas da sua loja.</li>' +
          '<li>A VemDeDelivery não recebe comissão sobre essas vendas.</li>' +
          '<li>Serão cobradas somente as taxas do Asaas. Os valores variam por modalidade e conta; consulte a tabela vigente em <strong>Configurações de Conta &gt; Taxas</strong> no Asaas.</li>' +
          '<li>O Asaas poderá solicitar documentos e aprovar o cadastro antes da liberação.</li>' +
          '<li>A VemDeDelivery não armazena dados de cartão e não define as taxas do Asaas.</li>' +
        '</ul>' +
        '<p style="margin:0 0 22px;line-height:1.55;color:#475569;">Ao aceitar, você confirma que está de acordo com essas condições e poderá preencher os dados cadastrais da subconta.</p>' +
        '<div style="display:flex;justify-content:flex-end;gap:12px;flex-wrap:wrap;">' +
          '<button type="button" data-payment-terms="decline" style="border:1px solid #cbd5e1;border-radius:10px;background:#fff;color:#334155;padding:10px 18px;font-weight:700;cursor:pointer;">Não aceito</button>' +
          '<button type="button" data-payment-terms="accept" style="border:0;border-radius:10px;background:#c8471e;color:#fff;padding:10px 18px;font-weight:700;cursor:pointer;">Aceito e continuar</button>' +
        '</div>' +
      '</div>';

    modal.addEventListener('click', function (event) {
      var action = event.target && event.target.getAttribute('data-payment-terms');
      if (!action) return;
      if (action === 'accept') {
        termsInput.checked = true;
        toggleFields(row, true);
      } else {
        termsInput.checked = false;
        enabledInput.checked = false;
        toggleFields(row, false);
      }
      closeModal();
    });

    document.body.appendChild(modal);
    var accept = modal.querySelector('[data-payment-terms="accept"]');
    if (accept) accept.focus();
  }

  function initializeRow(row) {
    if (!row) return;
    var enabledInput = findField(row, 'enabled');
    var termsInput = findField(row, 'terms_accepted');
    if (!enabledInput || !termsInput) return;
    toggleFields(row, enabledInput.checked && termsInput.checked);
  }

  document.addEventListener('change', function (event) {
    var input = event.target;
    if (!input || !input.name || !input.name.endsWith('-enabled')) return;
    var row = rowFor(input);
    var termsInput = findField(row, 'terms_accepted');
    if (!termsInput) return;
    if (input.checked && !termsInput.checked) {
      toggleFields(row, false);
      showTermsModal(row, input, termsInput);
    } else {
      toggleFields(row, input.checked && termsInput.checked);
    }
  });

  document.querySelectorAll('.inline-related, tr').forEach(initializeRow);
}());
