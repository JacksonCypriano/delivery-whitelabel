import { EVENTS, on } from '../core/events.js';

let toastContainer = null;

function createToastContainer() {
  const container = document.createElement('div');
  container.setAttribute('data-toast-container', '');
  container.className = 'fixed top-4 right-4 z-[9999] flex flex-col gap-3';
  document.body.appendChild(container);
  return container;
}

function getToastContainer() {
  if (toastContainer) return toastContainer;

  toastContainer =
    document.querySelector('[data-toast-container]') || createToastContainer();

  return toastContainer;
}

function getToastClasses(type) {
  const base =
    'pointer-events-auto rounded-xl px-4 py-3 text-sm font-medium shadow-lg border transition-opacity duration-300';

  const variants = {
    success: 'bg-green-50 text-green-800 border-green-200',
    error: 'bg-red-50 text-red-800 border-red-200',
    warning: 'bg-yellow-50 text-yellow-800 border-yellow-200',
    info: 'bg-blue-50 text-blue-800 border-blue-200',
  };

  return `${base} ${variants[type] || variants.info}`;
}

export function showToast(message, type = 'info', timeout = 3000) {
  if (!message) return;

  const container = getToastContainer();
  const toast = document.createElement('div');

  toast.className = getToastClasses(type);
  toast.textContent = message;
  toast.style.opacity = '1';

  container.appendChild(toast);

  window.setTimeout(() => {
    toast.style.opacity = '0';

    window.setTimeout(() => {
      toast.remove();
    }, 300);
  }, timeout);
}

export function initToast() {
  getToastContainer();

  on(EVENTS.TOAST_SHOW, (event) => {
    const { message, type = 'info', timeout = 3000 } = event.detail || {};
    showToast(message, type, timeout);
  });
}