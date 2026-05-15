import { getConfig } from './config.js';

function getCookie(name) {
  const cookies = document.cookie ? document.cookie.split(';') : [];

  for (const cookie of cookies) {
    const trimmed = cookie.trim();
    if (trimmed.startsWith(`${name}=`)) {
      return decodeURIComponent(trimmed.substring(name.length + 1));
    }
  }

  return null;
}

export function getCSRFToken() {
  return (
    getConfig('csrfToken') ||
    getCookie('csrftoken') ||
    document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
    ''
  );
}