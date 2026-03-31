/**
 * LongPressMenu — A context menu that appears at the touch point after a
 * long-press gesture on mobile. Provides quick actions on list items without
 * requiring navigation.
 *
 * Props:
 *   items    — Array of { label, icon, action, destructive? }
 *   position — { x, y } in viewport coordinates (the touch point)
 *   onClose  — Called when the menu should dismiss (backdrop tap or item select)
 *
 * Usage:
 *   <LongPressMenu
 *     items={[
 *       { label: 'Call',   icon: 'phone',   action: () => {} },
 *       { label: 'Text',   icon: 'message', action: () => {} },
 *       { label: 'Delete', icon: 'trash',   action: () => {}, destructive: true },
 *     ]}
 *     position={{ x: 120, y: 300 }}
 *     onClose={() => setMenuOpen(false)}
 *   />
 */
import React, { useEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { haptics } from '../../services/nativeServices';
import './LongPressMenu.css';

// ---------------------------------------------------------------------------
// Built-in SVG icons keyed by name. Keeps the component self-contained so
// consumers can just pass a string like "phone" instead of importing icons.
// ---------------------------------------------------------------------------
const ICONS = {
  phone: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z" />
    </svg>
  ),
  message: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
    </svg>
  ),
  mail: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
      <polyline points="22,6 12,13 2,6" />
    </svg>
  ),
  edit: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
      <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
    </svg>
  ),
  trash: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
      <line x1="10" y1="11" x2="10" y2="17" />
      <line x1="14" y1="11" x2="14" y2="17" />
    </svg>
  ),
  copy: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
      <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
    </svg>
  ),
  share: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="18" cy="5" r="3" />
      <circle cx="6" cy="12" r="3" />
      <circle cx="18" cy="19" r="3" />
      <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
      <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
    </svg>
  ),
  star: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
    </svg>
  ),
  calendar: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
      <line x1="16" y1="2" x2="16" y2="6" />
      <line x1="8" y1="2" x2="8" y2="6" />
      <line x1="3" y1="10" x2="21" y2="10" />
    </svg>
  ),
  notes: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
      <polyline points="10 9 9 9 8 9" />
    </svg>
  ),
};

// Viewport edge padding to prevent menu from clipping offscreen
const VIEWPORT_PADDING = 12;

/**
 * Compute the menu's top/left so it stays fully inside the viewport,
 * and set the CSS custom properties for transform-origin so the scale
 * animation appears to bloom from the touch point.
 */
function computeMenuPosition(touchX, touchY, menuEl) {
  const rect = menuEl.getBoundingClientRect();
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const mw = rect.width;
  const mh = rect.height;

  // Start with the menu centered horizontally on the touch point, top-aligned
  let left = touchX - mw / 2;
  let top = touchY + 8; // small offset below touch

  // Clamp to viewport
  if (left < VIEWPORT_PADDING) left = VIEWPORT_PADDING;
  if (left + mw > vw - VIEWPORT_PADDING) left = vw - VIEWPORT_PADDING - mw;
  if (top + mh > vh - VIEWPORT_PADDING) {
    // Flip above the touch point
    top = touchY - mh - 8;
  }
  if (top < VIEWPORT_PADDING) top = VIEWPORT_PADDING;

  // Transform-origin expressed as percentage of the menu element so the
  // scale animation fans out from where the finger was.
  const originX = ((touchX - left) / mw) * 100;
  const originY = ((touchY - top) / mh) * 100;

  return { left, top, originX, originY };
}

export default function LongPressMenu({ items, position, onClose }) {
  const menuRef = useRef(null);

  // Position the menu once it mounts and we know its dimensions
  useEffect(() => {
    const el = menuRef.current;
    if (!el || !position) return;

    const { left, top, originX, originY } = computeMenuPosition(
      position.x,
      position.y,
      el,
    );

    el.style.left = `${left}px`;
    el.style.top = `${top}px`;
    el.style.setProperty('--lpm-origin-x', `${originX}%`);
    el.style.setProperty('--lpm-origin-y', `${originY}%`);
  }, [position]);

  // Close on Escape key (useful for testing on desktop)
  useEffect(() => {
    const handleKey = (e) => {
      if (e.key === 'Escape') onClose?.();
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onClose]);

  const handleItemClick = useCallback(
    (item) => {
      haptics.selection();
      onClose?.();
      // Run the action after the menu starts closing so the UI feels snappy
      requestAnimationFrame(() => {
        item.action?.();
      });
    },
    [onClose],
  );

  const handleBackdropClick = useCallback(() => {
    onClose?.();
  }, [onClose]);

  if (!items || items.length === 0 || !position) return null;

  const menu = (
    <>
      {/* Backdrop */}
      <div
        className="lpm-backdrop"
        onClick={handleBackdropClick}
        onTouchEnd={handleBackdropClick}
      />

      {/* Menu */}
      <div
        ref={menuRef}
        className="lpm-menu"
        role="menu"
        aria-label="Context menu"
      >
        {items.map((item, idx) => (
          <button
            key={item.label || idx}
            className={`lpm-item${item.destructive ? ' lpm-item--destructive' : ''}`}
            role="menuitem"
            onClick={() => handleItemClick(item)}
          >
            {item.icon && (
              <span className="lpm-icon">
                {typeof item.icon === 'string' ? ICONS[item.icon] || null : item.icon}
              </span>
            )}
            <span className="lpm-label">{item.label}</span>
          </button>
        ))}
      </div>
    </>
  );

  // Render into a portal so stacking context is never an issue
  return createPortal(menu, document.body);
}
