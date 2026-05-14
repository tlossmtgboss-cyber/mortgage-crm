import React from 'react';
import { timeOptions } from './utils';

const SettingsView = ({
  editableConfig, setEditableConfig, config,
  settingsTab, setSettingsTab,
  savingSettings, handleSaveSettings,
  updateWorkingHours, updateConfigField,
  seedDefaultTemplates
}) => {
  // Render working hours tab content
  const renderWorkingHoursTab = () => {
    const days = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
    const dayLabels = {
      sunday: 'Sunday', monday: 'Monday', tuesday: 'Tuesday',
      wednesday: 'Wednesday', thursday: 'Thursday',
      friday: 'Friday', saturday: 'Saturday'
    };

    return (
      <div className="settings-tab-content">
        <p className="settings-description">Configure which days and hours you're available for video meetings.</p>
        <div className="working-hours-editor">
          {days.map(day => {
            const hours = editableConfig?.working_hours?.[day] || { enabled: false, start: '09:00', end: '17:00' };
            return (
              <div key={day} className={`day-row ${hours.enabled ? 'enabled' : 'disabled'}`}>
                <div className="day-toggle">
                  <label className="toggle-switch">
                    <input
                      type="checkbox"
                      checked={hours.enabled}
                      onChange={(e) => updateWorkingHours(day, 'enabled', e.target.checked)}
                    />
                    <span className="toggle-slider"></span>
                  </label>
                  <span className="day-label">{dayLabels[day]}</span>
                </div>
                {hours.enabled ? (
                  <div className="time-range">
                    <select
                      value={hours.start}
                      onChange={(e) => updateWorkingHours(day, 'start', e.target.value)}
                    >
                      {timeOptions.map(opt => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                    <span className="time-separator">to</span>
                    <select
                      value={hours.end}
                      onChange={(e) => updateWorkingHours(day, 'end', e.target.value)}
                    >
                      {timeOptions.map(opt => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                  </div>
                ) : (
                  <div className="time-range-off">
                    <span>Unavailable</span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  // Render booking settings tab content
  const renderBookingTab = () => (
    <div className="settings-tab-content">
      <p className="settings-description">Configure default booking behavior and limits for video meetings.</p>
      <div className="booking-settings-form">
        <div className="form-group">
          <label>Default Duration</label>
          <select
            value={editableConfig?.default_duration_minutes || 30}
            onChange={(e) => updateConfigField('default_duration_minutes', parseInt(e.target.value))}
          >
            <option value={15}>15 minutes</option>
            <option value={20}>20 minutes</option>
            <option value={30}>30 minutes</option>
            <option value={45}>45 minutes</option>
            <option value={60}>60 minutes</option>
            <option value={90}>90 minutes</option>
          </select>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Buffer Before (minutes)</label>
            <input
              type="number"
              value={editableConfig?.buffer_before_minutes || 0}
              onChange={(e) => updateConfigField('buffer_before_minutes', parseInt(e.target.value) || 0)}
              min="0" max="60"
            />
            <span className="help-text">Time before meetings for preparation</span>
          </div>
          <div className="form-group">
            <label>Buffer After (minutes)</label>
            <input
              type="number"
              value={editableConfig?.buffer_after_minutes || 0}
              onChange={(e) => updateConfigField('buffer_after_minutes', parseInt(e.target.value) || 0)}
              min="0" max="60"
            />
            <span className="help-text">Time after meetings for follow-up</span>
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Minimum Notice (hours)</label>
            <input
              type="number"
              value={editableConfig?.min_notice_hours || 1}
              onChange={(e) => updateConfigField('min_notice_hours', parseInt(e.target.value) || 1)}
              min="1" max="168"
            />
            <span className="help-text">How far in advance clients must book</span>
          </div>
          <div className="form-group">
            <label>Max Advance Booking (days)</label>
            <input
              type="number"
              value={editableConfig?.max_advance_days || 30}
              onChange={(e) => updateConfigField('max_advance_days', parseInt(e.target.value) || 30)}
              min="1" max="365"
            />
            <span className="help-text">How far in the future clients can book</span>
          </div>
        </div>

        <div className="form-group">
          <label>Max Meetings Per Day</label>
          <input
            type="number"
            value={editableConfig?.max_meetings_per_day || 8}
            onChange={(e) => updateConfigField('max_meetings_per_day', parseInt(e.target.value) || 8)}
            min="1" max="20"
          />
          <span className="help-text">Maximum number of video meetings per day</span>
        </div>
      </div>
    </div>
  );

  // Render AI settings tab content
  const renderAITab = () => (
    <div className="settings-tab-content">
      <p className="settings-description">Configure AI-powered video meeting features.</p>
      <div className="ai-settings-form">
        <div className="form-group checkbox-group">
          <label className="toggle-label">
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={editableConfig?.ai_scheduling_enabled || false}
                onChange={(e) => updateConfigField('ai_scheduling_enabled', e.target.checked)}
              />
              <span className="toggle-slider"></span>
            </label>
            <div className="toggle-info">
              <span className="toggle-title">AI Smart Scheduling</span>
              <span className="toggle-description">Let AI suggest optimal meeting times based on your patterns and client preferences</span>
            </div>
          </label>
        </div>

        <div className="form-group checkbox-group">
          <label className="toggle-label">
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={editableConfig?.auto_reschedule_enabled || false}
                onChange={(e) => updateConfigField('auto_reschedule_enabled', e.target.checked)}
              />
              <span className="toggle-slider"></span>
            </label>
            <div className="toggle-info">
              <span className="toggle-title">Auto-Reschedule Suggestions</span>
              <span className="toggle-description">Automatically suggest better times when conflicts arise</span>
            </div>
          </label>
        </div>

        <div className="form-group checkbox-group">
          <label className="toggle-label">
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={editableConfig?.smart_reminders_enabled || false}
                onChange={(e) => updateConfigField('smart_reminders_enabled', e.target.checked)}
              />
              <span className="toggle-slider"></span>
            </label>
            <div className="toggle-info">
              <span className="toggle-title">Smart Reminders</span>
              <span className="toggle-description">AI-optimized reminder timing based on client engagement</span>
            </div>
          </label>
        </div>
      </div>
    </div>
  );

  return (
    <div className="scheduler-settings-view">
      {editableConfig ? (
        <>
          <div className="settings-sub-tabs">
            <button
              className={`sub-tab ${settingsTab === 'working-hours' ? 'active' : ''}`}
              onClick={() => setSettingsTab('working-hours')}
            >
              Working Hours
            </button>
            <button
              className={`sub-tab ${settingsTab === 'booking' ? 'active' : ''}`}
              onClick={() => setSettingsTab('booking')}
            >
              Booking Settings
            </button>
            <button
              className={`sub-tab ${settingsTab === 'ai' ? 'active' : ''}`}
              onClick={() => setSettingsTab('ai')}
            >
              AI Settings
            </button>
          </div>

          {settingsTab === 'working-hours' && renderWorkingHoursTab()}
          {settingsTab === 'booking' && renderBookingTab()}
          {settingsTab === 'ai' && renderAITab()}

          <div className="settings-actions">
            <button
              className="save-settings-btn"
              onClick={handleSaveSettings}
              disabled={savingSettings}
            >
              {savingSettings ? 'Saving...' : 'Save Settings'}
            </button>
            <button
              className="reset-settings-btn"
              onClick={() => setEditableConfig(JSON.parse(JSON.stringify(config)))}
              disabled={savingSettings}
            >
              Reset Changes
            </button>
          </div>
        </>
      ) : (
        <div className="empty-state">
          <p>No configuration found</p>
          <button onClick={seedDefaultTemplates}>Initialize Meetings</button>
        </div>
      )}
    </div>
  );
};

export default SettingsView;
