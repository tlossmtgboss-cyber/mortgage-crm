import React, { useState, useEffect, useCallback } from 'react';
import { API_BASE_URL } from '../services/api';
import { toast } from '../utils/toast';
import './AccountManagement.css';

// Utility functions
const formatCurrency = (amount) => {
  if (!amount) return '$0';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(amount);
};

const formatPercent = (value, decimals = 1) => {
  if (value === null || value === undefined) return '0%';
  return `${Number(value).toFixed(decimals)}%`;
};

const formatDate = (dateString) => {
  if (!dateString) return '-';
  return new Date(dateString).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  });
};

const formatDateTime = (dateString) => {
  if (!dateString) return '-';
  return new Date(dateString).toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true
  });
};

const formatRelativeTime = (dateString) => {
  if (!dateString) return 'Never';
  const diffMs = Date.now() - new Date(dateString).getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);
  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  if (diffDays < 30) return `${Math.floor(diffDays/7)}w ago`;
  return `${Math.floor(diffDays/30)}mo ago`;
};

const formatDuration = (seconds) => {
  if (!seconds) return '-';
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  return hours > 0 ? `${hours}h ${mins}m` : `${mins}m`;
};

// API helper
const getAuthHeaders = () => ({
  'Content-Type': 'application/json',
  'Authorization': `Bearer ${localStorage.getItem('token')}`
});

// Status Badge Component
const StatusBadge = ({ status }) => {
  const statusClass = {
    active: 'status-active',
    suspended: 'status-suspended',
    canceled: 'status-canceled',
    invited: 'status-invited',
    disabled: 'status-disabled',
    success: 'status-success',
    failed: 'status-failed',
    paid: 'status-success',
    pending: 'status-pending',
    open: 'status-pending'
  }[status] || 'status-default';

  return (
    <span className={`status-badge ${statusClass}`}>
      {status?.replace('_', ' ')}
    </span>
  );
};

// Health Indicator Component
const HealthIndicator = ({ value, thresholds = { high: 80, low: 50 } }) => {
  const health = value >= thresholds.high ? 'healthy' : value >= thresholds.low ? 'warning' : 'critical';
  return <span className={`health-dot health-${health}`} title={`${value}%`} />;
};

// KPI Card Component
const KPICard = ({ label, value, subValue, trend, variant = 'default' }) => {
  const trendClass = trend !== undefined ? (trend >= 0 ? 'trend-up' : 'trend-down') : '';

  return (
    <div className={`kpi-card kpi-${variant}`}>
      <p className="kpi-label">{label}</p>
      <p className="kpi-value">{value}</p>
      {subValue && <p className="kpi-subvalue">{subValue}</p>}
      {trend !== undefined && (
        <div className={`kpi-trend ${trendClass}`}>
          <span className="trend-arrow">{trend >= 0 ? '↑' : '↓'}</span>
          <span>{Math.abs(trend).toFixed(1)}% vs last month</span>
        </div>
      )}
    </div>
  );
};

// KPI Dashboard Component
const KPIDashboard = ({ kpis, loading }) => {
  if (loading || !kpis) {
    return (
      <div className="kpi-dashboard loading">
        {[...Array(6)].map((_, i) => (
          <div key={i} className="kpi-card skeleton">
            <div className="skeleton-line short" />
            <div className="skeleton-line medium" />
            <div className="skeleton-line short" />
          </div>
        ))}
      </div>
    );
  }

  const utilization = kpis.totalSeatsPurchased > 0
    ? (kpis.totalSeatsUsed / kpis.totalSeatsPurchased) * 100
    : 0;

  const utilizationVariant = utilization >= 70 ? 'success' : utilization >= 50 ? 'warning' : 'danger';
  const marginVariant = kpis.avgMarginPercent >= 60 ? 'success' : kpis.avgMarginPercent >= 45 ? 'warning' : 'danger';
  const riskVariant = kpis.accountsAtRisk > 10 ? 'danger' : kpis.accountsAtRisk > 5 ? 'warning' : 'success';

  return (
    <div className="kpi-section">
      <div className="kpi-dashboard">
        <KPICard
          label="Active Accounts"
          value={kpis.totalActiveAccounts?.toLocaleString()}
          subValue={`${kpis.totalSuspendedAccounts} suspended`}
          variant="success"
        />
        <KPICard
          label="Total MRR"
          value={formatCurrency(kpis.totalMRR)}
          subValue={`${formatCurrency(kpis.totalARR)} ARR`}
          trend={kpis.mrrGrowth}
        />
        <KPICard
          label="Seat Utilization"
          value={formatPercent(utilization)}
          subValue={`${kpis.totalSeatsUsed?.toLocaleString()} / ${kpis.totalSeatsPurchased?.toLocaleString()}`}
          variant={utilizationVariant}
        />
        <KPICard
          label="Avg Cost/User"
          value={formatCurrency(kpis.avgCostPerUser)}
          subValue="per month"
        />
        <KPICard
          label="Avg Margin"
          value={formatPercent(kpis.avgMarginPercent)}
          subValue="gross margin"
          variant={marginVariant}
        />
        <KPICard
          label="At Risk"
          value={kpis.accountsAtRisk}
          subValue={`${kpis.accountsNoActivity30d} inactive`}
          variant={riskVariant}
        />
      </div>
      <div className="kpi-footer">
        <div className="kpi-metrics">
          <span>Churn Rate: <strong className={kpis.churnRate > 5 ? 'text-danger' : 'text-success'}>{formatPercent(kpis.churnRate)}</strong></span>
          <span>Canceled: <strong>{kpis.totalCanceledAccounts}</strong></span>
        </div>
      </div>
    </div>
  );
};

