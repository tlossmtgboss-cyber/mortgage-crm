/**
 * Perennia AI - Calendar Settings (Container)
 *
 * Thin container that manages cross-cutting state, navigation, data loading,
 * and save dispatch. Each tab's UI is delegated to a section component in
 * ./calendar-settings/.
 *
 * Infrastructure (defaults, reducer, loader, saver) is extracted to
 * components/calendar/settings/ for testability.
 */

import { useReducer, useEffect, useCallback, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { API_BASE_URL } from '../services/api';
import { toast } from '../utils/toast';
import '../styles/calendar-settings.css';

// Infrastructure
import {
  NAV_SECTIONS,
  ALL_NAV_ITEMS,
  SAVEABLE_SECTIONS,
  settingsReducer,
  initialState,
  SET_TAB,
  UPDATE_FIELD,
} from '../components/calendar/settings';
import { loadTabData } from '../components/calendar/settings/calendarSettingsLoader';
import { handleSave as dispatchSave } from '../components/calendar/settings/calendarSettingsSaver';

// Section components
import AvailabilitySection from './calendar-settings/AvailabilitySection';
import AppointmentTypesSection from './calendar-settings/AppointmentTypesSection';
import NotificationsSection from './calendar-settings/NotificationsSection';
import BookingPageSection from './calendar-settings/BookingPageSection';
import CancellationPolicySection from './calendar-settings/CancellationPolicySection';
import IntegrationsSection from './calendar-settings/IntegrationsSection';
import TeamSection from './calendar-settings/TeamSection';
import LocationsLabelsSection from './calendar-settings/LocationsLabelsSection';
import AdvancedSection from './calendar-settings/AdvancedSection';
import AISchedulingSection from './calendar-settings/AISchedulingSection';
import FollowUpCadenceSection from './calendar-settings/FollowUpCadenceSection';
import { getToken } from '../utils/tokenStore';

// ============================================================================
// Component
// ============================================================================

function CalendarSettings() {
  const navigate = useNavigate();
  const contentRef = useRef(null);
  const tabPanelRef = useRef(null);
  const [state, dispatch] = useReducer(settingsReducer, initialState);
  const [testResult, setTestResult] = useState(null);
  const [isTesting, setIsTesting] = useState(false);

  // Stable ref for accessing current state in async callbacks
  const stateRef = useRef(state);
  stateRef.current = state;
  const getState = useCallback(() => stateRef.current, []);

  // Destructure top-level state for convenience
  const { activeSection, loading, saving, hasChanges, saveStatus, sections } = state;

  // Section data aliases
  const availability = sections.availability.data;
  const seasonalHours = sections.availability.seasonalHours;
  const overrideDays = sections.availability.overrideDays;
  const expandedSections = sections.availability.expandedSections;
  const appointmentTypes = sections['appointment-types'].data;
  const notifications = sections.notifications.data;
  const bookingPage = sections['booking-page'].data;
  const cancellationPolicy = sections['cancellation-policy'].data;
  const advancedSettings = sections.advanced.data;
  const integrations = sections.integrations.data;
  const integrationSettings = sections.integrations.integrationSettings;
  const syncErrors = sections.integrations.syncErrors;
  const webhookSettings = sections.integrations.webhookSettings;
  const meetingDefaults = sections.integrations.meetingDefaults;
  const team = sections.team.data;
  const isManager = sections.team.isManager;
  const locations = sections['locations-labels'].locations;
  const locationsLoading = sections['locations-labels'].locationsLoading;
  const labels = sections['locations-labels'].labels;
  const labelsLoading = sections['locations-labels'].labelsLoading;
  const templates = sections['locations-labels'].templates;
  const templatesLoading = sections['locations-labels'].templatesLoading;
  const autoAssignLabels = sections['locations-labels'].autoAssignLabels;
  const labelMappings = sections['locations-labels'].labelMappings;
  const defaultLabelId = sections['locations-labels'].defaultLabelId;
  const aiScheduling = sections['ai-scheduling'].data;

  // ========== Derived ==========

  const activeNavItem = ALL_NAV_ITEMS.find(item => item.id === activeSection);
  const activeGroupName = NAV_SECTIONS.find(s => s.items.some(i => i.id === activeSection))?.group || '';
  const showSaveButton = SAVEABLE_SECTIONS.includes(activeSection);

  // ============================================================================
  // Setter factories (stable callbacks that mimic useState setters for children)
  // ============================================================================

  const setAvailability = useCallback((v) => dispatch({ type: UPDATE_FIELD, section: 'availability', field: 'data', value: v }), []);
  const setSeasonalHours = useCallback((v) => dispatch({ type: UPDATE_FIELD, section: 'availability', field: 'seasonalHours', value: v }), []);
  const setOverrideDays = useCallback((v) => dispatch({ type: UPDATE_FIELD, section: 'availability', field: 'overrideDays', value: v }), []);
  const setAppointmentTypes = useCallback((v) => dispatch({ type: UPDATE_FIELD, section: 'appointment-types', field: 'data', value: v }), []);
  const setNotifications = useCallback((v) => dispatch({ type: UPDATE_FIELD, section: 'notifications', field: 'data', value: v }), []);
  const setBookingPage = useCallback((v) => dispatch({ type: UPDATE_FIELD, section: 'booking-page', field: 'data', value: v }), []);
  const setCancellationPolicy = useCallback((v) => dispatch({ type: UPDATE_FIELD, section: 'cancellation-policy', field: 'data', value: v }), []);
  const setAdvancedSettings = useCallback((v) => dispatch({ type: UPDATE_FIELD, section: 'advanced', field: 'data', value: v }), []);
  const setIntegrations = useCallback((v) => dispatch({ type: UPDATE_FIELD, section: 'integrations', field: 'data', value: v }), []);
  const setIntegrationSettings = useCallback((v) => dispatch({ type: UPDATE_FIELD, section: 'integrations', field: 'integrationSettings', value: v }), []);
  const setSyncErrors = useCallback((v) => dispatch({ type: UPDATE_FIELD, section: 'integrations', field: 'syncErrors', value: v }), []);
  const setWebhookSettings = useCallback((v) => dispatch({ type: UPDATE_FIELD, section: 'integrations', field: 'webhookSettings', value: v }), []);
  const setMeetingDefaults = useCallback((v) => dispatch({ type: UPDATE_FIELD, section: 'integrations', field: 'meetingDefaults', value: v }), []);
  const setTeam = useCallback((v) => dispatch({ type: UPDATE_FIELD, section: 'team', field: 'data', value: v }), []);
  const setLocations = useCallback((v) => dispatch({ type: UPDATE_FIELD, section: 'locations-labels', field: 'locations', value: v }), []);
  const setLabels = useCallback((v) => dispatch({ type: UPDATE_FIELD, section: 'locations-labels', field: 'labels', value: v }), []);
  const setTemplates = useCallback((v) => dispatch({ type: UPDATE_FIELD, section: 'locations-labels', field: 'templates', value: v }), []);
  const setAutoAssignLabels = useCallback((v) => dispatch({ type: UPDATE_FIELD, section: 'locations-labels', field: 'autoAssignLabels', value: v }), []);
  const setLabelMappings = useCallback((v) => dispatch({ type: UPDATE_FIELD, section: 'locations-labels', field: 'labelMappings', value: v }), []);
  const setDefaultLabelId = useCallback((v) => dispatch({ type: UPDATE_FIELD, section: 'locations-labels', field: 'defaultLabelId', value: v }), []);
  const setAIScheduling = useCallback((v) => dispatch({ type: UPDATE_FIELD, section: 'ai-scheduling', field: 'data', value: v }), []);

  // ============================================================================
  // Data Loading
  // ============================================================================

  const doLoadTab = useCallback((tab) => {
    loadTabData(tab, dispatch, getState);
  }, [getState]);

  useEffect(() => {
    doLoadTab(activeSection);
  }, [activeSection]); // eslint-disable-line react-hooks/exhaustive-deps

  // Move focus to the active tab panel when tab changes (keyboard accessibility)
  useEffect(() => {
    if (tabPanelRef.current) {
      tabPanelRef.current.focus();
    }
  }, [activeSection]);

  // ============================================================================
  // Navigation
  // ============================================================================

  const handleSectionChange = useCallback((sectionId) => {
    if (hasChanges) {
      const proceed = window.confirm('You have unsaved changes. Discard and continue?');
      if (!proceed) return;
    }
    dispatch({ type: SET_TAB, payload: sectionId });
    if (contentRef.current) {
      contentRef.current.scrollTo(0, 0);
    }
  }, [hasChanges]);

  const handleNavKeyDown = useCallback((e, currentId) => {
    const ids = ALL_NAV_ITEMS.map(t => t.id);
    const idx = ids.indexOf(currentId);
    let newIdx;
    if (e.key === 'ArrowDown') { e.preventDefault(); newIdx = (idx + 1) % ids.length; }
    else if (e.key === 'ArrowUp') { e.preventDefault(); newIdx = (idx - 1 + ids.length) % ids.length; }
    else if (e.key === 'Home') { e.preventDefault(); newIdx = 0; }
    else if (e.key === 'End') { e.preventDefault(); newIdx = ids.length - 1; }
    else return;
    handleSectionChange(ids[newIdx]);
    document.getElementById(`calnav-${ids[newIdx]}`)?.focus();
  }, [handleSectionChange]);

  // ============================================================================
  // Save & Test
  // ============================================================================

  const markChanged = useCallback(() => {
    dispatch({ type: UPDATE_FIELD, section: activeSection, field: 'dirty', value: true });
  }, [activeSection]);

  const toggleExpandedSection = useCallback((key) => {
    dispatch({
      type: UPDATE_FIELD,
      section: 'availability',
      field: 'expandedSections',
      value: (prev) => ({ ...prev, [key]: !prev[key] }),
    });
  }, []);

  const handleTestConfig = async () => {
    setTestResult(null);
    setIsTesting(true);
    try {
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/scheduler/settings/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ test_duration: availability.buffer_minutes || 30 }),
      });
      const data = await response.json();
      if (response.ok && data.data) {
        setTestResult(data.data);
        if (data.data.success) {
          toast.success('Configuration test passed!');
        } else {
          toast.warning('Configuration test found issues');
        }
      } else {
        toast.error('Test failed — check your settings');
      }
    } catch (err) {
      toast.error('Configuration test failed');
    } finally {
      setIsTesting(false);
    }
  };

  const handleSave = useCallback(() => {
    dispatchSave(activeSection, sections, dispatch);
  }, [activeSection, sections]);

  // ============================================================================
  // Section router
  // ============================================================================

  const renderActiveSection = () => {
    if (loading) {
      return (
        <div className="cal-settings-loading" role="status">
          <div className="spinner"></div>
          <p>Loading settings...</p>
        </div>
      );
    }

    switch (activeSection) {
      case 'availability':
        return (
          <AvailabilitySection
            availability={availability}
            setAvailability={setAvailability}
            seasonalHours={seasonalHours}
            setSeasonalHours={setSeasonalHours}
            overrideDays={overrideDays}
            setOverrideDays={setOverrideDays}
            expandedSections={expandedSections}
            toggleExpandedSection={toggleExpandedSection}
            markChanged={markChanged}
          />
        );
      case 'appointment-types':
        return (
          <AppointmentTypesSection
            appointmentTypes={appointmentTypes}
            setAppointmentTypes={setAppointmentTypes}
            loading={loading}
            loadTabData={doLoadTab}
          />
        );
      case 'notifications':
        return (
          <NotificationsSection
            notifications={notifications}
            setNotifications={setNotifications}
            markChanged={markChanged}
          />
        );
      case 'booking-page':
        return (
          <BookingPageSection
            bookingPage={bookingPage}
            setBookingPage={setBookingPage}
            markChanged={markChanged}
          />
        );
      case 'cancellation-policy':
        return (
          <CancellationPolicySection
            cancellationPolicy={cancellationPolicy}
            setCancellationPolicy={setCancellationPolicy}
            markChanged={markChanged}
          />
        );
      case 'integrations':
        return (
          <IntegrationsSection
            integrations={integrations}
            setIntegrations={setIntegrations}
            integrationSettings={integrationSettings}
            setIntegrationSettings={setIntegrationSettings}
            syncErrors={syncErrors}
            setSyncErrors={setSyncErrors}
            webhookSettings={webhookSettings}
            setWebhookSettings={setWebhookSettings}
            meetingDefaults={meetingDefaults}
            setMeetingDefaults={setMeetingDefaults}
            markChanged={markChanged}
          />
        );
      case 'team':
        return (
          <TeamSection
            team={team}
            setTeam={setTeam}
            isManager={isManager}
            appointmentTypes={appointmentTypes}
            markChanged={markChanged}
            loadTabData={doLoadTab}
          />
        );
      case 'locations-labels':
        return (
          <LocationsLabelsSection
            locations={locations}
            setLocations={setLocations}
            locationsLoading={locationsLoading}
            labels={labels}
            setLabels={setLabels}
            labelsLoading={labelsLoading}
            templates={templates}
            setTemplates={setTemplates}
            templatesLoading={templatesLoading}
            autoAssignLabels={autoAssignLabels}
            setAutoAssignLabels={setAutoAssignLabels}
            labelMappings={labelMappings}
            setLabelMappings={setLabelMappings}
            defaultLabelId={defaultLabelId}
            setDefaultLabelId={setDefaultLabelId}
            appointmentTypes={appointmentTypes}
            loadTabData={doLoadTab}
          />
        );
      case 'ai-automation':
        return (
          <>
            <AISchedulingSection
              config={aiScheduling}
              setConfig={setAIScheduling}
              markChanged={markChanged}
            />
            <hr className="ai-automation-divider" />
            <FollowUpCadenceSection />
            <hr className="ai-automation-divider" />
            <AdvancedSection
              advancedSettings={advancedSettings}
              setAdvancedSettings={setAdvancedSettings}
              markChanged={markChanged}
            />
          </>
        );
      default:
        return (
          <AvailabilitySection
            availability={availability}
            setAvailability={setAvailability}
            seasonalHours={seasonalHours}
            setSeasonalHours={setSeasonalHours}
            overrideDays={overrideDays}
            setOverrideDays={setOverrideDays}
            expandedSections={expandedSections}
            toggleExpandedSection={toggleExpandedSection}
            markChanged={markChanged}
          />
        );
    }
  };

  // ============================================================================
  // Layout
  // ============================================================================

  return (
    <div className="cal-settings-page">
      {/* Top Bar */}
      <header className="cal-settings-topbar">
        <div className="cal-settings-topbar-inner">
          <div className="topbar-left">
            <button onClick={() => navigate(-1)} className="back-btn" aria-label="Go back">
              <i className="fas fa-arrow-left"></i>
            </button>
            <h1>Smart Calendar Settings</h1>
          </div>

          <div className="topbar-right">
            <div className={`save-status ${saveStatus}`}>
              <span className="status-dot"></span>
              <span>
                {saveStatus === 'saved' && 'All changes saved'}
                {saveStatus === 'saving' && 'Saving...'}
                {saveStatus === 'unsaved' && 'Unsaved changes'}
              </span>
            </div>

            <button
              className="btn-outline"
              onClick={handleTestConfig}
              disabled={isTesting || saving}
              title="Test your scheduler configuration"
            >
              {isTesting ? (
                <><i className="fas fa-spinner fa-spin"></i><span>Testing...</span></>
              ) : (
                <><i className="fas fa-vial"></i><span>Test Config</span></>
              )}
            </button>

            <button
              className="btn-outline"
              onClick={() => navigate('/calendar/setup')}
              title="Run Setup Wizard"
            >
              <i className="fas fa-magic"></i>
              <span>Setup Wizard</span>
            </button>

            <button
              className="btn-outline"
              onClick={() => toast.info('Calendar tour starting...')}
              title="Take a guided tour"
            >
              <i className="fas fa-info-circle"></i>
              <span>Tour</span>
            </button>

            {showSaveButton && (
              <button
                onClick={handleSave}
                disabled={saving || !hasChanges}
                className="btn-primary btn-sm"
              >
                {saving ? (
                  <><i className="fas fa-spinner fa-spin"></i> Saving</>
                ) : (
                  <><i className="fas fa-save"></i> Save</>
                )}
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Test Result Banner */}
      {testResult && (
        <div className={`cal-settings-test-result ${testResult.success ? 'success' : 'warning'}`} role="status">
          <div className="test-result-inner">
            <div className="test-result-header">
              <i className={`fas ${testResult.success ? 'fa-check-circle' : 'fa-exclamation-circle'}`}></i>
              <strong>{testResult.success ? 'Test Passed' : 'Issues Found'}</strong>
              <button className="btn-icon-sm" onClick={() => setTestResult(null)} aria-label="Dismiss">
                <i className="fas fa-times"></i>
              </button>
            </div>
            {testResult.loan_officers_available !== undefined && (
              <p>Loan officers available: {testResult.loan_officers_available}</p>
            )}
            {testResult.issues?.length > 0 && (
              <ul className="test-result-issues">
                {testResult.issues.map((issue, idx) => <li key={idx}>{issue}</li>)}
              </ul>
            )}
          </div>
        </div>
      )}

      {/* Mobile Tabs (visible < 768px) */}
      <div className="cal-settings-mobile-tabs" role="tablist" aria-label="Calendar settings sections">
        <div className="cal-settings-mobile-tabs-inner">
          {ALL_NAV_ITEMS.map(item => (
            <button
              key={item.id}
              role="tab"
              aria-selected={activeSection === item.id}
              aria-controls={`panel-${item.id}`}
              className={`mobile-tab-btn ${activeSection === item.id ? 'active' : ''}`}
              onClick={() => handleSectionChange(item.id)}
            >
              <i className={`fas ${item.icon}`}></i> {item.label}
            </button>
          ))}
        </div>
      </div>

      {/* Body: Sidebar + Content */}
      <div className="cal-settings-body">
        {/* Sidebar Navigation (hidden on mobile) */}
        <nav className="cal-settings-sidebar" role="tablist" aria-label="Calendar settings navigation" aria-orientation="vertical">
          {NAV_SECTIONS.map(section => (
            <div key={section.group} className="sidebar-nav-group" role="group" aria-labelledby={`nav-group-${section.group.toLowerCase()}`}>
              <span className="sidebar-group-label" id={`nav-group-${section.group.toLowerCase()}`}>{section.group}</span>
              {section.items.map(item => (
                <button
                  key={item.id}
                  id={`calnav-${item.id}`}
                  role="tab"
                  aria-selected={activeSection === item.id}
                  aria-controls={`panel-${item.id}`}
                  tabIndex={activeSection === item.id ? 0 : -1}
                  className={`sidebar-nav-item ${activeSection === item.id ? 'active' : ''}`}
                  onClick={() => handleSectionChange(item.id)}
                  onKeyDown={(e) => handleNavKeyDown(e, item.id)}
                >
                  <i className={`fas ${item.icon}`} aria-hidden="true"></i>
                  <span>{item.label}</span>
                  {item.badge && <span className="nav-badge">{item.badge}</span>}
                </button>
              ))}
            </div>
          ))}
        </nav>

        {/* Content Area */}
        <main
          className="cal-settings-content"
          ref={(node) => { contentRef.current = node; tabPanelRef.current = node; }}
          id={`panel-${activeSection}`}
          role="tabpanel"
          tabIndex={-1}
          aria-labelledby={`calnav-${activeSection}`}
        >
          {/* Breadcrumb */}
          <div className="cal-settings-breadcrumb">
            <span>Settings</span>
            <span className="breadcrumb-separator">/</span>
            <span>{activeGroupName}</span>
            <span className="breadcrumb-separator">/</span>
            <span className="breadcrumb-current">{activeNavItem?.label}</span>
          </div>

          {/* Section Header */}
          <div className="section-page-header">
            <h2>{activeNavItem?.label}</h2>
            <p>{activeNavItem?.description}</p>
          </div>

          {/* Section Content */}
          {renderActiveSection()}
        </main>
      </div>

      {/* Sticky Save Bar (bottom, only when unsaved) */}
      {hasChanges && showSaveButton && (
        <div className="sticky-save-bar">
          <div className="save-bar-content">
            <span>You have unsaved changes</span>
            <div className="save-bar-actions">
              <button
                type="button"
                onClick={() => doLoadTab(activeSection)}
                className="btn-secondary"
                disabled={saving}
              >
                Discard
              </button>
              <button
                onClick={handleSave}
                className="btn-primary"
                disabled={saving}
              >
                {saving ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default CalendarSettings;
