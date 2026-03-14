/**
 * CancellationPolicySection - Calendar Settings
 *
 * Handles cancellation policy selection and rescheduling rules.
 */
import React from 'react';

const CANCELLATION_POLICIES = [
  { value: 'flexible', label: 'Flexible', description: 'Clients can cancel or reschedule up to 1 hour before' },
  { value: 'moderate', label: 'Moderate', description: 'Clients can cancel or reschedule up to 24 hours before' },
  { value: 'strict', label: 'Strict', description: 'Clients can cancel or reschedule up to 48 hours before' },
  { value: 'none', label: 'No Cancellation', description: 'Clients cannot cancel or reschedule online' },
];

export default function CancellationPolicySection({
  cancellationPolicy,
  setCancellationPolicy,
  markChanged,
}) {
  return (
    <div role="tabpanel" id="panel-cancellation-policy" aria-labelledby="calnav-cancellation-policy">
      <section className="cal-settings-section">
        <h2>Cancellation Policy</h2>
        <p className="section-description">Set rules for when clients can cancel or reschedule appointments.</p>

        <div className="cancel-policy-options">
          {CANCELLATION_POLICIES.map(policy => (
            <label
              key={policy.value}
              className={`cancel-policy-option ${cancellationPolicy.policy === policy.value ? 'selected' : ''}`}
            >
              <input
                type="radio"
                name="cancellation-policy"
                value={policy.value}
                checked={cancellationPolicy.policy === policy.value}
                onChange={() => {
                  setCancellationPolicy(prev => ({ ...prev, policy: policy.value }));
                  markChanged();
                }}
              />
              <div className="strategy-content">
                <strong>{policy.label}</strong>
                <span>{policy.description}</span>
              </div>
            </label>
          ))}
        </div>

        <h3 className="subsection-title">Rescheduling</h3>
        <div className="form-grid">
          <div className="form-field">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={cancellationPolicy.allow_reschedule}
                onChange={(e) => {
                  setCancellationPolicy(prev => ({ ...prev, allow_reschedule: e.target.checked }));
                  markChanged();
                }}
              />
              Allow clients to reschedule online
            </label>
          </div>
          <div className="form-field">
            <label htmlFor="reschedule-limit">Max reschedules per appointment</label>
            <input
              id="reschedule-limit"
              type="number"
              min="0"
              max="10"
              value={cancellationPolicy.reschedule_limit}
              onChange={(e) => {
                setCancellationPolicy(prev => ({ ...prev, reschedule_limit: parseInt(e.target.value) || 0 }));
                markChanged();
              }}
            />
          </div>
          <div className="form-field">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={cancellationPolicy.require_reason}
                onChange={(e) => {
                  setCancellationPolicy(prev => ({ ...prev, require_reason: e.target.checked }));
                  markChanged();
                }}
              />
              Require reason for cancellation
            </label>
          </div>
        </div>
      </section>
    </div>
  );
}
