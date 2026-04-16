import React, { useState, useEffect, useCallback } from 'react';
import './WorkflowScorecard.css';
import { getToken } from '../utils/tokenStore';

const API_BASE = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

// Performance grade thresholds
const getGrade = (score) => {
  if (score >= 95) return { grade: 'A+', color: '#10b981' };
  if (score >= 90) return { grade: 'A', color: '#10b981' };
  if (score >= 85) return { grade: 'A-', color: '#22c55e' };
  if (score >= 80) return { grade: 'B+', color: '#84cc16' };
  if (score >= 75) return { grade: 'B', color: '#84cc16' };
  if (score >= 70) return { grade: 'B-', color: '#eab308' };
  if (score >= 65) return { grade: 'C+', color: '#f59e0b' };
  if (score >= 60) return { grade: 'C', color: '#f59e0b' };
  if (score >= 55) return { grade: 'C-', color: '#f97316' };
  if (score >= 50) return { grade: 'D', color: '#ef4444' };
  return { grade: 'F', color: '#dc2626' };
};

function WorkflowScorecard({ workflowKey, workflowName, workflowColor }) {
  const [loading, setLoading] = useState(true);
  const [roleMetrics, setRoleMetrics] = useState([]);
  const [employeeMetrics, setEmployeeMetrics] = useState([]);
  const [selectedRole, setSelectedRole] = useState(null);
  const [selectedEmployee, setSelectedEmployee] = useState(null);
  const [overallStats, setOverallStats] = useState({
    totalTasks: 0,
    completedOnTime: 0,
    completedLate: 0,
    overdue: 0,
    avgCompletionTime: 0
  });
  const [timeRange, setTimeRange] = useState('30d');
  const [capacityMetrics, setCapacityMetrics] = useState({
    avgTasksPerDay: 0,
    topPerformers: [],
    capacityLeaderboard: []
  });

  const fetchScorecardData = useCallback(async () => {
    setLoading(true);
    try {
      const token = getToken();
      const headers = { 'Authorization': `Bearer ${token}` };

      // Fetch workflow scorecard data
      const response = await fetch(
        `${API_BASE}/api/v1/workflow/scorecard/${workflowKey}?time_range=${timeRange}`,
        { headers }
      );

      if (response.ok) {
        const data = await response.json();
        setRoleMetrics(data.role_metrics || []);
        setOverallStats(data.overall_stats || {
          totalTasks: 0,
          completedOnTime: 0,
          completedLate: 0,
          overdue: 0,
          avgCompletionTime: 0
        });
      } else {
        // Use mock data for demo
        generateMockData();
      }
    } catch (error) {
      console.error('Error fetching scorecard:', error);
      generateMockData();
    } finally {
      setLoading(false);
    }
  }, [workflowKey, timeRange]);

  const generateMockData = () => {
    // Generate realistic mock data for demonstration
    const roles = [
      { id: 1, name: 'Loan Officer', abbr: 'LO' },
      { id: 2, name: 'Jr. Loan Officer', abbr: 'JLO' },
      { id: 3, name: 'Processor', abbr: 'PRO' },
      { id: 4, name: 'Production Assistant', abbr: 'PA' },
      { id: 5, name: 'Concierge', abbr: 'CON' },
    ];

    const mockRoleMetrics = roles.map(role => ({
      roleId: role.id,
      roleName: role.name,
      roleAbbr: role.abbr,
      tasksAssigned: Math.floor(Math.random() * 50) + 20,
      tasksCompleted: Math.floor(Math.random() * 40) + 15,
      completedOnTime: Math.floor(Math.random() * 35) + 10,
      completedLate: Math.floor(Math.random() * 10),
      overdue: Math.floor(Math.random() * 5),
      avgCompletionHours: Math.floor(Math.random() * 24) + 2,
      score: Math.floor(Math.random() * 30) + 65,
      employees: generateMockEmployees(role.id, role.name)
    }));

    setRoleMetrics(mockRoleMetrics);
    setOverallStats({
      totalTasks: mockRoleMetrics.reduce((sum, r) => sum + r.tasksAssigned, 0),
      completedOnTime: mockRoleMetrics.reduce((sum, r) => sum + r.completedOnTime, 0),
      completedLate: mockRoleMetrics.reduce((sum, r) => sum + r.completedLate, 0),
      overdue: mockRoleMetrics.reduce((sum, r) => sum + r.overdue, 0),
      avgCompletionTime: Math.floor(mockRoleMetrics.reduce((sum, r) => sum + r.avgCompletionHours, 0) / mockRoleMetrics.length)
    });

    // Generate capacity metrics for daily task completion
    const allEmployees = mockRoleMetrics.flatMap(r => r.employees || []);
    const capacityLeaderboard = allEmployees
      .map(emp => ({
        ...emp,
        avgTasksPerDay: Math.round((emp.tasksCompleted / (timeRange === '7d' ? 7 : timeRange === '30d' ? 30 : timeRange === '90d' ? 90 : 365)) * 10) / 10 || Math.floor(Math.random() * 8) + 5,
        peakDay: Math.floor(Math.random() * 15) + 10,
        consistencyScore: Math.floor(Math.random() * 30) + 70,
        totalDaysActive: timeRange === '7d' ? 5 : timeRange === '30d' ? 22 : timeRange === '90d' ? 65 : 250
      }))
      .sort((a, b) => b.avgTasksPerDay - a.avgTasksPerDay);

    setCapacityMetrics({
      avgTasksPerDay: Math.round(capacityLeaderboard.reduce((sum, e) => sum + e.avgTasksPerDay, 0) / capacityLeaderboard.length * 10) / 10,
      topPerformers: capacityLeaderboard.slice(0, 3),
      capacityLeaderboard
    });
  };

  const generateMockEmployees = (roleId, roleName) => {
    const firstNames = ['John', 'Sarah', 'Mike', 'Emily', 'David', 'Lisa', 'Chris', 'Amanda'];
    const lastNames = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis'];
    const count = Math.floor(Math.random() * 3) + 2;

    return Array.from({ length: count }, (_, i) => ({
      id: roleId * 100 + i,
      name: `${firstNames[Math.floor(Math.random() * firstNames.length)]} ${lastNames[Math.floor(Math.random() * lastNames.length)]}`,
      role: roleName,
      tasksAssigned: Math.floor(Math.random() * 20) + 5,
      tasksCompleted: Math.floor(Math.random() * 18) + 3,
      completedOnTime: Math.floor(Math.random() * 15) + 2,
      completedLate: Math.floor(Math.random() * 5),
      overdue: Math.floor(Math.random() * 3),
      avgCompletionHours: Math.floor(Math.random() * 20) + 1,
      score: Math.floor(Math.random() * 35) + 60,
      recentTasks: generateRecentTasks()
    }));
  };

  const generateRecentTasks = () => {
    const taskNames = [
      'Initial Contact Call',
      'Send Follow-up Email',
      'Document Collection',
      'Credit Review',
      'Application Review',
      'Rate Lock Confirmation',
      'Disclosure Delivery'
    ];

    return Array.from({ length: 5 }, (_, i) => ({
      id: i + 1,
      name: taskNames[Math.floor(Math.random() * taskNames.length)],
      status: ['completed', 'completed', 'completed', 'late', 'overdue'][Math.floor(Math.random() * 5)],
      dueDate: new Date(Date.now() - Math.random() * 7 * 24 * 60 * 60 * 1000).toLocaleDateString(),
      completedDate: Math.random() > 0.2 ? new Date(Date.now() - Math.random() * 5 * 24 * 60 * 60 * 1000).toLocaleDateString() : null
    }));
  };

  useEffect(() => {
    fetchScorecardData();
  }, [fetchScorecardData]);

  const handleRoleClick = (role) => {
    setSelectedRole(role);
    setEmployeeMetrics(role.employees || []);
    setSelectedEmployee(null);
  };

  const handleEmployeeClick = (employee) => {
    setSelectedEmployee(employee);
  };

  const handleBack = () => {
    if (selectedEmployee) {
      setSelectedEmployee(null);
    } else if (selectedRole) {
      setSelectedRole(null);
      setEmployeeMetrics([]);
    }
  };

  const calculateOverallScore = () => {
    if (overallStats.totalTasks === 0) return 0;
    const onTimeRate = (overallStats.completedOnTime / overallStats.totalTasks) * 100;
    const lateRate = (overallStats.completedLate / overallStats.totalTasks) * 50;
    return Math.min(100, Math.round(onTimeRate - (overallStats.overdue * 2) + lateRate * 0.5));
  };

  if (loading) {
    return <div className="scorecard-loading">Loading scorecard data...</div>;
  }

  const overallScore = calculateOverallScore();
  const overallGrade = getGrade(overallScore);

  return (
    <div className="workflow-scorecard">
      {/* Breadcrumb Navigation */}
      {(selectedRole || selectedEmployee) && (
        <div className="scorecard-breadcrumb">
          <button onClick={() => { setSelectedRole(null); setSelectedEmployee(null); }}>
            All Roles
          </button>
          {selectedRole && (
            <>
              <span className="breadcrumb-separator">›</span>
              <button onClick={() => setSelectedEmployee(null)} className={!selectedEmployee ? 'active' : ''}>
                {selectedRole.roleName}
              </button>
            </>
          )}
          {selectedEmployee && (
            <>
              <span className="breadcrumb-separator">›</span>
              <span className="active">{selectedEmployee.name}</span>
            </>
          )}
        </div>
      )}

      {/* Time Range Filter */}
      <div className="scorecard-header">
        <div className="header-left">
          {selectedRole && (
            <button className="btn-back" onClick={handleBack}>
              ← Back
            </button>
          )}
          <h3 style={{ color: workflowColor }}>
            {selectedEmployee ? `${selectedEmployee.name} Performance` :
             selectedRole ? `${selectedRole.roleName} Team Performance` :
             `${workflowName} Workflow Scorecard`}
          </h3>
        </div>
        <div className="time-filter">
          <select value={timeRange} onChange={(e) => setTimeRange(e.target.value)}>
            <option value="7d">Last 7 Days</option>
            <option value="30d">Last 30 Days</option>
            <option value="90d">Last 90 Days</option>
            <option value="ytd">Year to Date</option>
          </select>
        </div>
      </div>

      {/* Employee Detail View */}
      {selectedEmployee ? (
        <div className="employee-detail-view">
          {/* Employee Score Card */}
          <div className="employee-score-header">
            <div className="employee-info">
              <div className="employee-avatar">
                {selectedEmployee.name.split(' ').map(n => n[0]).join('')}
              </div>
              <div className="employee-details">
                <h4>{selectedEmployee.name}</h4>
                <p>{selectedEmployee.role}</p>
              </div>
            </div>
            <div className="employee-grade-card">
              <div className="grade-circle" style={{ borderColor: getGrade(selectedEmployee.score).color }}>
                <span className="grade" style={{ color: getGrade(selectedEmployee.score).color }}>
                  {getGrade(selectedEmployee.score).grade}
                </span>
                <span className="score">{selectedEmployee.score}</span>
              </div>
              <span className="grade-label">Performance Score</span>
            </div>
          </div>

          {/* Employee KPIs */}
          <div className="employee-kpis">
            <div className="kpi-card">
              <div className="kpi-value">{selectedEmployee.tasksAssigned}</div>
              <div className="kpi-label">Assigned</div>
            </div>
            <div className="kpi-card success">
              <div className="kpi-value">{selectedEmployee.completedOnTime}</div>
              <div className="kpi-label">On Time</div>
            </div>
            <div className="kpi-card warning">
              <div className="kpi-value">{selectedEmployee.completedLate}</div>
              <div className="kpi-label">Late</div>
            </div>
            <div className="kpi-card danger">
              <div className="kpi-value">{selectedEmployee.overdue}</div>
              <div className="kpi-label">Overdue</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-value">{selectedEmployee.avgCompletionHours}h</div>
              <div className="kpi-label">Avg Time</div>
            </div>
          </div>

          {/* Recent Tasks */}
          <div className="recent-tasks-section">
            <h4>Recent Tasks</h4>
            <table className="tasks-table">
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Due Date</th>
                  <th>Completed</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {selectedEmployee.recentTasks?.map(task => (
                  <tr key={task.id}>
                    <td>{task.name}</td>
                    <td>{task.dueDate}</td>
                    <td>{task.completedDate || '-'}</td>
                    <td>
                      <span className={`status-badge ${task.status}`}>
                        {task.status === 'completed' ? 'On Time' :
                         task.status === 'late' ? 'Late' : 'Overdue'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : selectedRole ? (
        /* Role Team View */
        <div className="role-team-view">
          {/* Role Summary */}
          <div className="role-summary-card">
            <div className="role-grade">
              <div className="grade-circle large" style={{ borderColor: getGrade(selectedRole.score).color }}>
                <span className="grade" style={{ color: getGrade(selectedRole.score).color }}>
                  {getGrade(selectedRole.score).grade}
                </span>
                <span className="score">{selectedRole.score}</span>
              </div>
              <span className="grade-label">Team Score</span>
            </div>
            <div className="role-stats">
              <div className="stat">
                <span className="stat-value">{selectedRole.tasksAssigned}</span>
                <span className="stat-label">Tasks Assigned</span>
              </div>
              <div className="stat">
                <span className="stat-value success">{selectedRole.completedOnTime}</span>
                <span className="stat-label">On Time</span>
              </div>
              <div className="stat">
                <span className="stat-value warning">{selectedRole.completedLate}</span>
                <span className="stat-label">Late</span>
              </div>
              <div className="stat">
                <span className="stat-value danger">{selectedRole.overdue}</span>
                <span className="stat-label">Overdue</span>
              </div>
            </div>
          </div>

          {/* Team Members */}
          <h4 className="section-title">Team Members</h4>
          <div className="employee-grid">
            {employeeMetrics.map(employee => {
              const empGrade = getGrade(employee.score);
              return (
                <div
                  key={employee.id}
                  className="employee-card"
                  onClick={() => handleEmployeeClick(employee)}
                >
                  <div className="employee-card-header">
                    <div className="employee-avatar small">
                      {employee.name.split(' ').map(n => n[0]).join('')}
                    </div>
                    <div className="employee-name">{employee.name}</div>
                  </div>
                  <div className="employee-card-score">
                    <span className="score-value" style={{ color: empGrade.color }}>
                      {empGrade.grade}
                    </span>
                    <span className="score-number">{employee.score}</span>
                  </div>
                  <div className="employee-card-stats">
                    <div className="mini-stat">
                      <span className="value">{employee.tasksCompleted}</span>
                      <span className="label">Done</span>
                    </div>
                    <div className="mini-stat success">
                      <span className="value">{employee.completedOnTime}</span>
                      <span className="label">On Time</span>
                    </div>
                    <div className="mini-stat danger">
                      <span className="value">{employee.overdue}</span>
                      <span className="label">Overdue</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        /* Main Scorecard View - All Roles */
        <>
          {/* Overall KPIs */}
          <div className="overall-kpis">
            <div className="overall-score-card">
              <div className="score-circle" style={{ borderColor: overallGrade.color }}>
                <span className="grade" style={{ color: overallGrade.color }}>{overallGrade.grade}</span>
                <span className="score">{overallScore}</span>
              </div>
              <span className="score-label">Overall Score</span>
            </div>
            <div className="kpi-grid">
              <div className="kpi-item">
                <div className="kpi-value">{overallStats.totalTasks}</div>
                <div className="kpi-label">Total Tasks</div>
              </div>
              <div className="kpi-item success">
                <div className="kpi-value">{overallStats.completedOnTime}</div>
                <div className="kpi-label">Completed On Time</div>
                <div className="kpi-percent">
                  {overallStats.totalTasks > 0 ?
                    Math.round((overallStats.completedOnTime / overallStats.totalTasks) * 100) : 0}%
                </div>
              </div>
              <div className="kpi-item warning">
                <div className="kpi-value">{overallStats.completedLate}</div>
                <div className="kpi-label">Completed Late</div>
                <div className="kpi-percent">
                  {overallStats.totalTasks > 0 ?
                    Math.round((overallStats.completedLate / overallStats.totalTasks) * 100) : 0}%
                </div>
              </div>
              <div className="kpi-item danger">
                <div className="kpi-value">{overallStats.overdue}</div>
                <div className="kpi-label">Overdue</div>
                <div className="kpi-percent">
                  {overallStats.totalTasks > 0 ?
                    Math.round((overallStats.overdue / overallStats.totalTasks) * 100) : 0}%
                </div>
              </div>
              <div className="kpi-item">
                <div className="kpi-value">{overallStats.avgCompletionTime}h</div>
                <div className="kpi-label">Avg Completion</div>
              </div>
            </div>
          </div>

          {/* Daily Capacity Leaderboard */}
          <div className="capacity-leaderboard-section">
            <div className="section-header-row">
              <h4 className="section-title">📊 Daily Task Capacity Leaderboard</h4>
              <div className="capacity-avg">
                Team Avg: <strong>{capacityMetrics.avgTasksPerDay}</strong> tasks/day
              </div>
            </div>
            <p className="section-description">
              Track how many tasks each team member completes per day to measure and optimize capacity.
            </p>

            {/* Top 3 Performers */}
            <div className="top-performers">
              {capacityMetrics.topPerformers.map((performer, idx) => (
                <div key={performer.id} className={`performer-card rank-${idx + 1}`}>
                  <div className="rank-badge">#{idx + 1}</div>
                  <div className="performer-avatar">
                    {performer.name.split(' ').map(n => n[0]).join('')}
                  </div>
                  <div className="performer-info">
                    <span className="performer-name">{performer.name}</span>
                    <span className="performer-role">{performer.role}</span>
                  </div>
                  <div className="performer-stats">
                    <div className="stat-main">
                      <span className="stat-value">{performer.avgTasksPerDay}</span>
                      <span className="stat-label">tasks/day</span>
                    </div>
                    <div className="stat-secondary">
                      <span>Peak: {performer.peakDay}</span>
                      <span>Consistency: {performer.consistencyScore}%</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Full Leaderboard Table */}
            <div className="capacity-table-wrapper">
              <table className="capacity-leaderboard-table">
                <thead>
                  <tr>
                    <th>Rank</th>
                    <th>Team Member</th>
                    <th>Role</th>
                    <th>Avg Tasks/Day</th>
                    <th>Peak Day</th>
                    <th>Days Active</th>
                    <th>Consistency</th>
                    <th>vs Team Avg</th>
                  </tr>
                </thead>
                <tbody>
                  {capacityMetrics.capacityLeaderboard.map((employee, idx) => {
                    const vsAvg = capacityMetrics.avgTasksPerDay > 0
                      ? Math.round(((employee.avgTasksPerDay - capacityMetrics.avgTasksPerDay) / capacityMetrics.avgTasksPerDay) * 100)
                      : 0;

                    return (
                      <tr
                        key={employee.id}
                        className={idx < 3 ? `top-rank top-${idx + 1}` : ''}
                        onClick={() => handleEmployeeClick(employee)}
                      >
                        <td className="rank-cell">{idx + 1}</td>
                        <td>
                          <div className="employee-cell">
                            <span className="employee-avatar-sm">
                              {employee.name.split(' ').map(n => n[0]).join('')}
                            </span>
                            {employee.name}
                          </div>
                        </td>
                        <td>{employee.role}</td>
                        <td className="tasks-cell">
                          <strong>{employee.avgTasksPerDay}</strong>
                        </td>
                        <td>{employee.peakDay}</td>
                        <td>{employee.totalDaysActive}</td>
                        <td>
                          <div className="consistency-bar">
                            <div
                              className="consistency-fill"
                              style={{ width: `${employee.consistencyScore}%` }}
                            />
                            <span>{employee.consistencyScore}%</span>
                          </div>
                        </td>
                        <td className={vsAvg >= 0 ? 'positive' : 'negative'}>
                          {vsAvg >= 0 ? '+' : ''}{vsAvg}%
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Role Performance Cards */}
          <h4 className="section-title">Performance by Role</h4>
          <div className="role-cards-grid">
            {roleMetrics.map(role => {
              const roleGrade = getGrade(role.score);
              const completionRate = role.tasksAssigned > 0
                ? Math.round((role.completedOnTime / role.tasksAssigned) * 100)
                : 0;

              return (
                <div
                  key={role.roleId}
                  className="role-performance-card"
                  onClick={() => handleRoleClick(role)}
                >
                  <div className="role-card-header">
                    <div className="role-info">
                      <span className="role-abbr">{role.roleAbbr}</span>
                      <span className="role-name">{role.roleName}</span>
                    </div>
                    <div className="role-grade" style={{ color: roleGrade.color }}>
                      {roleGrade.grade}
                    </div>
                  </div>

                  <div className="role-score-bar">
                    <div
                      className="score-fill"
                      style={{
                        width: `${role.score}%`,
                        backgroundColor: roleGrade.color
                      }}
                    />
                  </div>

                  <div className="role-metrics">
                    <div className="metric">
                      <span className="value">{role.tasksAssigned}</span>
                      <span className="label">Assigned</span>
                    </div>
                    <div className="metric success">
                      <span className="value">{role.completedOnTime}</span>
                      <span className="label">On Time</span>
                    </div>
                    <div className="metric warning">
                      <span className="value">{role.completedLate}</span>
                      <span className="label">Late</span>
                    </div>
                    <div className="metric danger">
                      <span className="value">{role.overdue}</span>
                      <span className="label">Overdue</span>
                    </div>
                  </div>

                  <div className="role-footer">
                    <span className="completion-rate">{completionRate}% on-time rate</span>
                    <span className="team-count">{role.employees?.length || 0} team members →</span>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

export default WorkflowScorecard;
