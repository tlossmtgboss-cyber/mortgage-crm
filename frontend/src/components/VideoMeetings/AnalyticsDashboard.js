import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './AnalyticsDashboard.css';

const AnalyticsDashboard = ({ userId, recordingId }) => {
  const [analytics, setAnalytics] = useState(null);
  const [recordingAnalytics, setRecordingAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [timeRange, setTimeRange] = useState('30days');
  const [activeTab, setActiveTab] = useState('overview');

  useEffect(() => {
    if (recordingId) {
      loadRecordingAnalytics();
    } else {
      loadUserAnalytics();
    }
  }, [userId, recordingId, timeRange]);

  const loadUserAnalytics = async () => {
    try {
      setLoading(true);
      setError(null);

      let days = 30;
      if (timeRange === '7days') days = 7;
      else if (timeRange === '90days') days = 90;

      const endpoint = userId
        ? `/api/v1/meetings/analytics/user/${userId}?days=${days}`
        : `/api/v1/meetings/analytics/me?days=${days}`;

      const response = await axios.get(endpoint);
      setAnalytics(response.data);
      setLoading(false);
    } catch (err) {
      console.error('Error loading analytics:', err);
      setError('Failed to load analytics');
      setLoading(false);
    }
  };

  const loadRecordingAnalytics = async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await axios.get(
        `/api/v1/meetings/recordings/${recordingId}/analytics`
      );
      setRecordingAnalytics(response.data.analytics);
      setLoading(false);
    } catch (err) {
      console.error('Error loading recording analytics:', err);
      setError('Failed to load recording analytics');
      setLoading(false);
    }
  };

  const formatTime = (seconds) => {
    if (!seconds) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const getEngagementColor = (score) => {
    if (score >= 0.7) return 'positive';
    if (score >= 0.5) return 'neutral';
    return 'negative';
  };

  const getPriorityColor = (priority) => {
    switch (priority) {
      case 'high': return '#ef4444';
      case 'medium': return '#f59e0b';
      case 'low': return '#2D7A52';
      default: return '#6b7280';
    }
  };

  if (loading) {
    return (
      <div className="analytics-loading">
        <div className="loading-spinner"></div>
        <p>Loading analytics...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="analytics-error">
        <p>{error}</p>
        <button onClick={recordingId ? loadRecordingAnalytics : loadUserAnalytics}>
          Retry
        </button>
      </div>
    );
  }

  // Recording-specific analytics view
  if (recordingId && recordingAnalytics) {
    return (
      <div className="analytics-dashboard recording-analytics">
        <div className="analytics-header">
          <h2>Meeting Analytics</h2>
        </div>

        {recordingAnalytics.map((participant, idx) => (
          <div key={idx} className="participant-analytics-card">
            <div className="participant-header">
              <h3>{participant.participant_name || `Participant ${idx + 1}`}</h3>
              <span className={`engagement-badge ${getEngagementColor(participant.engagement_score)}`}>
                {((participant.engagement_score || 0) * 100).toFixed(0)}% Engaged
              </span>
            </div>

            <div className="metrics-grid">
              <div className="metric-card">
                <div className="metric-label">Talk Time</div>
                <div className="metric-value">{formatTime(participant.talk_time_seconds)}</div>
              </div>
              <div className="metric-card">
                <div className="metric-label">Listen Time</div>
                <div className="metric-value">{formatTime(participant.listen_time_seconds)}</div>
              </div>
              <div className="metric-card">
                <div className="metric-label">Questions Asked</div>
                <div className="metric-value">{participant.question_count || 0}</div>
              </div>
              <div className="metric-card">
                <div className="metric-label">Interruptions</div>
                <div className="metric-value">{participant.interruption_count || 0}</div>
              </div>
            </div>

            <div className="analytics-section">
              <h4>Talk-Listen Balance</h4>
              <div className="ratio-bar">
                <div
                  className="ratio-talk"
                  style={{ width: `${(participant.talk_listen_ratio || 0) * 100}%` }}
                >
                  You: {((participant.talk_listen_ratio || 0) * 100).toFixed(0)}%
                </div>
                <div
                  className="ratio-listen"
                  style={{ width: `${(1 - (participant.talk_listen_ratio || 0)) * 100}%` }}
                >
                  Them: {((1 - (participant.talk_listen_ratio || 0)) * 100).toFixed(0)}%
                </div>
              </div>
              <div className="ratio-guidance">
                <span className="ideal-range">Ideal range: 40-50%</span>
              </div>
            </div>

            <div className="metrics-row">
              <div className="metric-small">
                <span className="label">Filler Words</span>
                <span className="value">{participant.filler_word_count || 0}</span>
              </div>
              <div className="metric-small">
                <span className="label">Speaking Pace</span>
                <span className="value">{participant.speaking_pace_wpm || 0} WPM</span>
              </div>
              <div className="metric-small">
                <span className="label">Longest Monologue</span>
                <span className="value">{formatTime(participant.longest_monologue_seconds)}</span>
              </div>
            </div>

            {participant.coaching_recommendations && participant.coaching_recommendations.length > 0 && (
              <div className="coaching-section">
                <h4>Coaching Recommendations</h4>
                <div className="coaching-list">
                  {participant.coaching_recommendations.map((rec, recIdx) => (
                    <div key={recIdx} className="coaching-item">
                      <div className="coaching-header">
                        <span
                          className="priority-badge"
                          style={{ backgroundColor: getPriorityColor(rec.priority) }}
                        >
                          {rec.priority}
                        </span>
                        <span className="category">{rec.category}</span>
                      </div>
                      <p className="recommendation">{rec.recommendation}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    );
  }

  // User aggregate analytics view
  if (!analytics || analytics.meetings_analyzed === 0) {
    return (
      <div className="analytics-empty">
        <div className="empty-icon">📊</div>
        <h3>No Analytics Available Yet</h3>
        <p>Start having meetings to see your performance metrics!</p>
      </div>
    );
  }

  return (
    <div className="analytics-dashboard">
      <div className="analytics-header">
        <h2>Your Performance Analytics</h2>
        <select
          value={timeRange}
          onChange={(e) => setTimeRange(e.target.value)}
          className="time-range-selector"
        >
          <option value="7days">Last 7 Days</option>
          <option value="30days">Last 30 Days</option>
          <option value="90days">Last 90 Days</option>
        </select>
      </div>

      <div className="tab-navigation">
        <button
          className={`tab-button ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button
          className={`tab-button ${activeTab === 'coaching' ? 'active' : ''}`}
          onClick={() => setActiveTab('coaching')}
        >
          Coaching
        </button>
      </div>

      {activeTab === 'overview' && (
        <>
          {/* Key Metrics */}
          <div className="metrics-grid">
            <div className="metric-card highlight">
              <div className="metric-label">Meetings Analyzed</div>
              <div className="metric-value">{analytics.meetings_analyzed}</div>
            </div>

            <div className="metric-card highlight">
              <div className="metric-label">Engagement Score</div>
              <div className="metric-value">
                {((analytics.averages?.engagement_score || 0) * 100).toFixed(0)}%
              </div>
              <div className={`metric-trend ${getEngagementColor(analytics.averages?.engagement_score)}`}>
                {analytics.averages?.engagement_score >= 0.7
                  ? '↑ Great'
                  : analytics.averages?.engagement_score >= 0.5
                  ? '→ Good'
                  : '↓ Needs Work'}
              </div>
            </div>

            <div className="metric-card">
              <div className="metric-label">Talk-Listen Ratio</div>
              <div className="metric-value">
                {((analytics.averages?.talk_listen_ratio || 0) * 100).toFixed(0)}%
              </div>
              <div className="metric-subtitle">Target: 40-50%</div>
            </div>

            <div className="metric-card">
              <div className="metric-label">Questions Per Call</div>
              <div className="metric-value">
                {(analytics.averages?.question_count_per_call || 0).toFixed(1)}
              </div>
              <div className="metric-subtitle">Target: 5-8</div>
            </div>
          </div>

          {/* Talk-Listen Visualization */}
          <div className="analytics-section">
            <h3>Talk-Listen Balance</h3>
            <div className="ratio-bar">
              <div
                className="ratio-talk"
                style={{ width: `${(analytics.averages?.talk_listen_ratio || 0) * 100}%` }}
              >
                You: {((analytics.averages?.talk_listen_ratio || 0) * 100).toFixed(0)}%
              </div>
              <div
                className="ratio-listen"
                style={{ width: `${(1 - (analytics.averages?.talk_listen_ratio || 0)) * 100}%` }}
              >
                Them: {((1 - (analytics.averages?.talk_listen_ratio || 0)) * 100).toFixed(0)}%
              </div>
            </div>
            <div className="ratio-guidance">
              <span className="ideal-range">Ideal range: 40-50%</span>
            </div>
          </div>

          {/* Additional Metrics */}
          <div className="analytics-section">
            <h3>Additional Metrics</h3>
            <div className="metrics-row">
              <div className="metric-small">
                <span className="label">Avg. Interruptions</span>
                <span className="value">
                  {(analytics.averages?.interruption_count_per_call || 0).toFixed(1)}
                </span>
              </div>
              <div className="metric-small">
                <span className="label">Total Filler Words</span>
                <span className="value">{analytics.totals?.total_filler_words || 0}</span>
              </div>
              <div className="metric-small">
                <span className="label">Total Recommendations</span>
                <span className="value">{analytics.totals?.total_recommendations || 0}</span>
              </div>
            </div>
          </div>
        </>
      )}

      {activeTab === 'coaching' && (
        <>
          {/* Coaching Priorities */}
          {analytics.top_coaching_priorities && analytics.top_coaching_priorities.length > 0 ? (
            <div className="analytics-section">
              <h3>Top Coaching Priorities</h3>
              <div className="coaching-list">
                {analytics.top_coaching_priorities.map((priority, idx) => (
                  <div key={idx} className="coaching-priority">
                    <div className="priority-header">
                      <span className="priority-category">{priority.category}</span>
                      <span className="priority-frequency">
                        {priority.frequency} occurrence{priority.frequency !== 1 ? 's' : ''}
                      </span>
                    </div>
                    <p className="priority-recommendation">{priority.latest_recommendation}</p>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="empty-coaching">
              <p>No coaching recommendations yet. Keep having meetings to get personalized feedback!</p>
            </div>
          )}

          {/* Recommendations by Category */}
          {analytics.recommendations_by_category && Object.keys(analytics.recommendations_by_category).length > 0 && (
            <div className="analytics-section">
              <h3>Recommendations by Category</h3>
              <div className="category-breakdown">
                {Object.entries(analytics.recommendations_by_category).map(([category, count]) => (
                  <div key={category} className="category-item">
                    <span className="category-name">{category}</span>
                    <div className="category-bar-container">
                      <div
                        className="category-bar"
                        style={{
                          width: `${(count / Math.max(...Object.values(analytics.recommendations_by_category))) * 100}%`
                        }}
                      ></div>
                    </div>
                    <span className="category-count">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* Comparison Section */}
      <div className="analytics-section comparison-section">
        <h3>How You Compare</h3>
        <div className="comparison-grid">
          <div className="comparison-item">
            <span className="comparison-label">Your Engagement</span>
            <span className="comparison-value">
              {((analytics.averages?.engagement_score || 0) * 100).toFixed(0)}%
            </span>
          </div>
          <div className="comparison-item">
            <span className="comparison-label">Top Performer Avg</span>
            <span className="comparison-value target">85%</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AnalyticsDashboard;
