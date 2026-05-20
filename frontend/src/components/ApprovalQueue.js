import React, { useState, useEffect, useCallback } from 'react';
import { API_BASE_URL } from '../services/api';
import { getToken } from '../utils/tokenStore';
import { toast } from '../utils/toast';
import './ApprovalQueue.css';

function ApprovalQueue({ embedded = false }) {
  const [actions, setActions] = useState([]);
  const [total, setTotal] = useState(0);
  const [graduation, setGraduation] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [processingIds, setProcessingIds] = useState(new Set());
  const [filterType, setFilterType] = useState('');
  const [lastUpdated, setLastUpdated] = useState(null);

  const fetchPendingActions = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    const headers = { 'Authorization': `Bearer ${token}` };

    try {
      const params = new URLSearchParams({ limit: '50', offset: '0' });
      if (filterType) params.set('action_type', filterType);

      const res = await fetch(
        `${API_BASE_URL}/api/v1/autonomous/actions/pending?${params}`,
        { headers }
      );

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setActions(data.actions || []);
      setTotal(data.total || 0);
      setError(null);
    } catch (err) {
      console.error('Failed to fetch pending actions:', err);
      setError('Failed to load pending actions');
    }
  }, [filterType]);

  const fetchGraduation = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    const headers = { 'Authorization': `Bearer ${token}` };

    try {
      const res = await fetch(
        `${API_BASE_URL}/api/v1/autonomous/confidence`,
        { headers }
      );
      if (res.ok) {
        const data = await res.json();
        setGraduation(data);
      }
    } catch (err) {
      console.error('Failed to fetch confidence data:', err);
    }
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    await Promise.all([fetchPendingActions(), fetchGraduation()]);
    setLastUpdated(new Date());
    setLoading(false);
  }, [fetchPendingActions, fetchGraduation]);

  // Initial load + auto-refresh every 30 seconds
  useEffect(() => {
    loadAll();
    const interval = setInterval(loadAll, 30 * 1000);
    return () => clearInterval(interval);
  }, [loadAll]);

  const handleApprove = async (actionId) => {
    const token = getToken();
    if (!token) return;

    setProcessingIds((prev) => new Set(prev).add(actionId));

    try {
      const res = await fetch(
        `${API_BASE_URL}/api/v1/autonomous/actions/${actionId}/approve`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        }
      );

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP ${res.status}`);
      }

      const result = await res.json();
      const replayNote = result.replayed
        ? 'Action executed successfully.'
        : 'Approved but replay did not complete — check agent logs.';
      toast.success(`Approved: ${replayNote}`);

      // Remove from list
      setActions((prev) => prev.filter((a) => a.id !== actionId));
      setTotal((prev) => Math.max(0, prev - 1));
    } catch (err) {
      console.error('Approve failed:', err);
      toast.error(`Failed to approve: ${err.message}`);
    } finally {
      setProcessingIds((prev) => {
        const next = new Set(prev);
        next.delete(actionId);
        return next;
      });
    }
  };

  const handleReject = async (actionId) => {
    const token = getToken();
    if (!token) return;

    setProcessingIds((prev) => new Set(prev).add(actionId));

    try {
      const res = await fetch(
        `${API_BASE_URL}/api/v1/autonomous/actions/${actionId}/reject`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        }
      );

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `HTTP ${res.status}`);
      }

      toast.info('Action rejected.');
      setActions((prev) => prev.filter((a) => a.id !== actionId));
      setTotal((prev) => Math.max(0, prev - 1));
    } catch (err) {
      console.error('Reject failed:', err);
      toast.error(`Failed to reject: ${err.message}`);
    } finally {
      setProcessingIds((prev) => {
        const next = new Set(prev);
        next.delete(actionId);
        return next;
      });
    }
  };

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'N/A';
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffMins < 1440) return `${Math.floor(diffMins / 60)}h ago`;
    return date.toLocaleDateString();
  };

  const getActionTypeLabel = (type) => {
    if (!type) return 'Unknown';
    return type
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (c) => c.toUpperCase());
  };

  const getActionTypeIcon = (type) => {
    const icons = {
      send_email: '✉️',
      update_lead: '✏️',
      create_task: '✅',
      schedule_call: '📞',
      move_stage: '➡️',
      generate_content: '📝',
    };
    return icons[type] || '⚙️';
  };

  // Collect unique action types for filter dropdown
  const actionTypes = [...new Set(actions.map((a) => a.action_type).filter(Boolean))];

  // ------- Render -------

  if (loading && actions.length === 0) {
    return (
      <div className={`approval-queue ${embedded ? 'embedded' : ''}`}>
        <div className="aq-loading">
          <div className="aq-spinner"></div>
          <p>Loading pending actions...</p>
        </div>
      </div>
    );
  }

  if (error && actions.length === 0) {
    return (
      <div className={`approval-queue ${embedded ? 'embedded' : ''}`}>
        <div className="aq-error">
          <p>{error}</p>
          <button className="aq-btn aq-btn-retry" onClick={loadAll}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={`approval-queue ${embedded ? 'embedded' : ''}`}>
      {/* Header */}
      {!embedded && (
        <div className="aq-page-header">
          <div>
            <h1>Approval Queue</h1>
            <p>Review and approve AI-proposed actions before they execute</p>
          </div>
          <div className="aq-header-actions">
            {lastUpdated && (
              <span className="aq-last-updated">
                Updated {formatTimestamp(lastUpdated)}
              </span>
            )}
            <button className="aq-btn aq-btn-refresh" onClick={loadAll}>
              Refresh
            </button>
          </div>
        </div>
      )}

      {/* Summary strip */}
      <div className="aq-summary-strip">
        <div className="aq-summary-card aq-pending">
          <div className="aq-summary-value">{total}</div>
          <div className="aq-summary-label">
            {total === 1 ? 'action pending approval' : 'actions pending approval'}
          </div>
        </div>

        {graduation && graduation.action_types && (
          <>
            <div className="aq-summary-card">
              <div className="aq-summary-value">
                {Object.keys(graduation.action_types).length}
              </div>
              <div className="aq-summary-label">Action types tracked</div>
            </div>
            <div className="aq-summary-card">
              <div className="aq-summary-value">
                {Object.values(graduation.action_types).filter(
                  (at) => at.current_level === 'autonomous'
                ).length}
              </div>
              <div className="aq-summary-label">Graduated to autonomous</div>
            </div>
          </>
        )}
      </div>

      {/* Confidence graduation progress */}
      {graduation && graduation.action_types && Object.keys(graduation.action_types).length > 0 && (
        <div className="aq-graduation-section">
          <h3>Confidence Graduation Progress</h3>
          <div className="aq-graduation-grid">
            {Object.entries(graduation.action_types).map(([actionType, info]) => {
              const level = info.current_level || 'manual';
              const confidence = info.confidence_score || 0;
              const threshold = info.graduation_threshold || 80;
              const progressPct = Math.min(100, (confidence / threshold) * 100);

              return (
                <div key={actionType} className={`aq-graduation-card level-${level}`}>
                  <div className="aq-grad-header">
                    <span className="aq-grad-type">{getActionTypeLabel(actionType)}</span>
                    <span className={`aq-grad-level level-${level}`}>
                      {level === 'autonomous' ? 'Autonomous' :
                       level === 'supervised' ? 'Supervised' : 'Manual'}
                    </span>
                  </div>
                  <div className="aq-progress-bar">
                    <div
                      className="aq-progress-fill"
                      style={{ width: `${progressPct}%` }}
                    />
                  </div>
                  <div className="aq-grad-stats">
                    <span>Confidence: {confidence.toFixed(0)}%</span>
                    <span>Threshold: {threshold}%</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Filter */}
      {actionTypes.length > 1 && (
        <div className="aq-filter-bar">
          <label htmlFor="aq-filter-type">Filter by type:</label>
          <select
            id="aq-filter-type"
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
          >
            <option value="">All types</option>
            {actionTypes.map((t) => (
              <option key={t} value={t}>
                {getActionTypeLabel(t)}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Action list */}
      {actions.length === 0 ? (
        <div className="aq-empty-state">
          <div className="aq-empty-icon">&#10003;</div>
          <h3>No pending actions</h3>
          <p>
            AI is either auto-handling everything or hasn't proposed any actions yet.
          </p>
        </div>
      ) : (
        <div className="aq-actions-list">
          {actions.map((action) => {
            const isProcessing = processingIds.has(action.id);
            return (
              <div key={action.id} className="aq-action-card">
                <div className="aq-action-header">
                  <div className="aq-action-meta">
                    <span className="aq-action-icon">
                      {getActionTypeIcon(action.action_type)}
                    </span>
                    <span className="aq-action-type">
                      {getActionTypeLabel(action.action_type)}
                    </span>
                    {action.target_entity && (
                      <span className="aq-action-target">
                        {action.target_entity}
                        {action.target_id ? ` #${action.target_id}` : ''}
                      </span>
                    )}
                    <span className="aq-action-time">
                      {formatTimestamp(action.created_at)}
                    </span>
                  </div>
                </div>

                {action.description && (
                  <div className="aq-action-description">{action.description}</div>
                )}

                {action.payload && (
                  <details className="aq-action-payload">
                    <summary>View payload</summary>
                    <pre>{JSON.stringify(action.payload, null, 2)}</pre>
                  </details>
                )}

                <div className="aq-action-buttons">
                  <button
                    className="aq-btn aq-btn-approve"
                    onClick={() => handleApprove(action.id)}
                    disabled={isProcessing}
                  >
                    {isProcessing ? 'Processing...' : 'Approve'}
                  </button>
                  <button
                    className="aq-btn aq-btn-reject"
                    onClick={() => handleReject(action.id)}
                    disabled={isProcessing}
                  >
                    {isProcessing ? 'Processing...' : 'Reject'}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default ApprovalQueue;
