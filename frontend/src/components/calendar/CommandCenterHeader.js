import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { schedulerAPI, tasksAPI, leadsAPI, loansAPI } from '../../services/api';
import { normalizeUTCDate, getUserTimezone } from './calendarUtils';
import './CommandCenterHeader.css';
import { getUserData } from '../../utils/tokenStore';

// SLA targets in days — mirrors backend SLA_TARGETS
const SLA_TARGETS_BY_STAGE = {
  APPLICATION: 3, DISCLOSED: 7, PROCESSING: 7, SUBMITTED: 2,
  UNDERWRITING: 5, UW_RECEIVED: 5, CONDITIONAL_APPROVAL: 3,
  APPROVED: 3, CLEAR_TO_CLOSE: 3, CTC: 3, DOCS: 5, DOCS_OUT: 5, CLOSING: 5,
};

const TERMINAL_STAGES = ['FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY'];

function getGreeting() {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  return 'Good evening';
}

function getUserName() {
  try {
    const d = getUserData();
    if (d) {
      const u = JSON.parse(d);
      return u.first_name || u.name || '';
    }
  } catch { /* ignore */ }
  return '';
}

function daysBetween(dateStr) {
  if (!dateStr) return null;
  return Math.floor((new Date() - new Date(dateStr)) / 86400000);
}

/**
 * StatCard -- Displays a single KPI metric with icon, value, label, and optional link.
 *
 * Used in: CommandCenterHeader
 *
 * @param {Object} props
 * @param {React.ReactNode} props.icon - SVG icon element rendered beside the stat
 * @param {string} props.label - Metric label (e.g. "Today's Appointments")
 * @param {number|string} props.value - The metric value to display
 * @param {string|null} [props.sublabel=null] - Secondary text below the label (e.g. "Next at 2:00 PM")
 * @param {string} props.color - Color theme key applied as CSS modifier (primary|info|danger|warning|success)
 * @param {boolean} props.loading - Whether the stat is still loading (shows placeholder dash)
 * @param {string} [props.to] - Optional React Router path; wraps card in a Link when provided
 * @returns {React.ReactElement}
 *
 * @example
 * <StatCard icon={<CalendarIcon />} label="Today's Appointments" value={5} color="primary" loading={false} />
 */
function StatCard({ icon, label, value, sublabel, color, loading, to }) {
  const content = (
    <div className={`cc-stat-card cc-stat-card--${color}`}>
      <div className="cc-stat-icon">{icon}</div>
      <div className="cc-stat-data">
        <div className="cc-stat-value">{loading ? '-' : value}</div>
        <div className="cc-stat-label">{label}</div>
        {sublabel && <div className="cc-stat-sublabel">{sublabel}</div>}
      </div>
    </div>
  );

  if (to) return <Link to={to} className="cc-stat-link">{content}</Link>;
  return content;
}

/**
 * CommandCenterHeader -- Top-of-page greeting banner with four independently-fetched KPI stat cards.
 *
 * Fetches today's appointments, pending tasks, SLA alerts, and leads needing follow-up
 * in parallel on mount, then notifies the parent when all stats are loaded.
 *
 * Used in: Calendar (main page)
 *
 * @param {Object} props
 * @param {Function} [props.onStatsFetched] - Callback(stats) invoked once all four stats finish loading
 * @returns {React.ReactElement}
 *
 * @example
 * <CommandCenterHeader onStatsFetched={(stats) => console.log(stats)} />
 */
