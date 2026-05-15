import React, { useState, useEffect, useCallback } from 'react';
import './CategoryTasksModal.css';
import { getToken } from '../utils/tokenStore';

const API_BASE = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

// Map role_id to responsibility field keys
const ROLE_TO_RESPONSIBILITY_FIELD = {
  1: 'lo_responsible',           // Loan Officer
  2: 'jr_lo_responsible',        // Jr. Loan Officer
  3: 'production_asst_responsible', // Loan Officer Assistant
  4: 'production_asst_responsible', // Application Analyst
  5: 'production_asst_responsible', // Processor
  6: 'production_asst_responsible', // Processing Assistant
  7: 'production_asst_responsible', // Production Assistant 1
  8: 'production_asst_responsible', // Production Assistant 2
  9: 'concierge_responsible',    // Concierge
  10: 'production_asst_responsible', // Closer
  11: 'production_asst_responsible', // Underwriter
  12: 'lo_responsible',          // Team Lead
  13: 'lo_responsible',          // Branch Manager
  14: 'lo_responsible',          // Area Manager
  15: 'lo_responsible'           // Regional Manager
};

// Friendly role labels
const ROLE_LABELS = {
  'lo_responsible': 'Loan Officer',
  'jr_lo_responsible': 'Jr. Loan Officer',
  'production_asst_responsible': 'Production Assistant',
  'concierge_responsible': 'Concierge',
  'ai_responsible': 'AI'
};

