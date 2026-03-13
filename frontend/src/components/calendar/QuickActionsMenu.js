import React, { useEffect, useRef, useCallback, useState, useMemo } from 'react';
import '../../styles/context-menu.css';

/**
 * MENU_ITEMS - Action definitions for the context menu.
 *
 * Two groups:
 *   "slot"  - Actions when right-clicking an empty time slot
 *   "event" - Actions when right-clicking an existing appointment/event
 *
 * Each item: { id, label, icon (unicode), group (for dividers), shortcut? }
 */
const SLOT_ACTIONS = [
  { id: 'new-appointment', label: 'New Appointment', icon: '\u2795', group: 'create' },
  { id: 'block-time', label: 'Block Time', icon: '\u{1F6AB}', group: 'create' },
  { id: 'add-note', label: 'Add Note', icon: '\u{1F4DD}', group: 'create' },
];

const EVENT_ACTIONS = [
  { id: 'view-details', label: 'View Details', icon: '\u{1F50D}', group: 'view' },
  { id: 'edit', label: 'Edit', icon: '\u270F\uFE0F', group: 'view' },
  { id: 'reschedule', label: 'Reschedule', icon: '\u{1F504}', group: 'modify' },
  { id: 'mark-completed', label: 'Mark as Completed', icon: '\u2705', group: 'modify' },
  { id: 'send-reminder', label: 'Send Reminder', icon: '\u{1F514}', group: 'modify' },
  { id: 'copy-clipboard', label: 'Copy to Clipboard', icon: '\u{1F4CB}', group: 'utility' },
  { id: 'cancel', label: 'Cancel', icon: '\u274C', group: 'danger' },
];

/**
 * QuickActionsMenu - Context menu for the calendar grid.
 *
 * Positioned at cursor, adjusts for viewport overflow.
 * Keyboard navigable: ArrowUp/ArrowDown to move, Enter to select, Escape to close.
 *
 * Props:
 *   isOpen      - Whether the menu is visible
 *   position    - { x, y } screen coordinates
 *   contextData - { type: 'slot' | 'event', date?, hour?, event? }
 *   onAction    - Callback(actionId, contextData) when an item is selected
 *   onClose     - Callback to close the menu
 *   menuRef     - Ref to attach to the menu container (for outside-click detection)
 */
