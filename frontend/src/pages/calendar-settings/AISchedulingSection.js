/**
 * AI Scheduling Section — Calendar Settings
 *
 * Configures how AI agents schedule appointments on the LO's calendar:
 * - Auto-scheduling rules (which cadences can book)
 * - SMS/email follow-up scheduling triggers
 * - AI booking preferences (preferred times, buffer, max per day)
 * - Smart conflict resolution
 */

export default function AISchedulingSection({ config, setConfig, markChanged }) {
  const update = (field, value) => {
    setConfig(prev => ({ ...prev, [field]: value }));
    if (markChanged) markChanged();
  };

  const updateNested = (parent, field, value) => {
    setConfig(prev => ({
      ...prev,
      [parent]: { ...prev[parent], [field]: value },
    }));
    if (markChanged) markChanged();
  };

  const addPreferredTime = () => {
    setConfig(prev => ({
      ...prev,
      preferred_times: [...prev.preferred_times, '12:00'],
    }));
    if (markChanged) markChanged();
  };

  const removePreferredTime = (idx) => {
    setConfig(prev => ({
      ...prev,
      preferred_times: prev.preferred_times.filter((_, i) => i !== idx),
    }));
    if (markChanged) markChanged();
  };

  const updatePreferredTime = (idx, val) => {
    setConfig(prev => {
      const times = [...prev.preferred_times];
      times[idx] = val;
      return { ...prev, preferred_times: times };
    });
    if (markChanged) markChanged();
  };

  return (
    <div className="settings-section ai-scheduling-section">
      <div className="section-header-block">
        <h2>AI Scheduling</h2>
        <p className="section-desc">
          Configure how AI agents and automated follow-ups schedule appointments on your calendar
        </p>
      </div>

      {/* Master toggle */}
      <div className="setting-card">
        <div className="setting-card-header">
          <h3>AI Appointment Scheduling</h3>
          <label className="toggle-switch">
            <input
              type="checkbox"
              checked={config.enabled}
              onChange={e => update('enabled', e.target.checked)}
            />
            <span className="toggle-slider"></span>
          </label>
        </div>
        <p className="setting-desc">
          Allow AI agents to view your availability and schedule appointments with borrowers
        </p>
      </div>

      {config.enabled && (
        <>
          {/* Auto-booking */}
          <div className="setting-card">
            <div className="setting-card-header">
              <h3>Auto-Book Without Confirmation</h3>
              <label className="toggle-switch">
                <input
                  type="checkbox"
                  checked={config.auto_book_enabled}
                  onChange={e => update('auto_book_enabled', e.target.checked)}
                />
                <span className="toggle-slider"></span>
              </label>
            </div>
            <p className="setting-desc">
              When enabled, AI will book directly on your calendar. When disabled, borrowers receive a booking link to choose their time.
            </p>

            {!config.auto_book_enabled && (
              <div className="setting-sub-option">
                <label>Confirmation method</label>
                <select
                  value={config.confirmation_method}
                  onChange={e => update('confirmation_method', e.target.value)}
                >
                  <option value="sms">SMS with booking link</option>
                  <option value="email">Email with booking link</option>
                  <option value="both">Both SMS and email</option>
                </select>
              </div>
            )}
          </div>

          {/* Preferred times */}
          <div className="setting-card">
            <h3>Preferred Meeting Times</h3>
            <p className="setting-desc">
              AI will prioritize scheduling at these times when available
            </p>
            <div className="preferred-times-list">
              {config.preferred_times.map((time, idx) => (
                <div key={idx} className="preferred-time-row">
                  <input
                    type="time"
                    value={time}
                    onChange={e => updatePreferredTime(idx, e.target.value)}
                  />
                  <button
                    className="btn-remove-sm"
                    onClick={() => removePreferredTime(idx)}
                    aria-label="Remove time"
                  >
                    &times;
                  </button>
                </div>
              ))}
              <button className="btn-add-sm" onClick={addPreferredTime}>
                + Add Time
              </button>
            </div>
          </div>

          {/* Limits */}
          <div className="setting-card">
            <h3>Booking Limits</h3>
            <div className="setting-row-grid">
              <div className="setting-field">
                <label>Max AI bookings per day</label>
                <input
                  type="number"
                  min="1"
                  max="20"
                  value={config.max_ai_bookings_per_day}
                  onChange={e => update('max_ai_bookings_per_day', parseInt(e.target.value) || 5)}
                />
              </div>
              <div className="setting-field">
                <label>Buffer before (min)</label>
                <input
                  type="number"
                  min="0"
                  max="60"
                  value={config.buffer_before_minutes}
                  onChange={e => update('buffer_before_minutes', parseInt(e.target.value) || 0)}
                />
              </div>
              <div className="setting-field">
                <label>Buffer after (min)</label>
                <input
                  type="number"
                  min="0"
                  max="60"
                  value={config.buffer_after_minutes}
                  onChange={e => update('buffer_after_minutes', parseInt(e.target.value) || 0)}
                />
              </div>
            </div>
          </div>

          {/* Smart scheduling */}
          <div className="setting-card">
            <h3>Smart Scheduling Rules</h3>
            <p className="setting-desc">
              AI uses these rules to optimize your daily schedule
            </p>
            <div className="checkbox-list">
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={config.smart_scheduling.avoid_back_to_back}
                  onChange={e => updateNested('smart_scheduling', 'avoid_back_to_back', e.target.checked)}
                />
                <div>
                  <span className="checkbox-label-text">Avoid back-to-back meetings</span>
                  <span className="checkbox-desc">Ensures buffer between consecutive appointments</span>
                </div>
              </label>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={config.smart_scheduling.cluster_similar_meetings}
                  onChange={e => updateNested('smart_scheduling', 'cluster_similar_meetings', e.target.checked)}
                />
                <div>
                  <span className="checkbox-label-text">Cluster similar meeting types</span>
                  <span className="checkbox-desc">Groups discovery calls together, document reviews together</span>
                </div>
              </label>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={config.smart_scheduling.protect_focus_time}
                  onChange={e => updateNested('smart_scheduling', 'protect_focus_time', e.target.checked)}
                />
                <div>
                  <span className="checkbox-label-text">Protect focus time blocks</span>
                  <span className="checkbox-desc">AI will not schedule meetings during your protected time</span>
                </div>
              </label>
            </div>
          </div>

          {/* SMS follow-up triggers */}
          <div className="setting-card">
            <h3>SMS Follow-Up Scheduling</h3>
            <p className="setting-desc">
              How AI sends booking links via SMS when following up with borrowers
            </p>
            <div className="checkbox-list">
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={config.sms_triggers.send_booking_link}
                  onChange={e => updateNested('sms_triggers', 'send_booking_link', e.target.checked)}
                />
                <div>
                  <span className="checkbox-label-text">Include booking link in SMS follow-ups</span>
                  <span className="checkbox-desc">AI will include a one-click booking link in outreach messages</span>
                </div>
              </label>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={config.sms_triggers.include_calendar_preview}
                  onChange={e => updateNested('sms_triggers', 'include_calendar_preview', e.target.checked)}
                />
                <div>
                  <span className="checkbox-label-text">Show next available slots in message</span>
                  <span className="checkbox-desc">e.g., "I have openings Tue 2pm, Wed 10am, or Thu 3pm"</span>
                </div>
              </label>
            </div>
            <div className="setting-row-grid" style={{ marginTop: 16 }}>
              <div className="setting-field">
                <label>Follow up after (hours)</label>
                <input
                  type="number"
                  min="1"
                  max="168"
                  value={config.sms_triggers.follow_up_no_response_hours}
                  onChange={e => updateNested('sms_triggers', 'follow_up_no_response_hours', parseInt(e.target.value) || 24)}
                />
              </div>
              <div className="setting-field">
                <label>Max follow-up messages</label>
                <input
                  type="number"
                  min="1"
                  max="10"
                  value={config.sms_triggers.max_follow_ups}
                  onChange={e => updateNested('sms_triggers', 'max_follow_ups', parseInt(e.target.value) || 3)}
                />
              </div>
            </div>
          </div>

          {/* AI response handling */}
          <div className="setting-card">
            <h3>AI Response Handling</h3>
            <div className="checkbox-list">
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={config.ai_response_handling.auto_reschedule_on_cancel}
                  onChange={e => updateNested('ai_response_handling', 'auto_reschedule_on_cancel', e.target.checked)}
                />
                <div>
                  <span className="checkbox-label-text">Auto-suggest reschedule when borrower cancels</span>
                  <span className="checkbox-desc">AI sends new time options automatically</span>
                </div>
              </label>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={config.ai_response_handling.respect_borrower_timezone}
                  onChange={e => updateNested('ai_response_handling', 'respect_borrower_timezone', e.target.checked)}
                />
                <div>
                  <span className="checkbox-label-text">Respect borrower timezone</span>
                  <span className="checkbox-desc">Show times in the borrower's local timezone</span>
                </div>
              </label>
            </div>
            <div className="setting-row-grid" style={{ marginTop: 16 }}>
              <div className="setting-field">
                <label>Alternative time slots to suggest</label>
                <input
                  type="number"
                  min="1"
                  max="10"
                  value={config.ai_response_handling.suggest_alternatives}
                  onChange={e => updateNested('ai_response_handling', 'suggest_alternatives', parseInt(e.target.value) || 3)}
                />
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
