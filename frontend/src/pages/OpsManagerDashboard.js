import React, { useState, useEffect, useCallback } from 'react';
import { getAuthHeaders } from '../utils/auth';
import { toast } from '../utils/toast';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell
} from 'recharts';
import './OpsManagerDashboard.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const CATEGORY_COLORS = {
  SLA_BREACH: '#ef4444',
  LOCK_EXPIRING: '#f59e0b',
  DOC_EXPIRING: '#f97316',
  DOC_MISSING: '#8b5cf6',
  COMPLIANCE_OPEN: '#dc2626',
  LEAD_STALE: '#6b7280',
  LEAD_UNASSIGNED: '#3b82f6',
  TEAM_GAP: '#10b981',
  MUM_OVERDUE: '#14b8a6',
  STALLED: '#64748b',
};

const CATEGORY_LABELS = {
  SLA_BREACH: 'SLA Breach',
  LOCK_EXPIRING: 'Lock Expiring',
  DOC_EXPIRING: 'Doc Expiring',
  DOC_MISSING: 'Doc Missing',
  COMPLIANCE_OPEN: 'Compliance',
  LEAD_STALE: 'Stale Leads',
  LEAD_UNASSIGNED: 'Unassigned',
  TEAM_GAP: 'Team Gaps',
  MUM_OVERDUE: 'MUM Overdue',
  STALLED: 'Stalled',
};

