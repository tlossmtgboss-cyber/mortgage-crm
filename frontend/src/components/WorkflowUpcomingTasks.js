import React, { useState, useEffect, useCallback } from 'react';
import './WorkflowUpcomingTasks.css';

const API_BASE = process.env.REACT_APP_API_URL || 'https://mortgage-crm-production-7a9a.up.railway.app';

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

  const businessDays = getNext7BusinessDays();

  const fetchUpcomingTasks = useCallback(async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const headers = { 'Authorization': `Bearer ${token}` };

      // Try to fetch from API
      const response = await fetch(
        `${API_BASE}/api/v1/workflow/upcoming-tasks/${workflowKey}`,
        { headers }
      );

      if (response.ok) {
        const data = await response.json();
        setTasksByDay(data.tasks_by_day || {});
        setUserCapacity(data.user_capacity || []);
        setTotalTasks(data.total_tasks || 0);
      } else {
        // Generate mock data for demo
        generateMockData();
      }
    } catch (error) {
      console.error('Error fetching upcoming tasks:', error);
      generateMockData();
    } finally {
      setLoading(false);
    }
  }, [workflowKey]);

  const generateMockData = () => {
    const users = [
      { id: 1, name: 'Sarah Johnson', role: 'Loan Officer', avgDailyCapacity: 15 },
      { id: 2, name: 'Mike Chen', role: 'Processor', avgDailyCapacity: 20 },
      { id: 3, name: 'Emily Davis', role: 'Jr. Loan Officer', avgDailyCapacity: 12 },
      { id: 4, name: 'David Wilson', role: 'Production Assistant', avgDailyCapacity: 25 },
      { id: 5, name: 'Lisa Brown', role: 'Concierge', avgDailyCapacity: 18 }
    ];

    const taskTypes = [
      'Initial Contact Call',
      'Send Follow-up Email',
      'Document Collection',
      'Credit Review',
      'Rate Lock Reminder',
      'Application Review',
      'Disclosure Delivery',
      'Appraisal Follow-up',
      'Condition Clearing',
      'Closing Prep'
    ];

    const clients = [
      'John Smith', 'Maria Garcia', 'Robert Lee', 'Jennifer Williams',
      'Michael Brown', 'Amanda Taylor', 'James Anderson', 'Patricia Martinez'
    ];

    const mockTasksByDay = {};
    let total = 0;

    businessDays.forEach(day => {
      const dateKey = day.toISOString().split('T')[0];
      const numTasks = Math.floor(Math.random() * 15) + 8;
      total += numTasks;

      mockTasksByDay[dateKey] = Array.from({ length: numTasks }, (_, i) => ({
        id: `${dateKey}-${i}`,
        title: taskTypes[Math.floor(Math.random() * taskTypes.length)],
        clientName: clients[Math.floor(Math.random() * clients.length)],
        assignedTo: users[Math.floor(Math.random() * users.length)],
        priority: ['urgent', 'high', 'medium', 'low'][Math.floor(Math.random() * 4)],
        dueTime: `${Math.floor(Math.random() * 8) + 9}:00`,
        estimatedMinutes: [15, 30, 45, 60][Math.floor(Math.random() * 4)],
        status: 'pending',
        loanNumber: `LN${Math.floor(Math.random() * 900000) + 100000}`
      }));
    });

    // Generate user capacity data
    const mockUserCapacity = users.map(user => {
      const dailyTasks = businessDays.map(day => {
        const dateKey = day.toISOString().split('T')[0];
        const tasksForUser = mockTasksByDay[dateKey]?.filter(t => t.assignedTo.id === user.id) || [];
        const completedYesterday = Math.floor(Math.random() * user.avgDailyCapacity * 0.3) + Math.floor(user.avgDailyCapacity * 0.6);

        return {
          date: dateKey,
          assigned: tasksForUser.length,
          estimatedHours: tasksForUser.reduce((sum, t) => sum + (t.estimatedMinutes || 30), 0) / 60
        };
      });

      const totalAssigned = dailyTasks.reduce((sum, d) => sum + d.assigned, 0);
      const avgDaily = totalAssigned / 7;
      const completedToday = Math.floor(Math.random() * 10) + 5;
      const completedThisWeek = Math.floor(Math.random() * 50) + 30;

      return {
        ...user,
        dailyTasks,
        totalAssigned,
        avgDailyAssigned: avgDaily.toFixed(1),
        completedToday,
        completedThisWeek,
        capacityUtilization: Math.min(100, Math.round((avgDaily / user.avgDailyCapacity) * 100)),
        overCapacity: avgDaily > user.avgDailyCapacity
      };
    });

    setTasksByDay(mockTasksByDay);
    setUserCapacity(mockUserCapacity);
    setTotalTasks(total);
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
          <h3 style={{ color: workflowColor }}>{workflowName} - Upcoming Tasks</h3>
          <p className="header-subtitle">Next 7 business days • {totalTasks} total tasks</p>
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

      {viewMode === 'calendar' ? (
        /* Calendar View - Tasks by Day */
        <div className="calendar-view">
          <div className="days-grid">
            {businessDays.map(day => {
              const dateKey = day.toISOString().split('T')[0];
              const dayTasks = tasksByDay[dateKey] || [];
              const isToday = formatDate(day) === 'Today';

              return (
                <div key={dateKey} className={`day-column ${isToday ? 'today' : ''}`}>
                  <div className="day-header">
                    <span className="day-name">{formatDate(day)}</span>
                    <span className="task-count">{dayTasks.length} tasks</span>
                  </div>
                  <div className="day-tasks">
                    {dayTasks.slice(0, 8).map(task => (
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
                            {task.assignedTo.name.split(' ').map(n => n[0]).join('')}
                          </span>
                          <span className="assignee-name">{task.assignedTo.name.split(' ')[0]}</span>
                        </div>
                      </div>
                    ))}
                    {dayTasks.length > 8 && (
                      <div className="more-tasks">+{dayTasks.length - 8} more</div>
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
                          {user.name.split(' ').map(n => n[0]).join('')}
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
