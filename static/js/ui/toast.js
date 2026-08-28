import { EVENTS, on } from '../core/events.js';

let toastContainer = null;


function createToastContainer() {
  const container = document.createElement('div');

  container.setAttribute(
    'data-toast-container',
    ''
  );

  container.className = [
    'fixed',
    'top-20',
    'left-1/2',
    '-translate-x-1/2',
    'z-[9999]',
    'flex',
    'flex-col',
    'items-center',
    'gap-3',
    'w-[calc(100%-2rem)]',
    'max-w-md',
    'pointer-events-none',
  ].join(' ');

  document.body.appendChild(container);

  return container;
}


function getToastContainer() {
  if (toastContainer) {
    return toastContainer;
  }

  toastContainer =
    document.querySelector(
      '[data-toast-container]'
    )
    || createToastContainer();

  return toastContainer;
}


function getToastClasses(type) {
  const base = [
    'pointer-events-auto',
    'w-auto',
    'max-w-full',
    'rounded-2xl',
    'px-4',
    'py-3',
    'text-sm',
    'font-semibold',
    'shadow-xl',
    'border',
    'backdrop-blur-sm',

    'transition-all',
    'duration-300',
    'ease-out',

    'opacity-0',
    '-translate-y-4',
  ].join(' ');

  const variants = {
    success: [
      'bg-green-50',
      'text-green-800',
      'border-green-200',
      'dark:bg-green-950',
      'dark:text-green-200',
      'dark:border-green-800',
    ].join(' '),

    error: [
      'bg-red-50',
      'text-red-800',
      'border-red-200',
      'dark:bg-red-950',
      'dark:text-red-200',
      'dark:border-red-800',
    ].join(' '),

    warning: [
      'bg-yellow-50',
      'text-yellow-800',
      'border-yellow-200',
      'dark:bg-yellow-950',
      'dark:text-yellow-200',
      'dark:border-yellow-800',
    ].join(' '),

    info: [
      'bg-blue-50',
      'text-blue-800',
      'border-blue-200',
      'dark:bg-blue-950',
      'dark:text-blue-200',
      'dark:border-blue-800',
    ].join(' '),
  };

  return `
    ${base}
    ${variants[type] || variants.info}
  `;
}


function getToastIcon(type) {
  const icons = {
    success: '✓',
    error: '✕',
    warning: '!',
    info: 'i',
  };

  return icons[type] || icons.info;
}


export function showToast(
  message,
  type = 'info',
  timeout = 3000
) {
  if (!message) {
    return;
  }

  const container =
    getToastContainer();

  const toast =
    document.createElement('div');

  toast.className =
    getToastClasses(type);


  /*
   * Conteúdo
   */

  const content =
    document.createElement('div');

  content.className = [
    'flex',
    'items-center',
    'gap-2.5',
  ].join(' ');


  /*
   * Ícone
   */

  const icon =
    document.createElement('span');

  icon.className = [
    'flex',
    'items-center',
    'justify-center',
    'w-5',
    'h-5',
    'rounded-full',
    'text-xs',
    'font-bold',
    'flex-shrink-0',
  ].join(' ');

  icon.textContent =
    getToastIcon(type);


  /*
   * Mensagem
   */

  const text =
    document.createElement('span');

  text.textContent =
    message;


  content.appendChild(icon);
  content.appendChild(text);

  toast.appendChild(content);

  container.appendChild(toast);


  /*
   * Animação de entrada
   */

  requestAnimationFrame(() => {

    requestAnimationFrame(() => {

      toast.classList.remove(
        'opacity-0',
        '-translate-y-4'
      );

      toast.classList.add(
        'opacity-100',
        'translate-y-0'
      );

    });

  });


  /*
   * Remoção
   */

  window.setTimeout(() => {

    toast.classList.remove(
      'opacity-100',
      'translate-y-0'
    );

    toast.classList.add(
      'opacity-0',
      '-translate-y-4'
    );


    window.setTimeout(() => {
      toast.remove();
    }, 300);

  }, timeout);
}


export function initToast() {
  getToastContainer();

  on(
    EVENTS.TOAST_SHOW,
    event => {

      const {
        message,
        type = 'info',
        timeout = 3000,
      } = event.detail || {};

      showToast(
        message,
        type,
        timeout
      );

    }
  );
}