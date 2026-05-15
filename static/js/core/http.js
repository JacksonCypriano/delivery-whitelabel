import { getCSRFToken } from './csrf.js';

async function parseResponse(response) {
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return response.json().catch(() => null);
  }
  return response.text().catch(() => null);
}

export async function request(url, options = {}) {
  const {
    method = 'GET',
    data = null,
    headers = {},
    body = null,
  } = options;

  const finalHeaders = {
    'X-Requested-With': 'XMLHttpRequest',
    ...headers,
  };

  let finalBody = body;

  if (data !== null && body === null) {
    finalHeaders['Content-Type'] = 'application/json';
    finalBody = JSON.stringify(data);
  }

  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method.toUpperCase())) {
    const csrfToken = getCSRFToken();
    if (csrfToken) {
      finalHeaders['X-CSRFToken'] = csrfToken;
    }
  }

  const response = await fetch(url, {
    method,
    headers: finalHeaders,
    body: finalBody,
    credentials: 'same-origin',
  });

  const parsedData = await parseResponse(response);

  return {
    ok: response.ok,
    status: response.status,
    data: parsedData,
    response,
  };
}

export function getJSON(url, options = {}) {
  return request(url, { ...options, method: 'GET' });
}

export function postJSON(url, data = {}, options = {}) {
  return request(url, { ...options, method: 'POST', data });
}

export function patchJSON(url, data = {}, options = {}) {
  return request(url, { ...options, method: 'PATCH', data });
}

export function deleteJSON(url, data = {}, options = {}) {
  return request(url, { ...options, method: 'DELETE', data });
}

// Envia dados como FormData (usado pelo cart.js para update_quantity e remove)
export async function postForm(url, payload = {}) {
  const form = new FormData();
  const csrf = getCSRFToken();

  Object.entries(payload).forEach(([k, v]) => form.append(k, String(v)));
  if (csrf) form.append('csrfmiddlewaretoken', csrf);

  const response = await fetch(url, {
    method: 'POST',
    body: form,
    headers: {
      'X-Requested-With': 'XMLHttpRequest',
      ...(csrf ? { 'X-CSRFToken': csrf } : {}),
    },
    credentials: 'same-origin',
  });

  const parsedData = await parseResponse(response);

  return {
    ok: response.ok,
    status: response.status,
    data: parsedData,
    response,
  };
}