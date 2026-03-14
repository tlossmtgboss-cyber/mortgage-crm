/**
 * AdvancedSection - Calendar Settings
 *
 * Handles advanced settings: auto-confirm, timezone selector, waitlist, calendar feed.
 */
import React from 'react';
import CalendarFeedSettings from '../../components/calendar/CalendarFeedSettings';

export default function AdvancedSection({
  advancedSettings,
  setAdvancedSettings,
  markChanged,
}) {
  return (
    <div role="tabpanel" id="panel-advanced" aria-labelledby="calnav-advanced">
      <section className="cal-settings-section">
        <h2>Advanced Settings</h2>
        <p className="section-description">Additional configuration options for power users.</p>

        <div className="advanced-settings-list">
          <div className="advanced-setting-item">
            <div className="advanced-setting-info">
              <h4>Auto-confirm Appointments</h4>
              <p>Automatically confirm appointments without manual approval.</p>
            </div>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={advancedSettings.auto_confirm_appointments}
                onChange={(e) => {
                  setAdvancedSettings(prev => ({ ...prev, auto_confirm_appointments: e.target.checked }));
                  markChanged();
                }}
              />
              <span className="toggle-slider"></span>
            </label>
          </div>

          <div className="advanced-setting-item">
            <div className="advanced-setting-info">
              <h4>Show Timezone Selector</h4>
              <p>Allow clients to select their timezone on the booking page.</p>
            </div>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={advancedSettings.show_timezone_selector}
                onChange={(e) => {
                  setAdvancedSettings(prev => ({ ...prev, show_timezone_selector: e.target.checked }));
                  markChanged();
                }}
              />
              <span className="toggle-slider"></span>
            </label>
          </div>

          <div className="advanced-setting-item">
            <div className="advanced-setting-info">
              <h4>Enable Waitlist</h4>
              <p>Allow clients to join a waitlist when no slots are available.</p>
            </div>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={advancedSettings.enable_waitlist}
                onChange={(e) => {
                  setAdvancedSettings(prev => ({ ...prev, enable_waitlist: e.target.checked }));
                  markChanged();
                }}
              />
              <span className="toggle-slider"></span>
            </label>
          </div>

          <div className="advanced-setting-item">
            <div className="advanced-setting-info">
              <h4>Calendar Feed (iCal/ICS)</h4>
              <p>Generate an ICS feed URL for subscribing in external calendar apps.</p>
            </div>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={advancedSettings.calendar_feed_enabled}
                onChange={(e) => {
                  setAdvancedSettings(prev => ({ ...prev, calendar_feed_enabled: e.target.checked }));
                  markChanged();
                }}
              />
              <span className="toggle-slider"></span>
            </label>
          </div>
        </div>
      </section>

      {advancedSettings.calendar_feed_enabled && (
        <section className="cal-settings-section">
          <CalendarFeedSettings />
        </section>
      )}
    </div>
  );
}
