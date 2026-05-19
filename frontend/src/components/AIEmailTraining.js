import React, { useState, useEffect, useCallback } from 'react';
import './AIEmailTraining.css';
import api from '../services/api';

const AIEmailTraining = () => {
  const [emails, setEmails] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedEmail, setSelectedEmail] = useState(null);
  const [filter, setFilter] = useState('all'); // all, pending, correct, incorrect
  const [source, setSource] = useState('all'); // all, ai_conversations, inbox
  const [feedbackForm, setFeedbackForm] = useState({
    is_correct: null,
    feedback_type: '',
    correct_response: '',
    feedback_notes: ''
  });
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState(null);

  const fetchEmails = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (filter !== 'all') params.append('status', filter);
      if (source !== 'all') params.append('source', source);
      const queryString = params.toString() ? `?${params.toString()}` : '';

      const { data } = await api.get(`/api/v1/email-training/emails${queryString}`);
      setEmails(data);
    } catch (err) {
      console.error('Error fetching emails:', err);
    }
  }, [filter, source]);

  const fetchStats = useCallback(async () => {
    try {
      const { data } = await api.get('/api/v1/email-training/stats');
      setStats(data);
    } catch (err) {
      console.error('Error fetching stats:', err);
    }
  }, []);

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([fetchEmails(), fetchStats()]);
      setLoading(false);
    };
    loadData();
  }, [fetchEmails, fetchStats]);

  const handleSelectEmail = (email) => {
    setSelectedEmail(email);
    setFeedbackForm({
      is_correct: email.is_correct,
      feedback_type: email.feedback_type || '',
      correct_response: email.correct_response || '',
      feedback_notes: email.feedback_notes || ''
    });
    setMessage(null);
  };

  const handleSubmitFeedback = async () => {
    if (feedbackForm.is_correct === null) {
      setMessage({ type: 'error', text: 'Please select if the response is correct or incorrect' });
      return;
    }

    setSubmitting(true);
    try {
      await api.post(`/api/v1/email-training/emails/${selectedEmail.id}/review`, feedbackForm);
      setMessage({ type: 'success', text: 'Feedback submitted successfully!' });
      await Promise.all([fetchEmails(), fetchStats()]);
      const updatedEmail = { ...selectedEmail, ...feedbackForm };
      setSelectedEmail(updatedEmail);
    } catch (err) {
      const detail = err.response?.data?.detail || err.message;
      setMessage({ type: 'error', text: detail || 'Failed to submit feedback' });
    } finally {
      setSubmitting(false);
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return '';
    return new Date(dateString).toLocaleString();
  };

  const getStatusBadge = (email) => {
    if (email.is_correct === null) return <span className="badge pending">Pending Review</span>;
    if (email.is_correct) return <span className="badge correct">Correct</span>;
    return <span className="badge incorrect">Needs Improvement</span>;
  };

  if (loading) {
    return <div className="ai-email-training loading">Loading...</div>;
  }

  return (
    <div className="ai-email-training">
      <div className="training-header">
        <h2>AI Email Training & Feedback</h2>
        <p>Review AI-generated email responses and provide feedback to improve the system.</p>
      </div>

      {/* Stats Overview */}
      {stats && (
        <div className="stats-overview">
          <div className="stat-card">
            <div className="stat-value">{stats.total_emails}</div>
            <div className="stat-label">Total Conversations</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{stats.pending_review}</div>
            <div className="stat-label">Pending Review</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{stats.correct_count}</div>
            <div className="stat-label">Marked Correct</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{stats.incorrect_count}</div>
            <div className="stat-label">Needs Improvement</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{stats.accuracy_rate}%</div>
            <div className="stat-label">Accuracy Rate</div>
          </div>
        </div>
      )}

      <div className="training-content">
        {/* Email List */}
        <div className="email-list-panel">
          <div className="filter-bar">
            <select value={source} onChange={(e) => setSource(e.target.value)}>
              <option value="all">All Sources</option>
              <option value="inbox">Real Inbox Emails</option>
              <option value="ai_conversations">AI Conversations</option>
            </select>
            <select value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="all">All Status</option>
              <option value="pending">Pending Review</option>
              <option value="correct">Marked Correct</option>
              <option value="incorrect">Needs Improvement</option>
            </select>
            <button onClick={() => { fetchEmails(); fetchStats(); }} className="refresh-btn">
              Refresh
            </button>
          </div>

          <div className="email-list">
            {emails.length === 0 ? (
              <div className="no-emails">No email conversations found</div>
            ) : (
              emails.map(email => (
                <div
                  key={email.id}
                  className={`email-item ${selectedEmail?.id === email.id ? 'selected' : ''}`}
                  onClick={() => handleSelectEmail(email)}
                >
                  <div className="email-item-header">
                    <span className="email-from">{email.from_email}</span>
                    {getStatusBadge(email)}
                  </div>
                  <div className="email-subject">{email.subject || 'No Subject'}</div>
                  <div className="email-preview">
                    {email.user_message.substring(0, 80)}...
                  </div>
                  <div className="email-date">{formatDate(email.created_at)}</div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Email Detail & Feedback */}
        <div className="email-detail-panel">
          {selectedEmail ? (
            <>
              <div className="conversation-view">
                <h3>Conversation</h3>
                {selectedEmail.subject && (
                  <div className="email-subject-header" style={{ marginBottom: '16px', padding: '8px 12px', background: '#f8f9fa', borderRadius: '6px' }}>
                    <strong>Subject:</strong> {selectedEmail.subject}
                  </div>
                )}

                <div className="message user-message">
                  <div className="message-header">
                    <span className="sender">{selectedEmail.from_email}</span>
                    <span className="date">{formatDate(selectedEmail.created_at)}</span>
                  </div>
                  <div className="message-content" style={{ whiteSpace: 'pre-wrap' }}>{selectedEmail.user_message}</div>
                </div>

                {selectedEmail.ai_response && selectedEmail.ai_response !== 'No AI response recorded' && (
                  <div className="message ai-message">
                    <div className="message-header">
                      <span className="sender">Sarah (AI)</span>
                    </div>
                    <div className="message-content" style={{ whiteSpace: 'pre-wrap' }}>{selectedEmail.ai_response}</div>
                  </div>
                )}

                {selectedEmail.detected_topics && selectedEmail.detected_topics.length > 0 && (
                  <div className="detected-topics">
                    <strong>Detected Topics:</strong>
                    {selectedEmail.detected_topics.map((topic, i) => (
                      <span key={i} className="topic-tag">{topic}</span>
                    ))}
                  </div>
                )}

                {selectedEmail.conversation_stage && (
                  <div className="conversation-stage">
                    <strong>Stage:</strong> {selectedEmail.conversation_stage}
                  </div>
                )}
              </div>

              <div className="feedback-section">
                <h3>Provide Feedback</h3>

                {message && (
                  <div className={`message-alert ${message.type}`}>
                    {message.text}
                  </div>
                )}

                <div className="feedback-buttons">
                  <button
                    className={`feedback-btn correct ${feedbackForm.is_correct === true ? 'selected' : ''}`}
                    onClick={() => setFeedbackForm({ ...feedbackForm, is_correct: true })}
                  >
                    Correct Response
                  </button>
                  <button
                    className={`feedback-btn incorrect ${feedbackForm.is_correct === false ? 'selected' : ''}`}
                    onClick={() => setFeedbackForm({ ...feedbackForm, is_correct: false })}
                  >
                    Needs Improvement
                  </button>
                </div>

                {feedbackForm.is_correct === false && (
                  <>
                    <div className="form-group">
                      <label>Issue Type</label>
                      <select
                        value={feedbackForm.feedback_type}
                        onChange={(e) => setFeedbackForm({ ...feedbackForm, feedback_type: e.target.value })}
                      >
                        <option value="">Select issue type...</option>
                        <option value="wrong_answer">Wrong Answer</option>
                        <option value="incomplete">Incomplete Response</option>
                        <option value="tone_issue">Tone/Style Issue</option>
                        <option value="missed_question">Missed Question</option>
                        <option value="other">Other</option>
                      </select>
                    </div>

                    <div className="form-group">
                      <label>What should the AI have said?</label>
                      <textarea
                        value={feedbackForm.correct_response}
                        onChange={(e) => setFeedbackForm({ ...feedbackForm, correct_response: e.target.value })}
                        placeholder="Enter the correct response the AI should have given..."
                        rows={5}
                      />
                    </div>
                  </>
                )}

                <div className="form-group">
                  <label>Additional Notes (optional)</label>
                  <textarea
                    value={feedbackForm.feedback_notes}
                    onChange={(e) => setFeedbackForm({ ...feedbackForm, feedback_notes: e.target.value })}
                    placeholder="Any additional feedback or context..."
                    rows={3}
                  />
                </div>

                <button
                  className="submit-feedback-btn"
                  onClick={handleSubmitFeedback}
                  disabled={submitting || feedbackForm.is_correct === null}
                >
                  {submitting ? 'Submitting...' : 'Submit Feedback'}
                </button>
              </div>
            </>
          ) : (
            <div className="no-selection">
              <p>Select a conversation from the list to review and provide feedback</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default AIEmailTraining;
