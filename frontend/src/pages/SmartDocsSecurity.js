import React, { useState, useEffect, useCallback } from 'react';
import {
  getAuditLog,
  getComplianceReport,
  getSuspiciousActivity,
  getRetentionPolicies,
} from '../services/docSecurityApi';
import AnalyticsCard from '../components/smart-docs/AnalyticsCard';
import { toast } from '../utils/toast';
import './SmartDocsSecurity.css';

const TABS = [
  { key: 'audit', label: 'Audit Log' },
  { key: 'compliance', label: 'Compliance Report' },
  { key: 'suspicious', label: 'Suspicious Activity' },
  { key: 'retention', label: 'Retention Policies' },
];

const PERIOD_OPTIONS = [
  { value: 7, label: 'Last 7 days' },
  { value: 30, label: 'Last 30 days' },
  { value: 90, label: 'Last 90 days' },
  { value: 365, label: 'Last 365 days' },
];

const ACTION_COLORS = {
  view: { bg: '#dbeafe', color: '#1d4ed8' },
  download: { bg: '#dcfce7', color: '#15803d' },
  upload: { bg: '#ede9fe', color: '#6d28d9' },
  delete: { bg: '#fee2e2', color: '#dc2626' },
  share: { bg: '#fef3c7', color: '#92400e' },
  edit: { bg: '#ffedd5', color: '#c2410c' },
  encrypt: { bg: '#e0f2fe', color: '#0369a1' },
  watermark: { bg: '#fce7f3', color: '#9d174d' },
};

const SEVERITY_STYLES = {
  critical: { bg: '#fee2e2', border: '#dc2626', color: '#991b1b', label: 'Critical' },
  high: { bg: '#ffedd5', border: '#f97316', color: '#c2410c', label: 'High' },
  medium: { bg: '#fef3c7', border: '#f59e0b', color: '#92400e', label: 'Medium' },
  low: { bg: '#f0fdf4', border: '#22c55e', color: '#15803d', label: 'Low' },
};

function getActionStyle(action) {
  if (!action) return { bg: '#f1f5f9', color: '#475569' };
  const key = action.toLowerCase();
  return ACTION_COLORS[key] || { bg: '#f1f5f9', color: '#475569' };
}

function getSeverityStyle(severity) {
  const key = (severity || '').toLowerCase();
  return SEVERITY_STYLES[key] || SEVERITY_STYLES.low;
}

function formatTimestamp(ts) {
  if (!ts) return '—';
  try {
    return new Date(ts).toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return ts;
  }
}

