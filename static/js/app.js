import { initToast } from './ui/toast.js';
import { initModal } from './ui/modal.js';
import { initCartBadge } from './ui/cart-badge.js';

const PAGE_MODULES = {
  catalog:  () => import('./pages/catalog.js').then(m => m.initCatalogPage()),
  cart:     () => import('./pages/cart.js').then(m => m.initCartPage()),
  checkout: () => import('./pages/checkout.js').then(m => m.initCheckoutPage()),
};

document.addEventListener('DOMContentLoaded', () => {
  initToast();
  initModal();
  initCartBadge();

  const page = document.body.dataset.page;
  if (page && PAGE_MODULES[page]) {
    PAGE_MODULES[page]().catch(console.error);
  }
});