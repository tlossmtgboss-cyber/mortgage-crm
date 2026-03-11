import { useEffect } from 'react';

/**
 * Custom hook that manages ESC key dismissal and focus trapping
 * for create/edit appointment modals.
 */
export function useModalFocusTrap({
  showCreateModal,
  showEditModal,
  createModalRef,
  editModalRef,
  onCloseCreate,
  onCloseEdit,
}) {
  useEffect(() => {
    const activeModal = showCreateModal || showEditModal;
    if (!activeModal) return;

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        if (showEditModal) onCloseEdit();
        else if (showCreateModal) onCloseCreate();
      }
      if (e.key === 'Tab') {
        const modalRef = showEditModal ? editModalRef : createModalRef;
        const modal = modalRef.current;
        if (!modal) return;
        const focusable = modal.querySelectorAll('button, input, select, textarea, [tabindex]:not([tabindex="-1"])');
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    const modalRef = showEditModal ? editModalRef : createModalRef;
    const timer = setTimeout(() => {
      const modal = modalRef.current;
      if (modal) {
        const first = modal.querySelector('button, input, select, textarea');
        if (first) first.focus();
      }
    }, 50);

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      clearTimeout(timer);
    };
  }, [showCreateModal, showEditModal, createModalRef, editModalRef, onCloseCreate, onCloseEdit]);
}
