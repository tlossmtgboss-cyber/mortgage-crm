/**
 * URLA Session Detail Component
 *
 * Full detail view of a URLA voice agent session including:
 * - Overview with scores, progress, compliance flags
 * - Chat-style transcript with search
 * - Auto-generated tasks with CRM push
 * - LO Briefing embed
 * - Raw application data with collapsible URLA sections
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { urlaCallIntelligenceApi } from '../../services/urlaCallIntelligenceApi';
import { toast } from '../../utils/toast';
import { sanitizeHTML } from '../../utils/sanitize';

// ── Score color helper ──────────────────────────────────────
const getScoreColor = (score) => {
  if (score >= 80) return '#2D7A52';
  if (score >= 60) return '#f59e0b';
  return '#ef4444';
};

const getScoreLabel = (score) => {
  if (score >= 80) return 'Good';
  if (score >= 60) return 'Fair';
  return 'Needs Attention';
};

// ── Status badge color ──────────────────────────────────────
const getStatusStyle = (status) => {
  switch (status?.toLowerCase()) {
    case 'finalized':
    case 'completed':
      return { background: '#dcfce7', color: '#166534' };
    case 'in_progress':
    case 'in progress':
      return { background: '#dbeafe', color: '#1e40af' };
    case 'abandoned':
    case 'expired':
      return { background: '#fee2e2', color: '#991b1b' };
    default:
      return { background: '#f3f4f6', color: '#374151' };
  }
};

// ── Severity badge color ────────────────────────────────────
const getSeverityStyle = (severity) => {
  switch (severity?.toLowerCase()) {
    case 'critical':
    case 'high':
      return { background: '#fee2e2', color: '#991b1b', border: '1px solid #fecaca' };
    case 'medium':
    case 'warning':
      return { background: '#fef3c7', color: '#92400e', border: '1px solid #fde68a' };
    case 'low':
    case 'info':
      return { background: '#dbeafe', color: '#1e40af', border: '1px solid #bfdbfe' };
    default:
      return { background: '#f3f4f6', color: '#374151', border: '1px solid #e5e7eb' };
  }
};

// ── Priority badge style ────────────────────────────────────
const getPriorityStyle = (priority) => {
  switch (priority?.toLowerCase()) {
    case 'urgent':
    case 'critical':
      return { background: '#fee2e2', color: '#991b1b' };
    case 'high':
      return { background: '#ffedd5', color: '#9a3412' };
    case 'medium':
      return { background: '#fef3c7', color: '#92400e' };
    case 'low':
      return { background: '#dbeafe', color: '#1e40af' };
    default:
      return { background: '#f3f4f6', color: '#374151' };
  }
};

// ── Format date ─────────────────────────────────────────────
const formatDate = (dateStr) => {
  if (!dateStr) return '--';
  const date = new Date(dateStr);
  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const formatShortDate = (dateStr) => {
  if (!dateStr) return '--';
  const date = new Date(dateStr);
  return date.toLocaleDateString([], {
    month: 'short',
    day: 'numeric',
  });
};

// ── Mask SSN ────────────────────────────────────────────────
const maskSSN = (ssn) => {
  if (!ssn) return '--';
  const cleaned = ssn.replace(/[^0-9]/g, '');
  if (cleaned.length >= 4) {
    return `***-**-${cleaned.slice(-4)}`;
  }
  return '***-**-****';
};

// ── Format currency ─────────────────────────────────────────
const formatCurrency = (value) => {
  if (value === null || value === undefined || value === '') return '--';
  const num = parseFloat(String(value).replace(/[,$]/g, ''));
  if (isNaN(num)) return value;
  return `$${num.toLocaleString()}`;
};

// ═══════════════════════════════════════════════════════════
// SCORE GAUGE
// ═══════════════════════════════════════════════════════════
const ScoreGauge = ({ label, score, size = 80 }) => {
  const color = getScoreColor(score ?? 0);
  const radius = (size - 8) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = ((score ?? 0) / 100) * circumference;

  return (
    <div style={{ textAlign: 'center', flex: '1 1 0' }}>
      <svg width={size} height={size} style={{ display: 'block', margin: '0 auto' }}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#e5e7eb"
          strokeWidth="6"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="6"
          strokeDasharray={circumference}
          strokeDashoffset={circumference - progress}
          strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{ transition: 'stroke-dashoffset 0.6s ease' }}
        />
        <text
          x={size / 2}
          y={size / 2}
          textAnchor="middle"
          dominantBaseline="central"
          style={{ fontSize: '1.1rem', fontWeight: '700', fill: color }}
        >
          {score ?? '--'}
        </text>
      </svg>
      <div style={{ fontSize: '0.75rem', color: '#6b7280', marginTop: '6px', fontWeight: '500' }}>
        {label}
      </div>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// PROGRESS BAR
// ═══════════════════════════════════════════════════════════
const ProgressBar = ({ completed, total, label }) => {
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
  const color = pct >= 80 ? '#2D7A52' : pct >= 50 ? '#f59e0b' : '#ef4444';

  return (
    <div style={{ marginBottom: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
        <span style={{ fontSize: '0.8rem', color: '#374151', fontWeight: '500' }}>{label}</span>
        <span style={{ fontSize: '0.8rem', color: '#6b7280' }}>
          {completed}/{total} ({pct}%)
        </span>
      </div>
      <div style={{
        height: '8px',
        background: '#e5e7eb',
        borderRadius: '4px',
        overflow: 'hidden',
      }}>
        <div style={{
          height: '100%',
          width: `${pct}%`,
          background: color,
          borderRadius: '4px',
          transition: 'width 0.5s ease',
        }} />
      </div>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// COLLAPSIBLE SECTION
// ═══════════════════════════════════════════════════════════
const CollapsibleSection = ({ title, children, defaultOpen = false }) => {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div style={{
      border: '1px solid #e5e7eb',
      borderRadius: '8px',
      marginBottom: '8px',
      overflow: 'hidden',
    }}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 16px',
          background: isOpen ? '#f9fafb' : '#fff',
          border: 'none',
          cursor: 'pointer',
          fontSize: '0.875rem',
          fontWeight: '600',
          color: '#374151',
          textAlign: 'left',
        }}
      >
        <span>{title}</span>
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          style={{
            transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)',
            transition: 'transform 0.2s',
          }}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
      {isOpen && (
        <div style={{ padding: '12px 16px', borderTop: '1px solid #e5e7eb' }}>
          {children}
        </div>
      )}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// DATA ROW (for Application Data tab)
// ═══════════════════════════════════════════════════════════
const DataRow = ({ label, value, highlight = false }) => (
  <div style={{
    display: 'flex',
    padding: '6px 0',
    borderBottom: '1px solid #f3f4f6',
  }}>
    <span style={{
      width: '180px',
      flexShrink: 0,
      fontSize: '0.8rem',
      color: '#6b7280',
    }}>
      {label}
    </span>
    <span style={{
      flex: 1,
      fontSize: '0.8rem',
      color: highlight ? '#dc2626' : '#111827',
      fontWeight: highlight ? '600' : '400',
    }}>
      {value || '--'}
    </span>
  </div>
);

// ═══════════════════════════════════════════════════════════
// TAB DEFINITIONS
// ═══════════════════════════════════════════════════════════
const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'transcript', label: 'Transcript' },
  { id: 'tasks', label: 'Tasks' },
  { id: 'briefing', label: 'Briefing' },
  { id: 'application', label: 'Application Data' },
];

// ═══════════════════════════════════════════════════════════
// TASK CATEGORIES
// ═══════════════════════════════════════════════════════════
const TASK_CATEGORIES = [
  'Document Collection',
  'Verification',
  'Follow-Up',
  'Compliance',
  'Scheduling',
];

// ═══════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════
const URLASessionDetail = ({ loanId, onClose }) => {
  const [activeTab, setActiveTab] = useState('overview');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Data stores
  const [intelligence, setIntelligence] = useState(null);
  const [scores, setScores] = useState(null);
  const [transcript, setTranscript] = useState(null);
  const [tasks, setTasks] = useState(null);

  // UI state
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedTasks, setSelectedTasks] = useState(new Set());
  const [pushingTasks, setPushingTasks] = useState(false);

  // ── Fetch all data on mount ─────────────────────────────
  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const [intelligenceRes, scoreRes, transcriptRes, tasksRes] = await Promise.allSettled([
        urlaCallIntelligenceApi.getCallIntelligence(loanId),
        urlaCallIntelligenceApi.getCallScore(loanId),
        urlaCallIntelligenceApi.getTranscript(loanId),
        urlaCallIntelligenceApi.getCallTasks(loanId),
      ]);

      if (intelligenceRes.status === 'fulfilled') {
        setIntelligence(intelligenceRes.value);
      }
      if (scoreRes.status === 'fulfilled') {
        setScores(scoreRes.value);
      }
      if (transcriptRes.status === 'fulfilled') {
        setTranscript(transcriptRes.value);
      }
      if (tasksRes.status === 'fulfilled') {
        setTasks(tasksRes.value);
      }

      // If all failed, show error
      const allFailed = [intelligenceRes, scoreRes, transcriptRes, tasksRes]
        .every(r => r.status === 'rejected');
      if (allFailed) {
        const msg = intelligenceRes.reason?.message || 'Failed to load session data';
        setError(msg);
        toast.error(msg);
      }
    } catch (err) {
      const msg = err.message || 'Failed to load session data';
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, [loanId]);

  useEffect(() => {
    if (loanId) {
      fetchData();
    }
  }, [loanId, fetchData]);

  // ── Push tasks to CRM ───────────────────────────────────
  const handlePushAllTasks = async () => {
    setPushingTasks(true);
    try {
      await urlaCallIntelligenceApi.pushTasksToCrm(loanId);
      toast.success('All tasks pushed to CRM');
      // Refresh tasks
      const refreshed = await urlaCallIntelligenceApi.getCallTasks(loanId);
      setTasks(refreshed);
    } catch (err) {
      toast.error(err.message || 'Failed to push tasks to CRM');
    } finally {
      setPushingTasks(false);
    }
  };

  const handlePushSelectedTasks = async () => {
    if (selectedTasks.size === 0) {
      toast.warning('No tasks selected');
      return;
    }
    setPushingTasks(true);
    try {
      await urlaCallIntelligenceApi.pushTasksToCrm(loanId);
      toast.success(`${selectedTasks.size} task(s) pushed to CRM`);
      setSelectedTasks(new Set());
      const refreshed = await urlaCallIntelligenceApi.getCallTasks(loanId);
      setTasks(refreshed);
    } catch (err) {
      toast.error(err.message || 'Failed to push tasks to CRM');
    } finally {
      setPushingTasks(false);
    }
  };

  // ── Toggle task selection ───────────────────────────────
  const toggleTaskSelection = (taskId) => {
    setSelectedTasks(prev => {
      const next = new Set(prev);
      if (next.has(taskId)) {
        next.delete(taskId);
      } else {
        next.add(taskId);
      }
      return next;
    });
  };

  // ── Parse transcript into messages ──────────────────────
  const parsedMessages = useMemo(() => {
    if (!transcript) return [];

    // Handle array of message objects
    if (Array.isArray(transcript)) {
      return transcript.map((msg, idx) => ({
        id: msg.id || idx,
        speaker: msg.speaker || msg.role || 'Unknown',
        text: msg.text || msg.content || msg.message || '',
        timestamp: msg.timestamp || msg.time || null,
        isAgent: (msg.speaker || msg.role || '').toLowerCase().includes('agent') ||
                 (msg.speaker || msg.role || '').toLowerCase().includes('aria') ||
                 (msg.speaker || msg.role || '').toLowerCase() === 'assistant',
      }));
    }

    // Handle string transcript
    if (typeof transcript === 'string' || transcript?.transcript) {
      const text = typeof transcript === 'string' ? transcript : transcript.transcript;
      const lines = text.split('\n').filter(l => l.trim());

      return lines.map((line, idx) => {
        const speakerMatch = line.match(/^\[([^\]]+)\]:\s*(.*)$/) ||
                             line.match(/^([A-Za-z\s]+):\s*(.*)$/);

        if (speakerMatch) {
          const speaker = speakerMatch[1].trim();
          return {
            id: idx,
            speaker,
            text: speakerMatch[2],
            timestamp: null,
            isAgent: speaker.toLowerCase().includes('agent') ||
                     speaker.toLowerCase().includes('aria') ||
                     speaker.toLowerCase() === 'assistant',
          };
        }
        return { id: idx, speaker: null, text: line, timestamp: null, isAgent: false };
      });
    }

    // Handle object with messages array
    if (transcript?.messages) {
      return transcript.messages.map((msg, idx) => ({
        id: msg.id || idx,
        speaker: msg.speaker || msg.role || 'Unknown',
        text: msg.text || msg.content || '',
        timestamp: msg.timestamp || null,
        isAgent: (msg.speaker || msg.role || '').toLowerCase().includes('agent') ||
                 (msg.speaker || msg.role || '').toLowerCase().includes('aria') ||
                 (msg.speaker || msg.role || '').toLowerCase() === 'assistant',
      }));
    }

    return [];
  }, [transcript]);

  // ── Filtered messages ───────────────────────────────────
  const filteredMessages = useMemo(() => {
    if (!searchTerm) return parsedMessages;
    const term = searchTerm.toLowerCase();
    return parsedMessages.filter(
      msg => msg.text.toLowerCase().includes(term) ||
             msg.speaker?.toLowerCase().includes(term)
    );
  }, [parsedMessages, searchTerm]);

  // ── Group tasks by category ─────────────────────────────
  const groupedTasks = useMemo(() => {
    const taskList = Array.isArray(tasks) ? tasks : tasks?.tasks || [];
    const groups = {};
    TASK_CATEGORIES.forEach(cat => { groups[cat] = []; });
    groups['Other'] = [];

    taskList.forEach(task => {
      const cat = task.category || task.group || 'Other';
      const matchedCat = TASK_CATEGORIES.find(
        c => c.toLowerCase() === cat.toLowerCase()
      );
      if (matchedCat) {
        groups[matchedCat].push(task);
      } else {
        groups['Other'].push(task);
      }
    });

    return groups;
  }, [tasks]);

  // ── Extract application data ────────────────────────────
  const appData = intelligence?.application_data || intelligence?.extracted_data || {};

  // ── Extract section completion info ─────────────────────
  const sections = intelligence?.sections || intelligence?.progress?.sections || [];
  const completedSections = sections.filter(s => s.completed || s.status === 'complete').length;
  const totalSections = sections.length || 8;

  // ── Extract compliance flags ────────────────────────────
  const complianceFlags = scores?.compliance_flags || intelligence?.compliance_flags || [];

  // ── Application status ──────────────────────────────────
  const applicationStatus = intelligence?.status || intelligence?.application_status || 'unknown';

  // ═══════════════════════════════════════════════════════
  // STYLES
  // ═══════════════════════════════════════════════════════
  const styles = {
    container: {
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      background: '#fff',
      borderRadius: '12px',
      boxShadow: '0 4px 24px rgba(0,0,0,0.08)',
      overflow: 'hidden',
    },
    header: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '16px 20px',
      borderBottom: '1px solid #e5e7eb',
      background: '#fafbfc',
    },
    headerTitle: {
      fontSize: '1.1rem',
      fontWeight: '600',
      color: '#111827',
      margin: 0,
    },
    closeBtn: {
      width: '32px',
      height: '32px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'none',
      border: '1px solid #e5e7eb',
      borderRadius: '6px',
      cursor: 'pointer',
      color: '#6b7280',
    },
    tabNav: {
      display: 'flex',
      borderBottom: '1px solid #e5e7eb',
      padding: '0 20px',
      gap: '4px',
      background: '#fafbfc',
    },
    tab: (active) => ({
      padding: '10px 16px',
      fontSize: '0.8rem',
      fontWeight: active ? '600' : '400',
      color: active ? '#2563eb' : '#6b7280',
      background: 'none',
      border: 'none',
      borderBottom: active ? '2px solid #2563eb' : '2px solid transparent',
      cursor: 'pointer',
      whiteSpace: 'nowrap',
      transition: 'color 0.15s, border-color 0.15s',
    }),
    content: {
      flex: 1,
      overflow: 'auto',
      padding: '20px',
    },
    card: {
      background: '#fff',
      border: '1px solid #e5e7eb',
      borderRadius: '8px',
      padding: '16px',
      marginBottom: '16px',
    },
    cardTitle: {
      fontSize: '0.8rem',
      fontWeight: '600',
      color: '#374151',
      marginBottom: '12px',
      textTransform: 'uppercase',
      letterSpacing: '0.05em',
    },
    emptyState: {
      color: '#6b7280',
      textAlign: 'center',
      padding: '40px',
      fontSize: '0.875rem',
    },
    btnPrimary: {
      padding: '8px 16px',
      background: '#2563eb',
      color: '#fff',
      border: 'none',
      borderRadius: '6px',
      fontSize: '0.8rem',
      fontWeight: '500',
      cursor: 'pointer',
      display: 'inline-flex',
      alignItems: 'center',
      gap: '6px',
    },
    btnSecondary: {
      padding: '8px 16px',
      background: '#f3f4f6',
      color: '#374151',
      border: '1px solid #e5e7eb',
      borderRadius: '6px',
      fontSize: '0.8rem',
      fontWeight: '500',
      cursor: 'pointer',
      display: 'inline-flex',
      alignItems: 'center',
      gap: '6px',
    },
  };

  // ═══════════════════════════════════════════════════════
  // LOADING STATE
  // ═══════════════════════════════════════════════════════
  if (loading) {
    return (
      <div style={styles.container}>
        <div style={styles.header}>
          <h3 style={styles.headerTitle}>URLA Session</h3>
          <button style={styles.closeBtn} onClick={onClose}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{
              width: '40px',
              height: '40px',
              border: '3px solid #e5e7eb',
              borderTop: '3px solid #2563eb',
              borderRadius: '50%',
              animation: 'urla-spin 0.8s linear infinite',
              margin: '0 auto 12px',
            }} />
            <style>{`@keyframes urla-spin { to { transform: rotate(360deg); } }`}</style>
            <p style={{ color: '#6b7280', fontSize: '0.875rem', margin: 0 }}>
              Loading session data...
            </p>
          </div>
        </div>
      </div>
    );
  }

  // ═══════════════════════════════════════════════════════
  // ERROR STATE
  // ═══════════════════════════════════════════════════════
  if (error && !intelligence && !scores && !transcript && !tasks) {
    return (
      <div style={styles.container}>
        <div style={styles.header}>
          <h3 style={styles.headerTitle}>URLA Session</h3>
          <button style={styles.closeBtn} onClick={onClose}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ textAlign: 'center', padding: '40px' }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2" width="40" height="40" style={{ margin: '0 auto 12px', display: 'block' }}>
              <circle cx="12" cy="12" r="10" />
              <line x1="15" y1="9" x2="9" y2="15" />
              <line x1="9" y1="9" x2="15" y2="15" />
            </svg>
            <p style={{ color: '#374151', fontSize: '0.875rem', marginBottom: '16px' }}>{error}</p>
            <button style={styles.btnPrimary} onClick={fetchData}>
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ═══════════════════════════════════════════════════════
  // OVERVIEW TAB
  // ═══════════════════════════════════════════════════════
  const renderOverview = () => (
    <div>
      {/* Status + Progress */}
      <div style={styles.card}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
          <div style={styles.cardTitle}>Application Status</div>
          <span style={{
            ...getStatusStyle(applicationStatus),
            padding: '4px 12px',
            borderRadius: '12px',
            fontSize: '0.75rem',
            fontWeight: '600',
            textTransform: 'capitalize',
          }}>
            {applicationStatus.replace(/_/g, ' ')}
          </span>
        </div>
        <ProgressBar
          completed={completedSections}
          total={totalSections}
          label="Sections Completed"
        />
        {sections.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '8px' }}>
            {sections.map((section, idx) => (
              <span
                key={idx}
                style={{
                  fontSize: '0.7rem',
                  padding: '3px 8px',
                  borderRadius: '4px',
                  background: (section.completed || section.status === 'complete') ? '#dcfce7' : '#f3f4f6',
                  color: (section.completed || section.status === 'complete') ? '#166534' : '#6b7280',
                  fontWeight: '500',
                }}
              >
                {section.name || section.label || `Section ${idx + 1}`}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Score Cards */}
      <div style={styles.card}>
        <div style={styles.cardTitle}>Quality Scores</div>
        <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
          <ScoreGauge
            label="Compliance"
            score={scores?.compliance_score ?? scores?.compliance ?? null}
          />
          <ScoreGauge
            label="Data Quality"
            score={scores?.data_quality_score ?? scores?.data_quality ?? null}
          />
          <ScoreGauge
            label="Conversation"
            score={scores?.conversation_quality_score ?? scores?.conversation_quality ?? null}
          />
          <ScoreGauge
            label="Overall"
            score={scores?.overall_score ?? scores?.overall ?? null}
          />
        </div>
        {scores?.overall_score != null && (
          <div style={{
            marginTop: '12px',
            padding: '8px 12px',
            background: '#f9fafb',
            borderRadius: '6px',
            textAlign: 'center',
            fontSize: '0.8rem',
            color: getScoreColor(scores.overall_score),
            fontWeight: '500',
          }}>
            {getScoreLabel(scores.overall_score)}
          </div>
        )}
      </div>

      {/* Compliance Flags */}
      {complianceFlags.length > 0 && (
        <div style={styles.card}>
          <div style={styles.cardTitle}>Compliance Flags</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {complianceFlags.map((flag, idx) => (
              <div
                key={idx}
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '10px',
                  padding: '10px 12px',
                  background: '#fafbfc',
                  borderRadius: '6px',
                  border: '1px solid #f3f4f6',
                }}
              >
                <span style={{
                  ...getSeverityStyle(flag.severity),
                  padding: '2px 8px',
                  borderRadius: '4px',
                  fontSize: '0.65rem',
                  fontWeight: '600',
                  textTransform: 'uppercase',
                  whiteSpace: 'nowrap',
                  flexShrink: 0,
                }}>
                  {flag.severity || 'info'}
                </span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: '0.8rem', color: '#111827', fontWeight: '500' }}>
                    {flag.title || flag.name || flag.rule || 'Flag'}
                  </div>
                  {flag.description && (
                    <div style={{ fontSize: '0.75rem', color: '#6b7280', marginTop: '2px' }}>
                      {flag.description}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {complianceFlags.length === 0 && (
        <div style={styles.card}>
          <div style={styles.cardTitle}>Compliance Flags</div>
          <div style={{
            padding: '20px',
            textAlign: 'center',
            color: '#2D7A52',
            fontSize: '0.8rem',
          }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="#2D7A52" strokeWidth="2" width="24" height="24" style={{ display: 'block', margin: '0 auto 8px' }}>
              <path d="M22 11.08V12a10 10 0 11-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
            No compliance flags detected
          </div>
        </div>
      )}
    </div>
  );

  // ═══════════════════════════════════════════════════════
  // TRANSCRIPT TAB
  // ═══════════════════════════════════════════════════════
  const renderTranscript = () => (
    <div>
      {/* Search */}
      <div style={{ marginBottom: '16px' }}>
        <input
          type="text"
          placeholder="Search transcript..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          style={{
            width: '100%',
            padding: '10px 14px',
            border: '1px solid #e5e7eb',
            borderRadius: '8px',
            fontSize: '0.875rem',
            outline: 'none',
            boxSizing: 'border-box',
          }}
        />
        {searchTerm && (
          <div style={{ fontSize: '0.75rem', color: '#6b7280', marginTop: '4px' }}>
            {filteredMessages.length} of {parsedMessages.length} messages
          </div>
        )}
      </div>

      {/* Messages */}
      {filteredMessages.length === 0 && (
        <p style={styles.emptyState}>
          {searchTerm ? 'No messages match your search.' : 'No transcript available.'}
        </p>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {filteredMessages.map((msg) => (
          <div
            key={msg.id}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: msg.isAgent ? 'flex-start' : 'flex-end',
            }}
          >
            {msg.speaker && (
              <span style={{
                fontSize: '0.65rem',
                color: '#9ca3af',
                marginBottom: '2px',
                fontWeight: '500',
                paddingLeft: msg.isAgent ? '12px' : '0',
                paddingRight: msg.isAgent ? '0' : '12px',
              }}>
                {msg.speaker}
                {msg.timestamp && ` \u00b7 ${formatDate(msg.timestamp)}`}
              </span>
            )}
            <div style={{
              maxWidth: '80%',
              padding: '10px 14px',
              borderRadius: msg.isAgent ? '4px 12px 12px 12px' : '12px 4px 12px 12px',
              background: msg.isAgent ? '#2563eb' : '#f3f4f6',
              color: msg.isAgent ? '#fff' : '#111827',
              fontSize: '0.8rem',
              lineHeight: '1.5',
              wordBreak: 'break-word',
            }}>
              {msg.text}
            </div>
            {msg.timestamp && !msg.speaker && (
              <span style={{
                fontSize: '0.6rem',
                color: '#d1d5db',
                marginTop: '2px',
                paddingLeft: msg.isAgent ? '12px' : '0',
                paddingRight: msg.isAgent ? '0' : '12px',
              }}>
                {formatDate(msg.timestamp)}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );

  // ═══════════════════════════════════════════════════════
  // TASKS TAB
  // ═══════════════════════════════════════════════════════
  const renderTasks = () => {
    const taskList = Array.isArray(tasks) ? tasks : tasks?.tasks || [];
    const taskCount = taskList.length;

    return (
      <div>
        {/* Action Bar */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '16px',
          flexWrap: 'wrap',
          gap: '8px',
        }}>
          <span style={{ fontSize: '0.8rem', color: '#6b7280' }}>
            {taskCount} task{taskCount !== 1 ? 's' : ''} generated
          </span>
          <div style={{ display: 'flex', gap: '8px' }}>
            {selectedTasks.size > 0 && (
              <button
                style={styles.btnSecondary}
                onClick={handlePushSelectedTasks}
                disabled={pushingTasks}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14">
                  <path d="M22 2L11 13" />
                  <path d="M22 2L15 22L11 13L2 9L22 2Z" />
                </svg>
                Push Selected ({selectedTasks.size})
              </button>
            )}
            <button
              style={styles.btnPrimary}
              onClick={handlePushAllTasks}
              disabled={pushingTasks || taskCount === 0}
            >
              {pushingTasks ? (
                <>
                  <span style={{
                    width: '14px',
                    height: '14px',
                    border: '2px solid rgba(255,255,255,0.3)',
                    borderTop: '2px solid #fff',
                    borderRadius: '50%',
                    animation: 'urla-spin 0.8s linear infinite',
                    display: 'inline-block',
                  }} />
                  Pushing...
                </>
              ) : (
                <>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14">
                    <path d="M22 2L11 13" />
                    <path d="M22 2L15 22L11 13L2 9L22 2Z" />
                  </svg>
                  Push All to CRM
                </>
              )}
            </button>
          </div>
        </div>

        {taskCount === 0 && (
          <p style={styles.emptyState}>No tasks generated for this session.</p>
        )}

        {/* Grouped Tasks */}
        {Object.entries(groupedTasks).map(([category, catTasks]) => {
          if (catTasks.length === 0) return null;

          return (
            <div key={category} style={{ marginBottom: '20px' }}>
              <h4 style={{
                fontSize: '0.8rem',
                fontWeight: '600',
                color: '#374151',
                marginBottom: '8px',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}>
                {category}
                <span style={{
                  fontSize: '0.65rem',
                  background: '#e5e7eb',
                  color: '#6b7280',
                  padding: '1px 6px',
                  borderRadius: '10px',
                  fontWeight: '500',
                }}>
                  {catTasks.length}
                </span>
              </h4>

              {catTasks.map((task, idx) => {
                const taskId = task.id || `${category}-${idx}`;
                const isSelected = selectedTasks.has(taskId);

                return (
                  <div
                    key={taskId}
                    style={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: '10px',
                      padding: '12px',
                      border: isSelected ? '1px solid #93c5fd' : '1px solid #e5e7eb',
                      borderRadius: '8px',
                      marginBottom: '6px',
                      background: isSelected ? '#eff6ff' : '#fff',
                      transition: 'border-color 0.15s, background 0.15s',
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleTaskSelection(taskId)}
                      style={{ marginTop: '2px', cursor: 'pointer' }}
                    />
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                        <span style={{ fontSize: '0.8rem', fontWeight: '600', color: '#111827' }}>
                          {task.title || task.name || 'Task'}
                        </span>
                        <span style={{
                          ...getPriorityStyle(task.priority),
                          padding: '1px 8px',
                          borderRadius: '4px',
                          fontSize: '0.65rem',
                          fontWeight: '600',
                          textTransform: 'uppercase',
                        }}>
                          {task.priority || 'medium'}
                        </span>
                      </div>
                      {(task.description || task.content) && (
                        <div style={{ fontSize: '0.75rem', color: '#6b7280', lineHeight: '1.4' }}>
                          {task.description || task.content}
                        </div>
                      )}
                      {task.due_date && (
                        <div style={{ fontSize: '0.7rem', color: '#9ca3af', marginTop: '4px' }}>
                          Due: {formatShortDate(task.due_date)}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    );
  };

  // ═══════════════════════════════════════════════════════
  // BRIEFING TAB
  // ═══════════════════════════════════════════════════════
  const renderBriefing = () => {
    // Lazy-load URLALOBriefing to avoid hard dependency on a component
    // that may not exist yet. Falls back to an inline display.
    let URLALOBriefing = null;
    try {
      // Dynamic import is async; for synchronous render we use require
      // eslint-disable-next-line
      URLALOBriefing = require('./URLALOBriefing').default;
    } catch {
      // Component not available yet
    }

    if (URLALOBriefing) {
      return <URLALOBriefing loanId={loanId} />;
    }

    // Fallback: fetch and display briefing inline
    return <InlineBriefing loanId={loanId} />;
  };

  // ═══════════════════════════════════════════════════════
  // APPLICATION DATA TAB
  // ═══════════════════════════════════════════════════════
  const renderApplicationData = () => {
    const personal = appData?.personal_info || appData?.borrower || appData?.section_1a || {};
    const employment = appData?.employment || appData?.section_1b || {};
    const assets = appData?.assets_liabilities || appData?.section_2 || {};
    const loanProperty = appData?.loan_property || appData?.section_4 || {};
    const declarations = appData?.declarations || appData?.section_5 || {};
    const military = appData?.military_service || appData?.section_7 || {};
    const demographics = appData?.demographics || appData?.section_8 || {};

    const isEmpty = Object.keys(appData).length === 0;

    if (isEmpty) {
      return <p style={styles.emptyState}>No application data extracted for this session.</p>;
    }

    return (
      <div>
        {/* Section 1a: Personal Info */}
        <CollapsibleSection title="Section 1a: Personal Information" defaultOpen={true}>
          <DataRow label="First Name" value={personal.first_name} />
          <DataRow label="Last Name" value={personal.last_name} />
          <DataRow label="Email" value={personal.email} />
          <DataRow label="Phone" value={personal.phone} />
          <DataRow label="SSN" value={maskSSN(personal.ssn || personal.social_security)} />
          <DataRow label="Date of Birth" value={personal.date_of_birth || personal.dob} />
          <DataRow label="Marital Status" value={personal.marital_status} />
          <DataRow label="Dependents" value={personal.dependents} />
          <DataRow label="Current Address" value={personal.current_address || personal.address} />
          <DataRow label="Citizenship" value={personal.citizenship} />
        </CollapsibleSection>

        {/* Section 1b: Employment */}
        <CollapsibleSection title="Section 1b: Employment">
          {Array.isArray(employment) ? (
            employment.map((emp, idx) => (
              <div key={idx} style={{ marginBottom: '12px' }}>
                {idx > 0 && <hr style={{ border: 'none', borderTop: '1px solid #f3f4f6', margin: '8px 0' }} />}
                <DataRow label="Employer" value={emp.employer_name || emp.employer} />
                <DataRow label="Position" value={emp.position || emp.title} />
                <DataRow label="Start Date" value={emp.start_date} />
                <DataRow label="End Date" value={emp.end_date || 'Present'} />
                <DataRow label="Monthly Income" value={formatCurrency(emp.monthly_income || emp.income)} />
                <DataRow label="Employment Type" value={emp.employment_type || emp.type} />
              </div>
            ))
          ) : (
            <>
              <DataRow label="Employer" value={employment.employer_name || employment.employer} />
              <DataRow label="Position" value={employment.position || employment.title} />
              <DataRow label="Start Date" value={employment.start_date} />
              <DataRow label="Monthly Income" value={formatCurrency(employment.monthly_income || employment.income)} />
              <DataRow label="Employment Type" value={employment.employment_type || employment.type} />
              <DataRow label="Years in Field" value={employment.years_in_field} />
            </>
          )}
        </CollapsibleSection>

        {/* Section 2: Assets & Liabilities */}
        <CollapsibleSection title="Section 2: Assets & Liabilities">
          {assets.total_assets != null && (
            <DataRow label="Total Assets" value={formatCurrency(assets.total_assets)} />
          )}
          {assets.total_liabilities != null && (
            <DataRow label="Total Liabilities" value={formatCurrency(assets.total_liabilities)} />
          )}
          {Array.isArray(assets.accounts) && assets.accounts.map((acct, idx) => (
            <DataRow
              key={idx}
              label={acct.institution || acct.name || `Account ${idx + 1}`}
              value={formatCurrency(acct.balance || acct.value)}
            />
          ))}
          {Object.keys(assets).length === 0 && (
            <p style={{ color: '#6b7280', fontSize: '0.8rem', margin: '8px 0' }}>No data collected</p>
          )}
        </CollapsibleSection>

        {/* Section 4: Loan & Property */}
        <CollapsibleSection title="Section 4: Loan & Property">
          <DataRow label="Loan Purpose" value={loanProperty.loan_purpose || loanProperty.purpose} />
          <DataRow label="Loan Amount" value={formatCurrency(loanProperty.loan_amount || loanProperty.amount)} />
          <DataRow label="Property Address" value={loanProperty.property_address || loanProperty.address} />
          <DataRow label="Property Type" value={loanProperty.property_type} />
          <DataRow label="Occupancy" value={loanProperty.occupancy || loanProperty.occupancy_type} />
          <DataRow label="Estimated Value" value={formatCurrency(loanProperty.estimated_value || loanProperty.property_value)} />
          <DataRow label="Down Payment" value={formatCurrency(loanProperty.down_payment)} />
        </CollapsibleSection>

        {/* Section 5: Declarations */}
        <CollapsibleSection title="Section 5: Declarations">
          {typeof declarations === 'object' && Object.entries(declarations).map(([key, value]) => {
            const label = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
            const isYes = value === true || value === 'yes' || value === 'Yes';
            return (
              <DataRow
                key={key}
                label={label}
                value={typeof value === 'boolean' ? (value ? 'Yes' : 'No') : String(value || '--')}
                highlight={isYes}
              />
            );
          })}
          {Object.keys(declarations).length === 0 && (
            <p style={{ color: '#6b7280', fontSize: '0.8rem', margin: '8px 0' }}>No data collected</p>
          )}
        </CollapsibleSection>

        {/* Section 7: Military Service */}
        <CollapsibleSection title="Section 7: Military Service">
          <DataRow label="Currently Serving" value={
            military.currently_serving != null
              ? (military.currently_serving ? 'Yes' : 'No')
              : military.status || '--'
          } />
          <DataRow label="Veteran" value={
            military.veteran != null ? (military.veteran ? 'Yes' : 'No') : '--'
          } />
          <DataRow label="Branch" value={military.branch} />
          <DataRow label="Service Period" value={military.service_period || military.dates} />
          {Object.keys(military).length === 0 && (
            <p style={{ color: '#6b7280', fontSize: '0.8rem', margin: '8px 0' }}>No data collected</p>
          )}
        </CollapsibleSection>

        {/* Section 8: Demographics */}
        <CollapsibleSection title="Section 8: Demographics">
          <DataRow label="Ethnicity" value={demographics.ethnicity} />
          <DataRow label="Race" value={
            Array.isArray(demographics.race) ? demographics.race.join(', ') : demographics.race
          } />
          <DataRow label="Sex" value={demographics.sex || demographics.gender} />
          {Object.keys(demographics).length === 0 && (
            <p style={{ color: '#6b7280', fontSize: '0.8rem', margin: '8px 0' }}>No data collected</p>
          )}
        </CollapsibleSection>
      </div>
    );
  };

  // ═══════════════════════════════════════════════════════
  // RENDER
  // ═══════════════════════════════════════════════════════
  return (
    <div style={styles.container}>
      {/* Header */}
      <div style={styles.header}>
        <div>
          <h3 style={styles.headerTitle}>URLA Session Detail</h3>
          {intelligence?.borrower_name && (
            <div style={{ fontSize: '0.8rem', color: '#6b7280', marginTop: '2px' }}>
              {intelligence.borrower_name}
              {intelligence?.created_at && (
                <span> &middot; {formatDate(intelligence.created_at)}</span>
              )}
            </div>
          )}
        </div>
        <button style={styles.closeBtn} onClick={onClose} title="Close">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      {/* Tab Navigation */}
      <div style={styles.tabNav}>
        {TABS.map(tab => (
          <button
            key={tab.id}
            style={styles.tab(activeTab === tab.id)}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
            {tab.id === 'tasks' && tasks && (
              <span style={{
                marginLeft: '4px',
                fontSize: '0.65rem',
                background: activeTab === 'tasks' ? '#dbeafe' : '#e5e7eb',
                color: activeTab === 'tasks' ? '#2563eb' : '#6b7280',
                padding: '1px 6px',
                borderRadius: '10px',
                fontWeight: '500',
              }}>
                {(Array.isArray(tasks) ? tasks : tasks?.tasks || []).length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div style={styles.content}>
        {activeTab === 'overview' && renderOverview()}
        {activeTab === 'transcript' && renderTranscript()}
        {activeTab === 'tasks' && renderTasks()}
        {activeTab === 'briefing' && renderBriefing()}
        {activeTab === 'application' && renderApplicationData()}
      </div>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// INLINE BRIEFING (fallback when URLALOBriefing doesn't exist)
// ═══════════════════════════════════════════════════════════
const InlineBriefing = ({ loanId }) => {
  const [briefing, setBriefing] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;

    const fetchBriefing = async () => {
      setLoading(true);
      try {
        const data = await urlaCallIntelligenceApi.getLOBriefingHtml(loanId);
        if (!cancelled) setBriefing(data);
      } catch (err) {
        if (!cancelled) {
          // Fall back to JSON briefing
          try {
            const jsonData = await urlaCallIntelligenceApi.getLOBriefing(loanId);
            if (!cancelled) setBriefing(jsonData);
          } catch (innerErr) {
            if (!cancelled) setError(innerErr.message || 'Failed to load briefing');
          }
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchBriefing();
    return () => { cancelled = true; };
  }, [loanId]);

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '40px', color: '#6b7280' }}>
        Loading briefing...
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ textAlign: 'center', padding: '40px', color: '#ef4444', fontSize: '0.875rem' }}>
        {error}
      </div>
    );
  }

  if (!briefing) {
    return (
      <div style={{ textAlign: 'center', padding: '40px', color: '#6b7280', fontSize: '0.875rem' }}>
        No briefing available for this session.
      </div>
    );
  }

  // If HTML string
  if (typeof briefing === 'string' && briefing.includes('<')) {
    return (
      <div
        style={{
          fontSize: '0.875rem',
          lineHeight: '1.6',
          color: '#374151',
        }}
        dangerouslySetInnerHTML={{ __html: sanitizeHTML(briefing) }}
      />
    );
  }

  // If JSON briefing object
  if (typeof briefing === 'object') {
    return (
      <div style={{ fontSize: '0.875rem', lineHeight: '1.6', color: '#374151' }}>
        {briefing.title && (
          <h3 style={{ fontSize: '1rem', fontWeight: '600', color: '#111827', marginBottom: '12px' }}>
            {briefing.title}
          </h3>
        )}
        {briefing.summary && (
          <div style={{
            padding: '12px 16px',
            background: '#f9fafb',
            borderRadius: '8px',
            marginBottom: '16px',
            border: '1px solid #e5e7eb',
          }}>
            {briefing.summary}
          </div>
        )}
        {briefing.key_points && Array.isArray(briefing.key_points) && (
          <div style={{ marginBottom: '16px' }}>
            <h4 style={{ fontSize: '0.85rem', fontWeight: '600', marginBottom: '8px' }}>Key Points</h4>
            <ul style={{ margin: 0, paddingLeft: '20px' }}>
              {briefing.key_points.map((point, idx) => (
                <li key={idx} style={{ marginBottom: '4px' }}>{point}</li>
              ))}
            </ul>
          </div>
        )}
        {briefing.action_items && Array.isArray(briefing.action_items) && (
          <div>
            <h4 style={{ fontSize: '0.85rem', fontWeight: '600', marginBottom: '8px' }}>Action Items</h4>
            <ul style={{ margin: 0, paddingLeft: '20px' }}>
              {briefing.action_items.map((item, idx) => (
                <li key={idx} style={{ marginBottom: '4px' }}>{typeof item === 'string' ? item : item.title || item.description || JSON.stringify(item)}</li>
              ))}
            </ul>
          </div>
        )}
        {!briefing.summary && !briefing.key_points && !briefing.action_items && (
          <pre style={{
            background: '#f9fafb',
            padding: '16px',
            borderRadius: '8px',
            fontSize: '0.75rem',
            overflow: 'auto',
            whiteSpace: 'pre-wrap',
            border: '1px solid #e5e7eb',
          }}>
            {JSON.stringify(briefing, null, 2)}
          </pre>
        )}
      </div>
    );
  }

  // Fallback: plain text
  return (
    <div style={{
      fontSize: '0.875rem',
      lineHeight: '1.6',
      color: '#374151',
      whiteSpace: 'pre-wrap',
    }}>
      {String(briefing)}
    </div>
  );
};

export default URLASessionDetail;
