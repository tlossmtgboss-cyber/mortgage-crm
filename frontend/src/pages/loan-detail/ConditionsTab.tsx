/**
 * Conditions tab -- Track and manage loan conditions / needs list.
 */
import React from 'react';
import type { Condition, NewCondition } from './types';

interface ConditionsTabProps {
  conditions: Condition[];
  conditionsLoading: boolean;
  showAddConditionModal: boolean;
  setShowAddConditionModal: (show: boolean) => void;
  newCondition: NewCondition;
  setNewCondition: (condition: NewCondition) => void;
  addingCondition: boolean;
  handleAddCondition: (e: React.FormEvent) => void;
  updateConditionStatus: (conditionId: number, newStatus: string) => void;
}

export default function ConditionsTab({
  conditions,
  conditionsLoading,
  showAddConditionModal,
  setShowAddConditionModal,
  newCondition,
  setNewCondition,
  addingCondition,
  handleAddCondition,
  updateConditionStatus,
}: ConditionsTabProps) {
  return (
    <div className="info-section">
      <h2>Conditions</h2>
      <div className="conditions-content">
        <p className="circle-description">
          Track and manage loan conditions. Items added here will appear in the client portal's
          Needs List. Clients will be notified when new conditions are requested.
        </p>

        <div className="conditions-header-actions">
          <button
            className="btn-add-condition"
            onClick={() => setShowAddConditionModal(true)}
          >
            + Add Condition
          </button>
          <div className="conditions-summary">
            <span className="condition-count pending">
              {conditions.filter(c => c.status === 'pending').length} Pending
            </span>
            <span className="condition-count received">
              {conditions.filter(c => c.status === 'received').length} Received
            </span>
            <span className="condition-count approved">
              {conditions.filter(c => c.status === 'approved').length} Approved
            </span>
          </div>
        </div>

        {conditionsLoading ? (
          <div className="loading-state">Loading conditions...</div>
        ) : conditions.length === 0 ? (
          <div className="empty-conditions">
            <div className="empty-icon">📋</div>
            <h3>No Conditions Yet</h3>
            <p>When the applicant completes their application, the needs list will be populated automatically.</p>
            <p>You can also manually add conditions using the button above.</p>
          </div>
        ) : (
          <div className="conditions-list">
            {conditions.map(condition => (
              <div key={condition.id} className={`condition-item status-${condition.status}`}>
                <div className="condition-checkbox">
                  <input
                    type="checkbox"
                    checked={condition.status === 'approved'}
                    onChange={() => updateConditionStatus(
                      condition.id,
                      condition.status === 'approved' ? 'pending' : 'approved'
                    )}
                  />
                </div>
                <div className="condition-info">
                  <div className="condition-name">
                    {condition.name}
                    {condition.is_new && <span className="new-badge">NEW</span>}
                  </div>
                  {condition.description && (
                    <div className="condition-description">{condition.description}</div>
                  )}
                  <div className="condition-meta">
                    <span className="condition-category">{condition.category?.replace(/_/g, ' ')}</span>
                    {condition.due_date && (
                      <span className="condition-due">Due: {new Date(condition.due_date).toLocaleDateString()}</span>
                    )}
                    <span className={`condition-priority priority-${condition.priority}`}>
                      {condition.priority}
                    </span>
                  </div>
                </div>
                <div className="condition-status">
                  <select
                    value={condition.status}
                    onChange={(e) => updateConditionStatus(condition.id, e.target.value)}
                    className={`status-select status-${condition.status}`}
                  >
                    <option value="pending">Pending</option>
                    <option value="requested">Requested</option>
                    <option value="received">Received</option>
                    <option value="approved">Approved</option>
                    <option value="waived">Waived</option>
                  </select>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Add Condition Modal */}
        {showAddConditionModal && (
          <div className="modal-overlay" onClick={() => setShowAddConditionModal(false)}>
            <div className="modal-content condition-modal" onClick={e => e.stopPropagation()}>
              <div className="modal-header">
                <h3>Add Condition</h3>
                <button className="modal-close" onClick={() => setShowAddConditionModal(false)}>&times;</button>
              </div>
              <form onSubmit={handleAddCondition}>
                <div className="modal-body">
                  <div className="form-group">
                    <label>Condition Name *</label>
                    <input
                      type="text"
                      value={newCondition.name}
                      onChange={(e) => setNewCondition({...newCondition, name: e.target.value})}
                      placeholder="e.g., Most Recent Pay Stub"
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label>Description</label>
                    <textarea
                      value={newCondition.description}
                      onChange={(e) => setNewCondition({...newCondition, description: e.target.value})}
                      placeholder="Additional details or instructions for the client"
                      rows={3}
                    />
                  </div>
                  <div className="form-row">
                    <div className="form-group">
                      <label>Category</label>
                      <select
                        value={newCondition.category}
                        onChange={(e) => setNewCondition({...newCondition, category: e.target.value})}
                      >
                        <option value="income_verification">Income Verification</option>
                        <option value="asset_verification">Asset Verification</option>
                        <option value="employment_verification">Employment Verification</option>
                        <option value="credit_documentation">Credit Documentation</option>
                        <option value="property_documentation">Property Documentation</option>
                        <option value="identity_verification">Identity Verification</option>
                        <option value="other">Other</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label>Priority</label>
                      <select
                        value={newCondition.priority}
                        onChange={(e) => setNewCondition({...newCondition, priority: e.target.value})}
                      >
                        <option value="required">Required</option>
                        <option value="recommended">Recommended</option>
                        <option value="optional">Optional</option>
                      </select>
                    </div>
                  </div>
                  <div className="form-group">
                    <label>Due Date</label>
                    <input
                      type="date"
                      value={newCondition.due_date}
                      onChange={(e) => setNewCondition({...newCondition, due_date: e.target.value})}
                    />
                  </div>
                  <div className="form-group notification-toggle">
                    <label className="toggle-label">
                      <input type="checkbox" defaultChecked />
                      <span>Notify client via email and portal</span>
                    </label>
                  </div>
                </div>
                <div className="modal-footer">
                  <button type="button" className="btn-secondary" onClick={() => setShowAddConditionModal(false)}>
                    Cancel
                  </button>
                  <button type="submit" className="btn-primary" disabled={addingCondition}>
                    {addingCondition ? 'Adding...' : 'Add Condition'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
