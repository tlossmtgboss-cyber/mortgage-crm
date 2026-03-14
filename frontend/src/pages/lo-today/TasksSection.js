import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { tasksAPI } from '../../services/api';
import { daysBetween, LoadingSkeleton } from './helpers';

// =============================================================================
// Section 2: Pipeline Tasks Due
// =============================================================================

export function TasksSection() {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchTasks = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await tasksAPI.getAll({ status: 'pending' });
      const allTasks = Array.isArray(data) ? data : [];

      // Filter to tasks due today or overdue, then sort: overdue first, then today, then upcoming
      const now = new Date();
      const todayStr = now.toISOString().split('T')[0];

      const relevant = allTasks
        .filter((t) => {
          if (t.status === 'completed' || t.status === 'cancelled') return false;
          if (!t.due_date) return false;
          const dueStr = typeof t.due_date === 'string' ? t.due_date.split('T')[0] : '';
          // Include if due today, overdue, or due within next 2 days
          const dueDate = new Date(dueStr);
          const twoDaysFromNow = new Date(now);
          twoDaysFromNow.setDate(twoDaysFromNow.getDate() + 2);
          return dueDate <= twoDaysFromNow;
        })
        .sort((a, b) => new Date(a.due_date) - new Date(b.due_date))
        .slice(0, 15);

      setTasks(relevant);
    } catch (err) {
      console.error('Failed to fetch tasks:', err);
      setError(err.message || 'Failed to load tasks');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  const overdueCount = useMemo(() => {
    const todayStr = new Date().toISOString().split('T')[0];
    return tasks.filter((t) => {
      const dueStr = (t.due_date || '').split('T')[0];
      return dueStr < todayStr;
    }).length;
  }, [tasks]);

  function getTaskPriority(task) {
    const todayStr = new Date().toISOString().split('T')[0];
    const dueStr = (task.due_date || '').split('T')[0];
    if (dueStr < todayStr) return 'overdue';
    if (dueStr === todayStr) return 'today';
    return 'upcoming';
  }

  function getSlaLabel(task) {
    const todayStr = new Date().toISOString().split('T')[0];
    const dueStr = (task.due_date || '').split('T')[0];
    const days = daysBetween(dueStr);
    if (days === null) return null;
    if (dueStr < todayStr) return { text: `${Math.abs(days)}d overdue`, className: 'lo-today__task-sla--overdue' };
    if (dueStr === todayStr) return { text: 'Due today', className: 'lo-today__task-sla--warning' };
    return { text: `${Math.abs(days)}d left`, className: 'lo-today__task-sla--ok' };
  }

  return (
    <div className="lo-today__section">
      <div className="lo-today__section-header">
        <h2 className="lo-today__section-title">
          Pipeline Tasks
          {overdueCount > 0 && (
            <span className="lo-today__section-badge lo-today__section-badge--danger">{overdueCount}</span>
          )}
        </h2>
        <Link to="/tasks" style={{ fontSize: 13, color: '#3b82f6', textDecoration: 'none' }}>
          All Tasks
        </Link>
      </div>
      <div className="lo-today__section-body">
        {loading ? (
          <LoadingSkeleton rows={4} />
        ) : error ? (
          <div className="lo-today__error">
            <p>{error}</p>
            <button className="lo-today__retry-btn" onClick={fetchTasks}>Retry</button>
          </div>
        ) : tasks.length === 0 ? (
          <div className="lo-today__empty">
            <div className="lo-today__empty-icon">&#10003;</div>
            <div>All caught up!</div>
            <div style={{ fontSize: 12, marginTop: 4 }}>No tasks due today</div>
          </div>
        ) : (
          tasks.map((task) => {
            const priority = getTaskPriority(task);
            const sla = getSlaLabel(task);
            return (
              <div key={task.id} className="lo-today__task-item">
                <div className={`lo-today__task-priority lo-today__task-priority--${priority}`} />
                <div className="lo-today__task-content">
                  <div className="lo-today__task-desc">
                    {task.title || task.description || 'Untitled task'}
                  </div>
                  <div className="lo-today__task-meta">
                    {task.loan_number && <span>Loan #{task.loan_number}</span>}
                    {task.borrower_name && <span>{task.borrower_name}</span>}
                    {sla && (
                      <span className={`lo-today__task-sla ${sla.className}`}>{sla.text}</span>
                    )}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

export default TasksSection;
