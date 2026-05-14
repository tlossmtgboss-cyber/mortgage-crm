import React from 'react';
import '../SmartScheduler.css';
import RecordingPlayer from '../VideoMeetings/RecordingPlayer';
import { useVideoMeetingsState } from './useVideoMeetingsState';
import MeetingTypesView from './MeetingTypesView';
import BookingLinksView from './BookingLinksView';
import RemindersView from './RemindersView';
import SettingsView from './SettingsView';
import LandingPageView from './LandingPageView';
import TutorialView from './TutorialView';
import { CreateMeetingModal, MeetingDetailModal, MeetingTypeModal, NewLinkModal } from './MeetingModals';

const VideoMeetings = ({ onClose, leadId, loanId, contactId }) => {
  const state = useVideoMeetingsState({ leadId, loanId });

  const {
    view, setView,
    loading, error, setError,
    meetingTypes, stats,
    bookingLinks, config, editableConfig, setEditableConfig,
    meetingForm, setMeetingForm,
    typeForm, setTypeForm,
    linkForm, setLinkForm,
    showCreateModal, setShowCreateModal,
    showMeetingDetail, setShowMeetingDetail,
    showRecordingPlayer, setShowRecordingPlayer,
    selectedRecording, setSelectedRecording,
    showNewTypeModal, setShowNewTypeModal,
    showNewLinkModal, setShowNewLinkModal,
    editingType, setEditingType,
    selectedMeeting,
    settingsTab, setSettingsTab,
    savingSettings,
    landingPageSettings, setLandingPageSettings,
    savingLandingPage, previewMode, setPreviewMode,
    reminderSettings, setReminderSettings,
    savingReminders, setSavingReminders,
    createScheduledMeeting,
    startMeeting, endMeeting, cancelMeeting,
    viewRecording,
    seedDefaultTemplates,
    handleSaveMeetingType, handleDeleteMeetingType,
    handleEditType, resetTypeForm,
    handleCreateBookingLink,
    handleSaveSettings,
    updateWorkingHours, updateConfigField,
    handleSaveLandingPage,
    DEFAULT_LANDING_PAGE
  } = state;

  // Render Stats Cards
  const renderStats = () => {
    if (!stats) return null;
    return (
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value">{stats.total_meetings}</div>
          <div className="stat-label">Total Meetings</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.meetings_this_week}</div>
          <div className="stat-label">This Week</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.upcoming_meetings}</div>
          <div className="stat-label">Upcoming</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.total_meeting_hours}h</div>
          <div className="stat-label">Total Hours</div>
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div className="video-meetings-container">
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading meetings...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="smart-scheduler">
      {/* Header */}
      <div className="scheduler-header">
        <h2>Video Meetings</h2>
        <div className="scheduler-tabs">
          <button className={`tab ${view === 'types' ? 'active' : ''}`} onClick={() => setView('types')}>Meeting Types</button>
          <button className={`tab ${view === 'booking-links' ? 'active' : ''}`} onClick={() => setView('booking-links')}>Booking Links</button>
          <button className={`tab ${view === 'reminders' ? 'active' : ''}`} onClick={() => setView('reminders')}>Reminders</button>
          <button className={`tab ${view === 'settings' ? 'active' : ''}`} onClick={() => setView('settings')}>Settings</button>
          <button className={`tab ${view === 'landing-page' ? 'active' : ''}`} onClick={() => setView('landing-page')}>Landing Page</button>
          <button className={`tab tutorial-tab ${view === 'tutorial' ? 'active' : ''}`} onClick={() => setView('tutorial')}>Tutorial</button>
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <button onClick={() => setError(null)}>x</button>
        </div>
      )}

      {/* Content */}
      <div className="scheduler-content">
        {view === 'types' && (
          <MeetingTypesView
            meetingTypes={meetingTypes}
            seedDefaultTemplates={seedDefaultTemplates}
            setEditingType={setEditingType}
            resetTypeForm={resetTypeForm}
            setShowNewTypeModal={setShowNewTypeModal}
            handleEditType={handleEditType}
          />
        )}
        {view === 'booking-links' && (
          <BookingLinksView
            bookingLinks={bookingLinks}
            setShowNewLinkModal={setShowNewLinkModal}
          />
        )}
        {view === 'reminders' && (
          <RemindersView
            reminderSettings={reminderSettings}
            setReminderSettings={setReminderSettings}
            savingReminders={savingReminders}
            setSavingReminders={setSavingReminders}
          />
        )}
        {view === 'settings' && (
          <SettingsView
            editableConfig={editableConfig}
            setEditableConfig={setEditableConfig}
            config={config}
            settingsTab={settingsTab}
            setSettingsTab={setSettingsTab}
            savingSettings={savingSettings}
            handleSaveSettings={handleSaveSettings}
            updateWorkingHours={updateWorkingHours}
            updateConfigField={updateConfigField}
            seedDefaultTemplates={seedDefaultTemplates}
          />
        )}
        {view === 'landing-page' && (
          <LandingPageView
            landingPageSettings={landingPageSettings}
            setLandingPageSettings={setLandingPageSettings}
            previewMode={previewMode}
            setPreviewMode={setPreviewMode}
            savingLandingPage={savingLandingPage}
            handleSaveLandingPage={handleSaveLandingPage}
            DEFAULT_LANDING_PAGE={DEFAULT_LANDING_PAGE}
          />
        )}
        {view === 'tutorial' && <TutorialView setView={setView} />}
      </div>

      {/* Modals */}
      <CreateMeetingModal
        showCreateModal={showCreateModal}
        setShowCreateModal={setShowCreateModal}
        meetingForm={meetingForm}
        setMeetingForm={setMeetingForm}
        createScheduledMeeting={createScheduledMeeting}
      />
      <MeetingDetailModal
        showMeetingDetail={showMeetingDetail}
        setShowMeetingDetail={setShowMeetingDetail}
        selectedMeeting={selectedMeeting}
        startMeeting={startMeeting}
        endMeeting={endMeeting}
        cancelMeeting={cancelMeeting}
        viewRecording={viewRecording}
      />
      <MeetingTypeModal
        showNewTypeModal={showNewTypeModal}
        setShowNewTypeModal={setShowNewTypeModal}
        editingType={editingType}
        setEditingType={setEditingType}
        typeForm={typeForm}
        setTypeForm={setTypeForm}
        handleSaveMeetingType={handleSaveMeetingType}
        handleDeleteMeetingType={handleDeleteMeetingType}
      />
      <NewLinkModal
        showNewLinkModal={showNewLinkModal}
        setShowNewLinkModal={setShowNewLinkModal}
        linkForm={linkForm}
        setLinkForm={setLinkForm}
        meetingTypes={meetingTypes}
        handleCreateBookingLink={handleCreateBookingLink}
      />

      {/* Recording Player */}
      {showRecordingPlayer && selectedRecording && (
        <RecordingPlayer
          recording={selectedRecording}
          onClose={() => {
            setShowRecordingPlayer(false);
            setSelectedRecording(null);
          }}
        />
      )}
    </div>
  );
};

export default VideoMeetings;
