import { useState, useEffect, useCallback, useRef } from 'react';
import { API_BASE_URL } from '../services/api';
import { getAuthHeaders } from '../utils/auth';
import { toast } from '../utils/toast';
import './SMSTasks.css';

const POLL_INTERVAL = 30000;

const STATUS_TABS = [
  { key: 'all', label: 'All' },
  { key: 'pending', label: 'Pending' },
  { key: 'in_progress', label: 'In Progress' },
  { key: 'auto_responded', label: 'Auto-responded' },
  { key: 'completed', label: 'Completed' },
  { key: 'dismissed', label: 'Dismissed' },
  { key: 'expired', label: 'Expired' },
];

const CATEGORY_OPTIONS = [
  { value: '', label: 'All Categories' },
  { value: 'scheduling', label: 'Scheduling' },
  { value: 'question', label: 'Question' },
  { value: 'document_request', label: 'Document Request' },
  { value: 'status_update', label: 'Status Update' },
  { value: 'rate_inquiry', label: 'Rate Inquiry' },
  { value: 'general', label: 'General' },
];

const CATEGORY_COLORS = {
  scheduling: { bg: '#e0f2fe', text: '#0369a1' },
  question: { bg: '#fef3c7', text: '#92400e' },
  document_request: { bg: '#ede9fe', text: '#6d28d9' },
  status_update: { bg: '#d1fae5', text: '#065f46' },
  rate_inquiry: { bg: '#fce7f3', text: '#9d174d' },
  general: { bg: '#f3f4f6', text: '#374151' },
};

const PRIORITY_COLORS = {
  urgent: '#ef4444',
  high: '#f97316',
  normal: '#22c55e',
  low: '#9ca3af',
};

