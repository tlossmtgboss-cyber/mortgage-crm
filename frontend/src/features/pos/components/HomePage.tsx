import React, { useCallback, useEffect, useState } from 'react';

import { posApi } from '../api';
import type {
  ApplicationResponse,
  BookingResponse,
  BorrowerTask,
  BorrowerMessage,
  TeamMember,
} from '../types';

import './home-page.css';

interface HomePageProps {
  application: ApplicationResponse;
  onAskAria?: () => void;
  onNavigate: (view: string) => void;
}

interface Appointment {
  id: number;
  title: string;
  scheduledStart: string;
  scheduledEnd: string;
  loName: string;
  videoLink: string | null;
  icsLink: string | null;
}

const MEETING_LABELS: Record<string, string> = {
  checkin: 'Check-in Call',
  application_review: 'Application Review Call',
  full_consultation: 'Full Consultation',
};

function formatDue(iso: string | null): { label: string; urgent: boolean } {
  if (!iso) return { label: 'No deadline', urgent: false };
  const due = new Date(iso);
  const now = new Date();
  const diffDays = Math.ceil((due.getTime() - now.getTime()) / 86_400_000);

  if (diffDays < 0) return { label: `Overdue by ${Math.abs(diffDays)} day${Math.abs(diffDays) !== 1 ? 's' : ''}`, urgent: true };
  if (diffDays === 0) return { label: 'Due today', urgent: true };
  if (diffDays === 1) return { label: 'Due tomorrow', urgent: true };
  const dateStr = due.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  return { label: `Due ${dateStr} — ${diffDays} days left`, urgent: diffDays <= 3 };
}

function deriveInitials(name: string): string {
  return name.split(' ').map(p => p[0]).filter(Boolean).join('').toUpperCase().slice(0, 2);
}

