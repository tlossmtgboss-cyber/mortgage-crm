import { useEffect, useRef, useCallback } from 'react';

/**
 * FOCUSABLE_SELECTOR - Elements that can receive focus within a container.
 */
const FOCUSABLE_SELECTOR =
  'a[href], area[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"]), details > summary, [contenteditable]';

/**
 * useFocusTrap - Reusable focus trap hook for modal dialogs and overlays.
 *
 * Features:
 * - Traps focus within a container ref when active
 * - Handles Tab / Shift+Tab cycling
 * - Escape key callback
 * - Auto-focuses first focusable element on activation
 * - Restores focus to the trigger element on deactivation
 * - Observes dynamic content changes via MutationObserver to recalculate focusable elements
 *
 * @param {React.RefObject} containerRef - Ref to the container element to trap focus within
 * @param {Object} options
 * @param {boolean} [options.active=true] - Whether the focus trap is active
 * @param {function} [options.onEscape] - Callback when Escape key is pressed
 * @param {boolean} [options.autoFocus=true] - Whether to auto-focus the first focusable element
 * @param {boolean} [options.restoreFocus=true] - Whether to restore focus on deactivation
 * @param {string} [options.initialFocusSelector] - CSS selector for the element to focus initially
 */
const useFocusTrap = (containerRef, {
  active = true,
  onEscape,
  autoFocus = true,
  restoreFocus = true,
  initialFocusSelector,
} = {}) => {
  const previousFocusRef = useRef(null);
  const focusableElementsRef = useRef([]);

  const updateFocusableElements = useCallback(() => {
    const container = containerRef.current;
    if (!container) {
      focusableElementsRef.current = [];
      return;
    }
    const elements = Array.from(container.querySelectorAll(FOCUSABLE_SELECTOR)).filter(
      (el) => {
        // Exclude hidden elements
        if (el.offsetParent === null && el.tagName !== 'BODY') return false;
        if (el.getAttribute('aria-hidden') === 'true') return false;
        return true;
      }
    );
    focusableElementsRef.current = elements;
  }, [containerRef]);

  useEffect(() => {
    if (!active) return;

    const container = containerRef.current;
    if (!container) return;

    // Store the element that had focus before the trap was activated
    previousFocusRef.current = document.activeElement;

    // Initial scan of focusable elements
    updateFocusableElements();

    // Auto-focus first focusable element or the one matching initialFocusSelector
    if (autoFocus) {
      requestAnimationFrame(() => {
        updateFocusableElements();
        const elements = focusableElementsRef.current;
        if (initialFocusSelector) {
          const target = container.querySelector(initialFocusSelector);
          if (target) {
            target.focus();
            return;
          }
        }
        if (elements.length > 0) {
          elements[0].focus();
        }
      });
    }

    // Handle keydown for tab trapping and escape
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        if (onEscape) {
          e.preventDefault();
          e.stopPropagation();
          onEscape();
        }
        return;
      }

      if (e.key !== 'Tab') return;

      // Re-scan in case content changed since last scan
      updateFocusableElements();
      const elements = focusableElementsRef.current;

      if (elements.length === 0) {
        e.preventDefault();
        return;
      }

      const first = elements[0];
      const last = elements[elements.length - 1];

      if (e.shiftKey) {
        // Shift+Tab: if focus is on first element, wrap to last
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        // Tab: if focus is on last element, wrap to first
        if (document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    container.addEventListener('keydown', handleKeyDown);

    // MutationObserver to handle dynamic content changes
    const observer = new MutationObserver(() => {
      updateFocusableElements();
    });
    observer.observe(container, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['disabled', 'tabindex', 'hidden', 'aria-hidden'],
    });

    return () => {
      container.removeEventListener('keydown', handleKeyDown);
      observer.disconnect();

      // Restore focus to the previously focused element
      if (restoreFocus && previousFocusRef.current) {
        // Use requestAnimationFrame to ensure the element is still in the DOM
        requestAnimationFrame(() => {
          if (previousFocusRef.current && typeof previousFocusRef.current.focus === 'function') {
            previousFocusRef.current.focus();
          }
        });
      }
    };
  }, [active, containerRef, onEscape, autoFocus, restoreFocus, initialFocusSelector, updateFocusableElements]);
};

export default useFocusTrap;
