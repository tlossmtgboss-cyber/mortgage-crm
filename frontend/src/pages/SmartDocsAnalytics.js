/**
 * SmartDocsAnalytics Page
 *
 * Full analytics dashboard with 5 tabs and a period selector.
 * Tabs: Overview, SLA Compliance, AI Performance, Team Productivity, Bottlenecks
 */
import React, { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import { useDocAnalytics } from '../hooks/useDocAnalytics';
import AnalyticsCard from '../components/smart-docs/AnalyticsCard';
import {
  getAiPerformance,
  getProcessorProductivity,
  getTrends,
} from '../services/docAnalyticsApi';
import './SmartDocsAnalytics.css';

const PERIOD_OPTIONS = [
  { value: 7, label: '7 days' },
  { value: 30, label: '30 days' },
  { value: 90, label: '90 days' },
];

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'sla', label: 'SLA Compliance' },
  { id: 'ai', label: 'AI Performance' },
  { id: 'team', label: 'Team Productivity' },
  { id: 'bottlenecks', label: 'Bottlenecks' },
];

const SEVERITY_LABELS = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
};

function SmartDocsAnalytics() {
  const [days, setDays] = useState(30);
  const [activeTab, setActiveTab] = useState('overview');

  // Extended data loaded separately
  const [aiPerf, setAiPerf] = useState(null);
  const [processorData, setProcessorData] = useState(null);
  const [trends, setTrends] = useState(null);

  const { dashboard, sla, bottlenecks, loading, error, refresh } = useDocAnalytics(days);

  // Load extended data when days or activeTab changes
  useEffect(() => {
    let cancelled = false;

    async function fetchExtended() {
      try {
        const [aiData, procData, trendData] = await Promise.all([
          getAiPerformance(days),
          getProcessorProductivity(days),
          getTrends('weekly', days),
        ]);
        if (!cancelled) {
          setAiPerf(aiData);
          setProcessorData(procData);
          setTrends(trendData);
        }
      } catch (err) {
        if (!cancelled) {
          toast.error('Failed to load extended analytics data');
        }
      }
    }

    fetchExtended();

    return () => {
      cancelled = true;
    };
  }, [days]);

  function handlePeriodChange(e) {
    setDays(Number(e.target.value));
  }

  function handleRefresh() {
    refresh();
  }

  if (loading) {
    return (
      <div className="sd-analytics">
        <div className="loading">Loading analytics...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="sd-analytics">
        <div className="error">
          <p>Failed to load analytics: {error}</p>
          <button onClick={handleRefresh} className="sd-analytics__refresh-btn">
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="sd-analytics">
      {/* Header */}
      <div className="sd-analytics__header">
        <div className="sd-analytics__title-group">
          <h1 className="sd-analytics__title">Document Analytics</h1>
          <p className="sd-analytics__subtitle">
            Performance metrics and compliance insights
          </p>
        </div>
        <div className="sd-analytics__controls">
          <select
            className="sd-analytics__period-select"
            value={days}
            onChange={handlePeriodChange}
            aria-label="Select time period"
          >
            {PERIOD_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <button className="sd-analytics__refresh-btn" onClick={handleRefresh}>
            Refresh
          </button>
        </div>
      </div>

      {/* Tab Bar */}
      <div className="sd-analytics__tabs" role="tablist">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            className={[
              'sd-analytics__tab',
              activeTab === tab.id ? 'sd-analytics__tab--active' : '',
            ]
              .filter(Boolean)
              .join(' ')}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="sd-analytics__content" role="tabpanel">
        {activeTab === 'overview' && <OverviewTab dashboard={dashboard} />}
        {activeTab === 'sla' && <SlaTab sla={sla} />}
        {activeTab === 'ai' && <AiTab aiPerf={aiPerf} />}
        {activeTab === 'team' && <TeamTab processorData={processorData} />}
        {activeTab === 'bottlenecks' && <BottlenecksTab bottlenecks={bottlenecks} />}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Overview Tab
// ---------------------------------------------------------------------------

function OverviewTab({ dashboard }) {
  const d = dashboard || {};

  return (
    <div className="sd-analytics__grid">
      <AnalyticsCard
        title="Total Documents"
        value={d.total_documents ?? '-'}
        subtitle={`Last ${d.period_days ?? 30} days`}
      />
      <AnalyticsCard
        title="Pending Review"
        value={d.pending_review ?? '-'}
        status={d.pending_review > 20 ? 'warning' : undefined}
        subtitle="Awaiting review"
      />
      <AnalyticsCard
        title="Approved"
        value={d.approved ?? '-'}
        status="success"
        subtitle="Documents approved"
      />
      <AnalyticsCard
        title="Rejected"
        value={d.rejected ?? '-'}
        status={d.rejected > 10 ? 'error' : undefined}
        subtitle="Documents rejected"
      />
      <AnalyticsCard
        title="Avg Review Time"
        value={d.avg_review_hours != null ? `${d.avg_review_hours}h` : '-'}
        subtitle="Hours per document"
      />
      <AnalyticsCard
        title="Auto-Approved"
        value={d.auto_approved ?? '-'}
        subtitle="AI auto-approvals"
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// SLA Compliance Tab
// ---------------------------------------------------------------------------

function SlaTab({ sla }) {
  const s = sla || {};
  const byDocType = s.by_doc_type || [];

  return (
    <div>
      <div className="sd-analytics__grid sd-analytics__grid--2">
        <AnalyticsCard
          title="SLA Compliance Rate"
          value={s.compliance_rate != null ? `${s.compliance_rate}%` : '-'}
          status={
            s.compliance_rate >= 90
              ? 'success'
              : s.compliance_rate >= 70
              ? 'warning'
              : 'error'
          }
          subtitle="Documents reviewed on time"
        />
        <AnalyticsCard
          title="SLA Breaches"
          value={s.breaches ?? '-'}
          status={s.breaches > 0 ? 'error' : 'success'}
          subtitle="Documents past SLA deadline"
        />
      </div>

      {byDocType.length > 0 && (
        <div className="sd-analytics__table-container">
          <table className="sd-analytics__table">
            <thead>
              <tr>
                <th>Doc Type</th>
                <th>Total</th>
                <th>On Time</th>
                <th>Breached</th>
                <th>Rate</th>
              </tr>
            </thead>
            <tbody>
              {byDocType.map((row, idx) => (
                <tr key={row.doc_type || idx}>
                  <td>{row.doc_type}</td>
                  <td>{row.total ?? '-'}</td>
                  <td>{row.on_time ?? '-'}</td>
                  <td>{row.breached ?? '-'}</td>
                  <td>
                    {row.rate != null ? `${row.rate}%` : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// AI Performance Tab
// ---------------------------------------------------------------------------

function AiTab({ aiPerf }) {
  const a = aiPerf || {};

  return (
    <div className="sd-analytics__grid">
      <AnalyticsCard
        title="Accuracy"
        value={a.accuracy != null ? `${a.accuracy}%` : '-'}
        status={a.accuracy >= 90 ? 'success' : a.accuracy >= 75 ? 'warning' : 'error'}
        subtitle="Classification accuracy"
      />
      <AnalyticsCard
        title="Total Reviewed"
        value={a.total_reviewed ?? '-'}
        subtitle="Documents processed by AI"
      />
      <AnalyticsCard
        title="Auto-Approved"
        value={a.auto_approved ?? '-'}
        status="success"
        subtitle="Automatically approved"
      />
      <AnalyticsCard
        title="Escalated"
        value={a.escalated ?? '-'}
        subtitle="Sent for human review"
      />
      <AnalyticsCard
        title="Avg Confidence"
        value={a.avg_confidence != null ? `${a.avg_confidence}%` : '-'}
        subtitle="Mean AI confidence score"
      />
      <AnalyticsCard
        title="False Rejections"
        value={a.false_rejections ?? '-'}
        status={a.false_rejections > 5 ? 'error' : undefined}
        subtitle="Incorrectly rejected"
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Team Productivity Tab
// ---------------------------------------------------------------------------

function TeamTab({ processorData }) {
  const processors = (processorData && processorData.processors) || [];

  if (processors.length === 0) {
    return (
      <div className="sd-analytics__empty">
        No processor data available for this period.
      </div>
    );
  }

  return (
    <div className="sd-analytics__table-container">
      <table className="sd-analytics__table">
        <thead>
          <tr>
            <th>Processor</th>
            <th>Reviewed</th>
            <th>Approved</th>
            <th>Rejected</th>
            <th>Avg Time</th>
          </tr>
        </thead>
        <tbody>
          {processors.map((proc, idx) => (
            <tr key={proc.processor_id || proc.name || idx}>
              <td>{proc.name || proc.processor_name || 'Unknown'}</td>
              <td>{proc.reviewed ?? '-'}</td>
              <td>{proc.approved ?? '-'}</td>
              <td>{proc.rejected ?? '-'}</td>
              <td>
                {proc.avg_time != null ? `${proc.avg_time}h` : '-'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Bottlenecks Tab
// ---------------------------------------------------------------------------

function BottlenecksTab({ bottlenecks }) {
  const items =
    bottlenecks && bottlenecks.bottlenecks
      ? bottlenecks.bottlenecks
      : Array.isArray(bottlenecks)
      ? bottlenecks
      : [];

  if (items.length === 0) {
    return (
      <div className="sd-analytics__empty">
        No bottlenecks detected.
      </div>
    );
  }

  return (
    <div className="sd-analytics__bottleneck-list">
      {items.map((item, idx) => (
        <div
          key={idx}
          className={[
            'sd-analytics__bottleneck',
            item.severity ? `sd-analytics__bottleneck--${item.severity}` : '',
          ]
            .filter(Boolean)
            .join(' ')}
        >
          <div className="sd-analytics__bottleneck-header">
            <span className="sd-analytics__bottleneck-name">
              {item.stage || item.doc_type || 'Unknown stage'}
            </span>
            {item.severity && (
              <span
                className={`sd-analytics__severity-badge sd-analytics__severity-badge--${item.severity}`}
              >
                {SEVERITY_LABELS[item.severity] || item.severity}
              </span>
            )}
          </div>
          {item.description && (
            <p className="sd-analytics__bottleneck-desc">{item.description}</p>
          )}
          <div className="sd-analytics__bottleneck-meta">
            {item.count != null && (
              <span className="sd-analytics__bottleneck-stat">
                {item.count} documents
              </span>
            )}
            {item.avg_days != null && (
              <span className="sd-analytics__bottleneck-stat">
                Avg {item.avg_days} days
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

export default SmartDocsAnalytics;
