import React from 'react';
import ReactMarkdown from 'react-markdown';

const getPriorityBadgeStyle = (priority) => {
  const colors = {
    'URGENT': { bg: '#fef2f2', text: '#dc2626', border: '#fecaca' },
    'HIGH': { bg: '#fff7ed', text: '#ea580c', border: '#fed7aa' },
    'MEDIUM': { bg: '#fefce8', text: '#ca8a04', border: '#fef08a' },
    'LOW': { bg: '#f0fdf4', text: '#16a34a', border: '#bbf7d0' }
  };
  return colors[priority?.toUpperCase()] || { bg: '#f3f4f6', text: '#6b7280', border: '#e5e7eb' };
};

const styles = {
  container: {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    color: '#1a1a1a',
    lineHeight: 1.6,
    maxWidth: '800px'
  },
  card: {
    background: '#ffffff',
    borderRadius: '12px',
    boxShadow: '0 1px 3px rgba(0, 0, 0, 0.1), 0 1px 2px rgba(0, 0, 0, 0.06)',
    padding: '24px',
    marginTop: '16px'
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    border: '1px solid #e5e7eb',
    borderRadius: '8px',
    overflow: 'hidden',
    marginBottom: '20px'
  },
  th: {
    background: '#f9fafb',
    padding: '12px 16px',
    textAlign: 'left',
    fontSize: '13px',
    fontWeight: 600,
    color: '#374151',
    borderBottom: '1px solid #e5e7eb'
  },
  td: {
    padding: '12px 16px',
    borderBottom: '1px solid #e5e7eb',
    fontSize: '14px',
    verticalAlign: 'top'
  },
  taskName: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '8px',
    padding: '4px 10px',
    background: '#faf5ff',
    border: '1px solid #e9d5ff',
    borderRadius: '6px',
    color: '#B8924A',
    fontSize: '13px',
    fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace',
    textDecoration: 'none',
    cursor: 'pointer',
    transition: 'all 0.15s ease'
  },
  sectionTitle: {
    fontSize: '16px',
    fontWeight: 600,
    color: '#111827',
    marginTop: '24px',
    marginBottom: '12px'
  },
  bulletList: {
    listStyle: 'disc',
    paddingLeft: '24px',
    margin: '0 0 20px 0'
  },
  bulletItem: {
    marginBottom: '8px',
    color: '#374151',
    fontSize: '14px'
  },
  outputsSection: {
    display: 'flex',
    alignItems: 'center',
    gap: '16px',
    padding: '16px',
    background: '#f9fafb',
    borderRadius: '8px',
    border: '1px solid #e5e7eb',
    marginTop: '20px'
  },
  fileIcon: {
    width: '48px',
    height: '48px',
    background: '#ffffff',
    border: '1px solid #e5e7eb',
    borderRadius: '8px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#9ca3af'
  },
  downloadBtn: {
    marginLeft: 'auto',
    padding: '8px 16px',
    background: '#ffffff',
    border: '1px solid #d1d5db',
    borderRadius: '6px',
    fontSize: '14px',
    fontWeight: 500,
    color: '#374151',
    cursor: 'pointer',
    transition: 'all 0.15s ease'
  },
  completeBtn: {
    padding: '6px 14px',
    background: '#2D7A52',
    color: 'white',
    border: 'none',
    borderRadius: '6px',
    fontSize: '13px',
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'all 0.15s ease'
  },
  completedBadge: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    color: '#2D7A52',
    fontSize: '13px',
    fontWeight: 500
  }
};

