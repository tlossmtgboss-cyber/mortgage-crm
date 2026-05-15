/**
 * Tasks Generated Component
 *
 * Displays tasks and action items generated from call analysis.
 * Allows approval/rejection of pending tasks.
 */

import React from 'react';

const TasksGenerated = ({ tasks, actionItems, onApprove }) => {
  const allItems = [
    ...(tasks || []).map(t => ({ ...t, itemType: 'task' })),
    ...(actionItems || []).filter(a => !a.structured_data?.owner?.toLowerCase().includes('borrower'))
      .map(a => ({ ...a, itemType: 'action_item' })),
  ];

  if (allItems.length === 0) {
    return (
      <div className="tasks-generated">
        <p style={{ color: '#6b7280', textAlign: 'center', padding: '40px' }}>
          No tasks generated from this call.
        </p>
      </div>
    );
  }

  const pendingItems = allItems.filter(item => item.approval_status === 'pending');
  const approvedItems = allItems.filter(item => item.approval_status === 'approved' || item.approval_status === 'auto_approved');
  const executedItems = allItems.filter(item => item.execution_status === 'executed');

  return (
    <div className="tasks-generated">
      {/* Summary Stats */}
      <div style={{
        display: 'flex',
        gap: '16px',
        marginBottom: '20px',
        padding: '12px',
        background: '#f9fafb',
        borderRadius: '8px',
      }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '1.5rem', fontWeight: '600', color: '#f59e0b' }}>
            {pendingItems.length}
          </div>
          <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>Pending</div>
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '1.5rem', fontWeight: '600', color: '#2D7A52' }}>
            {approvedItems.length}
          </div>
          <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>Approved</div>
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '1.5rem', fontWeight: '600', color: '#3b82f6' }}>
            {executedItems.length}
          </div>
          <div style={{ fontSize: '0.75rem', color: '#6b7280' }}>Created</div>
        </div>
      </div>

      {/* Pending Tasks */}
      {pendingItems.length > 0 && (
        <>
          <h4 style={{ margin: '0 0 12px', fontSize: '0.875rem', color: '#374151' }}>
            Pending Approval
          </h4>
          {pendingItems.map((item) => (
            <div
              key={item.id}
              className={`task-card pending`}
            >
              <div className="task-header">
                <span className="task-title">{item.title}</span>
                <span className={`task-priority ${item.priority || item.structured_data?.priority || 'medium'}`}>
                  {item.priority || item.structured_data?.priority || 'medium'}
                </span>
              </div>

              <div className="task-content">
                {item.content}
                {item.structured_data?.owner && (
                  <span style={{ display: 'block', marginTop: '8px', fontSize: '0.75rem', color: '#3b82f6' }}>
                    Owner: {item.structured_data.owner}
                  </span>
                )}
              </div>

              <div className="task-actions">
                <button
                  className="approve-btn"
                  onClick={() => onApprove([item.id])}
                >
                  Approve & Create Task
                </button>
              </div>
            </div>
          ))}
        </>
      )}

      {/* Approved/Executed Tasks */}
      {(approvedItems.length > 0 || executedItems.length > 0) && (
        <>
          <h4 style={{ margin: '20px 0 12px', fontSize: '0.875rem', color: '#374151' }}>
            Approved Tasks
          </h4>
          {[...executedItems, ...approvedItems.filter(a => a.execution_status !== 'executed')].map((item) => (
            <div
              key={item.id}
              className={`task-card approved`}
            >
              <div className="task-header">
                <span className="task-title">{item.title}</span>
                <div style={{ display: 'flex', gap: '8px' }}>
                  {item.execution_status === 'executed' && (
                    <span style={{
                      fontSize: '0.7rem',
                      padding: '2px 8px',
                      background: '#dcfce7',
                      color: '#166534',
                      borderRadius: '4px',
                    }}>
                      Task Created
                    </span>
                  )}
                  <span className={`task-priority ${item.priority || 'medium'}`}>
                    {item.priority || 'medium'}
                  </span>
                </div>
              </div>

              <div className="task-content">
                {item.content}
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  );
};

export default TasksGenerated;
