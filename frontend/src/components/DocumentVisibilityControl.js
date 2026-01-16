import React, { useState, useEffect } from 'react';
import './DocumentVisibilityControl.css';

const API_BASE = process.env.REACT_APP_API_BASE || '';

/**
 * DocumentVisibilityControl - Control document visibility to portals
 *
 * Supports three modes:
 * - Full: Complete visibility controls with release settings
 * - Compact: Inline toggles for table rows
 * - Badge: Status display only
 */
function DocumentVisibilityControl({
  documentTable = 'perennia_documents',
  documentId,
  loanId,
  initialVisibility = null,
  mode = 'full', // 'full', 'compact', 'badge'
  onUpdate = null,
  showPartner = true,
  readOnly = false,
}) {
  const [visibility, setVisibility] = useState({
    visible_to_borrower: true,
    visible_to_partner: true,
    visible_to_internal: true,
    release_mode: 'manual',
    release_milestone: null,
    release_at: null,
    hidden_reason: '',
    visibility_locked: false,
  });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [hasChanges, setHasChanges] = useState(false);

  // Loan milestones for auto-release
  const milestones = [
    { value: 'clear_to_close', label: 'Clear to Close' },
    { value: 'docs_out', label: 'Docs Out' },
    { value: 'docs_back', label: 'Docs Back' },
    { value: 'funded', label: 'Funded' },
    { value: 'closed', label: 'Closed' },
  ];

  // Load visibility on mount
  useEffect(() => {
    if (initialVisibility) {
      setVisibility(prev => ({ ...prev, ...initialVisibility }));
    } else if (documentId) {
      loadVisibility();
    }
  }, [documentId, initialVisibility]);

  const loadVisibility = async () => {
    if (!documentId || !loanId) return;

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `${API_BASE}/api/v1/documents/${documentTable}/${documentId}/visibility?loan_id=${loanId}`
      );

      if (response.ok) {
        const data = await response.json();
        setVisibility(prev => ({
          ...prev,
          visible_to_borrower: data.visible_to_borrower ?? true,
          visible_to_partner: data.visible_to_partner ?? true,
          visible_to_internal: data.visible_to_internal ?? true,
          release_mode: data.release_mode || 'manual',
          release_milestone: data.release_milestone || null,
          release_at: data.release_at || null,
          hidden_reason: data.hidden_reason || '',
          visibility_locked: data.visibility_locked || false,
        }));
      }
    } catch (err) {
      console.error('Failed to load visibility:', err);
      setError('Failed to load visibility settings');
    } finally {
      setLoading(false);
    }
  };

  const saveVisibility = async () => {
    if (!documentId || !loanId) return;

    setSaving(true);
    setError(null);

    try {
      const response = await fetch(
        `${API_BASE}/api/v1/documents/${documentTable}/${documentId}/visibility?loan_id=${loanId}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            visible_to_borrower: visibility.visible_to_borrower,
            visible_to_partner: visibility.visible_to_partner,
            visible_to_internal: visibility.visible_to_internal,
            release_mode: visibility.release_mode,
            release_milestone: visibility.release_milestone,
            release_at: visibility.release_at,
            hidden_reason: visibility.hidden_reason,
            visibility_locked: visibility.visibility_locked,
          }),
        }
      );

      if (response.ok) {
        const data = await response.json();
        setHasChanges(false);
        if (onUpdate) {
          onUpdate(data.visibility);
        }
      } else {
        throw new Error('Failed to save');
      }
    } catch (err) {
      console.error('Failed to save visibility:', err);
      setError('Failed to save visibility settings');
    } finally {
      setSaving(false);
    }
  };

  const handleToggle = async (field) => {
    if (readOnly || visibility.visibility_locked) return;

    const newValue = !visibility[field];
    setVisibility(prev => ({ ...prev, [field]: newValue }));
    setHasChanges(true);

    // For compact mode, save immediately
    if (mode === 'compact' && documentId && loanId) {
      try {
        const response = await fetch(
          `${API_BASE}/api/v1/documents/${documentTable}/${documentId}/visibility?loan_id=${loanId}`,
          {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ [field]: newValue }),
          }
        );

        if (response.ok && onUpdate) {
          const data = await response.json();
          onUpdate(data.visibility);
        }
      } catch (err) {
        console.error('Failed to update visibility:', err);
        // Revert on error
        setVisibility(prev => ({ ...prev, [field]: !newValue }));
      }
    }
  };

  const handleReleaseModeChange = (e) => {
    const newMode = e.target.value;
    setVisibility(prev => ({
      ...prev,
      release_mode: newMode,
      release_milestone: newMode === 'milestone' ? prev.release_milestone : null,
      release_at: newMode === 'datetime' ? prev.release_at : null,
    }));
    setHasChanges(true);
  };

  const handleMilestoneChange = (e) => {
    setVisibility(prev => ({ ...prev, release_milestone: e.target.value }));
    setHasChanges(true);
  };

  const handleReasonChange = (e) => {
    setVisibility(prev => ({ ...prev, hidden_reason: e.target.value }));
    setHasChanges(true);
  };

  const handleLockChange = (e) => {
    setVisibility(prev => ({ ...prev, visibility_locked: e.target.checked }));
    setHasChanges(true);
  };

  // Badge mode - just show status
  if (mode === 'badge') {
    const isHidden = !visibility.visible_to_borrower;
    const isScheduled = isHidden && visibility.release_mode === 'milestone';

    if (!isHidden) return null;

    return (
      <span className={`visibility-status-badge ${isScheduled ? 'scheduled' : 'hidden'}`}>
        {isScheduled ? (
          <>
            <span>Releases at: {visibility.release_milestone}</span>
          </>
        ) : (
          <>
            <span>Hidden</span>
          </>
        )}
      </span>
    );
  }

  // Compact mode - inline toggles
  if (mode === 'compact') {
    return (
      <div className="visibility-inline-toggle">
        <div
          className="toggle-item visibility-tooltip"
          onClick={() => handleToggle('visible_to_borrower')}
        >
          <span className={`toggle-icon ${visibility.visible_to_borrower ? 'visible' : 'hidden'}`}>
            {visibility.visible_to_borrower ? '👁️' : '🚫'}
          </span>
          <span className="tooltip-content">
            {visibility.visible_to_borrower ? 'Visible to Borrower' : 'Hidden from Borrower'}
          </span>
        </div>
        {showPartner && (
          <div
            className="toggle-item visibility-tooltip"
            onClick={() => handleToggle('visible_to_partner')}
          >
            <span className={`toggle-icon ${visibility.visible_to_partner ? 'visible' : 'hidden'}`}>
              {visibility.visible_to_partner ? '🤝' : '⛔'}
            </span>
            <span className="tooltip-content">
              {visibility.visible_to_partner ? 'Visible to Partner' : 'Hidden from Partner'}
            </span>
          </div>
        )}
      </div>
    );
  }

  // Full mode - complete control panel
  if (loading) {
    return (
      <div className="document-visibility-control">
        <div className="visibility-loading">
          <div className="spinner"></div>
          Loading visibility settings...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="document-visibility-control">
        <div className="visibility-error">{error}</div>
      </div>
    );
  }

  const isHidden = !visibility.visible_to_borrower || !visibility.visible_to_partner;

  return (
    <div className="document-visibility-control">
      <div className="visibility-header">
        <span className="icon">{isHidden ? '🔒' : '🔓'}</span>
        Document Visibility
      </div>

      <div className="visibility-toggles">
        {/* Borrower Toggle */}
        <div className="visibility-toggle-row">
          <div className="toggle-label">
            <span className="role-icon">👤</span>
            <span>Visible to Borrower Portal</span>
          </div>
          <div
            className={`toggle-switch ${visibility.visible_to_borrower ? 'active' : ''} ${readOnly || visibility.visibility_locked ? 'disabled' : ''}`}
            onClick={() => handleToggle('visible_to_borrower')}
          >
            <div className="toggle-knob"></div>
          </div>
        </div>

        {/* Partner Toggle */}
        {showPartner && (
          <div className="visibility-toggle-row">
            <div className="toggle-label">
              <span className="role-icon">🤝</span>
              <span>Visible to Partner Portal</span>
            </div>
            <div
              className={`toggle-switch ${visibility.visible_to_partner ? 'active' : ''} ${readOnly || visibility.visibility_locked ? 'disabled' : ''}`}
              onClick={() => handleToggle('visible_to_partner')}
            >
              <div className="toggle-knob"></div>
            </div>
          </div>
        )}
      </div>

      {/* Release Settings - only show when document is hidden */}
      {isHidden && (
        <div className="release-settings">
          <h4>Auto-Release Settings</h4>

          <select
            className="release-mode-select"
            value={visibility.release_mode}
            onChange={handleReleaseModeChange}
            disabled={readOnly}
          >
            <option value="manual">Manual Release Only</option>
            <option value="milestone">Release on Milestone</option>
            <option value="datetime">Release at Date/Time</option>
          </select>

          {visibility.release_mode === 'milestone' && (
            <select
              className="release-mode-select milestone-select"
              value={visibility.release_milestone || ''}
              onChange={handleMilestoneChange}
              disabled={readOnly}
            >
              <option value="">Select milestone...</option>
              {milestones.map(m => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </select>
          )}

          {visibility.release_mode === 'datetime' && (
            <input
              type="datetime-local"
              className="release-mode-select milestone-select"
              value={visibility.release_at || ''}
              onChange={(e) => {
                setVisibility(prev => ({ ...prev, release_at: e.target.value }));
                setHasChanges(true);
              }}
              disabled={readOnly}
            />
          )}

          <div className="hidden-reason">
            <label>Reason for Hiding (optional)</label>
            <textarea
              value={visibility.hidden_reason}
              onChange={handleReasonChange}
              placeholder="e.g., Contains sensitive closing costs..."
              disabled={readOnly}
            />
          </div>

          <div className="lock-toggle">
            <input
              type="checkbox"
              id="visibility-lock"
              checked={visibility.visibility_locked}
              onChange={handleLockChange}
              disabled={readOnly}
            />
            <label htmlFor="visibility-lock">
              Lock visibility (prevent auto-release from changing)
            </label>
          </div>
        </div>
      )}

      {/* Action Buttons */}
      {!readOnly && hasChanges && (
        <div className="visibility-actions">
          <button
            className="cancel-btn"
            onClick={loadVisibility}
            disabled={saving}
          >
            Cancel
          </button>
          <button
            className="save-btn"
            onClick={saveVisibility}
            disabled={saving}
          >
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * Quick toggle button for document lists
 */
export function VisibilityToggleButton({
  visible,
  onClick,
  type = 'borrower',
  disabled = false
}) {
  const icons = {
    borrower: { visible: '👁️', hidden: '🚫' },
    partner: { visible: '🤝', hidden: '⛔' },
  };

  const labels = {
    borrower: { visible: 'Visible to Borrower', hidden: 'Hidden from Borrower' },
    partner: { visible: 'Visible to Partner', hidden: 'Hidden from Partner' },
  };

  return (
    <div
      className={`toggle-item visibility-tooltip ${disabled ? 'disabled' : ''}`}
      onClick={disabled ? undefined : onClick}
      style={{ cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.5 : 1 }}
    >
      <span className={`toggle-icon ${visible ? 'visible' : 'hidden'}`}>
        {visible ? icons[type].visible : icons[type].hidden}
      </span>
      <span className="tooltip-content">
        {visible ? labels[type].visible : labels[type].hidden}
      </span>
    </div>
  );
}

export default DocumentVisibilityControl;
