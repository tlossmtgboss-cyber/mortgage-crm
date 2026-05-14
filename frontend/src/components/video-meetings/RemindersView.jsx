import React from 'react';
import { toast } from '../../utils/toast';

const RemindersView = ({ reminderSettings, setReminderSettings, savingReminders, setSavingReminders }) => {
  const addReminder = () => {
    const newId = Math.max(...reminderSettings.reminders.map(r => r.id), 0) + 1;
    setReminderSettings(prev => ({
      ...prev,
      reminders: [...prev.reminders, {
        id: newId,
        timing: 24,
        unit: 'hours',
        method: 'email',
        enabled: true,
        message: 'Reminder: Your video meeting is coming up on {{appointment_date}} at {{appointment_time}}.'
      }]
    }));
  };

  const updateReminder = (id, field, value) => {
    setReminderSettings(prev => ({
      ...prev,
      reminders: prev.reminders.map(r =>
        r.id === id ? { ...r, [field]: value } : r
      )
    }));
  };

  const deleteReminder = (id) => {
    setReminderSettings(prev => ({
      ...prev,
      reminders: prev.reminders.filter(r => r.id !== id)
    }));
  };

  const handleSaveReminders = async () => {
    setSavingReminders(true);
    try {
      await new Promise(resolve => setTimeout(resolve, 500));
      toast.success('Reminder settings saved successfully!');
    } catch (err) {
      console.error('Save reminders error:', err);
      toast.error('Failed to save reminder settings');
    } finally {
      setSavingReminders(false);
    }
  };

  return (
    <div className="scheduler-reminders-view">
      <div className="reminders-header">
        <div className="header-content">
          <h3>Meeting Reminders</h3>
          <p className="description">Configure automatic reminder messages to reduce no-shows and keep clients informed about their upcoming video meetings.</p>
        </div>
        <label className="master-toggle">
          <span>Reminders {reminderSettings.enabled ? 'Enabled' : 'Disabled'}</span>
          <label className="toggle-switch">
            <input
              type="checkbox"
              checked={reminderSettings.enabled}
              onChange={(e) => setReminderSettings(prev => ({ ...prev, enabled: e.target.checked }))}
            />
            <span className="toggle-slider"></span>
          </label>
        </label>
      </div>

      {reminderSettings.enabled && (
        <>
          <div className="reminders-list">
            <div className="list-header">
              <h4>Reminder Schedule</h4>
              <button className="add-reminder-btn" onClick={addReminder}>+ Add Reminder</button>
            </div>

            {/* Booking Confirmation */}
            <div className={`reminder-card booking-confirmation ${reminderSettings.bookingConfirmation?.enabled ? '' : 'disabled'}`}>
              <div className="reminder-header">
                <div className="reminder-number">Meeting Confirmation</div>
                <div className="reminder-controls">
                  <label className="toggle-switch small">
                    <input
                      type="checkbox"
                      checked={reminderSettings.bookingConfirmation?.enabled ?? true}
                      onChange={(e) => setReminderSettings(prev => ({
                        ...prev,
                        bookingConfirmation: { ...prev.bookingConfirmation, enabled: e.target.checked }
                      }))}
                    />
                    <span className="toggle-slider"></span>
                  </label>
                </div>
              </div>

              <div className="reminder-config">
                <div className="timing-row">
                  <label>Send</label>
                  <span className="confirmation-timing">immediately after booking</span>
                  <span>via</span>
                  <select
                    value={reminderSettings.bookingConfirmation?.method || 'both'}
                    onChange={(e) => setReminderSettings(prev => ({
                      ...prev,
                      bookingConfirmation: { ...prev.bookingConfirmation, method: e.target.value }
                    }))}
                    className="method-select"
                  >
                    <option value="email">Email</option>
                    <option value="sms">SMS</option>
                    <option value="both">Both</option>
                  </select>
                </div>

                <div className="message-row">
                  <label>Message</label>
                  <textarea
                    value={reminderSettings.bookingConfirmation?.message || ''}
                    onChange={(e) => setReminderSettings(prev => ({
                      ...prev,
                      bookingConfirmation: { ...prev.bookingConfirmation, message: e.target.value }
                    }))}
                    placeholder="Enter confirmation message..."
                    rows={3}
                  />
                  <div className="message-help">
                    <span className="help-label">Available variables:</span>
                    <code>{'{{appointment_date}}'}</code>
                    <code>{'{{appointment_time}}'}</code>
                    <code>{'{{attendee_name}}'}</code>
                    <code>{'{{meeting_type}}'}</code>
                    <code>{'{{meeting_link}}'}</code>
                  </div>
                </div>
              </div>
            </div>

            {reminderSettings.reminders.map((reminder, index) => (
              <div key={reminder.id} className={`reminder-card ${reminder.enabled ? '' : 'disabled'}`}>
                <div className="reminder-header">
                  <div className="reminder-number">Reminder {index + 1}</div>
                  <div className="reminder-controls">
                    <label className="toggle-switch small">
                      <input
                        type="checkbox"
                        checked={reminder.enabled}
                        onChange={(e) => updateReminder(reminder.id, 'enabled', e.target.checked)}
                      />
                      <span className="toggle-slider"></span>
                    </label>
                    <button
                      className="delete-reminder-btn"
                      onClick={() => deleteReminder(reminder.id)}
                      title="Delete reminder"
                    >
                      x
                    </button>
                  </div>
                </div>

                <div className="reminder-config">
                  <div className="timing-row">
                    <label>Send</label>
                    <input
                      type="number"
                      value={reminder.timing}
                      onChange={(e) => updateReminder(reminder.id, 'timing', parseInt(e.target.value) || 1)}
                      min="1"
                      max="168"
                      className="timing-input"
                    />
                    <select
                      value={reminder.unit}
                      onChange={(e) => updateReminder(reminder.id, 'unit', e.target.value)}
                      className="unit-select"
                    >
                      <option value="minutes">minutes</option>
                      <option value="hours">hours</option>
                      <option value="days">days</option>
                    </select>
                    <span>before meeting via</span>
                    <select
                      value={reminder.method}
                      onChange={(e) => updateReminder(reminder.id, 'method', e.target.value)}
                      className="method-select"
                    >
                      <option value="email">Email</option>
                      <option value="sms">SMS</option>
                      <option value="both">Both</option>
                    </select>
                  </div>

                  <div className="message-row">
                    <label>Message</label>
                    <textarea
                      value={reminder.message}
                      onChange={(e) => updateReminder(reminder.id, 'message', e.target.value)}
                      placeholder="Enter reminder message..."
                      rows={3}
                    />
                    <div className="message-help">
                      <span className="help-label">Available variables:</span>
                      <code>{'{{appointment_date}}'}</code>
                      <code>{'{{appointment_time}}'}</code>
                      <code>{'{{attendee_name}}'}</code>
                      <code>{'{{meeting_type}}'}</code>
                      <code>{'{{meeting_link}}'}</code>
                    </div>
                  </div>
                </div>
              </div>
            ))}

            {reminderSettings.reminders.length === 0 && (
              <div className="empty-reminders">
                <p>No reminders configured. Add a reminder to reduce no-shows.</p>
                <button onClick={addReminder}>+ Add Your First Reminder</button>
              </div>
            )}
          </div>

          <div className="reminder-options">
            <h4>Email Options</h4>

            <div className="form-group">
              <label>Default Email Subject</label>
              <input
                type="text"
                value={reminderSettings.default_email_subject}
                onChange={(e) => setReminderSettings(prev => ({ ...prev, default_email_subject: e.target.value }))}
                placeholder="Reminder: Your Upcoming Video Meeting"
              />
            </div>

            <div className="checkbox-options">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={reminderSettings.include_calendar_link}
                  onChange={(e) => setReminderSettings(prev => ({ ...prev, include_calendar_link: e.target.checked }))}
                />
                Include "Add to Calendar" link
              </label>

              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={reminderSettings.include_reschedule_link}
                  onChange={(e) => setReminderSettings(prev => ({ ...prev, include_reschedule_link: e.target.checked }))}
                />
                Include reschedule link
              </label>

              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={reminderSettings.include_cancel_link}
                  onChange={(e) => setReminderSettings(prev => ({ ...prev, include_cancel_link: e.target.checked }))}
                />
                Include cancellation link
              </label>
            </div>
          </div>

          <div className="reminders-actions">
            <button
              className="save-reminders-btn"
              onClick={handleSaveReminders}
              disabled={savingReminders}
            >
              {savingReminders ? 'Saving...' : 'Save Reminder Settings'}
            </button>
          </div>
        </>
      )}
    </div>
  );
};

export default RemindersView;
