import React, { useEffect, useRef } from 'react';

const SHORTCUT_SECTIONS = [
  {
    section: 'Navigation',
    items: [
      { keys: ['Shift', '\u2190'], action: 'Previous period' },
      { keys: ['Shift', '\u2192'], action: 'Next period' },
      { keys: ['\u2191'], action: 'Previous event' },
      { keys: ['\u2193'], action: 'Next event' },
      { keys: ['T'], action: 'Go to today' },
    ],
  },
  {
    section: 'Views',
    items: [
      { keys: ['D'], action: 'Day view' },
      { keys: ['W'], action: 'Week view' },
      { keys: ['M'], action: 'Month view' },
    ],
  },
  {
    section: 'Actions',
    items: [
      { keys: ['N'], action: 'New appointment' },
      { keys: ['Enter'], action: 'Open selected event' },
      { keys: ['Esc'], action: 'Close modal' },
      { keys: ['/'], action: 'Search' },
      { keys: ['?'], action: 'Show shortcuts' },
    ],
  },
];

/**
 * KeyboardShortcutsHelp - Modal overlay showing all keyboard shortcuts.
 *
 * Props:
 *   isOpen  - Whether the modal is visible
 *   onClose - Callback to close the modal
 */
function KeyboardShortcutsHelp({ isOpen, onClose }) {
  const modalRef = useRef(null);

  // Focus trap and escape handling
  useEffect(() => {
    if (!isOpen) return;

    const modal = modalRef.current;
    if (!modal) return;

    const previousFocus = document.activeElement;

    // Focus the close button on open
    const closeBtn = modal.querySelector('.shortcuts-close-btn');
    closeBtn?.focus();

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose?.();
        return;
      }
      // Trap Tab within the modal
      if (e.key === 'Tab') {
        const focusable = modal.querySelectorAll(
          'button, [href], [tabindex]:not([tabindex="-1"])'
        );
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
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
      }
    };

    modal.addEventListener('keydown', handleKeyDown);
    return () => {
      modal.removeEventListener('keydown', handleKeyDown);
      previousFocus?.focus();
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      className="shortcuts-overlay"
      onClick={onClose}
      role="presentation"
    >
      <div
        ref={modalRef}
        className="shortcuts-modal"
        role="dialog"
        aria-modal="true"
        aria-label="Keyboard shortcuts"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="shortcuts-header">
          <h2 className="shortcuts-title">Keyboard Shortcuts</h2>
          <button
            className="shortcuts-close-btn"
            onClick={onClose}
            aria-label="Close keyboard shortcuts"
          >
            &times;
          </button>
        </div>

        <div className="shortcuts-body">
          {SHORTCUT_SECTIONS.map((section) => (
            <div key={section.section} className="shortcuts-section">
              <h3 className="shortcuts-section-title">{section.section}</h3>
              <dl className="shortcuts-list">
                {section.items.map((item, idx) => (
                  <div key={idx} className="shortcut-row">
                    <dt className="shortcut-keys">
                      {item.keys.map((key, ki) => (
                        <span key={ki}>
                          <kbd className="shortcut-key">{key}</kbd>
                          {ki < item.keys.length - 1 && (
                            <span className="shortcut-separator">+</span>
                          )}
                        </span>
                      ))}
                    </dt>
                    <dd className="shortcut-action">{item.action}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
        </div>

        <div className="shortcuts-footer">
          <span className="shortcuts-hint">
            Press <kbd className="shortcut-key">?</kbd> to toggle this dialog
          </span>
        </div>
      </div>
    </div>
  );
}

export default KeyboardShortcutsHelp;
