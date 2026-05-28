import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// Email Campaign Preview Component
export function EmailCampaignPreview({ preview, onExecute, onEdit }) {
  const recipients = preview?.recipients || ['47 mortgages under management clients'];
  const recipientCount = preview?.count || recipients.length || 47;
  const subject = preview?.subject || 'Unlock More Financial Flexibility with the All In One Loan';
  const body = preview?.body || `Hi [First Name],

I wanted to reach out to share an exciting loan option that could help you maximize your home's equity while maintaining financial flexibility.

The All In One loan combines your mortgage with a checking account and line of credit, allowing you to:
• Pay down your mortgage faster by applying your income directly to principal
• Access your equity when needed without a separate HELOC
• Reduce interest costs through daily balance calculations

With today's economic landscape, having this kind of financial flexibility could be valuable for your situation. I'd love to discuss whether this might be a good fit for your goals.

Would you be available for a quick call this week?

Best regards,
Tim
TL Development, LLC`;

  return (
    <div className="ai-message-content-new ai-special-content">
      I've drafted an email for {recipientCount} clients:

      <div className="ai-action-preview">
        <h3>Email Preview</h3>
        <div style={{ marginBottom: '12px' }}>
          <strong>To:</strong> {recipientCount} clients<br/>
          <strong>Subject:</strong> {subject}
        </div>
        <div className="ai-preview-content">
          {body.split('\n').map((line, i) => (
            <React.Fragment key={i}>{line}<br/></React.Fragment>
          ))}
        </div>
        <div className="ai-action-buttons">
          <button className="ai-btn ai-btn-edit" onClick={onEdit}>Edit Draft</button>
          <button className="ai-btn ai-btn-approve" onClick={onExecute}>Send to {recipientCount} Clients</button>
        </div>
      </div>
    </div>
  );
}

// Text Campaign Preview Component
export function TextCampaignPreview({ textData, onExecute, onEdit }) {
  const audience = textData?.audience || 'pre-approved leads';

  return (
    <div className="ai-message-content-new ai-special-content">
      I've prepared a text message for your {audience}. Here's the preview:

      <div className="ai-action-preview">
        <h3>Text Message Preview</h3>
        <div style={{ marginBottom: '12px' }}>
          <strong>To:</strong> 12 {audience}<br/>
          <strong>Type:</strong> SMS
        </div>

        <div className="ai-preview-content">
          <div style={{ background: '#e8f5e9', padding: '12px', borderRadius: '8px', marginBottom: '12px' }}>
            <strong style={{ color: '#2e7d32' }}>Message Preview:</strong>
          </div>
          <div style={{ background: '#f5f5f5', padding: '16px', borderRadius: '12px', border: '1px solid #e0e0e0' }}>
            Hi [First Name]!<br/><br/>
            Hope you're having a great week! Quick question - are you planning to check out any houses this weekend?<br/><br/>
            With your pre-approval in place, you're ready to make a strong offer when you find the right one. I'd love to help coordinate any showings.<br/><br/>
            Let me know if you'd like some neighborhood recommendations or want me to set up any tours!<br/><br/>
            - Tim
          </div>
        </div>

        <div className="ai-partner-list">
          <strong>Recipients Preview:</strong>
          <div className="ai-partner-item">
            <strong>Sarah Johnson</strong> - (555) 123-4567
          </div>
          <div className="ai-partner-item">
            <strong>Mike Chen</strong> - (555) 234-5678
          </div>
          <div className="ai-partner-item">
            <strong>Amanda Rodriguez</strong> - (555) 345-6789
          </div>
          <div className="ai-partner-item more">... and 9 more leads</div>
        </div>

        <div className="ai-note">
          Each message will be personalized with the lead's first name
        </div>

        <div className="ai-action-buttons">
          <button className="ai-btn ai-btn-edit" onClick={onEdit}>Edit Message</button>
          <button className="ai-btn ai-btn-approve" onClick={onExecute}>Send to 12 Leads</button>
        </div>
      </div>
    </div>
  );
}

