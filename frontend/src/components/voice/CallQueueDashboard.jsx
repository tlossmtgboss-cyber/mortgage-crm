// Call Queue Dashboard - Manage and monitor call queues
import React, { useState, useEffect, useCallback } from 'react';
import './CallQueueDashboard.css';
import { toast } from '../../utils/toast';

const CallQueueDashboard = () => {
  const [queues, setQueues] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedQueue, setSelectedQueue] = useState(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [refreshInterval, setRefreshInterval] = useState(null);

  const API_BASE_URL = typeof window !== 'undefined' &&
    (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1')
    ? 'https://api.perenniaai.com'
    : 'http://localhost:8000';

  const fetchQueues = useCallback(async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/queues`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch queues: ${response.status}`);
      }

      const data = await response.json();
      setQueues(data.queues || []);
      setError(null);
    } catch (err) {
      setError(err?.message || 'Failed to load queues');
      // Demo data fallback
      setQueues([
        {
          id: 1,
          name: 'sales',
          friendly_name: 'Sales Queue',
          description: 'Queue for new loan inquiries',
          max_wait_time_seconds: 600,
          max_queue_size: 20,
          is_active: true,
          member_count: 3,
          waiting_calls: 2,
          avg_wait_time: 45
        },
        {
          id: 2,
          name: 'support',
          friendly_name: 'Support Queue',
          description: 'Queue for existing loan support',
          max_wait_time_seconds: 600,
          max_queue_size: 20,
          is_active: true,
          member_count: 5,
          waiting_calls: 0,
          avg_wait_time: 30
        }
      ]);
    } finally {
      setLoading(false);
    }
  }, [API_BASE_URL]);

  useEffect(() => {
    fetchQueues();
    // Auto-refresh every 10 seconds
    const interval = setInterval(fetchQueues, 10000);
    setRefreshInterval(interval);
    return () => clearInterval(interval);
  }, [fetchQueues]);

  const handleTakeNextCall = async (queueId) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/queues/${queueId}/take-next`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to take call');
      }

      const data = await response.json();
      toast.info(`Connecting to caller: ${data.caller_name || data.caller_phone}`);
      fetchQueues();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const formatWaitTime = (seconds) => {
    if (!seconds) return '0s';
    if (seconds < 60) return `${seconds}s`;
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
  };

  const getStatusColor = (queue) => {
    if (!queue.is_active) return '#6b7280';
    if (queue.waiting_calls > 5) return '#ef4444';
    if (queue.waiting_calls > 0) return '#f59e0b';
    return '#22c55e';
  };

  if (loading) {
    return (
      <div className="cq-dashboard">
        <div className="cq-loading">
          <div className="cq-spinner"></div>
          <p>Loading call queues...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="cq-dashboard">
      <div className="cq-header">
        <div className="cq-header-left">
          <h1>Call Queues</h1>
          <p className="cq-subtitle">Monitor and manage inbound call queues</p>
        </div>
        <div className="cq-header-right">
          <button className="cq-btn cq-btn-secondary" onClick={fetchQueues}>
            <span className="cq-icon">&#x21bb;</span> Refresh
          </button>
          <button className="cq-btn cq-btn-primary" onClick={() => setShowCreateModal(true)}>
            <span className="cq-icon">+</span> Create Queue
          </button>
        </div>
      </div>

      {error && (
        <div className="cq-error-banner">
          <span className="cq-icon">&#x26A0;</span>
          {error}
          <button onClick={fetchQueues}>Retry</button>
        </div>
      )}

      <div className="cq-stats-row">
        <div className="cq-stat-card">
          <div className="cq-stat-value">{queues.length}</div>
          <div className="cq-stat-label">Total Queues</div>
        </div>
        <div className="cq-stat-card">
          <div className="cq-stat-value">{queues.filter(q => q.is_active).length}</div>
          <div className="cq-stat-label">Active Queues</div>
        </div>
        <div className="cq-stat-card cq-stat-highlight">
          <div className="cq-stat-value">{queues.reduce((sum, q) => sum + (q.waiting_calls || 0), 0)}</div>
          <div className="cq-stat-label">Callers Waiting</div>
        </div>
        <div className="cq-stat-card">
          <div className="cq-stat-value">{queues.reduce((sum, q) => sum + (q.member_count || 0), 0)}</div>
          <div className="cq-stat-label">Total Agents</div>
        </div>
      </div>

      <div className="cq-grid">
        {queues.map(queue => (
          <div
            key={queue.id}
            className={`cq-card ${selectedQueue?.id === queue.id ? 'cq-card-selected' : ''}`}
            onClick={() => setSelectedQueue(queue)}
          >
            <div className="cq-card-header">
              <div className="cq-card-status" style={{ backgroundColor: getStatusColor(queue) }}></div>
              <div className="cq-card-title">
                <h3>{queue.friendly_name}</h3>
                <span className="cq-card-name">{queue.name}</span>
              </div>
              <div className={`cq-card-badge ${queue.is_active ? 'cq-badge-active' : 'cq-badge-inactive'}`}>
                {queue.is_active ? 'Active' : 'Inactive'}
              </div>
            </div>

            <p className="cq-card-description">{queue.description}</p>

            <div className="cq-card-metrics">
              <div className="cq-metric">
                <div className="cq-metric-value">{queue.waiting_calls || 0}</div>
                <div className="cq-metric-label">Waiting</div>
              </div>
              <div className="cq-metric">
                <div className="cq-metric-value">{queue.member_count || 0}</div>
                <div className="cq-metric-label">Agents</div>
              </div>
              <div className="cq-metric">
                <div className="cq-metric-value">{formatWaitTime(queue.avg_wait_time)}</div>
                <div className="cq-metric-label">Avg Wait</div>
              </div>
              <div className="cq-metric">
                <div className="cq-metric-value">{queue.max_queue_size}</div>
                <div className="cq-metric-label">Max Size</div>
              </div>
            </div>

            <div className="cq-card-actions">
              <button
                className="cq-btn cq-btn-take-call"
                disabled={!queue.waiting_calls || queue.waiting_calls === 0}
                onClick={(e) => {
                  e.stopPropagation();
                  handleTakeNextCall(queue.id);
                }}
              >
                <span className="cq-icon">&#x260E;</span>
                Take Next Call
              </button>
              <button
                className="cq-btn cq-btn-outline"
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedQueue(queue);
                }}
              >
                Manage
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Queue Detail Panel */}
      {selectedQueue && (
        <div className="cq-detail-panel">
          <div className="cq-detail-header">
            <h2>{selectedQueue.friendly_name}</h2>
            <button className="cq-close-btn" onClick={() => setSelectedQueue(null)}>&times;</button>
          </div>

          <div className="cq-detail-content">
            <div className="cq-detail-section">
              <h4>Queue Settings</h4>
              <div className="cq-detail-row">
                <span>Queue Name:</span>
                <strong>{selectedQueue.name}</strong>
              </div>
              <div className="cq-detail-row">
                <span>Max Wait Time:</span>
                <strong>{formatWaitTime(selectedQueue.max_wait_time_seconds)}</strong>
              </div>
              <div className="cq-detail-row">
                <span>Max Queue Size:</span>
                <strong>{selectedQueue.max_queue_size} callers</strong>
              </div>
              <div className="cq-detail-row">
                <span>Status:</span>
                <strong className={selectedQueue.is_active ? 'cq-text-success' : 'cq-text-muted'}>
                  {selectedQueue.is_active ? 'Active' : 'Inactive'}
                </strong>
              </div>
            </div>

            <div className="cq-detail-section">
              <h4>Current Status</h4>
              <div className="cq-detail-row">
                <span>Callers Waiting:</span>
                <strong>{selectedQueue.waiting_calls || 0}</strong>
              </div>
              <div className="cq-detail-row">
                <span>Agents Online:</span>
                <strong>{selectedQueue.member_count || 0}</strong>
              </div>
              <div className="cq-detail-row">
                <span>Avg Wait Time:</span>
                <strong>{formatWaitTime(selectedQueue.avg_wait_time)}</strong>
              </div>
            </div>

            <div className="cq-detail-actions">
              <button className="cq-btn cq-btn-primary">
                <span className="cq-icon">&#x270E;</span> Edit Queue
              </button>
              <button className="cq-btn cq-btn-secondary">
                <span className="cq-icon">&#x1F464;</span> Manage Agents
              </button>
              <button className="cq-btn cq-btn-danger">
                {selectedQueue.is_active ? 'Deactivate' : 'Activate'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create Queue Modal */}
      {showCreateModal && (
        <CreateQueueModal
          onClose={() => setShowCreateModal(false)}
          onCreated={() => {
            setShowCreateModal(false);
            fetchQueues();
          }}
          apiBaseUrl={API_BASE_URL}
        />
      )}
    </div>
  );
};

// Create Queue Modal Component
const CreateQueueModal = ({ onClose, onCreated, apiBaseUrl }) => {
  const [formData, setFormData] = useState({
    name: '',
    friendly_name: '',
    description: '',
    max_wait_time_seconds: 600,
    max_queue_size: 20
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);

    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${apiBaseUrl}/api/v1/queues`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(formData)
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to create queue');
      }

      onCreated();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="cq-modal-overlay" onClick={onClose}>
      <div className="cq-modal" onClick={e => e.stopPropagation()}>
        <div className="cq-modal-header">
          <h2>Create New Queue</h2>
          <button className="cq-close-btn" onClick={onClose}>&times;</button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="cq-modal-body">
            {error && <div className="cq-form-error">{error}</div>}

            <div className="cq-form-group">
              <label>Queue Name (internal)</label>
              <input
                type="text"
                value={formData.name}
                onChange={e => setFormData({...formData, name: e.target.value.toLowerCase().replace(/\s+/g, '_')})}
                placeholder="e.g., sales_team"
                required
              />
            </div>

            <div className="cq-form-group">
              <label>Display Name</label>
              <input
                type="text"
                value={formData.friendly_name}
                onChange={e => setFormData({...formData, friendly_name: e.target.value})}
                placeholder="e.g., Sales Team Queue"
                required
              />
            </div>

            <div className="cq-form-group">
              <label>Description</label>
              <textarea
                value={formData.description}
                onChange={e => setFormData({...formData, description: e.target.value})}
                placeholder="Describe the purpose of this queue"
                rows={3}
              />
            </div>

            <div className="cq-form-row">
              <div className="cq-form-group">
                <label>Max Wait Time (seconds)</label>
                <input
                  type="number"
                  value={formData.max_wait_time_seconds}
                  onChange={e => setFormData({...formData, max_wait_time_seconds: parseInt(e.target.value)})}
                  min={60}
                  max={3600}
                />
              </div>

              <div className="cq-form-group">
                <label>Max Queue Size</label>
                <input
                  type="number"
                  value={formData.max_queue_size}
                  onChange={e => setFormData({...formData, max_queue_size: parseInt(e.target.value)})}
                  min={1}
                  max={100}
                />
              </div>
            </div>
          </div>

          <div className="cq-modal-footer">
            <button type="button" className="cq-btn cq-btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="cq-btn cq-btn-primary" disabled={saving}>
              {saving ? 'Creating...' : 'Create Queue'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default CallQueueDashboard;
