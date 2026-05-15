export const EVENTS = {
  TOAST_SHOW: 'toast:show',
  MODAL_OPEN: 'modal:open',
  MODAL_CLOSE: 'modal:close',
  CART_UPDATED: 'cart:updated',
};

export function emit(eventName, detail = {}) {
  document.dispatchEvent(new CustomEvent(eventName, { detail }));
}

export function on(eventName, handler) {
  document.addEventListener(eventName, handler);
}

export function off(eventName, handler) {
  document.removeEventListener(eventName, handler);
}