import { initAddToCart } from '../features/add-to-cart.js';
import { initHalfHalf } from '../features/half-half.js';

export function initCatalogPage() {
  initAddToCart();
  initHalfHalf();
}