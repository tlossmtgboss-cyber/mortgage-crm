import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { tasksAPI } from '../../services/api';
import { toast } from '../../utils/toast';
import AriaTabNav from '../../components/mobile/AriaTabNav';
import PullToRefreshContainer from '../../components/mobile/PullToRefreshContainer';
import './MobileTasks.css';

// ============================================================================
// Helpers
// ============================================================================

function toDateStr(d) {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function formatDueDate(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr + 'T00:00:00');
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `Due ${months[d.getMonth()]} ${d.getDate()}`;
}

function classifyTask(task, todayStr) {
  const dueDate = (task.due_date || '').slice(0, 10);
  if (!dueDate) return 'upcoming';
  if (dueDate < todayStr && !task.is_completed) return 'overdue';
  if (dueDate === todayStr) return 'today';
  if (dueDate > todayStr) return 'upcoming';
  // Past + completed
  return 'today';
}

// ============================================================================
// Checkbox SVG
// ============================================================================

function CheckIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
      <path d="M2.5 6.5L5 9L9.5 3.5" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// ============================================================================
// TaskCard
// ============================================================================

function TaskCard({ task, todayStr, onToggle }) {
  const done = task.is_completed;
  const dueDate = (task.due_date || '').slice(0, 10);
  const isOverdue = dueDate && dueDate < todayStr && !done;
  const name = task.title || task.task_name || 'Untitled task';
  const category = task.category || task.task_type || '';

  let badgeClass = 'mt-badge-yellow';
  let badgeLabel = 'Pending';
  if (done) {
    badgeClass = 'mt-badge-green';
    badgeLabel = 'Done';
  } else if (isOverdue) {
    badgeClass = 'mt-badge-red';
    badgeLabel = 'Overdue';
  } else if (category) {
    badgeClass = 'mt-badge-blue';
    badgeLabel = category;
  }

  const subtitle = [
    dueDate ? formatDueDate(dueDate) : null,
    category && !done && !isOverdue ? null : category || null,
  ].filter(Boolean).join(' \u00b7 ');

  return (
    <div className={`mt-task-card ${done ? 'mt-task-card--done' : ''}`}>
      <button
        className={`mt-checkbox ${done ? 'mt-checkbox--checked' : ''}`}
        onClick={() => onToggle(task)}
        type="button"
        role="checkbox"
        aria-checked={done}
        aria-label={`${name}: ${done ? 'Mark incomplete' : 'Mark complete'}`}
      >
        {done && <CheckIcon />}
      </button>

      <div className="mt-task-info">
        <span className={`mt-task-name ${done ? 'mt-task-name--done' : ''}`}>
          {name}
        </span>
        {subtitle && (
          <span className="mt-task-subtitle">{subtitle}</span>
        )}
      </div>

      <span className={`mt-badge ${badgeClass}`}>{badgeLabel}</span>
    </div>
  );
}

// ============================================================================
// Section
// ============================================================================

function TaskSection({ label, tasks, todayStr, onToggle }) {
  if (!tasks || tasks.length === 0) return null;
  return (
    <div className="mt-section">
      <div className="mt-section-label">{label}</div>
      <div className="mt-section-cards">
        {tasks.map((task) => (
          <TaskCard
            key={task.id}
            task={task}
            todayStr={todayStr}
            onToggle={onToggle}
          />
        ))}
      </div>
    </div>
  );
}

// ============================================================================
// MobileTasks
// ============================================================================

const PAGE_SIZE = 20;

