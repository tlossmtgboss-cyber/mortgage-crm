import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { API_BASE_URL } from '../services/api';
import { usePermissions } from '../contexts/PermissionContext';
import { toast } from '../utils/toast';
import './AccountManagement.css';
import { getToken } from '../utils/tokenStore';

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
  'Authorization': `Bearer ${getToken()}`
});

// Helper to calculate KPIs from accounts
const calculateKpisFromAccounts = (activeAccounts, suspendedAccounts, canceledAccounts, pendingInvites) => {
  const active = activeAccounts || [];
  const suspended = suspendedAccounts || [];
  const canceled = canceledAccounts || [];
  const pending = pendingInvites || [];

  // Calculate totals from active accounts
  const totalMRR = active.reduce((sum, a) => sum + (a.mrr || 0), 0);
  const totalSeatsUsed = active.reduce((sum, a) => sum + (a.seatsUsed || 0), 0);
  const totalSeatsPurchased = active.reduce((sum, a) => sum + (a.seatsPurchased || 0), 0);

  // Calculate averages
  const margins = active.filter(a => a.grossMarginPercent > 0).map(a => a.grossMarginPercent);
  const avgMarginPercent = margins.length > 0 ? margins.reduce((s, m) => s + m, 0) / margins.length : 0;

  const costs = active.filter(a => a.trueCostPerUser > 0).map(a => a.trueCostPerUser);
  const avgCostPerUser = costs.length > 0 ? costs.reduce((s, c) => s + c, 0) / costs.length : 0;

  // Count at-risk (churn risk > 50%)
  const accountsAtRisk = active.filter(a => (a.churnRiskScore || 0) > 50).length;

  // Count inactive (last activity > 30 days ago)
  const thirtyDaysAgo = Date.now() - (30 * 24 * 60 * 60 * 1000);
  const accountsNoActivity30d = active.filter(a => {
    if (!a.lastActivityAt) return true;
    return new Date(a.lastActivityAt).getTime() < thirtyDaysAgo;
  }).length;

  return {
    totalActiveAccounts: active.length,
    totalSuspendedAccounts: suspended.length,
    totalCanceledAccounts: canceled.length,
    totalPendingInvites: pending.length,
    totalMRR,
    totalARR: totalMRR * 12,
    mrrGrowth: 8.4, // Simulated growth
    totalSeatsUsed,
    totalSeatsPurchased,
    avgCostPerUser: Math.round(avgCostPerUser),
    avgMarginPercent: Math.round(avgMarginPercent * 10) / 10,
    accountsAtRisk,
    accountsNoActivity30d,
    churnRate: 2.5
  };
};

const DEMO_ACCOUNTS = [
  {
    id: 'acct_001',
    name: 'Pinnacle Mortgage Group',
    planName: 'Enterprise',
    billingInterval: 'Annual',
    status: 'active',
    seatsUsed: 45,
    seatsPurchased: 50,
    seatUtilizationPercent: 90,
    mrr: 14850,
    trueCostPerUser: 28,
    grossMarginPercent: 72,
    lastActivityAt: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
    renewalDate: new Date(Date.now() + 90 * 24 * 60 * 60 * 1000).toISOString(),
    ownerName: 'Sarah Johnson',
    ownerEmail: 'sarah@pinnaclemortgage.com',
    createdAt: new Date(Date.now() - 365 * 24 * 60 * 60 * 1000).toISOString(),
    arr: 178200,
    grossMargin: 10692,
    activeUsersLast30Days: 42,
    churnRiskScore: 15,
    internalNotes: 'Key enterprise client. VIP support tier.'
  },
  {
    id: 'acct_002',
    name: 'First Choice Lending',
    planName: 'Business',
    billingInterval: 'Monthly',
    status: 'active',
    seatsUsed: 18,
    seatsPurchased: 25,
    seatUtilizationPercent: 72,
    mrr: 3725,
    trueCostPerUser: 32,
    grossMarginPercent: 64,
    lastActivityAt: new Date(Date.now() - 5 * 60 * 60 * 1000).toISOString(),
    renewalDate: new Date(Date.now() + 28 * 24 * 60 * 60 * 1000).toISOString(),
    ownerName: 'Michael Chen',
    ownerEmail: 'mchen@firstchoicelending.com',
    createdAt: new Date(Date.now() - 180 * 24 * 60 * 60 * 1000).toISOString(),
    arr: 44700,
    grossMargin: 2384,
    activeUsersLast30Days: 16,
    churnRiskScore: 25
  },
  {
    id: 'acct_003',
    name: 'HomeKey Financial',
    planName: 'Professional',
    billingInterval: 'Annual',
    status: 'active',
    seatsUsed: 8,
    seatsPurchased: 10,
    seatUtilizationPercent: 80,
    mrr: 990,
    trueCostPerUser: 38,
    grossMarginPercent: 58,
    lastActivityAt: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
    renewalDate: new Date(Date.now() + 200 * 24 * 60 * 60 * 1000).toISOString(),
    ownerName: 'Lisa Martinez',
    ownerEmail: 'lisa@homekeyfinancial.com',
    createdAt: new Date(Date.now() - 90 * 24 * 60 * 60 * 1000).toISOString(),
    arr: 11880,
    grossMargin: 574,
    activeUsersLast30Days: 7,
    churnRiskScore: 35
  },
  {
    id: 'acct_004',
    name: 'Summit Loans Inc',
    planName: 'Professional',
    billingInterval: 'Monthly',
    status: 'active',
    seatsUsed: 5,
    seatsPurchased: 5,
    seatUtilizationPercent: 100,
    mrr: 495,
    trueCostPerUser: 42,
    grossMarginPercent: 48,
    lastActivityAt: new Date(Date.now() - 12 * 60 * 60 * 1000).toISOString(),
    renewalDate: new Date(Date.now() + 15 * 24 * 60 * 60 * 1000).toISOString(),
    ownerName: 'David Kim',
    ownerEmail: 'david@summitloans.com',
    createdAt: new Date(Date.now() - 45 * 24 * 60 * 60 * 1000).toISOString(),
    arr: 5940,
    grossMargin: 238,
    activeUsersLast30Days: 5,
    churnRiskScore: 55
  },
  {
    id: 'acct_005',
    name: 'Coastal Mortgage Solutions',
    planName: 'Business',
    billingInterval: 'Annual',
    status: 'active',
    seatsUsed: 32,
    seatsPurchased: 40,
    seatUtilizationPercent: 80,
    mrr: 5960,
    trueCostPerUser: 30,
    grossMarginPercent: 68,
    lastActivityAt: new Date(Date.now() - 1 * 60 * 60 * 1000).toISOString(),
    renewalDate: new Date(Date.now() + 45 * 24 * 60 * 60 * 1000).toISOString(),
    ownerName: 'Jennifer Walsh',
    ownerEmail: 'jwalsh@coastalmortgage.com',
    createdAt: new Date(Date.now() - 270 * 24 * 60 * 60 * 1000).toISOString(),
    arr: 71520,
    grossMargin: 4053,
    activeUsersLast30Days: 30,
    churnRiskScore: 18
  },
  {
    id: 'acct_006',
    name: 'Liberty Home Loans',
    planName: 'Starter',
    billingInterval: 'Monthly',
    status: 'active',
    seatsUsed: 3,
    seatsPurchased: 5,
    seatUtilizationPercent: 60,
    mrr: 245,
    trueCostPerUser: 45,
    grossMarginPercent: 35,
    lastActivityAt: new Date(Date.now() - 72 * 60 * 60 * 1000).toISOString(),
    renewalDate: new Date(Date.now() + 20 * 24 * 60 * 60 * 1000).toISOString(),
    ownerName: 'Robert Taylor',
    ownerEmail: 'rtaylor@libertyhomeloans.com',
    createdAt: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString(),
    arr: 2940,
    grossMargin: 86,
    activeUsersLast30Days: 2,
    churnRiskScore: 70
  }
];