// Modal Component
const Modal = ({ isOpen, onClose, title, children, size = 'medium' }) => {
  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className={`modal-content modal-${size}`} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{title}</h2>
          <button className="modal-close" onClick={onClose}>&times;</button>
        </div>
        <div className="modal-body">
          {children}
        </div>
      </div>
    </div>
  );
};

// Reason Modal Component
const ReasonModal = ({ isOpen, onClose, onSubmit, title, description, submitLabel, variant = 'primary', loading }) => {
  const [reason, setReason] = useState('');

  const handleSubmit = () => {
    onSubmit(reason);
    setReason('');
  };

  const handleClose = () => {
    setReason('');
    onClose();
  };

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title={title}>
      <p className="modal-description">{description}</p>
      <textarea
        value={reason}
        onChange={e => setReason(e.target.value)}
        placeholder="Enter reason..."
        rows={3}
        className="modal-textarea"
      />
      <div className="modal-actions">
        <button onClick={handleClose} disabled={loading} className="btn-secondary">
          Cancel
        </button>
        <button
          onClick={handleSubmit}
          disabled={loading || !reason.trim()}
          className={`btn-${variant}`}
        >
          {loading ? 'Processing...' : submitLabel}
        </button>
      </div>
    </Modal>
  );
};

// Impersonation Modal Component
const ImpersonationModal = ({ isOpen, onClose, onSubmit, userName, loading }) => {
  const [reason, setReason] = useState('');
  const [acknowledged, setAcknowledged] = useState(false);

  const handleSubmit = () => {
    onSubmit(reason, acknowledged);
    setReason('');
    setAcknowledged(false);
  };

  const handleClose = () => {
    setReason('');
    setAcknowledged(false);
    onClose();
  };

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Impersonate User">
      <div className="impersonation-warning">
        <span className="warning-icon">!</span>
        <p>You are about to impersonate <strong>{userName}</strong>. This action is fully audited.</p>
      </div>
      <textarea
        value={reason}
        onChange={e => setReason(e.target.value)}
        placeholder="Reason for impersonation (required)..."
        rows={3}
        className="modal-textarea"
      />
      <label className="checkbox-label">
        <input
          type="checkbox"
          checked={acknowledged}
          onChange={e => setAcknowledged(e.target.checked)}
        />
        I understand that all actions will be logged and attributed to my admin account
      </label>
      <div className="modal-actions">
        <button onClick={handleClose} disabled={loading} className="btn-secondary">
          Cancel
        </button>
        <button
          onClick={handleSubmit}
          disabled={loading || !reason.trim() || !acknowledged}
          className="btn-warning"
        >
          {loading ? 'Starting...' : 'Start Impersonation'}
        </button>
      </div>
    </Modal>
  );
};

