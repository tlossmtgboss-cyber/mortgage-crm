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

  const groupedTasks = {
    'Human Needed': tasks.filter((t) => t.type === 'Human Needed'),
    'In Progress': tasks.filter((t) => t.type === 'In Progress'),
    'Awaiting Review': tasks.filter((t) => t.type === 'Awaiting Review'),
    'Completed': tasks.filter((t) => t.type === 'Completed'),
  };

  return (
    <div className="tasks-page">
      <div className="page-header">
        <h1>AI Tasks</h1>
        <p>{tasks.length} total tasks</p>
      </div>

      <div className="tasks-board">
        {Object.entries(groupedTasks).map(([status, statusTasks]) => (
          <div key={status} className="task-column">
            <div className="column-header">
              <h3>{status}</h3>
              <span className="task-count">{statusTasks.length}</span>
            </div>
            <div className="task-list">
              {statusTasks.map((task) => (
                <div key={task.id} className="task-card">
                  <h4>{task.title}</h4>
                  {task.borrower_name && (
                    <p className="borrower">{task.borrower_name}</p>
                  )}
                  {task.ai_confidence && (
                    <div className="confidence">
                      <span>AI Confidence: {task.ai_confidence}%</span>
                    </div>
                  )}
                  <div className="task-footer">
                    <span className={`priority priority-${task.priority}`}>
                      {task.priority}
                    </span>
                    {status !== 'Completed' && (
                      <button
                        className="btn-complete"
                        onClick={() => handleComplete(task)}
                      >
                        Complete
                      </button>
                    )}
                  </div>
                </div>
              ))}
              {statusTasks.length === 0 && (
                <div className="empty-column">No tasks</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default Tasks;
