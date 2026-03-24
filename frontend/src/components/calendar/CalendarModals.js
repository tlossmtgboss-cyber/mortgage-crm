import React, { lazy, Suspense } from 'react';
import AddEventModal from './AddEventModal';
import EditAppointmentModal from './EditAppointmentModal';
import ConfirmDialog from './ConfirmDialog';

// Lazy load heavy modal/overlay components that are conditionally rendered
const CalendarSearch = lazy(() => import('./CalendarSearch'));
const KeyboardShortcutsHelp = lazy(() => import('./KeyboardShortcutsHelp'));
const CalendarTour = lazy(() => import('./setup/CalendarTour'));

/**
 * CalendarModals -- Renders all conditional modals and overlays for the Calendar page.
 *
 * Centralizes the rendering logic for: AddEventModal, EditAppointmentModal,
 * ConfirmDialog, CalendarSearch, KeyboardShortcutsHelp, and CalendarTour.
 *
 * Used in: Calendar (main page)
 *
 * @param {Object} props
 * @param {boolean} props.showAddModal - Whether the add event/appointment modal is visible
 * @param {Date|null} props.selectedDate - Pre-selected date for the add modal
 * @param {number|null} props.selectedTime - Pre-selected hour for the add modal
 * @param {Function} props.onCloseAddModal - Close the add modal
 * @param {Function} props.onAddEvent - Handler for creating an event
 * @param {Function} props.onAddAppointment - Handler for creating an appointment
 * @param {Array} props.teamMembers - Team members for the add modal's assign dropdown
 * @param {boolean} props.isBooking - Whether a booking operation is in progress
 * @param {boolean} props.showEditModal - Whether the edit modal is visible
 * @param {Object|null} props.editingAppointment - The appointment being edited
 * @param {Function} props.onEditFieldChange - Handler for changing a field on the editing appointment
 * @param {Function} props.onSaveAppointment - Handler for saving the edit
 * @param {Function} props.onCancelAppointment - Handler for cancelling the appointment from the edit modal
 * @param {Function} props.onCloseEditModal - Close the edit modal
 * @param {boolean} props.saving - Whether a save operation is in progress
 * @param {Object|null} props.confirmAction - Confirm dialog state ({ message, onConfirm })
 * @param {Function} props.onDismissConfirm - Dismiss the confirm dialog
 * @param {boolean} props.showSearch - Whether the search overlay is visible
 * @param {Function} props.onCloseSearch - Close the search overlay
 * @param {Function} props.onSearchSelectAppointment - Handler for selecting a search result
 * @param {boolean} props.showShortcutsHelp - Whether the shortcuts help overlay is visible
 * @param {Function} props.onCloseShortcutsHelp - Close the shortcuts help overlay
 * @param {Object|null} props.tour - Tour state object (or null if not available)
 * @param {boolean} props.hasTour - Whether the tour feature is enabled
 * @returns {React.ReactElement}
 */
const CalendarModals = React.memo(function CalendarModals({
  showAddModal,
  selectedDate,
  selectedTime,
  onCloseAddModal,
  onAddEvent,
  onAddAppointment,
  teamMembers,
  isBooking,
  showEditModal,
  editingAppointment,
  onEditFieldChange,
  onSaveAppointment,
  onCancelAppointment,
  onCloseEditModal,
  saving,
  confirmAction,
  onDismissConfirm,
  showSearch,
  onCloseSearch,
  onSearchSelectAppointment,
  showShortcutsHelp,
  onCloseShortcutsHelp,
  tour,
  hasTour,
}) {
  return (
    <>
      {showAddModal && (
        <AddEventModal
          selectedDate={selectedDate}
          selectedTime={selectedTime}
          onClose={onCloseAddModal}
          onAdd={onAddEvent}
          onAddAppointment={onAddAppointment}
          teamMembers={teamMembers}
          saving={isBooking}
        />
      )}

      {showEditModal && editingAppointment && (
        <EditAppointmentModal
          appointment={editingAppointment}
          onFieldChange={onEditFieldChange}
          onSave={onSaveAppointment}
          onCancel={onCancelAppointment}
          onClose={onCloseEditModal}
          saving={saving}
        />
      )}

      {confirmAction && (
        <ConfirmDialog
          message={confirmAction.message}
          onConfirm={confirmAction.onConfirm}
          onCancel={onDismissConfirm}
        />
      )}

      {showSearch && (
        <Suspense fallback={null}>
          <CalendarSearch
            visible={showSearch}
            onClose={onCloseSearch}
            onSelectAppointment={onSearchSelectAppointment}
          />
        </Suspense>
      )}

      {showShortcutsHelp && (
        <Suspense fallback={null}>
          <KeyboardShortcutsHelp onClose={onCloseShortcutsHelp} />
        </Suspense>
      )}

      {hasTour && tour && tour.isActive && (
        <Suspense fallback={null}>
          <CalendarTour
            isActive={tour.isActive}
            currentStep={tour.currentStep}
            steps={tour.steps}
            totalSteps={tour.totalSteps}
            dontShowAgain={tour.dontShowAgain}
            onNext={tour.next}
            onBack={tour.back}
            onSkip={tour.skip}
            onComplete={tour.complete}
            onToggleDontShowAgain={tour.toggleDontShowAgain}
          />
        </Suspense>
      )}
    </>
  );
});

export default CalendarModals;