const QuickActionsMenu = React.memo(function QuickActionsMenu({
  isOpen,
  position,
  contextData,
  onAction,
  onClose,
  menuRef: externalMenuRef,
}) {
  const internalRef = useRef(null);
  const containerRef = externalMenuRef || internalRef;
  const itemRefs = useRef([]);
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const [copyFeedback, setCopyFeedback] = useState(false);

  // Determine which actions to show
  const actions = useMemo(() => {
    if (!contextData) return [];
    return contextData.type === 'event' ? EVENT_ACTIONS : SLOT_ACTIONS;
  }, [contextData]);

  // Build groups with dividers
  const itemsWithDividers = useMemo(() => {
    const result = [];
    let lastGroup = null;
    actions.forEach((action, idx) => {
      if (lastGroup && action.group !== lastGroup) {
        result.push({ isDivider: true, key: `divider-${idx}` });
      }
      result.push({ ...action, isDivider: false });
      lastGroup = action.group;
    });
    return result;
  }, [actions]);

  // Only actionable items (not dividers) for keyboard navigation
  const actionableItems = useMemo(
    () => itemsWithDividers.filter(item => !item.isDivider),
    [itemsWithDividers]
  );

  // Reset focus when menu opens/closes or actions change
  useEffect(() => {
    if (isOpen) {
      setFocusedIndex(0);
      setCopyFeedback(false);
    } else {
      setFocusedIndex(-1);
    }
  }, [isOpen]);

  // Focus the active item
  useEffect(() => {
    if (isOpen && focusedIndex >= 0 && itemRefs.current[focusedIndex]) {
      itemRefs.current[focusedIndex].focus();
    }
  }, [isOpen, focusedIndex]);

  // Adjust position to stay within viewport
  const adjustedPosition = useMemo(() => {
    if (!isOpen) return position;

    const menuWidth = 220;
    const menuHeight = actions.length * 38 + 16; // estimate
    const padding = 8;

    let x = position.x;
    let y = position.y;

    // Viewport bounds
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    if (x + menuWidth + padding > vw) {
      x = vw - menuWidth - padding;
    }
    if (x < padding) {
      x = padding;
    }
    if (y + menuHeight + padding > vh) {
      y = vh - menuHeight - padding;
    }
    if (y < padding) {
      y = padding;
    }

    return { x, y };
  }, [isOpen, position, actions.length]);

  const handleItemClick = useCallback((actionId) => {
    if (actionId === 'copy-clipboard' && contextData?.event) {
      // Build summary text
      const event = contextData.event;
      const parts = [event.title || 'Appointment'];
      if (event.start_time) {
        const d = new Date(event.start_time);
        parts.push(d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }));
        parts.push(d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true }));
      }
      if (event.attendee_name) {
        parts.push(`with ${event.attendee_name}`);
      }
      if (event.location) {
        parts.push(`at ${event.location}`);
      }
      const summary = parts.join(' - ');

      navigator.clipboard.writeText(summary).then(() => {
        setCopyFeedback(true);
        setTimeout(() => {
          setCopyFeedback(false);
          onClose();
        }, 800);
      }).catch(() => {
        // Fallback: still fire the action
        onAction(actionId, contextData);
        onClose();
      });
      return;
    }

    onAction(actionId, contextData);
    onClose();
  }, [contextData, onAction, onClose]);

  const handleKeyDown = useCallback((e) => {
    const totalItems = actionableItems.length;
    if (totalItems === 0) return;

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setFocusedIndex(prev => (prev + 1) % totalItems);
        break;
      case 'ArrowUp':
        e.preventDefault();
        setFocusedIndex(prev => (prev - 1 + totalItems) % totalItems);
        break;
      case 'Enter':
      case ' ':
        e.preventDefault();
        if (focusedIndex >= 0 && focusedIndex < totalItems) {
          handleItemClick(actionableItems[focusedIndex].id);
        }
        break;
      case 'Home':
        e.preventDefault();
        setFocusedIndex(0);
        break;
      case 'End':
        e.preventDefault();
        setFocusedIndex(totalItems - 1);
        break;
      case 'Escape':
        e.preventDefault();
        onClose();
        break;
      default:
        break;
    }
  }, [actionableItems, focusedIndex, handleItemClick, onClose]);

  if (!isOpen || !contextData) return null;

  // Build a label for accessibility
  const menuLabel = contextData.type === 'event'
    ? `Actions for ${contextData.event?.title || 'appointment'}`
    : 'Quick actions for time slot';

  let actionableIndex = -1;

  return (
    <div
      ref={containerRef}
      className="context-menu"
      role="menu"
      aria-label={menuLabel}
      style={{
        left: `${adjustedPosition.x}px`,
        top: `${adjustedPosition.y}px`,
      }}
      onKeyDown={handleKeyDown}
    >
      {/* Header showing context */}
      {contextData.type === 'slot' && contextData.date && (
        <div className="context-menu-header" aria-hidden="true">
          {contextData.date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}
          {contextData.hour != null && (
            <span className="context-menu-time">
              {' '}{contextData.hour > 12 ? contextData.hour - 12 : contextData.hour}:00 {contextData.hour >= 12 ? 'PM' : 'AM'}
            </span>
          )}
        </div>
      )}
      {contextData.type === 'event' && contextData.event && (
        <div className="context-menu-header" aria-hidden="true">
          {contextData.event.title || 'Appointment'}
        </div>
      )}

      <div className="context-menu-items">
        {itemsWithDividers.map((item) => {
          if (item.isDivider) {
            return <div key={item.key} className="context-menu-divider" role="separator" />;
          }

          actionableIndex++;
          const currentIndex = actionableIndex;
          const isFocused = focusedIndex === currentIndex;
          const isDanger = item.group === 'danger';

          return (
            <div
              key={item.id}
              ref={(el) => { itemRefs.current[currentIndex] = el; }}
              className={`context-menu-item${isFocused ? ' focused' : ''}${isDanger ? ' danger' : ''}`}
              role="menuitem"
              tabIndex={isFocused ? 0 : -1}
              onClick={() => handleItemClick(item.id)}
              aria-label={item.label}
            >
              <span className="context-menu-icon" aria-hidden="true">{item.icon}</span>
              <span className="context-menu-label">
                {item.id === 'copy-clipboard' && copyFeedback ? 'Copied!' : item.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
});

export default QuickActionsMenu;
