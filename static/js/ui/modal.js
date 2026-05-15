import { EVENTS, emit, on } from '../core/events.js';

function getModalElement(name) {
  return document.querySelector(`[data-modal="${name}"]`);
}

export function openModal(name) {
  const modal = getModalElement(name);
  if (!modal) return;

  modal.classList.remove('hidden');
  modal.classList.add('flex');
  document.body.classList.add('overflow-hidden');
}

export function closeModal(name) {
  const modal = getModalElement(name);
  if (!modal) return;

  modal.classList.add('hidden');
  modal.classList.remove('flex');

  if (!document.querySelector('[data-modal].flex')) {
    document.body.classList.remove('overflow-hidden');
  }
}

export function closeAllModals() {
  document.querySelectorAll('[data-modal]').forEach((modal) => {
    modal.classList.add('hidden');
    modal.classList.remove('flex');
  });

  document.body.classList.remove('overflow-hidden');
}

function bindModalTriggers() {
  document.addEventListener('click', (event) => {
    const openTrigger = event.target.closest('[data-modal-open]');
    if (openTrigger) {
      const modalName = openTrigger.dataset.modalOpen;
      emit(EVENTS.MODAL_OPEN, { name: modalName });
      return;
    }

    const closeTrigger = event.target.closest('[data-modal-close]');
    if (closeTrigger) {
      const modalName = closeTrigger.dataset.modalClose;
      if (modalName) {
        emit(EVENTS.MODAL_CLOSE, { name: modalName });
      } else {
        closeAllModals();
      }
      return;
    }

    const overlay = event.target.closest('[data-modal-overlay]');
    if (overlay) {
      const modal = overlay.closest('[data-modal]');
      if (modal?.dataset.modal) {
        emit(EVENTS.MODAL_CLOSE, { name: modal.dataset.modal });
      }
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      closeAllModals();
    }
  });
}

export function initModal() {
  bindModalTriggers();

  on(EVENTS.MODAL_OPEN, (event) => {
    const { name } = event.detail || {};
    if (name) openModal(name);
  });

  on(EVENTS.MODAL_CLOSE, (event) => {
    const { name } = event.detail || {};
    if (name) {
      closeModal(name);
    } else {
      closeAllModals();
    }
  });
}