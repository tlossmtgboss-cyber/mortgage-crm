/**
 * URLA Call Intelligence Page
 *
 * Dashboard for URLA voice agent call intelligence:
 * - Dashboard: Overview metrics and recent sessions
 * - Sessions: List of URLA agent calls with detail expansion
 * - Briefings: LO briefings generated from calls
 * - Analytics: Charts for trends, drop-off, quality, and calling patterns
 */

import React, { useState, useEffect, useCallback } from 'react';
import { toast } from '../utils/toast';
import { urlaCallIntelligenceApi } from '../services/urlaCallIntelligenceApi';
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';

// ─── Color Palette ───────────────────────────────────────────────
const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444', '#06b6d4'];

const STATUS_STYLES = {
  completed: { bg: '#dcfce7', color: '#166534', label: 'Completed' },
  in_progress: { bg: '#fef3c7', color: '#92400e', label: 'In Progress' },
  abandoned: { bg: '#fee2e2', color: '#991b1b', label: 'Abandoned' },
};

// ─── Style Objects (matching CallIntelligencePage.css patterns) ──
const styles = {
  page: {
    padding: 24,
    maxWidth: 1600,
    margin: '0 auto',
    minHeight: 'calc(100vh - 80px)',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 24,
  },
  headerTitle: {
    margin: '0 0 4px',
    fontSize: '1.75rem',
    fontWeight: 600,
    color: '#111827',
  },
  headerSub: {
    margin: 0,
    color: '#6b7280',
    fontSize: '0.875rem',
  },
  headerActions: {
    display: 'flex',
    gap: 12,
  },
  refreshBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '8px 16px',
    border: '1px solid #e5e7eb',
    background: 'white',
    borderRadius: 8,
    fontSize: '0.875rem',
    color: '#374151',
    cursor: 'pointer',
  },
  tabs: {
    display: 'flex',
    gap: 4,
    padding: 4,
    background: '#f3f4f6',
    borderRadius: 12,
    marginBottom: 24,
  },
  tab: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '10px 20px',
    border: 'none',
    background: 'transparent',
    borderRadius: 8,
    fontSize: '0.875rem',
    fontWeight: 500,
    color: '#6b7280',
    cursor: 'pointer',
    transition: 'all 0.2s',
  },
  tabActive: {
    background: 'white',
    color: '#111827',
    boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
  },
  tabBadge: {
    background: '#3b82f6',
    color: 'white',
    fontSize: '0.7rem',
    padding: '2px 6px',
    borderRadius: 10,
    minWidth: 20,
    textAlign: 'center',
  },
  content: {
    minHeight: 500,
  },
  loading: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '80px 20px',
    color: '#6b7280',
  },
  spinner: {
    width: 40,
    height: 40,
    border: '3px solid #e5e7eb',
    borderTopColor: '#3b82f6',
    borderRadius: '50%',
    marginBottom: 16,
    animation: 'urla-spin 1s linear infinite',
  },
  // Metric cards
  metricsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(5, 1fr)',
    gap: 16,
    marginBottom: 24,
  },
  metricCard: {
    background: 'white',
    border: '1px solid #e5e7eb',
    borderRadius: 12,
    padding: 20,
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
  },
  metricIcon: {
    width: 40,
    height: 40,
    borderRadius: 10,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  metricValue: {
    fontSize: '2rem',
    fontWeight: 600,
    color: '#111827',
    lineHeight: 1,
  },
  metricLabel: {
    fontSize: '0.875rem',
    color: '#6b7280',
  },
  // Sections
  section: {
    background: 'white',
    border: '1px solid #e5e7eb',
    borderRadius: 12,
    padding: 20,
    marginBottom: 24,
  },
  sectionHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  sectionTitle: {
    margin: 0,
    fontSize: '1rem',
    fontWeight: 600,
    color: '#111827',
  },
  // Table
  table: {
    width: '100%',
    borderCollapse: 'collapse',
  },
  th: {
    textAlign: 'left',
    padding: '10px 12px',
    fontSize: '0.75rem',
    fontWeight: 600,
    color: '#6b7280',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    borderBottom: '2px solid #e5e7eb',
  },
  td: {
    padding: '12px',
    fontSize: '0.875rem',
    color: '#374151',
    borderBottom: '1px solid #f3f4f6',
  },
  tr: {
    cursor: 'pointer',
    transition: 'background 0.15s',
  },
  // Status badge
  statusBadge: {
    display: 'inline-block',
    padding: '4px 8px',
    borderRadius: 4,
    fontSize: '0.7rem',
    fontWeight: 500,
  },
  // Expanded row
  expandedRow: {
    background: '#f9fafb',
    padding: 20,
    borderBottom: '1px solid #e5e7eb',
  },
  expandedGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, 1fr)',
    gap: 16,
    marginBottom: 16,
  },
  expandedCard: {
    background: 'white',
    border: '1px solid #e5e7eb',
    borderRadius: 8,
    padding: 16,
  },
  // Briefings
  briefingCard: {
    background: 'white',
    border: '1px solid #e5e7eb',
    borderRadius: 12,
    padding: 20,
    marginBottom: 12,
    cursor: 'pointer',
    transition: 'all 0.2s',
  },
  briefingHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 12,
  },
  briefingActions: {
    display: 'flex',
    gap: 8,
    marginTop: 12,
  },
  actionBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '8px 16px',
    border: '1px solid #e5e7eb',
    background: 'white',
    borderRadius: 6,
    fontSize: '0.8rem',
    fontWeight: 500,
    color: '#374151',
    cursor: 'pointer',
  },
  primaryBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '8px 16px',
    border: 'none',
    background: '#3b82f6',
    borderRadius: 6,
    fontSize: '0.8rem',
    fontWeight: 500,
    color: 'white',
    cursor: 'pointer',
  },
  // Filters
  filterBar: {
    display: 'flex',
    gap: 12,
    marginBottom: 16,
    alignItems: 'center',
  },
  filterSelect: {
    padding: '8px 12px',
    border: '1px solid #e5e7eb',
    borderRadius: 6,
    fontSize: '0.8rem',
    color: '#374151',
    background: 'white',
    cursor: 'pointer',
  },
  filterInput: {
    padding: '8px 12px',
    border: '1px solid #e5e7eb',
    borderRadius: 6,
    fontSize: '0.8rem',
    color: '#374151',
  },
  // Charts
  chartGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: 24,
    marginBottom: 24,
  },
  chartCard: {
    background: 'white',
    border: '1px solid #e5e7eb',
    borderRadius: 12,
    padding: 20,
  },
  chartTitle: {
    margin: '0 0 16px',
    fontSize: '1rem',
    fontWeight: 600,
    color: '#111827',
  },
  // Quick actions
  quickActionsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(2, 1fr)',
    gap: 12,
  },
  quickActionCard: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    padding: 16,
    background: '#f9fafb',
    borderRadius: 8,
    cursor: 'pointer',
    border: 'none',
    width: '100%',
    textAlign: 'left',
    transition: 'background 0.2s',
  },
  quickActionIcon: {
    width: 40,
    height: 40,
    borderRadius: 10,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  // Empty state
  emptyState: {
    textAlign: 'center',
    padding: 40,
    color: '#6b7280',
  },
  // Red flags list
  redFlagItem: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: 8,
    padding: '8px 0',
    fontSize: '0.875rem',
    color: '#dc2626',
  },
  talkingPointItem: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: 8,
    padding: '8px 0',
    fontSize: '0.875rem',
    color: '#374151',
  },
  // Score indicator
  scoreCircle: {
    width: 48,
    height: 48,
    borderRadius: '50%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontWeight: 700,
    fontSize: '0.875rem',
    color: 'white',
  },
};

