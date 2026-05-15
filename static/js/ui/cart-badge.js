import { EVENTS, on } from '../core/events.js';

export function updateCartBadge(count = 0) {
  const elements = document.querySelectorAll('[data-cart-count]');

  elements.forEach((element) => {
    element.textContent = count;

    if (count > 0) {
      element.classList.remove('hidden');
    } else {
      element.classList.add('hidden');
    }
  });
}

export function initCartBadge() {
  const initialCount = Number(
    document.querySelector('[data-cart-count]')?.dataset.initialCount || 0
  );

  updateCartBadge(initialCount);

  on(EVENTS.CART_UPDATED, (event) => {
    const count = Number(event.detail?.count ?? 0);
    updateCartBadge(count);
  });
}