function OpsManagerDashboard() {
  const [summary, setSummary] = useState(null);
  const [history, setHistory] = useState(null);
  const [priorityQueue, setPriorityQueue] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sweeping, setSweeping] = useState(false);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    const headers = getAuthHeaders();

    try {
      const [summaryRes, historyRes, queueRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/v1/ops-manager/summary`, { headers })
          .then(r => r.ok ? r.json() : null)
          .catch(() => null),
        fetch(`${API_BASE_URL}/api/v1/ops-manager/history?limit=10`, { headers })
          .then(r => r.ok ? r.json() : null)
          .catch(() => null),
        fetch(`${API_BASE_URL}/api/v1/ops-manager/priority-queue`, { headers })
          .then(r => r.ok ? r.json() : null)
          .catch(() => null),
      ]);

      setSummary(summaryRes?.data || null);
      setHistory(historyRes?.data || null);
      setPriorityQueue(queueRes?.data || null);
    } catch (err) {
      console.error('Failed to fetch ops data:', err);
      setError('Failed to load operations data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const triggerSweep = async (dryRun = false) => {
    setSweeping(true);
    const headers = getAuthHeaders();

    try {
      const res = await fetch(
        `${API_BASE_URL}/api/v1/ops-manager/sweep?dry_run=${dryRun}`,
        { method: 'POST', headers }
      );

      if (res.status === 429) {
        const data = await res.json();
        toast.warning(data.detail || 'Sweep rate limited. Please wait.');
        return;
      }

      if (!res.ok) {
        throw new Error('Sweep failed');
      }

      const data = await res.json();
      const msg = dryRun
        ? `Dry run complete: ${data.data?.impediments_found || 0} impediments found`
        : `Sweep complete: ${data.data?.tasks_created || 0} tasks created`;
      toast.success(msg);
      fetchData();
    } catch (err) {
      console.error('Sweep failed:', err);
      toast.error('Pipeline sweep failed');
    } finally {
      setSweeping(false);
    }
  };

  if (loading) {
    return (
      <div className="ops-manager-dashboard">
        <div className="ops-loading">
          <div className="ops-spinner" />
          <p>Loading operations data...</p>
        </div>
      </div>
    );
  }

  // Build chart data from summary
  const chartData = summary?.by_category
    ? Object.entries(summary.by_category).map(([key, val]) => ({
        name: CATEGORY_LABELS[key] || key,
        count: val.total || val,
        color: CATEGORY_COLORS[key] || '#6b7280',
      })).filter(d => d.count > 0)
    : [];

  const totalImpediments = summary?.total_impediments || 0;
  const criticalCount = summary?.critical_count || 0;
  const lastSweep = history?.sweeps?.[0];
  const lastSweepTime = lastSweep?.completed_at
    ? new Date(lastSweep.completed_at).toLocaleString()
    : 'Never';

  const mustToday = priorityQueue?.must_today || [];
  const shouldToday = priorityQueue?.should_today || [];
  const strategic = priorityQueue?.strategic || [];

  return (
    <div className="ops-manager-dashboard">
      {/* Header */}
      <div className="ops-header">
        <div>
          <h1>Operations Manager</h1>
          <p>Pipeline health monitoring and impediment detection</p>
          <div className="ops-last-sweep">Last sweep: {lastSweepTime}</div>
        </div>
        <div className="ops-header-actions">
          <button
            className="ops-btn ops-btn-secondary"
            onClick={() => triggerSweep(true)}
            disabled={sweeping}
          >
            {sweeping ? 'Running...' : 'Dry Run'}
          </button>
          <button
            className="ops-btn ops-btn-primary"
            onClick={() => triggerSweep(false)}
            disabled={sweeping}
          >
            {sweeping ? 'Sweeping...' : 'Run Sweep'}
          </button>
        </div>
      </div>

      {error && <div className="ops-error">{error}</div>}

      {/* KPI Cards */}
      <div className="ops-kpi-grid">
        <div className={`ops-kpi-card ${totalImpediments > 0 ? 'warning' : 'success'}`}>
          <div className="ops-kpi-value">{totalImpediments}</div>
          <div className="ops-kpi-label">Total Impediments</div>
        </div>
        <div className={`ops-kpi-card ${criticalCount > 0 ? 'danger' : 'success'}`}>
          <div className="ops-kpi-value">{criticalCount}</div>
          <div className="ops-kpi-label">Critical</div>
        </div>
        <div className="ops-kpi-card highlight">
          <div className="ops-kpi-value">{mustToday.length}</div>
          <div className="ops-kpi-label">Must Today</div>
        </div>
        <div className="ops-kpi-card">
          <div className="ops-kpi-value">{lastSweep?.tasks_created || 0}</div>
          <div className="ops-kpi-label">Tasks Created (Last Sweep)</div>
        </div>
      </div>

      {/* Charts */}
      {chartData.length > 0 && (
        <div className="ops-charts-row">
          <div className="ops-chart-card wide">
            <h3>Impediments by Category</h3>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={chartData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis type="number" stroke="#9ca3af" />
                <YAxis
                  dataKey="name"
                  type="category"
                  width={120}
                  stroke="#9ca3af"
                  tick={{ fontSize: 12 }}
                />
                <Tooltip
                  contentStyle={{ borderRadius: '8px', border: '1px solid #e5e7eb' }}
                />
                <Bar dataKey="count" name="Count" radius={[0, 4, 4, 0]}>
                  {chartData.map((entry, index) => (
                    <Cell key={index} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Priority Queue */}
      <div className="ops-priority-section">
        <h2>Daily Priority Queue</h2>
        <div className="ops-priority-buckets">
          <PriorityBucket
            label="Must Today"
            className="must-today"
            items={mustToday}
          />
          <PriorityBucket
            label="Should Today"
            className="should-today"
            items={shouldToday}
          />
          <PriorityBucket
            label="Strategic"
            className="strategic"
            items={strategic}
          />
        </div>
      </div>

      {/* Sweep History */}
      <div className="ops-history-section">
        <h3>Sweep History</h3>
        {history?.sweeps?.length > 0 ? (
          <table className="ops-history-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Status</th>
                <th>Impediments</th>
                <th>Tasks Created</th>
                <th>Duration</th>
              </tr>
            </thead>
            <tbody>
              {history.sweeps.map((sweep, i) => (
                <tr key={i}>
                  <td>{sweep.completed_at ? new Date(sweep.completed_at).toLocaleString() : '-'}</td>
                  <td>
                    <span className={`ops-status-badge ${sweep.status === 'success' ? 'success' : 'error'}`}>
                      {sweep.status || 'unknown'}
                    </span>
                  </td>
                  <td>{sweep.impediments_found ?? '-'}</td>
                  <td>{sweep.tasks_created ?? '-'}</td>
                  <td>{sweep.duration_ms ? `${(sweep.duration_ms / 1000).toFixed(1)}s` : '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="ops-empty">No sweep history yet. Run your first sweep above.</div>
        )}
      </div>
    </div>
  );
}

function PriorityBucket({ label, className, items }) {
  return (
    <div className="ops-bucket">
      <div className={`ops-bucket-header ${className}`}>
        <span>{label}</span>
        <span className="ops-bucket-count">{items.length}</span>
      </div>
      <div className="ops-bucket-items">
        {items.length > 0 ? (
          items.map((item, i) => (
            <div key={i} className="ops-bucket-item">
              <div className="ops-bucket-item-title">{item.title}</div>
              <div className="ops-bucket-item-meta">
                {item.category && <span>{CATEGORY_LABELS[item.category] || item.category}</span>}
                {item.loan_number && <span> &middot; Loan #{item.loan_number}</span>}
                {item.priority_score != null && <span> &middot; Score: {item.priority_score}</span>}
              </div>
            </div>
          ))
        ) : (
          <div className="ops-bucket-empty">No items</div>
        )}
      </div>
    </div>
  );
}

export default OpsManagerDashboard;
