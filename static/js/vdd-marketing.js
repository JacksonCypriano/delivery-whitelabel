/* Marketing landing only. Never load on tenant catalogues/admin/homolog.
 * WhatsApp reference is operational; UTM, click IDs and GA client ID require opt-in.
 */
(function () {
  'use strict';
  const consentKey = 'vdd_analytics_permission';
  const touchKey = 'vdd_analytics_first_touch';
  const banner = document.getElementById('vdd-consent-banner');
  const data = document.getElementById('vdd-marketing-data');
  const allowed = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'gclid', 'gbraid', 'wbraid'];
  const getChoice = () => { try { return localStorage.getItem(consentKey); } catch (_) { return null; } };
  const consented = () => getChoice() === 'yes';
  const removeAnalyticsCookies = () => {
    document.cookie.split(';').forEach(function (value) {
      const name = value.trim().split('=')[0];
      if (!/^(_ga|_gcl_)/.test(name)) return;
      ['', '.vemdedelivery.com.br', 'vemdedelivery.com.br'].forEach(function (domain) {
        document.cookie = name + '=; Max-Age=0; path=/' + (domain ? '; domain=' + domain : '');
      });
    });
  };
  const showBanner = () => { if (banner) banner.hidden = false; };
  if (!getChoice()) showBanner();
  document.querySelectorAll('[data-vdd-consent]').forEach(function (button) {
    button.addEventListener('click', function () {
      const decision = button.getAttribute('data-vdd-consent') === 'yes' ? 'yes' : 'no';
      try { localStorage.setItem(consentKey, decision); } catch (_) {}
      if (decision === 'no') {
        try { sessionStorage.removeItem(touchKey); } catch (_) {}
        removeAnalyticsCookies();
      }
      window.location.reload(); // GTM loads only after explicit consent.
    });
  });
  document.querySelectorAll('[data-vdd-reopen]').forEach(function (button) {
    button.addEventListener('click', showBanner);
  });

  // First-touch campaign params are not stored before explicit approval.
  if (consented()) {
    try {
      const params = new URLSearchParams(window.location.search);
      const touched = {};
      allowed.forEach(k => { if (params.get(k)) touched[k] = params.get(k).slice(0, 180); });
      if (Object.keys(touched).length && !sessionStorage.getItem(touchKey)) {
        sessionStorage.setItem(touchKey, JSON.stringify(touched));
      }
    } catch (_) {}
  }
  const clientId = () => {
    const cookie = document.cookie.split(';').map(v => v.trim()).find(v => v.indexOf('_ga=') === 0);
    if (!cookie) return '';
    const parts = decodeURIComponent(cookie.slice(4)).split('.');
    const candidate = parts.length >= 4 ? parts.slice(-2).join('.') : '';
    return /^\d{1,20}\.\d{1,20}$/.test(candidate) ? candidate : '';
  };
  if (!data || !data.dataset.token) return;
  document.querySelectorAll('a[href^="https://wa.me/"]').forEach(function (link) {
    link.addEventListener('click', function () {
      const body = new FormData();
      body.append('csrfmiddlewaretoken', data.dataset.csrf);
      body.append('token', data.dataset.token);
      body.append('cta', (link.dataset.cta || 'contact').slice(0, 64));
      body.append('consent', consented() ? 'yes' : 'no');
      if (consented()) {
        try {
          const touch = JSON.parse(sessionStorage.getItem(touchKey) || '{}');
          allowed.forEach(k => { if (touch[k]) body.append(k, String(touch[k]).slice(0, 180)); });
          const id = clientId();
          if (id) body.append('ga_client_id', id);
        } catch (_) {}
      }
      try {
        if (navigator.sendBeacon && navigator.sendBeacon(data.dataset.clickUrl, body)) return;
        fetch(data.dataset.clickUrl, { method: 'POST', body, credentials: 'same-origin', keepalive: true });
      } catch (_) { /* The reference is still in the WhatsApp message. */ }
    });
  });
})();
