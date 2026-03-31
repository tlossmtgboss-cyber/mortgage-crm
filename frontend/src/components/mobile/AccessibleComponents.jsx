/**
 * Accessible wrapper components for Perennia AI mobile app.
 *
 * Each component enforces WCAG 2.1 AA compliance with proper ARIA
 * attributes, keyboard support, and focus management.
 *
 * These are building blocks -- use them inside feature components
 * to ensure consistent screen reader behavior across the app.
 */

import React, { useRef, useEffect, useCallback, useState } from 'react';
import useFocusTrap from '../../hooks/useFocusTrap';
import { generateId, announceToScreenReader } from '../../utils/accessibility';

// ---------------------------------------------------------------------------
// ScreenReaderOnly
// ---------------------------------------------------------------------------

/**
 * Visually hidden content that remains accessible to screen readers.
 *
 * Uses the standard .sr-only technique recommended by WebAIM. The element
 * is removed from visual layout but stays in the accessibility tree.
 *
 * @param {{ children: React.ReactNode, as?: string, id?: string }} props
 */
export function ScreenReaderOnly({ children, as: Tag = 'span', id, ...rest }) {
  const style = {
    position: 'absolute',
    width: '1px',
    height: '1px',
    padding: 0,
    margin: '-1px',
    overflow: 'hidden',
    clip: 'rect(0, 0, 0, 0)',
    whiteSpace: 'nowrap',
    border: 0,
  };

  return (
    <Tag style={style} id={id} {...rest}>
      {children}
    </Tag>
  );
}

// ---------------------------------------------------------------------------
// AccessibleButton
// ---------------------------------------------------------------------------

/**
 * Button with enforced accessibility attributes.
 *
 * - Renders a real <button> element (never a div with role="button")
 * - Announces disabled state changes to screen readers
 * - Supports loading state with aria-busy
 * - Keyboard: Enter and Space activate (native button behavior)
 *
 * @param {Object} props
 * @param {React.ReactNode} props.children - Button content
 * @param {string} [props.ariaLabel] - Accessible label (required when children is an icon)
 * @param {boolean} [props.disabled=false]
 * @param {boolean} [props.loading=false]
 * @param {string} [props.loadingText='Loading'] - Announced when loading
 * @param {string} [props.describedBy] - ID of element describing the button
 * @param {function} [props.onClick]
 * @param {string} [props.className]
 */
export function AccessibleButton({
  children,
  ariaLabel,
  disabled = false,
  loading = false,
  loadingText = 'Loading',
  describedBy,
  onClick,
  className = '',
  type = 'button',
  ...rest
}) {
  const prevDisabled = useRef(disabled);
  const prevLoading = useRef(loading);

  // Announce state transitions
  useEffect(() => {
    if (loading && !prevLoading.current) {
      announceToScreenReader(loadingText, 'polite');
    }
    prevLoading.current = loading;
  }, [loading, loadingText]);

  useEffect(() => {
    if (disabled && !prevDisabled.current && ariaLabel) {
      announceToScreenReader(`${ariaLabel}, disabled`, 'polite');
    }
    prevDisabled.current = disabled;
  }, [disabled, ariaLabel]);

  return (
    <button
      type={type}
      className={className}
      aria-label={ariaLabel}
      aria-disabled={disabled || loading}
      aria-busy={loading}
      aria-describedby={describedBy}
      disabled={disabled || loading}
      onClick={onClick}
      {...rest}
    >
      {loading ? (
        <>
          <ScreenReaderOnly>{loadingText}</ScreenReaderOnly>
          {children}
        </>
      ) : (
        children
      )}
    </button>
  );
}

// ---------------------------------------------------------------------------
// AccessibleCard
// ---------------------------------------------------------------------------

/**
 * Touchable card component with proper semantics for screen readers.
 *
 * - role="button" when clickable, role="region" when static
 * - aria-label summarizes the card content
 * - Keyboard: Enter and Space activate (when clickable)
 * - Supports aria-describedby for supplementary details
 *
 * @param {Object} props
 * @param {React.ReactNode} props.children
 * @param {string} props.ariaLabel - Summary of card content for screen readers
 * @param {function} [props.onClick] - If provided, card becomes interactive
 * @param {string} [props.describedBy] - ID of element with additional details
 * @param {string} [props.className]
 * @param {string} [props.headingLevel] - If set, renders an sr-only heading (e.g., 'h3')
 */