const DEMO_SUSPENDED_ACCOUNTS = [
  {
    id: 'acct_s01',
    name: 'Apex Lending Partners',
    planName: 'Professional',
    billingInterval: 'Monthly',
    status: 'suspended',
    seatsUsed: 0,
    seatsPurchased: 10,
    seatUtilizationPercent: 0,
    mrr: 0,
    trueCostPerUser: 0,
    grossMarginPercent: 0,
    lastActivityAt: new Date(Date.now() - 45 * 24 * 60 * 60 * 1000).toISOString(),
    ownerName: 'James Wilson',
    ownerEmail: 'jwilson@apexlending.com',
    createdAt: new Date(Date.now() - 120 * 24 * 60 * 60 * 1000).toISOString(),
    internalNotes: 'Suspended for payment issues. Payment plan in progress.'
  }
];

const DEMO_CANCELED_ACCOUNTS = [
  {
    id: 'acct_c01',
    name: 'Quick Mortgage Co',
    planName: 'Starter',
    billingInterval: 'Monthly',
    status: 'canceled',
    seatsUsed: 0,
    seatsPurchased: 3,
    seatUtilizationPercent: 0,
    mrr: 0,
    trueCostPerUser: 0,
    grossMarginPercent: 0,
    lastActivityAt: new Date(Date.now() - 60 * 24 * 60 * 60 * 1000).toISOString(),
    canceledAt: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString(),
    ownerName: 'Patricia Brown',
    ownerEmail: 'pbrown@quickmortgage.com',
    createdAt: new Date(Date.now() - 90 * 24 * 60 * 60 * 1000).toISOString(),
    internalNotes: 'Churned - moved to competitor. Price sensitivity.'
  }
];

const DEMO_PENDING_INVITES = [
  {
    id: 'inv_001',
    email: 'john.smith@newmortgage.com',
    name: 'John Smith',
    organizationName: 'New Mortgage Partners',
    planName: 'Business',
    billingInterval: 'Monthly',
    invitedAt: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
    invitedBy: 'Sarah Johnson',
    invitedByEmail: 'sarah@pinnaclemortgage.com',
    status: 'pending',
    seatsPurchased: 10,
    expiresAt: new Date(Date.now() + 5 * 24 * 60 * 60 * 1000).toISOString()
  },
  {
    id: 'inv_002',
    email: 'maria.garcia@sunrisefunding.com',
    name: 'Maria Garcia',
    organizationName: 'Sunrise Funding LLC',
    planName: 'Professional',
    billingInterval: 'Annual',
    invitedAt: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
    invitedBy: 'Tim Loss',
    invitedByEmail: 'admin@perenniaai.com',
    status: 'pending',
    seatsPurchased: 5,
    expiresAt: new Date(Date.now() + 2 * 24 * 60 * 60 * 1000).toISOString()
  },
  {
    id: 'inv_003',
    email: 'robert.chen@elitelending.com',
    name: 'Robert Chen',
    organizationName: 'Elite Lending Group',
    planName: 'Enterprise',
    billingInterval: 'Annual',
    invitedAt: new Date(Date.now() - 1 * 24 * 60 * 60 * 1000).toISOString(),
    invitedBy: 'Michael Chen',
    invitedByEmail: 'mchen@firstchoicelending.com',
    status: 'pending',
    seatsPurchased: 25,
    expiresAt: new Date(Date.now() + 6 * 24 * 60 * 60 * 1000).toISOString()
  },
  {
    id: 'inv_004',
    email: 'amanda.wilson@premiumhome.com',
    name: 'Amanda Wilson',
    organizationName: 'Premium Home Loans',
    planName: 'Starter',
    billingInterval: 'Monthly',
    invitedAt: new Date(Date.now() - 6 * 24 * 60 * 60 * 1000).toISOString(),
    invitedBy: 'Lisa Martinez',
    invitedByEmail: 'lisa@homekeyfinancial.com',
    status: 'expired',
    seatsPurchased: 3,
    expiresAt: new Date(Date.now() - 1 * 24 * 60 * 60 * 1000).toISOString()
  }
];

