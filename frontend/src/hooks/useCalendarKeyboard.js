import { useEffect, useCallback } from 'react';

/**
 * useCalendarKeyboard - Full keyboard navigation for the Calendar page.
 *
 * Provides shortcuts for navigating dates, switching views, creating events,
 * opening search, and cycling through events in the sidebar.
 *
 * @param {Object} options
 * @param {function} options.onPrev - Navigate to previous period
 * @param {function} options.onNext - Navigate to next period
 * @param {function} options.onToday - Navigate to today
 * @param {function} options.onSetView - Set calendar view (receives 'day'|'week'|'month')
 * @param {function} options.onNewEvent - Open the create event modal
 * @param {function} options.onOpenSearch - Open the search overlay
 * @param {function} options.onCloseModals - Close all open modals
 * @param {function} options.onToggleShortcutsHelp - Toggle keyboard shortcuts help modal
 * @param {function} options.onSelectPrevEvent - Select the previous event in the sidebar list
 * @param {function} options.onSelectNextEvent - Select the next event in the sidebar list
 * @param {function} options.onOpenSelectedEvent - Open the currently selected event for editing
 * @param {boolean} options.hasModalOpen - Whether any modal is currently open (disables most shortcuts)
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
    // Don't capture keys when typing in form elements
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return;

    // Escape always works (for closing modals)
    if (e.key === 'Escape') {
      onCloseModals?.();
      return;
    }

    // Don't handle other shortcuts when a modal is open
    if (hasModalOpen) return;

    switch (e.key) {
      // Navigation
      case 'ArrowLeft':
        if (e.shiftKey) {
          e.preventDefault();
          onPrev?.();
        }
        break;
      case 'ArrowRight':
        if (e.shiftKey) {
          e.preventDefault();
          onNext?.();
        }
        break;
      case 'ArrowUp':
        e.preventDefault();
        onSelectPrevEvent?.();
        break;
      case 'ArrowDown':
        e.preventDefault();
        onSelectNextEvent?.();
        break;

      // View switching (only when not holding meta/ctrl)
      case 'd':
        if (!e.metaKey && !e.ctrlKey) {
          onSetView?.('day');
        }
        break;
      case 'w':
        if (!e.metaKey && !e.ctrlKey) {
          onSetView?.('week');
        }
        break;
      case 'm':
        if (!e.metaKey && !e.ctrlKey) {
          onSetView?.('month');
        }
        break;

      // Actions
      case 't':
        if (!e.metaKey && !e.ctrlKey) {
          onToday?.();
        }
        break;
      case 'n':
        if (!e.metaKey && !e.ctrlKey) {
          e.preventDefault();
          onNewEvent?.();
        }
        break;
      case 'Enter':
        onOpenSelectedEvent?.();
        break;
      case '/':
        e.preventDefault();
        onOpenSearch?.();
        break;
      case '?':
        onToggleShortcutsHelp?.();
        break;
      default:
        break;
    }
  }, [
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
    hasModalOpen,
  ]);

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);
}

export default useCalendarKeyboard;
