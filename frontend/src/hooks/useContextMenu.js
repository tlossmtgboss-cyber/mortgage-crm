import { useState, useCallback, useEffect, useRef } from 'react';

/**
 * useContextMenu - Hook for managing a context menu on the calendar.
 *
 * Returns:
 *   isOpen      - Whether the context menu is currently visible
 *   position    - { x, y } screen coordinates for positioning
 *   contextData - Data about what was right-clicked:
 *                   { type: 'slot' | 'event', date, hour, event }
 *   openMenu    - Function to call on contextmenu event
 *   closeMenu   - Function to programmatically close the menu
 *
 * Automatically closes on:
 *   - Click outside the menu
 *   - Scroll anywhere on the page
 *   - Escape key
 *   - Window resize
 */
const useContextMenu = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [contextData, setContextData] = useState(null);
  const menuRef = useRef(null);

  const openMenu = useCallback((e, data) => {
    // Prevent browser default context menu
    e.preventDefault();
    e.stopPropagation();

    setPosition({ x: e.clientX, y: e.clientY });
    setContextData(data);
    setIsOpen(true);
  }, []);

  const closeMenu = useCallback(() => {
    setIsOpen(false);
    setContextData(null);
  }, []);

  // Close on outside click
  useEffect(() => {
    if (!isOpen) return;

    const handleClick = (e) => {
      // If a menuRef is attached, check if click is inside
      if (menuRef.current && menuRef.current.contains(e.target)) {
        return;
      }
      closeMenu();
    };

    const handleScroll = () => {
      closeMenu();
    };

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        closeMenu();
      }
    };

    const handleResize = () => {
      closeMenu();
    };

    // Use a short delay so the opening click doesn't immediately close
    const timer = setTimeout(() => {
      document.addEventListener('click', handleClick, true);
      document.addEventListener('contextmenu', handleClick, true);
      window.addEventListener('scroll', handleScroll, true);
      document.addEventListener('keydown', handleKeyDown);
      window.addEventListener('resize', handleResize);
    }, 0);

    return () => {
      clearTimeout(timer);
      document.removeEventListener('click', handleClick, true);
      document.removeEventListener('contextmenu', handleClick, true);
      window.removeEventListener('scroll', handleScroll, true);
      document.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('resize', handleResize);
    };
  }, [isOpen, closeMenu]);

  return {
    isOpen,
    position,
    contextData,
    openMenu,
    closeMenu,
    menuRef,
  };
};

export default useContextMenu;