// ---------------------------------------------------------------------------
// Audit Log Tab
// ---------------------------------------------------------------------------
function AuditLogTab({ entries }) {
  if (!entries || entries.length === 0) {
    return (
      <div className="sd-security__empty">
        No audit log entries found for this period.
      </div>
    );
  }

  return (
    <div className="sd-security__table-container">
      <table className="sd-security__table">
        <thead>
          <tr>
            <th>Timestamp</th>
            <th>User</th>
            <th>Action</th>
            <th>Document</th>
            <th>Details</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry, idx) => {
            const actionStyle = getActionStyle(entry.action);
            return (
              <tr key={entry.id || idx}>
                <td className="sd-security__ts-cell">
                  {formatTimestamp(entry.timestamp || entry.created_at)}
                </td>
                <td>{entry.user_name || entry.user_email || entry.user_id || '—'}</td>
                <td>
                  <span
                    className="sd-security__badge"
                    style={{ background: actionStyle.bg, color: actionStyle.color }}
                  >
                    {entry.action || '—'}
                  </span>
                </td>
                <td>{entry.document_name || entry.document_id || '—'}</td>
                <td className="sd-security__details-cell">
                  {entry.details || '—'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Compliance Report Tab
// ---------------------------------------------------------------------------
function ComplianceReportTab({ report }) {
  if (!report) {
    return <div className="sd-security__empty">No compliance data available.</div>;
  }

  const score = report.compliance_score ?? report.score ?? 0;
  const encrypted = report.encrypted_documents ?? report.encrypted ?? 0;
  const integrity = report.integrity_verified ?? report.verified ?? 0;
  const retention = report.retention_compliant ?? report.compliant ?? 0;
  const issues = report.open_issues || report.issues || [];

  return (
    <div>
      <div className="sd-security__grid">
        <AnalyticsCard
          title="Compliance Score"
          value={`${Math.round(score)}%`}
          status={score >= 90 ? 'success' : score >= 70 ? 'warning' : 'error'}
          subtitle="Overall document compliance"
        />
        <AnalyticsCard
          title="Encrypted Documents"
          value={encrypted}
          subtitle="Documents with encryption enabled"
        />
        <AnalyticsCard
          title="Integrity Verified"
          value={integrity}
          subtitle="Hash-verified documents"
        />
        <AnalyticsCard
          title="Retention Compliant"
          value={retention}
          subtitle="Documents meeting retention policy"
        />
      </div>

      {issues.length > 0 && (
        <div className="sd-security__issues">
          <h3 className="sd-security__issues-title">Open Issues</h3>
          <ul className="sd-security__issues-list">
            {issues.map((issue, idx) => {
              const sev = getSeverityStyle(issue.severity);
              return (
                <li
                  key={issue.id || idx}
                  className="sd-security__issue-item"
                  style={{ borderLeftColor: sev.border }}
                >
                  <span
                    className="sd-security__badge"
                    style={{ background: sev.bg, color: sev.color }}
                  >
                    {sev.label}
                  </span>
                  <span className="sd-security__issue-text">
                    {issue.message || issue.description || issue.title || String(issue)}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Suspicious Activity Tab
// ---------------------------------------------------------------------------
function SuspiciousActivityTab({ items }) {
  if (!items || items.length === 0) {
    return (
      <div className="sd-security__empty sd-security__empty--success">
        No suspicious activity detected.
      </div>
    );
  }

  return (
    <div className="sd-security__alerts">
      {items.map((item, idx) => {
        const sev = getSeverityStyle(item.severity);
        return (
          <div
            key={item.id || idx}
            className="sd-security__alert"
            style={{ borderLeftColor: sev.border, background: sev.bg }}
          >
            <div className="sd-security__alert-header">
              <span className="sd-security__alert-type">{item.type || item.alert_type || 'Alert'}</span>
              <span
                className="sd-security__badge"
                style={{ background: sev.border + '20', color: sev.color }}
              >
                {sev.label}
              </span>
            </div>
            <p className="sd-security__alert-desc">
              {item.description || item.message || '—'}
            </p>
            <div className="sd-security__alert-meta">
              {item.user_name || item.user_email ? (
                <span>User: {item.user_name || item.user_email}</span>
              ) : null}
              <span>{formatTimestamp(item.timestamp || item.created_at)}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Retention Policies Tab
// ---------------------------------------------------------------------------
function RetentionPoliciesTab({ policies }) {
  if (!policies || policies.length === 0) {
    return (
      <div className="sd-security__empty">No retention policies configured.</div>
    );
  }

  return (
    <div className="sd-security__table-container">
      <table className="sd-security__table">
        <thead>
          <tr>
            <th>Policy Name</th>
            <th>Document Type</th>
            <th>Retention Days</th>
            <th>Action</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {policies.map((policy, idx) => {
            const isActive = policy.is_active !== false && policy.status !== 'inactive';
            return (
              <tr key={policy.id || idx}>
                <td>{policy.policy_name || policy.name || '—'}</td>
                <td>{policy.doc_type || policy.document_type || '—'}</td>
                <td>{policy.retention_days != null ? policy.retention_days : '—'}</td>
                <td>{policy.action || policy.retention_action || '—'}</td>
                <td>
                  <span
                    className="sd-security__badge"
                    style={
                      isActive
                        ? { background: '#dcfce7', color: '#15803d' }
                        : { background: '#f1f5f9', color: '#64748b' }
                    }
                  >
                    {isActive ? 'Active' : 'Inactive'}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Page Component
// ---------------------------------------------------------------------------
export default function SmartDocsSecurity() {
  const [activeTab, setActiveTab] = useState('audit');
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(false);

  const [auditLog, setAuditLog] = useState([]);
  const [compliance, setCompliance] = useState(null);
  const [suspicious, setSuspicious] = useState([]);
  const [retentionPolicies, setRetentionPolicies] = useState([]);

  const loadData = useCallback(async (selectedDays) => {
    setLoading(true);
    try {
      const [auditRes, complianceRes, suspiciousRes, retentionRes] = await Promise.allSettled([
        getAuditLog({ days: selectedDays }),
        getComplianceReport(selectedDays),
        getSuspiciousActivity(selectedDays),
        getRetentionPolicies(),
      ]);

      if (auditRes.status === 'fulfilled') {
        const data = auditRes.value;
        setAuditLog(Array.isArray(data) ? data : data.entries || data.logs || data.audit_log || []);
      } else {
        toast.error('Failed to load audit log');
      }

      if (complianceRes.status === 'fulfilled') {
        setCompliance(complianceRes.value);
      } else {
        toast.error('Failed to load compliance report');
      }

      if (suspiciousRes.status === 'fulfilled') {
        const data = suspiciousRes.value;
        setSuspicious(Array.isArray(data) ? data : data.items || data.alerts || data.activity || []);
      } else {
        toast.error('Failed to load suspicious activity');
      }

      if (retentionRes.status === 'fulfilled') {
        const data = retentionRes.value;
        setRetentionPolicies(Array.isArray(data) ? data : data.policies || []);
      } else {
        toast.error('Failed to load retention policies');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData(days);
  }, [days, loadData]);

  function handlePeriodChange(e) {
    setDays(Number(e.target.value));
  }

  return (
    <div className="sd-security">
      <div className="sd-security__header">
        <div>
          <h1 className="sd-security__title">Security &amp; Compliance</h1>
          <p className="sd-security__subtitle">
            Audit trails, compliance monitoring, suspicious activity, and retention policies
          </p>
        </div>
        <div className="sd-security__period-selector">
          <label htmlFor="sd-period" className="sd-security__period-label">Period</label>
          <select
            id="sd-period"
            className="sd-security__period-select"
            value={days}
            onChange={handlePeriodChange}
          >
            {PERIOD_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="sd-security__tabs">
        {TABS.map(tab => (
          <button
            key={tab.key}
            className={`sd-security__tab${activeTab === tab.key ? ' active' : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="sd-security__content">
        {loading ? (
          <div className="sd-security__loading">Loading security data...</div>
        ) : (
          <>
            {activeTab === 'audit' && <AuditLogTab entries={auditLog} />}
            {activeTab === 'compliance' && <ComplianceReportTab report={compliance} />}
            {activeTab === 'suspicious' && <SuspiciousActivityTab items={suspicious} />}
            {activeTab === 'retention' && <RetentionPoliciesTab policies={retentionPolicies} />}
          </>
        )}
      </div>
    </div>
  );
}
