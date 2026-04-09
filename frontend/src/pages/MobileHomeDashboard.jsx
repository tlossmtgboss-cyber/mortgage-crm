import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import { getCurrentUser } from '../utils/auth';
import { ensureArray } from '../utils/arrayHelpers';
import { initAuditLogger, auditLog, AUDIT_EVENTS } from '../services/mobileAuditLogger';
import MobileBottomNav from '../components/mobile/MobileBottomNav';
import './MobileHomeDashboard.css';

/**
 * MobileHomeDashboard - Quick-glance home screen for LOs on mobile.
 *
 * Replaces the previous /aria landing for mobile users.
 * Shows pipeline stats, urgent alerts, today's schedule, quick actions,
 * and recent activity in a single-column card-based layout.
 *
 * Rate lock alerts are displayed via /api/v1/pipeline/alerts (the single
 * canonical source). Do NOT add the RateLockAlert component here --
 * it uses a separate endpoint and would cause duplicate alerts.
 */

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

function formatTodayDate() {
  return new Date().toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  });
}

function formatCurrency(amount) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount || 0);
}

function relativeTime(dateStr) {
  if (!dateStr) return '';
  const now = new Date();
  const then = new Date(dateStr);
  const diffMs = now - then;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return 'Just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay === 1) return 'Yesterday';
  return `${diffDay}d ago`;
}

function relativeTimeFuture(dateStr) {
  if (!dateStr) return '';
  const now = new Date();
  const then = new Date(dateStr);
  const diffMs = then - now;
  if (diffMs < 0) {
    // Past due
    const pastMin = Math.floor(-diffMs / 60000);
    if (pastMin < 60) return `${pastMin}m overdue`;
    const pastHr = Math.floor(pastMin / 60);
    if (pastHr < 24) return `${pastHr}h overdue`;
    const pastDay = Math.floor(pastHr / 24);
    return `${pastDay}d overdue`;
  }
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 60) return `in ${diffMin}m`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `in ${diffHr}h`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay === 1) return 'Tomorrow';
  return `in ${diffDay}d`;
}

function formatTime(dateStr) {
  if (!dateStr) return '';
  return new Date(dateStr).toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
  });
}

// ---------------------------------------------------------------------------
// Skeleton loaders
// ---------------------------------------------------------------------------

function StatsSkeleton() {
  return (
    <div className="mhd-stats-grid">
      {[1, 2, 3, 4, 5].map((i) => (
        <div key={i} className="mhd-stat-card mhd-skeleton-card">
          <div className="mhd-skeleton-line mhd-skeleton-number" />
          <div className="mhd-skeleton-line mhd-skeleton-label" />
        </div>
      ))}
    </div>
  );
}

function AlertsSkeleton() {
  return (
    <div className="mhd-alerts">
      {[1, 2, 3].map((i) => (
        <div key={i} className="mhd-alert-item mhd-skeleton-card">
          <div className="mhd-skeleton-line mhd-skeleton-wide" />
          <div className="mhd-skeleton-line mhd-skeleton-narrow" />
        </div>
      ))}
    </div>
  );
}

function ScheduleSkeleton() {
  return (
    <div className="mhd-schedule-list">
      {[1, 2, 3].map((i) => (
        <div key={i} className="mhd-schedule-item mhd-skeleton-card">
          <div className="mhd-skeleton-line mhd-skeleton-narrow" />
          <div className="mhd-skeleton-line mhd-skeleton-wide" />
        </div>
      ))}
    </div>
  );
}

