(function () {
  'use strict';

  var MODAL_ID = 'payment-account-terms-modal-v9';

  function rowFor(input) {
    return input && input.closest('.inline-related, tr');
  }

  function wrapperFor(field) {
    if (!field) return null;
    var name = String(field.name || '');
    var suffix = name.split('-').pop();
    var selector = '.form-row, td, .fieldBox' + (suffix ? ', .field-' + suffix : '');
    return field.closest(selector) || field.parentElement;
  }

  function fieldPrefix(enabledInput) {
    var name = String((enabledInput && enabledInput.name) || '');
    return name.endsWith('-enabled') ? name.slice(0, -8) : '';
  }

  function inlineRootFor(input) {
    if (!input) return null;
    return input.closest('.payment-account-inline')
      || document.querySelector('.payment-account-inline')
      || input.closest('.inline-related')
      || input.closest('.inline-group')
      || input.closest('form');
  }

  function findField(row, suffix) {
    if (!row) return null;
    var prefix = row._paymentPrefix || '';
    if (prefix) {
      var exact = document.getElementsByName(prefix + '-' + suffix);
      if (exact && exact.length) return exact[0];
    }
    return row.querySelector(
      'input[name$="-' + suffix + '"], select[name$="-' + suffix + '"], textarea[name$="-' + suffix + '"]'
    );
  }

  function digitsOnly(value) {
    return String(value || '').replace(/\D/g, '');
  }

  function formatCep(value) {
    var digits = digitsOnly(value).slice(0, 8);
    if (digits.length > 5) return digits.slice(0, 5) + '-' + digits.slice(5);
    return digits;
  }

  function termsAccepted(input) {
    if (!input) return false;
    var value = String(input.value || '').trim().toLowerCase();
    return value === 'true' || value === '1' || value === 'on' || value === 'yes';
  }

  function setTermsAccepted(input, accepted) {
    if (!input) return;
    input.value = accepted ? 'True' : 'False';
    input.checked = Boolean(accepted);
  }

  function setDetailsVisible(row, visible) {
    if (!row) return;
    row.classList.toggle('payment-online-details-visible', Boolean(visible));
    row.querySelectorAll('.payment-online-details-section').forEach(function (section) {
      section.hidden = !visible;
      if (visible) {
        section.style.removeProperty('display');
      } else {
        section.style.setProperty('display', 'none', 'important');
      }
    });
  }

  function ensureCepStatus(postalInput) {
    var wrapper = wrapperFor(postalInput);
    if (!wrapper) return null;
    var status = wrapper.querySelector('.payment-cep-status');
    if (!status) {
      status = document.createElement('p');
      status.className = 'payment-cep-status';
      status.setAttribute('aria-live', 'polite');
      wrapper.appendChild(status);
    }
    return status;
  }

  function setCepStatus(postalInput, message, kind) {
    var status = ensureCepStatus(postalInput);
    if (!status) return;
    status.textContent = message || '';
    status.className = 'payment-cep-status' + (kind ? ' is-' + kind : '');
  }

  function fillFromCep(row, postalInput) {
    var cep = digitsOnly(postalInput && postalInput.value);
    if (cep.length !== 8) {
      if (cep.length) {
        setCepStatus(postalInput, 'Informe um CEP válido com 8 dígitos.', 'error');
      }
      return;
    }
    if (postalInput.dataset.cepLoading === '1') return;
    if (postalInput.dataset.cepLoaded === cep) return;

    postalInput.dataset.cepLoading = '1';
    setCepStatus(postalInput, 'Consultando CEP...', 'loading');

    fetch('/api/cep/' + encodeURIComponent(cep) + '/', {
      method: 'GET',
      credentials: 'same-origin',
      headers: { 'Accept': 'application/json' }
    })
      .then(function (response) {
        return response.json().catch(function () { return {}; }).then(function (data) {
          if (!response.ok || data.success === false) {
            throw new Error(data.error || 'Não foi possível consultar o CEP.');
          }
          return data;
        });
      })
      .then(function (data) {
        var address = findField(row, 'address');
        var province = findField(row, 'province');
        var complement = findField(row, 'complement');
        var number = findField(row, 'address_number');

        postalInput.value = formatCep(data.cep || cep);
        postalInput.dataset.cepLoaded = cep;

        if (address && data.street) address.value = data.street;
        if (province && data.neighborhood) province.value = data.neighborhood;
        if (complement && data.complement && !String(complement.value || '').trim()) {
          complement.value = data.complement;
        }

        var location = [data.city, data.state].filter(Boolean).join(' / ');
        setCepStatus(
          postalInput,
          location
            ? 'CEP encontrado: ' + location + '. Confira o endereço e informe o número.'
            : 'CEP encontrado. Confira o endereço e informe o número.',
          'success'
        );

        if (number && !String(number.value || '').trim()) number.focus();
      })
      .catch(function (error) {
        delete postalInput.dataset.cepLoaded;
        setCepStatus(postalInput, error.message || 'Não foi possível consultar o CEP agora.', 'error');
      })
      .finally(function () {
        delete postalInput.dataset.cepLoading;
      });
  }

  function closeModal() {
    var modal = document.getElementById(MODAL_ID);
    if (modal) modal.remove();
  }

  function sourceStatusText(row, enabledInput) {
    if (enabledInput && enabledInput.dataset) {
      var saved = String(enabledInput.dataset.paymentAccountStatus || '').trim();
      if (saved) return saved;
    }
    if (!row) return '';
    var readonly = row.querySelector('.field-status .readonly, [class*="field-status"] .readonly');
    if (readonly) return String(readonly.textContent || '').trim();
    return '';
  }

  function hideTechnicalInlineHeading(row) {
    if (!row) return;
    row.querySelectorAll('h3').forEach(function (heading) {
      var text = String(heading.textContent || '').replace(/\s+/g, ' ').trim().toLowerCase();
      if (text.indexOf('conta de pagamentos online') !== -1 || /#\s*\d+/.test(text)) {
        heading.style.setProperty('display', 'none', 'important');
        heading.setAttribute('aria-hidden', 'true');
      }
    });
  }

  function hideOriginalControls(row, enabledInput) {
    var enabledWrapper = wrapperFor(enabledInput);
    if (enabledWrapper) enabledWrapper.classList.add('payment-online-control-source');

    var statusWrapper = row && row.querySelector('.field-status');
    if (statusWrapper) statusWrapper.classList.add('payment-status-source');
  }

  function focusFirstMissing(row) {
    var names = [
      'legal_name', 'document', 'email', 'mobile_phone', 'birth_date',
      'income_value', 'postal_code', 'address', 'address_number', 'province'
    ];
    for (var i = 0; i < names.length; i += 1) {
      var field = findField(row, names[i]);
      if (field && !String(field.value || '').trim() && !field.disabled) {
        field.focus();
        return;
      }
    }
  }

  function maybeResolveExistingCep(row) {
    var postal = findField(row, 'postal_code');
    var address = findField(row, 'address');
    var province = findField(row, 'province');
    if (!postal || digitsOnly(postal.value).length !== 8) return;
    if ((!address || !String(address.value || '').trim()) || (!province || !String(province.value || '').trim())) {
      fillFromCep(row, postal);
    }
  }

  function updateCompactControl(row, control, enabledInput, termsInput) {
    var enabled = Boolean(enabledInput.checked);
    var accepted = termsAccepted(termsInput);
    var active = enabled && accepted;

    control.switchButton.setAttribute('aria-checked', active ? 'true' : 'false');
    setDetailsVisible(row, active);

    var savedStatus = control.savedStatus || '';
    var label;
    if (active) {
      label = savedStatus || 'Ativado';
    } else if (accepted) {
      label = 'Desativado';
    } else {
      label = 'Não solicitado';
    }
    control.status.textContent = label;
    control.status.classList.toggle('is-on', active);

    if (active) maybeResolveExistingCep(row);
  }

  function showTermsModal(row, control, enabledInput, termsInput) {
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
          '<li>Serão cobradas somente as taxas do Asaas. Consulte a tabela vigente no próprio Asaas.</li>' +
          '<li>O Asaas poderá solicitar documentos e aprovar o cadastro antes da liberação.</li>' +
          '<li>Após a aprovação, o pagamento online será liberado automaticamente e os pedidos pelo WhatsApp continuarão disponíveis.</li>' +
          '<li>A chave técnica usada pela plataforma ficará armazenada de forma protegida e não será exibida no painel.</li>' +
          '<li>A VemDeDelivery não armazena dados de cartão e não define as taxas do Asaas.</li>' +
        '</ul>' +
        '<p style="margin:0 0 22px;line-height:1.55;color:#475569;">Ao aceitar, os dados que já existem no seu cadastro serão reaproveitados e você precisará completar apenas o que estiver faltando.</p>' +
        '<div style="display:flex;justify-content:flex-end;gap:12px;flex-wrap:wrap;">' +
          '<button type="button" data-payment-terms="decline" style="border:1px solid #cbd5e1;border-radius:10px;background:#fff;color:#334155;padding:10px 18px;font-weight:700;cursor:pointer;">Não aceito</button>' +
          '<button type="button" data-payment-terms="accept" style="border:0;border-radius:10px;background:#c8471e;color:#fff;padding:10px 18px;font-weight:700;cursor:pointer;">Aceito e continuar</button>' +
        '</div>' +
      '</div>';

    modal.addEventListener('click', function (event) {
      var action = event.target && event.target.getAttribute('data-payment-terms');
      if (!action) return;

      if (action === 'accept') {
        setTermsAccepted(termsInput, true);
        enabledInput.checked = true;
        updateCompactControl(row, control, enabledInput, termsInput);
        closeModal();
        window.setTimeout(function () {
          maybeResolveExistingCep(row);
          focusFirstMissing(row);
        }, 30);
        return;
      }

      enabledInput.checked = false;
      setTermsAccepted(termsInput, false);
      updateCompactControl(row, control, enabledInput, termsInput);
      closeModal();
    });

    modal.addEventListener('click', function (event) {
      if (event.target === modal) closeModal();
    });

    document.body.appendChild(modal);
    var acceptButton = modal.querySelector('[data-payment-terms="accept"]');
    if (acceptButton) acceptButton.focus();
  }

  function buildCompactControl(row, enabledInput, termsInput) {
    var section = row.querySelector('.payment-online-control-section') || wrapperFor(enabledInput) || row;
    var existing = section.querySelector('.payment-online-compact');
    if (existing && existing._paymentControl) return existing._paymentControl;

    var compact = document.createElement('div');
    compact.className = 'payment-online-compact';

    var main = document.createElement('div');
    main.className = 'payment-online-compact-main';

    var switchButton = document.createElement('button');
    switchButton.type = 'button';
    switchButton.className = 'payment-online-switch';
    switchButton.setAttribute('role', 'switch');
    switchButton.setAttribute('aria-label', 'Quero receber pagamentos online além do WhatsApp');

    var label = document.createElement('span');
    label.className = 'payment-online-label';
    label.textContent = 'Quero receber pagamentos online além do WhatsApp';

    var status = document.createElement('span');
    status.className = 'payment-online-status';

    var note = document.createElement('p');
    note.className = 'payment-online-note';
    note.textContent = 'O WhatsApp continua disponível. Ative para adicionar Pix e cartão de crédito online.';

    main.appendChild(switchButton);
    main.appendChild(label);
    main.appendChild(status);
    compact.appendChild(main);
    compact.appendChild(note);

    var description = section.querySelector('.description');
    if (description && description.parentNode) {
      description.insertAdjacentElement('afterend', compact);
    } else {
      section.appendChild(compact);
    }

    var control = {
      root: compact,
      switchButton: switchButton,
      status: status,
      savedStatus: sourceStatusText(row, enabledInput)
    };
    compact._paymentControl = control;

    switchButton.addEventListener('click', function () {
      if (enabledInput.checked && termsAccepted(termsInput)) {
        enabledInput.checked = false;
        updateCompactControl(row, control, enabledInput, termsInput);
        return;
      }

      // O aceite é solicitado apenas na primeira ativação. Se já foi aceito no
      // passado, reativar não obriga o lojista a aceitar o mesmo termo de novo.
      if (termsAccepted(termsInput)) {
        enabledInput.checked = true;
        updateCompactControl(row, control, enabledInput, termsInput);
        window.setTimeout(function () {
          maybeResolveExistingCep(row);
          focusFirstMissing(row);
        }, 30);
        return;
      }

      showTermsModal(row, control, enabledInput, termsInput);
    });

    label.addEventListener('click', function () {
      switchButton.click();
    });

    return control;
  }

  function bindCep(row) {
    var postalInput = findField(row, 'postal_code');
    if (!postalInput || postalInput.dataset.cepBound === '1') return;

    postalInput.dataset.cepBound = '1';
    postalInput.value = formatCep(postalInput.value);

    postalInput.addEventListener('input', function () {
      postalInput.value = formatCep(postalInput.value);
      delete postalInput.dataset.cepLoaded;
      if (digitsOnly(postalInput.value).length === 8) fillFromCep(row, postalInput);
    });

    postalInput.addEventListener('blur', function () {
      fillFromCep(row, postalInput);
    });
  }

  function initializeInput(enabledInput) {
    if (!enabledInput || enabledInput.dataset.paymentAccountV9 === '1') return;

    var row = inlineRootFor(enabledInput);
    if (!row) return;
    hideTechnicalInlineHeading(row);

    var prefix = fieldPrefix(enabledInput);
    if (!prefix) return;
    row._paymentPrefix = prefix;

    var termsInput = findField(row, 'terms_accepted');
    if (!termsInput) return;

    enabledInput.dataset.paymentAccountV9 = '1';
    enabledInput.style.setProperty('display', 'none', 'important');
    enabledInput.setAttribute('aria-hidden', 'true');
    enabledInput.tabIndex = -1;

    var control = buildCompactControl(row, enabledInput, termsInput);
    hideOriginalControls(row, enabledInput);
    bindCep(row);
    updateCompactControl(row, control, enabledInput, termsInput);
    row.classList.add('payment-online-js-ready');
  }

  function initializeAll() {
    document.querySelectorAll(
      '.payment-account-inline input[name$="-enabled"], input.payment-online-toggle[name$="-enabled"]'
    ).forEach(initializeInput);
  }

  document.addEventListener('formset:added', function () {
    window.setTimeout(initializeAll, 0);
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeAll);
  } else {
    initializeAll();
  }
}());
