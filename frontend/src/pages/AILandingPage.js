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
  const [actionContext, setActionContext] = useState({}); // Store action previews for context
  const [taskListData, setTaskListData] = useState(null); // Tasks to display below button
  const [selectedTask, setSelectedTask] = useState(null);
  const [tasksCompleted, setTasksCompleted] = useState(false); // Track if user completed tasks
  const [selectedSendMethod, setSelectedSendMethod] = useState('email'); // Track selected send method
  const [editingMessage, setEditingMessage] = useState(false);
  const [editedMessage, setEditedMessage] = useState('');
  const chatAreaRef = useRef(null);

  // Session ID for permanent memory - persists to localStorage
  const [sessionId, setSessionId] = useState(() => {
    const stored = localStorage.getItem('ai_session_id');
    if (stored) return stored;
    const newId = crypto.randomUUID();
    localStorage.setItem('ai_session_id', newId);
    return newId;
  });

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
      // Call the AI processing endpoint with FULL conversation history and session_id for permanent memory
      const response = await aiAPI.processCommand(message, {
        session_id: sessionId, // For permanent memory tracking
        conversation_context: conversationHistory.slice(-20), // Send last 20 messages
        action_context: actionContext, // Include all action previews for context
        current_state: {
          last_action_id: Object.keys(actionContext).slice(-1)[0] || null,
          total_actions: Object.keys(actionContext).length
        }
      });

      // Update session ID if server returns a new one
      if (response.session_id && response.session_id !== sessionId) {
        setSessionId(response.session_id);
        localStorage.setItem('ai_session_id', response.session_id);
      }

      // Build detailed assistant response for history
      let historyContent = response.explanation || '';

      // If there's an action, add detailed context to history
      if (response.action_id && response.preview) {
        historyContent += `\n[Action ${response.action_id}: ${response.intent} - Preview: ${JSON.stringify(response.preview)}]`;

        // Store action context for future reference
        setActionContext(prev => ({
          ...prev,
          [response.action_id]: {
            intent: response.intent,
            preview: response.preview,
            timestamp: new Date().toISOString(),
            status: 'previewed'
          }
        }));
      }

      // Update conversation history with full context
      setConversationHistory(prev => [
        ...prev,
        { role: 'user', content: message },
        {
          role: 'assistant',
          content: historyContent,
          action_id: response.action_id || null,
          intent: response.intent || null
        }
      ]);

      // Handle different response types based on intent
      if (response.intent === 'DAILY_VIEW' && response.data) {
        // Use the real data from the response
        showDailyViewWithData(response.data, response.explanation);
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

    // Handle task completion
    if ((lower.includes('done') || lower.includes('completed') || lower.includes('finished')) &&
        (lower.includes('task') || lower.includes('all'))) {
      handleTasksCompleted();
    }
    // Handle "what's next" after task completion
    else if (lower.includes('next') || lower.includes("what's next") || lower.includes('whats next')) {
      if (tasksCompleted) {
        showNextPriorities();
      } else {
        showDailyView();
      }
    }
    else if (lower.includes('today') || lower.includes('do today') || lower.includes('task') || lower.includes('to do') || lower.includes('todo')) {
      showDailyView();
    } else if (lower.includes('email') && (lower.includes('all in one') || lower.includes('mortgages under management'))) {
      showEmailCampaign();
    } else if (lower.includes('text') || lower.includes('sms') || (lower.includes('message') && !lower.includes('voicemail'))) {
      showTextCampaign(message);
    } else if (lower.includes('update') && lower.includes('deals')) {
      showBulkUpdate();
    } else if (lower.includes('voicemail') || (lower.includes('call') && lower.includes('partners'))) {
      showVoicemailCampaign();
    } else if (lower.includes('report') || lower.includes('pipeline')) {
      showPipelineReport();
    } else {
      // Default to showing daily view with tasks for any unrecognized query
      addMessage("Let me show you your current tasks and priorities:", 'assistant');
      showDailyView();
    }
  };

  const handleTasksCompleted = () => {
    setTasksCompleted(true);
    setTaskListData(null); // Clear the task list
    setSelectedTask(null);
    addMessage("Great job! I've marked all of today's tasks as completed. You're making excellent progress!", 'assistant');

    setTimeout(() => {
      addMessage("When you're ready, just ask 'what's next?' and I'll show you your upcoming priorities and opportunities.", 'assistant');
    }, 500);
  };

  const showNextPriorities = () => {
    addMessage("Now that you've completed today's tasks, here are your next priorities:", 'assistant');

    // Set different tasks - upcoming priorities
    const nextTasks = [
      {
        id: 101,
        title: 'Rate lock opportunity',
        client: 'Jennifer Martinez',
        stage: 'Pre-Approved',
        priority: 'HIGH',
        type: 'Opportunity',
        source: 'AI Recommendation',
        owner: 'Loan Officer',
        dateCreated: 'Just now',
        details: 'Rates dropped 0.25% - great time to lock for 3 pre-approved clients',
        dueTime: 'Tomorrow 9:00 AM',
        aiDraftedMessage: 'Hi Jennifer,\n\nGreat news! Interest rates have dropped, and I wanted to reach out about locking in your rate...'
      },
      {
        id: 102,
        title: 'Nurture cold leads',
        client: '8 leads inactive 30+ days',
        stage: 'Lead',
        priority: 'MEDIUM',
        type: 'Campaign',
        source: 'AI Recommendation',
        owner: 'Loan Officer',
        dateCreated: 'Just now',
        details: 'Re-engagement campaign for leads that have gone cold',
        dueTime: 'This week'
      },
      {
        id: 103,
        title: 'Review denied applications',
        client: '3 denials this month',
        stage: 'Review',
        priority: 'LOW',
        type: 'Analysis',
        source: 'Monthly Review',
        owner: 'Loan Officer',
        dateCreated: 'Just now',
        details: 'Analyze denial reasons and identify improvement opportunities',
        dueTime: 'Friday'
      }
    ];

    setTaskListData(nextTasks);
    setSelectedTask(nextTasks[0]);
    setTasksCompleted(false); // Reset for next cycle

    setTimeout(() => {
      addMessage("These are proactive opportunities to grow your pipeline. Let me know which one you'd like to tackle first!", 'assistant');
    }, 500);
  };

  const showDailyViewWithData = (data, explanation) => {
    // Add the AI's explanation
    addMessage(explanation || "Here's your daily overview:", 'assistant');

    // Convert API data to task list format
    const tasks = [];
    let taskId = 1;

    // Add follow-up items as tasks
    if (data.follow_ups) {
      data.follow_ups.forEach(followUp => {
        followUp.items?.forEach(item => {
          tasks.push({
            id: taskId++,
            title: `${followUp.type}`,
            client: item,
            stage: followUp.type,
            priority: followUp.priority === 'High' ? 'HIGH' : 'MEDIUM',
            type: 'Follow-up',
            source: 'CRM Data',
            owner: 'Loan Officer',
            dateCreated: new Date().toLocaleString(),
            details: `${followUp.type} - ${item}`,
            dueTime: 'Today'
          });
        });
      });
    }

    // Add reconciliation items as tasks
    if (data.reconciliations) {
      data.reconciliations.forEach(recon => {
        recon.items?.forEach(item => {
          tasks.push({
            id: taskId++,
            title: recon.type,
            client: item,
            stage: 'Pipeline',
            priority: 'HIGH',
            type: 'Reconciliation',
            source: 'System Alert',
            owner: 'Loan Officer',
            dateCreated: new Date().toLocaleString(),
            details: `${recon.type} - ${item}`
          });
        });
      });
    }

    // If no tasks found, show summary message
    if (tasks.length === 0) {
      // Handle both field naming conventions from AI
      const activeLeads = data.summary?.active_leads || data.summary?.leads_needing_attention || 0;
      const loansInPipeline = data.summary?.loans_in_pipeline || data.summary?.deals_in_pipeline || 0;
      const pipelineVolume = data.summary?.pipeline_volume || '$0';
      addMessage(`Your pipeline: ${activeLeads} active leads, ${loansInPipeline} loans in pipeline (${pipelineVolume})`, 'assistant');
    } else {
      setTaskListData(tasks);
      setSelectedTask(tasks[0]);

      setTimeout(() => {
        addMessage(`You have ${tasks.length} items to review. Complete these and let me know when you're done!`, 'assistant');
      }, 500);
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

  const showTextCampaign = (originalMessage) => {
    // Extract context from the original message
    const lower = originalMessage.toLowerCase();
    let audience = 'pre-approved leads';
    let messageContext = 'weekend house hunting plans';

    if (lower.includes('pre-approv')) {
      audience = 'pre-approved leads';
    }
    if (lower.includes('weekend') || lower.includes('house')) {
      messageContext = 'weekend house hunting plans';
    }

    addMessage('text_campaign', 'assistant', {
      isSpecialContent: true,
      contentType: 'text_campaign',
      textData: {
        audience,
        messageContext
      }
    });
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
      const result = await aiAPI.executeAction(actionId, modifications, sessionId);

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
      text_campaign: '✅ Text messages sent successfully to 12 pre-approved leads!',
      bulk_update: '✅ Successfully updated 14 deals. Processors have been notified.',
      voicemail_campaign: '✅ Voicemail drops initiated! All 10 calls are being placed now.',
      pipeline_report: '✅ Pipeline report generated and sent to your team!'
    };
    addMessage(confirmMessages[actionType] || '✅ Action completed successfully!', 'assistant');
  };

  // Task action handlers
  const handleSendViaEmail = async () => {
    if (!selectedTask) return;
    const message = editingMessage ? editedMessage : selectedTask.aiDraftedMessage;
    addMessage(`📧 Sending email to ${selectedTask.client}...`, 'assistant');

    // Simulate API call
    setTimeout(() => {
      addMessage(`✅ Email sent successfully to ${selectedTask.client}!`, 'assistant');
      // Remove task from list
      removeTaskFromList(selectedTask.id);
    }, 1000);
  };

  const handleApproveAIAction = async () => {
    if (!selectedTask) return;
    addMessage(`✅ Approving AI action for "${selectedTask.title}"...`, 'assistant');

    // Execute the AI's recommended action based on send method
    setTimeout(() => {
      const methodMessages = {
        email: `📧 Email sent to ${selectedTask.client}`,
        text: `💬 Text message sent to ${selectedTask.client}`,
        phone: `📞 Call initiated to ${selectedTask.client}`,
        voicemail: `📱 Voicemail dropped for ${selectedTask.client}`
      };
      addMessage(`✅ Action completed! ${methodMessages[selectedSendMethod]}`, 'assistant');
      removeTaskFromList(selectedTask.id);
    }, 1000);
  };

  const handleSnooze = () => {
    if (!selectedTask) return;
    // Show snooze options
    addMessage(`⏰ Snoozing "${selectedTask.title}". When would you like to be reminded?\n\n• 1 hour\n• 3 hours\n• Tomorrow morning\n• Next week`, 'assistant');

    // For demo, snooze for "later today"
    setTimeout(() => {
      addMessage(`✅ Task snoozed! I'll remind you about "${selectedTask.title}" in 3 hours.`, 'assistant');
      removeTaskFromList(selectedTask.id);
    }, 1500);
  };

  const handleDelegate = () => {
    if (!selectedTask) return;
    addMessage(`👥 Delegating "${selectedTask.title}". Select a team member:\n\n• John (Processor)\n• Maria (Assistant)\n• David (Junior LO)`, 'assistant');

    // For demo, delegate to a team member
    setTimeout(() => {
      addMessage(`✅ Task delegated to Maria! She'll receive a notification with all the details.`, 'assistant');
      removeTaskFromList(selectedTask.id);
    }, 1500);
  };

  const handleDeleteTask = () => {
    if (!selectedTask) return;
    addMessage(`🗑️ Are you sure you want to delete "${selectedTask.title}"? This action cannot be undone.`, 'assistant');

    // For demo, confirm deletion
    setTimeout(() => {
      addMessage(`✅ Task deleted successfully.`, 'assistant');
      removeTaskFromList(selectedTask.id);
    }, 1000);
  };

  const handleEditMessage = () => {
    if (selectedTask?.aiDraftedMessage) {
      setEditedMessage(selectedTask.aiDraftedMessage);
      setEditingMessage(true);
    }
  };

  const handleSaveMessage = () => {
    setEditingMessage(false);
    addMessage('✅ Message updated successfully!', 'assistant');
  };

  const removeTaskFromList = (taskId) => {
    setTaskListData(prev => {
      const updated = prev.filter(t => t.id !== taskId);
      if (updated.length === 0) {
        setSelectedTask(null);
        addMessage("🎉 Great job! You've completed all your tasks. Ask 'what's next?' for your upcoming priorities.", 'assistant');
      } else {
        setSelectedTask(updated[0]);
      }
      return updated;
    });
  };

  const handleSendMethodChange = (method) => {
    setSelectedSendMethod(method);
  };

  const renderSpecialContent = (message) => {
    const actionId = message.actionId;
    const preview = message.preview;
    const backendData = message.backendData;

    switch (message.contentType) {
      case 'email_campaign':
        return (
          <EmailCampaignPreview
            preview={preview}
            onExecute={() => actionId ? executeAction(actionId) : executeDemoAction('email_campaign')}
            onEdit={() => addMessage('What changes would you like to make?', 'assistant')}
          />
        );
      case 'text_campaign':
        return (
          <TextCampaignPreview
            textData={message.textData}
            onExecute={() => actionId ? executeAction(actionId) : executeDemoAction('text_campaign')}
            onEdit={() => addMessage('What would you like to change in the message?', 'assistant')}
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
                  <button
                    className={`ai-send-via-btn ${selectedSendMethod === 'email' ? 'active' : ''}`}
                    onClick={() => handleSendMethodChange('email')}
                  >📧 Email</button>
                  <button
                    className={`ai-send-via-btn ${selectedSendMethod === 'text' ? 'active' : ''}`}
                    onClick={() => handleSendMethodChange('text')}
                  >💬 Text</button>
                  <button
                    className={`ai-send-via-btn ${selectedSendMethod === 'phone' ? 'active' : ''}`}
                    onClick={() => handleSendMethodChange('phone')}
                  >📞 Phone</button>
                  <button
                    className={`ai-send-via-btn ${selectedSendMethod === 'voicemail' ? 'active' : ''}`}
                    onClick={() => handleSendMethodChange('voicemail')}
                  >📱 Voicemail</button>
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
                    {editingMessage ? (
                      <button className="ai-edit-message-btn" onClick={handleSaveMessage}>💾 Save</button>
                    ) : (
                      <button className="ai-edit-message-btn" onClick={handleEditMessage}>✏️ Edit Message</button>
                    )}
                  </div>
                  {editingMessage ? (
                    <textarea
                      className="ai-drafted-content-edit"
                      value={editedMessage}
                      onChange={(e) => setEditedMessage(e.target.value)}
                      rows={6}
                    />
                  ) : (
                    <div className="ai-drafted-content">
                      {selectedTask.aiDraftedMessage}
                    </div>
                  )}
                </div>
              )}

              <div className="ai-task-actions">
                <button className="ai-action-btn send" onClick={handleSendViaEmail}>📧 Send via Email</button>
                <button className="ai-action-btn approve" onClick={handleApproveAIAction}>✅ Approve AI Action</button>
                <button className="ai-action-btn snooze" onClick={handleSnooze}>⏰ Snooze</button>
                <button className="ai-action-btn delegate" onClick={handleDelegate}>👥 Delegate</button>
                <button className="ai-action-btn delete" onClick={handleDeleteTask}>🗑️ Delete</button>
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

// Text Campaign Preview Component
function TextCampaignPreview({ textData, onExecute, onEdit }) {
  const audience = textData?.audience || 'pre-approved leads';

  return (
    <div className="ai-message-content ai-special-content">
      I've prepared a text message for your {audience}. Here's the preview:

      <div className="ai-action-preview">
        <h3>💬 Text Message Preview</h3>
        <div style={{ marginBottom: '12px' }}>
          <strong>To:</strong> 12 {audience}<br/>
          <strong>Type:</strong> SMS
        </div>

        <div className="ai-preview-content">
          <div style={{ background: '#e8f5e9', padding: '12px', borderRadius: '8px', marginBottom: '12px' }}>
            <strong style={{ color: '#2e7d32' }}>📱 Message Preview:</strong>
          </div>
          <div style={{ background: '#f5f5f5', padding: '16px', borderRadius: '12px', border: '1px solid #e0e0e0' }}>
            Hi [First Name]! 👋<br/><br/>
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
          📋 Each message will be personalized with the lead's first name
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
