import React, { useEffect, useRef } from 'react';

const SHORTCUT_SECTIONS = [
  {
    section: 'Navigation',
    items: [
      { keys: ['\u2190'], action: 'Previous period' },
      { keys: ['\u2192'], action: 'Next period' },
      { keys: ['\u2191'], action: 'Select previous event' },
      { keys: ['\u2193'], action: 'Select next event' },
      { keys: ['T'], action: 'Go to today' },
    ],
  },
  {
    section: 'Views',
    items: [
      { keys: ['D'], action: 'Day view' },
      { keys: ['W'], action: 'Week view' },
      { keys: ['M'], action: 'Month view' },
      { keys: ['A'], action: 'Agenda view' },
    ],
  },
  {
    section: 'Actions',
    items: [
      { keys: ['N'], action: 'New appointment' },
      { keys: ['Enter'], action: 'Open selected event' },
      { keys: ['Esc'], action: 'Close modal' },
      { keys: ['/'], action: 'Search' },
      { keys: ['Ctrl', 'K'], action: 'Search (works anywhere)' },
      { keys: ['?'], action: 'Show this help' },
    ],
  },
];

/* Inline styles to keep the component self-contained (no external CSS file needed) */
const styles = {
  overlay: {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1100,
  },
  modal: {
    background: '#fff',
    borderRadius: '12px',
    padding: '0',
    width: '480px',
    maxWidth: '90vw',
    maxHeight: '80vh',
    overflow: 'auto',
    boxShadow: '0 20px 25px -5px rgba(0,0,0,0.1), 0 10px 10px -5px rgba(0,0,0,0.04)',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '20px 24px 12px',
    borderBottom: '1px solid #e5e7eb',
  },
  title: {
    margin: 0,
    fontSize: '1.125rem',
    fontWeight: 600,
    color: '#111827',
  },
  closeBtn: {
    background: 'none',
    border: 'none',
    fontSize: '1.5rem',
    lineHeight: 1,
    cursor: 'pointer',
    color: '#6b7280',
    padding: '4px 8px',
    borderRadius: '4px',
  },
  body: {
    padding: '16px 24px',
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '20px',
  },
  section: {
    minWidth: 0,
  },
  sectionTitle: {
    margin: '0 0 8px',
    fontSize: '0.75rem',
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    color: '#6b7280',
  },
  list: {
    margin: 0,
    padding: 0,
  },
  row: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '6px 0',
  },
  keys: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
    flexShrink: 0,
  },
  kbd: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    minWidth: '24px',
    height: '24px',
    padding: '0 6px',
    fontSize: '0.75rem',
    fontFamily: 'inherit',
    fontWeight: 500,
    color: '#374151',
    backgroundColor: '#f3f4f6',
    border: '1px solid #d1d5db',
    borderRadius: '4px',
    boxShadow: '0 1px 0 #d1d5db',
  },
  separator: {
    fontSize: '0.7rem',
    color: '#9ca3af',
  },
  action: {
    margin: 0,
    fontSize: '0.8125rem',
    color: '#374151',
    textAlign: 'right',
    paddingLeft: '12px',
  },
  footer: {
    padding: '12px 24px 16px',
    borderTop: '1px solid #e5e7eb',
    textAlign: 'center',
  },
  hint: {
    fontSize: '0.75rem',
    color: '#9ca3af',
  },
};

/**
 * KeyboardShortcutsHelp - Modal overlay showing all keyboard shortcuts.
 *
 * Rendered conditionally by the parent (Calendar.js). When mounted, the
 * overlay is visible. The component does NOT use an `isOpen` prop — the
 * parent gates rendering via `{showShortcutsHelp && <KeyboardShortcutsHelp />}`.
 *
 * Props:
 *   onClose - Callback to close the modal
 */
function KeyboardShortcutsHelp({ onClose }) {
  const modalRef = useRef(null);

  // Focus trap and escape handling
  useEffect(() => {
    const modal = modalRef.current;
    if (!modal) return;

    const previousFocus = document.activeElement;

    // Focus the close button on open
    const closeBtn = modal.querySelector('[data-autofocus]');
    if (closeBtn) {
      requestAnimationFrame(() => closeBtn.focus());
    }

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        onClose?.();
        return;
      }
      // Trap Tab within the modal
      if (e.key === 'Tab') {
        const focusable = modal.querySelectorAll(
          'button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'
        );
        if (focusable.length === 0) {
          e.preventDefault();
          return;
        }
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

    document.addEventListener('keydown', handleKeyDown, true);
    return () => {
      document.removeEventListener('keydown', handleKeyDown, true);
      if (previousFocus && typeof previousFocus.focus === 'function') {
        requestAnimationFrame(() => previousFocus.focus());
      }
    };
  }, [onClose]);

  return (
    <div
      style={styles.overlay}
      onClick={onClose}
      role="presentation"
    >
      <div
        ref={modalRef}
        style={styles.modal}
        role="dialog"
        aria-modal="true"
        aria-label="Keyboard shortcuts"
        onClick={(e) => e.stopPropagation()}
      >
        <div style={styles.header}>
          <h2 style={styles.title}>Keyboard Shortcuts</h2>
          <button
            data-autofocus
            style={styles.closeBtn}
            onClick={onClose}
            aria-label="Close keyboard shortcuts"
          >
            &times;
          </button>
        </div>

        <div style={styles.body}>
          {SHORTCUT_SECTIONS.map((section) => (
            <div key={section.section} style={styles.section}>
              <h3 style={styles.sectionTitle}>{section.section}</h3>
              <dl style={styles.list}>
                {section.items.map((item, idx) => (
                  <div key={idx} style={styles.row}>
                    <dt style={styles.keys}>
                      {item.keys.map((key, ki) => (
                        <span key={ki}>
                          <kbd style={styles.kbd}>{key}</kbd>
                          {ki < item.keys.length - 1 && (
                            <span style={styles.separator}>+</span>
                          )}
                        </span>
                      ))}
                    </dt>
                    <dd style={styles.action}>{item.action}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
        </div>

        <div style={styles.footer}>
          <span style={styles.hint}>
            Press <kbd style={styles.kbd}>?</kbd> to toggle this dialog
          </span>
        </div>
      </div>
    </div>
  );
}

export default KeyboardShortcutsHelp;
