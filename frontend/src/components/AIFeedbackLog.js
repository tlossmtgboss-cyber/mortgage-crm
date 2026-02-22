import React, { useState, useEffect } from 'react';
import { aiAPI } from '../services/api';
import './AIFeedbackLog.css';
import { toast } from '../utils/toast';

function AIFeedbackLog() {
  const [feedbackLogs, setFeedbackLogs] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedFeedback, setSelectedFeedback] = useState(null);
  const [filters, setFilters] = useState({
    status: '',
    category: '',
    feedback_type: ''
  });
  const [updating, setUpdating] = useState(false);

  useEffect(() => {
    loadFeedbackData();
  }, [filters]);

  const loadFeedbackData = async () => {
    setLoading(true);
    try {
      const [logsResponse, statsResponse] = await Promise.all([
        aiAPI.getFeedbackLogs(filters),
        aiAPI.getFeedbackStats()
      ]);
      setFeedbackLogs(logsResponse || []);
      setStats(statsResponse);
    } catch (error) {
      console.error('Failed to load feedback data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateStatus = async (feedbackId, newStatus, resolutionNotes = '') => {
    setUpdating(true);
    try {
      await aiAPI.updateFeedback(feedbackId, {
        status: newStatus,
        resolution_notes: resolutionNotes
      });
      // Refresh data
      loadFeedbackData();
      setSelectedFeedback(null);
    } catch (error) {
      console.error('Failed to update feedback:', error);
      toast.error('Failed to update feedback status');
    } finally {
      setUpdating(false);
    }
  };

  const handleDelete = async (feedbackId) => {
    try {
      await aiAPI.deleteFeedback(feedbackId);
      loadFeedbackData();
      setSelectedFeedback(null);
    } catch (error) {
      console.error('Failed to delete feedback:', error);
      toast.error('Failed to delete feedback');
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return '-';
    return new Date(dateString).toLocaleString();
  };

  const getStatusBadgeClass = (status) => {
    const classes = {
      pending: 'badge-pending',
      reviewed: 'badge-reviewed',
      fixed: 'badge-fixed',
      dismissed: 'badge-dismissed'
    };
    return classes[status] || 'badge-pending';
  };

  const getFeedbackTypeLabel = (type) => {
    const labels = {
      wrong_answer: 'Wrong Answer',
      incomplete: 'Incomplete',
      outdated: 'Outdated Info',
      irrelevant: 'Irrelevant',
      other: 'Other'
    };
    return labels[type] || type;
  };

  return (
    <div className="ai-feedback-log-container">
      <div className="ai-feedback-header">
        <h2>AI Feedback Log</h2>
        <p>Track and manage user feedback on AI responses to continuously improve the system.</p>
      </div>

      {/* Stats Summary */}
      {stats && (
        <div className="ai-feedback-stats">
          <div className="stat-card">
            <div className="stat-value">{stats.total_feedback}</div>
            <div className="stat-label">Total Feedback</div>
          </div>
          <div className="stat-card pending">
            <div className="stat-value">{stats.pending_count}</div>
            <div className="stat-label">Pending</div>
          </div>
          <div className="stat-card reviewed">
            <div className="stat-value">{stats.reviewed_count}</div>
            <div className="stat-label">Reviewed</div>
          </div>
          <div className="stat-card fixed">
            <div className="stat-value">{stats.fixed_count}</div>
            <div className="stat-label">Fixed</div>
          </div>
          <div className="stat-card dismissed">
            <div className="stat-value">{stats.dismissed_count}</div>
            <div className="stat-label">Dismissed</div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="ai-feedback-filters">
        <select
          value={filters.status}
          onChange={(e) => setFilters({ ...filters, status: e.target.value })}
        >
          <option value="">All Statuses</option>
          <option value="pending">Pending</option>
          <option value="reviewed">Reviewed</option>
          <option value="fixed">Fixed</option>
          <option value="dismissed">Dismissed</option>
        </select>

        <select
          value={filters.category}
          onChange={(e) => setFilters({ ...filters, category: e.target.value })}
        >
          <option value="">All Categories</option>
          <option value="sla">SLA</option>
          <option value="pipeline">Pipeline</option>
          <option value="tasks">Tasks</option>
          <option value="loans">Loans</option>
          <option value="leads">Leads</option>
          <option value="general">General</option>
        </select>

        <select
          value={filters.feedback_type}
          onChange={(e) => setFilters({ ...filters, feedback_type: e.target.value })}
        >
          <option value="">All Types</option>
          <option value="wrong_answer">Wrong Answer</option>
          <option value="incomplete">Incomplete</option>
          <option value="outdated">Outdated Info</option>
          <option value="irrelevant">Irrelevant</option>
          <option value="other">Other</option>
        </select>

        <button className="refresh-btn" onClick={loadFeedbackData}>
          Refresh
        </button>
      </div>

      {/* Feedback Table */}
      <div className="ai-feedback-table-container">
        {loading ? (
          <div className="loading-state">Loading feedback logs...</div>
        ) : feedbackLogs.length === 0 ? (
          <div className="empty-state">
            <p>No feedback logs found.</p>
            <p className="empty-hint">When users report issues with AI responses, they'll appear here.</p>
          </div>
        ) : (
          <table className="ai-feedback-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>User</th>
                <th>Question</th>
                <th>Type</th>
                <th>Category</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {feedbackLogs.map((feedback) => (
                <tr key={feedback.id} className={selectedFeedback?.id === feedback.id ? 'selected' : ''}>
                  <td>{formatDate(feedback.created_at)}</td>
                  <td>{feedback.user_email || `User ${feedback.user_id}`}</td>
                  <td className="question-cell">
                    <span title={feedback.user_question}>
                      {feedback.user_question.substring(0, 50)}
                      {feedback.user_question.length > 50 ? '...' : ''}
                    </span>
                  </td>
                  <td>{getFeedbackTypeLabel(feedback.feedback_type)}</td>
                  <td>{feedback.category || '-'}</td>
                  <td>
                    <span className={`status-badge ${getStatusBadgeClass(feedback.status)}`}>
                      {feedback.status}
                    </span>
                  </td>
                  <td>
                    <button
                      className="view-btn"
                      onClick={() => setSelectedFeedback(feedback)}
                    >
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Detail Modal */}
      {selectedFeedback && (
        <div className="ai-feedback-detail-overlay" onClick={() => setSelectedFeedback(null)}>
          <div className="ai-feedback-detail-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Feedback Details</h3>
              <button className="close-btn" onClick={() => setSelectedFeedback(null)}>x</button>
            </div>

            <div className="modal-body">
              <div className="detail-section">
                <label>Submitted By:</label>
                <p>{selectedFeedback.user_email || `User ${selectedFeedback.user_id}`}</p>
              </div>

              <div className="detail-section">
                <label>Date:</label>
                <p>{formatDate(selectedFeedback.created_at)}</p>
              </div>

              <div className="detail-section">
                <label>Type:</label>
                <p>{getFeedbackTypeLabel(selectedFeedback.feedback_type)}</p>
              </div>

              <div className="detail-section">
                <label>Category:</label>
                <p>{selectedFeedback.category || 'Not categorized'}</p>
              </div>

              <div className="detail-section">
                <label>User Question:</label>
                <div className="question-box">{selectedFeedback.user_question}</div>
              </div>

              <div className="detail-section">
                <label>AI Response:</label>
                <div className="response-box">{selectedFeedback.ai_response}</div>
              </div>

              {selectedFeedback.user_feedback && (
                <div className="detail-section">
                  <label>User's Additional Feedback:</label>
                  <div className="feedback-box">{selectedFeedback.user_feedback}</div>
                </div>
              )}

              <div className="detail-section">
                <label>Current Status:</label>
                <span className={`status-badge ${getStatusBadgeClass(selectedFeedback.status)}`}>
                  {selectedFeedback.status}
                </span>
              </div>

              {selectedFeedback.resolution_notes && (
                <div className="detail-section">
                  <label>Resolution Notes:</label>
                  <div className="resolution-box">{selectedFeedback.resolution_notes}</div>
                </div>
              )}

              {selectedFeedback.resolved_by && (
                <div className="detail-section">
                  <label>Resolved By:</label>
                  <p>{selectedFeedback.resolver_email || `User ${selectedFeedback.resolved_by}`} at {formatDate(selectedFeedback.resolved_at)}</p>
                </div>
              )}
            </div>

            <div className="modal-footer">
              <div className="status-actions">
                <span>Update Status:</span>
                {selectedFeedback.status !== 'reviewed' && (
                  <button
                    className="status-btn reviewed"
                    onClick={() => handleUpdateStatus(selectedFeedback.id, 'reviewed')}
                    disabled={updating}
                  >
                    Mark Reviewed
                  </button>
                )}
                {selectedFeedback.status !== 'fixed' && (
                  <button
                    className="status-btn fixed"
                    onClick={() => handleUpdateStatus(selectedFeedback.id, 'fixed')}
                    disabled={updating}
                  >
                    Mark Fixed
                  </button>
                )}
                {selectedFeedback.status !== 'dismissed' && (
                  <button
                    className="status-btn dismissed"
                    onClick={() => handleUpdateStatus(selectedFeedback.id, 'dismissed')}
                    disabled={updating}
                  >
                    Dismiss
                  </button>
                )}
              </div>
              <button
                className="delete-btn"
                onClick={() => handleDelete(selectedFeedback.id)}
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AIFeedbackLog;