// Bulk Update Preview Component
export function BulkUpdatePreview({ preview, onExecute, onEdit }) {
  return (
    <div className="ai-message-content-new ai-special-content">
      I found 14 deals in underwriting that need the new appraisal waiver guidelines added.

      <div className="ai-action-preview">
        <h3>Bulk Deal Update</h3>
        <div className="ai-preview-content">
          Found 14 deals currently in underwriting status:<br/><br/>
          Will Update:<br/>
          • LN-2024-8901 - Lisa Anderson - Conventional<br/>
          • LN-2024-8834 - Robert Taylor - Refinance<br/>
          • LN-2024-8756 - James Wilson - FHA<br/>
          • LN-2024-9012 - Patricia White - Conventional<br/>
          • LN-2024-9088 - John Davis - VA<br/>
          ... and 9 more<br/><br/>
          Update Details:<br/>
          Field: Guidelines Notes<br/>
          Adding: "NEW: Appraisal waiver available for LTV ≤ 80% on conv. loans per Fannie Mae 11/2025 updates. Eligible borrowers can save $500-700 and 1-2 weeks processing time."<br/><br/>
          This will be added to each deal's notes section and trigger a notification to assigned processors.
        </div>
        <div className="ai-action-buttons">
          <button className="ai-btn ai-btn-edit" onClick={onEdit}>Modify Update</button>
          <button className="ai-btn ai-btn-approve" onClick={onExecute}>Update 14 Deals</button>
        </div>
      </div>
    </div>
  );
}

// Voicemail Campaign Preview Component
export function VoicemailCampaignPreview({ preview, onExecute, onEdit }) {
  return (
    <div className="ai-message-content-new ai-special-content">
      I've identified your top 10 referral partners for Q4 2024 based on deal volume and value.

      <div className="ai-action-preview">
        <h3>Voicemail Drop Campaign</h3>
        <div className="ai-partner-list">
          <div className="ai-partner-item">
            <strong>1. Sarah Mitchell - Coldwell Banker</strong><br/>
            <span>12 deals • $4.2M funded</span>
          </div>
          <div className="ai-partner-item">
            <strong>2. Robert Chen - RE/MAX Premier</strong><br/>
            <span>9 deals • $3.1M funded</span>
          </div>
          <div className="ai-partner-item">
            <strong>3. Jennifer Lopez - Keller Williams</strong><br/>
            <span>8 deals • $2.8M funded</span>
          </div>
          <div className="ai-partner-item more">... and 7 more partners</div>
        </div>

        <div className="ai-script-preview">
          <strong>Voicemail Script:</strong>
          <p>
            Hi [Partner Name], this is Tim from TL Development. I wanted to personally reach out to thank you for an incredible Q4. Your [X] referrals totaling [Value] have been instrumental to our success. I'm looking forward to continuing our partnership in 2025. Let's grab coffee in January - I have some exciting new programs to share. Happy holidays!
          </p>
        </div>

        <div className="ai-note">
          Each voicemail will be personalized with partner name, deal count, and total volume
        </div>

        <div className="ai-action-buttons">
          <button className="ai-btn ai-btn-edit" onClick={onEdit}>Edit Script</button>
          <button className="ai-btn ai-btn-approve" onClick={onExecute}>Drop 10 Voicemails</button>
        </div>
      </div>
    </div>
  );
}

// Pipeline Report Preview Component
export function PipelineReportPreview({ preview, onExecute, onEdit }) {
  return (
    <div className="ai-message-content-new ai-special-content">
      I've generated your pipeline report for December 2024 closings.

      <div className="ai-action-preview">
        <h3>Pipeline Report - December 2024 Closings</h3>

        <div className="ai-daily-summary">
          <div className="ai-summary-item">
            <div className="ai-summary-number">18</div>
            <div className="ai-summary-label">Total Deals</div>
          </div>
          <div className="ai-summary-item">
            <div className="ai-summary-number">$6.2M</div>
            <div className="ai-summary-label">Total Volume</div>
          </div>
          <div className="ai-summary-item">
            <div className="ai-summary-number">12</div>
            <div className="ai-summary-label">Clear to Close</div>
          </div>
          <div className="ai-summary-item">
            <div className="ai-summary-number">2</div>
            <div className="ai-summary-label">At Risk</div>
          </div>
        </div>

        <div className="ai-report-breakdown">
          <strong>Loan Type Breakdown:</strong>
          <ul>
            <li>Conventional: 8 deals</li>
            <li>FHA: 5 deals</li>
            <li>VA: 3 deals</li>
            <li>Jumbo: 2 deals</li>
          </ul>
        </div>

        <div className="ai-send-to">
          <strong>Send To:</strong>
          <ul>
            <li>Your team (5 members)</li>
            <li>Format: PDF + Excel</li>
            <li>Include: Deal-by-deal breakdown, commission projections, and risk analysis</li>
          </ul>
        </div>

        <div className="ai-action-buttons">
          <button className="ai-btn ai-btn-edit" onClick={onEdit}>Customize Report</button>
          <button className="ai-btn ai-btn-approve" onClick={onExecute}>Generate & Send</button>
        </div>
      </div>
    </div>
  );
}