// Account Row Component
const AccountRow = ({ account, onClick, onAction }) => {
  const [menuOpen, setMenuOpen] = useState(false);

  const marginClass = account.grossMarginPercent >= 60 ? 'text-success'
    : account.grossMarginPercent >= 40 ? 'text-warning'
    : 'text-danger';

  const utilizationClass = account.seatUtilizationPercent >= 80 ? 'text-success'
    : account.seatUtilizationPercent >= 50 ? 'text-warning'
    : 'text-danger';

  const actions = [
    { id: 'view', label: 'View Account' },
    account.status === 'active' && { id: 'suspend', label: 'Suspend Account' },
    account.status === 'suspended' && { id: 'reinstate', label: 'Reinstate Account' },
    (account.status === 'active' || account.status === 'suspended') && { id: 'cancel', label: 'Cancel Account', danger: true },
    { id: 'addNote', label: 'Add Internal Note' },
  ].filter(Boolean);

  return (
    <tr onClick={() => onClick(account)} className="account-row">
      <td>
        <div className="account-cell">
          <HealthIndicator value={account.grossMarginPercent} thresholds={{ high: 60, low: 40 }} />
          <div>
            <p className="account-name">{account.name}</p>
            <p className="account-id">{account.id}</p>
          </div>
        </div>
      </td>
      <td>
        <p className="plan-name">{account.planName}</p>
        <p className="billing-interval">{account.billingInterval}</p>
      </td>
      <td><StatusBadge status={account.status} /></td>
      <td>
        <span className="seats-used">{account.seatsUsed} / {account.seatsPurchased}</span>
        <span className={`seats-pct ${utilizationClass}`}>({account.seatUtilizationPercent}%)</span>
      </td>
      <td className="text-right">{formatCurrency(account.mrr)}</td>
      <td className="text-right">{formatCurrency(account.trueCostPerUser)}</td>
      <td className={`text-right ${marginClass}`}>{formatPercent(account.grossMarginPercent)}</td>
      <td>{formatRelativeTime(account.lastActivityAt)}</td>
      <td>
        {account.renewalDate ? formatDate(account.renewalDate)
          : account.canceledAt ? `Canceled ${formatDate(account.canceledAt)}`
          : '-'}
      </td>
      <td>
        <p className="owner-name">{account.ownerName}</p>
        <p className="owner-email">{account.ownerEmail}</p>
      </td>
      <td onClick={e => e.stopPropagation()}>
        <div className="action-menu">
          <button className="action-btn" onClick={() => setMenuOpen(!menuOpen)}>
            &#8942;
          </button>
          {menuOpen && (
            <>
              <div className="menu-backdrop" onClick={() => setMenuOpen(false)} />
              <div className="menu-dropdown">
                {actions.map(action => (
                  <button
                    key={action.id}
                    onClick={() => { onAction(action.id, account); setMenuOpen(false); }}
                    className={action.danger ? 'danger' : ''}
                  >
                    {action.label}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </td>
    </tr>
  );
};

// Account List Component
const AccountList = ({ accounts, loading, onAccountClick, onAccountAction, filters, onFiltersChange }) => {
  if (loading) {
    return (
      <div className="account-list loading">
        {[...Array(8)].map((_, i) => (
          <div key={i} className="account-skeleton">
            <div className="skeleton-line long" />
            <div className="skeleton-line medium" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="account-list-section">
      <div className="filter-bar">
        <div className="search-input">
          <span className="search-icon">&#128269;</span>
          <input
            type="text"
            placeholder="Search by name, email, or ID..."
            value={filters.search || ''}
            onChange={e => onFiltersChange({ ...filters, search: e.target.value })}
          />
        </div>
        <select
          value={filters.planId || ''}
          onChange={e => onFiltersChange({ ...filters, planId: e.target.value || undefined })}
        >
          <option value="">All Plans</option>
          <option value="starter">Starter</option>
          <option value="professional">Professional</option>
          <option value="business">Business</option>
          <option value="enterprise">Enterprise</option>
        </select>
        <label className="checkbox-filter">
          <input
            type="checkbox"
            checked={filters.churnRisk || false}
            onChange={e => onFiltersChange({ ...filters, churnRisk: e.target.checked })}
          />
          At Risk Only
        </label>
      </div>

      {accounts.length === 0 ? (
        <div className="empty-state">
          <h3>No accounts found</h3>
          <p>Try adjusting your search or filter criteria</p>
        </div>
      ) : (
        <div className="table-container">
          <table className="accounts-table">
            <thead>
              <tr>
                <th>Account</th>
                <th>Plan</th>
                <th>Status</th>
                <th>Seats</th>
                <th className="text-right">MRR</th>
                <th className="text-right">Cost/User</th>
                <th className="text-right">Margin</th>
                <th>Last Activity</th>
                <th>Renewal</th>
                <th>Owner</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {accounts.map(account => (
                <AccountRow
                  key={account.id}
                  account={account}
                  onClick={onAccountClick}
                  onAction={onAccountAction}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

// User Row Component
const UserRow = ({ user, onClick }) => {
  const initials = user.name?.split(' ').map(n => n[0]).join('').toUpperCase() || '??';

  return (
    <tr onClick={() => onClick(user)} className="user-row">
      <td>
        <div className="user-cell">
          <div className="user-avatar">{initials}</div>
          <div>
            <p className="user-name">{user.name || 'No name'}</p>
            <p className="user-email">{user.email}</p>
          </div>
        </div>
      </td>
      <td>
        <div className="role-tags">
          {user.roles?.map(role => (
            <span key={role} className="role-tag">{role}</span>
          ))}
        </div>
      </td>
      <td><StatusBadge status={user.status} /></td>
      <td>{formatRelativeTime(user.lastLoginAt)}</td>
      <td>{formatDate(user.createdAt)}</td>
      <td className="text-right">
        <div className="activity-summary">
          <span className="activity-main">{user.tasksCompleted30d} tasks</span>
          <span className="activity-sub">{user.callsPlaced30d} calls &bull; {user.emailsSent30d} emails</span>
        </div>
      </td>
    </tr>
  );
};

// Cost Breakdown Component
const CostBreakdown = ({ account, costBreakdown, costTrend }) => {
  if (!costBreakdown) {
    return <div className="empty-state"><p>No cost data available</p></div>;
  }

  const totalCost = costBreakdown.totalCost || 0;
  const categories = costBreakdown.categories || [];

  return (
    <div className="cost-section">
      <div className="cost-summary">
        <div className="cost-card">
          <p className="cost-label">Total Revenue</p>
          <p className="cost-value">{formatCurrency(account.mrr)}</p>
          <p className="cost-sub">/month</p>
        </div>
        <div className="cost-card">
          <p className="cost-label">Total Direct Cost</p>
          <p className="cost-value">{formatCurrency(totalCost)}</p>
          <p className="cost-sub">/month</p>
        </div>
        <div className="cost-card success">
          <p className="cost-label">Gross Margin</p>
          <p className="cost-value">{formatCurrency(account.grossMargin)}</p>
          <p className={`cost-sub ${account.grossMarginPercent >= 60 ? 'text-success' : account.grossMarginPercent >= 40 ? 'text-warning' : 'text-danger'}`}>
            {formatPercent(account.grossMarginPercent)} margin
          </p>
        </div>
        <div className="cost-card">
          <p className="cost-label">True Cost / User</p>
          <p className="cost-value">{formatCurrency(account.trueCostPerUser)}</p>
          <p className="cost-sub">/active user/month</p>
        </div>
      </div>

      <div className="cost-breakdown-panel">
        <h3>Cost Breakdown - {costBreakdown.month}</h3>
        <div className="cost-bars">
          {categories.map(item => (
            <div key={item.category} className="cost-bar-row">
              <div className="cost-bar-label">{item.category.replace('_', ' ')}</div>
              <div className="cost-bar-track">
                <div
                  className="cost-bar-fill"
                  style={{ width: `${Math.min(item.percentage, 100)}%` }}
                />
              </div>
              <div className="cost-bar-amount">{formatCurrency(item.amount)}</div>
              <div className="cost-bar-pct">{formatPercent(item.percentage, 0)}</div>
            </div>
          ))}
        </div>
      </div>

      {costTrend && costTrend.trend && costTrend.trend.length > 0 && (
        <div className="cost-trend-panel">
          <h3>6-Month Trend</h3>
          <table className="trend-table">
            <thead>
              <tr>
                <th>Month</th>
                <th className="text-right">Total Cost</th>
                <th className="text-right">Cost/User</th>
                <th className="text-right">Margin</th>
              </tr>
            </thead>
            <tbody>
              {costTrend.trend.map(row => (
                <tr key={row.month}>
                  <td>{row.month}</td>
                  <td className="text-right">{formatCurrency(row.totalCost)}</td>
                  <td className="text-right">{formatCurrency(row.costPerUser)}</td>
                  <td className={`text-right ${row.margin >= 60 ? 'text-success' : row.margin >= 40 ? 'text-warning' : 'text-danger'}`}>
                    {formatPercent(row.margin)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

// Account Detail Header Component
const AccountDetailHeader = ({ account, onBack, onAction }) => {
  return (
    <div className="account-detail-header">
      <div className="header-top">
        <div className="header-left">
          <button className="back-btn" onClick={onBack}>&larr;</button>
          <div>
            <div className="header-title">
              <h1>{account.name}</h1>
              <StatusBadge status={account.status} />
            </div>
            <p className="header-id">{account.id}</p>
          </div>
        </div>
        <div className="header-actions">
          {account.status === 'active' && (
            <button className="btn-warning-outline" onClick={() => onAction('suspend')}>
              Suspend
            </button>
          )}
          {account.status === 'suspended' && (
            <button className="btn-success-outline" onClick={() => onAction('reinstate')}>
              Reinstate
            </button>
          )}
        </div>
      </div>
      <div className="header-details">
        <div className="detail-item">
          <p className="detail-label">Plan</p>
          <p className="detail-value">{account.planName} ({account.billingInterval})</p>
        </div>
        <div className="detail-item">
          <p className="detail-label">Seats</p>
          <p className="detail-value">{account.seatsUsed} / {account.seatsPurchased}</p>
          <p className={`detail-sub ${account.seatUtilizationPercent >= 80 ? 'text-success' : account.seatUtilizationPercent >= 50 ? 'text-warning' : 'text-danger'}`}>
            {account.seatUtilizationPercent}% utilized
          </p>
        </div>
        <div className="detail-item">
          <p className="detail-label">MRR / ARR</p>
          <p className="detail-value">{formatCurrency(account.mrr)}</p>
          <p className="detail-sub">{formatCurrency(account.arr)} ARR</p>
        </div>
        <div className="detail-item">
          <p className="detail-label">Primary Admin</p>
          <p className="detail-value">{account.ownerName}</p>
          <p className="detail-sub">{account.ownerEmail}</p>
        </div>
        <div className="detail-item">
          <p className="detail-label">Created</p>
          <p className="detail-value">{formatDate(account.createdAt)}</p>
          <p className="detail-sub">{formatRelativeTime(account.createdAt)}</p>
        </div>
        <div className="detail-item">
          <p className="detail-label">{account.status === 'canceled' ? 'Canceled' : 'Renewal'}</p>
          <p className="detail-value">
            {account.canceledAt ? formatDate(account.canceledAt)
              : account.renewalDate ? formatDate(account.renewalDate)
              : '-'}
          </p>
        </div>
      </div>
      {account.internalNotes && (
        <div className="internal-notes">
          <p className="notes-label">Internal Notes</p>
          <p className="notes-content">{account.internalNotes}</p>
        </div>
      )}
    </div>
  );
};

// Account Detail Page Component
const AccountDetailPage = ({
  account, users, invoices, subscriptionTimeline, costBreakdown, costTrend, auditLog,
  onBack, onUserClick, onAccountAction
}) => {
  const [activeTab, setActiveTab] = useState('users');

  const tabs = [
    { id: 'users', label: 'Users', count: users?.length },
    { id: 'billing', label: 'Subscription & Billing' },
    { id: 'costs', label: 'Cost & Profitability' },
    { id: 'activity', label: 'Activity & Audit' },
  ];

  return (
    <div className="account-detail-page">
      <AccountDetailHeader account={account} onBack={onBack} onAction={onAccountAction} />

      <div className="tab-nav">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`tab-btn ${activeTab === tab.id ? 'active' : ''}`}
          >
            {tab.label}
            {tab.count !== undefined && <span className="tab-count">{tab.count}</span>}
          </button>
        ))}
      </div>

      <div className="tab-content">
        {activeTab === 'users' && (
          <div className="users-tab">
            {users && users.length > 0 ? (
              <div className="table-container">
                <table className="users-table">
                  <thead>
                    <tr>
                      <th>User</th>
                      <th>Roles</th>
                      <th>Status</th>
                      <th>Last Login</th>
                      <th>Created</th>
                      <th className="text-right">Activity (30d)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map(user => (
                      <UserRow key={user.id} user={user} onClick={onUserClick} />
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="empty-state">
                <p>No users in this account</p>
              </div>
            )}
          </div>
        )}

        {activeTab === 'billing' && (
          <div className="billing-tab">
            <div className="panel">
              <h3>Invoice History</h3>
              {invoices && invoices.length > 0 ? (
                <div className="table-container">
                  <table className="invoices-table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Description</th>
                        <th>Status</th>
                        <th className="text-right">Amount</th>
                      </tr>
                    </thead>
                    <tbody>
                      {invoices.map(inv => (
                        <tr key={inv.id}>
                          <td>{formatDate(inv.createdAt)}</td>
                          <td>{inv.description}</td>
                          <td><StatusBadge status={inv.status} /></td>
                          <td className="text-right">{formatCurrency(inv.amount)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="empty-text">No invoices found</p>
              )}
            </div>

            {subscriptionTimeline && subscriptionTimeline.length > 0 && (
              <div className="panel">
                <h3>Subscription Timeline</h3>
                <div className="timeline">
                  {subscriptionTimeline.map(event => (
                    <div key={event.id} className="timeline-item">
                      <div className="timeline-dot" />
                      <div className="timeline-content">
                        <p className="timeline-event">{event.eventType}</p>
                        {event.toPlan && <p className="timeline-detail">{event.fromPlan ? `${event.fromPlan} → ${event.toPlan}` : event.toPlan}</p>}
                        <p className="timeline-meta">{formatDateTime(event.timestamp)} by {event.actorName}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'costs' && (
          <CostBreakdown account={account} costBreakdown={costBreakdown} costTrend={costTrend} />
        )}

        {activeTab === 'activity' && (
          <div className="activity-tab">
            <div className="activity-summary-cards">
              <div className="summary-card">
                <p className="summary-label">Active Users (30d)</p>
                <p className="summary-value">{account.activeUsersLast30Days}</p>
              </div>
              <div className="summary-card">
                <p className="summary-label">Last Activity</p>
                <p className="summary-value">{formatRelativeTime(account.lastActivityAt)}</p>
              </div>
              <div className="summary-card">
                <p className="summary-label">Churn Risk</p>
                <p className={`summary-value ${(account.churnRiskScore || 0) <= 30 ? 'text-success' : (account.churnRiskScore || 0) <= 60 ? 'text-warning' : 'text-danger'}`}>
                  {account.churnRiskScore || 0}%
                </p>
              </div>
              <div className="summary-card">
                <p className="summary-label">Seat Utilization</p>
                <p className={`summary-value ${account.seatUtilizationPercent >= 80 ? 'text-success' : account.seatUtilizationPercent >= 50 ? 'text-warning' : 'text-danger'}`}>
                  {account.seatUtilizationPercent}%
                </p>
              </div>
            </div>

            <div className="panel">
              <h3>Audit Log</h3>
              {auditLog && auditLog.length > 0 ? (
                <div className="table-container audit-table-container">
                  <table className="audit-table">
                    <thead>
                      <tr>
                        <th>Timestamp</th>
                        <th>Action</th>
                        <th>Actor</th>
                        <th>IP Address</th>
                      </tr>
                    </thead>
                    <tbody>
                      {auditLog.map(entry => (
                        <tr key={entry.id}>
                          <td>{formatDateTime(entry.timestamp)}</td>
                          <td>{entry.actionType.replace('.', ' > ')}</td>
                          <td>{entry.actorName}</td>
                          <td className="ip-address">{entry.ipAddress}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="empty-text">No audit entries found</p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

// User Detail Page Component
const UserDetailPage = ({ user, loginHistory, onBack, onAction }) => {
  const [activeTab, setActiveTab] = useState('overview');
  const [historyFilter, setHistoryFilter] = useState('all');

  const initials = user?.name?.split(' ').map(n => n[0]).join('').toUpperCase() || '??';
  const filteredHistory = loginHistory?.filter(e => historyFilter === 'all' || e.result === historyFilter) || [];

  const statItems = [
    { label: 'Tasks', value: user?.tasksCompleted30d || 0, icon: '✓', color: 'emerald' },
    { label: 'Calls Placed', value: user?.callsPlaced30d || 0, icon: '📞', color: 'blue' },
    { label: 'Calls Received', value: user?.callsReceived30d || 0, icon: '📲', color: 'cyan' },
    { label: 'Texts Sent', value: user?.textsSent30d || 0, icon: '💬', color: 'purple' },
    { label: 'Emails Sent', value: user?.emailsSent30d || 0, icon: '📧', color: 'amber' },
    { label: 'Notes Created', value: user?.notesCreated30d || 0, icon: '📝', color: 'pink' },
    { label: 'Leads Created', value: user?.leadsCreated30d || 0, icon: '👤', color: 'indigo' },
    { label: 'Loans Created', value: user?.loansCreated30d || 0, icon: '🏠', color: 'teal' },
    { label: 'Docs Uploaded', value: user?.documentsUploaded30d || 0, icon: '📄', color: 'orange' },
    { label: 'AI Actions', value: user?.aiActionsTriggered30d || 0, icon: '🤖', color: 'violet' },
  ];

  if (!user) return null;

  return (
    <div className="user-detail-page">
      <div className="user-detail-header">
        <div className="header-top">
          <div className="header-left">
            <button className="back-btn" onClick={onBack}>&larr;</button>
            <div className="user-avatar large">{initials}</div>
            <div>
              <div className="header-title">
                <h1>{user.name || 'No name'}</h1>
                <StatusBadge status={user.status} />
              </div>
              <p className="header-email">{user.email}</p>
              <p className="header-id">{user.accountName} &bull; ID: {user.id}</p>
            </div>
          </div>
          <div className="header-actions">
            {user.status === 'active' && (
              <button className="btn-danger-outline" onClick={() => onAction('disable')}>
                Disable User
              </button>
            )}
            <button className="btn-warning-outline" onClick={() => onAction('impersonate')}>
              Impersonate
            </button>
          </div>
        </div>
        <div className="header-details">
          <div className="detail-item">
            <p className="detail-label">Roles</p>
            <div className="role-tags">
              {user.roles?.map(r => <span key={r} className="role-tag">{r}</span>)}
            </div>
          </div>
          <div className="detail-item">
            <p className="detail-label">Last Login</p>
            <p className="detail-value">{formatRelativeTime(user.lastLoginAt)}</p>
          </div>
          <div className="detail-item">
            <p className="detail-label">Created</p>
            <p className="detail-value">{formatDate(user.createdAt)}</p>
          </div>
          <div className="detail-item">
            <p className="detail-label">MFA Status</p>
            <p className={`detail-value ${user.mfaEnabled ? 'text-success' : 'text-warning'}`}>
              {user.mfaEnabled ? 'Enabled' : 'Not Enabled'}
            </p>
          </div>
          <div className="detail-item">
            <p className="detail-label">Sessions</p>
            <p className="detail-value">{user.activeSessions} active</p>
          </div>
        </div>
      </div>

      <div className="tab-nav">
        <button onClick={() => setActiveTab('overview')} className={`tab-btn ${activeTab === 'overview' ? 'active' : ''}`}>
          Overview
        </button>
        <button onClick={() => setActiveTab('login-history')} className={`tab-btn ${activeTab === 'login-history' ? 'active' : ''}`}>
          Login History
        </button>
        <button onClick={() => setActiveTab('stats')} className={`tab-btn ${activeTab === 'stats' ? 'active' : ''}`}>
          Activity Stats
        </button>
      </div>

      <div className="tab-content">
        {activeTab === 'overview' && (
          <div className="overview-tab">
            <div className="quick-actions">
              <button className="action-card" onClick={() => onAction('resetPassword')}>
                <span className="action-icon">🔐</span>
                <span className="action-label">Reset Password</span>
              </button>
              <button className="action-card" onClick={() => onAction('resetMfa')}>
                <span className="action-icon">🔒</span>
                <span className="action-label">Reset MFA</span>
              </button>
              <button className="action-card" onClick={() => onAction('forceLogout')}>
                <span className="action-icon">🚪</span>
                <span className="action-label">Force Logout</span>
              </button>
              <button className="action-card" onClick={() => onAction('changeRoles')}>
                <span className="action-icon">👤</span>
                <span className="action-label">Change Roles</span>
              </button>
            </div>

            <div className="panel">
              <h3>Activity Summary (30 Days)</h3>
              <div className="activity-grid">
                <div className="activity-item">
                  <p className="activity-label">Tasks</p>
                  <p className="activity-value">{user.tasksCompleted30d?.toLocaleString()}</p>
                </div>
                <div className="activity-item">
                  <p className="activity-label">Calls</p>
                  <p className="activity-value">{user.callsReceived30d}/{user.callsPlaced30d}</p>
                </div>
                <div className="activity-item">
                  <p className="activity-label">Texts</p>
                  <p className="activity-value">{user.textsSent30d?.toLocaleString()}</p>
                </div>
                <div className="activity-item">
                  <p className="activity-label">Emails</p>
                  <p className="activity-value">{user.emailsSent30d?.toLocaleString()}</p>
                </div>
                <div className="activity-item">
                  <p className="activity-label">AI Actions</p>
                  <p className="activity-value">{user.aiActionsTriggered30d?.toLocaleString()}</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'login-history' && (
          <div className="login-history-tab">
            <div className="filter-tabs">
              {['all', 'success', 'failed'].map(f => (
                <button
                  key={f}
                  onClick={() => setHistoryFilter(f)}
                  className={`filter-tab ${historyFilter === f ? 'active' : ''}`}
                >
                  {f.charAt(0).toUpperCase() + f.slice(1)}
                </button>
              ))}
              <span className="filter-count">{filteredHistory.length} events</span>
            </div>

            {filteredHistory.length > 0 ? (
              <div className="table-container">
                <table className="login-table">
                  <thead>
                    <tr>
                      <th>Timestamp</th>
                      <th>Result</th>
                      <th>IP Address</th>
                      <th>Device</th>
                      <th>Location</th>
                      <th className="text-right">Duration</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredHistory.slice(0, 20).map(event => (
                      <tr key={event.id}>
                        <td>{formatDateTime(event.timestamp)}</td>
                        <td>
                          <span className={`login-result ${event.result}`}>
                            {event.result === 'success' ? '✓' : '✕'} {event.result}
                          </span>
                          {event.failureReason && (
                            <p className="failure-reason">{event.failureReason}</p>
                          )}
                        </td>
                        <td className="ip-address">{event.ipAddress}</td>
                        <td>{event.device || '-'}</td>
                        <td>{event.location || '-'}</td>
                        <td className="text-right">{formatDuration(event.sessionDuration)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="empty-state">
                <p>No login events found</p>
              </div>
            )}
          </div>
        )}

        {activeTab === 'stats' && (
          <div className="stats-tab">
            <div className="stats-grid">
              {statItems.map(item => (
                <div key={item.label} className="stat-card">
                  <div className="stat-header">
                    <span className="stat-icon">{item.icon}</span>
                    <span className="stat-value">{item.value.toLocaleString()}</span>
                  </div>
                  <p className="stat-label">{item.label}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

// Main Account Management Page Component
const AccountManagement = () => {
  // State
  const [view, setView] = useState({ type: 'list' });
  const [activeTab, setActiveTab] = useState('active');
  const [filters, setFilters] = useState({});
  const [kpis, setKpis] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [selectedAccount, setSelectedAccount] = useState(null);
  const [accountUsers, setAccountUsers] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [subscriptionTimeline, setSubscriptionTimeline] = useState([]);
  const [costBreakdown, setCostBreakdown] = useState(null);
  const [costTrend, setCostTrend] = useState(null);
  const [auditLog, setAuditLog] = useState([]);
  const [selectedUser, setSelectedUser] = useState(null);
  const [loginHistory, setLoginHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState({ type: 'none' });
  const [actionLoading, setActionLoading] = useState(false);

  // Fetch KPIs
  const fetchKpis = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/admin/account-management/kpis`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setKpis(data.data);
      }
    } catch (err) {
      console.error('Error fetching KPIs:', err);
    }
  }, []);

  // Fetch Accounts
  const fetchAccounts = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        status: activeTab,
        page: '1',
        limit: '50'
      });
      if (filters.search) params.append('search', filters.search);

      const response = await fetch(`${API_BASE_URL}/api/v1/admin/account-management/accounts?${params}`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setAccounts(data.data?.accounts || []);
      }
    } catch (err) {
      console.error('Error fetching accounts:', err);
    } finally {
      setLoading(false);
    }
  }, [activeTab, filters.search]);

  // Fetch Account Detail
  const fetchAccountDetail = useCallback(async (accountId) => {
    try {
      const [accountRes, usersRes, invoicesRes, timelineRes, costRes, trendRes, auditRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/v1/admin/account-management/accounts/${accountId}`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE_URL}/api/v1/admin/account-management/accounts/${accountId}/users`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE_URL}/api/v1/admin/account-management/accounts/${accountId}/invoices`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE_URL}/api/v1/admin/account-management/accounts/${accountId}/subscription-timeline`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE_URL}/api/v1/admin/account-management/accounts/${accountId}/cost-breakdown`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE_URL}/api/v1/admin/account-management/accounts/${accountId}/cost-trend`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE_URL}/api/v1/admin/account-management/accounts/${accountId}/audit-log`, { headers: getAuthHeaders() }),
      ]);

      if (accountRes.ok) {
        const data = await accountRes.json();
        setSelectedAccount(data.data);
      }
      if (usersRes.ok) {
        const data = await usersRes.json();
        setAccountUsers(data.data?.users || []);
      }
      if (invoicesRes.ok) {
        const data = await invoicesRes.json();
        setInvoices(data.data?.invoices || []);
      }
      if (timelineRes.ok) {
        const data = await timelineRes.json();
        setSubscriptionTimeline(data.data?.timeline || []);
      }
      if (costRes.ok) {
        const data = await costRes.json();
        setCostBreakdown(data.data);
      }
      if (trendRes.ok) {
        const data = await trendRes.json();
        setCostTrend(data.data);
      }
      if (auditRes.ok) {
        const data = await auditRes.json();
        setAuditLog(data.data?.logs || []);
      }
    } catch (err) {
      console.error('Error fetching account detail:', err);
      toast.error('Failed to load account details');
    }
  }, []);

  // Fetch User Detail
  const fetchUserDetail = useCallback(async (userId) => {
    try {
      const [userRes, historyRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/v1/admin/account-management/users/${userId}`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE_URL}/api/v1/admin/account-management/users/${userId}/login-history`, { headers: getAuthHeaders() }),
      ]);

      if (userRes.ok) {
        const data = await userRes.json();
        setSelectedUser(data.data);
      }
      if (historyRes.ok) {
        const data = await historyRes.json();
        setLoginHistory(data.data?.events || []);
      }
    } catch (err) {
      console.error('Error fetching user detail:', err);
      toast.error('Failed to load user details');
    }
  }, []);

  // Initial load
  useEffect(() => {
    fetchKpis();
  }, [fetchKpis]);

  // Load accounts when tab/filters change
  useEffect(() => {
    fetchAccounts();
  }, [fetchAccounts]);

  // Load account detail when viewing
  useEffect(() => {
    if (view.type === 'account-detail' && view.accountId) {
      fetchAccountDetail(view.accountId);
    }
  }, [view, fetchAccountDetail]);

  // Load user detail when viewing
  useEffect(() => {
    if (view.type === 'user-detail' && view.userId) {
      fetchUserDetail(view.userId);
    }
  }, [view, fetchUserDetail]);

  // Handlers
  const handleAccountClick = (account) => {
    setView({ type: 'account-detail', accountId: account.id });
  };

  const handleUserClick = (user) => {
    setView({ type: 'user-detail', userId: user.id, accountId: view.accountId });
  };

  const handleBack = () => {
    if (view.type === 'user-detail') {
      setView({ type: 'account-detail', accountId: view.accountId });
    } else {
      setView({ type: 'list' });
      setSelectedAccount(null);
      setSelectedUser(null);
    }
  };

  const handleAccountAction = async (action, account) => {
    const target = account || selectedAccount;
    if (!target) return;

    switch (action) {
      case 'view':
        setView({ type: 'account-detail', accountId: target.id });
        break;
      case 'suspend':
        setModal({ type: 'suspend', account: target });
        break;
      case 'reinstate':
        setModal({ type: 'reinstate', account: target });
        break;
      case 'cancel':
        setModal({ type: 'cancel', account: target });
        break;
      case 'addNote':
        setModal({ type: 'note', account: target });
        break;
      default:
        break;
    }
  };

  const handleUserAction = (action) => {
    if (!selectedUser) return;

    switch (action) {
      case 'disable':
        setModal({ type: 'disable-user', user: selectedUser });
        break;
      case 'impersonate':
        setModal({ type: 'impersonate', user: selectedUser });
        break;
      default:
        toast.info(`Action: ${action}`);
    }
  };

  const closeModal = () => setModal({ type: 'none' });

  const handleModalSubmit = async (reason) => {
    setActionLoading(true);
    try {
      const { type } = modal;
      let endpoint = '';
      let method = 'POST';

      if (type === 'suspend') {
        endpoint = `/api/v1/admin/account-management/accounts/${modal.account.id}/suspend`;
      } else if (type === 'reinstate') {
        endpoint = `/api/v1/admin/account-management/accounts/${modal.account.id}/reinstate`;
      } else if (type === 'cancel') {
        endpoint = `/api/v1/admin/account-management/accounts/${modal.account.id}/cancel`;
      } else if (type === 'disable-user') {
        endpoint = `/api/v1/admin/account-management/users/${modal.user.id}/disable`;
      } else if (type === 'note') {
        endpoint = `/api/v1/admin/account-management/accounts/${modal.account.id}/notes`;
        method = 'PUT';
      }

      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method,
        headers: getAuthHeaders(),
        body: JSON.stringify({ reason, notes: reason })
      });

      if (response.ok) {
        toast.success('Action completed successfully');
        closeModal();
        fetchAccounts();
        if (selectedAccount) {
          fetchAccountDetail(selectedAccount.id);
        }
      } else {
        const error = await response.json();
        toast.error(error.message || 'Action failed');
      }
    } catch (err) {
      console.error('Action error:', err);
      toast.error('Failed to complete action');
    } finally {
      setActionLoading(false);
    }
  };

  const handleImpersonationSubmit = async (reason, acknowledged) => {
    if (!acknowledged) return;

    setActionLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/admin/account-management/impersonate/start`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          user_id: modal.user.id,
          reason,
          acknowledgment: acknowledged
        })
      });

      if (response.ok) {
        toast.success(`Impersonation started for ${modal.user.name}`);
        closeModal();
        // In a real app, you would redirect to the app with impersonation banner
      } else {
        const error = await response.json();
        toast.error(error.message || 'Failed to start impersonation');
      }
    } catch (err) {
      console.error('Impersonation error:', err);
      toast.error('Failed to start impersonation');
    } finally {
      setActionLoading(false);
    }
  };

  // Tab counts
  const tabCounts = kpis ? {
    active: kpis.totalActiveAccounts,
    suspended: kpis.totalSuspendedAccounts,
    canceled: kpis.totalCanceledAccounts
  } : {};

  return (
    <div className="account-management-page">
      <div className="page-header">
        <div className="breadcrumb">
          <span>Settings</span>
          <span className="separator">&rsaquo;</span>
          <span>Master Administrator</span>
          <span className="separator">&rsaquo;</span>
          <span className="current">Account Management</span>
        </div>
        <h1>Account Management</h1>
        <p>Manage all business accounts, users, subscriptions, and costs.</p>
      </div>

      {view.type === 'list' && (
        <>
          <KPIDashboard kpis={kpis} loading={!kpis} />

          <div className="status-tabs">
            {['active', 'suspended', 'canceled'].map(status => (
              <button
                key={status}
                onClick={() => setActiveTab(status)}
                className={`status-tab ${activeTab === status ? 'active' : ''}`}
              >
                {status.charAt(0).toUpperCase() + status.slice(1)} Subscriptions
                {tabCounts[status] !== undefined && (
                  <span className="tab-count">{tabCounts[status]}</span>
                )}
              </button>
            ))}
          </div>

          <AccountList
            accounts={accounts}
            loading={loading}
            onAccountClick={handleAccountClick}
            onAccountAction={handleAccountAction}
            filters={filters}
            onFiltersChange={setFilters}
          />
        </>
      )}

      {view.type === 'account-detail' && selectedAccount && (
        <AccountDetailPage
          account={selectedAccount}
          users={accountUsers}
          invoices={invoices}
          subscriptionTimeline={subscriptionTimeline}
          costBreakdown={costBreakdown}
          costTrend={costTrend}
          auditLog={auditLog}
          onBack={handleBack}
          onUserClick={handleUserClick}
          onAccountAction={handleAccountAction}
        />
      )}

      {view.type === 'user-detail' && selectedUser && (
        <UserDetailPage
          user={selectedUser}
          loginHistory={loginHistory}
          onBack={handleBack}
          onAction={handleUserAction}
        />
      )}

      {/* Modals */}
      <ReasonModal
        isOpen={modal.type === 'suspend'}
        onClose={closeModal}
        onSubmit={handleModalSubmit}
        title="Suspend Account"
        description={`Suspending "${modal.account?.name || ''}" will immediately revoke access for all users.`}
        submitLabel="Suspend Account"
        variant="warning"
        loading={actionLoading}
      />

      <ReasonModal
        isOpen={modal.type === 'reinstate'}
        onClose={closeModal}
        onSubmit={handleModalSubmit}
        title="Reinstate Account"
        description={`Reinstating "${modal.account?.name || ''}" will restore access for all users.`}
        submitLabel="Reinstate Account"
        variant="primary"
        loading={actionLoading}
      />

      <ReasonModal
        isOpen={modal.type === 'cancel'}
        onClose={closeModal}
        onSubmit={handleModalSubmit}
        title="Cancel Account"
        description={`Canceling "${modal.account?.name || ''}" is a soft cancel that preserves data but revokes access.`}
        submitLabel="Cancel Account"
        variant="danger"
        loading={actionLoading}
      />

      <ReasonModal
        isOpen={modal.type === 'disable-user'}
        onClose={closeModal}
        onSubmit={handleModalSubmit}
        title="Disable User"
        description={`Disabling "${modal.user?.name || ''}" will prevent them from logging in.`}
        submitLabel="Disable User"
        variant="danger"
        loading={actionLoading}
      />

      <ReasonModal
        isOpen={modal.type === 'note'}
        onClose={closeModal}
        onSubmit={handleModalSubmit}
        title="Add Internal Note"
        description={`Add an internal note for "${modal.account?.name || ''}".`}
        submitLabel="Save Note"
        variant="primary"
        loading={actionLoading}
      />

      <ImpersonationModal
        isOpen={modal.type === 'impersonate'}
        onClose={closeModal}
        onSubmit={handleImpersonationSubmit}
        userName={modal.user?.name || modal.user?.email || ''}
        loading={actionLoading}
      />
    </div>
  );
};

export default AccountManagement;
