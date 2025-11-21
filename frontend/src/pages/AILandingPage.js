import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { aiAPI } from '../services/api';
import './AILandingPage.css';

function AILandingPage() {
  const navigate = useNavigate();
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [userName, setUserName] = useState('');
  const [conversationHistory, setConversationHistory] = useState([]);
  const [taskListData, setTaskListData] = useState(null); // Tasks to display below button
  const [selectedTask, setSelectedTask] = useState(null);
  const chatAreaRef = useRef(null);

  useEffect(() => {
    // Get user name from token or localStorage
    const token = localStorage.getItem('token');
    if (!token) {
      navigate('/login');
      return;
    }

    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      const email = payload.sub || '';
      const name = email.split('@')[0];
      setUserName(name.charAt(0).toUpperCase() + name.slice(1));
    } catch (e) {
      setUserName('there');
    }
  }, [navigate]);

  useEffect(() => {
    if (chatAreaRef.current) {
      chatAreaRef.current.scrollTop = chatAreaRef.current.scrollHeight;
    }
  }, [messages]);

  const addMessage = (content, type, extraData = {}) => {
    setMessages(prev => [...prev, {
      id: Date.now(),
      content,
      type,
      ...extraData
    }]);
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const handleExamplePrompt = (prompt) => {
    setInputValue(prompt);
    setTimeout(() => sendMessage(prompt), 100);
  };

  const sendMessage = async (overrideMessage = null) => {
    const message = overrideMessage || inputValue.trim();
    if (!message || loading) return;

    addMessage(message, 'user');
    setInputValue('');
    setLoading(true);

    try {
      // Call the AI processing endpoint with conversation history
      const response = await aiAPI.processCommand(message, {
        conversation_context: conversationHistory
      });

      // Update conversation history
      setConversationHistory(prev => [
        ...prev,
        { role: 'user', content: message },
        { role: 'assistant', content: response.explanation || '' }
      ]);

      // Handle different response types based on intent
      if (response.intent === 'DAILY_VIEW' && response.data) {
        addMessage(response.explanation || "Here's your daily overview:", 'assistant');
        addMessage('daily_view', 'assistant', {
          isSpecialContent: true,
          contentType: 'daily_view',
          backendData: response.data
        });
      } else if (response.intent === 'SEARCH' && response.data) {
        addMessage(response.explanation || "Here are your search results:", 'assistant');
        // Show search results
        const results = response.data;
        if (results.leads?.length > 0 || results.deals?.length > 0) {
          const resultText = [
            results.leads?.length > 0 ? `Found ${results.leads.length} leads` : '',
            results.deals?.length > 0 ? `Found ${results.deals.length} deals` : ''
          ].filter(Boolean).join(', ');
          addMessage(resultText, 'assistant');
        }
      } else if (response.preview && response.action_id) {
        // Actionable command with preview
        addMessage(response.explanation || "Here's what I can do:", 'assistant', {
          preview: response.preview,
          actionId: response.action_id,
          actionType: response.intent
        });
      } else if (response.preview) {
        // Preview without action (like reports)
        addMessage(response.explanation || "Here's what I found:", 'assistant', {
          preview: response.preview,
          actionType: response.intent
        });
      } else {
        addMessage(response.explanation || "I understand your request.", 'assistant');
      }
    } catch (error) {
      console.error('AI processing error:', error);
      // For demo purposes, route to simulated responses
      routeMessage(message);
    } finally {
      setLoading(false);
    }
  };

  const routeMessage = (message) => {
    const lower = message.toLowerCase();

    if (lower.includes('today') || lower.includes('do today')) {
      showDailyView();
    } else if (lower.includes('email') && (lower.includes('all in one') || lower.includes('mortgages under management'))) {
      showEmailCampaign();
    } else if (lower.includes('update') && lower.includes('deals')) {
      showBulkUpdate();
    } else if (lower.includes('voicemail') || (lower.includes('call') && lower.includes('partners'))) {
      showVoicemailCampaign();
    } else if (lower.includes('report') || lower.includes('pipeline')) {
      showPipelineReport();
    } else {
      addMessage("I understand your request. Let me pull the relevant data from your CRM and show you what I can do.", 'assistant');
    }
  };

  const showDailyView = () => {
    // Add summary message in chat
    addMessage("I'll show you your daily overview including all tasks, follow-ups, and reconciliation items scheduled for today.", 'assistant');

    // Set task list data to display below the button
    const tasks = [
      {
        id: 1,
        title: 'Follow up on pre-approval',
        client: 'Sarah Johnson',
        stage: 'Pre-Approved',
        priority: 'HIGH',
        type: 'Follow-up Call',
        source: 'Manual Priority',
        owner: 'Loan Officer',
        dateCreated: '11/9/2025, 10:30:00 AM',
        details: 'Rate lock expires in 3 days - discuss extension options',
        dueTime: 'Today 10:00 AM',
        aiDraftedMessage: 'Hi Sarah,\n\nI wanted to reach out regarding your pre-approval...'
      },
      {
        id: 2,
        title: 'Upload missing documents',
        client: 'Mike Chen',
        stage: 'Processing',
        priority: 'MEDIUM',
        type: 'Document Upload',
        source: 'System Alert',
        owner: 'Loan Officer',
        dateCreated: '11/8/2025, 2:15:00 PM',
        details: 'Need W-2s and bank statements for underwriting',
        dueTime: 'Today 2:00 PM'
      },
      {
        id: 3,
        title: 'Schedule appraisal',
        client: 'Emily Davis',
        stage: 'Application Complete',
        priority: 'MEDIUM',
        type: 'Scheduling',
        source: 'Workflow',
        owner: 'Loan Officer',
        dateCreated: '11/7/2025, 9:00:00 AM',
        details: 'Property at 123 Oak Street ready for appraisal',
        dueTime: 'Today 4:00 PM'
      },
      {
        id: 4,
        title: 'Appraisal delay',
        client: 'John Smith',
        stage: 'Underwriting',
        priority: 'HIGH',
        type: 'Milestone Alert',
        source: 'System Alert',
        owner: 'Loan Officer',
        dateCreated: '11/10/2025, 8:00:00 AM',
        details: 'Appraisal came in $15K below purchase price'
      },
      {
        id: 5,
        title: 'Insurance missing',
        client: 'Jane Doe',
        stage: 'Clear to Close',
        priority: 'HIGH',
        type: 'Milestone Alert',
        source: 'System Alert',
        owner: 'Loan Officer',
        dateCreated: '11/10/2025, 10:00:00 AM',
        details: 'Need homeowners insurance binder before closing'
      }
    ];

    setTaskListData(tasks);
    setSelectedTask(tasks[0]);

    // Add instruction to return when completed
    setTimeout(() => {
      addMessage("Here are your tasks for today. Complete these items and come back to let me know when you're done - I'll help you with the next steps!", 'assistant');
    }, 500);
  };

  const showEmailCampaign = () => {
    addMessage('email_campaign', 'assistant', { isSpecialContent: true, contentType: 'email_campaign' });
  };

  const showBulkUpdate = () => {
    addMessage('bulk_update', 'assistant', { isSpecialContent: true, contentType: 'bulk_update' });
  };

  const showVoicemailCampaign = () => {
    addMessage('voicemail_campaign', 'assistant', { isSpecialContent: true, contentType: 'voicemail_campaign' });
  };

  const showPipelineReport = () => {
    addMessage('pipeline_report', 'assistant', { isSpecialContent: true, contentType: 'pipeline_report' });
  };

  const executeAction = async (actionId, modifications = {}) => {
    if (!actionId) {
      // Fallback for demo mode without actionId
      addMessage('Action executed successfully!', 'assistant');
      return;
    }

    try {
      addMessage('Executing action...', 'assistant');
      const result = await aiAPI.executeAction(actionId, modifications);

      if (result.success) {
        addMessage(`✅ ${result.message}`, 'assistant');
      } else {
        addMessage(`❌ ${result.message || 'Action failed'}`, 'assistant');
      }
    } catch (error) {
      console.error('Action execution error:', error);
      addMessage('Failed to execute action. Please try again.', 'assistant');
    }
  };

  // Demo mode execute (for fallback without backend)
  const executeDemoAction = (actionType) => {
    const confirmMessages = {
      email_campaign: '✅ Email sent successfully to 47 clients!',
      bulk_update: '✅ Successfully updated 14 deals. Processors have been notified.',
      voicemail_campaign: '✅ Voicemail drops initiated! All 10 calls are being placed now.',
      pipeline_report: '✅ Pipeline report generated and sent to your team!'
    };
    addMessage(confirmMessages[actionType] || '✅ Action completed successfully!', 'assistant');
  };

  const renderSpecialContent = (message) => {
    const actionId = message.actionId;
    const preview = message.preview;
    const backendData = message.backendData;

    switch (message.contentType) {
      case 'daily_view':
        return <DailyView onAction={executeDemoAction} data={backendData} />;
      case 'email_campaign':
        return (
          <EmailCampaignPreview
            preview={preview}
            onExecute={() => actionId ? executeAction(actionId) : executeDemoAction('email_campaign')}
            onEdit={() => addMessage('What changes would you like to make?', 'assistant')}
          />
        );
      case 'bulk_update':
        return (
          <BulkUpdatePreview
            preview={preview}
            onExecute={() => actionId ? executeAction(actionId) : executeDemoAction('bulk_update')}
            onEdit={() => addMessage('What would you like to modify?', 'assistant')}
          />
        );
      case 'voicemail_campaign':
        return (
          <VoicemailCampaignPreview
            preview={preview}
            onExecute={() => actionId ? executeAction(actionId) : executeDemoAction('voicemail_campaign')}
            onEdit={() => addMessage('What would you like to change in the script?', 'assistant')}
          />
        );
      case 'pipeline_report':
        return (
          <PipelineReportPreview
            preview={preview}
            onExecute={() => actionId ? executeAction(actionId) : executeDemoAction('pipeline_report')}
            onEdit={() => addMessage('How would you like to customize this report?', 'assistant')}
          />
        );
      default:
        return null;
    }
  };

  return (
    <div className="ai-landing-page">
      <div className="ai-header">
        <div className="ai-logo">✱</div>
        <h1>Back at it, {userName}</h1>
      </div>

      <div className="ai-container">
        <div className="ai-chat-area" ref={chatAreaRef}>
          {messages.length === 0 ? (
            <div className="ai-empty-state">
              <div className="ai-empty-icon">💬</div>
              <h2>What would you like to do today?</h2>
              <p>Ask me anything about your CRM data, clients, or tasks. I'll handle the rest.</p>

              <div className="ai-example-prompts">
                <button className="ai-example-prompt" onClick={() => handleExamplePrompt('What do I need to do today?')}>
                  What do I need to do today?
                </button>
                <button className="ai-example-prompt" onClick={() => handleExamplePrompt('Send an email to all mortgages under management clients about the All In One loan')}>
                  Send an email to all mortgages under management clients about the All In One loan
                </button>
                <button className="ai-example-prompt" onClick={() => handleExamplePrompt('Update all deals in underwriting to include the new appraisal waiver guidelines')}>
                  Update all deals in underwriting to include the new appraisal waiver guidelines
                </button>
                <button className="ai-example-prompt" onClick={() => handleExamplePrompt('Call my top 10 referral partners and leave a voicemail thanking them for Q4')}>
                  Call my top 10 referral partners and leave a voicemail thanking them for Q4
                </button>
                <button className="ai-example-prompt" onClick={() => handleExamplePrompt('Generate a pipeline report for deals closing this month and send to my team')}>
                  Generate a pipeline report for deals closing this month and send to my team
                </button>
              </div>
            </div>
          ) : (
            messages.map(message => (
              <div key={message.id} className={`ai-message ai-message-${message.type}`}>
                {message.isSpecialContent ? (
                  renderSpecialContent(message)
                ) : (
                  <div className="ai-message-content">{message.content}</div>
                )}
              </div>
            ))
          )}

          {loading && (
            <div className="ai-message ai-message-assistant">
              <div className="ai-typing-indicator">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          )}
        </div>

        <div className="ai-input-container">
          <button className="ai-icon-btn" title="Add attachment">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 5v14M5 12h14"/>
            </svg>
          </button>

          <button className="ai-icon-btn" title="Voice input">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
              <path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8"/>
            </svg>
          </button>

          <div className="ai-input-wrapper">
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Ask me to do something..."
              disabled={loading}
            />
          </div>

          <div className="ai-model-selector">
            <span>Sonnet 4.5</span>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M6 9l6 6 6-6"/>
            </svg>
          </div>

          <button
            className="ai-send-btn"
            onClick={() => sendMessage()}
            disabled={!inputValue.trim() || loading}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>
            </svg>
          </button>
        </div>
      </div>

      <button className="ai-back-to-crm" onClick={() => navigate('/dashboard')}>
        Back to CRM Dashboard
      </button>

      {/* Task List Display - Shows below button when tasks are available */}
      {taskListData && taskListData.length > 0 && (
        <div className="ai-task-list-container">
          <div className="ai-task-sidebar">
            <div className="ai-task-sidebar-header">
              <h3>Tasks</h3>
              <span className="ai-task-count">{taskListData.length}</span>
            </div>
            <div className="ai-task-list">
              {taskListData.map(task => (
                <div
                  key={task.id}
                  className={`ai-task-list-item ${selectedTask?.id === task.id ? 'selected' : ''}`}
                  onClick={() => setSelectedTask(task)}
                >
                  <div className="ai-task-list-icon">
                    {task.priority === 'HIGH' ? '🔴' : task.type === 'Milestone Alert' ? '⚡' : '📋'}
                  </div>
                  <div className="ai-task-list-content">
                    <div className="ai-task-list-title">{task.title}</div>
                    <div className="ai-task-list-client">{task.client}</div>
                    <div className="ai-task-list-stage">{task.stage}</div>
                  </div>
                  {task.priority === 'HIGH' && <div className="ai-task-dot high"></div>}
                  {task.priority === 'MEDIUM' && <div className="ai-task-dot medium"></div>}
                </div>
              ))}
            </div>
          </div>

          {selectedTask && (
            <div className="ai-task-detail-panel">
              <div className="ai-task-detail-header">
                <span className={`ai-task-detail-badge ${selectedTask.source === 'Manual Priority' ? 'manual' : 'system'}`}>
                  {selectedTask.source === 'Manual Priority' ? '⚙️ MANUAL PRIORITY' : '🔔 ' + selectedTask.source.toUpperCase()}
                </span>
                <h2>{selectedTask.title}</h2>
              </div>

              <div className="ai-task-detail-info">
                <div className="ai-task-detail-row">
                  <span className="ai-task-detail-label">CLIENT</span>
                  <span className="ai-task-detail-value">{selectedTask.client}</span>
                </div>
                <div className="ai-task-detail-row">
                  <span className="ai-task-detail-label">STAGE</span>
                  <span className="ai-task-detail-value">{selectedTask.stage}</span>
                </div>
                <div className="ai-task-detail-row">
                  <span className="ai-task-detail-label">PRIORITY</span>
                  <span className={`ai-priority-badge ${selectedTask.priority.toLowerCase()}`}>
                    {selectedTask.priority}
                  </span>
                </div>
                <div className="ai-task-detail-row">
                  <span className="ai-task-detail-label">SOURCE</span>
                  <span className="ai-task-detail-value">{selectedTask.source}</span>
                </div>
                <div className="ai-task-detail-row">
                  <span className="ai-task-detail-label">OWNER</span>
                  <span className="ai-task-detail-value">{selectedTask.owner}</span>
                </div>
                <div className="ai-task-detail-row">
                  <span className="ai-task-detail-label">DATE CREATED</span>
                  <span className="ai-task-detail-value">{selectedTask.dateCreated}</span>
                </div>
              </div>

              <div className="ai-task-send-via">
                <span className="ai-task-detail-label">SEND VIA</span>
                <div className="ai-send-via-buttons">
                  <button className="ai-send-via-btn active">📧 Email</button>
                  <button className="ai-send-via-btn">💬 Text</button>
                  <button className="ai-send-via-btn">📞 Phone</button>
                  <button className="ai-send-via-btn">📱 Voicemail</button>
                </div>
              </div>

              <div className="ai-train-section">
                <div className="ai-train-header">
                  <span>🎯 Train AI (Optional)</span>
                </div>
                <textarea
                  className="ai-train-input"
                  placeholder="Type instructions to teach AI how to handle similar tasks in the future... (e.g., 'Always mention our competitive rates when following up on pre-approvals')"
                />
              </div>

              {selectedTask.aiDraftedMessage && (
                <div className="ai-drafted-message">
                  <div className="ai-drafted-header">
                    <span>🤖 AI-Drafted Message</span>
                    <button className="ai-edit-message-btn">✏️ Edit Message</button>
                  </div>
                  <div className="ai-drafted-content">
                    {selectedTask.aiDraftedMessage}
                  </div>
                </div>
              )}

              <div className="ai-task-actions">
                <button className="ai-action-btn send">📧 Send via Email</button>
                <button className="ai-action-btn approve">✅ Approve AI Action</button>
                <button className="ai-action-btn snooze">⏰ Snooze</button>
                <button className="ai-action-btn delegate">👥 Delegate</button>
                <button className="ai-action-btn delete">🗑️ Delete</button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Daily View Component
function DailyView({ onAction }) {
  return (
    <div className="ai-message-content ai-special-content">
      <strong>Your Day - {new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}</strong>

      <div className="ai-daily-summary">
        <div className="ai-summary-item">
          <div className="ai-summary-number">5</div>
          <div className="ai-summary-label">Tasks</div>
        </div>
        <div className="ai-summary-item">
          <div className="ai-summary-number">2</div>
          <div className="ai-summary-label">High Priority</div>
        </div>
        <div className="ai-summary-item">
          <div className="ai-summary-number">3</div>
          <div className="ai-summary-label">Reconciliations</div>
        </div>
        <div className="ai-summary-item">
          <div className="ai-summary-number">2</div>
          <div className="ai-summary-label">Calls</div>
        </div>
      </div>

      <div className="ai-section-header">📋 Tasks</div>

      <div className="ai-task-card">
        <div className="ai-task-header">
          <span className="ai-task-priority high">high</span>
          <span className="ai-task-type">Follow-up Call</span>
        </div>
        <div className="ai-task-client">Sarah Johnson</div>
        <div className="ai-task-details">Rate lock expires in 3 days - discuss extension options</div>
        <div className="ai-task-due urgent">🕐 Today 10:00 AM</div>
      </div>

      <div className="ai-task-card">
        <div className="ai-task-header">
          <span className="ai-task-priority high">high</span>
          <span className="ai-task-type">Document Review</span>
        </div>
        <div className="ai-task-client">Michael Chen</div>
        <div className="ai-task-details">VA loan docs ready for final review before submission</div>
        <div className="ai-task-due urgent">🕐 Today 2:00 PM</div>
      </div>

      <div className="ai-task-card">
        <div className="ai-task-header">
          <span className="ai-task-priority medium">medium</span>
          <span className="ai-task-type">Pre-qualification Call</span>
        </div>
        <div className="ai-task-client">Amanda Rodriguez</div>
        <div className="ai-task-details">First-time buyer consultation - budget $450K</div>
        <div className="ai-task-due">🕐 Today 4:00 PM</div>
      </div>

      <div className="ai-section-header">⚠️ Reconciliations Needed</div>

      <div className="ai-reconciliation-card">
        <div className="ai-reconciliation-header">
          <span className="ai-reconciliation-type">Loan Processing</span>
          <span className="ai-reconciliation-status needs_attention">needs attention</span>
        </div>
        <div className="ai-reconciliation-client">Robert Taylor</div>
        <div className="ai-reconciliation-loan">Loan #LN-2024-8834</div>
        <div className="ai-reconciliation-action">Review title report discrepancies</div>
      </div>

      <div className="ai-reconciliation-card">
        <div className="ai-reconciliation-header">
          <span className="ai-reconciliation-type">Underwriting</span>
          <span className="ai-reconciliation-status needs_attention">needs attention</span>
        </div>
        <div className="ai-reconciliation-client">Lisa Anderson</div>
        <div className="ai-reconciliation-loan">Loan #LN-2024-8901</div>
        <div className="ai-reconciliation-action">Address income verification questions</div>
      </div>

      <div className="ai-quick-actions">
        <button className="ai-quick-action-btn" onClick={() => onAction('mark_reviewed')}>Mark All Reviewed</button>
        <button className="ai-quick-action-btn" onClick={() => onAction('export_calendar')}>Export to Calendar</button>
        <button className="ai-quick-action-btn" onClick={() => onAction('reprioritize')}>Re-prioritize</button>
      </div>
    </div>
  );
}

// Email Campaign Preview Component
function EmailCampaignPreview({ preview, onExecute, onEdit }) {
  // Use backend data if available, otherwise use demo data
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
    <div className="ai-message-content ai-special-content">
      I've drafted an email for {recipientCount} clients:

      <div className="ai-action-preview">
        <h3>📧 Email Preview</h3>
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

// Bulk Update Preview Component
function BulkUpdatePreview({ preview, onExecute, onEdit }) {
  return (
    <div className="ai-message-content ai-special-content">
      I found 14 deals in underwriting that need the new appraisal waiver guidelines added.

      <div className="ai-action-preview">
        <h3>📊 Bulk Deal Update</h3>
        <div className="ai-preview-content">
          Found 14 deals currently in underwriting status:<br/><br/>
          ✅ Will Update:<br/>
          • LN-2024-8901 - Lisa Anderson - Conventional<br/>
          • LN-2024-8834 - Robert Taylor - Refinance<br/>
          • LN-2024-8756 - James Wilson - FHA<br/>
          • LN-2024-9012 - Patricia White - Conventional<br/>
          • LN-2024-9088 - John Davis - VA<br/>
          ... and 9 more<br/><br/>
          📝 Update Details:<br/>
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
function VoicemailCampaignPreview({ preview, onExecute, onEdit }) {
  return (
    <div className="ai-message-content ai-special-content">
      I've identified your top 10 referral partners for Q4 2024 based on deal volume and value.

      <div className="ai-action-preview">
        <h3>📞 Voicemail Drop Campaign</h3>
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
          📋 Each voicemail will be personalized with partner name, deal count, and total volume
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
function PipelineReportPreview({ preview, onExecute, onEdit }) {
  return (
    <div className="ai-message-content ai-special-content">
      I've generated your pipeline report for December 2024 closings.

      <div className="ai-action-preview">
        <h3>📈 Pipeline Report - December 2024 Closings</h3>

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

export default AILandingPage;
