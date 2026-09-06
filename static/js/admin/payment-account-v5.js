(function () {
  var MODAL_ID = 'payment-account-terms-modal';
  var STYLE_ID = 'payment-account-onboarding-style';

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

  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    var style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = '' +
      '.payment-online-trigger{display:inline-flex;align-items:center;justify-content:center;gap:8px;border:0;border-radius:11px;background:linear-gradient(135deg,#c8471e,#a93a18);color:#fff;padding:11px 17px;font-weight:800;line-height:1.2;cursor:pointer;box-shadow:0 5px 14px rgba(200,71,30,.22);transition:transform .15s ease,box-shadow .15s ease,background .15s ease;}' +
      '.payment-online-trigger:hover{transform:translateY(-1px);box-shadow:0 8px 18px rgba(200,71,30,.28);}' +
      '.payment-online-trigger.is-active{background:linear-gradient(135deg,#173f35,#225848);box-shadow:0 5px 14px rgba(23,63,53,.22);}' +
      '.payment-online-trigger.is-active:hover{box-shadow:0 8px 18px rgba(23,63,53,.28);}' +
      '.payment-online-trigger-wrap{display:flex;flex-direction:column;align-items:flex-start;gap:7px;}' +
      '.payment-online-trigger-note{margin:0;color:#64748b;font-size:12px;line-height:1.35;}';
    document.head.appendChild(style);
  }

  function updateTrigger(row, button, enabledInput, termsInput) {
    var active = enabledInput.checked && termsInput.checked;
    button.classList.toggle('is-active', active);
    button.textContent = active ? 'Recebimento online ativado' : 'Ativar recebimento online';
    button.setAttribute('aria-pressed', active ? 'true' : 'false');
    toggleFields(row, active);
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
          '<li>A VemDeDelivery criará a subconta Asaas em nome da sua loja.</li>' +
          '<li>Depois da criação, o Asaas enviará ao e-mail informado as instruções de ativação, a definição da senha e o link para entrar na conta.</li>' +
          '<li>O dinheiro das vendas será direcionado para a subconta Asaas da sua loja.</li>' +
          '<li>A VemDeDelivery não recebe comissão sobre essas vendas.</li>' +
          '<li>Serão cobradas somente as taxas do Asaas. Os valores variam por modalidade e conta; consulte a tabela vigente em <strong>Configurações de Conta &gt; Taxas</strong> no Asaas.</li>' +
          '<li>O Asaas poderá solicitar documentos e aprovar o cadastro antes da liberação.</li>' +
          '<li>Após a aprovação do cadastro pelo Asaas, a plataforma confirmará o status e o pagamento online será liberado automaticamente. Os pedidos pelo WhatsApp continuam disponíveis; o recebimento online é uma opção adicional.</li>' +
          '<li>A chave técnica usada pela plataforma ficará armazenada de forma protegida e não será exibida no painel.</li>' +
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
        enabledInput.checked = true;
        termsInput.checked = true;
        if (modal._trigger) updateTrigger(row, modal._trigger, enabledInput, termsInput);
        else toggleFields(row, true);
      } else {
        termsInput.checked = false;
        enabledInput.checked = false;
        if (modal._trigger) updateTrigger(row, modal._trigger, enabledInput, termsInput);
        else toggleFields(row, false);
      }
      closeModal();
    });

    document.body.appendChild(modal);
    modal._trigger = row.querySelector('.payment-online-trigger');
    var accept = modal.querySelector('[data-payment-terms="accept"]');
    if (accept) accept.focus();
  }

  function initializeRow(row) {
    if (!row) return;
    var enabledInput = findField(row, 'enabled');
    var termsInput = findField(row, 'terms_accepted');
    if (!enabledInput || !termsInput) return;
    injectStyles();

    var wrapper = wrapperFor(enabledInput);
    if (!wrapper) return;
    enabledInput.style.setProperty('display', 'none', 'important');
    enabledInput.setAttribute('aria-hidden', 'true');
    enabledInput.tabIndex = -1;
    var label = wrapper.querySelector('label');
    if (label) label.style.display = 'none';
    var help = wrapper.querySelector('.help, .helptext, .help-text');
    if (help) help.style.display = 'none';

    var button = wrapper.querySelector('.payment-online-trigger');
    if (!button) {
      var buttonWrap = document.createElement('div');
      buttonWrap.className = 'payment-online-trigger-wrap';
      button = document.createElement('button');
      button.type = 'button';
      button.className = 'payment-online-trigger';
      buttonWrap.appendChild(button);
      var note = document.createElement('p');
      note.className = 'payment-online-trigger-note';
      note.textContent = 'O WhatsApp continua disponível. Ative esta opção para também receber Pix e cartão de crédito online.';
      buttonWrap.appendChild(note);
      wrapper.appendChild(buttonWrap);
      button.addEventListener('click', function () {
        if (enabledInput.checked && termsInput.checked) {
          enabledInput.checked = false;
          updateTrigger(row, button, enabledInput, termsInput);
          return;
        }
        showTermsModal(row, enabledInput, termsInput);
      });
    }
    updateTrigger(row, button, enabledInput, termsInput);
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
      var button = row && row.querySelector('.payment-online-trigger');
      if (button) updateTrigger(row, button, input, termsInput);
    }
  });

  document.addEventListener('formset:added', function (event) {
    initializeRow(event.target);
  });

  function initializeAll() {
    document.querySelectorAll('.inline-related, tr').forEach(initializeRow);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeAll);
  } else {
    initializeAll();
  }
}());
