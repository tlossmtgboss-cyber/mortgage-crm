import { useEffect, useCallback } from 'react';

/**
 * useCalendarKeyboard - Keyboard shortcut hook for the Calendar page.
 *
 * Shortcuts (only active when no input/textarea/select is focused):
 *   n           - Open new appointment modal
 *   t           - Go to today
 *   w           - Switch to week view
 *   m           - Switch to month view
 *   d           - Switch to day view
 *   a           - Switch to agenda view
 *   ArrowLeft   - Navigate to previous period
 *   ArrowRight  - Navigate to next period
 *   ArrowUp     - Select previous event in sidebar
 *   ArrowDown   - Select next event in sidebar
 *   Enter       - Open the currently selected event
 *   Escape      - Close any open modal
 *   / or Ctrl+K - Focus search
 *   ?           - Show/hide keyboard shortcuts help overlay
 *
 * When a modal is open, only Escape and Ctrl+K are active.
 *
 * @param {Object} options
 * @param {function} options.onPrev           - Navigate to previous period
 * @param {function} options.onNext           - Navigate to next period
 * @param {function} options.onToday          - Navigate to today
 * @param {function} options.onSetView        - Switch view (receives 'week'|'month'|'day'|'agenda')
 * @param {function} options.onNewEvent       - Open new appointment modal
 * @param {function} options.onOpenSearch     - Open search overlay
 * @param {function} options.onCloseModals    - Close currently open modal
 * @param {function} options.onToggleShortcutsHelp - Toggle the shortcuts help overlay
 * @param {function} options.onSelectPrevEvent - Select previous event in list
 * @param {function} options.onSelectNextEvent - Select next event in list
 * @param {function} options.onOpenSelectedEvent - Open the currently selected event
 * @param {boolean}  options.hasModalOpen     - Whether any modal is currently open
 */
export function useCalendarKeyboard({
  onPrev,
  onNext,
  onToday,
  onSetView,
  onNewEvent,
  onOpenSearch,
  onCloseModals,
  onToggleShortcutsHelp,
  onSelectPrevEvent,
  onSelectNextEvent,
  onOpenSelectedEvent,
  hasModalOpen = false,
}) {
  const handleKeyDown = useCallback((e) => {
    // Escape always works — close the topmost modal
    if (e.key === 'Escape') {
      if (hasModalOpen) {
        e.preventDefault();
        onCloseModals?.();
      }
      return;
    }

    // Ctrl+K / Cmd+K — open search regardless of focus or modal state
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      onOpenSearch?.();
      return;
    }

    // Skip all other shortcuts when a modal is open
    if (hasModalOpen) return;

    // Skip when focus is inside an input, textarea, select, or contenteditable
    const tag = document.activeElement?.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    if (document.activeElement?.isContentEditable) return;

    // Don't intercept when modifier keys are held (except Shift for '?')
    if (e.ctrlKey || e.metaKey || e.altKey) return;

    switch (e.key) {
      // --- New appointment ---
      case 'n':
        e.preventDefault();
        onNewEvent?.();
        break;

      // --- Go to today ---
      case 't':
        e.preventDefault();
        onToday?.();
        break;

      // --- View switching ---
      case 'w':
        e.preventDefault();
        onSetView?.('week');
        break;

      case 'm':
        e.preventDefault();
        onSetView?.('month');
        break;

      case 'd':
        e.preventDefault();
        onSetView?.('day');
        break;

      case 'a':
        e.preventDefault();
        onSetView?.('agenda');
        break;

      // --- Period navigation ---
      case 'ArrowLeft':
        e.preventDefault();
        onPrev?.();
        break;

      case 'ArrowRight':
        e.preventDefault();
        onNext?.();
        break;

      // --- Event list navigation ---
      case 'ArrowUp':
        e.preventDefault();
        onSelectPrevEvent?.();
        break;

      case 'ArrowDown':
        e.preventDefault();
        onSelectNextEvent?.();
        break;

      case 'Enter':
        e.preventDefault();
        onOpenSelectedEvent?.();
        break;

      // --- Search ---
      case '/':
        e.preventDefault();
        onOpenSearch?.();
        break;

      // --- Shortcuts help ---
      case '?':
        e.preventDefault();
        onToggleShortcutsHelp?.();
        break;

      default:
        break;
    }
  }, [
    hasModalOpen,
    onCloseModals,
    onNewEvent,
    onToday,
    onSetView,
    onPrev,
    onNext,
    onOpenSearch,
    onToggleShortcutsHelp,
    onSelectPrevEvent,
    onSelectNextEvent,
    onOpenSelectedEvent,
  ]);

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);
}

export default useCalendarKeyboard;