function ActivitySkeleton() {
  return (
    <div className="mhd-activity-list">
      {[1, 2, 3].map((i) => (
        <div key={i} className="mhd-activity-item mhd-skeleton-card">
          <div className="mhd-skeleton-circle" />
          <div style={{ flex: 1 }}>
            <div className="mhd-skeleton-line mhd-skeleton-wide" />
            <div className="mhd-skeleton-line mhd-skeleton-narrow" />
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// SVG Icons (inline to avoid extra dependencies)
// ---------------------------------------------------------------------------

const Icons = {
  loans: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="7" width="20" height="14" rx="2" ry="2" /><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2" />
    </svg>
  ),
  leads: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  ),
  tasks: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
    </svg>
  ),
  closing: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9z" /><polyline points="9 22 9 12 15 12 15 22" />
    </svg>
  ),
  workflow: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="16 3 21 3 21 8" /><line x1="4" y1="20" x2="21" y2="3" /><polyline points="21 16 21 21 16 21" /><line x1="15" y1="15" x2="21" y2="21" /><line x1="4" y1="4" x2="9" y2="9" />
    </svg>
  ),
  addLead: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="8.5" cy="7" r="4" /><line x1="20" y1="8" x2="20" y2="14" /><line x1="23" y1="11" x2="17" y2="11" />
    </svg>
  ),
  phone: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.79 19.79 0 0 1 2.12 4.18 2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
    </svg>
  ),
  upload: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" />
    </svg>
  ),
  newTask: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  ),
  clock: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
    </svg>
  ),
  alert: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  ),
  lock: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  ),
  chevronRight: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="9 18 15 12 9 6" />
    </svg>
  ),
  sparkle: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2 L13.5 8.5 L20 10 L13.5 11.5 L12 18 L10.5 11.5 L4 10 L10.5 8.5 Z" fill="currentColor" />
      <path d="M18 3 L18.6 5.4 L21 6 L18.6 6.6 L18 9 L17.4 6.6 L15 6 L17.4 5.4 Z" fill="currentColor" opacity="0.7" />
    </svg>
  ),
  ariaChat: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2 L13.2 7.2 L18.5 8.5 L13.2 9.8 L12 15 L10.8 9.8 L5.5 8.5 L10.8 7.2 Z" fill="currentColor" stroke="none" />
      <path d="M18 16v1a2 2 0 0 1-2 2H5l-3 3V9a2 2 0 0 1 2-2h1" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  ),
  call: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.79 19.79 0 0 1 2.12 4.18 2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
    </svg>
  ),
  meeting: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="18" rx="2" ry="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" />
    </svg>
  ),
  task: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
    </svg>
  ),
  email: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" /><polyline points="22,6 12,13 2,6" />
    </svg>
  ),
  note: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" />
    </svg>
  ),
};

function getActivityIcon(type) {
  const t = (type || '').toLowerCase();
  if (t.includes('call')) return Icons.call;
  if (t.includes('email')) return Icons.email;
  if (t.includes('meeting')) return Icons.meeting;
  if (t.includes('task')) return Icons.task;
  return Icons.note;
}

function getScheduleIcon(type) {
  const t = (type || '').toLowerCase();
  if (t.includes('call')) return Icons.call;
  if (t.includes('meeting')) return Icons.meeting;
  return Icons.task;
}

/**
 * Return the appropriate icon for an alert based on its type.
 * Rate lock alerts get a distinctive lock icon; others get the triangle alert.
 */
function getAlertIcon(alertType) {
  const t = (alertType || '').toLowerCase();
  if (t.includes('rate_lock') || t.includes('lock_expir')) return Icons.lock;
  return Icons.alert;
}

/**
 * Map pipeline alert severity to CSS modifier class.
 * - critical / rate_lock_expiring -> 'red'
 * - high -> 'red'
 * - everything else -> 'amber'
 */