// Chat Response Component - displays all AI responses in sidebar
export function ChatResponseComponent({ content }) {
  return (
    <div className="ai-message-content-new ai-special-content">
      <div className="ai-action-preview chat-response">
        <div className="ai-chat-response-content">
          <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>{content}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}

// Task Priorities Component - Claude.ai style with table layout
export function TaskPrioritiesComponent({ content, tasks, onCompleteTask, onViewDetails, onSnoozeTask }) {
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

  const getPriorityBadgeStyle = (priority) => {
    const colors = {
      'URGENT': { bg: '#fef2f2', text: '#dc2626', border: '#fecaca' },
      'HIGH': { bg: '#fff7ed', text: '#ea580c', border: '#fed7aa' },
      'MEDIUM': { bg: '#fefce8', text: '#ca8a04', border: '#fef08a' },
      'LOW': { bg: '#f0fdf4', text: '#16a34a', border: '#bbf7d0' }
    };
    return colors[priority?.toUpperCase()] || { bg: '#f3f4f6', text: '#6b7280', border: '#e5e7eb' };
  };

  // Styles matching Claude.ai
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

  return (
    <div className="ai-message-content-new ai-special-content" style={styles.container}>
      {/* AI Response Text */}
      <div className="ai-chat-response-content">
        <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>{content}</ReactMarkdown>
      </div>

      {tasks && tasks.length > 0 && (
        <div style={styles.card}>
          {/* Tasks Table - Claude.ai style */}
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
                // Generate and download task summary
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

// Accountability Review Component
export function AccountabilityReviewComponent({ content }) {
  // Parse the content to extract sections
  const sections = content.split('\n\n').filter(s => s.trim());

  return (
    <div className="ai-message-content-new ai-special-content">
      <div className="ai-action-preview accountability-review">
        <h3>📊 Accountability Review</h3>

        <div className="ai-review-content">
          {sections.map((section, index) => {
            // Check if this is a header section
            if (section.includes(':') && !section.includes('•')) {
              const [header, ...rest] = section.split(':');
              return (
                <div key={index} className="ai-review-section">
                  <h4>{header.trim()}</h4>
                  <p>{rest.join(':').trim()}</p>
                </div>
              );
            }

            // Check if this is a bullet list
            if (section.includes('•') || section.includes('-')) {
              const lines = section.split('\n');
              return (
                <div key={index} className="ai-review-section">
                  <ul>
                    {lines.map((line, i) => {
                      const cleanLine = line.replace(/^[•\-]\s*/, '').trim();
                      if (cleanLine) {
                        return <li key={i}>{cleanLine}</li>;
                      }
                      return null;
                    })}
                  </ul>
                </div>
              );
            }

            // Regular paragraph
            return (
              <div key={index} className="ai-review-section">
                <p>{section}</p>
              </div>
            );
          })}
        </div>

        <div className="ai-review-actions">
          <div className="ai-note">
            💡 <strong>Tip:</strong> Focus on moving leads from NEW stage to later stages, and completing pending tasks to improve your metrics.
          </div>
        </div>
      </div>
    </div>
  );
}

// Lead Preview Component for Screenshot Parsing
export function LeadPreviewComponent({ leadData, onConfirm, onCancel }) {
  return (
    <div className="ai-message-content-new ai-special-content">
      I found the following lead information from the screenshot:

      <div className="ai-action-preview">
        <h3>Lead Information</h3>
        <div className="ai-lead-preview-data">
          {leadData.first_name && (
            <div className="ai-lead-field">
              <strong>First Name:</strong> {leadData.first_name}
            </div>
          )}
          {leadData.last_name && (
            <div className="ai-lead-field">
              <strong>Last Name:</strong> {leadData.last_name}
            </div>
          )}
          {leadData.email && (
            <div className="ai-lead-field">
              <strong>Email:</strong> {leadData.email}
            </div>
          )}
          {leadData.phone && (
            <div className="ai-lead-field">
              <strong>Phone:</strong> {leadData.phone}
            </div>
          )}
          {leadData.referral_source && (
            <div className="ai-lead-field">
              <strong>Referral Source:</strong> {leadData.referral_source}
            </div>
          )}
          {leadData.property_address && (
            <div className="ai-lead-field">
              <strong>Property Address:</strong> {leadData.property_address}
            </div>
          )}
          {leadData.loan_type && (
            <div className="ai-lead-field">
              <strong>Loan Type:</strong> {leadData.loan_type}
            </div>
          )}
          {leadData.notes && (
            <div className="ai-lead-field">
              <strong>Notes:</strong> {leadData.notes}
            </div>
          )}
        </div>

        <div className="ai-note">
          This lead will be created in the <strong>"Attempted Contact"</strong> stage
        </div>

        <div className="ai-action-buttons">
          <button className="ai-btn ai-btn-edit" onClick={onCancel}>Cancel</button>
          <button className="ai-btn ai-btn-approve" onClick={onConfirm}>Create Lead</button>
        </div>
      </div>
    </div>
  );
}
