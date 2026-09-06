(function () {
  'use strict';

  function digits(value) {
    return String(value || '').replace(/\D/g, '');
  }

  function formatCep(value) {
    var d = digits(value).slice(0, 8);
    if (d.length <= 5) return d;
    return d.slice(0, 5) + '-' + d.slice(5);
  }

  function formatWhatsapp(value) {
    var d = digits(value).slice(0, 13);
    if (!d) return '';
    if (d.indexOf('55') !== 0 && d.length <= 11) d = '55' + d;
    if (d.length <= 2) return '+' + d;
    var country = d.slice(0, 2);
    var area = d.slice(2, 4);
    var number = d.slice(4);
    var result = '+' + country;
    if (area) result += ' (' + area + ')';
    if (number) {
      if (number.length <= 4) result += ' ' + number;
      else if (number.length <= 8) result += ' ' + number.slice(0, 4) + '-' + number.slice(4);
      else result += ' ' + number.slice(0, 5) + '-' + number.slice(5, 9);
    }
    return result;
  }

  function normalizeTime(value) {
    var raw = String(value || '').trim();
    if (!raw) return '';

    var onlyDigits = digits(raw).slice(0, 4);
    var hour;
    var minute;

    if (raw.indexOf(':') >= 0) {
      var parts = raw.split(':');
      hour = parseInt(parts[0], 10);
      minute = parts.length > 1 && parts[1] !== '' ? parseInt(parts[1], 10) : 0;
    } else if (onlyDigits.length <= 2) {
      hour = parseInt(onlyDigits, 10);
      minute = 0;
    } else if (onlyDigits.length === 3) {
      hour = parseInt(onlyDigits.slice(0, 1), 10);
      minute = parseInt(onlyDigits.slice(1), 10);
    } else {
      hour = parseInt(onlyDigits.slice(0, 2), 10);
      minute = parseInt(onlyDigits.slice(2), 10);
    }

    if (!Number.isFinite(hour) || !Number.isFinite(minute) || hour < 0 || hour > 23 || minute < 0 || minute > 59) {
      return raw;
    }

    return String(hour).padStart(2, '0') + ':' + String(minute).padStart(2, '0');
  }

  function ensureStatus(input) {
    var id = 'store-cep-status';
    var status = document.getElementById(id);
    if (status) return status;
    status = document.createElement('div');
    status.id = id;
    status.style.marginTop = '6px';
    status.style.fontSize = '12px';
    status.style.lineHeight = '1.4';
    input.insertAdjacentElement('afterend', status);
    return status;
  }

  function setStatus(input, message, error) {
    var status = ensureStatus(input);
    status.textContent = message || '';
    status.style.color = error ? '#dc2626' : '#64748b';
  }

  function field(name) {
    return document.getElementById('id_' + name) || document.querySelector('[name="' + name + '"]');
  }

  function lookupStoreCep(input) {
    var cep = digits(input.value);
    if (cep.length !== 8) {
      if (cep.length) setStatus(input, 'Informe um CEP válido com 8 dígitos.', true);
      return;
    }
    if (input.dataset.loading === '1' || input.dataset.loadedCep === cep) return;

    input.dataset.loading = '1';
    setStatus(input, 'Consultando CEP...', false);

    fetch('/api/cep/' + encodeURIComponent(cep) + '/', {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' }
    })
      .then(function (response) {
        return response.json().catch(function () { return {}; }).then(function (data) {
          if (!response.ok || data.success === false) throw new Error(data.error || 'Não foi possível consultar o CEP.');
          return data;
        });
      })
      .then(function (data) {
        input.value = formatCep(data.cep || cep);
        input.dataset.loadedCep = cep;

        var address = field('pickup_address');
        var neighborhood = field('pickup_neighborhood');
        var city = field('pickup_city');
        var complement = field('pickup_complement');
        var number = field('pickup_number');

        if (address && data.street) address.value = data.street;
        if (neighborhood && data.neighborhood) neighborhood.value = data.neighborhood;
        if (city && data.city) city.value = data.city;
        if (complement && data.complement && !String(complement.value || '').trim()) complement.value = data.complement;

        var label = [data.city, data.state].filter(Boolean).join(' / ');
        setStatus(input, label ? 'CEP encontrado: ' + label + '. Informe o número e o complemento, se houver.' : 'CEP encontrado. Informe o número e o complemento, se houver.', false);
        if (number && !String(number.value || '').trim()) number.focus();
      })
      .catch(function (error) {
        delete input.dataset.loadedCep;
        setStatus(input, error.message || 'Não foi possível consultar o CEP agora.', true);
      })
      .finally(function () {
        delete input.dataset.loading;
      });
  }

  function timeSibling(checkbox, fieldName) {
    var name = String(checkbox.name || '');
    if (!name) return null;
    var targetName = name.replace(/is_open$/, fieldName);
    return document.querySelector('[name="' + targetName.replace(/"/g, '\"') + '"]');
  }

  function syncBusinessOpen(checkbox) {
    var opening = timeSibling(checkbox, 'opening_time');
    var closing = timeSibling(checkbox, 'closing_time');
    [opening, closing].forEach(function (input) {
      if (!input) return;
      input.disabled = !checkbox.checked;
      input.setAttribute('aria-disabled', checkbox.checked ? 'false' : 'true');
    });
  }

  function init() {
    document.querySelectorAll('[data-store-whatsapp="1"]').forEach(function (input) {
      if (input.value) input.value = formatWhatsapp(input.value);
      input.addEventListener('input', function () {
        var caretAtEnd = input.selectionStart === input.value.length;
        input.value = formatWhatsapp(input.value);
        if (caretAtEnd) input.setSelectionRange(input.value.length, input.value.length);
      });
    });

    document.querySelectorAll('[data-store-cep="1"]').forEach(function (input) {
      if (input.value) input.value = formatCep(input.value);
      input.addEventListener('input', function () {
        input.value = formatCep(input.value);
        if (digits(input.value).length === 8) lookupStoreCep(input);
      });
      input.addEventListener('blur', function () { lookupStoreCep(input); });
    });

    document.querySelectorAll('[data-business-time="1"]').forEach(function (input) {
      input.addEventListener('blur', function () {
        input.value = normalizeTime(input.value);
      });
    });

    document.querySelectorAll('[data-business-open="1"]').forEach(function (checkbox) {
      syncBusinessOpen(checkbox);
      checkbox.addEventListener('change', function () { syncBusinessOpen(checkbox); });
    });

    document.querySelectorAll('form').forEach(function (form) {
      form.addEventListener('submit', function () {
        form.querySelectorAll('[data-store-whatsapp="1"]').forEach(function (input) {
          input.value = digits(input.value);
        });
        form.querySelectorAll('[data-business-time="1"]').forEach(function (input) {
          input.value = normalizeTime(input.value);
        });
      });
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