export default function MobileTasks() {
  const navigate = useNavigate();
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const todayStr = useMemo(() => toDateStr(new Date()), []);

  // ---------- Fetch tasks (initial + paginated) ----------
  const fetchTasks = useCallback(async (pageNum, append = false) => {
    try {
      const data = await tasksAPI.getAll({
        limit: PAGE_SIZE,
        offset: pageNum * PAGE_SIZE,
      });
      const list = Array.isArray(data) ? data : (data?.tasks || []);
      if (append) {
        setTasks((prev) => [...prev, ...list]);
      } else {
        setTasks(list);
      }
      if (list.length < PAGE_SIZE) {
        setHasMore(false);
      }
    } catch (err) {
      if (!append) {
        toast.error('Failed to load tasks');
      } else {
        toast.error('Failed to load more tasks');
      }
    }
  }, []);

  // ---------- Initial load ----------
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const data = await tasksAPI.getAll({ limit: PAGE_SIZE, offset: 0 });
        if (!cancelled) {
          const list = Array.isArray(data) ? data : (data?.tasks || []);
          setTasks(list);
          if (list.length < PAGE_SIZE) setHasMore(false);
        }
      } catch (err) {
        if (!cancelled) {
          toast.error('Failed to load tasks');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  // ---------- Load more ----------
  const handleLoadMore = useCallback(async () => {
    if (loadingMore || !hasMore) return;
    setLoadingMore(true);
    const nextPage = page + 1;
    try {
      await fetchTasks(nextPage, true);
      setPage(nextPage);
    } finally {
      setLoadingMore(false);
    }
  }, [page, loadingMore, hasMore, fetchTasks]);

  // ---------- Pull-to-refresh ----------
  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      setPage(0);
      setHasMore(true);
      await fetchTasks(0, false);
    } finally {
      setRefreshing(false);
    }
  }, [fetchTasks]);

  // ---------- Group tasks ----------
  const { overdue, today, upcoming } = useMemo(() => {
    const groups = { overdue: [], today: [], upcoming: [] };
    for (const task of tasks) {
      const bucket = classifyTask(task, todayStr);
      if (groups[bucket]) {
        groups[bucket].push(task);
      }
    }
    // Sort each group by due_date ascending
    const sortByDate = (a, b) => (a.due_date || '').localeCompare(b.due_date || '');
    groups.overdue.sort(sortByDate);
    groups.today.sort(sortByDate);
    groups.upcoming.sort(sortByDate);
    return groups;
  }, [tasks, todayStr]);

  // ---------- Summary ----------
  const dueToday = today.filter((t) => !t.is_completed).length;
  const overdueCount = overdue.length;

  // ---------- Toggle completion ----------
  const handleToggle = useCallback(async (task) => {
    const newCompleted = !task.is_completed;

    // Optimistic update
    setTasks((prev) =>
      prev.map((t) =>
        t.id === task.id ? { ...t, is_completed: newCompleted } : t
      )
    );

    try {
      await tasksAPI.update(task.id, { is_completed: newCompleted });
    } catch (err) {
      // Revert
      setTasks((prev) =>
        prev.map((t) =>
          t.id === task.id ? { ...t, is_completed: task.is_completed } : t
        )
      );
      toast.error('Failed to update task');
    }
  }, []);

  return (
    <div className="mt-page">
      {/* Header */}
      <header className="mt-header">
        <h1 className="mt-header-title">Tasks</h1>
        <p className="mt-header-summary">
          {loading
            ? 'Loading...'
            : `${dueToday} due today \u00b7 ${overdueCount} overdue`}
        </p>
      </header>

      {/* Body */}
      <PullToRefreshContainer onRefresh={handleRefresh} className="mt-body">
        {loading && (
          <div className="mt-loading">
            <div className="mt-spinner" />
          </div>
        )}

        {!loading && tasks.length === 0 && (
          <div className="mt-empty">
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" style={{ marginBottom: 12 }}>
              <rect x="8" y="8" width="32" height="32" rx="6" stroke="#ccc" strokeWidth="2" />
              <path d="M16 24l5 5L32 18" stroke="#ccc" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <p className="mt-empty-text">No tasks yet</p>
          </div>
        )}

        {!loading && tasks.length > 0 && (
          <>
            <TaskSection label="Overdue" tasks={overdue} todayStr={todayStr} onToggle={handleToggle} />
            <TaskSection label="Today" tasks={today} todayStr={todayStr} onToggle={handleToggle} />
            <TaskSection label="Upcoming" tasks={upcoming} todayStr={todayStr} onToggle={handleToggle} />

            {hasMore && (
              <div className="mt-load-more-wrap">
                <button
                  className="mt-load-more-btn"
                  onClick={handleLoadMore}
                  disabled={loadingMore}
                  type="button"
                >
                  {loadingMore ? (
                    <span className="mt-load-more-spinner" />
                  ) : (
                    'Load more'
                  )}
                </button>
              </div>
            )}
          </>
        )}
      </PullToRefreshContainer>

      {/* Bottom nav */}
      <AriaTabNav
        variant="light"
        activeTab="tasks"
        showFab={true}
        onFabPress={() => navigate('/tasks')}
      />
    </div>
  );
}