function CategoryTasksModal({ isOpen, onClose, category, selectedRoleId, onTasksChange }) {
  const [workflowDays, setWorkflowDays] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  // Determine which responsibility field to filter by
  const responsibilityField = ROLE_TO_RESPONSIBILITY_FIELD[selectedRoleId] || 'lo_responsible';
  const roleName = ROLE_LABELS[responsibilityField] || 'Team Member';

  const fetchWorkflowTasks = useCallback(async () => {
    if (!category?.workflow_key) {
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      const token = getToken();
      const headers = { 'Authorization': `Bearer ${token}` };

      // Fetch workflow configuration for this category
      const response = await fetch(
        `${API_BASE}/api/v1/workflow-config/workflows/${category.workflow_key}`,
        { headers }
      );

      if (response.ok) {
        const data = await response.json();
        // Filter days where the selected role has responsibility
        const filteredDays = (data.days || []).filter(day => day[responsibilityField]);
        setWorkflowDays(filteredDays);
      } else if (response.status === 404) {
        // Workflow doesn't exist yet - show empty state
        setWorkflowDays([]);
      } else {
        throw new Error('Failed to fetch workflow tasks');
      }
      setError(null);
    } catch (err) {
      console.error('Error fetching workflow tasks:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [category?.workflow_key, responsibilityField]);

  useEffect(() => {
    if (isOpen && category) {
      fetchWorkflowTasks();
    }
  }, [isOpen, category, fetchWorkflowTasks]);

  // Toggle task responsibility for a day
  const toggleTaskResponsibility = async (dayId) => {
    const day = workflowDays.find(d => d.id === dayId);
    if (!day) return;

    const newValue = !day[responsibilityField];

    try {
      setSaving(true);
      const token = getToken();
      const response = await fetch(
        `${API_BASE}/api/v1/workflow-config/workflows/${category.workflow_key}/days/${dayId}`,
        {
          method: 'PUT',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ [responsibilityField]: newValue })
        }
      );

      if (response.ok) {
        // Update local state
        setWorkflowDays(prev => prev.map(d =>
          d.id === dayId ? { ...d, [responsibilityField]: newValue } : d
        ));

        // If removing responsibility, filter it out
        if (!newValue) {
          setWorkflowDays(prev => prev.filter(d => d.id !== dayId));
        }

        // Notify parent of change
        if (onTasksChange) {
          onTasksChange();
        }
      }
    } catch (err) {
      console.error('Error updating task responsibility:', err);
    } finally {
      setSaving(false);
    }
  };

  // Add a task from available tasks
  const addTask = async (day) => {
    try {
      setSaving(true);
      const token = getToken();
      const response = await fetch(
        `${API_BASE}/api/v1/workflow-config/workflows/${category.workflow_key}/days/${day.id}`,
        {
          method: 'PUT',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ [responsibilityField]: true })
        }
      );

      if (response.ok) {
        // Refresh to get the updated day
        fetchWorkflowTasks();

        if (onTasksChange) {
          onTasksChange();
        }
      }
    } catch (err) {
      console.error('Error adding task:', err);
    } finally {
      setSaving(false);
    }
  };

  // Get communication methods as badges
  const getCommunicationBadges = (day) => {
    const badges = [];
    if (day.phone_enabled) badges.push({ key: 'phone', label: 'Phone', color: '#3b82f6' });
    if (day.text_enabled) badges.push({ key: 'text', label: 'Text', color: '#2D7A52' });
    if (day.email_enabled) badges.push({ key: 'email', label: 'Email', color: '#f59e0b' });
    if (day.referral_partner_enabled) badges.push({ key: 'referral', label: 'Referral', color: '#ec4899' });
    return badges;
  };

  if (!isOpen) return null;

  return (
    <div className="category-tasks-modal-overlay" onClick={onClose}>
      <div className="category-tasks-modal" onClick={(e) => e.stopPropagation()}>
        <div className="category-tasks-header">
          <div className="header-content">
            <h2>{category?.display_name} Tasks</h2>
            <p className="header-subtitle">
              Tasks assigned to <strong>{roleName}</strong> for this category
            </p>
          </div>
          <button className="modal-close-btn" onClick={onClose}>×</button>
        </div>

        <div className="category-tasks-body">
          {loading ? (
            <div className="loading-state">
              <div className="spinner"></div>
              <p>Loading tasks...</p>
            </div>
          ) : error ? (
            <div className="error-state">
              <p>{error}</p>
              <button onClick={fetchWorkflowTasks}>Retry</button>
            </div>
          ) : workflowDays.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">📋</div>
              <h3>No Tasks Assigned</h3>
              <p>
                No workflow tasks are currently assigned to {roleName} for {category?.display_name}.
                Tasks can be configured in the Workflow Configuration editor.
              </p>
            </div>
          ) : (
            <div className="tasks-list">
              <div className="tasks-header-row">
                <span className="task-header-status">Status</span>
                <span className="task-header-day">Task Day</span>
                <span className="task-header-methods">Communication Methods</span>
                <span className="task-header-actions">Actions</span>
              </div>

              {workflowDays.map(day => (
                <div key={day.id} className={`task-row ${day.is_disabled ? 'disabled' : ''}`}>
                  <div className="task-status">
                    <span
                      className={`status-indicator ${day.has_issues ? 'has-issues' : day.is_disabled ? 'disabled' : 'active'}`}
                      title={day.has_issues ? 'Has issues' : day.is_disabled ? 'Disabled' : 'Active'}
                    ></span>
                  </div>

                  <div className="task-day">
                    <span className="day-label">{day.day_label}</span>
                    <span className="day-value">({day.day_value} days)</span>
                  </div>

                  <div className="task-methods">
                    {getCommunicationBadges(day).map(badge => (
                      <span
                        key={badge.key}
                        className="method-badge"
                        style={{ backgroundColor: badge.color }}
                      >
                        {badge.label}
                      </span>
                    ))}
                    {getCommunicationBadges(day).length === 0 && (
                      <span className="no-methods">No methods set</span>
                    )}
                  </div>

                  <div className="task-actions">
                    <button
                      className="btn-remove-task"
                      onClick={() => toggleTaskResponsibility(day.id)}
                      disabled={saving}
                      title="Remove this task from your responsibilities"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="category-tasks-footer">
          <span className="task-count">
            {workflowDays.length} task{workflowDays.length !== 1 ? 's' : ''} assigned
          </span>
          <div className="footer-actions">
            <button className="btn-secondary" onClick={onClose}>
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default CategoryTasksModal;
