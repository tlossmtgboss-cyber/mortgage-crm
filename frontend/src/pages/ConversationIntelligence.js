/**
 * Conversation Intelligence Dashboard
 *
 * Manager view for voice call analysis platform:
 * - Team metrics and performance
 * - Call recordings list
 * - QA scorecards
 * - Coaching management
 * - Compliance monitoring
 */

import { useState, useEffect, useMemo, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from '../utils/toast';
import {
  useTeamDashboard,
  useRecordings,
  useCoachingClips,
  useCoachingAssignments,
  useComplianceDashboard,
  useQARubrics,
} from '../hooks/useConversationIntelligence';
import { exportApi, summaryApi } from '../services/conversationIntelligenceApi';
import './ConversationIntelligence.css';

function ConversationIntelligence() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState(searchParams.get('tab') || 'overview');
  const [dateRange, setDateRange] = useState({
    startDate: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
    endDate: new Date().toISOString().split('T')[0],
  });
  const [recordingFilters, setRecordingFilters] = useState({
    status: '',
    agentId: '',
    limit: 20,
    offset: 0,
  });

  // Data hooks
  const { dashboard: teamDashboard, loading: teamLoading } = useTeamDashboard({
    startDate: dateRange.startDate,
    endDate: dateRange.endDate,
  });

  const { recordings, total: recordingsTotal, loading: recordingsLoading, refetch: refetchRecordings } = useRecordings({
    ...recordingFilters,
    startDate: dateRange.startDate,
    endDate: dateRange.endDate,
  });

  const { clips, loading: clipsLoading } = useCoachingClips({ limit: 10 });
  const { assignments, loading: assignmentsLoading } = useCoachingAssignments({ limit: 10 });
  const { dashboard: complianceDashboard, loading: complianceLoading } = useComplianceDashboard({
    startDate: dateRange.startDate,
    endDate: dateRange.endDate,
  });
  const { rubrics } = useQARubrics();

  // Summaries state
  const [summaryFeed, setSummaryFeed] = useState([]);
  const [summaryStats, setSummaryStats] = useState(null);
  const [summariesLoading, setSummariesLoading] = useState(false);
  const [summaryFilter, setSummaryFilter] = useState({ outcome: '', sentiment: '' });
  const [processingPending, setProcessingPending] = useState(false);

  // Fetch summaries when tab is active
  const fetchSummaries = useCallback(async () => {
    setSummariesLoading(true);
    try {
      const [feedRes, statsRes] = await Promise.all([
        summaryApi.getFeed({
          outcome: summaryFilter.outcome || undefined,
          sentiment: summaryFilter.sentiment || undefined,
          limit: 30,
        }),
        summaryApi.getStats({ days: 30 }),
      ]);
      setSummaryFeed(feedRes.feed || []);
      setSummaryStats(statsRes);
    } catch (error) {
      console.error('Failed to fetch summaries:', error);
    } finally {
      setSummariesLoading(false);
    }
  }, [summaryFilter]);

  useEffect(() => {
    if (activeTab === 'summaries') {
      fetchSummaries();
    }
  }, [activeTab, fetchSummaries]);

  // Handle processing pending summaries
  const handleProcessPending = async () => {
    setProcessingPending(true);
    try {
      const result = await summaryApi.processPending({ limit: 50 });
      toast.success(`Processed ${result.processed} summaries. ${result.errors?.length || 0} errors.`);
      fetchSummaries();
    } catch (error) {
      console.error('Failed to process pending:', error);
      toast.error('Failed to process pending summaries');
    } finally {
      setProcessingPending(false);
    }
  };

  // Update URL when tab changes
  useEffect(() => {
    setSearchParams({ tab: activeTab });
  }, [activeTab, setSearchParams]);

  // Format helpers
  const formatDuration = (seconds) => {
    if (!seconds) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const formatDate = (dateString) => {
    if (!dateString) return '-';
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getGradeColor = (grade) => {
    const colors = {
      A: '#22c55e',
      B: '#84cc16',
      C: '#eab308',
      D: '#f97316',
      F: '#ef4444',
    };
    return colors[grade] || '#6b7280';
  };

  const getSeverityColor = (severity) => {
    const colors = {
      critical: '#ef4444',
      high: '#f97316',
      medium: '#eab308',
      low: '#22c55e',
    };
    return colors[severity] || '#6b7280';
  };

  const getStatusBadge = (status) => {
    const statusConfig = {
      pending: { label: 'Pending', color: '#6b7280' },
      uploading: { label: 'Uploading', color: '#3b82f6' },
      uploaded: { label: 'Uploaded', color: '#3b82f6' },
      transcribing: { label: 'Transcribing', color: '#8b5cf6' },
      transcribed: { label: 'Transcribed', color: '#8b5cf6' },
      analyzing: { label: 'Analyzing', color: '#f59e0b' },
      analyzed: { label: 'Analyzed', color: '#f59e0b' },
      scoring: { label: 'Scoring', color: '#10b981' },
      scored: { label: 'Scored', color: '#22c55e' },
      completed: { label: 'Complete', color: '#22c55e' },
      failed: { label: 'Failed', color: '#ef4444' },
    };
    return statusConfig[status] || { label: status, color: '#6b7280' };
  };

  // Export handler
  const handleExport = async (format) => {
    try {
      const data = await exportApi.exportRecordings(format, {
        startDate: dateRange.startDate,
        endDate: dateRange.endDate,
        agentId: recordingFilters.agentId ? parseInt(recordingFilters.agentId) : undefined,
      });
      if (format === 'csv') {
        exportApi.downloadCsv(data, `recordings_${dateRange.startDate}_${dateRange.endDate}.csv`);
      }
    } catch (error) {
      console.error('Export failed:', error);
    }
  };

  // Render overview tab
  const renderOverview = () => (
    <div className="ci-overview">
      {/* Key Metrics */}
      <div className="ci-metrics-grid">
        <div className="ci-metric-card">
          <div className="ci-metric-icon">
            <i className="fas fa-phone-volume"></i>
          </div>
          <div className="ci-metric-content">
            <span className="ci-metric-value">{teamDashboard?.metrics?.total_calls || 0}</span>
            <span className="ci-metric-label">Total Calls</span>
          </div>
        </div>
        <div className="ci-metric-card">
          <div className="ci-metric-icon">
            <i className="fas fa-clock"></i>
          </div>
          <div className="ci-metric-content">
            <span className="ci-metric-value">
              {formatDuration(teamDashboard?.metrics?.avg_duration_seconds || 0)}
            </span>
            <span className="ci-metric-label">Avg Duration</span>
          </div>
        </div>
        <div className="ci-metric-card">
          <div className="ci-metric-icon">
            <i className="fas fa-chart-line"></i>
          </div>
          <div className="ci-metric-content">
            <span className="ci-metric-value">{teamDashboard?.qa_summary?.avg_score?.toFixed(1) || 0}%</span>
            <span className="ci-metric-label">Avg QA Score</span>
          </div>
        </div>
        <div className="ci-metric-card">
          <div className="ci-metric-icon">
            <i className="fas fa-exclamation-triangle"></i>
          </div>
          <div className="ci-metric-content">
            <span className="ci-metric-value">{complianceDashboard?.total_violations || 0}</span>
            <span className="ci-metric-label">Compliance Issues</span>
          </div>
        </div>
      </div>

      {/* Grade Distribution & Top Performers */}
      <div className="ci-overview-row">
        <div className="ci-card ci-grade-distribution">
          <h3>QA Grade Distribution</h3>
          <div className="ci-grade-bars">
            {['A', 'B', 'C', 'D/F'].map((grade) => {
              const count = teamDashboard?.qa_summary?.grade_distribution?.[grade] || 0;
              const total = Object.values(teamDashboard?.qa_summary?.grade_distribution || {}).reduce((a, b) => a + b, 0) || 1;
              const percentage = (count / total) * 100;
              return (
                <div key={grade} className="ci-grade-bar-item">
                  <span className="ci-grade-label">{grade}</span>
                  <div className="ci-grade-bar-container">
                    <div
                      className="ci-grade-bar"
                      style={{
                        width: `${percentage}%`,
                        backgroundColor: getGradeColor(grade.replace('/F', '')),
                      }}
                    ></div>
                  </div>
                  <span className="ci-grade-count">{count}</span>
                </div>
              );
            })}
          </div>
        </div>

        <div className="ci-card ci-top-performers">
          <h3>Top Performers</h3>
          <div className="ci-performers-list">
            {teamDashboard?.top_performers?.slice(0, 5).map((performer, index) => (
              <div key={performer.agent_id} className="ci-performer-item">
                <span className="ci-performer-rank">#{index + 1}</span>
                <span className="ci-performer-name">{performer.name || performer.email}</span>
                <span className="ci-performer-calls">{performer.call_count} calls</span>
                {performer.avg_score && (
                  <span
                    className="ci-performer-score"
                    style={{ backgroundColor: getGradeColor(performer.avg_score >= 90 ? 'A' : performer.avg_score >= 80 ? 'B' : 'C') }}
                  >
                    {performer.avg_score.toFixed(0)}%
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Recent Activity */}
      <div className="ci-card ci-recent-activity">
        <h3>Recent Recordings</h3>
        <div className="ci-recordings-mini-list">
          {recordings.slice(0, 5).map((recording) => {
            const status = getStatusBadge(recording.status);
            return (
              <div
                key={recording.id}
                className="ci-recording-mini-item"
                onClick={() => navigate(`/conversation-intelligence/recordings/${recording.id}`)}
              >
                <div className="ci-recording-mini-icon">
                  <i className={recording.direction === 'inbound' ? 'fas fa-phone-alt' : 'fas fa-phone-volume'}></i>
                </div>
                <div className="ci-recording-mini-info">
                  <span className="ci-recording-mini-agent">{recording.agent_name || `Agent #${recording.agent_id}`}</span>
                  <span className="ci-recording-mini-time">{formatDate(recording.created_at)}</span>
                </div>
                <span className="ci-recording-mini-duration">{formatDuration(recording.duration_seconds)}</span>
                <span className="ci-status-badge" style={{ backgroundColor: status.color }}>
                  {status.label}
                </span>
              </div>
            );
          })}
        </div>
        <button className="ci-view-all-btn" onClick={() => setActiveTab('recordings')}>
          View All Recordings <i className="fas fa-arrow-right"></i>
        </button>
      </div>
    </div>
  );

  // Render recordings tab
  const renderRecordings = () => (
    <div className="ci-recordings">
      <div className="ci-recordings-header">
        <div className="ci-recordings-filters">
          <select
            value={recordingFilters.status}
            onChange={(e) => setRecordingFilters({ ...recordingFilters, status: e.target.value, offset: 0 })}
          >
            <option value="">All Statuses</option>
            <option value="pending">Pending</option>
            <option value="transcribed">Transcribed</option>
            <option value="analyzed">Analyzed</option>
            <option value="scored">Scored</option>
            <option value="failed">Failed</option>
          </select>
          <input
            type="number"
            placeholder="Agent ID"
            value={recordingFilters.agentId}
            onChange={(e) => setRecordingFilters({ ...recordingFilters, agentId: e.target.value, offset: 0 })}
          />
        </div>
        <div className="ci-recordings-actions">
          <button className="ci-btn ci-btn-secondary" onClick={() => handleExport('csv')}>
            <i className="fas fa-download"></i> Export CSV
          </button>
          <button className="ci-btn ci-btn-primary" onClick={() => refetchRecordings()}>
            <i className="fas fa-sync-alt"></i> Refresh
          </button>
        </div>
      </div>

      <div className="ci-recordings-table-container">
        <table className="ci-recordings-table">
          <thead>
            <tr>
              <th>Date/Time</th>
              <th>Agent</th>
              <th>Direction</th>
              <th>Duration</th>
              <th>Status</th>
              <th>QA Score</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {recordingsLoading ? (
              <tr>
                <td colSpan="7" className="ci-loading-cell">
                  <i className="fas fa-spinner fa-spin"></i> Loading...
                </td>
              </tr>
            ) : recordings.length === 0 ? (
              <tr>
                <td colSpan="7" className="ci-empty-cell">No recordings found</td>
              </tr>
            ) : (
              recordings.map((recording) => {
                const status = getStatusBadge(recording.status);
                return (
                  <tr key={recording.id}>
                    <td>{formatDate(recording.created_at)}</td>
                    <td>{recording.agent_name || `Agent #${recording.agent_id}`}</td>
                    <td>
                      <i className={recording.direction === 'inbound' ? 'fas fa-phone-alt' : 'fas fa-phone-volume'}></i>
                      {' '}{recording.direction}
                    </td>
                    <td>{formatDuration(recording.duration_seconds)}</td>
                    <td>
                      <span className="ci-status-badge" style={{ backgroundColor: status.color }}>
                        {status.label}
                      </span>
                    </td>
                    <td>
                      {recording.qa_score ? (
                        <span
                          className="ci-qa-score"
                          style={{ backgroundColor: getGradeColor(recording.qa_grade) }}
                        >
                          {recording.qa_score}%
                        </span>
                      ) : (
                        '-'
                      )}
                    </td>
                    <td>
                      <button
                        className="ci-btn ci-btn-icon"
                        onClick={() => navigate(`/conversation-intelligence/recordings/${recording.id}`)}
                        title="View Details"
                      >
                        <i className="fas fa-eye"></i>
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="ci-pagination">
        <span className="ci-pagination-info">
          Showing {recordingFilters.offset + 1}-{Math.min(recordingFilters.offset + recordingFilters.limit, recordingsTotal)} of {recordingsTotal}
        </span>
        <div className="ci-pagination-buttons">
          <button
            className="ci-btn ci-btn-secondary"
            disabled={recordingFilters.offset === 0}
            onClick={() => setRecordingFilters({ ...recordingFilters, offset: Math.max(0, recordingFilters.offset - recordingFilters.limit) })}
          >
            <i className="fas fa-chevron-left"></i> Previous
          </button>
          <button
            className="ci-btn ci-btn-secondary"
            disabled={recordingFilters.offset + recordingFilters.limit >= recordingsTotal}
            onClick={() => setRecordingFilters({ ...recordingFilters, offset: recordingFilters.offset + recordingFilters.limit })}
          >
            Next <i className="fas fa-chevron-right"></i>
          </button>
        </div>
      </div>
    </div>
  );

  // Render coaching tab
  const renderCoaching = () => (
    <div className="ci-coaching">
      <div className="ci-coaching-row">
        {/* Coaching Clips */}
        <div className="ci-card ci-coaching-clips">
          <div className="ci-card-header">
            <h3>Coaching Clips</h3>
            <button className="ci-btn ci-btn-sm ci-btn-primary">
              <i className="fas fa-plus"></i> New Clip
            </button>
          </div>
          <div className="ci-clips-list">
            {clipsLoading ? (
              <div className="ci-loading">
                <i className="fas fa-spinner fa-spin"></i>
              </div>
            ) : clips.length === 0 ? (
              <p className="ci-empty">No coaching clips yet</p>
            ) : (
              clips.map((clip) => (
                <div key={clip.clip_id} className="ci-clip-item">
                  <div className="ci-clip-icon">
                    <i className="fas fa-play-circle"></i>
                  </div>
                  <div className="ci-clip-info">
                    <span className="ci-clip-title">{clip.title}</span>
                    <span className="ci-clip-meta">
                      {formatDuration(clip.duration_seconds)} | {clip.category}
                    </span>
                  </div>
                  <span className="ci-clip-views">
                    <i className="fas fa-eye"></i> {clip.view_count}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Assignments */}
        <div className="ci-card ci-coaching-assignments">
          <div className="ci-card-header">
            <h3>Active Assignments</h3>
            <button className="ci-btn ci-btn-sm ci-btn-primary">
              <i className="fas fa-plus"></i> New Assignment
            </button>
          </div>
          <div className="ci-assignments-list">
            {assignmentsLoading ? (
              <div className="ci-loading">
                <i className="fas fa-spinner fa-spin"></i>
              </div>
            ) : assignments.length === 0 ? (
              <p className="ci-empty">No active assignments</p>
            ) : (
              assignments.map((assignment) => (
                <div key={assignment.assignment_id} className="ci-assignment-item">
                  <div className="ci-assignment-status">
                    <i className={assignment.status === 'completed' ? 'fas fa-check-circle' : 'fas fa-clock'}></i>
                  </div>
                  <div className="ci-assignment-info">
                    <span className="ci-assignment-title">{assignment.title}</span>
                    <span className="ci-assignment-meta">
                      Assigned to: {assignment.assigned_to_name || `User #${assignment.assigned_to}`}
                    </span>
                  </div>
                  {assignment.due_date && (
                    <span className={`ci-assignment-due ${new Date(assignment.due_date) < new Date() ? 'overdue' : ''}`}>
                      Due: {formatDate(assignment.due_date)}
                    </span>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );

  // Render compliance tab
  const renderCompliance = () => (
    <div className="ci-compliance">
      {/* Severity Summary */}
      <div className="ci-compliance-summary">
        {['critical', 'high', 'medium', 'low'].map((severity) => (
          <div key={severity} className="ci-severity-card" style={{ borderColor: getSeverityColor(severity) }}>
            <span className="ci-severity-count">
              {complianceDashboard?.severity_summary?.[severity] || 0}
            </span>
            <span className="ci-severity-label">{severity}</span>
          </div>
        ))}
      </div>

      {/* Violations by Rule */}
      <div className="ci-card ci-violations-by-rule">
        <h3>Violations by Rule</h3>
        <div className="ci-violations-list">
          {complianceLoading ? (
            <div className="ci-loading">
              <i className="fas fa-spinner fa-spin"></i>
            </div>
          ) : complianceDashboard?.violations_by_rule?.length === 0 ? (
            <p className="ci-empty">No violations in this period</p>
          ) : (
            complianceDashboard?.violations_by_rule?.map((rule) => (
              <div key={rule.rule_id} className="ci-violation-rule-item">
                <span className="ci-violation-rule-name">{rule.rule_name}</span>
                <span className="ci-violation-severity" style={{ color: getSeverityColor(rule.severity) }}>
                  {rule.severity}
                </span>
                <span className="ci-violation-count">{rule.count} violations</span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Recent Violations */}
      <div className="ci-card ci-recent-violations">
        <h3>Recent Violations</h3>
        <table className="ci-violations-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Rule</th>
              <th>Severity</th>
              <th>Recording</th>
              <th>Reviewed</th>
            </tr>
          </thead>
          <tbody>
            {complianceDashboard?.recent_violations?.map((violation) => (
              <tr key={violation.id}>
                <td>{formatDate(violation.detected_at)}</td>
                <td>{violation.rule_name}</td>
                <td>
                  <span style={{ color: getSeverityColor(violation.severity) }}>
                    {violation.severity}
                  </span>
                </td>
                <td>
                  <button
                    className="ci-btn ci-btn-link"
                    onClick={() => navigate(`/conversation-intelligence/recordings/${violation.recording_id}`)}
                  >
                    View
                  </button>
                </td>
                <td>
                  <i className={violation.reviewed ? 'fas fa-check-circle text-green' : 'fas fa-times-circle text-gray'}></i>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );

  // Render summaries tab
  const renderSummaries = () => {
    const getSentimentIcon = (sentiment) => {
      switch (sentiment) {
        case 'positive': return { icon: 'fas fa-smile', color: '#22c55e' };
        case 'negative': return { icon: 'fas fa-frown', color: '#ef4444' };
        case 'mixed': return { icon: 'fas fa-meh', color: '#f59e0b' };
        default: return { icon: 'fas fa-meh-blank', color: '#6b7280' };
      }
    };

    const getOutcomeIcon = (outcome) => {
      switch (outcome) {
        case 'successful': return { icon: 'fas fa-check-circle', color: '#22c55e' };
        case 'callback_needed': return { icon: 'fas fa-phone-alt', color: '#f59e0b' };
        case 'escalation': return { icon: 'fas fa-exclamation-triangle', color: '#ef4444' };
        case 'no_answer': return { icon: 'fas fa-phone-slash', color: '#6b7280' };
        default: return { icon: 'fas fa-question-circle', color: '#6b7280' };
      }
    };

    const getUrgencyBadge = (urgency) => {
      const colors = {
        urgent: '#ef4444',
        normal: '#3b82f6',
        low: '#6b7280',
      };
      return colors[urgency] || colors.normal;
    };

    return (
      <div className="ci-summaries">
        {/* Summary Stats */}
        <div className="ci-summary-stats">
          <div className="ci-summary-stat-card">
            <div className="ci-stat-icon" style={{ backgroundColor: '#3b82f6' }}>
              <i className="fas fa-phone-volume"></i>
            </div>
            <div className="ci-stat-content">
              <span className="ci-stat-value">{summaryStats?.total_calls || 0}</span>
              <span className="ci-stat-label">Calls Summarized</span>
            </div>
          </div>
          <div className="ci-summary-stat-card">
            <div className="ci-stat-icon" style={{ backgroundColor: '#22c55e' }}>
              <i className="fas fa-check-circle"></i>
            </div>
            <div className="ci-stat-content">
              <span className="ci-stat-value">{summaryStats?.successful_rate || 0}%</span>
              <span className="ci-stat-label">Successful Calls</span>
            </div>
          </div>
          <div className="ci-summary-stat-card">
            <div className="ci-stat-icon" style={{ backgroundColor: '#22c55e' }}>
              <i className="fas fa-smile"></i>
            </div>
            <div className="ci-stat-content">
              <span className="ci-stat-value">{summaryStats?.positive_sentiment_rate || 0}%</span>
              <span className="ci-stat-label">Positive Sentiment</span>
            </div>
          </div>
          <div className="ci-summary-stat-card">
            <div className="ci-stat-icon" style={{ backgroundColor: '#f59e0b' }}>
              <i className="fas fa-phone-alt"></i>
            </div>
            <div className="ci-stat-content">
              <span className="ci-stat-value">{summaryStats?.callbacks_needed || 0}</span>
              <span className="ci-stat-label">Callbacks Needed</span>
            </div>
          </div>
        </div>

        {/* Filters and Actions */}
        <div className="ci-summary-controls">
          <div className="ci-summary-filters">
            <select
              value={summaryFilter.outcome}
              onChange={(e) => setSummaryFilter({ ...summaryFilter, outcome: e.target.value })}
            >
              <option value="">All Outcomes</option>
              <option value="successful">Successful</option>
              <option value="callback_needed">Callback Needed</option>
              <option value="escalation">Escalation</option>
              <option value="no_answer">No Answer</option>
            </select>
            <select
              value={summaryFilter.sentiment}
              onChange={(e) => setSummaryFilter({ ...summaryFilter, sentiment: e.target.value })}
            >
              <option value="">All Sentiment</option>
              <option value="positive">Positive</option>
              <option value="neutral">Neutral</option>
              <option value="negative">Negative</option>
              <option value="mixed">Mixed</option>
            </select>
          </div>
          <div className="ci-summary-actions">
            <button
              className="ci-btn ci-btn-secondary"
              onClick={handleProcessPending}
              disabled={processingPending}
            >
              {processingPending ? (
                <><i className="fas fa-spinner fa-spin"></i> Processing...</>
              ) : (
                <><i className="fas fa-magic"></i> Generate Pending</>
              )}
            </button>
            <button className="ci-btn ci-btn-primary" onClick={fetchSummaries}>
              <i className="fas fa-sync-alt"></i> Refresh
            </button>
          </div>
        </div>

        {/* Summary Feed */}
        <div className="ci-summary-feed">
          {summariesLoading ? (
            <div className="ci-loading-full">
              <i className="fas fa-spinner fa-spin"></i>
              <span>Loading summaries...</span>
            </div>
          ) : summaryFeed.length === 0 ? (
            <div className="ci-empty-state">
              <i className="fas fa-file-alt"></i>
              <h3>No Summaries Yet</h3>
              <p>Click "Generate Pending" to create AI summaries for recorded calls</p>
            </div>
          ) : (
            summaryFeed.map((summary) => {
              const sentiment = getSentimentIcon(summary.customer_sentiment);
              const outcome = getOutcomeIcon(summary.call_outcome);
              return (
                <div
                  key={summary.id}
                  className="ci-summary-card"
                  onClick={() => navigate(`/conversation-intelligence/recordings/${summary.recording_id}`)}
                >
                  <div className="ci-summary-header">
                    <div className="ci-summary-agent">
                      <div className="ci-agent-avatar">
                        {summary.agent?.name?.charAt(0) || 'A'}
                      </div>
                      <div className="ci-agent-info">
                        <span className="ci-agent-name">{summary.agent?.name || 'Unknown Agent'}</span>
                        <span className="ci-call-time">
                          {formatDate(summary.generated_at)} • {formatDuration(summary.duration_seconds)}
                          <span className="ci-call-direction">
                            <i className={summary.direction === 'inbound' ? 'fas fa-arrow-down' : 'fas fa-arrow-up'}></i>
                            {summary.direction}
                          </span>
                        </span>
                      </div>
                    </div>
                    <div className="ci-summary-badges">
                      <span
                        className="ci-sentiment-badge"
                        style={{ color: sentiment.color }}
                        title={`Sentiment: ${summary.customer_sentiment}`}
                      >
                        <i className={sentiment.icon}></i>
                      </span>
                      <span
                        className="ci-outcome-badge"
                        style={{ backgroundColor: outcome.color }}
                        title={`Outcome: ${summary.call_outcome}`}
                      >
                        <i className={outcome.icon}></i>
                        {summary.call_outcome?.replace('_', ' ')}
                      </span>
                      {summary.customer_urgency && summary.customer_urgency !== 'normal' && (
                        <span
                          className="ci-urgency-badge"
                          style={{ backgroundColor: getUrgencyBadge(summary.customer_urgency) }}
                        >
                          {summary.customer_urgency}
                        </span>
                      )}
                    </div>
                  </div>
                  {summary.customer_name && (
                    <div className="ci-summary-customer">
                      <i className="fas fa-user"></i>
                      <span>{summary.customer_name}</span>
                    </div>
                  )}
                  <div className="ci-summary-content">
                    <p className="ci-one-liner">{summary.one_liner}</p>
                  </div>
                  <div className="ci-summary-footer">
                    <span className="ci-view-details">
                      View full summary <i className="fas fa-arrow-right"></i>
                    </span>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    );
  };

  // Render settings tab
  const renderSettings = () => (
    <div className="ci-settings">
      <div className="ci-card">
        <h3>QA Rubrics</h3>
        <p>Manage scoring criteria for call quality assessments.</p>
        <div className="ci-rubrics-list">
          {rubrics.map((rubric) => (
            <div key={rubric.id} className="ci-rubric-item">
              <div className="ci-rubric-info">
                <span className="ci-rubric-name">{rubric.name}</span>
                <span className="ci-rubric-meta">{rubric.category} | Max Score: {rubric.max_total_score}</span>
              </div>
              {rubric.is_default && <span className="ci-rubric-default">Default</span>}
            </div>
          ))}
        </div>
      </div>

      <div className="ci-card">
        <h3>Transcription Settings</h3>
        <p>Configure transcription providers and options.</p>
        <div className="ci-settings-form">
          <label>
            Primary Provider
            <select defaultValue="deepgram">
              <option value="deepgram">Deepgram</option>
              <option value="assemblyai">AssemblyAI</option>
              <option value="whisper">OpenAI Whisper</option>
            </select>
          </label>
          <label>
            <input type="checkbox" defaultChecked />
            Enable speaker diarization
          </label>
          <label>
            <input type="checkbox" defaultChecked />
            Auto-transcribe new recordings
          </label>
        </div>
      </div>

      <div className="ci-card">
        <h3>Real-Time Assist</h3>
        <p>Configure live coaching prompts and triggers.</p>
        <div className="ci-settings-form">
          <label>
            <input type="checkbox" defaultChecked />
            Enable objection handling suggestions
          </label>
          <label>
            <input type="checkbox" defaultChecked />
            Enable compliance reminders
          </label>
          <label>
            <input type="checkbox" defaultChecked />
            Enable discovery prompts
          </label>
          <label>
            <input type="checkbox" defaultChecked />
            Enable sentiment alerts
          </label>
        </div>
      </div>
    </div>
  );

  return (
    <div className="ci-dashboard">
      {/* Header */}
      <div className="ci-header">
        <div className="ci-header-title">
          <h1>
            <i className="fas fa-headset"></i>
            Conversation Intelligence
          </h1>
          <p>Voice call analysis, QA scoring, and coaching</p>
        </div>
        <div className="ci-header-actions">
          <div className="ci-date-range">
            <input
              type="date"
              value={dateRange.startDate}
              onChange={(e) => setDateRange({ ...dateRange, startDate: e.target.value })}
            />
            <span>to</span>
            <input
              type="date"
              value={dateRange.endDate}
              onChange={(e) => setDateRange({ ...dateRange, endDate: e.target.value })}
            />
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="ci-tabs">
        {[
          { id: 'overview', label: 'Overview', icon: 'fas fa-chart-pie' },
          { id: 'summaries', label: 'AI Summaries', icon: 'fas fa-magic' },
          { id: 'recordings', label: 'Recordings', icon: 'fas fa-record-vinyl' },
          { id: 'coaching', label: 'Coaching', icon: 'fas fa-graduation-cap' },
          { id: 'compliance', label: 'Compliance', icon: 'fas fa-shield-alt' },
          { id: 'settings', label: 'Settings', icon: 'fas fa-cog' },
        ].map((tab) => (
          <button
            key={tab.id}
            className={`ci-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            <i className={tab.icon}></i>
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="ci-content">
        {teamLoading && activeTab === 'overview' ? (
          <div className="ci-loading-full">
            <i className="fas fa-spinner fa-spin"></i>
            <span>Loading dashboard...</span>
          </div>
        ) : (
          <>
            {activeTab === 'overview' && renderOverview()}
            {activeTab === 'summaries' && renderSummaries()}
            {activeTab === 'recordings' && renderRecordings()}
            {activeTab === 'coaching' && renderCoaching()}
            {activeTab === 'compliance' && renderCompliance()}
            {activeTab === 'settings' && renderSettings()}
          </>
        )}
      </div>
    </div>
  );
}

export default ConversationIntelligence;