function TaskPrioritiesComponent({ content, tasks, onCompleteTask, onViewDetails, onSnoozeTask }) {
  const [completingTask, setCompletingTask] = React.useState(null);
  const [completedTasks, setCompletedTasks] = React.useState(new Set());

  const handleComplete = async (task) => {
    setCompletingTask(task.id);
    try {
      if (onCompleteTask) {
        await onCompleteTask(task);
      }
      setCompletedTasks(prev => new Set([...prev, task.id]));
    } catch (error) {
      console.error('Error completing task:', error);
    } finally {
      setCompletingTask(null);
    }
  };

  return (
    <div className="ai-message-content-new ai-special-content" style={styles.container}>
      {/* AI Response Text */}
      <div className="ai-chat-response-content">
        <ReactMarkdown>{content}</ReactMarkdown>
      </div>

      {tasks && tasks.length > 0 && (
        <div style={styles.card}>
          {/* Tasks Table */}
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Task</th>
                <th style={styles.th}>Details</th>
                <th style={{ ...styles.th, width: '100px', textAlign: 'center' }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((task, index) => {
                const priorityStyle = getPriorityBadgeStyle(task.priority);
                const isCompleted = completedTasks.has(task.id);
                const isCompletingThis = completingTask === task.id;

                return (
                  <tr
                    key={task.id || index}
                    style={{
                      background: isCompleted ? '#f0fdf4' : (index % 2 === 0 ? '#ffffff' : '#f9fafb'),
                      opacity: isCompleted ? 0.7 : 1
                    }}
                  >
                    <td style={styles.td}>
                      <span
                        style={{
                          ...styles.taskName,
                          textDecoration: isCompleted ? 'line-through' : 'none',
                          opacity: isCompleted ? 0.7 : 1
                        }}
                        onClick={() => onViewDetails && onViewDetails(task)}
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
                        </svg>
                        {task.title}
                      </span>
                      <span
                        style={{
                          marginLeft: '8px',
                          padding: '2px 8px',
                          background: priorityStyle.bg,
                          color: priorityStyle.text,
                          border: `1px solid ${priorityStyle.border}`,
                          borderRadius: '4px',
                          fontSize: '11px',
                          fontWeight: 500
                        }}
                      >
                        {task.priority}
                      </span>
                    </td>
                    <td style={styles.td}>
                      <div style={{ color: '#111827', marginBottom: '4px' }}>
                        {task.client && <strong>{task.client}</strong>}
                        {task.loan_amount && <span style={{ color: '#6b7280' }}> ({task.loan_amount})</span>}
                      </div>
                      {task.description && (
                        <div style={{ color: '#6b7280', fontSize: '13px' }}>{task.description}</div>
                      )}
                      {task.due_date && (
                        <div style={{ color: '#9ca3af', fontSize: '12px', marginTop: '4px' }}>
                          Due: {task.due_date}
                        </div>
                      )}
                    </td>
                    <td style={{ ...styles.td, textAlign: 'center' }}>
                      {isCompleted ? (
                        <span style={styles.completedBadge}>
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M20 6L9 17l-5-5"/>
                          </svg>
                          Done
                        </span>
                      ) : (
                        <button
                          onClick={() => handleComplete(task)}
                          disabled={isCompletingThis}
                          style={{
                            ...styles.completeBtn,
                            opacity: isCompletingThis ? 0.7 : 1,
                            cursor: isCompletingThis ? 'wait' : 'pointer'
                          }}
                        >
                          {isCompletingThis ? '...' : 'Complete'}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {/* Key Actions Section */}
          <h4 style={styles.sectionTitle}>Key Actions:</h4>
          <ul style={styles.bulletList}>
            <li style={styles.bulletItem}>Click <strong>Complete</strong> to mark tasks as done</li>
            <li style={styles.bulletItem}>Click task names to view full details and send communications</li>
            <li style={styles.bulletItem}>Tasks are prioritized by urgency and due date</li>
            <li style={styles.bulletItem}>Completed tasks sync with your CRM automatically</li>
          </ul>

          {/* Outputs Section */}
          <div style={styles.outputsSection}>
            <div style={styles.fileIcon}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                <polyline points="14,2 14,8 20,8"/>
                <line x1="16" y1="13" x2="8" y2="13"/>
                <line x1="16" y1="17" x2="8" y2="17"/>
                <polyline points="10,9 9,9 8,9"/>
              </svg>
            </div>
            <div>
              <div style={{ fontWeight: 500, color: '#111827' }}>tasks_summary</div>
              <div style={{ fontSize: '13px', color: '#6b7280' }}>{tasks.length} priority tasks</div>
            </div>
            <button
              style={styles.downloadBtn}
              onClick={() => {
                const taskText = tasks.map((t, i) =>
                  `${i + 1}. ${t.title} (${t.priority})\n   Client: ${t.client || 'N/A'}\n   ${t.description || ''}\n   Due: ${t.due_date || 'N/A'}`
                ).join('\n\n');
                const blob = new Blob([`Priority Tasks Summary\n${'='.repeat(40)}\n\n${taskText}`], { type: 'text/plain' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'tasks_summary.txt';
                a.click();
                URL.revokeObjectURL(url);
              }}
            >
              Download
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default TaskPrioritiesComponent;