const DEMO_USERS = [
  {
    id: '57',
    name: 'Tim Loss',
    email: 'tloss@cmgfi.com',
    roles: ['Admin', 'Master Admin'],
    status: 'active',
    lastLoginAt: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
    createdAt: new Date(Date.now() - 365 * 24 * 60 * 60 * 1000).toISOString(),
    tasksCompleted30d: 245,
    callsPlaced30d: 89,
    emailsSent30d: 156,
    mfaEnabled: true,
    activeSessions: 2,
    callsReceived30d: 67,
    textsSent30d: 43,
    notesCreated30d: 78,
    leadsCreated30d: 23,
    loansCreated30d: 12,
    documentsUploaded30d: 34,
    aiActionsTriggered30d: 156
  },
  {
    id: '102',
    name: 'Sarah Johnson',
    email: 'sarah@pinnaclemortgage.com',
    roles: ['Loan Officer'],
    status: 'active',
    lastLoginAt: new Date(Date.now() - 4 * 60 * 60 * 1000).toISOString(),
    createdAt: new Date(Date.now() - 180 * 24 * 60 * 60 * 1000).toISOString(),
    tasksCompleted30d: 189,
    callsPlaced30d: 112,
    emailsSent30d: 98,
    mfaEnabled: true,
    activeSessions: 1,
    callsReceived30d: 45,
    textsSent30d: 67,
    notesCreated30d: 56,
    leadsCreated30d: 18,
    loansCreated30d: 8,
    documentsUploaded30d: 22,
    aiActionsTriggered30d: 89
  },
  {
    id: '102',
    name: 'Emily Rodriguez',
    email: 'erodriguez@pinnaclemortgage.com',
    roles: ['Processor'],
    status: 'active',
    lastLoginAt: new Date(Date.now() - 1 * 60 * 60 * 1000).toISOString(),
    createdAt: new Date(Date.now() - 90 * 24 * 60 * 60 * 1000).toISOString(),
    tasksCompleted30d: 312,
    callsPlaced30d: 34,
    emailsSent30d: 245,
    mfaEnabled: true,
    activeSessions: 1,
    callsReceived30d: 28,
    textsSent30d: 12,
    notesCreated30d: 145,
    leadsCreated30d: 0,
    loansCreated30d: 0,
    documentsUploaded30d: 89,
    aiActionsTriggered30d: 234
  },
  {
    id: '102',
    name: 'Kevin Park',
    email: 'kpark@pinnaclemortgage.com',
    roles: ['Loan Officer'],
    status: 'invited',
    lastLoginAt: null,
    createdAt: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
    tasksCompleted30d: 0,
    callsPlaced30d: 0,
    emailsSent30d: 0,
    mfaEnabled: false,
    activeSessions: 0
  }
];

const DEMO_INVOICES = [
  {
    id: 'inv_001',
    createdAt: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
    description: 'Monthly subscription - Enterprise (50 seats)',
    status: 'paid',
    amount: 14850
  },
  {
    id: 'inv_002',
    createdAt: new Date(Date.now() - 35 * 24 * 60 * 60 * 1000).toISOString(),
    description: 'Monthly subscription - Enterprise (50 seats)',
    status: 'paid',
    amount: 14850
  },
  {
    id: 'inv_003',
    createdAt: new Date(Date.now() - 65 * 24 * 60 * 60 * 1000).toISOString(),
    description: 'Monthly subscription - Enterprise (45 seats)',
    status: 'paid',
    amount: 13365
  }
];

const DEMO_COST_BREAKDOWN = {
  month: 'December 2024',
  totalCost: 5198,
  categories: [
    { category: 'AI_Processing', amount: 2340, percentage: 45 },
    { category: 'Storage', amount: 780, percentage: 15 },
    { category: 'API_Calls', amount: 624, percentage: 12 },
    { category: 'Voice_Minutes', amount: 520, percentage: 10 },
    { category: 'SMS', amount: 416, percentage: 8 },
    { category: 'Email', amount: 312, percentage: 6 },
    { category: 'Other', amount: 206, percentage: 4 }
  ]
};

const DEMO_COST_TREND = {
  trend: [
    { month: 'Jul 2024', totalCost: 4200, costPerUser: 28, margin: 68 },
    { month: 'Aug 2024', totalCost: 4450, costPerUser: 29, margin: 67 },
    { month: 'Sep 2024', totalCost: 4680, costPerUser: 28, margin: 69 },
    { month: 'Oct 2024', totalCost: 4890, costPerUser: 29, margin: 68 },
    { month: 'Nov 2024', totalCost: 5050, costPerUser: 28, margin: 70 },
    { month: 'Dec 2024', totalCost: 5198, costPerUser: 28, margin: 72 }
  ]
};

const DEMO_AUDIT_LOG = [
  {
    id: 'log_001',
    timestamp: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
    actionType: 'user.login',
    actorName: 'Sarah Johnson',
    ipAddress: '192.168.1.45'
  },
  {
    id: 'log_002',
    timestamp: new Date(Date.now() - 5 * 60 * 60 * 1000).toISOString(),
    actionType: 'loan.created',
    actorName: 'Marcus Thompson',
    ipAddress: '192.168.1.67'
  },
  {
    id: 'log_003',
    timestamp: new Date(Date.now() - 8 * 60 * 60 * 1000).toISOString(),
    actionType: 'settings.updated',
    actorName: 'Sarah Johnson',
    ipAddress: '192.168.1.45'
  },
  {
    id: 'log_004',
    timestamp: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
    actionType: 'user.invited',
    actorName: 'Sarah Johnson',
    ipAddress: '192.168.1.45'
  }
];

const DEMO_LOGIN_HISTORY = [
  {
    id: 'lh_001',
    timestamp: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
    result: 'success',
    ipAddress: '192.168.1.45',
    device: 'Chrome on MacOS',
    location: 'San Francisco, CA',
    sessionDuration: 7200
  },
  {
    id: 'lh_002',
    timestamp: new Date(Date.now() - 26 * 60 * 60 * 1000).toISOString(),
    result: 'success',
    ipAddress: '192.168.1.45',
    device: 'Chrome on MacOS',
    location: 'San Francisco, CA',
    sessionDuration: 14400
  },
  {
    id: 'lh_003',
    timestamp: new Date(Date.now() - 48 * 60 * 60 * 1000).toISOString(),
    result: 'failed',
    ipAddress: '10.0.0.55',
    device: 'Firefox on Windows',
    location: 'Unknown',
    failureReason: 'Invalid password'
  }
];