function timeAgo(dateStr) {
  if (!dateStr) return '';
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function truncate(str, len) {
  if (!str) return '';
  return str.length > len ? str.slice(0, len) + '...' : str;
}

function SMSTasks() {
  const [tasks, setTasks] = useState([]);
  const [selectedTask, setSelectedTask] = useState(null);
  const [taskDetail, setTaskDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('pending');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [stats, setStats] = useState({ pending: 0, auto_responded_today: 0, avg_confidence: 0 });
  const [settings, setSettings] = useState({});
  const [showAutopilot, setShowAutopilot] = useState(false);
  const [responseMode, setResponseMode] = useState(null);
  const [editText, setEditText] = useState('');
  const [sending, setSending] = useState(false);
  const [newTaskCount, setNewTaskCount] = useState(0);
  const [feedbackTaskId, setFeedbackTaskId] = useState(null);
  const [settingsLoading, setSettingsLoading] = useState({});
  const [fetchError, setFetchError] = useState(null);
  const previousCountRef = useRef(0);
  const pollRef = useRef(null);
  const fetchTasksRef = useRef(null);
  const fetchStatsRef = useRef(null);

  const headers = getAuthHeaders();

  const fetchTasks = useCallback(async (showLoader = false) => {
    if (showLoader) setLoading(true);
    try {
      const params = new URLSearchParams({ limit: '50' });
      if (activeTab !== 'all') params.set('status', activeTab);
      if (categoryFilter) params.set('category', categoryFilter);
      const res = await fetch(`${API_BASE_URL}/api/v1/sms-tasks?${params}`, { headers });
      if (!res.ok) throw new Error('Failed to fetch tasks');
      const data = await res.json();
      const taskList = Array.isArray(data) ? data : (data.tasks || data.items || []);

      if (!showLoader && taskList.length > previousCountRef.current && previousCountRef.current > 0) {
        setNewTaskCount(taskList.length - previousCountRef.current);
      }
      previousCountRef.current = taskList.length;
      setTasks(taskList);
      setFetchError(null);
    } catch (err) {
      console.error('Error fetching SMS tasks:', err);
      setFetchError('Failed to load tasks');
    } finally {
      setLoading(false);
    }
  }, [activeTab, categoryFilter]);

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/sms-tasks/stats`, { headers });
      if (!res.ok) return;
      const data = await res.json();
      const counts = data.counts || data;
      const confList = data.confidence || [];
      const avgConf = confList.length > 0
        ? Math.round(confList.reduce((s, c) => s + (c.confidence_score || 0), 0) / confList.length)
        : 0;
      setStats({
        pending: counts.pending || 0,
        auto_responded_today: counts.auto_responded_today || 0,
        avg_confidence: avgConf,
      });
    } catch (err) {
      console.error('Error fetching stats:', err);
    }
  }, []);

  fetchTasksRef.current = fetchTasks;
  fetchStatsRef.current = fetchStats;

  const fetchSettings = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/sms-tasks/settings`, { headers });
      if (!res.ok) return;
      const data = await res.json();
      setSettings(data);
    } catch (err) {
      console.error('Error fetching settings:', err);
    }
  }, []);

  const fetchTaskDetail = useCallback(async (taskId) => {
    setDetailLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/sms-tasks/${taskId}`, { headers });
      if (!res.ok) throw new Error('Failed to fetch task detail');
      const data = await res.json();
      setTaskDetail(data);
    } catch (err) {
      console.error('Error fetching task detail:', err);
      toast.error('Failed to load task details');
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTasks(true);
    fetchStats();
    fetchSettings();
  }, [fetchTasks, fetchStats, fetchSettings]);

  useEffect(() => {
    const id = setInterval(() => {
      if (fetchTasksRef.current) fetchTasksRef.current();
      if (fetchStatsRef.current) fetchStatsRef.current();
    }, POLL_INTERVAL);
    return () => clearInterval(id);
  }, []); // empty deps - refs always have latest functions

  useEffect(() => {
    if (selectedTask) {
      fetchTaskDetail(selectedTask);
      setResponseMode(null);
      setEditText('');
      setFeedbackTaskId(null);
    } else {
      setTaskDetail(null);
    }
  }, [selectedTask, fetchTaskDetail]);

  const handleSendResponse = async (text, source) => {
    if (!text.trim() || !selectedTask) return;
    setSending(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/sms-tasks/${selectedTask}/respond`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ response_text: text, response_source: source }),
      });
      if (!res.ok) throw new Error('Failed to send response');
      toast.success('Response sent successfully');
      setFeedbackTaskId(selectedTask);
      setResponseMode(null);
      setEditText('');
      await fetchTasks(false);
      await fetchStats();
      const currentIndex = tasks.findIndex(t => t.id === selectedTask);
      const nextPending = tasks.find((t, i) => i > currentIndex && t.status === 'pending');
      if (nextPending) {
        setSelectedTask(nextPending.id);
      }
    } catch (err) {
      console.error('Error sending response:', err);
      toast.error('Failed to send response');
    } finally {
      setSending(false);
    }
  };

  const handleDismiss = async () => {
    if (!selectedTask) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/sms-tasks/${selectedTask}/dismiss`, {
        method: 'POST',
        headers,
      });
      if (!res.ok) throw new Error('Failed to dismiss task');
      toast.success('Task dismissed');
      const currentIndex = tasks.findIndex(t => t.id === selectedTask);
      const nextPending = tasks.find((t, i) => i > currentIndex && t.status === 'pending');
      setSelectedTask(nextPending ? nextPending.id : null);
      await fetchTasks(false);
      await fetchStats();
    } catch (err) {
      console.error('Error dismissing task:', err);
      toast.error('Failed to dismiss task');
    }
  };

  const handleRegenerate = async () => {
    if (!selectedTask) return;
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/sms-tasks/${selectedTask}/regenerate`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ feedback: 'Please suggest a different response' }),
      });
      if (!res.ok) throw new Error('Failed to regenerate');
      toast.success('Regenerating AI response...');
      await fetchTaskDetail(selectedTask);
    } catch (err) {
      console.error('Error regenerating:', err);
      toast.error('Failed to regenerate response');
    }
  };

  const handleFeedback = async (rating) => {
    if (!feedbackTaskId) return;
    try {
      await fetch(`${API_BASE_URL}/api/v1/sms-tasks/${feedbackTaskId}/feedback`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ rating }),
      });
      toast.success('Feedback submitted');
      setFeedbackTaskId(null);
    } catch (err) {
      console.error('Error submitting feedback:', err);
    }
  };

  const handleSettingsChange = async (category, field, value) => {
    const key = `${category}-${field}`;
    setSettingsLoading(prev => ({ ...prev, [key]: true }));
    try {
      const body = { category };
      if (field === 'auto_respond_enabled') body.auto_respond_enabled = value;
      if (field === 'auto_respond_threshold') body.auto_respond_threshold = value;
      const res = await fetch(`${API_BASE_URL}/api/v1/sms-tasks/settings`, {
        method: 'PUT',
        headers,
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error('Failed to update settings');
      await fetchSettings();
      toast.success('Auto-pilot settings updated');
    } catch (err) {
      console.error('Error updating settings:', err);
      toast.error('Failed to update settings');
    } finally {
      setSettingsLoading(prev => ({ ...prev, [key]: false }));
    }
  };

  const dismissNewTaskBanner = () => setNewTaskCount(0);

  const pendingTasks = tasks.filter(t => t.status === 'pending');

  return (
    <div className="sms-tasks-page">
      <div className="sms-tasks-header">
        <div className="header-left">
          <h1>SMS Task Inbox</h1>
          {stats.pending > 0 && (
            <span className="task-count-badge">{stats.pending}</span>
          )}
        </div>
        <button
          className={`autopilot-toggle ${showAutopilot ? 'active' : ''}`}
          onClick={() => setShowAutopilot(!showAutopilot)}
        >
          Auto-pilot Settings {showAutopilot ? '\u25B2' : '\u25BC'}
        </button>
      </div>

      {showAutopilot && (
        <div className="autopilot-panel">
          <div className="autopilot-header">
            <h3>Auto-pilot Configuration</h3>
            <p className="autopilot-summary">
              AI has responded to {stats.auto_responded_today} messages automatically today
            </p>
          </div>
          <div className="autopilot-categories">
            {CATEGORY_OPTIONS.filter(c => c.value).map(cat => {
              const catSettings = settings[cat.value] || {};
              return (
                <div key={cat.value} className="autopilot-category-row">
                  <span className="category-name">{cat.label}</span>
                  <label className="toggle-switch">
                    <input
                      type="checkbox"
                      checked={catSettings.auto_respond_enabled || false}
                      onChange={(e) => handleSettingsChange(cat.value, 'auto_respond_enabled', e.target.checked)}
                      disabled={settingsLoading[`${cat.value}-auto_respond_enabled`]}
                    />
                    <span className="toggle-slider" />
                  </label>
                  <div className="threshold-control">
                    <label>Threshold: {catSettings.auto_respond_threshold || 85}%</label>
                    <input
                      type="range"
                      min="50"
                      max="99"
                      value={catSettings.auto_respond_threshold || 85}
                      onChange={(e) => handleSettingsChange(cat.value, 'auto_respond_threshold', parseInt(e.target.value))}
                      disabled={!catSettings.auto_respond_enabled}
                      className="threshold-slider"
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {newTaskCount > 0 && (
        <div className="new-tasks-banner" onClick={dismissNewTaskBanner}>
          {newTaskCount} new task{newTaskCount > 1 ? 's' : ''} arrived — click to dismiss
        </div>
      )}

      <div className="stats-bar">
        <div className="stat-item pending">
          <span className="stat-number">{stats.pending}</span>
          <span className="stat-label">Pending</span>
        </div>
        <div className="stat-item auto-responded">
          <span className="stat-number">{stats.auto_responded_today}</span>
          <span className="stat-label">Auto-responded Today</span>
        </div>
        <div className="stat-item confidence">
          <span className="stat-number">{stats.avg_confidence}%</span>
          <span className="stat-label">Avg AI Confidence</span>
        </div>
      </div>

      <div className="filter-bar">
        <div className="tab-group">
          {STATUS_TABS.map(tab => (
            <button
              key={tab.key}
              className={`filter-tab ${activeTab === tab.key ? 'active' : ''}`}
              onClick={() => { setActiveTab(tab.key); setSelectedTask(null); }}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <select
          className="category-select"
          value={categoryFilter}
          onChange={(e) => { setCategoryFilter(e.target.value); setSelectedTask(null); }}
        >
          {CATEGORY_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>

      {fetchError && (
        <div style={{ padding: '8px 16px', background: '#fee', color: '#c00', borderRadius: 4, margin: '0 16px 8px' }}>
          {fetchError} — <button onClick={fetchTasks} style={{ background: 'none', border: 'none', color: '#c00', textDecoration: 'underline', cursor: 'pointer' }}>retry</button>
        </div>
      )}

      <div className="sms-tasks-body">
        <div className={`task-list-panel ${selectedTask ? 'has-selection' : ''}`}>
          {loading ? (
            <div className="loading-state">
              {[1, 2, 3, 4, 5].map(i => (
                <div key={i} className="task-card-skeleton">
                  <div className="skeleton-line wide" />
                  <div className="skeleton-line medium" />
                  <div className="skeleton-line narrow" />
                </div>
              ))}
            </div>
          ) : tasks.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">&#x2709;</div>
              <h3>All caught up!</h3>
              <p>No pending SMS tasks.</p>
            </div>
          ) : (
            <div className="task-list">
              {tasks.map(task => (
                <div
                  key={task.id}
                  className={`task-card ${selectedTask === task.id ? 'selected' : ''} ${task.status === 'pending' ? 'is-pending' : ''}`}
                  onClick={() => setSelectedTask(task.id)}
                >
                  <div className="task-card-top">
                    <div className="task-card-contact">
                      <span
                        className="priority-dot"
                        style={{ backgroundColor: PRIORITY_COLORS[task.priority] || PRIORITY_COLORS.normal }}
                        title={task.priority || 'normal'}
                      />
                      <span className="contact-name">{task.contact_name || 'Unknown'}</span>
                      <span className="contact-phone">{task.phone_number || ''}</span>
                    </div>
                    <span className="task-time">{timeAgo(task.inbound_received_at || task.created_at)}</span>
                  </div>
                  <p className="task-message-preview">{truncate(task.inbound_message, 100)}</p>
                  <div className="task-card-bottom">
                    <span
                      className="category-badge"
                      style={{
                        backgroundColor: (CATEGORY_COLORS[task.category] || CATEGORY_COLORS.general).bg,
                        color: (CATEGORY_COLORS[task.category] || CATEGORY_COLORS.general).text,
                      }}
                    >
                      {(task.category || 'general').replace(/_/g, ' ')}
                    </span>
                    <div className="confidence-indicator">
                      <div className="confidence-bar-bg">
                        <div
                          className="confidence-bar-fill"
                          style={{ width: `${task.ai_confidence || 0}%` }}
                        />
                      </div>
                      <span className="confidence-pct">{task.ai_confidence || 0}%</span>
                    </div>
                    <span className={`status-badge status-${task.status}`}>
                      {(task.status || '').replace(/_/g, ' ')}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className={`task-detail-panel ${selectedTask ? 'visible' : ''}`}>
          {!selectedTask ? (
            <div className="detail-placeholder">
              <p>Select a task to view details</p>
            </div>
          ) : detailLoading ? (
            <div className="detail-loading">
              <div className="spinner" />
              <p>Loading task details...</p>
            </div>
          ) : taskDetail ? (
            <div className="detail-content">
              <div className="detail-header">
                <div>
                  <h2>{taskDetail.contact_name || 'Unknown Contact'}</h2>
                  <span className="detail-phone">{taskDetail.phone_number || ''}</span>
                </div>
                <button className="close-detail" onClick={() => setSelectedTask(null)}>&times;</button>
              </div>

              <div className="detail-section">
                <h4>Inbound Message</h4>
                <div className="inbound-message-box">
                  <p>{taskDetail.inbound_message}</p>
                  <span className="message-time">{timeAgo(taskDetail.inbound_received_at || taskDetail.created_at)}</span>
                </div>
              </div>

              <div className="detail-meta">
                <span
                  className="category-badge"
                  style={{
                    backgroundColor: (CATEGORY_COLORS[taskDetail.category] || CATEGORY_COLORS.general).bg,
                    color: (CATEGORY_COLORS[taskDetail.category] || CATEGORY_COLORS.general).text,
                  }}
                >
                  {(taskDetail.category || 'general').replace(/_/g, ' ')}
                </span>
                <span
                  className="priority-badge"
                  style={{ color: PRIORITY_COLORS[taskDetail.priority] || PRIORITY_COLORS.normal }}
                >
                  {taskDetail.priority || 'normal'} priority
                </span>
              </div>

              {taskDetail.ai_recommendation && (
                <div className="detail-section">
                  <h4>AI Recommended Response</h4>
                  <div className="ai-response-box">
                    <p>{taskDetail.ai_recommendation}</p>
                    <div className="ai-confidence-row">
                      <span>Confidence: {taskDetail.ai_confidence || 0}%</span>
                      <div className="confidence-bar-bg large">
                        <div
                          className="confidence-bar-fill"
                          style={{ width: `${taskDetail.ai_confidence || 0}%` }}
                        />
                      </div>
                      <button className="regen-btn" onClick={handleRegenerate} title="Regenerate">&#x21bb;</button>
                    </div>
                  </div>
                </div>
              )}

              {feedbackTaskId === selectedTask && (
                <div className="feedback-row">
                  <span>How was this response?</span>
                  <button className="feedback-btn up" onClick={() => handleFeedback('positive')}>&#x1F44D;</button>
                  <button className="feedback-btn down" onClick={() => handleFeedback('negative')}>&#x1F44E;</button>
                </div>
              )}

              {taskDetail.status === 'pending' && !responseMode && (
                <div className="action-buttons">
                  <button
                    className="action-btn send-ai"
                    onClick={() => handleSendResponse(taskDetail.ai_recommendation, 'ai')}
                    disabled={!taskDetail.ai_recommendation || sending}
                  >
                    {sending ? 'Sending...' : 'Send AI Response'}
                  </button>
                  <button
                    className="action-btn edit-send"
                    onClick={() => {
                      setResponseMode('edit');
                      setEditText(taskDetail.ai_recommendation || '');
                    }}
                  >
                    Edit & Send
                  </button>
                  <button
                    className="action-btn write-own"
                    onClick={() => {
                      setResponseMode('write');
                      setEditText('');
                    }}
                  >
                    Write Own
                  </button>
                  <button className="action-btn dismiss" onClick={handleDismiss}>
                    Dismiss
                  </button>
                </div>
              )}

              {responseMode && (
                <div className="compose-area">
                  <textarea
                    value={editText}
                    onChange={(e) => setEditText(e.target.value)}
                    placeholder={responseMode === 'edit' ? 'Edit the AI response...' : 'Write your response...'}
                    rows={4}
                    autoFocus
                  />
                  <div className="compose-actions">
                    <button
                      className="action-btn send-ai"
                      onClick={() => handleSendResponse(editText, responseMode === 'edit' ? 'ai_edited' : 'manual')}
                      disabled={!editText.trim() || sending}
                    >
                      {sending ? 'Sending...' : 'Send'}
                    </button>
                    <button
                      className="action-btn dismiss"
                      onClick={() => { setResponseMode(null); setEditText(''); }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {taskDetail.status !== 'pending' && (
                <div className="detail-section">
                  <h4>Response Sent</h4>
                  <div className="sent-response-box">
                    <p>{taskDetail.response_text || 'No response recorded'}</p>
                    <span className="response-source">
                      via {(taskDetail.response_source || 'unknown').replace(/_/g, ' ')}
                    </span>
                  </div>
                </div>
              )}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export default SMSTasks;
