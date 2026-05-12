import React, { useCallback, useEffect, useMemo, useState } from 'react';

import { posApi } from '../api';
import type { BorrowerTask, BorrowerTaskStatus } from '../types';

import './tasks-page.css';

type FilterKey = 'all' | 'pending' | 'in_progress' | 'completed';

interface TasksPageProps {
  applicationId: string;
  onAskAria?: () => void;
  onBack: () => void;
}

const FILTERS: { key: FilterKey; label: string; pulse?: boolean }[] = [
  { key: 'all', label: 'All Tasks' },
  { key: 'pending', label: 'To Do', pulse: true },
  { key: 'in_progress', label: 'In Progress' },
  { key: 'completed', label: 'Completed' },
];

const PRIORITY_LABELS: Record<string, string> = {
  high: 'High Priority',
  medium: 'Medium',
  low: 'Low Priority',
};

const STATUS_LABELS: Record<BorrowerTaskStatus, string> = {
  pending: 'To Do',
  in_progress: 'In Progress',
  completed: 'Completed',
};

const SECTION_TITLES: Record<BorrowerTaskStatus, string> = {
  pending: 'To Do',
  in_progress: 'In Progress',
  completed: 'Completed',
};

function formatDueDate(iso: string | null): { label: string; urgent: boolean } {
  if (!iso) return { label: '', urgent: false };
  const due = new Date(iso);
  const now = new Date();
  const diffMs = due.getTime() - now.getTime();
  const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays < 0) return { label: `Overdue by ${Math.abs(diffDays)} day${Math.abs(diffDays) !== 1 ? 's' : ''}`, urgent: true };
  if (diffDays === 0) return { label: 'Due today', urgent: true };
  if (diffDays === 1) return { label: 'Due tomorrow', urgent: true };
  if (diffDays <= 3) return { label: `Due in ${diffDays} days`, urgent: true };
  if (diffDays <= 7) return { label: `Due in ${diffDays} days`, urgent: false };
  return { label: `Due ${due.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`, urgent: false };
}

