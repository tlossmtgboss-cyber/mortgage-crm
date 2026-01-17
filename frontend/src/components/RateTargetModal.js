import React, { useState, useEffect } from 'react';
import { mumAPI } from '../services/api';
import './RateTargetModal.css';

function RateTargetModal({ target, onSave, onClose }) {
  const [formData, setFormData] = useState({
    mum_client_id: '',
    target_type: 'savings_threshold',
    monthly_savings_threshold: 200,
    rate_drop_percentage: 0.5,
    target_rate: 6.0,
    loan_type: 'conventional',
    loan_term: 30,
    auto_call_enabled: false,
    call_preference: 'business_hours',
    notify_email: true,
    notify_sms: true,
    notify_lo: true,
    notes: '',
  });

  const [mumClients, setMumClients] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadingClients, setLoadingClients] = useState(true);
  const [errors, setErrors] = useState({});

  useEffect(() => {
    loadMumClients();
    if (target) {
      setFormData({
        mum_client_id: target.mum_client_id || '',
        target_type: target.target_type || 'savings_threshold',
        monthly_savings_threshold: target.monthly_savings_threshold || 200,
        rate_drop_percentage: target.rate_drop_percentage || 0.5,
        target_rate: target.target_rate || 6.0,
        loan_type: target.loan_type || 'conventional',
        loan_term: target.loan_term || 30,
        auto_call_enabled: target.auto_call_enabled || false,
        call_preference: target.call_preference || 'business_hours',
        notify_email: target.notify_email !== false,
        notify_sms: target.notify_sms !== false,
        notify_lo: target.notify_lo !== false,
        notes: target.notes || '',
      });
    }
  }, [target]);

  const loadMumClients = async () => {
    try {
      setLoadingClients(true);
      const clients = await mumAPI.getAll();
      setMumClients(Array.isArray(clients) ? clients : []);
    } catch (error) {
      console.error('Failed to load MUM clients:', error);
    } finally {
      setLoadingClients(false);
    }
  };

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
    // Clear error when field changes
    if (errors[name]) {
      setErrors(prev => ({ ...prev, [name]: null }));
    }
  };

  const handleNumberChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value === '' ? '' : parseFloat(value)
    }));
  };

  const validate = () => {
    const newErrors = {};

    if (!formData.mum_client_id) {
      newErrors.mum_client_id = 'Please select a MUM client';
    }

    if (formData.target_type === 'savings_threshold') {
      if (!formData.monthly_savings_threshold || formData.monthly_savings_threshold <= 0) {
        newErrors.monthly_savings_threshold = 'Monthly savings threshold must be greater than 0';
      }
    } else if (formData.target_type === 'rate_drop_percentage') {
      if (!formData.rate_drop_percentage || formData.rate_drop_percentage <= 0) {
        newErrors.rate_drop_percentage = 'Rate drop percentage must be greater than 0';
      }
    } else if (formData.target_type === 'manual_target') {
      if (!formData.target_rate || formData.target_rate <= 0) {
        newErrors.target_rate = 'Target rate must be greater than 0';
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!validate()) return;

    setLoading(true);
    try {
      // Build payload based on target type
      const payload = {
        mum_client_id: parseInt(formData.mum_client_id),
        target_type: formData.target_type,
        loan_type: formData.loan_type,
        loan_term: formData.loan_term,
        auto_call_enabled: formData.auto_call_enabled,
        call_preference: formData.call_preference,
        notify_email: formData.notify_email,
        notify_sms: formData.notify_sms,
        notify_lo: formData.notify_lo,
        notes: formData.notes || null,
      };

      // Add type-specific field
      if (formData.target_type === 'savings_threshold') {
        payload.monthly_savings_threshold = formData.monthly_savings_threshold;
      } else if (formData.target_type === 'rate_drop_percentage') {
        payload.rate_drop_percentage = formData.rate_drop_percentage;
      } else if (formData.target_type === 'manual_target') {
        payload.target_rate = formData.target_rate;
      }

      await onSave(payload);
    } finally {
      setLoading(false);
    }
  };

  const getSelectedClient = () => {
    return mumClients.find(c => c.id === parseInt(formData.mum_client_id));
  };

  const selectedClient = getSelectedClient();

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="rate-target-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{target ? 'Edit Rate Target' : 'Create Rate Target'}</h2>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            {/* MUM Client Selection */}
            <div className="form-group">
              <label>MUM Client *</label>
              {loadingClients ? (
                <div className="loading-text">Loading clients...</div>
              ) : (
                <select
                  name="mum_client_id"
                  value={formData.mum_client_id}
                  onChange={handleChange}
                  disabled={target !== null}
                  className={errors.mum_client_id ? 'error' : ''}
                >
                  <option value="">Select a client...</option>
                  {mumClients.map(client => (
                    <option key={client.id} value={client.id}>
                      {client.client_name} - {client.interest_rate ? `${client.interest_rate}%` : 'No rate'}
                      {client.current_loan_amount && ` - $${client.current_loan_amount.toLocaleString()}`}
                    </option>
                  ))}
                </select>
              )}
              {errors.mum_client_id && <span className="error-text">{errors.mum_client_id}</span>}
            </div>

            {/* Client Info Display */}
            {selectedClient && (
              <div className="client-info-box">
                <div className="info-item">
                  <span className="label">Current Rate:</span>
                  <span className="value">{selectedClient.interest_rate ? `${selectedClient.interest_rate}%` : 'N/A'}</span>
                </div>
                <div className="info-item">
                  <span className="label">Loan Balance:</span>
                  <span className="value">{selectedClient.current_loan_amount ? `$${selectedClient.current_loan_amount.toLocaleString()}` : 'N/A'}</span>
                </div>
                <div className="info-item">
                  <span className="label">Loan Type:</span>
                  <span className="value">{selectedClient.loan_type || 'N/A'}</span>
                </div>
              </div>
            )}

            {/* Target Type */}
            <div className="form-group">
              <label>Target Type *</label>
              <div className="target-type-options">
                <label className={`type-option ${formData.target_type === 'savings_threshold' ? 'selected' : ''}`}>
                  <input
                    type="radio"
                    name="target_type"
                    value="savings_threshold"
                    checked={formData.target_type === 'savings_threshold'}
                    onChange={handleChange}
                  />
                  <div className="type-content">
                    <div className="type-title">Monthly Savings</div>
                    <div className="type-desc">Alert when potential monthly savings exceeds threshold</div>
                  </div>
                </label>
                <label className={`type-option ${formData.target_type === 'rate_drop_percentage' ? 'selected' : ''}`}>
                  <input
                    type="radio"
                    name="target_type"
                    value="rate_drop_percentage"
                    checked={formData.target_type === 'rate_drop_percentage'}
                    onChange={handleChange}
                  />
                  <div className="type-content">
                    <div className="type-title">Rate Drop %</div>
                    <div className="type-desc">Alert when market rate drops below client rate by X%</div>
                  </div>
                </label>
                <label className={`type-option ${formData.target_type === 'manual_target' ? 'selected' : ''}`}>
                  <input
                    type="radio"
                    name="target_type"
                    value="manual_target"
                    checked={formData.target_type === 'manual_target'}
                    onChange={handleChange}
                  />
                  <div className="type-content">
                    <div className="type-title">Target Rate</div>
                    <div className="type-desc">Alert when market rate hits a specific value</div>
                  </div>
                </label>
              </div>
            </div>

            {/* Threshold Value (dynamic based on type) */}
            <div className="form-group">
              {formData.target_type === 'savings_threshold' && (
                <>
                  <label>Monthly Savings Threshold *</label>
                  <div className="input-with-prefix">
                    <span className="prefix">$</span>
                    <input
                      type="number"
                      name="monthly_savings_threshold"
                      value={formData.monthly_savings_threshold}
                      onChange={handleNumberChange}
                      min="1"
                      step="25"
                      placeholder="200"
                      className={errors.monthly_savings_threshold ? 'error' : ''}
                    />
                    <span className="suffix">/month</span>
                  </div>
                  <span className="help-text">Alert when refinancing could save at least this amount per month</span>
                  {errors.monthly_savings_threshold && <span className="error-text">{errors.monthly_savings_threshold}</span>}
                </>
              )}

              {formData.target_type === 'rate_drop_percentage' && (
                <>
                  <label>Rate Drop Threshold *</label>
                  <div className="input-with-suffix">
                    <input
                      type="number"
                      name="rate_drop_percentage"
                      value={formData.rate_drop_percentage}
                      onChange={handleNumberChange}
                      min="0.125"
                      step="0.125"
                      placeholder="0.5"
                      className={errors.rate_drop_percentage ? 'error' : ''}
                    />
                    <span className="suffix">%</span>
                  </div>
                  <span className="help-text">Alert when market rate is this much below client's current rate</span>
                  {errors.rate_drop_percentage && <span className="error-text">{errors.rate_drop_percentage}</span>}
                </>
              )}

              {formData.target_type === 'manual_target' && (
                <>
                  <label>Target Rate *</label>
                  <div className="input-with-suffix">
                    <input
                      type="number"
                      name="target_rate"
                      value={formData.target_rate}
                      onChange={handleNumberChange}
                      min="0.1"
                      step="0.125"
                      placeholder="6.0"
                      className={errors.target_rate ? 'error' : ''}
                    />
                    <span className="suffix">%</span>
                  </div>
                  <span className="help-text">Alert when market rate reaches or drops below this rate</span>
                  {errors.target_rate && <span className="error-text">{errors.target_rate}</span>}
                </>
              )}
            </div>

            {/* Loan Parameters */}
            <div className="form-row">
              <div className="form-group half">
                <label>Loan Type</label>
                <select name="loan_type" value={formData.loan_type} onChange={handleChange}>
                  <option value="conventional">Conventional</option>
                  <option value="fha">FHA</option>
                  <option value="va">VA</option>
                  <option value="usda">USDA</option>
                  <option value="jumbo">Jumbo</option>
                </select>
              </div>
              <div className="form-group half">
                <label>Loan Term</label>
                <select name="loan_term" value={formData.loan_term} onChange={handleChange}>
                  <option value={15}>15 Year</option>
                  <option value={20}>20 Year</option>
                  <option value={30}>30 Year</option>
                </select>
              </div>
            </div>

            {/* AI Call Settings */}
            <div className="form-section">
              <h3>AI Receptionist Settings</h3>
              <div className="form-group">
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    name="auto_call_enabled"
                    checked={formData.auto_call_enabled}
                    onChange={handleChange}
                  />
                  <span>Enable automatic AI calls when target is triggered</span>
                </label>
              </div>

              {formData.auto_call_enabled && (
                <div className="form-group">
                  <label>Call Preference</label>
                  <select name="call_preference" value={formData.call_preference} onChange={handleChange}>
                    <option value="business_hours">Business Hours (8am-6pm weekdays)</option>
                    <option value="mornings">Mornings Only (8am-12pm)</option>
                    <option value="afternoons">Afternoons Only (12pm-6pm)</option>
                    <option value="evenings">Evenings (5pm-8pm)</option>
                    <option value="weekdays_only">Weekdays Extended (8am-8pm)</option>
                    <option value="any_time">Any Time (8am-8pm daily)</option>
                  </select>
                </div>
              )}
            </div>

            {/* Notification Settings */}
            <div className="form-section">
              <h3>Notifications</h3>
              <div className="checkbox-group">
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    name="notify_email"
                    checked={formData.notify_email}
                    onChange={handleChange}
                  />
                  <span>Email notification</span>
                </label>
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    name="notify_sms"
                    checked={formData.notify_sms}
                    onChange={handleChange}
                  />
                  <span>SMS notification</span>
                </label>
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    name="notify_lo"
                    checked={formData.notify_lo}
                    onChange={handleChange}
                  />
                  <span>Notify Loan Officer</span>
                </label>
              </div>
            </div>

            {/* Notes */}
            <div className="form-group">
              <label>Notes (optional)</label>
              <textarea
                name="notes"
                value={formData.notes}
                onChange={handleChange}
                rows={3}
                placeholder="Any additional notes about this rate target..."
              />
            </div>
          </div>

          <div className="modal-footer">
            <button type="button" className="btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={loading}>
              {loading ? 'Saving...' : (target ? 'Update Target' : 'Create Target')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default RateTargetModal;