function mapAlertSeverity(alert) {
  const severity = (alert.severity || '').toLowerCase();
  const type = (alert.alert_type || alert.type || '').toLowerCase();

  if (severity === 'critical' || severity === 'high') return 'red';
  if (type.includes('rate_lock') || type.includes('lock_expir')) return 'red';
  return 'amber';
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const MobileHomeDashboard = () => {
  const navigate = useNavigate();
  const user = getCurrentUser();
  const firstName = user?.first_name || user?.full_name?.split(' ')[0] || 'there';

  // State
  const [stats, setStats] = useState(null);
  const [alerts, setAlerts] = useState(null);
  const [workflowTasks, setWorkflowTasks] = useState(null);
  const [schedule, setSchedule] = useState(null);
  const [activity, setActivity] = useState(null);
  const [ariaInsight, setAriaInsight] = useState(null);
  const [ariaInsightLoading, setAriaInsightLoading] = useState(true);

  const [statsLoading, setStatsLoading] = useState(true);
  const [statsError, setStatsError] = useState(false);
  const [alertsLoading, setAlertsLoading] = useState(true);
  const [workflowTasksLoading, setWorkflowTasksLoading] = useState(true);
  const [scheduleLoading, setScheduleLoading] = useState(true);
  const [activityLoading, setActivityLoading] = useState(true);

  // Fetch stats
  const loadStats = useCallback(async () => {
    setStatsLoading(true);
    setStatsError(false);
    try {
      const [pipelineRes, taskSummaryRes, leadsRes, workflowSummaryRes] = await Promise.allSettled([
        api.get('/api/v1/loans/'),
        api.get('/api/v1/mobile/tasks/summary'),
        api.get('/api/v1/leads'),
        api.get('/api/v1/workflow/tasks', { params: { status: 'pending', limit: 1 } }),
      ]);

      // Count active loans (non-terminal stages)
      const terminalStages = new Set(['FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY']);
      const allLoans = pipelineRes.status === 'fulfilled'
        ? ensureArray(pipelineRes.value.data, 'loans')
        : [];
      const activeLoans = allLoans.filter(l => !terminalStages.has((l.stage || '').toUpperCase()));

      // Count closing this week
      const now = new Date();
      const endOfWeek = new Date(now);
      endOfWeek.setDate(now.getDate() + (7 - now.getDay()));
      const closingThisWeek = activeLoans.filter(l => {
        if (!l.closing_date) return false;
        const cd = new Date(l.closing_date);
        return cd >= now && cd <= endOfWeek;
      }).length;

      // Task count from mobile summary endpoint
      const taskSummary = taskSummaryRes.status === 'fulfilled'
        ? taskSummaryRes.value.data
        : null;
      const tasksDue = taskSummary?.pending ?? taskSummary?.total_active ?? 0;

      // Workflow task count
      const workflowData = workflowSummaryRes.status === 'fulfilled'
        ? workflowSummaryRes.value.data
        : null;
      const workflowPending = workflowData?.total ?? workflowData?.total_count ?? workflowData?.count ?? 0;

      // Count leads created today
      const todayStr = now.toISOString().split('T')[0];
      const leadsArr = leadsRes.status === 'fulfilled'
        ? ensureArray(leadsRes.value.data, 'leads')
        : [];
      const leadsToday = leadsArr.filter(l => (l.created_at || '').startsWith(todayStr)).length;

      setStats({
        activeLoans: activeLoans.length,
        leadsToday,
        tasksDue,
        closingThisWeek,
        workflowPending,
      });
    } catch (err) {
      console.error('MobileHomeDashboard: stats load error', err);
      setStatsError(true);
      setStats({ activeLoans: 0, leadsToday: 0, tasksDue: 0, closingThisWeek: 0, workflowPending: 0 });
    } finally {
      setStatsLoading(false);
    }
  }, []);

  // Fetch alerts -- single source: /api/v1/pipeline/alerts
  // This endpoint returns all alert types including rate_lock_expiring,
  // so we do NOT also fetch from /api/v1/rate-lock-intelligence/alerts.
  const loadAlerts = useCallback(async () => {
    setAlertsLoading(true);
    try {
      const [locksRes, tasksRes] = await Promise.allSettled([
        api.get('/api/v1/pipeline/alerts', { params: { limit: 5 } }),
        api.get('/api/v1/mobile/tasks', { params: { status: 'overdue', limit: 5 } }),
      ]);

      const lockAlerts = locksRes.status === 'fulfilled'
        ? (locksRes.value.data.alerts || locksRes.value.data || [])
        : [];

      const overdueTaskAlerts = tasksRes.status === 'fulfilled'
        ? (tasksRes.value.data?.tasks || tasksRes.value.data?.items || (Array.isArray(tasksRes.value.data) ? tasksRes.value.data : [])).map((t) => ({
            id: `task-${t.id}`,
            type: 'task_overdue',
            severity: 'amber',
            title: t.title || t.description || 'Overdue task',
            subtitle: t.borrower_name || t.loan_number || '',
            link: '/tasks',
          }))
        : [];

      // Normalize pipeline alerts with type-aware severity and icons
      const pipelineAlerts = Array.isArray(lockAlerts)
        ? lockAlerts.map((a) => {
            const alertType = a.alert_type || a.type || 'pipeline';
            return {
              id: a.id || a.loan_id || Math.random(),
              type: alertType,
              severity: mapAlertSeverity(a),
              title: a.title || a.message || a.description || 'Pipeline alert',
              subtitle: a.borrower_name || a.loan_number || '',
              link: a.loan_id ? `/loans/${a.loan_id}` : '/pipeline',
            };
          })
        : [];

      const combined = [...pipelineAlerts, ...overdueTaskAlerts].slice(0, 5);
      setAlerts(combined);
    } catch (err) {
      console.error('MobileHomeDashboard: alerts load error', err);
      setAlerts([]);
    } finally {
      setAlertsLoading(false);
    }
  }, []);

  // Fetch workflow tasks
  const loadWorkflowTasks = useCallback(async () => {
    setWorkflowTasksLoading(true);
    try {
      const res = await api.get('/api/v1/workflow/tasks', {
        params: { status: 'pending', limit: 5 },
      });
      const tasks = res.data?.tasks || res.data?.items || (Array.isArray(res.data) ? res.data : []);
      setWorkflowTasks(
        tasks.slice(0, 5).map((t) => ({
          id: t.id,
          name: t.name || t.title || t.task_name || 'Workflow Task',
          due_date: t.due_date || t.due_at || t.deadline,
          escalation_level: t.escalation_level ?? 0,
          health_status: t.health_status || t.health || 'healthy',
          ai_eligible: t.ai_eligible ?? false,
          loan_number: t.loan_number || '',
          borrower_name: t.borrower_name || '',
        }))
      );
    } catch (err) {
      console.error('MobileHomeDashboard: workflow tasks load error', err);
      setWorkflowTasks([]);
    } finally {
      setWorkflowTasksLoading(false);
    }
  }, []);

  // Fetch today's schedule
  const loadSchedule = useCallback(async () => {
    setScheduleLoading(true);
    try {
      const today = new Date().toISOString().split('T')[0];
      const res = await api.get('/api/v1/calendar/events', {
        params: { start_date: today, end_date: today, limit: 3 },
      });
      const events = res.data.events || res.data.items || res.data || [];
      setSchedule(
        (Array.isArray(events) ? events : []).slice(0, 3).map((e) => ({
          id: e.id,
          time: formatTime(e.start_time || e.start || e.scheduled_at),
          type: e.type || e.event_type || 'task',
          title: e.title || e.subject || e.description || '',
          contact: e.contact_name || e.attendee_name || e.borrower_name || '',
          link: e.id ? `/calendar?event=${e.id}` : '/calendar',
        }))
      );
    } catch (err) {
      console.error('MobileHomeDashboard: schedule load error', err);
      setSchedule([]);
    } finally {
      setScheduleLoading(false);
    }
  }, []);

  // Fetch recent activity
  const loadActivity = useCallback(async () => {
    setActivityLoading(true);
    try {
      const res = await api.get('/api/v1/lo/activity', { params: { limit: 5 } });
      const activities = res.data.activities || res.data.items || res.data || [];
      setActivity(
        (Array.isArray(activities) ? activities : []).slice(0, 5).map((a) => ({
          id: a.id || Math.random(),
          type: a.type || a.activity_type || '',
          description: a.description || a.content || a.title || '',
          time: relativeTime(a.created_at || a.timestamp),
          contact: a.contact_name || a.borrower_name || a.lead_name || '',
        }))
      );
    } catch (err) {
      console.error('MobileHomeDashboard: activity load error', err);
      setActivity([]);
    } finally {
      setActivityLoading(false);
    }
  }, []);

  // Fetch Aria insight — cached 30 min in localStorage
  const loadAriaInsight = useCallback(async () => {
    const CACHE_KEY = 'mhd_aria_insight';
    const CACHE_TTL = 30 * 60 * 1000; // 30 minutes
    setAriaInsightLoading(true);
    try {
      const cached = localStorage.getItem(CACHE_KEY);
      if (cached) {
        const { text, ts } = JSON.parse(cached);
        if (Date.now() - ts < CACHE_TTL && text) {
          setAriaInsight(text);
          setAriaInsightLoading(false);
          return;
        }
      }
      const res = await api.post('/api/v1/ai/orchestrator-chat', {
        message: 'Give me one brief actionable insight for my day in 1-2 sentences based on my pipeline and tasks',
      });
      const text = res.data?.response || res.data?.message || res.data?.content || null;
      if (text) {
        setAriaInsight(text);
        localStorage.setItem(CACHE_KEY, JSON.stringify({ text, ts: Date.now() }));
      }
    } catch (_err) {
      // Silently fail — section won't render
      setAriaInsight(null);
    } finally {
      setAriaInsightLoading(false);
    }
  }, []);

  // Initialize mobile audit logger once per session
  useEffect(() => {
    initAuditLogger(user?.id, user?.organization_id);
    auditLog(AUDIT_EVENTS.APP_OPENED, { screen: 'dashboard' });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    loadStats();
    loadAlerts();
    loadWorkflowTasks();
    loadSchedule();
    loadActivity();
    loadAriaInsight();
  }, [loadStats, loadAlerts, loadWorkflowTasks, loadSchedule, loadActivity, loadAriaInsight]);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="mhd">
      {/* 1. Greeting bar */}
      <header className="mhd-greeting">
        <h1 className="mhd-greeting__name">{getGreeting()}, {firstName}</h1>
        <p className="mhd-greeting__date">{formatTodayDate()}</p>
      </header>

      {/* 2. Quick stats 2x2 */}
      {statsLoading ? (
        <StatsSkeleton />
      ) : (
        <div className="mhd-stats-grid">
          <button
            className="mhd-stat-card mhd-stat-card--primary"
            onClick={() => navigate('/pipeline')}
            aria-label={`Active loans: ${stats?.activeLoans}`}
          >
            <span className="mhd-stat-card__icon">{Icons.loans}</span>
            <span className="mhd-stat-card__value">{stats?.activeLoans ?? 0}</span>
            <span className="mhd-stat-card__label">Active Loans</span>
          </button>

          <button
            className="mhd-stat-card mhd-stat-card--success"
            onClick={() => navigate('/leads')}
            aria-label={`Leads today: ${stats?.leadsToday}`}
          >
            <span className="mhd-stat-card__icon">{Icons.leads}</span>
            <span className="mhd-stat-card__value">{stats?.leadsToday ?? 0}</span>
            <span className="mhd-stat-card__label">Leads Today</span>
          </button>

          <button
            className="mhd-stat-card mhd-stat-card--warning"
            onClick={() => navigate('/tasks')}
            aria-label={`Tasks due: ${stats?.tasksDue}`}
          >
            <span className="mhd-stat-card__icon">{Icons.tasks}</span>
            <span className="mhd-stat-card__value">{stats?.tasksDue ?? 0}</span>
            <span className="mhd-stat-card__label">Tasks Due</span>
          </button>

          <button
            className="mhd-stat-card mhd-stat-card--info"
            onClick={() => navigate('/pipeline?filter=closing')}
            aria-label={`Closing this week: ${stats?.closingThisWeek}`}
          >
            <span className="mhd-stat-card__icon">{Icons.closing}</span>
            <span className="mhd-stat-card__value">{stats?.closingThisWeek ?? 0}</span>
            <span className="mhd-stat-card__label">Closing This Week</span>
          </button>

          <button
            className="mhd-stat-card mhd-stat-card--workflow"
            onClick={() => navigate('/tasks')}
            aria-label={`Workflow tasks: ${stats?.workflowPending}`}
          >
            <span className="mhd-stat-card__icon">{Icons.workflow}</span>
            <span className="mhd-stat-card__value">{stats?.workflowPending ?? 0}</span>
            <span className="mhd-stat-card__label">Workflow Tasks</span>
          </button>
        </div>
      )}

      {statsError && (
        <button className="mhd-stats-error" onClick={loadStats} aria-label="Retry loading stats">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M8 1.333A6.674 6.674 0 0 0 1.333 8 6.674 6.674 0 0 0 8 14.667 6.674 6.674 0 0 0 14.667 8 6.674 6.674 0 0 0 8 1.333zm0 10a.667.667 0 1 1 0-1.334.667.667 0 0 1 0 1.334zm.667-3.333a.667.667 0 0 1-1.334 0V4.667a.667.667 0 0 1 1.334 0V8z" fill="currentColor"/>
          </svg>
          <span>Some data couldn't be loaded. Tap to retry.</span>
        </button>
      )}

      {/* 3. Urgent alerts (single source: /api/v1/pipeline/alerts) */}
      <section className="mhd-section">
        <div className="mhd-section__header">
          <h2 className="mhd-section__title">Urgent Alerts</h2>
          {alerts && alerts.length > 0 && (
            <button className="mhd-section__link" onClick={() => navigate('/pipeline')}>
              View all {Icons.chevronRight}
            </button>
          )}
        </div>

        {alertsLoading ? (
          <AlertsSkeleton />
        ) : alerts && alerts.length > 0 ? (
          <div className="mhd-alerts">
            {alerts.map((alert) => (
              <button
                key={alert.id}
                className={`mhd-alert-item mhd-alert-item--${alert.severity}`}
                onClick={() => navigate(alert.link)}
              >
                <span className="mhd-alert-item__icon">{getAlertIcon(alert.type)}</span>
                <div className="mhd-alert-item__content">
                  <span className="mhd-alert-item__title">{alert.title}</span>
                  {alert.subtitle && (
                    <span className="mhd-alert-item__subtitle">{alert.subtitle}</span>
                  )}
                </div>
                <span className="mhd-alert-item__chevron">{Icons.chevronRight}</span>
              </button>
            ))}
          </div>
        ) : (
          <div className="mhd-empty">No urgent alerts right now</div>
        )}
      </section>

      {/* 4. Workflow Tasks */}
      <section className="mhd-section">
        <div className="mhd-section__header">
          <h2 className="mhd-section__title">Workflow Tasks</h2>
          {workflowTasks && workflowTasks.length > 0 && (
            <button className="mhd-section__link" onClick={() => navigate('/tasks')}>
              View all {Icons.chevronRight}
            </button>
          )}
        </div>

        {workflowTasksLoading ? (
          <AlertsSkeleton />
        ) : workflowTasks && workflowTasks.length > 0 ? (
          <div className="mhd-workflow-tasks">
            {workflowTasks.map((task) => (
              <button
                key={task.id}
                className="mhd-workflow-task-item"
                onClick={() => navigate('/tasks')}
              >
                <span className={`mhd-workflow-task-health mhd-workflow-task-health--${task.health_status}`} />
                <div className="mhd-workflow-task-content">
                  <div className="mhd-workflow-task-header">
                    <span className="mhd-workflow-task-name">{task.name}</span>
                    <div className="mhd-workflow-task-badges">
                      {task.ai_eligible && (
                        <span className="mhd-workflow-badge mhd-workflow-badge--ai">AI</span>
                      )}
                      {task.escalation_level > 0 && (
                        <span className="mhd-workflow-badge mhd-workflow-badge--escalated">
                          Escalated L{task.escalation_level}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="mhd-workflow-task-meta">
                    {task.borrower_name && <span>{task.borrower_name}</span>}
                    {task.borrower_name && task.due_date && <span className="mhd-activity-item__dot" />}
                    {task.due_date && <span>{relativeTimeFuture(task.due_date)}</span>}
                  </div>
                </div>
                <span className="mhd-alert-item__chevron">{Icons.chevronRight}</span>
              </button>
            ))}
          </div>
        ) : (
          <div className="mhd-empty">No workflow tasks</div>
        )}
      </section>

      {/* 5. Aria Insights */}
      {(ariaInsightLoading || ariaInsight) && (
        <section className="mhd-section">
          <div className="mhd-section__header">
            <h2 className="mhd-section__title mhd-section__title--aria">
              <span className="mhd-aria-sparkle">{Icons.sparkle}</span>
              Aria Insights
            </h2>
          </div>
          <div className="mhd-aria-insight-card">
            {ariaInsightLoading ? (
              <>
                <div className="mhd-skeleton-line mhd-skeleton-wide" style={{ marginBottom: 8 }} />
                <div className="mhd-skeleton-line mhd-skeleton-narrow" />
              </>
            ) : (
              <>
                <p className="mhd-aria-insight-text">{ariaInsight}</p>
                <button
                  className="mhd-aria-ask-btn"
                  onClick={() => navigate('/mobile-aria')}
                  aria-label="Ask Aria"
                >
                  {Icons.ariaChat}
                  Ask Aria
                </button>
              </>
            )}
          </div>
        </section>
      )}

      {/* 6. Today's schedule */}
      <section className="mhd-section">
        <div className="mhd-section__header">
          <h2 className="mhd-section__title">Today's Schedule</h2>
          <button className="mhd-section__link" onClick={() => navigate('/calendar')}>
            Full calendar {Icons.chevronRight}
          </button>
        </div>

        {scheduleLoading ? (
          <ScheduleSkeleton />
        ) : schedule && schedule.length > 0 ? (
          <div className="mhd-schedule-list">
            {schedule.map((event) => (
              <button
                key={event.id}
                className="mhd-schedule-item"
                onClick={() => navigate(event.link)}
              >
                <div className="mhd-schedule-item__time">
                  {Icons.clock}
                  <span>{event.time}</span>
                </div>
                <div className="mhd-schedule-item__body">
                  <span className="mhd-schedule-item__title">{event.title}</span>
                  {event.contact && (
                    <span className="mhd-schedule-item__contact">{event.contact}</span>
                  )}
                </div>
                <span className="mhd-schedule-item__type-badge">
                  {getScheduleIcon(event.type)}
                </span>
              </button>
            ))}
          </div>
        ) : (
          <div className="mhd-empty">No events scheduled for today</div>
        )}
      </section>

      {/* 7. Quick actions */}
      <section className="mhd-section">
        <h2 className="mhd-section__title">Quick Actions</h2>
        <div className="mhd-quick-actions">
          <button
            className="mhd-quick-action"
            onClick={() => navigate('/leads?action=new')}
            aria-label="Add Lead"
          >
            <span className="mhd-quick-action__circle mhd-quick-action__circle--blue">
              {Icons.addLead}
            </span>
            <span className="mhd-quick-action__label">Add Lead</span>
          </button>

          <button
            className="mhd-quick-action"
            onClick={() => navigate('/dialer')}
            aria-label="Make Call"
          >
            <span className="mhd-quick-action__circle mhd-quick-action__circle--green">
              {Icons.phone}
            </span>
            <span className="mhd-quick-action__label">Make Call</span>
          </button>

          <button
            className="mhd-quick-action"
            onClick={() => navigate('/smart-docs')}
            aria-label="Upload Doc"
          >
            <span className="mhd-quick-action__circle mhd-quick-action__circle--purple">
              {Icons.upload}
            </span>
            <span className="mhd-quick-action__label">Upload Doc</span>
          </button>

          <button
            className="mhd-quick-action"
            onClick={() => navigate('/tasks?action=new')}
            aria-label="New Task"
          >
            <span className="mhd-quick-action__circle mhd-quick-action__circle--amber">
              {Icons.newTask}
            </span>
            <span className="mhd-quick-action__label">New Task</span>
          </button>

          <button
            className="mhd-quick-action"
            onClick={() => navigate('/mobile-aria')}
            aria-label="Ask Aria"
          >
            <span className="mhd-quick-action__circle mhd-quick-action__circle--aria">
              {Icons.sparkle}
            </span>
            <span className="mhd-quick-action__label">Ask Aria</span>
          </button>
        </div>
      </section>

      {/* 8. Recent activity feed */}
      <section className="mhd-section mhd-section--last">
        <div className="mhd-section__header">
          <h2 className="mhd-section__title">Recent Activity</h2>
        </div>

        {activityLoading ? (
          <ActivitySkeleton />
        ) : activity && activity.length > 0 ? (
          <div className="mhd-activity-list">
            {activity.map((item) => (
              <div key={item.id} className="mhd-activity-item">
                <span className="mhd-activity-item__icon">
                  {getActivityIcon(item.type)}
                </span>
                <div className="mhd-activity-item__content">
                  <span className="mhd-activity-item__desc">{item.description}</span>
                  <span className="mhd-activity-item__meta">
                    {item.contact && <span>{item.contact}</span>}
                    {item.contact && item.time && <span className="mhd-activity-item__dot" />}
                    <span>{item.time}</span>
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="mhd-empty">No recent activity</div>
        )}
      </section>

      {/* Spacer for bottom nav */}
      <div className="mhd-bottom-spacer" />

      <MobileBottomNav />
    </div>
  );
};

export default MobileHomeDashboard;