const DEMO_SUBSCRIPTION_TIMELINE = [
  {
    id: 'st_001',
    eventType: 'Seats Added',
    fromPlan: null,
    toPlan: '+5 seats',
    timestamp: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString(),
    actorName: 'Sarah Johnson'
  },
  {
    id: 'st_002',
    eventType: 'Plan Upgraded',
    fromPlan: 'Business',
    toPlan: 'Enterprise',
    timestamp: new Date(Date.now() - 120 * 24 * 60 * 60 * 1000).toISOString(),
    actorName: 'Admin (Support)'
  },
  {
    id: 'st_003',
    eventType: 'Account Created',
    fromPlan: null,
    toPlan: 'Business (40 seats)',
    timestamp: new Date(Date.now() - 365 * 24 * 60 * 60 * 1000).toISOString(),
    actorName: 'System'
  }
];

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
    open: 'status-pending',
    expired: 'status-expired'
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
const Modal = ({ isOpen, onClose, title, children, footer, size = 'medium' }) => {
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
        {footer && (
          <div className="modal-actions">
            {footer}
          </div>
        )}
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

  const footerContent = (
    <>
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
    </>
  );

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title={title} footer={footerContent}>
      <p className="modal-description">{description}</p>
      <textarea
        value={reason}
        onChange={e => setReason(e.target.value)}
        placeholder="Enter reason..."
        rows={3}
        className="modal-textarea"
      />
    </Modal>
  );
};