const CommandCenterHeader = React.memo(function CommandCenterHeader({ onStatsFetched }) {
  const [stats, setStats] = useState({
    appointments: { today: 0, next: null, loading: true },
    tasks: { due: 0, overdue: 0, loading: true },
    sla: { alerts: 0, critical: 0, loading: true },
    leads: { needFollowUp: 0, loading: true },
  });

  const userName = getUserName();
  const greeting = getGreeting();
  const now = new Date();
  const dateStr = now.toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
  });

  // Fetch appointments count
  useEffect(() => {
    (async () => {
      try {
        const today = new Date();
        const start = new Date(today.getFullYear(), today.getMonth(), today.getDate()).toISOString();
        const end = new Date(today.getFullYear(), today.getMonth(), today.getDate(), 23, 59, 59).toISOString();
        const data = await schedulerAPI.getAppointments({ start_date: start, end_date: end });
        const appts = Array.isArray(data) ? data : [];
        const upcoming = appts
          .filter(a => new Date(a.start_time || a.starts_at || 0) > new Date())
          .sort((a, b) => new Date(a.start_time || a.starts_at || 0) - new Date(b.start_time || b.starts_at || 0));
        const nextAppt = upcoming[0];
        let nextLabel = null;
        if (nextAppt) {
          const t = new Date(normalizeUTCDate(nextAppt.start_time || nextAppt.starts_at));
          const tz = getUserTimezone();
          nextLabel = t.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true, timeZone: tz });
        }
        setStats(prev => ({ ...prev, appointments: { today: appts.length, next: nextLabel, loading: false } }));
      } catch {
        setStats(prev => ({ ...prev, appointments: { today: 0, next: null, loading: false } }));
      }
    })();
  }, []);

  // Fetch tasks count
  useEffect(() => {
    (async () => {
      try {
        const data = await tasksAPI.getAll({ status: 'pending' });
        const all = Array.isArray(data) ? data : [];
        const todayStr = new Date().toISOString().split('T')[0];
        let due = 0, overdue = 0;
        for (const t of all) {
          if (t.status === 'completed' || t.status === 'cancelled' || !t.due_date) continue;
          const dueStr = (t.due_date || '').split('T')[0];
          if (dueStr <= todayStr) {
            due++;
            if (dueStr < todayStr) overdue++;
          }
        }
        setStats(prev => ({ ...prev, tasks: { due, overdue, loading: false } }));
      } catch {
        setStats(prev => ({ ...prev, tasks: { due: 0, overdue: 0, loading: false } }));
      }
    })();
  }, []);

  // Fetch SLA alerts
  useEffect(() => {
    (async () => {
      try {
        const data = await loansAPI.getAll();
        const loans = Array.isArray(data) ? data : [];
        let alerts = 0, critical = 0;
        for (const loan of loans) {
          const stage = (loan.stage || '').toUpperCase();
          if (TERMINAL_STAGES.includes(stage)) continue;
          const changed = loan.stage_changed_at || loan.updated_at;
          const days = daysBetween(changed);
          if (days === null) continue;
          const target = SLA_TARGETS_BY_STAGE[stage] || 7;
          const remaining = target - days;
          if (remaining <= 2) {
            alerts++;
            if (remaining < 0) critical++;
          }
        }
        setStats(prev => ({ ...prev, sla: { alerts, critical, loading: false } }));
      } catch {
        setStats(prev => ({ ...prev, sla: { alerts: 0, critical: 0, loading: false } }));
      }
    })();
  }, []);

  // Fetch leads needing follow-up
  useEffect(() => {
    (async () => {
      try {
        const data = await leadsAPI.getAll();
        const all = Array.isArray(data) ? data : [];
        const closed = ['Funded', 'Closed', 'Dead', 'Lost', 'Cancelled', 'Withdrawn'];
        let count = 0;
        for (const lead of all) {
          if (closed.includes(lead.stage)) continue;
          const last = lead.last_contact || lead.last_contacted_at || lead.updated_at;
          const days = daysBetween(last);
          if (days === null || days >= 3) count++;
        }
        setStats(prev => ({ ...prev, leads: { needFollowUp: count, loading: false } }));
      } catch {
        setStats(prev => ({ ...prev, leads: { needFollowUp: 0, loading: false } }));
      }
    })();
  }, []);

  // Notify parent when stats are ready
  useEffect(() => {
    const allLoaded = !stats.appointments.loading && !stats.tasks.loading
      && !stats.sla.loading && !stats.leads.loading;
    if (allLoaded && onStatsFetched) {
      onStatsFetched(stats);
    }
  }, [stats, onStatsFetched]);

  return (
    <div className="cc-header" role="banner">
      <div className="cc-header-top">
        <div className="cc-greeting">
          <h1 className="cc-greeting-text">
            {greeting}{userName ? `, ${userName}` : ''}
          </h1>
          <p className="cc-date">{dateStr}</p>
        </div>
        <div className="cc-quick-actions">
          <Link to="/calendar/analytics" className="cc-quick-btn">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 20V10M12 20V4M6 20v-6" />
            </svg>
            Analytics
          </Link>
          <Link to="/team-calendar" className="cc-quick-btn">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
              <circle cx="9" cy="7" r="4" />
              <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
            </svg>
            Team
          </Link>
          <Link to="/calendar-settings" className="cc-quick-btn">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
            Settings
          </Link>
        </div>
      </div>

      <div className="cc-stats-strip" role="region" aria-label="Daily overview">
        <StatCard
          icon={<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" /></svg>}
          label="Today's Appointments"
          value={stats.appointments.today}
          sublabel={stats.appointments.next ? `Next at ${stats.appointments.next}` : null}
          color="primary"
          loading={stats.appointments.loading}
        />
        <StatCard
          icon={<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" /></svg>}
          label="Tasks Due"
          value={stats.tasks.due}
          sublabel={stats.tasks.overdue > 0 ? `${stats.tasks.overdue} overdue` : null}
          color={stats.tasks.overdue > 0 ? 'danger' : 'info'}
          loading={stats.tasks.loading}
          to="/tasks"
        />
        <StatCard
          icon={<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" /></svg>}
          label="SLA Alerts"
          value={stats.sla.alerts}
          sublabel={stats.sla.critical > 0 ? `${stats.sla.critical} critical` : null}
          color={stats.sla.critical > 0 ? 'danger' : stats.sla.alerts > 0 ? 'warning' : 'success'}
          loading={stats.sla.loading}
          to="/pipeline-efficiency"
        />
        <StatCard
          icon={<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" /></svg>}
          label="Leads Need Follow-Up"
          value={stats.leads.needFollowUp}
          sublabel={stats.leads.needFollowUp > 0 ? 'Action needed' : 'All caught up'}
          color={stats.leads.needFollowUp > 5 ? 'warning' : 'success'}
          loading={stats.leads.loading}
          to="/leads"
        />
      </div>
    </div>
  );
});

export default CommandCenterHeader;
