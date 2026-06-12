import { initToast } from './ui/toast.js';
import { initModal } from './ui/modal.js';
import { initCartBadge } from './ui/cart-badge.js';
import { initCatalogPage } from './pages/catalog.js';
import { initCartPage } from './pages/cart.js';
import { initCheckoutPage } from './pages/checkout.js';

document.addEventListener('DOMContentLoaded', () => {
  initToast();
  initModal();
  initCartBadge();

  const page = document.body.dataset.page;
  console.log('Iniciando página:', page);

  if (page === 'catalog') {
    initCatalogPage();
  }

  if (page === 'cart') {
    initCartPage();
  }

  if (page === 'checkout') {
    initCheckoutPage();
  }
});
