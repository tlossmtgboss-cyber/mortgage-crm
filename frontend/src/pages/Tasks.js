import React, { useState, useEffect } from 'react';
import { tasksAPI } from '../services/api';
import './Tasks.css';

function Tasks() {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadTasks();
  }, []);

  const loadTasks = async () => {
    try {
      const data = await tasksAPI.getAll();
      setTasks(data);
    } catch (err) {
      console.error('Failed to load tasks:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleComplete = async (task) => {
    try {
      await tasksAPI.update(task.id, { type: 'Completed' });
      loadTasks();
    } catch (err) {
      console.error('Failed to update task:', err);
    }
  };

  if (loading) return <div className="loading">Loading tasks...</div>;

  const outstandingTasks = tasks.filter((t) => t.type !== 'Completed');
  const completedTasks = tasks.filter((t) => t.type === 'Completed');

  return (
    <div className="tasks-page">
      <div className="page-header">
        <h1>Tasks</h1>
        <p>{tasks.length} total tasks</p>
      </div>

      <div className="tasks-sections">
        <div className="task-section">
          <div className="section-header">
            <h2>Outstanding Tasks</h2>
            <span className="task-count">{outstandingTasks.length}</span>
          </div>
          <div className="task-list">
            {outstandingTasks.map((task) => (
              <div key={task.id} className="task-item">
                <div className="task-main">
                  <h4>{task.title}</h4>
                  {task.borrower_name && (
                    <p className="task-client">Client: {task.borrower_name}</p>
                  )}
                  <div className="task-meta">
                    {task.due_date && (
                      <span className="due-date">Due: {new Date(task.due_date).toLocaleDateString()}</span>
                    )}
                    {task.ai_can_complete && (
                      <span className="ai-badge">AI Can Complete</span>
                    )}
                  </div>
                </div>
                <div className="task-actions">
                  <button
                    className="btn-complete"
                    onClick={() => handleComplete(task)}
                  >
                    Complete
                  </button>
                </div>
              </div>
            ))}
            {outstandingTasks.length === 0 && (
              <div className="empty-state">
                <p>No outstanding tasks</p>
              </div>
            )}
          </div>
        </div>

        <div className="task-section">
          <div className="section-header">
            <h2>Completed Tasks</h2>
            <span className="task-count">{completedTasks.length}</span>
          </div>
          <div className="task-list">
            {completedTasks.map((task) => (
              <div key={task.id} className="task-item completed">
                <div className="task-main">
                  <h4>{task.title}</h4>
                  {task.borrower_name && (
                    <p className="task-client">Client: {task.borrower_name}</p>
                  )}
                  <div className="task-meta">
                    {task.completed_at && (
                      <span className="completed-date">
                        Completed: {new Date(task.completed_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
            {completedTasks.length === 0 && (
              <div className="empty-state">
                <p>No completed tasks</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default Tasks;