// ─── Keyframe injection ──────────────────────────────────────────
if (typeof document !== 'undefined') {
  const styleTag = document.getElementById('urla-ci-keyframes') || (() => {
    const tag = document.createElement('style');
    tag.id = 'urla-ci-keyframes';
    tag.textContent = `
      @keyframes urla-spin { to { transform: rotate(360deg); } }
    `;
    document.head.appendChild(tag);
    return tag;
  })();
}

// ─── Helpers ─────────────────────────────────────────────────────
const formatDuration = (seconds) => {
  if (!seconds) return '--';
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
};

const formatDate = (dateStr) => {
  if (!dateStr) return '--';
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
};

const formatDateTime = (dateStr) => {
  if (!dateStr) return '--';
  const d = new Date(dateStr);
  return d.toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  });
};

const getScoreColor = (score) => {
  if (score >= 80) return '#10b981';
  if (score >= 60) return '#f59e0b';
  return '#ef4444';
};

const getStatusStyle = (status) => {
  const key = (status || '').toLowerCase().replace(/\s+/g, '_');
  return STATUS_STYLES[key] || { bg: '#f3f4f6', color: '#6b7280', label: status || 'Unknown' };
};

// ─── Component ───────────────────────────────────────────────────
const URLACallIntelligencePage = () => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [loading, setLoading] = useState(true);
  const [sessions, setSessions] = useState([]);
  const [briefings, setBriefings] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [expandedSessionId, setExpandedSessionId] = useState(null);
  const [expandedBriefingId, setExpandedBriefingId] = useState(null);
  const [sessionDetails, setSessionDetails] = useState({});
  const [briefingDetails, setBriefingDetails] = useState({});

  // Filters
  const [statusFilter, setStatusFilter] = useState('all');
  const [dateRangeFilter, setDateRangeFilter] = useState('30');

  // ── Data Fetching ─────────────────────────────────────────
  const fetchSessions = useCallback(async () => {
    try {
      const params = {};
      if (statusFilter !== 'all') params.status = statusFilter;
      params.limit = 50;
      const data = await urlaCallIntelligenceApi.listSessions(params);
      setSessions(data.sessions || data || []);
    } catch (error) {
      console.error('Error fetching URLA sessions:', error);
      toast.error('Failed to load URLA sessions');
    }
  }, [statusFilter]);

  const fetchAnalytics = useCallback(async () => {
    try {
      const endDate = new Date().toISOString().split('T')[0];
      const startDate = new Date(Date.now() - Number(dateRangeFilter) * 86400000)
        .toISOString().split('T')[0];
      const data = await urlaCallIntelligenceApi.getAnalytics(startDate, endDate);
      setAnalytics(data);
    } catch (error) {
      console.error('Error fetching URLA analytics:', error);
      // Analytics may not be available yet — degrade gracefully
    }
  }, [dateRangeFilter]);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      await Promise.allSettled([fetchSessions(), fetchAnalytics()]);
    } finally {
      setLoading(false);
    }
  }, [fetchSessions, fetchAnalytics]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  // ── Session Detail Expansion ──────────────────────────────
  const handleExpandSession = async (session) => {
    const loanId = session.loan_id || session.id;
    if (expandedSessionId === loanId) {
      setExpandedSessionId(null);
      return;
    }
    setExpandedSessionId(loanId);

    if (!sessionDetails[loanId]) {
      try {
        const [scoreData, taskData] = await Promise.allSettled([
          urlaCallIntelligenceApi.getCallScore(loanId),
          urlaCallIntelligenceApi.getCallTasks(loanId),
        ]);

        setSessionDetails(prev => ({
          ...prev,
          [loanId]: {
            score: scoreData.status === 'fulfilled' ? scoreData.value : null,
            tasks: taskData.status === 'fulfilled' ? taskData.value : null,
          },
        }));
      } catch (error) {
        console.error('Error fetching session details:', error);
      }
    }
  };

  // ── Briefing Expansion ────────────────────────────────────
  const handleExpandBriefing = async (session) => {
    const loanId = session.loan_id || session.id;
    if (expandedBriefingId === loanId) {
      setExpandedBriefingId(null);
      return;
    }
    setExpandedBriefingId(loanId);

    if (!briefingDetails[loanId]) {
      try {
        const briefing = await urlaCallIntelligenceApi.getLOBriefing(loanId);
        setBriefingDetails(prev => ({
          ...prev,
          [loanId]: briefing,
        }));
      } catch (error) {
        console.error('Error fetching briefing:', error);
        toast.error('Failed to load briefing details');
      }
    }
  };

  // ── View Briefing HTML ────────────────────────────────────
  const handleViewBriefingHtml = async (loanId) => {
    try {
      const html = await urlaCallIntelligenceApi.getLOBriefingHtml(loanId);
      const htmlContent = typeof html === 'string' ? html : html.html || html.content || '';
      const win = window.open('', '_blank');
      if (win) {
        win.document.write(htmlContent);
        win.document.close();
      }
    } catch (error) {
      toast.error('Failed to load briefing HTML');
    }
  };

  // ── Push Tasks to CRM ─────────────────────────────────────
  const handlePushTasks = async (loanId) => {
    try {
      const result = await urlaCallIntelligenceApi.pushTasksToCrm(loanId);
      toast.success(`Pushed ${result.tasks_created || 0} tasks to CRM`);
    } catch (error) {
      toast.error('Failed to push tasks to CRM');
    }
  };

  // ── Analyze a Call ────────────────────────────────────────
  const handleAnalyzeCall = async (loanId) => {
    try {
      await urlaCallIntelligenceApi.analyzeCall(loanId);
      toast.success('Call analysis started');
      fetchSessions();
    } catch (error) {
      toast.error('Failed to start call analysis');
    }
  };

  // ── Computed Values ───────────────────────────────────────
  const completedSessions = sessions.filter(s =>
    (s.status || '').toLowerCase() === 'completed'
  );
  const totalSessions = sessions.length;
  const completionRate = totalSessions > 0
    ? Math.round((completedSessions.length / totalSessions) * 100)
    : 0;
  const avgDuration = sessions.length > 0
    ? Math.round(sessions.reduce((sum, s) => sum + (s.duration || 0), 0) / sessions.length)
    : 0;
  const avgComplianceScore = sessions.length > 0
    ? Math.round(
        sessions.reduce((sum, s) => sum + (s.compliance_score || s.score || 0), 0) / sessions.length
      )
    : 0;

  // Derive briefings from sessions that have briefing data
  const briefingSessions = sessions.filter(s =>
    s.has_briefing || (s.status || '').toLowerCase() === 'completed'
  );

  // ── Tab Config ────────────────────────────────────────────
  const tabs = [
    { id: 'dashboard', label: 'Dashboard', icon: 'grid' },
    { id: 'sessions', label: 'Sessions', badge: totalSessions },
    { id: 'briefings', label: 'Briefings', badge: briefingSessions.length },
    { id: 'analytics', label: 'Analytics' },
  ];

  // ═══════════════════════════════════════════════════════════
  //  RENDER: Dashboard Tab
  // ═══════════════════════════════════════════════════════════
  const renderDashboard = () => (
    <div>
      {/* Metric Cards */}
      <div style={styles.metricsGrid}>
        <div style={styles.metricCard}>
          <div style={{ ...styles.metricIcon, background: '#dbeafe', color: '#3b82f6' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z" />
            </svg>
          </div>
          <div>
            <div style={styles.metricValue}>{totalSessions}</div>
            <div style={styles.metricLabel}>Total Sessions</div>
          </div>
        </div>

        <div style={styles.metricCard}>
          <div style={{ ...styles.metricIcon, background: '#dcfce7', color: '#10b981' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 11.08V12a10 10 0 11-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
          </div>
          <div>
            <div style={styles.metricValue}>{completedSessions.length}</div>
            <div style={styles.metricLabel}>Completed Applications</div>
          </div>
        </div>

        <div style={styles.metricCard}>
          <div style={{ ...styles.metricIcon, background: '#f3e8ff', color: '#8b5cf6' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="12" y1="20" x2="12" y2="10" />
              <line x1="18" y1="20" x2="18" y2="4" />
              <line x1="6" y1="20" x2="6" y2="16" />
            </svg>
          </div>
          <div>
            <div style={styles.metricValue}>{completionRate}%</div>
            <div style={styles.metricLabel}>Completion Rate</div>
          </div>
        </div>

        <div style={styles.metricCard}>
          <div style={{ ...styles.metricIcon, background: '#fef3c7', color: '#f59e0b' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
          </div>
          <div>
            <div style={styles.metricValue}>{formatDuration(avgDuration)}</div>
            <div style={styles.metricLabel}>Avg Duration</div>
          </div>
        </div>

        <div style={styles.metricCard}>
          <div style={{
            ...styles.metricIcon,
            background: avgComplianceScore >= 80 ? '#dcfce7' : avgComplianceScore >= 60 ? '#fef3c7' : '#fee2e2',
            color: getScoreColor(avgComplianceScore),
          }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
          </div>
          <div>
            <div style={{ ...styles.metricValue, color: getScoreColor(avgComplianceScore) }}>
              {avgComplianceScore || '--'}
            </div>
            <div style={styles.metricLabel}>Avg Compliance Score</div>
          </div>
        </div>
      </div>

      {/* Recent Sessions + Quick Actions row */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 24 }}>
        {/* Recent Sessions */}
        <div style={styles.section}>
          <div style={styles.sectionHeader}>
            <h3 style={styles.sectionTitle}>Recent Sessions</h3>
            <button
              style={styles.actionBtn}
              onClick={() => setActiveTab('sessions')}
            >
              View All
            </button>
          </div>
          {sessions.length === 0 ? (
            <div style={styles.emptyState}>
              <p>No URLA voice sessions yet</p>
            </div>
          ) : (
            <div>
              {sessions.slice(0, 10).map((session) => {
                const st = getStatusStyle(session.status);
                return (
                  <div
                    key={session.id || session.loan_id}
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      padding: '12px 0',
                      borderBottom: '1px solid #f3f4f6',
                      cursor: 'pointer',
                    }}
                    onClick={() => {
                      handleExpandSession(session);
                      setActiveTab('sessions');
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 500, color: '#111827', fontSize: '0.9rem' }}>
                        {session.borrower_name || session.borrower || 'Unknown Borrower'}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: '#6b7280', marginTop: 2 }}>
                        Loan {session.loan_id || '--'}
                        <span style={{ margin: '0 6px', opacity: 0.5 }}>|</span>
                        {formatDuration(session.duration)}
                        <span style={{ margin: '0 6px', opacity: 0.5 }}>|</span>
                        {session.sections_completed || 0} sections
                      </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <span style={{
                        ...styles.statusBadge,
                        background: st.bg,
                        color: st.color,
                      }}>
                        {st.label}
                      </span>
                      <span style={{ fontSize: '0.75rem', color: '#9ca3af' }}>
                        {formatDateTime(session.created_at || session.date)}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Quick Actions */}
        <div style={styles.section}>
          <h3 style={{ ...styles.sectionTitle, marginBottom: 16 }}>Quick Actions</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <button
              style={styles.quickActionCard}
              onClick={() => setActiveTab('analytics')}
              onMouseEnter={(e) => { e.currentTarget.style.background = '#f3f4f6'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = '#f9fafb'; }}
            >
              <div style={{ ...styles.quickActionIcon, background: '#dbeafe', color: '#3b82f6' }}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="18" y1="20" x2="18" y2="10" />
                  <line x1="12" y1="20" x2="12" y2="4" />
                  <line x1="6" y1="20" x2="6" y2="14" />
                </svg>
              </div>
              <div>
                <div style={{ fontWeight: 500, color: '#111827' }}>View Analytics</div>
                <div style={{ fontSize: '0.8rem', color: '#6b7280' }}>Trends, drop-off, quality scores</div>
              </div>
            </button>
            <button
              style={styles.quickActionCard}
              onClick={() => setActiveTab('briefings')}
              onMouseEnter={(e) => { e.currentTarget.style.background = '#f3f4f6'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = '#f9fafb'; }}
            >
              <div style={{ ...styles.quickActionIcon, background: '#dcfce7', color: '#10b981' }}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                </svg>
              </div>
              <div>
                <div style={{ fontWeight: 500, color: '#111827' }}>LO Briefings</div>
                <div style={{ fontSize: '0.8rem', color: '#6b7280' }}>Review generated briefings</div>
              </div>
            </button>
            <button
              style={styles.quickActionCard}
              onClick={() => setActiveTab('sessions')}
              onMouseEnter={(e) => { e.currentTarget.style.background = '#f3f4f6'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = '#f9fafb'; }}
            >
              <div style={{ ...styles.quickActionIcon, background: '#f3e8ff', color: '#8b5cf6' }}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                  <line x1="16" y1="2" x2="16" y2="6" />
                  <line x1="8" y1="2" x2="8" y2="6" />
                  <line x1="3" y1="10" x2="21" y2="10" />
                </svg>
              </div>
              <div>
                <div style={{ fontWeight: 500, color: '#111827' }}>All Sessions</div>
                <div style={{ fontSize: '0.8rem', color: '#6b7280' }}>Browse call history</div>
              </div>
            </button>
          </div>
        </div>
      </div>
    </div>
  );

  // ═══════════════════════════════════════════════════════════
  //  RENDER: Sessions Tab
  // ═══════════════════════════════════════════════════════════
  const renderSessions = () => {
    const filteredSessions = statusFilter === 'all'
      ? sessions
      : sessions.filter(s => (s.status || '').toLowerCase().replace(/\s+/g, '_') === statusFilter);

    return (
      <div style={styles.section}>
        {/* Filters */}
        <div style={styles.filterBar}>
          <label style={{ fontSize: '0.8rem', color: '#6b7280', fontWeight: 500 }}>Status:</label>
          <select
            style={styles.filterSelect}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="all">All Statuses</option>
            <option value="in_progress">In Progress</option>
            <option value="completed">Completed</option>
            <option value="abandoned">Abandoned</option>
          </select>
          <label style={{ fontSize: '0.8rem', color: '#6b7280', fontWeight: 500, marginLeft: 12 }}>
            Period:
          </label>
          <select
            style={styles.filterSelect}
            value={dateRangeFilter}
            onChange={(e) => setDateRangeFilter(e.target.value)}
          >
            <option value="7">Last 7 days</option>
            <option value="30">Last 30 days</option>
            <option value="90">Last 90 days</option>
          </select>
        </div>

        {/* Table */}
        {filteredSessions.length === 0 ? (
          <div style={styles.emptyState}>
            <p>No sessions match the current filters</p>
          </div>
        ) : (
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Loan ID</th>
                <th style={styles.th}>Borrower Name</th>
                <th style={styles.th}>Status</th>
                <th style={styles.th}>Duration</th>
                <th style={styles.th}>Sections</th>
                <th style={styles.th}>Compliance</th>
                <th style={styles.th}>Date</th>
              </tr>
            </thead>
            <tbody>
              {filteredSessions.map((session) => {
                const loanId = session.loan_id || session.id;
                const st = getStatusStyle(session.status);
                const isExpanded = expandedSessionId === loanId;
                const details = sessionDetails[loanId];

                return (
                  <React.Fragment key={loanId}>
                    <tr
                      style={{
                        ...styles.tr,
                        background: isExpanded ? '#f9fafb' : 'transparent',
                      }}
                      onClick={() => handleExpandSession(session)}
                      onMouseEnter={(e) => {
                        if (!isExpanded) e.currentTarget.style.background = '#f9fafb';
                      }}
                      onMouseLeave={(e) => {
                        if (!isExpanded) e.currentTarget.style.background = 'transparent';
                      }}
                    >
                      <td style={styles.td}>
                        <span style={{ fontWeight: 500, color: '#3b82f6' }}>{loanId || '--'}</span>
                      </td>
                      <td style={styles.td}>
                        {session.borrower_name || session.borrower || 'Unknown'}
                      </td>
                      <td style={styles.td}>
                        <span style={{
                          ...styles.statusBadge,
                          background: st.bg,
                          color: st.color,
                        }}>
                          {st.label}
                        </span>
                      </td>
                      <td style={styles.td}>{formatDuration(session.duration)}</td>
                      <td style={styles.td}>
                        {session.sections_completed || 0}/{session.total_sections || 10}
                      </td>
                      <td style={styles.td}>
                        <span style={{ color: getScoreColor(session.compliance_score || session.score || 0) }}>
                          {session.compliance_score || session.score || '--'}
                        </span>
                      </td>
                      <td style={{ ...styles.td, color: '#9ca3af', fontSize: '0.8rem' }}>
                        {formatDate(session.created_at || session.date)}
                      </td>
                    </tr>

                    {/* Expanded Detail Row */}
                    {isExpanded && (
                      <tr>
                        <td colSpan={7} style={{ padding: 0 }}>
                          <div style={styles.expandedRow}>
                            <div style={styles.expandedGrid}>
                              {/* Score Breakdown */}
                              <div style={styles.expandedCard}>
                                <h4 style={{ margin: '0 0 12px', fontSize: '0.875rem', fontWeight: 600, color: '#374151' }}>
                                  Score Breakdown
                                </h4>
                                {details?.score ? (
                                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                    {renderScoreBar('Compliance', details.score.compliance_score || details.score.compliance || 0)}
                                    {renderScoreBar('Data Quality', details.score.data_quality_score || details.score.data_quality || 0)}
                                    {renderScoreBar('Conversation', details.score.conversation_score || details.score.conversation || 0)}
                                    <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid #e5e7eb' }}>
                                      <strong style={{ fontSize: '0.875rem' }}>
                                        Overall: {details.score.overall_score || details.score.overall || '--'}
                                      </strong>
                                    </div>
                                  </div>
                                ) : (
                                  <div style={{ color: '#9ca3af', fontSize: '0.8rem' }}>Loading...</div>
                                )}
                              </div>

                              {/* Briefing Summary */}
                              <div style={styles.expandedCard}>
                                <h4 style={{ margin: '0 0 12px', fontSize: '0.875rem', fontWeight: 600, color: '#374151' }}>
                                  Briefing Summary
                                </h4>
                                {briefingDetails[loanId] ? (
                                  <p style={{ fontSize: '0.8rem', color: '#374151', margin: 0, lineHeight: 1.5 }}>
                                    {briefingDetails[loanId].executive_summary ||
                                     briefingDetails[loanId].summary ||
                                     'No summary available'}
                                  </p>
                                ) : (
                                  <button
                                    style={{ ...styles.actionBtn, fontSize: '0.75rem' }}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleExpandBriefing(session);
                                    }}
                                  >
                                    Load Briefing
                                  </button>
                                )}
                              </div>

                              {/* Tasks */}
                              <div style={styles.expandedCard}>
                                <h4 style={{ margin: '0 0 12px', fontSize: '0.875rem', fontWeight: 600, color: '#374151' }}>
                                  Tasks ({details?.tasks?.tasks?.length || details?.tasks?.length || 0})
                                </h4>
                                {details?.tasks ? (
                                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                    {(details.tasks.tasks || details.tasks || []).slice(0, 5).map((task, i) => (
                                      <div key={i} style={{ fontSize: '0.8rem', color: '#374151', display: 'flex', alignItems: 'flex-start', gap: 6 }}>
                                        <span style={{ color: '#9ca3af', flexShrink: 0 }}>-</span>
                                        <span>{task.title || task.description || task}</span>
                                      </div>
                                    ))}
                                    <button
                                      style={{ ...styles.primaryBtn, marginTop: 8, fontSize: '0.75rem', padding: '6px 12px' }}
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        handlePushTasks(loanId);
                                      }}
                                    >
                                      Push Tasks to CRM
                                    </button>
                                  </div>
                                ) : (
                                  <div style={{ color: '#9ca3af', fontSize: '0.8rem' }}>Loading...</div>
                                )}
                              </div>
                            </div>

                            {/* Expanded Actions */}
                            <div style={{ display: 'flex', gap: 8 }}>
                              <button
                                style={styles.actionBtn}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleViewBriefingHtml(loanId);
                                }}
                              >
                                View Full Report
                              </button>
                              <button
                                style={styles.actionBtn}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleAnalyzeCall(loanId);
                                }}
                              >
                                Re-Analyze
                              </button>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    );
  };

  // ═══════════════════════════════════════════════════════════
  //  RENDER: Briefings Tab
  // ═══════════════════════════════════════════════════════════
  const renderBriefings = () => (
    <div>
      {briefingSessions.length === 0 ? (
        <div style={{ ...styles.section, ...styles.emptyState }}>
          <p>No briefings available yet. Complete a URLA voice session to generate a briefing.</p>
        </div>
      ) : (
        briefingSessions.map((session) => {
          const loanId = session.loan_id || session.id;
          const isExpanded = expandedBriefingId === loanId;
          const detail = briefingDetails[loanId];
          const score = session.compliance_score || session.score || 0;

          return (
            <div
              key={loanId}
              style={{
                ...styles.briefingCard,
                borderColor: isExpanded ? '#3b82f6' : '#e5e7eb',
                background: isExpanded ? '#fafbff' : 'white',
              }}
              onClick={() => handleExpandBriefing(session)}
              onMouseEnter={(e) => { e.currentTarget.style.borderColor = '#3b82f6'; }}
              onMouseLeave={(e) => {
                if (!isExpanded) e.currentTarget.style.borderColor = '#e5e7eb';
              }}
            >
              <div style={styles.briefingHeader}>
                <div>
                  <div style={{ fontWeight: 600, color: '#111827', fontSize: '1rem', marginBottom: 4 }}>
                    {session.borrower_name || session.borrower || 'Unknown Borrower'}
                  </div>
                  <div style={{ fontSize: '0.8rem', color: '#6b7280', display: 'flex', gap: 16 }}>
                    <span>Loan: {loanId}</span>
                    {session.loan_amount && <span>${Number(session.loan_amount).toLocaleString()}</span>}
                    {session.loan_purpose && <span>{session.loan_purpose}</span>}
                    <span>{formatDate(session.created_at || session.date)}</span>
                  </div>
                </div>
                <div style={{
                  ...styles.scoreCircle,
                  background: getScoreColor(score),
                  width: 44,
                  height: 44,
                }}>
                  {score || '--'}
                </div>
              </div>

              {/* Expanded Briefing Detail */}
              {isExpanded && detail && (
                <div style={{ borderTop: '1px solid #e5e7eb', paddingTop: 16, marginTop: 4 }}>
                  {/* Executive Summary */}
                  {(detail.executive_summary || detail.summary) && (
                    <div style={{ marginBottom: 16 }}>
                      <h4 style={{ margin: '0 0 8px', fontSize: '0.875rem', fontWeight: 600, color: '#374151' }}>
                        Executive Summary
                      </h4>
                      <p style={{ margin: 0, fontSize: '0.875rem', color: '#374151', lineHeight: 1.6 }}>
                        {detail.executive_summary || detail.summary}
                      </p>
                    </div>
                  )}

                  {/* Red Flags */}
                  {(detail.red_flags || []).length > 0 && (
                    <div style={{ marginBottom: 16 }}>
                      <h4 style={{ margin: '0 0 8px', fontSize: '0.875rem', fontWeight: 600, color: '#dc2626' }}>
                        Red Flags
                      </h4>
                      {detail.red_flags.map((flag, i) => (
                        <div key={i} style={styles.redFlagItem}>
                          <span>!</span>
                          <span>{typeof flag === 'string' ? flag : flag.description || flag.text}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Missing Items */}
                  {(detail.missing_items || detail.missing_fields || []).length > 0 && (
                    <div style={{ marginBottom: 16 }}>
                      <h4 style={{ margin: '0 0 8px', fontSize: '0.875rem', fontWeight: 600, color: '#f59e0b' }}>
                        Missing Items
                      </h4>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                        {(detail.missing_items || detail.missing_fields).map((item, i) => (
                          <span key={i} style={{
                            padding: '4px 10px',
                            background: '#fef3c7',
                            color: '#92400e',
                            borderRadius: 4,
                            fontSize: '0.75rem',
                            fontWeight: 500,
                          }}>
                            {typeof item === 'string' ? item : item.field || item.name}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Talking Points */}
                  {(detail.talking_points || []).length > 0 && (
                    <div style={{ marginBottom: 16 }}>
                      <h4 style={{ margin: '0 0 8px', fontSize: '0.875rem', fontWeight: 600, color: '#374151' }}>
                        Talking Points
                      </h4>
                      {detail.talking_points.map((point, i) => (
                        <div key={i} style={styles.talkingPointItem}>
                          <span style={{ color: '#3b82f6' }}>-</span>
                          <span>{typeof point === 'string' ? point : point.text || point.description}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Actions */}
                  <div style={styles.briefingActions}>
                    <button
                      style={styles.actionBtn}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleViewBriefingHtml(loanId);
                      }}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6" />
                        <polyline points="15 3 21 3 21 9" />
                        <line x1="10" y1="14" x2="21" y2="3" />
                      </svg>
                      View HTML
                    </button>
                    <button
                      style={styles.primaryBtn}
                      onClick={(e) => {
                        e.stopPropagation();
                        handlePushTasks(loanId);
                      }}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M4 12v8a2 2 0 002 2h12a2 2 0 002-2v-8" />
                        <polyline points="16 6 12 2 8 6" />
                        <line x1="12" y1="2" x2="12" y2="15" />
                      </svg>
                      Push Tasks to CRM
                    </button>
                  </div>
                </div>
              )}

              {isExpanded && !detail && (
                <div style={{ textAlign: 'center', padding: 20, color: '#9ca3af', fontSize: '0.8rem' }}>
                  Loading briefing details...
                </div>
              )}
            </div>
          );
        })
      )}
    </div>
  );

  // ═══════════════════════════════════════════════════════════
  //  RENDER: Analytics Tab
  // ═══════════════════════════════════════════════════════════
  const renderAnalytics = () => {
    // Derive chart data from analytics response or sessions fallback
    const sectionDropOff = analytics?.section_drop_off || analytics?.drop_off || buildSectionDropOff(sessions);
    const completionTrend = analytics?.completion_trend || analytics?.trend || buildCompletionTrend(sessions);
    const scoreDistribution = analytics?.score_distribution || buildScoreDistribution(sessions);
    const peakHours = analytics?.peak_hours || analytics?.hourly || buildPeakHours(sessions);
    const purposeSplit = analytics?.purpose_split || analytics?.loan_purpose || buildPurposeSplit(sessions);

    return (
      <div>
        {/* Period selector */}
        <div style={{ marginBottom: 24, display: 'flex', alignItems: 'center', gap: 12 }}>
          <label style={{ fontSize: '0.875rem', color: '#6b7280', fontWeight: 500 }}>Date Range:</label>
          <select
            style={styles.filterSelect}
            value={dateRangeFilter}
            onChange={(e) => setDateRangeFilter(e.target.value)}
          >
            <option value="7">Last 7 days</option>
            <option value="30">Last 30 days</option>
            <option value="90">Last 90 days</option>
          </select>
        </div>

        {/* Row 1: Drop-off + Completion Trend */}
        <div style={styles.chartGrid}>
          <div style={styles.chartCard}>
            <h3 style={styles.chartTitle}>Section Drop-off Analysis</h3>
            {sectionDropOff.length > 0 ? (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={sectionDropOff}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
                  <XAxis
                    dataKey="name"
                    tick={{ fontSize: 11, fill: '#6b7280' }}
                    angle={-30}
                    textAnchor="end"
                    height={60}
                  />
                  <YAxis tick={{ fontSize: 11, fill: '#6b7280' }} />
                  <Tooltip
                    contentStyle={{
                      background: 'white',
                      border: '1px solid #e5e7eb',
                      borderRadius: 8,
                      fontSize: '0.8rem',
                    }}
                  />
                  <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div style={styles.emptyState}>No drop-off data available</div>
            )}
          </div>

          <div style={styles.chartCard}>
            <h3 style={styles.chartTitle}>Completion Trend</h3>
            {completionTrend.length > 0 ? (
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={completionTrend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
                  <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#6b7280' }} />
                  <YAxis tick={{ fontSize: 11, fill: '#6b7280' }} />
                  <Tooltip
                    contentStyle={{
                      background: 'white',
                      border: '1px solid #e5e7eb',
                      borderRadius: 8,
                      fontSize: '0.8rem',
                    }}
                  />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="completed"
                    stroke="#10b981"
                    strokeWidth={2}
                    dot={{ r: 3, fill: '#10b981' }}
                    name="Completed"
                  />
                  <Line
                    type="monotone"
                    dataKey="total"
                    stroke="#3b82f6"
                    strokeWidth={2}
                    dot={{ r: 3, fill: '#3b82f6' }}
                    name="Total"
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div style={styles.emptyState}>No trend data available</div>
            )}
          </div>
        </div>

        {/* Row 2: Score Distribution + Peak Hours */}
        <div style={styles.chartGrid}>
          <div style={styles.chartCard}>
            <h3 style={styles.chartTitle}>Score Distribution</h3>
            {scoreDistribution.length > 0 ? (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={scoreDistribution}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
                  <XAxis dataKey="category" tick={{ fontSize: 11, fill: '#6b7280' }} />
                  <YAxis tick={{ fontSize: 11, fill: '#6b7280' }} domain={[0, 100]} />
                  <Tooltip
                    contentStyle={{
                      background: 'white',
                      border: '1px solid #e5e7eb',
                      borderRadius: 8,
                      fontSize: '0.8rem',
                    }}
                  />
                  <Legend />
                  <Bar dataKey="avg" fill="#8b5cf6" radius={[4, 4, 0, 0]} name="Avg Score" />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div style={styles.emptyState}>No score data available</div>
            )}
          </div>

          <div style={styles.chartCard}>
            <h3 style={styles.chartTitle}>Peak Calling Hours</h3>
            {peakHours.length > 0 ? (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={peakHours}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
                  <XAxis dataKey="hour" tick={{ fontSize: 11, fill: '#6b7280' }} />
                  <YAxis tick={{ fontSize: 11, fill: '#6b7280' }} />
                  <Tooltip
                    contentStyle={{
                      background: 'white',
                      border: '1px solid #e5e7eb',
                      borderRadius: 8,
                      fontSize: '0.8rem',
                    }}
                  />
                  <Bar dataKey="count" fill="#06b6d4" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div style={styles.emptyState}>No hourly data available</div>
            )}
          </div>
        </div>

        {/* Row 3: Purchase vs Refi (centered, smaller) */}
        <div style={{ display: 'flex', justifyContent: 'center' }}>
          <div style={{ ...styles.chartCard, width: '50%', minWidth: 400 }}>
            <h3 style={styles.chartTitle}>Purchase vs Refinance</h3>
            {purposeSplit.length > 0 ? (
              <ResponsiveContainer width="100%" height={280}>
                <PieChart>
                  <Pie
                    data={purposeSplit}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={100}
                    paddingAngle={4}
                    dataKey="value"
                    nameKey="name"
                    label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  >
                    {purposeSplit.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      background: 'white',
                      border: '1px solid #e5e7eb',
                      borderRadius: 8,
                      fontSize: '0.8rem',
                    }}
                  />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div style={styles.emptyState}>No loan purpose data available</div>
            )}
          </div>
        </div>
      </div>
    );
  };

  // ─── Score Bar Helper ─────────────────────────────────────
  const renderScoreBar = (label, value) => (
    <div style={{ marginBottom: 4 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', marginBottom: 4 }}>
        <span style={{ color: '#6b7280' }}>{label}</span>
        <span style={{ fontWeight: 600, color: getScoreColor(value) }}>{value}</span>
      </div>
      <div style={{ height: 6, background: '#e5e7eb', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{
          height: '100%',
          width: `${Math.min(value, 100)}%`,
          background: getScoreColor(value),
          borderRadius: 3,
          transition: 'width 0.3s',
        }} />
      </div>
    </div>
  );

  // ═══════════════════════════════════════════════════════════
  //  MAIN RENDER
  // ═══════════════════════════════════════════════════════════
  return (
    <div style={styles.page}>
      {/* Page Header */}
      <div style={styles.header}>
        <div>
          <h1 style={styles.headerTitle}>URLA Call Intelligence</h1>
          <p style={styles.headerSub}>
            AI-powered URLA voice agent analysis, briefings, and compliance scoring
          </p>
        </div>
        <div style={styles.headerActions}>
          <button
            style={styles.refreshBtn}
            onClick={fetchAll}
            disabled={loading}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = '#3b82f6';
              e.currentTarget.style.color = '#3b82f6';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = '#e5e7eb';
              e.currentTarget.style.color = '#374151';
            }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="23 4 23 10 17 10" />
              <polyline points="1 20 1 14 7 14" />
              <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
            </svg>
            Refresh
          </button>
        </div>
      </div>

      {/* Tab Navigation */}
      <div style={styles.tabs}>
        {tabs.map(tab => (
          <button
            key={tab.id}
            style={{
              ...styles.tab,
              ...(activeTab === tab.id ? styles.tabActive : {}),
            }}
            onClick={() => {
              setActiveTab(tab.id);
              setExpandedSessionId(null);
              setExpandedBriefingId(null);
            }}
          >
            <span>{tab.label}</span>
            {tab.badge > 0 && (
              <span style={{
                ...styles.tabBadge,
                ...(activeTab === tab.id ? { background: '#2563eb' } : {}),
              }}>
                {tab.badge}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div style={styles.content}>
        {loading && sessions.length === 0 ? (
          <div style={styles.loading}>
            <div style={styles.spinner} />
            <p>Loading URLA call data...</p>
          </div>
        ) : (
          <>
            {activeTab === 'dashboard' && renderDashboard()}
            {activeTab === 'sessions' && renderSessions()}
            {activeTab === 'briefings' && renderBriefings()}
            {activeTab === 'analytics' && renderAnalytics()}
          </>
        )}
      </div>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════════
//  Fallback Chart Data Builders (from session data when API
//  analytics endpoint returns no structured chart data)
// ═══════════════════════════════════════════════════════════════

const URLA_SECTIONS = [
  'Personal Info', 'Employment', 'Income', 'Assets',
  'Liabilities', 'Real Estate', 'Declarations',
  'Demographics', 'Loan Info', 'Property',
];

function buildSectionDropOff(sessions) {
  if (!sessions.length) return [];
  const counts = URLA_SECTIONS.map(() => 0);
  sessions.forEach(s => {
    const completed = s.sections_completed || 0;
    if (completed < URLA_SECTIONS.length) {
      counts[completed] = (counts[completed] || 0) + 1;
    }
  });
  return URLA_SECTIONS.map((name, i) => ({ name, count: counts[i] }));
}

function buildCompletionTrend(sessions) {
  if (!sessions.length) return [];
  const byDate = {};
  sessions.forEach(s => {
    const d = (s.created_at || s.date || '').split('T')[0];
    if (!d) return;
    if (!byDate[d]) byDate[d] = { total: 0, completed: 0 };
    byDate[d].total++;
    if ((s.status || '').toLowerCase() === 'completed') byDate[d].completed++;
  });
  return Object.entries(byDate)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, vals]) => ({ date, ...vals }));
}

function buildScoreDistribution(sessions) {
  const scored = sessions.filter(s => s.compliance_score || s.score);
  if (!scored.length) return [];
  const categories = [
    { category: 'Compliance', key: 'compliance_score' },
    { category: 'Data Quality', key: 'data_quality_score' },
    { category: 'Conversation', key: 'conversation_score' },
  ];
  return categories.map(({ category, key }) => {
    const vals = scored.map(s => s[key] || s.score || 0).filter(v => v > 0);
    const avg = vals.length ? Math.round(vals.reduce((a, b) => a + b, 0) / vals.length) : 0;
    return { category, avg };
  });
}

function buildPeakHours(sessions) {
  if (!sessions.length) return [];
  const hours = Array(24).fill(0);
  sessions.forEach(s => {
    const d = s.created_at || s.date;
    if (!d) return;
    const h = new Date(d).getHours();
    hours[h]++;
  });
  return hours.map((count, i) => ({
    hour: `${i === 0 ? 12 : i > 12 ? i - 12 : i}${i < 12 ? 'am' : 'pm'}`,
    count,
  }));
}

function buildPurposeSplit(sessions) {
  const purposeMap = {};
  sessions.forEach(s => {
    const p = (s.loan_purpose || 'Unknown').replace(/_/g, ' ');
    const label = p.charAt(0).toUpperCase() + p.slice(1).toLowerCase();
    purposeMap[label] = (purposeMap[label] || 0) + 1;
  });
  const entries = Object.entries(purposeMap);
  if (!entries.length) return [];
  return entries.map(([name, value]) => ({ name, value }));
}

export default URLACallIntelligencePage;