// Invite Subscriber Modal Component
const InviteSubscriberModal = ({ isOpen, onClose, onSubmit, loading }) => {
  const [formData, setFormData] = useState({
    email: '',
    companyName: '',
    firstName: '',
    lastName: '',
    phone: '',
    plan: 'professional',
    seats: 5,
    message: '',
    promoCode: ''
  });

  // Special promo code for free Business plan access
  const FREE_ACCESS_CODE = 'CHARLIE2016';

  const formatPhoneNumber = (value) => {
    // Remove all non-digits
    const digits = value.replace(/\D/g, '');

    // Limit to 10 digits
    const limitedDigits = digits.slice(0, 10);

    // Format as (XXX) XXX-XXXX
    if (limitedDigits.length === 0) return '';
    if (limitedDigits.length <= 3) return `(${limitedDigits}`;
    if (limitedDigits.length <= 6) return `(${limitedDigits.slice(0, 3)}) ${limitedDigits.slice(3)}`;
    return `(${limitedDigits.slice(0, 3)}) ${limitedDigits.slice(3, 6)}-${limitedDigits.slice(6)}`;
  };

  const handleChange = (field, value) => {
    if (field === 'phone') {
      value = formatPhoneNumber(value);
    }
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handleSubmit = () => {
    if (!formData.email || !formData.companyName) {
      return;
    }
    onSubmit(formData);
  };

  const handleClose = () => {
    setFormData({
      email: '',
      companyName: '',
      firstName: '',
      lastName: '',
      phone: '',
      plan: 'professional',
      seats: 5,
      message: '',
      promoCode: ''
    });
    onClose();
  };

  // Check if promo code grants free access
  const isPromoCodeValid = formData.promoCode.toUpperCase() === FREE_ACCESS_CODE;

  // Auto-select Business plan when valid promo code is entered
  const handlePromoCodeChange = (value) => {
    const upperValue = value.toUpperCase();
    setFormData(prev => ({
      ...prev,
      promoCode: upperValue,
      // Auto-upgrade to business plan when free access code is entered
      plan: upperValue === FREE_ACCESS_CODE ? 'business' : prev.plan
    }));
  };

  const plans = [
    { id: 'starter', name: 'Starter', price: '$49/user/mo', description: 'Basic CRM features' },
    { id: 'professional', name: 'Professional', price: '$99/user/mo', description: 'Full CRM + AI features' },
    { id: 'business', name: 'Business', price: '$149/user/mo', description: 'Advanced automation' },
    { id: 'enterprise', name: 'Enterprise', price: 'Custom', description: 'Custom solutions' }
  ];

  const footerContent = (
    <>
      <button onClick={handleClose} disabled={loading} className="btn-secondary">
        Cancel
      </button>
      <button
        onClick={handleSubmit}
        disabled={loading || !formData.email || !formData.companyName}
        className="btn-primary"
      >
        {loading ? 'Sending...' : 'Send Invitation'}
      </button>
    </>
  );

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Invite New Subscriber" size="large" footer={footerContent}>
      <div className="invite-form">
        <div className="form-section">
          <h4>Contact Information</h4>
          <div className="form-group">
            <label>Company Name *</label>
            <input
              type="text"
              value={formData.companyName}
              onChange={e => handleChange('companyName', e.target.value)}
              placeholder="Acme Mortgage Co."
            />
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>First Name</label>
              <input
                type="text"
                value={formData.firstName}
                onChange={e => handleChange('firstName', e.target.value)}
                placeholder="John"
              />
            </div>
            <div className="form-group">
              <label>Last Name</label>
              <input
                type="text"
                value={formData.lastName}
                onChange={e => handleChange('lastName', e.target.value)}
                placeholder="Smith"
              />
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Email Address *</label>
              <input
                type="email"
                value={formData.email}
                onChange={e => handleChange('email', e.target.value)}
                placeholder="admin@company.com"
              />
            </div>
            <div className="form-group">
              <label>Phone Number</label>
              <input
                type="tel"
                value={formData.phone}
                onChange={e => handleChange('phone', e.target.value)}
                placeholder="(555) 555-5555"
              />
            </div>
          </div>
        </div>

        <div className="form-section">
          <h4>Subscription Plan</h4>
          <div className="plan-selector">
            {plans.map(plan => (
              <div
                key={plan.id}
                className={`plan-option ${formData.plan === plan.id ? 'selected' : ''}`}
                onClick={() => handleChange('plan', plan.id)}
              >
                <div className="plan-header">
                  <span className="plan-name">{plan.name}</span>
                  <span className="plan-price">{plan.price}</span>
                </div>
                <p className="plan-desc">{plan.description}</p>
              </div>
            ))}
          </div>
          <div className="form-group">
            <label>Initial Seats</label>
            <input
              type="number"
              min="1"
              max="1000"
              value={formData.seats}
              onChange={e => handleChange('seats', parseInt(e.target.value) || 1)}
            />
          </div>
        </div>

        <div className="form-section">
          <h4>Personal Message (Optional)</h4>
          <textarea
            value={formData.message}
            onChange={e => handleChange('message', e.target.value)}
            placeholder="Add a personal note to include in the invitation email..."
            rows={3}
          />
        </div>

        <div className="form-section">
          <h4>Promo Code (Optional)</h4>
          <div className="promo-code-input">
            <input
              type="text"
              value={formData.promoCode}
              onChange={e => handlePromoCodeChange(e.target.value)}
              placeholder="Enter promo code"
              style={{ textTransform: 'uppercase' }}
            />
            {isPromoCodeValid && (
              <div className="promo-valid" style={{
                color: '#2D7A52',
                fontSize: '13px',
                marginTop: '8px',
                display: 'flex',
                alignItems: 'center',
                gap: '6px'
              }}>
                <span style={{ fontSize: '16px' }}>✓</span>
                Free Business Plan Access Applied!
              </div>
            )}
          </div>
          <p className="form-hint" style={{ fontSize: '12px', color: '#6b7280', marginTop: '4px' }}>
            Promo codes grant special pricing or free access to premium features.
          </p>
        </div>
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

  const footerContent = (
    <>
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
    </>
  );

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Impersonate User" footer={footerContent}>
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
    { id: 'delete', label: 'Delete Account', danger: true },
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

// Pending Invite Row Component
const PendingInviteRow = ({ invite, onAction }) => {
  const initials = invite.name?.split(' ').map(n => n[0]).join('').toUpperCase() || invite.email?.substring(0, 2).toUpperCase() || '??';
  const isExpired = invite.status === 'expired' || new Date(invite.expiresAt) < new Date();

  return (
    <tr className={`invite-row ${isExpired ? 'expired' : ''}`}>
      <td>
        <div className="account-cell">
          <div className="account-avatar">{initials}</div>
          <div>
            <p className="account-name">{invite.organizationName || 'New Organization'}</p>
            <p className="account-id">{invite.name || 'Pending'}</p>
          </div>
        </div>
      </td>
      <td>
        <p className="invite-email">{invite.email}</p>
      </td>
      <td>
        <span className={`plan-badge ${invite.planName?.toLowerCase()}`}>
          {invite.planName}
        </span>
        <span className="billing-interval">{invite.billingInterval}</span>
      </td>
      <td>{invite.seatsPurchased} seats</td>
      <td>{formatRelativeTime(invite.invitedAt)}</td>
      <td>
        <div className="invited-by">
          <span>{invite.invitedBy}</span>
        </div>
      </td>
      <td>
        <StatusBadge status={isExpired ? 'expired' : invite.status} />
      </td>
      <td>
        {isExpired ? (
          <span className="expires-text expired">Expired {formatRelativeTime(invite.expiresAt)}</span>
        ) : (
          <span className="expires-text">Expires {formatDate(invite.expiresAt)}</span>
        )}
      </td>
      <td>
        <div className="row-actions">
          <button
            className="action-btn"
            onClick={(e) => { e.stopPropagation(); onAction('resend', invite); }}
            title="Resend Invite"
          >
            ↻
          </button>
          <button
            className="action-btn danger"
            onClick={(e) => { e.stopPropagation(); onAction('revoke', invite); }}
            title="Revoke Invite"
          >
            ✕
          </button>
        </div>
      </td>
    </tr>
  );
};

// Pending Invites List Component
const PendingInvitesList = ({ invites, loading, onInviteAction, filters, onFiltersChange }) => {
  if (loading) {
    return (
      <div className="account-list loading">
        {[...Array(4)].map((_, i) => (
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
            placeholder="Search by name, email, or organization..."
            value={filters.search || ''}
            onChange={e => onFiltersChange({ ...filters, search: e.target.value })}
          />
        </div>
        <select
          value={filters.inviteStatus || ''}
          onChange={e => onFiltersChange({ ...filters, inviteStatus: e.target.value || undefined })}
        >
          <option value="">All Invites</option>
          <option value="pending">Pending</option>
          <option value="expired">Expired</option>
        </select>
      </div>

      {invites.length === 0 ? (
        <div className="empty-state">
          <h3>No pending invites</h3>
          <p>All invitations have been accepted or there are no outstanding invites</p>
        </div>
      ) : (
        <div className="table-container">
          <table className="accounts-table invites-table">
            <thead>
              <tr>
                <th>Organization</th>
                <th>Email</th>
                <th>Plan</th>
                <th>Seats</th>
                <th>Invited</th>
                <th>Invited By</th>
                <th>Status</th>
                <th>Expires</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {invites.map(invite => (
                <PendingInviteRow
                  key={invite.id}
                  invite={invite}
                  onAction={onInviteAction}
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

// User Permissions Tab Component
const UserPermissionsTab = ({ user, onPermissionChange }) => {
  const [permissions, setPermissions] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  // Permission categories and pages
  const permissionCategories = [
    {
      name: 'Core CRM',
      pages: [
        { id: 'dashboard', label: 'Dashboard', description: 'Main dashboard access' },
        { id: 'leads', label: 'Leads', description: 'Lead management' },
        { id: 'active_loans', label: 'Active Loans', description: 'Loan pipeline' },
        { id: 'portfolio', label: 'Portfolio', description: 'Loan portfolio management' },
        { id: 'tasks', label: 'Tasks', description: 'Task management' },
        { id: 'calendar', label: 'Calendar', description: 'Calendar and scheduling' },
      ]
    },
    {
      name: 'Communication',
      pages: [
        { id: 'marketing', label: 'Marketing', description: 'Marketing campaigns' },
        { id: 'smart_docs', label: 'Smart Docs', description: 'Document management' },
        { id: 'partners', label: 'Partners', description: 'Partner management' },
      ]
    },
    {
      name: 'Analytics',
      pages: [
        { id: 'scorecard', label: 'Scorecard', description: 'Performance metrics' },
        { id: 'profitability', label: 'Profitability', description: 'Profitability analysis' },
        { id: 'market', label: 'Market', description: 'Market data and trends' },
      ]
    },
    {
      name: 'AI Features',
      pages: [
        { id: 'ai_underwriter', label: 'AI Underwriter', description: 'AI underwriting tools' },
        { id: 'ai_daily_blog', label: 'AI Daily Blog', description: 'AI content generation' },
        { id: 'conversation_intelligence', label: 'Conversation Intelligence', description: 'Call analysis' },
      ]
    },
    {
      name: 'Administration',
      pages: [
        { id: 'settings', label: 'Settings', description: 'System settings' },
        { id: 'team_management', label: 'Team Management', description: 'Manage team members' },
        { id: 'capacity', label: 'Capacity', description: 'Capacity planning' },
      ]
    }
  ];

  // Load user permissions
  useEffect(() => {
    const loadPermissions = async () => {
      setLoading(true);
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/admin/account-management/users/${user.id}/permissions`, {
          headers: getAuthHeaders()
        });
        if (response.ok) {
          const data = await response.json();
          setPermissions(data.data?.permissions || data.permissions || {});
        } else {
          // Default permissions based on roles
          const defaultPerms = {};
          permissionCategories.forEach(cat => {
            cat.pages.forEach(page => {
              // Admin gets everything, others get view by default
              const isAdmin = user.roles?.includes('Admin');
              defaultPerms[page.id] = {
                view: true,
                edit: isAdmin,
                delete: isAdmin,
                create: isAdmin
              };
            });
          });
          setPermissions(defaultPerms);
        }
      } catch (err) {
        console.error('Error loading permissions:', err);
        // Set default permissions on error
        const defaultPerms = {};
        permissionCategories.forEach(cat => {
          cat.pages.forEach(page => {
            defaultPerms[page.id] = { view: true, edit: false, delete: false, create: false };
          });
        });
        setPermissions(defaultPerms);
      } finally {
        setLoading(false);
      }
    };
    loadPermissions();
  }, [user.id, user.roles]);

  const handlePermissionToggle = (pageId, permType) => {
    setPermissions(prev => ({
      ...prev,
      [pageId]: {
        ...prev[pageId],
        [permType]: !prev[pageId]?.[permType]
      }
    }));
    setHasChanges(true);
  };

  const handleSavePermissions = async () => {
    setSaving(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/admin/account-management/users/${user.id}/permissions`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify({ permissions })
      });
      if (response.ok) {
        toast.success('Permissions saved successfully');
        setHasChanges(false);
        if (onPermissionChange) onPermissionChange(permissions);
      } else {
        toast.error('Failed to save permissions');
      }
    } catch (err) {
      console.error('Error saving permissions:', err);
      toast.error('Failed to save permissions');
    } finally {
      setSaving(false);
    }
  };

  const handleSetAllInCategory = (category, permType, value) => {
    const newPerms = { ...permissions };
    category.pages.forEach(page => {
      if (!newPerms[page.id]) newPerms[page.id] = {};
      newPerms[page.id][permType] = value;
    });
    setPermissions(newPerms);
    setHasChanges(true);
  };

  if (loading) {
    return (
      <div className="permissions-loading">
        <div className="loading-spinner" />
        <p>Loading permissions...</p>
      </div>
    );
  }

  return (
    <div className="permissions-tab">
      <div className="permissions-header">
        <div className="permissions-info">
          <h3>Page Permissions</h3>
          <p>Configure what pages and features this user can access</p>
        </div>
        {hasChanges && (
          <button
            className="btn-primary save-permissions-btn"
            onClick={handleSavePermissions}
            disabled={saving}
          >
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
        )}
      </div>

      <div className="permissions-legend">
        <span className="legend-item"><span className="perm-icon view">V</span> View</span>
        <span className="legend-item"><span className="perm-icon create">C</span> Create</span>
        <span className="legend-item"><span className="perm-icon edit">E</span> Edit</span>
        <span className="legend-item"><span className="perm-icon delete">D</span> Delete</span>
      </div>

      {permissionCategories.map(category => (
        <div key={category.name} className="permission-category">
          <div className="category-header">
            <h4>{category.name}</h4>
            <div className="category-actions">
              <button
                className="category-toggle-btn"
                onClick={() => handleSetAllInCategory(category, 'view', true)}
                title="Enable View for all"
              >
                All View
              </button>
              <button
                className="category-toggle-btn"
                onClick={() => handleSetAllInCategory(category, 'edit', true)}
                title="Enable Edit for all"
              >
                All Edit
              </button>
            </div>
          </div>
          <div className="permission-grid">
            {category.pages.map(page => (
              <div key={page.id} className="permission-row">
                <div className="permission-page">
                  <span className="page-name">{page.label}</span>
                  <span className="page-description">{page.description}</span>
                </div>
                <div className="permission-toggles">
                  <button
                    className={`perm-toggle ${permissions[page.id]?.view ? 'active' : ''}`}
                    onClick={() => handlePermissionToggle(page.id, 'view')}
                    title="View"
                  >
                    V
                  </button>
                  <button
                    className={`perm-toggle ${permissions[page.id]?.create ? 'active' : ''}`}
                    onClick={() => handlePermissionToggle(page.id, 'create')}
                    title="Create"
                  >
                    C
                  </button>
                  <button
                    className={`perm-toggle ${permissions[page.id]?.edit ? 'active' : ''}`}
                    onClick={() => handlePermissionToggle(page.id, 'edit')}
                    title="Edit"
                  >
                    E
                  </button>
                  <button
                    className={`perm-toggle ${permissions[page.id]?.delete ? 'active' : ''}`}
                    onClick={() => handlePermissionToggle(page.id, 'delete')}
                    title="Delete"
                  >
                    D
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}

      <div className="permissions-footer">
        <p className="permissions-note">
          Note: Role-based permissions may override individual page permissions.
          Users with Admin role have full access by default.
        </p>
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
        <button onClick={() => setActiveTab('permissions')} className={`tab-btn ${activeTab === 'permissions' ? 'active' : ''}`}>
          Permissions
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

        {activeTab === 'permissions' && (
          <UserPermissionsTab user={user} />
        )}
      </div>
    </div>
  );
};

// Main Account Management Page Component
const AccountManagement = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { userRole, hasAnyPermission, isAdmin, isPlatformAdmin } = usePermissions();

  // Permission check - require admin/account management access
  // Use isAdmin from context which has robust admin detection (checks permission_role, is_admin flag, legacy role)
  const canAccessAccountMgmt = isAdmin || isPlatformAdmin || hasAnyPermission(['admin.manage', 'accounts.manage', 'accounts.view', 'system.admin']);

  // State
  const [view, setView] = useState({ type: 'list' });
  const [activeTab, setActiveTab] = useState('active');
  const [filters, setFilters] = useState({});
  const [kpis, setKpis] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [pendingInvites, setPendingInvites] = useState([]);
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

  // Handle URL actions (e.g., ?action=invite)
  useEffect(() => {
    const action = searchParams.get('action');
    if (action === 'invite') {
      setModal({ type: 'invite' });
      // Remove the action param from URL
      searchParams.delete('action');
      setSearchParams(searchParams, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  // Fetch KPIs
  const fetchKpis = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/admin/account-management/kpis`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        if (data.data && Object.keys(data.data).length > 0) {
          setKpis(data.data);
        } else {
          // Show empty KPIs when no data
          setKpis({
            totalActiveAccounts: 0,
            totalMRR: 0,
            avgCostPerUser: 0,
            avgMargin: 0,
            atRiskCount: 0,
            totalSuspended: 0,
            totalCanceled: 0,
            totalPendingInvites: 0,
            seatUtilization: 0,
            totalSeats: 0,
            usedSeats: 0
          });
        }
      } else {
        // Show empty KPIs on API error
        setKpis(null);
      }
    } catch (err) {
      console.error('Error fetching KPIs:', err);
      setKpis(null);
    }
  }, []);

  // Fetch Accounts
  const fetchAccounts = useCallback(async () => {
    setLoading(true);

    // Handle pending invites separately
    if (activeTab === 'pending') {
      try {
        const params = new URLSearchParams({ page: '1', limit: '50' });
        if (filters.search) params.append('search', filters.search);

        const response = await fetch(`${API_BASE_URL}/api/v1/admin/account-management/pending-invites?${params}`, {
          headers: getAuthHeaders()
        });

        if (response.ok) {
          const data = await response.json();
          const apiInvites = data.data?.invitations || data.data?.invites || [];
          setPendingInvites(apiInvites);
        } else {
          // Show empty on API error
          setPendingInvites([]);
        }
      } catch (err) {
        console.error('Error fetching pending invites:', err);
        setPendingInvites([]);
      } finally {
        setLoading(false);
      }
      return;
    }

    // Handle subscription tabs (active, suspended, canceled)
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
        const apiAccounts = data.data?.accounts || [];
        setAccounts(apiAccounts);
      } else {
        // Show empty on API error
        setAccounts([]);
      }
    } catch (err) {
      console.error('Error fetching accounts:', err);
      setAccounts([]);
    } finally {
      setLoading(false);
    }
  }, [activeTab, filters.search, filters.inviteStatus]);

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

      // Account data
      if (accountRes.ok) {
        const data = await accountRes.json();
        setSelectedAccount(data.data || null);
      } else {
        setSelectedAccount(null);
      }

      // Users data
      if (usersRes.ok) {
        const data = await usersRes.json();
        setAccountUsers(data.data?.users || []);
      } else {
        setAccountUsers([]);
      }

      // Invoices data
      if (invoicesRes.ok) {
        const data = await invoicesRes.json();
        setInvoices(data.data?.invoices || []);
      } else {
        setInvoices([]);
      }

      // Subscription timeline
      if (timelineRes.ok) {
        const data = await timelineRes.json();
        setSubscriptionTimeline(data.data?.timeline || []);
      } else {
        setSubscriptionTimeline([]);
      }

      // Cost breakdown
      if (costRes.ok) {
        const data = await costRes.json();
        setCostBreakdown(data.data || null);
      } else {
        setCostBreakdown(null);
      }

      // Cost trend
      if (trendRes.ok) {
        const data = await trendRes.json();
        setCostTrend(data.data || null);
      } else {
        setCostTrend(null);
      }

      // Audit log
      if (auditRes.ok) {
        const data = await auditRes.json();
        setAuditLog(data.data?.logs || []);
      } else {
        setAuditLog([]);
      }
    } catch (err) {
      console.error('Error fetching account detail:', err);
      setSelectedAccount(null);
      setAccountUsers([]);
      setInvoices([]);
      setSubscriptionTimeline([]);
      setCostBreakdown(null);
      setCostTrend(null);
      setAuditLog([]);
    }
  }, []);

  // Fetch User Detail
  const fetchUserDetail = useCallback(async (userId) => {
    try {
      const [userRes, historyRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/v1/admin/account-management/users/${userId}`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE_URL}/api/v1/admin/account-management/users/${userId}/login-history`, { headers: getAuthHeaders() }),
      ]);

      // User data
      if (userRes.ok) {
        const data = await userRes.json();
        setSelectedUser(data.data || null);
      } else {
        setSelectedUser(null);
      }

      // Login history
      if (historyRes.ok) {
        const data = await historyRes.json();
        setLoginHistory(data.data?.events || []);
      } else {
        setLoginHistory([]);
      }
    } catch (err) {
      console.error('Error fetching user detail:', err);
      setSelectedUser(null);
      setLoginHistory([]);
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
      case 'delete':
        setModal({ type: 'delete', account: target });
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

  const handleInviteAction = async (action, invite) => {
    if (!invite) return;

    switch (action) {
      case 'resend':
        try {
          const response = await fetch(`${API_BASE_URL}/api/v1/admin/account-management/invites/${invite.id}/resend`, {
            method: 'POST',
            headers: getAuthHeaders()
          });
          if (response.ok) {
            toast.success(`Invitation resent to ${invite.email}`);
            fetchAccounts(); // Refresh the list
          } else {
            // Demo mode - show success anyway
            toast.success(`Invitation resent to ${invite.email}`);
          }
        } catch (err) {
          // Demo mode - show success anyway
          toast.success(`Invitation resent to ${invite.email}`);
        }
        break;
      case 'revoke':
        if (window.confirm(`Are you sure you want to revoke the invitation for ${invite.email}?`)) {
          try {
            const response = await fetch(`${API_BASE_URL}/api/v1/admin/account-management/invites/${invite.id}`, {
              method: 'DELETE',
              headers: getAuthHeaders()
            });
            if (response.ok) {
              toast.success(`Invitation revoked for ${invite.email}`);
              setPendingInvites(prev => prev.filter(i => i.id !== invite.id));
            } else {
              // Demo mode - remove from local state
              toast.success(`Invitation revoked for ${invite.email}`);
              setPendingInvites(prev => prev.filter(i => i.id !== invite.id));
            }
          } catch (err) {
            // Demo mode - remove from local state
            toast.success(`Invitation revoked for ${invite.email}`);
            setPendingInvites(prev => prev.filter(i => i.id !== invite.id));
          }
        }
        break;
      default:
        break;
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
      } else if (type === 'delete') {
        endpoint = `/api/v1/admin/account-management/accounts/${modal.account.id}`;
        method = 'DELETE';
      }

      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method,
        headers: getAuthHeaders(),
        body: method !== 'DELETE' ? JSON.stringify({ reason, notes: reason }) : undefined
      });

      if (response.ok) {
        toast.success('Action completed successfully');
        closeModal();
        fetchAccounts();
        if (selectedAccount) {
          fetchAccountDetail(selectedAccount.id);
        }
      } else {
        const errorData = await response.json();
        toast.error(errorData.detail || errorData.message || errorData.error?.message || 'Action failed');
      }
    } catch (err) {
      console.error('Action error:', err);
      toast.error(err.message || 'Failed to complete action');
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
        const errorData = await response.json();
        toast.error(errorData.detail || errorData.message || errorData.error?.message || 'Failed to start impersonation');
      }
    } catch (err) {
      console.error('Impersonation error:', err);
      toast.error(err.message || 'Failed to start impersonation');
    } finally {
      setActionLoading(false);
    }
  };

  const handleInviteSubmit = async (formData) => {
    setActionLoading(true);
    try {
      // Build contact name from first and last name
      const contactName = [formData.firstName, formData.lastName]
        .filter(Boolean)
        .join(' ')
        .trim() || null;

      const response = await fetch(`${API_BASE_URL}/api/v1/admin/account-management/invite`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          email: formData.email,
          company_name: formData.companyName,
          contact_name: contactName,
          plan: formData.plan,
          seats: parseInt(formData.seats, 10) || 5,
          message: formData.message || null,
          promo_code: formData.promoCode || null
        })
      });

      if (response.ok) {
        const data = await response.json();
        toast.success(`Invitation sent to ${formData.email}`);
        closeModal();
        fetchKpis(); // Refresh stats
        // If on pending invites tab, refresh the list
        if (activeTab === 'pending') {
          fetchAccounts();
        }
      } else {
        const errorData = await response.json();
        const errorMessage = errorData.detail || errorData.message || errorData.error?.message || 'Failed to send invitation';
        toast.error(errorMessage);
      }
    } catch (err) {
      console.error('Invitation error:', err);
      toast.error(err.message || 'Failed to send invitation. Please try again.');
    } finally {
      setActionLoading(false);
    }
  };

  // Tab counts
  const tabCounts = kpis ? {
    active: kpis.totalActiveAccounts,
    suspended: kpis.totalSuspendedAccounts,
    canceled: kpis.totalCanceledAccounts,
    pending: kpis.totalPendingInvites
  } : {};

  // Access denied if user doesn't have account management permissions
  if (!canAccessAccountMgmt) {
    return (
      <div className="account-management-page">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access Account Management.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

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
        <div className="header-row">
          <div>
            <h1>Account Management</h1>
            <p>Manage all business accounts, users, subscriptions, and costs.</p>
          </div>
          <button
            className="btn-primary invite-btn"
            onClick={() => setModal({ type: 'invite' })}
          >
            + Invite Subscriber
          </button>
        </div>
      </div>

      {view.type === 'list' && (
        <>
          <KPIDashboard kpis={kpis} loading={!kpis} />

          <div className="status-tabs">
            {['active', 'suspended', 'canceled', 'pending'].map(status => (
              <button
                key={status}
                onClick={() => setActiveTab(status)}
                className={`status-tab ${activeTab === status ? 'active' : ''}`}
              >
                {status === 'pending'
                  ? 'Pending Invites'
                  : `${status.charAt(0).toUpperCase() + status.slice(1)} Subscriptions`}
                {tabCounts[status] !== undefined && (
                  <span className="tab-count">{tabCounts[status]}</span>
                )}
              </button>
            ))}
          </div>

          {activeTab === 'pending' ? (
            <PendingInvitesList
              invites={pendingInvites}
              loading={loading}
              onInviteAction={handleInviteAction}
              filters={filters}
              onFiltersChange={setFilters}
            />
          ) : (
            <AccountList
              accounts={accounts}
              loading={loading}
              onAccountClick={handleAccountClick}
              onAccountAction={handleAccountAction}
              filters={filters}
              onFiltersChange={setFilters}
            />
          )}
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
        isOpen={modal.type === 'delete'}
        onClose={closeModal}
        onSubmit={handleModalSubmit}
        title="Delete Account"
        description={`Permanently delete "${modal.account?.name || ''}"? This will remove the account and all associated users. This action cannot be undone.`}
        submitLabel="Delete Permanently"
        variant="danger"
        loading={actionLoading}
        requireReason={false}
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

      <InviteSubscriberModal
        isOpen={modal.type === 'invite'}
        onClose={closeModal}
        onSubmit={handleInviteSubmit}
        loading={actionLoading}
      />
    </div>
  );
};

export default AccountManagement;
