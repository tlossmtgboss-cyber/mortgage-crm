import React from 'react';

/**
 * Tasks tab — shows upcoming workflow tasks for the lead's current stage.
 */
function TasksTab({ lead, workflowTasks, workflowTasksLoading, onShowTaskModal }) {
  return (
    <div className="info-section">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <h2 style={{ margin: 0 }}>Tasks</h2>
        <button
          onClick={onShowTaskModal}
          style={{
            background: 'linear-gradient(135deg, #218D8D 0%, #10b981 100%)',
            color: 'white',
            border: 'none',
            padding: '10px 20px',
            borderRadius: '8px',
            fontWeight: '600',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: '14px',
            transition: 'transform 0.2s, box-shadow 0.2s'
          }}
          onMouseOver={(e) => {
            e.currentTarget.style.transform = 'translateY(-2px)';
            e.currentTarget.style.boxShadow = '0 4px 12px rgba(33, 141, 141, 0.3)';
          }}
          onMouseOut={(e) => {
            e.currentTarget.style.transform = 'translateY(0)';
            e.currentTarget.style.boxShadow = 'none';
          }}
        >
          <span style={{ fontSize: '18px' }}>+</span> Add Task
        </button>
      </div>
      <div className="tasks-content">
        <p className="section-description" style={{ color: '#666', marginBottom: '20px' }}>
          Upcoming tasks for the next 2 weeks based on status: <strong>{lead?.stage || 'Unknown'}</strong>
        </p>

        {workflowTasksLoading ? (
          <div style={{ backgroundColor: '#f8f9fa', borderRadius: '8px', padding: '40px', textAlign: 'center', color: '#666' }}>
            Loading workflow tasks...
          </div>
        ) : workflowTasks.length === 0 ? (
          <div style={{ backgroundColor: '#f8f9fa', borderRadius: '8px', padding: '40px', textAlign: 'center', color: '#666' }}>
            <p style={{ marginBottom: '12px' }}>No upcoming tasks for this stage.</p>
            <p style={{ fontSize: '13px' }}>Configure workflows in <strong>Settings &gt; Workflow Configuration</strong></p>
          </div>
        ) : (
          <div className="workflow-tasks-list">
            {workflowTasks.map((task) => (
              <div
                key={task.id}
                style={{
                  backgroundColor: task.status === 'due_today' ? '#fff8e1' : task.status === 'overdue' ? '#ffebee' : '#fff',
                  border: `1px solid ${task.status === 'due_today' ? '#ffca28' : task.status === 'overdue' ? '#ef5350' : '#e0e0e0'}`,
                  borderRadius: '8px',
                  padding: '16px',
                  marginBottom: '12px',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.05)'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                    <span style={{
                      backgroundColor: task.status === 'due_today' ? '#ff9800' : task.status === 'overdue' ? '#f44336' : '#1976d2',
                      color: '#fff',
                      padding: '4px 10px',
                      borderRadius: '12px',
                      fontSize: '12px',
                      fontWeight: '600'
                    }}>
                      {task.status === 'due_today' ? 'Due Today' : task.status === 'overdue' ? 'Overdue' : task.dueDateFormatted}
                    </span>
                    <span style={{
                      backgroundColor: '#e3f2fd',
                      color: '#1976d2',
                      padding: '4px 10px',
                      borderRadius: '12px',
                      fontSize: '12px',
                      fontWeight: '600'
                    }}>
                      {task.dayLabel}
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                    {task.phoneEnabled && (
                      <span title={`Phone call${task.phoneAmEnabled ? ' (AM)' : ''}${task.phonePmEnabled ? ' (PM)' : ''}`} style={{ fontSize: '16px' }}>📞</span>
                    )}
                    {task.textEnabled && (
                      <span title={`Text message${task.textAmEnabled ? ' (AM)' : ''}${task.textPmEnabled ? ' (PM)' : ''}`} style={{ fontSize: '16px' }}>💬</span>
                    )}
                    {task.emailEnabled && (
                      <span title="Email" style={{ fontSize: '16px' }}>📧</span>
                    )}
                    {task.referralPartnerEnabled && (
                      <span title="Referral partner" style={{ fontSize: '16px' }}>🤝</span>
                    )}
                  </div>
                </div>
                <p style={{ margin: '0 0 12px 0', fontSize: '14px', color: '#333', lineHeight: '1.5' }}>
                  {task.taskDescription}
                </p>
                {Object.keys(task.roleResponsibilities || {}).length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                    {Object.entries(task.roleResponsibilities).map(([role, isResponsible]) =>
                      isResponsible && (
                        <span
                          key={role}
                          style={{
                            backgroundColor: '#f5f5f5',
                            color: '#555',
                            padding: '3px 8px',
                            borderRadius: '4px',
                            fontSize: '11px'
                          }}
                        >
                          {role.replace(/_/g, ' ')}
                        </span>
                      )
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default TasksTab;
