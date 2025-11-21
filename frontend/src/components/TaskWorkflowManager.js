import { useState, useEffect } from 'react';
import { API_BASE_URL } from '../services/api';
import './TaskWorkflowManager.css';

function TaskWorkflowManager() {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });
  const [activeStage, setActiveStage] = useState(null);

  // Team members with their workflow progress (will be loaded from API)
  const [teamMembers, setTeamMembers] = useState([]);

  // Workflow stages with their tasks
  const [workflowStages, setWorkflowStages] = useState({
    lead: {
      name: 'Lead',
      description: 'Initial contact and qualification workflow',
      color: '#3b82f6',
      tasks: [
        { id: 1, title: 'Initial Contact', description: 'Make first contact with lead', order: 1, auto_trigger: 'on_lead_create', days_offset: 0 },
        { id: 2, title: 'Send Introduction Email', description: 'Send welcome email with information', order: 2, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 3, title: 'Schedule Discovery Call', description: 'Set up initial consultation', order: 3, auto_trigger: 'after_previous', days_offset: 1 },
        { id: 4, title: 'Pre-Qualification Check', description: 'Verify basic qualification criteria', order: 4, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 5, title: 'Collect Documents', description: 'Request income, assets, and ID documents', order: 5, auto_trigger: 'after_previous', days_offset: 1 },
        { id: 6, title: 'Credit Pull Authorization', description: 'Get authorization for credit check', order: 6, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 7, title: 'Generate Pre-Approval Letter', description: 'Create pre-approval documentation', order: 7, auto_trigger: 'after_previous', days_offset: 1 },
        { id: 8, title: 'Convert to Active Loan', description: 'Move to active loan processing', order: 8, auto_trigger: 'manual', days_offset: 0 }
      ]
    },
    active_loan: {
      name: 'Active Loan',
      description: 'Loan processing and underwriting workflow',
      color: '#10b981',
      tasks: [
        { id: 9, title: 'Application Submitted', description: 'Formal loan application received', order: 1, auto_trigger: 'on_conversion', days_offset: 0 },
        { id: 10, title: 'Order Appraisal', description: 'Request property appraisal', order: 2, auto_trigger: 'after_previous', days_offset: 1 },
        { id: 11, title: 'Title Search', description: 'Order title search and insurance', order: 3, auto_trigger: 'after_previous', days_offset: 0 },
        { id: 12, title: 'Submit to Underwriting', description: 'Package file for underwriter review', order: 4, auto_trigger: 'after_previous', days_offset: 2 },
        { id: 13, title: 'Address Conditions', description: 'Clear underwriting conditions', order: 5, auto_trigger: 'on_conditions', days_offset: 0 },
        { id: 14, title: 'Final Approval', description: 'Obtain clear to close', order: 6, auto_trigger: 'after_previous', days_offset: 3 },
        { id: 15, title: 'Schedule Closing', description: 'Coordinate closing date and location', order: 7, auto_trigger: 'after_previous', days_offset: 1 },
        { id: 16, title: 'Closing Day', description: 'Execute closing documents', order: 8, auto_trigger: 'on_closing_date', days_offset: 0 },
        { id: 17, title: 'Fund Loan', description: 'Wire funds and record documents', order: 9, auto_trigger: 'after_previous', days_offset: 1 },
        { id: 18, title: 'Move to Portfolio', description: 'Transfer to servicing/portfolio', order: 10, auto_trigger: 'after_previous', days_offset: 3 }
      ]
    },
    portfolio: {
      name: 'Portfolio',
      description: 'Post-closing servicing and retention workflow',
      color: '#8b5cf6',
      tasks: [
        { id: 19, title: 'Welcome to Portfolio', description: 'Send post-closing welcome package', order: 1, auto_trigger: 'on_portfolio_add', days_offset: 0 },
        { id: 20, title: '30-Day Check-In', description: 'First payment follow-up call', order: 2, auto_trigger: 'scheduled', days_offset: 30 },
        { id: 21, title: '90-Day Review', description: 'Ensure smooth servicing transition', order: 3, auto_trigger: 'scheduled', days_offset: 90 },
        { id: 22, title: 'Annual Review', description: 'Yearly financial checkup', order: 4, auto_trigger: 'annual', days_offset: 365 },
        { id: 23, title: 'Refinance Opportunity Check', description: 'Review for refinance potential', order: 5, auto_trigger: 'rate_trigger', days_offset: 0 },
        { id: 24, title: 'Birthday Outreach', description: 'Send birthday greeting', order: 6, auto_trigger: 'birthday', days_offset: 0 },
        { id: 25, title: 'Loan Anniversary', description: 'Celebrate loan anniversary', order: 7, auto_trigger: 'anniversary', days_offset: 0 },
        { id: 26, title: 'Referral Request', description: 'Ask for referrals at key moments', order: 8, auto_trigger: 'milestone', days_offset: 0 }
      ]
    }
  });

  useEffect(() => {
    loadWorkflowStages();
  }, []);

  useEffect(() => {
    if (activeStage) {
      loadTeamMembersForStage(activeStage);
    }
  }, [activeStage]);

  const loadTeamMembersForStage = async (stageKey) => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/workflow-stages/${stageKey}/team-members`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      if (response.ok) {
        const data = await response.json();
        setTeamMembers(data.team_members || []);
      } else {
        // Use mock data if API not available
        setTeamMembers([
          {
            id: 1,
            name: 'Sarah Johnson',
            role: 'Loan Officer',
            avatar: null,
            count: 12,
            tasks: workflowStages[stageKey].tasks.map((task, idx) => ({
              ...task,
              status: idx < 3 ? 'completed' : idx === 3 ? 'in_progress' : 'pending'
            }))
          },
          {
            id: 2,
            name: 'Mike Chen',
            role: 'Loan Officer',
            avatar: null,
            count: 8,
            tasks: workflowStages[stageKey].tasks.map((task, idx) => ({
              ...task,
              status: idx < 5 ? 'completed' : idx === 5 ? 'in_progress' : 'pending'
            }))
          },
          {
            id: 3,
            name: 'Emily Davis',
            role: 'Processor',
            avatar: null,
            count: 15,
            tasks: workflowStages[stageKey].tasks.map((task, idx) => ({
              ...task,
              status: idx < 2 ? 'completed' : idx === 2 ? 'in_progress' : 'pending'
            }))
          }
        ]);
      }
    } catch (error) {
      console.error('Error loading team members:', error);
      setTeamMembers([]);
    } finally {
      setLoading(false);
    }
  };

  const loadWorkflowStages = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/workflow-stages`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      if (response.ok) {
        const data = await response.json();
        if (data.stages) {
          setWorkflowStages(data.stages);
        }
      }
    } catch (error) {
      console.error('Error loading workflow stages:', error);
      // Keep default stages if API fails
    }
  };

  return (
    <div className="task-workflow-manager">
      <div className="manager-header">
        <h2>Workflow Management</h2>
        <p>Configure automated workflows for each stage of the client lifecycle</p>
      </div>

      {message.text && (
        <div className={`message-banner ${message.type}`}>
          {message.text}
          <button onClick={() => setMessage({ type: '', text: '' })} className="close-btn">×</button>
        </div>
      )}

      {/* Stage Overview Cards */}
      <div className="workflow-stages-grid">
        {Object.entries(workflowStages).map(([key, stage]) => (
          <div
            key={key}
            className={`stage-card ${activeStage === key ? 'active' : ''}`}
            style={{ '--stage-color': stage.color }}
          >
            <div className="stage-header" onClick={() => setActiveStage(activeStage === key ? null : key)}>
              <div className="stage-title">
                <h3>{stage.name}</h3>
              </div>
              <div className="stage-meta">
                <span className="task-count">{stage.tasks.length} tasks</span>
                <span className="expand-icon">{activeStage === key ? '▼' : '▶'}</span>
              </div>
            </div>
            <p className="stage-description">{stage.description}</p>

            {/* Collapsed Preview */}
            {activeStage !== key && (
              <div className="stage-preview">
                <div className="preview-tasks">
                  {stage.tasks.slice(0, 3).map((task, idx) => (
                    <div key={task.id} className="preview-task">
                      <span className="task-number">{idx + 1}</span>
                      <span className="task-name">{task.title}</span>
                    </div>
                  ))}
                  {stage.tasks.length > 3 && (
                    <div className="preview-more">+{stage.tasks.length - 3} more tasks</div>
                  )}
                </div>
              </div>
            )}

            {/* Expanded Team Members View */}
            {activeStage === key && (
              <div className="stage-tasks-expanded">
                {loading ? (
                  <div className="loading-state">Loading team members...</div>
                ) : teamMembers.length === 0 ? (
                  <div className="empty-state">No team members with {stage.name.toLowerCase()}s</div>
                ) : (
                  <div className="team-members-list">
                    {teamMembers.map((member) => (
                      <div key={member.id} className="team-member-card">
                        <div className="member-header">
                          <div className="member-info">
                            <div className="member-avatar">
                              {member.avatar ? (
                                <img src={member.avatar} alt={member.name} />
                              ) : (
                                <span>{member.name.split(' ').map(n => n[0]).join('')}</span>
                              )}
                            </div>
                            <div className="member-details">
                              <strong>{member.name}</strong>
                              <span className="member-role">{member.role}</span>
                            </div>
                          </div>
                          <div className="member-count">
                            <span className="count-value">{member.count}</span>
                            <span className="count-label">{stage.name.toLowerCase()}s</span>
                          </div>
                        </div>
                        <div className="member-workflow">
                          <div className="workflow-progress">
                            {member.tasks.map((task) => (
                              <div
                                key={task.id}
                                className={`workflow-step ${task.status}`}
                                title={`${task.title} - ${task.status}`}
                              >
                                <div className="step-indicator">
                                  {task.status === 'completed' ? '✓' : task.status === 'in_progress' ? '●' : '○'}
                                </div>
                              </div>
                            ))}
                          </div>
                          <div className="workflow-summary">
                            <span className="completed-count">
                              {member.tasks.filter(t => t.status === 'completed').length}/{member.tasks.length} completed
                            </span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Workflow Flow Visualization */}
      <div className="workflow-flow-section">
        <h3>Client Lifecycle Flow</h3>
        <div className="flow-visualization">
          <div className="flow-stage" style={{ '--stage-color': workflowStages.lead.color }}>
            <span>Lead</span>
            <small>{workflowStages.lead.tasks.length} tasks</small>
          </div>
          <div className="flow-arrow">→</div>
          <div className="flow-stage" style={{ '--stage-color': workflowStages.active_loan.color }}>
            <span>Active Loan</span>
            <small>{workflowStages.active_loan.tasks.length} tasks</small>
          </div>
          <div className="flow-arrow">→</div>
          <div className="flow-stage" style={{ '--stage-color': workflowStages.portfolio.color }}>
            <span>Portfolio</span>
            <small>{workflowStages.portfolio.tasks.length} tasks</small>
          </div>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="workflow-stats">
        <div className="stat-card">
          <span className="stat-value">
            {Object.values(workflowStages).reduce((sum, stage) => sum + stage.tasks.length, 0)}
          </span>
          <span className="stat-label">Total Tasks</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">3</span>
          <span className="stat-label">Workflow Stages</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">
            {Object.values(workflowStages).reduce((sum, stage) =>
              sum + stage.tasks.filter(t => t.auto_trigger !== 'manual').length, 0
            )}
          </span>
          <span className="stat-label">Automated Tasks</span>
        </div>
      </div>
    </div>
  );
}

export default TaskWorkflowManager;
