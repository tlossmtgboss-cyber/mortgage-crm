import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { schedulerAPI, tasksAPI, leadsAPI, loansAPI } from '../../services/api';
import { normalizeUTCDate, getUserTimezone } from './calendarUtils';
import './OperationalSidebar.css';

// ─── Shared helpers ──────────────────────────────────────────────────────────

function daysBetween(dateStr) {
  if (!dateStr) return null;
  return Math.floor((new Date() - new Date(dateStr)) / 86400000);
}

function formatTime(iso) {
  if (!iso) return '';
  const tz = getUserTimezone();
  return new Date(normalizeUTCDate(iso)).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true, timeZone: tz });
}

function isPast(iso) {
  if (!iso) return false;
  return new Date(normalizeUTCDate(iso)) < new Date();
}

// SLA targets — mirrors backend
const SLA_TARGETS = {
  APPLICATION: 3, DISCLOSED: 7, PROCESSING: 7, SUBMITTED: 2,
  UNDERWRITING: 5, UW_RECEIVED: 5, CONDITIONAL_APPROVAL: 3,
  APPROVED: 3, CLEAR_TO_CLOSE: 3, CTC: 3, DOCS: 5, DOCS_OUT: 5, CLOSING: 5,
};
const TERMINAL = ['FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY'];

// ─── Loading skeleton ────────────────────────────────────────────────────────

/**
 * SidebarSkeleton -- Animated placeholder rows shown while sidebar tab data is loading.
 *
 * Used in: TodayTab, TasksTab, LeadsTab, SLATab
 *
 * @param {Object} props
 * @param {number} [props.rows=4] - Number of skeleton rows to render
 * @returns {React.ReactElement}
 */
function SidebarSkeleton({ rows = 4 }) {
  return (
    <div className="ops-skeleton">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="ops-skeleton-row" />
      ))}
    </div>
  );
}

// ─── Empty state ─────────────────────────────────────────────────────────────

/**
 * SidebarEmpty -- Centered empty-state message with icon, title, and optional subtitle.
 *
 * Used in: TodayTab, TasksTab, LeadsTab, SLATab, AppointmentsTab
 *
 * @param {Object} props
 * @param {string} props.icon - HTML entity or emoji string for the icon
 * @param {string} props.title - Primary message text
 * @param {string} [props.subtitle] - Secondary descriptive text
 * @returns {React.ReactElement}
 */
function SidebarEmpty({ icon, title, subtitle }) {
  return (
    <div className="ops-empty">
      <div className="ops-empty-icon">{icon}</div>
      <div className="ops-empty-title">{title}</div>
      {subtitle && <div className="ops-empty-sub">{subtitle}</div>}
    </div>
  );
}

// ─── Error state ─────────────────────────────────────────────────────────────

/**
 * SidebarError -- Inline error message with a retry button for failed data fetches.
 *
 * Used in: TodayTab, TasksTab, LeadsTab, SLATab
 *
 * @param {Object} props
 * @param {string} props.message - Error message to display
 * @param {Function} props.onRetry - Callback invoked when the user clicks "Retry"
 * @returns {React.ReactElement}
 */
function SidebarError({ message, onRetry }) {
  return (
    <div className="ops-error">
      <p>{message}</p>
      <button className="ops-retry-btn" onClick={onRetry}>Retry</button>
    </div>
  );
}

// =============================================================================
// Tab: Today's Schedule
// =============================================================================

/**
 * TodayTab -- Timeline view of today's appointments with "NOW" indicator on the active one,
 * plus a Priority Alerts feed showing the most urgent items from Tasks, Leads, and SLA tabs.
 *
 * Self-contained: fetches today's schedule, pending tasks, leads, and loans on mount.
 *
 * Used in: OperationalSidebar
 *
 * @param {Object} props
 * @param {Function} props.onSwitchTab - Callback(tabKey) to switch the active sidebar tab
 * @returns {React.ReactElement}
 */