export const TasksPage: React.FC<TasksPageProps> = ({
  applicationId,
  onAskAria,
  onBack,
}) => {
  const [tasks, setTasks] = useState<BorrowerTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FilterKey>('all');
  const [showCompleted, setShowCompleted] = useState(false);
  const [completing, setCompleting] = useState<number | null>(null);

  const loadTasks = useCallback(async () => {
    try {
      const resp = await posApi.getTasks(applicationId, showCompleted);
      setTasks(resp.tasks);
    } catch (err) {
      console.error('Failed to load tasks:', err);
    } finally {
      setLoading(false);
    }
  }, [applicationId, showCompleted]);

  useEffect(() => { loadTasks(); }, [loadTasks]);

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: tasks.length };
    for (const t of tasks) c[t.status] = (c[t.status] || 0) + 1;
    return c;
  }, [tasks]);

  const visible = useMemo(
    () => filter === 'all' ? tasks : tasks.filter(t => t.status === filter),
    [tasks, filter],
  );

  const grouped = useMemo(() => {
    const order: BorrowerTaskStatus[] = ['pending', 'in_progress', 'completed'];
    return order
      .map(s => ({ status: s, items: visible.filter(t => t.status === s) }))
      .filter(g => g.items.length > 0);
  }, [visible]);

  const handleComplete = useCallback(async (taskId: number) => {
    setCompleting(taskId);
    try {
      const updated = await posApi.completeTask(applicationId, taskId);
      setTasks(prev => prev.map(t => t.id === taskId ? { ...t, ...updated } : t));
    } catch (err) {
      console.error('Failed to complete task:', err);
    } finally {
      setCompleting(null);
    }
  }, [applicationId]);

  const pendingCount = counts.pending || 0;
  const inProgressCount = counts.in_progress || 0;
  const completedCount = counts.completed || 0;

  if (loading) {
    return (
      <div className="tasks-page">
        <div className="tasks-page__loading">
          <div className="pos-loading__spinner" />
          <p>Loading tasks...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="tasks-page">
      {/* Back button */}
      <button type="button" className="tasks-page__back" onClick={onBack}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="15 18 9 12 15 6" />
        </svg>
        Back to application
      </button>

      {/* Header */}
      <div className="tasks-page__header">
        <div className="tasks-page__badge-row">
          <span className="tasks-chip">Tasks</span>
        </div>
        <h1 className="tasks-page__title">Your To-Do List</h1>
        <p className="tasks-page__subtitle">
          Items your lending team or the underwriter need you to complete.
          Finish these to keep your loan moving forward.
        </p>
      </div>

      {/* Stats */}
      <div className="tasks-stats">
        <StatCard label="To Do" value={pendingCount} sub={`${pendingCount === 1 ? '1 item' : `${pendingCount} items`} need attention`} variant="pending" />
        <StatCard label="In Progress" value={inProgressCount} sub="Being worked on" variant="progress" />
        <StatCard label="Completed" value={completedCount} sub="Done" variant="completed" />
      </div>

      {/* Aria banner */}
      <div className="tasks-banner">
        <span className="tasks-banner__seal">A</span>
        <div className="tasks-banner__content">
          <div className="tasks-banner__title">Aria tracks your tasks automatically</div>
          <p className="tasks-banner__desc">
            As your loan progresses, new tasks may appear here. Complete them promptly
            to keep things on track — Aria will remind you if a deadline is approaching.
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="tasks-filters" role="tablist">
        {FILTERS.map(f => (
          <button
            key={f.key}
            type="button"
            role="tab"
            aria-selected={filter === f.key}
            className={`tasks-filter${filter === f.key ? ' is-active' : ''}`}
            onClick={() => {
              setFilter(f.key);
              if (f.key === 'completed' && !showCompleted) setShowCompleted(true);
            }}
          >
            {f.pulse && f.key !== filter && pendingCount > 0 && <span className="tasks-filter__pulse" />}
            {f.label}
            <span className="tasks-filter__count">{counts[f.key] || 0}</span>
          </button>
        ))}
      </div>

      {/* Task sections */}
      {grouped.length === 0 ? (
        <div className="tasks-empty">
          <div className="tasks-empty__icon">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 11l3 3L22 4" />
              <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
            </svg>
          </div>
          <h3>You're all caught up!</h3>
          <p>No tasks right now. We'll let you know if anything comes up.</p>
        </div>
      ) : (
        grouped.map(group => (
          <section key={group.status} className="tasks-section">
            <div className="tasks-section__header">
              <h2 className="tasks-section__title">{SECTION_TITLES[group.status]}</h2>
              <span className={`tasks-chip tasks-chip--${group.status}`}>
                {group.items.length} {group.items.length === 1 ? 'item' : 'items'}
              </span>
              <div className="tasks-section__line" />
            </div>

            {group.status === 'completed' ? (
              <div className="tasks-completed-grid">
                {group.items.map(task => (
                  <div key={task.id} className="tasks-completed-row">
                    <div className="tasks-completed-row__icon"><CheckIcon /></div>
                    <div className="tasks-completed-row__main">
                      <p className="tasks-completed-row__title">{task.title}</p>
                      <p className="tasks-completed-row__sub">
                        {task.completed_at
                          ? `Completed ${new Date(task.completed_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`
                          : 'Done'}
                        {task.category ? ` · ${task.category}` : ''}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="tasks-card-list">
                {group.items.map(task => (
                  <TaskCard
                    key={task.id}
                    task={task}
                    onComplete={handleComplete}
                    completing={completing === task.id}
                    onAskAria={onAskAria}
                  />
                ))}
              </div>
            )}
          </section>
        ))
      )}

      {/* Footer */}
      <div className="tasks-page__footer">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
        <span>Questions about a task? Ask Aria or contact your loan officer.</span>
      </div>
    </div>
  );
};

// ---------- Sub-components ----------

const StatCard: React.FC<{
  label: string; value: number; sub: string; variant?: 'pending' | 'progress' | 'completed';
}> = ({ label, value, sub, variant }) => (
  <div className={`tasks-stat${variant ? ` tasks-stat--${variant}` : ''}`}>
    <p className="tasks-stat__label">{label}</p>
    <p className="tasks-stat__value">{value}</p>
    <p className="tasks-stat__sub">{sub}</p>
  </div>
);

const TaskCard: React.FC<{
  task: BorrowerTask;
  onComplete: (id: number) => void;
  completing: boolean;
  onAskAria?: () => void;
}> = ({ task, onComplete, completing, onAskAria }) => {
  const due = formatDueDate(task.due_date);
  const isPending = task.status === 'pending';

  return (
    <article className={`tasks-card${isPending ? ' tasks-card--pending' : ''}${task.priority === 'high' ? ' tasks-card--high' : ''}`}>
      <div className="tasks-card__top">
        <div className="tasks-card__info">
          <h3 className="tasks-card__name">{task.title}</h3>
          {task.description && <p className="tasks-card__desc">{task.description}</p>}
        </div>
        <div className="tasks-card__status-col">
          <span className={`tasks-status-pill tasks-status-pill--${task.status}`}>
            <span className="tasks-status-pill__dot" /> {STATUS_LABELS[task.status]}
          </span>
          {due.label && (
            <span className={`tasks-card__due${due.urgent ? ' tasks-card__due--urgent' : ''}`}>
              {due.label}
            </span>
          )}
          {task.priority === 'high' && (
            <span className="tasks-card__priority">{PRIORITY_LABELS[task.priority]}</span>
          )}
        </div>
      </div>

      {/* Action zone for pending tasks */}
      {isPending && (
        <div className="tasks-action-zone" onClick={() => onComplete(task.id)}>
          <div className="tasks-action-zone__icon">
            {completing ? <span className="tasks-action-zone__spinner" /> : <CheckIcon />}
          </div>
          <div className="tasks-action-zone__text">
            <p className="tasks-action-zone__primary">Mark as complete</p>
            <p className="tasks-action-zone__hint">Click when you've finished this task</p>
          </div>
          <button type="button" className="tasks-action-cta" disabled={completing}>
            {completing ? 'Completing...' : 'Complete'}
          </button>
        </div>
      )}

      {/* In-progress indicator */}
      {task.status === 'in_progress' && (
        <div className="tasks-progress-bar">
          <div className="tasks-progress-bar__body">
            <p className="tasks-progress-bar__label">
              <SparkIcon /> In progress
            </p>
            <div className="tasks-progress-bar__fields">
              {task.category && (
                <div className="tasks-progress-bar__field">
                  <p className="tasks-progress-bar__key">Category</p>
                  <p className="tasks-progress-bar__val">{task.category}</p>
                </div>
              )}
              {due.label && (
                <div className="tasks-progress-bar__field">
                  <p className="tasks-progress-bar__key">Timeline</p>
                  <p className="tasks-progress-bar__val">{due.label}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* AI hint */}
      {isPending && onAskAria && (
        <div className="tasks-ai-hint">
          <SparkIcon />
          <span>
            Not sure what to do?{' '}
            <button type="button" className="tasks-ai-hint__action" onClick={onAskAria}>
              Ask Aria for help
            </button>
          </span>
        </div>
      )}
    </article>
  );
};

// ---------- Icons ----------

const CheckIcon: React.FC = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="20 6 9 17 4 12" />
  </svg>
);

const SparkIcon: React.FC = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" className="tasks-spark">
    <path d="M12 2L13.5 8.5 20 10 13.5 11.5 12 18 10.5 11.5 4 10 10.5 8.5z" />
  </svg>
);