export const HomePage: React.FC<HomePageProps> = ({
  application,
  onAskAria,
  onNavigate,
}) => {
  const [tasks, setTasks] = useState<BorrowerTask[]>([]);
  const [messages, setMessages] = useState<BorrowerMessage[]>([]);
  const [team, setTeam] = useState<TeamMember[]>([]);
  const [appointment, setAppointment] = useState<Appointment | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!application?.id) return;
    let cancelled = false;

    async function load() {
      try {
        const [taskResp, msgResp, teamResp] = await Promise.all([
          posApi.getTasks(application.id).catch(() => null),
          posApi.getMessages(application.id).catch(() => null),
          posApi.getTeam(application.id).catch(() => null),
        ]);

        if (cancelled) return;

        if (taskResp) {
          const pending = taskResp.tasks
            .filter((t) => t.status !== 'completed')
            .sort((a, b) => {
              const pri: Record<string, number> = { high: 0, medium: 1, low: 2 };
              return (pri[a.priority] ?? 1) - (pri[b.priority] ?? 1);
            });
          setTasks(pending.slice(0, 5));
        }

        if (msgResp) setMessages(msgResp.messages.filter((m) => !m.is_read).slice(0, 3));
        if (teamResp) setTeam(teamResp.members);

        try {
          const calResp = await posApi.getAvailableSlots(application.id, {
            start_date: new Date().toISOString().slice(0, 10),
            end_date: new Date(Date.now() + 30 * 86_400_000).toISOString().slice(0, 10),
          });
          if (!cancelled && calResp.recommended_slot) {
            setAppointment(null);
          }
        } catch (err) {
          console.error('Failed to load calendar slots:', err);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, [application?.id]);

  const handleActionClick = useCallback(
    (task: BorrowerTask) => {
      if (task.category === 'document') {
        onNavigate('documents');
      } else {
        onNavigate('tasks');
      }
    },
    [onNavigate],
  );

  if (loading) {
    return (
      <div className="pos-home">
        <div className="pos-home__loading">Loading your dashboard...</div>
      </div>
    );
  }

  const unread = messages.filter((m) => !m.is_read && !m.is_from_borrower);
  const firstUnread = unread[0];

  return (
    <div className="pos-home">
      {/* ── Priority Banner ── */}
      <div className="pos-home__priority">
        <div className="pos-home__priority-header">
          <h2 className="pos-home__priority-title">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
              <path d="M13.73 21a2 2 0 0 1-3.46 0" />
            </svg>
            Needs your attention
          </h2>
          {tasks.length > 0 && (
            <span className="pos-home__priority-count">
              {tasks.length} item{tasks.length !== 1 ? 's' : ''}
            </span>
          )}
        </div>

        {tasks.length === 0 ? (
          <div className="pos-home__priority-empty">
            You're all caught up — nothing needs your attention right now.
          </div>
        ) : (
          tasks.map((task, i) => {
            const due = formatDue(task.due_date);
            return (
              <div key={task.id} className="pos-home__action-item">
                <div className="pos-home__action-num">{i + 1}</div>
                <div className="pos-home__action-info">
                  <div className="pos-home__action-title">{task.title}</div>
                  <div className={`pos-home__action-due${due.urgent ? ' pos-home__action-due--urgent' : ''}`}>
                    {due.label}
                  </div>
                </div>
                <button
                  type="button"
                  className="pos-home__action-btn"
                  onClick={() => handleActionClick(task)}
                >
                  {task.category === 'document' ? 'Upload Now' : 'Complete'} →
                </button>
              </div>
            );
          })
        )}
      </div>

      {/* ── Next Appointment ── */}
      <div className="pos-home__appointment">
        <div className="pos-home__appointment-header">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
            <line x1="16" y1="2" x2="16" y2="6" />
            <line x1="8" y1="2" x2="8" y2="6" />
            <line x1="3" y1="10" x2="21" y2="10" />
          </svg>
          Next Appointment
        </div>

        {appointment ? (
          <div className="pos-home__appointment-body">
            <div className="pos-home__appointment-detail">
              <div className="pos-home__appt-date">
                <span className="pos-home__appt-month">
                  {new Date(appointment.scheduledStart).toLocaleDateString(undefined, { month: 'short' })}
                </span>
                <span className="pos-home__appt-day">
                  {new Date(appointment.scheduledStart).getDate()}
                </span>
              </div>
              <div>
                <div className="pos-home__appt-title">{appointment.title}</div>
                <div className="pos-home__appt-sub">
                  {new Date(appointment.scheduledStart).toLocaleDateString(undefined, { weekday: 'long' })}
                  {' · '}
                  {new Date(appointment.scheduledStart).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}
                  {' – '}
                  {new Date(appointment.scheduledEnd).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}
                  {appointment.loName ? ` · with ${appointment.loName}` : ''}
                </div>
              </div>
            </div>
            <div className="pos-home__appt-actions">
              {appointment.icsLink && (
                <a href={appointment.icsLink} className="pos-home__appt-btn" download>
                  Add to Calendar
                </a>
              )}
              {appointment.videoLink && (
                <a href={appointment.videoLink} className="pos-home__appt-btn pos-home__appt-btn--primary" target="_blank" rel="noopener noreferrer">
                  Join Call
                </a>
              )}
            </div>
          </div>
        ) : (
          <div className="pos-home__no-appointment">
            <p>No upcoming appointments scheduled.</p>
            <button
              type="button"
              className="pos-home__book-btn"
              onClick={onAskAria}
            >
              Schedule with Aria
            </button>
          </div>
        )}
      </div>

      {/* ── Bottom Grid: Loan + Team ── */}
      <div className="pos-home__grid">
        {/* Loan Summary */}
        <div className="pos-home__card">
          <div className="pos-home__card-header">
            <span>Your Loan</span>
          </div>
          <div className="pos-home__loan-grid">
            <div>
              <div className="pos-home__loan-label">Status</div>
              <div className="pos-home__loan-value--sm">
                {application.status === 'submitted' ? 'Submitted' : 'In Progress'}
              </div>
            </div>
            <div>
              <div className="pos-home__loan-label">Progress</div>
              <div className="pos-home__loan-value">{application.completion_pct}%</div>
            </div>
            <div>
              <div className="pos-home__loan-label">Application</div>
              <div className="pos-home__loan-value--sm">
                {application.submitted_at
                  ? `Submitted ${new Date(application.submitted_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`
                  : 'Draft'
                }
              </div>
            </div>
          </div>
          <div style={{ paddingTop: 12 }}>
            <button
              type="button"
              className="pos-home__action-btn"
              onClick={() => onNavigate('application')}
              style={{ width: '100%', textAlign: 'center' }}
            >
              {application.status === 'submitted' ? 'View Application' : 'Continue Application'} →
            </button>
          </div>
        </div>

        {/* Team + Messages */}
        <div className="pos-home__card">
          <div className="pos-home__card-header">
            <span>Your Team</span>
            <button
              type="button"
              className="pos-home__card-link"
              onClick={() => onNavigate('team')}
            >
              View all
            </button>
          </div>
          {team.slice(0, 2).map((m) => (
            <div key={m.user_id} className="pos-home__team-member">
              <div className="pos-home__tm-avatar">{deriveInitials(m.name)}</div>
              <div>
                <div className="pos-home__tm-name">{m.name}</div>
                <div className="pos-home__tm-role">{m.title || m.role}</div>
                {m.phone && <div className="pos-home__tm-phone">{m.phone}</div>}
              </div>
            </div>
          ))}

          {firstUnread && (
            <div
              className="pos-home__unread-teaser"
              onClick={() => onNavigate('messages')}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && onNavigate('messages')}
            >
              <div className="pos-home__unread-avatar">
                {deriveInitials(firstUnread.sender_name)}
              </div>
              <div>
                <div className="pos-home__unread-sender">
                  {unread.length} unread message{unread.length !== 1 ? 's' : ''} from {firstUnread.sender_name}
                </div>
                <div className="pos-home__unread-preview">
                  "{firstUnread.content.slice(0, 60)}{firstUnread.content.length > 60 ? '...' : ''}"
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
