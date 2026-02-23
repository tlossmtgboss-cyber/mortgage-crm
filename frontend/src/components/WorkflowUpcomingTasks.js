import React, { useState, useEffect, useCallback } from 'react';
import './WorkflowUpcomingTasks.css';

const API_BASE = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

// Get next 7 business days
const getNext7BusinessDays = () => {
  const days = [];
  const today = new Date();
  let count = 0;
  let current = new Date(today);

  while (count < 7) {
    const dayOfWeek = current.getDay();
    if (dayOfWeek !== 0 && dayOfWeek !== 6) { // Skip weekends
      days.push(new Date(current));
      count++;
    }
    current.setDate(current.getDate() + 1);
  }

  return days;
};

// Format date for display
const formatDate = (date) => {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const compareDate = new Date(date);
  compareDate.setHours(0, 0, 0, 0);

  const diffDays = Math.floor((compareDate - today) / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Tomorrow';

  return date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
};

// Priority colors
const getPriorityColor = (priority) => {
  switch (priority) {
    case 'urgent': return '#ef4444';
    case 'high': return '#f59e0b';
    case 'medium': return '#3b82f6';
    case 'low': return '#10b981';
    default: return '#6b7280';
  }
};

function WorkflowUpcomingTasks({ workflowKey, workflowName, workflowColor }) {
  const [loading, setLoading] = useState(true);
  const [tasksByDay, setTasksByDay] = useState({});
  const [userCapacity, setUserCapacity] = useState([]);
  const [selectedUser, setSelectedUser] = useState(null);
  const [viewMode, setViewMode] = useState('calendar'); // 'calendar' or 'capacity'
  const [totalTasks, setTotalTasks] = useState(0);
  const [showAllTasks, setShowAllTasks] = useState(false);
  const [expandedDays, setExpandedDays] = useState({});

  const toggleDayExpand = (dateKey) => {
    setExpandedDays(prev => ({
      ...prev,
      [dateKey]: !prev[dateKey]
    }));
  };

  const businessDays = getNext7BusinessDays();

  const fetchUpcomingTasks = useCallback(async (getAllTasks = false) => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const headers = { 'Authorization': `Bearer ${token}` };

      // Fetch from appropriate endpoint
      const endpoint = getAllTasks
        ? `${API_BASE}/api/v1/workflow/upcoming-tasks-all`
        : `${API_BASE}/api/v1/workflow/upcoming-tasks/${workflowKey}`;

      const response = await fetch(endpoint, { headers });

      if (response.ok) {
        const data = await response.json();
        setTasksByDay(data.tasks_by_day || {});
        setUserCapacity(data.user_capacity || []);
        setTotalTasks(data.total_tasks || 0);
      } else {
        // Set empty state if API returns error
        setEmptyState();
      }
    } catch (error) {
      console.error('Error fetching upcoming tasks:', error);
      setEmptyState();
    } finally {
      setLoading(false);
    }
  }, [workflowKey]);

  const setEmptyState = () => {
    // Set empty state when no tasks are found for this workflow
    setTasksByDay({});
    setUserCapacity([]);
    setTotalTasks(0);
  };

  const handleGetAllTasks = () => {
    setShowAllTasks(true);
    fetchUpcomingTasks(true);
  };

  const handleGetStageTasks = () => {
    setShowAllTasks(false);
    fetchUpcomingTasks(false);
  };

  useEffect(() => {
    fetchUpcomingTasks();
  }, [fetchUpcomingTasks]);

  if (loading) {
    return <div className="upcoming-tasks-loading">Loading upcoming tasks...</div>;
  }

  return (
    <div className="workflow-upcoming-tasks">
      {/* Header */}
      <div className="upcoming-header">
        <div className="header-info">
          <h3 style={{ color: workflowColor }}>
            {showAllTasks ? 'All Upcoming Tasks' : `${workflowName} - Upcoming Tasks`}
          </h3>
          <p className="header-subtitle">Next 7 business days • {totalTasks} total tasks</p>
        </div>
        <div className="header-actions">
          <div className="task-filter-toggle">
            <button
              className={`filter-btn ${!showAllTasks ? 'active' : ''}`}
              onClick={handleGetStageTasks}
            >
              {workflowName} Only
            </button>
            <button
              className={`filter-btn get-tasks-btn ${showAllTasks ? 'active' : ''}`}
              onClick={handleGetAllTasks}
            >
              Get All Tasks
            </button>
          </div>
          <div className="view-toggle">
            <button
              className={viewMode === 'calendar' ? 'active' : ''}
              onClick={() => setViewMode('calendar')}
            >
              📅 Calendar View
            </button>
            <button
              className={viewMode === 'capacity' ? 'active' : ''}
              onClick={() => setViewMode('capacity')}
            >
              📊 Capacity View
            </button>
          </div>
        </div>
      </div>

      {viewMode === 'calendar' ? (
        /* Calendar View - Tasks by Day */
        <div className="calendar-view">
          <div className="days-grid">
            {businessDays.map(day => {
              const dateKey = day.toISOString().split('T')[0];
              const dayTasks = tasksByDay[dateKey] || [];
              const isToday = formatDate(day) === 'Today';
              const isExpanded = expandedDays[dateKey];
              const displayTasks = isExpanded ? dayTasks : dayTasks.slice(0, 8);

              return (
                <div key={dateKey} className={`day-column ${isToday ? 'today' : ''} ${isExpanded ? 'expanded' : ''}`}>
                  <div className="day-header">
                    <span className="day-name">{formatDate(day)}</span>
                    <span className="task-count">{dayTasks.length} tasks</span>
                  </div>
                  <div className={`day-tasks ${isExpanded ? 'expanded' : ''}`}>
                    {displayTasks.map(task => (
                      <div
                        key={task.id}
                        className="task-card-mini"
                        style={{ borderLeftColor: getPriorityColor(task.priority) }}
                      >
                        <div className="task-mini-header">
                          <span className="task-time">{task.dueTime}</span>
                          <span className="task-duration">{task.estimatedMinutes}m</span>
                        </div>
                        <div className="task-mini-title">{task.title}</div>
                        <div className="task-mini-client">{task.clientName}</div>
                        <div className="task-mini-assignee">
                          <span className="assignee-avatar">
                            {(task.assignedTo?.name || '?').split(' ').map(n => n[0]).join('')}
                          </span>
                          <span className="assignee-name">{(task.assignedTo?.name || '').split(' ')[0]}</span>
                        </div>
                      </div>
                    ))}
                    {dayTasks.length > 8 && (
                      <div className="more-tasks" onClick={() => toggleDayExpand(dateKey)}>
                        {isExpanded ? 'Show less' : `+${dayTasks.length - 8} more`}
                      </div>
                    )}
                    {dayTasks.length === 0 && (
                      <div className="no-tasks">No tasks scheduled</div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        /* Capacity View - User workload */
        <div className="capacity-view">
          {/* Capacity Summary */}
          <div className="capacity-summary">
            <div className="summary-card">
              <div className="summary-value">{totalTasks}</div>
              <div className="summary-label">Total Tasks (7 Days)</div>
            </div>
            <div className="summary-card">
              <div className="summary-value">{Math.round(totalTasks / 7)}</div>
              <div className="summary-label">Avg Daily Tasks</div>
            </div>
            <div className="summary-card">
              <div className="summary-value">{userCapacity.filter(u => u.overCapacity).length}</div>
              <div className="summary-label">Users Over Capacity</div>
            </div>
            <div className="summary-card">
              <div className="summary-value">
                {userCapacity.reduce((sum, u) => sum + u.completedToday, 0)}
              </div>
              <div className="summary-label">Completed Today</div>
            </div>
          </div>

          {/* User Capacity Table */}
          <div className="capacity-table-container">
            <table className="capacity-table">
              <thead>
                <tr>
                  <th>Team Member</th>
                  <th>Role</th>
                  <th>Daily Capacity</th>
                  <th>Assigned (7 Days)</th>
                  <th>Avg/Day</th>
                  <th>Today Done</th>
                  <th>Week Done</th>
                  <th>Utilization</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {userCapacity.map(user => (
                  <tr
                    key={user.id}
                    className={`${user.overCapacity ? 'over-capacity' : ''} ${selectedUser?.id === user.id ? 'selected' : ''}`}
                    onClick={() => setSelectedUser(selectedUser?.id === user.id ? null : user)}
                  >
                    <td>
                      <div className="user-cell">
                        <span className="user-avatar">
                          {(user.name || '?').split(' ').map(n => n[0]).join('')}
                        </span>
                        <span className="user-name">{user.name}</span>
                      </div>
                    </td>
                    <td>{user.role}</td>
                    <td>{user.avgDailyCapacity}</td>
                    <td>{user.totalAssigned}</td>
                    <td className={parseFloat(user.avgDailyAssigned) > user.avgDailyCapacity ? 'warning' : ''}>
                      {user.avgDailyAssigned}
                    </td>
                    <td className="completed">{user.completedToday}</td>
                    <td className="completed">{user.completedThisWeek}</td>
                    <td>
                      <div className="utilization-bar">
                        <div
                          className="utilization-fill"
                          style={{
                            width: `${Math.min(100, user.capacityUtilization)}%`,
                            backgroundColor: user.capacityUtilization > 100 ? '#ef4444' :
                                           user.capacityUtilization > 80 ? '#f59e0b' : '#10b981'
                          }}
                        />
                        <span className="utilization-text">{user.capacityUtilization}%</span>
                      </div>
                    </td>
                    <td>
                      <button className="expand-btn">
                        {selectedUser?.id === user.id ? '▲' : '▼'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Selected User Detail */}
          {selectedUser && (
            <div className="user-detail-panel">
              <div className="detail-header">
                <h4>{selectedUser.name} - Daily Breakdown</h4>
                <button className="close-detail" onClick={() => setSelectedUser(null)}>×</button>
              </div>
              <div className="daily-breakdown">
                {selectedUser.dailyTasks.map((day, idx) => {
                  const date = new Date(day.date);
                  const isOverCapacity = day.assigned > selectedUser.avgDailyCapacity;

                  return (
                    <div key={day.date} className={`day-bar ${isOverCapacity ? 'over' : ''}`}>
                      <div className="day-label">{formatDate(date)}</div>
                      <div className="bar-container">
                        <div
                          className="bar-fill"
                          style={{
                            height: `${Math.min(100, (day.assigned / selectedUser.avgDailyCapacity) * 100)}%`,
                            backgroundColor: isOverCapacity ? '#ef4444' : '#3b82f6'
                          }}
                        />
                        <div
                          className="capacity-line"
                          style={{ bottom: '100%' }}
                        />
                      </div>
                      <div className="day-tasks-count">{day.assigned}</div>
                      <div className="day-hours">{day.estimatedHours.toFixed(1)}h</div>
                    </div>
                  );
                })}
              </div>
              <div className="detail-summary">
                <div className="detail-stat">
                  <span className="stat-label">Avg Daily Capacity:</span>
                  <span className="stat-value">{selectedUser.avgDailyCapacity} tasks</span>
                </div>
                <div className="detail-stat">
                  <span className="stat-label">This Week Assigned:</span>
                  <span className="stat-value">{selectedUser.totalAssigned} tasks</span>
                </div>
                <div className="detail-stat">
                  <span className="stat-label">This Week Completed:</span>
                  <span className="stat-value">{selectedUser.completedThisWeek} tasks</span>
                </div>
                <div className="detail-stat">
                  <span className="stat-label">Completion Rate:</span>
                  <span className="stat-value">
                    {selectedUser.totalAssigned > 0
                      ? Math.round((selectedUser.completedThisWeek / selectedUser.totalAssigned) * 100)
                      : 0}%
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default WorkflowUpcomingTasks;