export function AccessibleCard({
  children,
  ariaLabel,
  onClick,
  describedBy,
  className = '',
  headingLevel,
  ...rest
}) {
  const isInteractive = typeof onClick === 'function';
  const [headingId] = useState(() => headingLevel ? generateId('card-heading') : undefined);

  const handleKeyDown = useCallback(
    (e) => {
      if (!isInteractive) return;
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onClick(e);
      }
    },
    [isInteractive, onClick]
  );

  return (
    <div
      role={isInteractive ? 'button' : 'region'}
      aria-label={ariaLabel}
      aria-labelledby={headingLevel ? headingId : undefined}
      aria-describedby={describedBy}
      tabIndex={isInteractive ? 0 : undefined}
      onClick={isInteractive ? onClick : undefined}
      onKeyDown={isInteractive ? handleKeyDown : undefined}
      className={className}
      style={isInteractive ? { cursor: 'pointer' } : undefined}
      {...rest}
    >
      {headingLevel && (
        <ScreenReaderOnly as={headingLevel} id={headingId}>
          {ariaLabel}
        </ScreenReaderOnly>
      )}
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// AccessibleBadge
// ---------------------------------------------------------------------------

/**
 * Badge / counter with a screen-reader-friendly label.
 *
 * Visual output: "3"
 * Screen reader: "3 unread notifications"
 *
 * @param {Object} props
 * @param {number|string} props.count - The number to display
 * @param {string} props.label - Full label for screen readers (e.g., "unread notifications")
 * @param {string} [props.className]
 * @param {boolean} [props.announceChanges=false] - Announce via aria-live when count changes
 */
export function AccessibleBadge({
  count,
  label,
  className = '',
  announceChanges = false,
  ...rest
}) {
  const prevCount = useRef(count);

  useEffect(() => {
    if (announceChanges && prevCount.current !== count) {
      announceToScreenReader(`${count} ${label}`, 'polite');
    }
    prevCount.current = count;
  }, [count, label, announceChanges]);

  const fullLabel = `${count} ${label}`;

  return (
    <span
      className={className}
      role="status"
      aria-label={fullLabel}
      {...rest}
    >
      <span aria-hidden="true">{count}</span>
      <ScreenReaderOnly>{fullLabel}</ScreenReaderOnly>
    </span>
  );
}

// ---------------------------------------------------------------------------
// AccessibleTabBar
// ---------------------------------------------------------------------------

/**
 * Tab bar with proper ARIA tablist/tab semantics and keyboard navigation.
 *
 * - role="tablist" on container
 * - role="tab" + aria-selected on each tab
 * - Arrow key navigation (left/right) with wrap-around
 * - Home/End key support
 * - Only the active tab is in the tab order (roving tabindex)
 *
 * @param {Object} props
 * @param {{ key: string, label: string, icon?: React.ReactNode }[]} props.tabs
 * @param {string} props.activeKey - Currently selected tab key
 * @param {function} props.onSelect - Called with tab key when selected
 * @param {string} [props.ariaLabel='Navigation tabs'] - Label for the tablist
 * @param {string} [props.className]
 */
export function AccessibleTabBar({
  tabs,
  activeKey,
  onSelect,
  ariaLabel = 'Navigation tabs',
  className = '',
  ...rest
}) {
  const tabRefs = useRef({});

  const handleKeyDown = useCallback(
    (e) => {
      const currentIndex = tabs.findIndex((t) => t.key === activeKey);
      if (currentIndex === -1) return;

      let nextIndex = -1;

      switch (e.key) {
        case 'ArrowRight':
        case 'ArrowDown':
          e.preventDefault();
          nextIndex = (currentIndex + 1) % tabs.length;
          break;
        case 'ArrowLeft':
        case 'ArrowUp':
          e.preventDefault();
          nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
          break;
        case 'Home':
          e.preventDefault();
          nextIndex = 0;
          break;
        case 'End':
          e.preventDefault();
          nextIndex = tabs.length - 1;
          break;
        default:
          return;
      }

      if (nextIndex >= 0) {
        const nextTab = tabs[nextIndex];
        onSelect(nextTab.key);
        // Move focus to the newly selected tab
        const tabEl = tabRefs.current[nextTab.key];
        if (tabEl) tabEl.focus();
      }
    },
    [tabs, activeKey, onSelect]
  );

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className={className}
      onKeyDown={handleKeyDown}
      {...rest}
    >
      {tabs.map((tab) => {
        const isActive = tab.key === activeKey;
        const tabId = `tab-${tab.key}`;
        const panelId = `tabpanel-${tab.key}`;

        return (
          <button
            key={tab.key}
            ref={(el) => { tabRefs.current[tab.key] = el; }}
            id={tabId}
            role="tab"
            type="button"
            aria-selected={isActive}
            aria-controls={panelId}
            tabIndex={isActive ? 0 : -1}
            onClick={() => onSelect(tab.key)}
          >
            {tab.icon && <span aria-hidden="true">{tab.icon}</span>}
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

/**
 * Tab panel companion for AccessibleTabBar.
 *
 * @param {Object} props
 * @param {string} props.tabKey - Matching tab key
 * @param {boolean} props.active - Whether this panel is visible
 * @param {React.ReactNode} props.children
 * @param {string} [props.className]
 */
export function AccessibleTabPanel({
  tabKey,
  active,
  children,
  className = '',
  ...rest
}) {
  return (
    <div
      id={`tabpanel-${tabKey}`}
      role="tabpanel"
      aria-labelledby={`tab-${tabKey}`}
      hidden={!active}
      tabIndex={0}
      className={className}
      {...rest}
    >
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// AccessibleModal
// ---------------------------------------------------------------------------

/**
 * Modal dialog with full accessibility support.
 *
 * - role="dialog" with aria-modal="true"
 * - Focus trap via useFocusTrap hook (already exists in codebase)
 * - Escape key closes the modal
 * - Focus returns to trigger element on close
 * - Prevents body scroll while open
 * - Backdrop click to close (optional)
 *
 * @param {Object} props
 * @param {boolean} props.isOpen - Whether the modal is visible
 * @param {function} props.onClose - Called when the modal should close
 * @param {string} props.title - Accessible title (rendered as heading and used for aria-labelledby)
 * @param {React.ReactNode} props.children
 * @param {boolean} [props.closeOnBackdrop=true] - Close when clicking the backdrop
 * @param {string} [props.className] - Class for the dialog container
 * @param {string} [props.size='medium'] - Size hint (not enforced, for styling)
 * @param {React.ReactNode} [props.footer] - Optional footer content
 */
export function AccessibleModal({
  isOpen,
  onClose,
  title,
  children,
  closeOnBackdrop = true,
  className = '',
  size = 'medium',
  footer,
  ...rest
}) {
  const containerRef = useRef(null);
  const [titleId] = useState(() => generateId('modal-title'));
  const [descId] = useState(() => generateId('modal-desc'));

  // Focus trap: delegates to the existing useFocusTrap hook
  useFocusTrap(containerRef, {
    active: isOpen,
    onEscape: onClose,
    autoFocus: true,
    restoreFocus: true,
  });

  // Prevent body scroll when modal is open
  useEffect(() => {
    if (!isOpen) return;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [isOpen]);

  // Announce modal opening
  useEffect(() => {
    if (isOpen && title) {
      announceToScreenReader(`Dialog opened: ${title}`);
    }
  }, [isOpen, title]);

  const handleBackdropClick = useCallback(
    (e) => {
      // Only close if click was on the backdrop itself, not the dialog content
      if (closeOnBackdrop && e.target === e.currentTarget) {
        onClose();
      }
    },
    [closeOnBackdrop, onClose]
  );

  if (!isOpen) return null;

  return (
    <div
      className="accessible-modal-backdrop"
      onClick={handleBackdropClick}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'rgba(0, 0, 0, 0.5)',
      }}
    >
      <div
        ref={containerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        className={`accessible-modal ${className}`}
        data-size={size}
        style={{
          background: '#fff',
          borderRadius: '12px',
          maxHeight: '90vh',
          maxWidth: size === 'small' ? '400px' : size === 'large' ? '720px' : '560px',
          width: '90%',
          overflow: 'auto',
          WebkitOverflowScrolling: 'touch',
        }}
        {...rest}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '16px 20px',
            borderBottom: '1px solid #e5e7eb',
          }}
        >
          <h2
            id={titleId}
            style={{
              margin: 0,
              fontSize: '1.125rem',
              fontWeight: 600,
            }}
          >
            {title}
          </h2>
          <button
            type="button"
            aria-label="Close dialog"
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              padding: '4px',
              cursor: 'pointer',
              fontSize: '1.5rem',
              lineHeight: 1,
              color: '#6b7280',
            }}
          >
            <span aria-hidden="true">&times;</span>
          </button>
        </div>

        {/* Body */}
        <div id={descId} style={{ padding: '20px' }}>
          {children}
        </div>

        {/* Footer (optional) */}
        {footer && (
          <div
            style={{
              display: 'flex',
              justifyContent: 'flex-end',
              gap: '8px',
              padding: '12px 20px',
              borderTop: '1px solid #e5e7eb',
            }}
          >
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Default export (all components)
// ---------------------------------------------------------------------------

export default {
  ScreenReaderOnly,
  AccessibleButton,
  AccessibleCard,
  AccessibleBadge,
  AccessibleTabBar,
  AccessibleTabPanel,
  AccessibleModal,
};