function TodayTab({ onSwitchTab, selectedDate }) {
  const [appointments, setAppointments] = useState([]);
  const [priorityAlerts, setPriorityAlerts] = useState({ tasks: [], leads: [], sla: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const targetDate = selectedDate || new Date();
      const dateStr = `${targetDate.getFullYear()}-${String(targetDate.getMonth() + 1).padStart(2, '0')}-${String(targetDate.getDate()).padStart(2, '0')}`;
      const todayStr = new Date().toISOString().split('T')[0];

      // Fetch all four data sources in parallel
      const [scheduleData, tasksData, leadsData, loansData] = await Promise.allSettled([
        schedulerAPI.getAppointments({ start_date: dateStr, end_date: dateStr }),
        tasksAPI.getAll({ status: 'pending' }),
        leadsAPI.getAll(),
        loansAPI.getAll(),
      ]);

      // --- Appointments ---
      const appts = scheduleData.status === 'fulfilled' ? scheduleData.value : [];
      const sorted = (Array.isArray(appts) ? appts : [])
        .map(a => ({
          ...a,
          start_time: a.start_time || a.scheduled_start || a.starts_at,
          end_time: a.end_time || a.scheduled_end || a.ends_at,
        }))
        .sort((a, b) => new Date(a.start_time || 0) - new Date(b.start_time || 0));
      setAppointments(sorted);

      // --- Overdue tasks (up to 3) ---
      let overdueTasks = [];
      if (tasksData.status === 'fulfilled') {
        const allTasks = Array.isArray(tasksData.value) ? tasksData.value : [];
        overdueTasks = allTasks
          .filter(t => {
            if (t.status === 'completed' || t.status === 'cancelled' || !t.due_date) return false;
            return (t.due_date || '').split('T')[0] < todayStr;
          })
          .sort((a, b) => new Date(a.due_date) - new Date(b.due_date))
          .slice(0, 3)
          .map(t => ({
            id: t.id,
            text: t.title || t.description || 'Task',
            detail: t.loan_number ? `#${t.loan_number}` : '',
            daysLate: Math.abs(daysBetween((t.due_date || '').split('T')[0])),
            link: t.loan_id ? `/loans/${t.loan_id}` : '/tasks',
          }));
      }

      // --- Leads needing follow-up > 5 days (up to 3) ---
      let staleLeads = [];
      if (leadsData.status === 'fulfilled') {
        const allLeads = Array.isArray(leadsData.value) ? leadsData.value : [];
        const closedStages = ['Funded', 'Closed', 'Dead', 'Lost', 'Cancelled', 'Withdrawn'];
        staleLeads = allLeads
          .filter(lead => {
            if (closedStages.includes(lead.stage)) return false;
            const last = lead.last_contact || lead.last_contacted_at || lead.updated_at;
            const days = daysBetween(last);
            return days === null || days > 5;
          })
          .sort((a, b) => {
            const ad = daysBetween(a.last_contact || a.last_contacted_at || a.updated_at) || 999;
            const bd = daysBetween(b.last_contact || b.last_contacted_at || b.updated_at) || 999;
            return bd - ad;
          })
          .slice(0, 3)
          .map(lead => {
            const name = lead.first_name && lead.last_name
              ? `${lead.first_name} ${lead.last_name}`
              : lead.first_name || lead.name || 'Unknown';
            const last = lead.last_contact || lead.last_contacted_at || lead.updated_at;
            const days = daysBetween(last);
            return {
              id: lead.id,
              text: name,
              detail: days === null ? 'Never contacted' : `${days}d since contact`,
              link: `/leads/${lead.id}`,
            };
          });
      }

      // --- Critical SLA alerts (remaining < 0, up to 3) ---
      let slaAlerts = [];
      if (loansData.status === 'fulfilled') {
        const allLoans = Array.isArray(loansData.value) ? loansData.value : [];
        const slaItems = [];
        for (const loan of allLoans) {
          const stage = (loan.stage || '').toUpperCase();
          if (TERMINAL.includes(stage)) continue;
          const changed = loan.stage_changed_at || loan.updated_at;
          const days = daysBetween(changed);
          if (days === null) continue;
          const target = SLA_TARGETS[stage] || 7;
          const remaining = target - days;
          if (remaining < 0) {
            slaItems.push({
              id: loan.id,
              text: loan.loan_number ? `#${loan.loan_number}` : 'Loan',
              detail: `${stage.replace(/_/g, ' ')} - ${Math.abs(remaining)}d over SLA`,
              borrower: loan.borrower_name || loan.borrower || '',
              remaining,
              link: `/loans/${loan.id}`,
            });
          }
        }
        slaAlerts = slaItems
          .sort((a, b) => a.remaining - b.remaining)
          .slice(0, 3);
      }

      setPriorityAlerts({ tasks: overdueTasks, leads: staleLeads, sla: slaAlerts });
    } catch (err) {
      setError('Failed to load today view');
    } finally {
      setLoading(false);
    }
  }, [selectedDate]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const currentIdx = useMemo(() => {
    const now = new Date();
    for (let i = 0; i < appointments.length; i++) {
      const s = new Date(appointments[i].start_time || appointments[i].starts_at || 0);
      const e = new Date(appointments[i].end_time || appointments[i].ends_at || s.getTime() + 3600000);
      if (now >= s && now <= e) return i;
    }
    for (let i = 0; i < appointments.length; i++) {
      if (new Date(appointments[i].start_time || appointments[i].starts_at || 0) > now) return i;
    }
    return -1;
  }, [appointments]);

  const totalAlerts = priorityAlerts.tasks.length + priorityAlerts.leads.length + priorityAlerts.sla.length;

  if (loading) return <SidebarSkeleton rows={5} />;
  if (error) return <SidebarError message={error} onRetry={fetchAll} />;

  const isToday = !selectedDate || new Date().toDateString() === selectedDate.toDateString();
  const dateLabel = isToday ? 'today' : selectedDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

  return (
    <div className="ops-today-container">
      {/* --- Timeline section --- */}
      {appointments.length === 0 ? (
        <SidebarEmpty icon="&#128197;" title={`No appointments ${dateLabel}`} subtitle="Your schedule is clear" />
      ) : (
        <div className="ops-today-list">
          {appointments.map((appt, idx) => {
            const startKey = appt.start_time || appt.starts_at;
            const endKey = appt.end_time || appt.ends_at;
            const isCurrent = idx === currentIdx && !isPast(endKey);
            const past = isPast(endKey) && !isCurrent;
            const name = appt.client_name || appt.borrower_name || appt.attendee_name || appt.name || 'Client';
            const type = appt.appointment_type_name || appt.type || appt.title || '';
            const mode = appt.meeting_mode || appt.mode || '';

            return (
              <div
                key={appt.id || idx}
                className={`ops-timeline-item${isCurrent ? ' ops-timeline-item--active' : ''}${past ? ' ops-timeline-item--past' : ''}`}
              >
                <div className="ops-timeline-dot" />
                <div className="ops-timeline-time">
                  {formatTime(startKey)} - {formatTime(endKey)}
                </div>
                <div className="ops-timeline-body">
                  <div className="ops-timeline-name">{name}</div>
                  <div className="ops-timeline-meta">
                    {type && <span>{type}</span>}
                    {mode && <span className="ops-timeline-mode">{mode}</span>}
                  </div>
                </div>
                {isCurrent && <span className="ops-timeline-live">NOW</span>}
              </div>
            );
          })}
        </div>
      )}

      {/* --- Priority Alerts section --- */}
      <div className="ops-priority-section">
        <div className="ops-priority-header">Priority Alerts</div>

        {totalAlerts === 0 ? (
          <div className="ops-priority-clear">
            <span className="ops-priority-clear-icon">&#10004;</span>
            <span className="ops-priority-clear-text">All clear — no urgent items</span>
          </div>
        ) : (
          <div className="ops-priority-list">
            {/* Overdue tasks */}
            {priorityAlerts.tasks.map(item => (
              <Link key={`task-${item.id}`} to={item.link} className="ops-priority-item">
                <span className="ops-priority-indicator ops-priority-indicator--red" />
                <span className="ops-priority-icon" title="Overdue task">&#9745;</span>
                <div className="ops-priority-body">
                  <div className="ops-priority-text">{item.text}</div>
                  <div className="ops-priority-detail">
                    {item.detail && <span>{item.detail}</span>}
                    <span className="ops-priority-late">{item.daysLate}d overdue</span>
                  </div>
                </div>
                <span className="ops-priority-category">Tasks</span>
              </Link>
            ))}
            {priorityAlerts.tasks.length > 0 && (
              <button className="ops-priority-viewall" onClick={() => onSwitchTab && onSwitchTab('tasks')}>
                View all tasks &rarr;
              </button>
            )}

            {/* Stale leads */}
            {priorityAlerts.leads.map(item => (
              <Link key={`lead-${item.id}`} to={item.link} className="ops-priority-item">
                <span className="ops-priority-indicator ops-priority-indicator--orange" />
                <span className="ops-priority-icon" title="Lead needs follow-up">&#9733;</span>
                <div className="ops-priority-body">
                  <div className="ops-priority-text">{item.text}</div>
                  <div className="ops-priority-detail">{item.detail}</div>
                </div>
                <span className="ops-priority-category">Leads</span>
              </Link>
            ))}
            {priorityAlerts.leads.length > 0 && (
              <button className="ops-priority-viewall" onClick={() => onSwitchTab && onSwitchTab('leads')}>
                View all leads &rarr;
              </button>
            )}

            {/* SLA breaches */}
            {priorityAlerts.sla.map(item => (
              <Link key={`sla-${item.id}`} to={item.link} className="ops-priority-item">
                <span className="ops-priority-indicator ops-priority-indicator--red" />
                <span className="ops-priority-icon" title="SLA breach">&#9888;</span>
                <div className="ops-priority-body">
                  <div className="ops-priority-text">{item.text}</div>
                  <div className="ops-priority-detail">
                    {item.borrower && <span>{item.borrower}</span>}
                    <span>{item.detail}</span>
                  </div>
                </div>
                <span className="ops-priority-category">SLA</span>
              </Link>
            ))}
            {priorityAlerts.sla.length > 0 && (
              <button className="ops-priority-viewall" onClick={() => onSwitchTab && onSwitchTab('sla')}>
                View all SLA alerts &rarr;
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// =============================================================================
// Tab: Tasks
// =============================================================================

/**
 * TasksTab -- List of tasks due today or within two days, with overdue highlighting.
 *
 * Self-contained: fetches pending tasks from tasksAPI on mount.
 *
 * Used in: OperationalSidebar
 *
 * @returns {React.ReactElement}
 */
function TasksTab() {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await tasksAPI.getAll({ status: 'pending' });
      const all = Array.isArray(data) ? data : [];
      const todayStr = new Date().toISOString().split('T')[0];
      const twoDays = new Date();
      twoDays.setDate(twoDays.getDate() + 2);

      const relevant = all
        .filter(t => {
          if (t.status === 'completed' || t.status === 'cancelled' || !t.due_date) return false;
          return new Date(t.due_date.split('T')[0]) <= twoDays;
        })
        .sort((a, b) => new Date(a.due_date) - new Date(b.due_date))
        .slice(0, 20);
      setTasks(relevant);
    } catch {
      setError('Failed to load tasks');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetch(); }, [fetch]);

  if (loading) return <SidebarSkeleton rows={5} />;
  if (error) return <SidebarError message={error} onRetry={fetch} />;
  if (tasks.length === 0) {
    return <SidebarEmpty icon="&#10003;" title="All caught up!" subtitle="No tasks due" />;
  }

  const todayStr = new Date().toISOString().split('T')[0];

  return (
    <div className="ops-tasks-list">
      {tasks.map(task => {
        const dueStr = (task.due_date || '').split('T')[0];
        const isOverdue = dueStr < todayStr;
        const isDueToday = dueStr === todayStr;

        return (
          <Link key={task.id} to={task.loan_id ? `/loans/${task.loan_id}` : '/tasks'} className="ops-task-item">
            <div className={`ops-task-dot ops-task-dot--${isOverdue ? 'overdue' : isDueToday ? 'today' : 'upcoming'}`} />
            <div className="ops-task-body">
              <div className="ops-task-title">{task.title || task.description || 'Task'}</div>
              <div className="ops-task-meta">
                {task.loan_number && <span>#{task.loan_number}</span>}
                {task.borrower_name && <span>{task.borrower_name}</span>}
              </div>
            </div>
            <div className={`ops-task-badge ops-task-badge--${isOverdue ? 'overdue' : isDueToday ? 'today' : 'upcoming'}`}>
              {isOverdue ? `${Math.abs(daysBetween(dueStr))}d late` : isDueToday ? 'Today' : `${Math.abs(daysBetween(dueStr))}d`}
            </div>
          </Link>
        );
      })}
    </div>
  );
}

// =============================================================================
// Tab: Leads
// =============================================================================

/**
 * LeadsTab -- List of leads needing follow-up (no contact in 3+ days), sorted by staleness.
 *
 * Self-contained: fetches all leads from leadsAPI on mount and filters client-side.
 *
 * Used in: OperationalSidebar
 *
 * @returns {React.ReactElement}
 */
function LeadsTab() {
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await leadsAPI.getAll();
      const all = Array.isArray(data) ? data : [];
      const closed = ['Funded', 'Closed', 'Dead', 'Lost', 'Cancelled', 'Withdrawn'];
      const needsFollowUp = all
        .filter(lead => {
          if (closed.includes(lead.stage)) return false;
          const last = lead.last_contact || lead.last_contacted_at || lead.updated_at;
          const days = daysBetween(last);
          return days === null || days >= 3;
        })
        .sort((a, b) => {
          const ad = daysBetween(a.last_contact || a.last_contacted_at || a.updated_at) || 999;
          const bd = daysBetween(b.last_contact || b.last_contacted_at || b.updated_at) || 999;
          return bd - ad;
        })
        .slice(0, 15);
      setLeads(needsFollowUp);
    } catch {
      setError('Failed to load leads');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetch(); }, [fetch]);

  if (loading) return <SidebarSkeleton rows={5} />;
  if (error) return <SidebarError message={error} onRetry={fetch} />;
  if (leads.length === 0) {
    return <SidebarEmpty icon="&#9734;" title="All leads contacted" subtitle="No follow-ups needed" />;
  }

  return (
    <div className="ops-leads-list">
      {leads.map(lead => {
        const name = lead.first_name && lead.last_name
          ? `${lead.first_name} ${lead.last_name}`
          : lead.first_name || lead.name || 'Unknown';
        const initial = (lead.first_name || lead.name || '?').charAt(0).toUpperCase();
        const last = lead.last_contact || lead.last_contacted_at || lead.updated_at;
        const days = daysBetween(last);
        const daysText = days === null ? 'Never' : days === 0 ? 'Today' : `${days}d ago`;
        const urgent = days === null || days >= 14;

        return (
          <Link key={lead.id} to={`/leads/${lead.id}`} className="ops-lead-item">
            <div className={`ops-lead-avatar${urgent ? ' ops-lead-avatar--urgent' : ''}`}>{initial}</div>
            <div className="ops-lead-body">
              <div className="ops-lead-name">{name}</div>
              <div className="ops-lead-meta">
                <span className={urgent ? 'ops-lead-urgent' : ''}>{daysText}</span>
                {lead.ai_score != null && <span>Score: {lead.ai_score}</span>}
              </div>
            </div>
          </Link>
        );
      })}
    </div>
  );
}

// =============================================================================
// Tab: SLA Alerts
// =============================================================================

/**
 * SLATab -- Loans approaching or exceeding SLA targets, sorted by urgency.
 *
 * Self-contained: fetches all loans from loansAPI, computes days-in-stage vs SLA target,
 * and shows loans within 2 days of or past their SLA deadline.
 *
 * Used in: OperationalSidebar
 *
 * @returns {React.ReactElement}
 */
function SLATab() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await loansAPI.getAll();
      const loans = Array.isArray(data) ? data : [];
      const sla = [];
      for (const loan of loans) {
        const stage = (loan.stage || '').toUpperCase();
        if (TERMINAL.includes(stage)) continue;
        const changed = loan.stage_changed_at || loan.updated_at;
        const days = daysBetween(changed);
        if (days === null) continue;
        const target = SLA_TARGETS[stage] || 7;
        const remaining = target - days;
        if (remaining <= 2) {
          sla.push({
            id: loan.id,
            loan_number: loan.loan_number,
            borrower: loan.borrower_name || loan.borrower || '',
            stage,
            daysIn: days,
            target,
            remaining,
          });
        }
      }
      sla.sort((a, b) => a.remaining - b.remaining);
      setAlerts(sla.slice(0, 15));
    } catch {
      setError('Failed to load SLA data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetch(); }, [fetch]);

  if (loading) return <SidebarSkeleton rows={5} />;
  if (error) return <SidebarError message={error} onRetry={fetch} />;
  if (alerts.length === 0) {
    return <SidebarEmpty icon="&#9989;" title="All loans within SLA" subtitle="No alerts" />;
  }

  return (
    <div className="ops-sla-list">
      {alerts.map(a => {
        const overdue = a.remaining < 0;
        const warn = a.remaining >= 0 && a.remaining <= 1;
        const stageLabel = a.stage.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

        return (
          <Link key={a.id} to={`/loans/${a.id}`} className={`ops-sla-item${overdue ? ' ops-sla-item--critical' : ''}`}>
            <div className={`ops-sla-indicator${overdue ? ' ops-sla-indicator--overdue' : warn ? ' ops-sla-indicator--warn' : ''}`}>
              {a.daysIn}d
            </div>
            <div className="ops-sla-body">
              <div className="ops-sla-loan">{a.loan_number ? `#${a.loan_number}` : 'Loan'}</div>
              {a.borrower && <div className="ops-sla-borrower">{a.borrower}</div>}
              <div className="ops-sla-stage">{stageLabel}</div>
            </div>
            <div className={`ops-sla-badge${overdue ? ' ops-sla-badge--overdue' : warn ? ' ops-sla-badge--warn' : ''}`}>
              {overdue ? `${Math.abs(a.remaining)}d over` : `${a.remaining}d left`}
            </div>
          </Link>
        );
      })}
    </div>
  );
}

// =============================================================================
// Tab: Appointments (existing events list)
// =============================================================================

const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/**
 * AppointmentsTab -- Searchable event list grouped by date, used as the "Events" tab.
 *
 * Unlike other tabs, this one receives its data from the parent (OperationalSidebar)
 * rather than fetching independently.
 *
 * Used in: OperationalSidebar
 *
 * @param {Object} props
 * @param {Array} props.events - Pre-sorted array of calendar events/appointments
 * @param {Function} props.onEventClick - Callback(event) when an appointment row is clicked
 * @param {Function} props.onDeleteEvent - Callback(event) when the delete button is clicked
 * @param {Function} props.formatEventTime - Function(startTime, endTime) => { startStr, duration }
 * @param {string} props.searchQuery - Current search filter string
 * @param {Function} props.onSearchChange - Callback(query) when the search input changes
 * @returns {React.ReactElement}
 */
function AppointmentsTab({ events, onEventClick, onDeleteEvent, formatEventTime, searchQuery, onSearchChange }) {
  const formatDate = useCallback((dateStr) => {
    const d = new Date(dateStr);
    const today = new Date();
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);
    if (d.toDateString() === today.toDateString()) return 'Today';
    if (d.toDateString() === tomorrow.toDateString()) return 'Tomorrow';
    return `${dayNames[d.getDay()]} \u2022 ${monthNames[d.getMonth()]} ${d.getDate()}`;
  }, []);

  return (
    <>
      <div className="ops-appt-search">
        <label htmlFor="ops-event-search" className="sr-only">Search events</label>
        <input
          id="ops-event-search"
          type="text"
          placeholder="Search events..."
          value={searchQuery}
          onChange={e => onSearchChange(e.target.value)}
          className="ops-search-input"
        />
      </div>
      <div className="ops-appt-list">
        {events.length === 0 ? (
          <SidebarEmpty
            icon="&#128197;"
            title={searchQuery ? 'No matching events' : 'No appointments'}
            subtitle={searchQuery ? 'Try a different search' : 'Click + to add one'}
          />
        ) : (
          events.map((event, idx) => {
            const { startStr, duration } = formatEventTime(event.start_time, event.end_time);
            const dateLabel = formatDate(event.start_time);
            const showHeader = idx === 0 || formatDate(events[idx - 1].start_time) !== dateLabel;

            return (
              <div key={event.id}>
                {showHeader && <div className="ops-appt-date-header">{dateLabel}</div>}
                <div
                  className={`ops-appt-item${event.isAppointment ? ' ops-appt-item--clickable' : ''}`}
                  role={event.isAppointment ? 'button' : undefined}
                  tabIndex={event.isAppointment ? 0 : undefined}
                  onClick={() => event.isAppointment && onEventClick(event)}
                  onKeyDown={event.isAppointment ? (e) => {
                    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onEventClick(event); }
                  } : undefined}
                >
                  <div className="ops-appt-time">
                    <span>{startStr}</span>
                    <span className="ops-appt-dur">{duration}m</span>
                  </div>
                  <div className="ops-appt-info">
                    <div className="ops-appt-title">{event.title}</div>
                    {event.attendee_name && <div className="ops-appt-attendee">{event.attendee_name}</div>}
                  </div>
                  <button
                    className="ops-appt-delete"
                    onClick={e => { e.stopPropagation(); onDeleteEvent(event); }}
                    title={event.isAppointment ? 'Cancel' : 'Delete'}
                    aria-label={`Delete ${event.title}`}
                  >
                    &times;
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </>
  );
}

// =============================================================================
// Main Sidebar
// =============================================================================

const SIDEBAR_TABS = [
  { key: 'today', label: 'Today', icon: '\u2630' },
  { key: 'events', label: 'Events', icon: '\uD83D\uDCC5' },
  { key: 'tasks', label: 'Tasks', icon: '\u2611' },
  { key: 'leads', label: 'Leads', icon: '\u2605' },
  { key: 'sla', label: 'SLA', icon: '\u26A0' },
];

/**
 * OperationalSidebar -- Multi-tab sidebar panel providing at-a-glance views of
 * today's schedule, events, tasks, leads needing follow-up, and SLA alerts.
 *
 * Used in: Calendar (main page)
 *
 * @param {Object} props
 * @param {Array} props.sortedEvents - Pre-sorted events array passed through to the Events tab
 * @param {Function} props.onAddClick - Callback() to open the add-appointment modal
 * @param {Function} props.onEventClick - Callback(event) when an appointment is clicked in Events tab
 * @param {Function} props.onDeleteEvent - Callback(event) when delete is clicked in Events tab
 * @param {Function} props.formatEventTime - Function(startTime, endTime) => { startStr, duration }
 * @param {string} props.searchQuery - Current search filter string for Events tab
 * @param {Function} props.onSearchChange - Callback(query) when Events tab search input changes
 * @returns {React.ReactElement}
 *
 * @example
 * <OperationalSidebar
 *   sortedEvents={events}
 *   onAddClick={openModal}
 *   onEventClick={handleEdit}
 *   onDeleteEvent={handleDelete}
 *   formatEventTime={formatFn}
 *   searchQuery={query}
 *   onSearchChange={setQuery}
 * />
 */
const OperationalSidebar = React.memo(function OperationalSidebar({
  // Appointment list props (for events tab)
  sortedEvents,
  onAddClick,
  onEventClick,
  onDeleteEvent,
  formatEventTime,
  searchQuery,
  onSearchChange,
  selectedDate,
}) {
  const [activeTab, setActiveTab] = useState('today');

  useEffect(() => {
    if (selectedDate) setActiveTab('today');
  }, [selectedDate]);

  const renderContent = () => {
    switch (activeTab) {
      case 'today':
        return <TodayTab onSwitchTab={setActiveTab} selectedDate={selectedDate} />;
      case 'events':
        return (
          <AppointmentsTab
            events={sortedEvents}
            onEventClick={onEventClick}
            onDeleteEvent={onDeleteEvent}
            formatEventTime={formatEventTime}
            searchQuery={searchQuery}
            onSearchChange={onSearchChange}
          />
        );
      case 'tasks':
        return <TasksTab />;
      case 'leads':
        return <LeadsTab />;
      case 'sla':
        return <SLATab />;
      default:
        return null;
    }
  };

  const isSelectedToday = !selectedDate || new Date().toDateString() === selectedDate.toDateString();
  const todayLabel = activeTab === 'today' && selectedDate && !isSelectedToday
    ? selectedDate.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
    : SIDEBAR_TABS.find(t => t.key === activeTab)?.label || 'Today';

  return (
    <div className="ops-sidebar" role="complementary" aria-label="Operations panel">
      <div className="ops-sidebar-header">
        <h2 className="ops-sidebar-title">{todayLabel}</h2>
        <button className="ops-add-btn" onClick={onAddClick} title="Add appointment">+ Add</button>
      </div>

      <div className="ops-tabs" role="tablist" aria-label="Sidebar sections">
        {SIDEBAR_TABS.map(tab => (
          <button
            key={tab.key}
            role="tab"
            aria-selected={activeTab === tab.key}
            className={`ops-tab${activeTab === tab.key ? ' ops-tab--active' : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            <span className="ops-tab-icon">{tab.icon}</span>
            <span className="ops-tab-label">{tab.label}</span>
          </button>
        ))}
      </div>

      <div className="ops-content" role="tabpanel">
        {renderContent()}
      </div>
    </div>
  );
});

export default OperationalSidebar;
