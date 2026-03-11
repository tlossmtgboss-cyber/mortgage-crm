import { useEffect } from 'react';

/**
 * useFocusTrap - Reusable focus trap hook for modal dialogs.
 *
 * Traps focus within a modal element matching `modalSelector` when `isActive` is true.
 * Handles Tab/Shift+Tab cycling and Escape to close.
 *
 * @param {boolean} isActive - Whether the focus trap is active (e.g., modal open state)
 * @param {Object} options
 * @param {string} [options.modalSelector='.scheduler-modal'] - CSS selector for the modal element
 * @param {function} [options.onEscape] - Callback when Escape key is pressed
 */
const useFocusTrap = (isActive, { modalSelector = '.scheduler-modal', onEscape } = {}) => {
  useEffect(() => {
    if (!isActive) return;

    const modal = document.querySelector(modalSelector);
    if (!modal) return;

    const focusableSelector = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
    const focusable = modal.querySelectorAll(focusableSelector);
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const previousFocus = document.activeElement;

    first?.focus();

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        if (onEscape) onEscape();
        return;
      }
      if (e.key !== 'Tab') return;
      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };

    modal.addEventListener('keydown', handleKeyDown);
    return () => {
      modal.removeEventListener('keydown', handleKeyDown);
      previousFocus?.focus();
    };
  }, [isActive, modalSelector, onEscape]);
};

export default useFocusTrap;
