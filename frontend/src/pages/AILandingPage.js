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
  const [actionContext, setActionContext] = useState({});
  const [taskListData, setTaskListData] = useState(null);
  const [selectedTask, setSelectedTask] = useState(null);
  const [tasksCompleted, setTasksCompleted] = useState(false);
  const [selectedSendMethod, setSelectedSendMethod] = useState('email');
  const [editingMessage, setEditingMessage] = useState(false);
  const [editedMessage, setEditedMessage] = useState('');
  const [parsedLeadData, setParsedLeadData] = useState(null);
  const [isParsingImage, setIsParsingImage] = useState(false);

  // New state for redesigned features
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarView, setSidebarView] = useState('chats'); // 'chats', 'reports', 'suggestions'
  const [chatHistory, setChatHistory] = useState(() => {
    const stored = localStorage.getItem('ai_chat_history');
    return stored ? JSON.parse(stored) : [];
  });
  const [searchQuery, setSearchQuery] = useState('');
  const [reports, setReports] = useState(() => {
    const stored = localStorage.getItem('ai_reports');
    return stored ? JSON.parse(stored) : [];
  });
  const [projects, setProjects] = useState(() => {
    const stored = localStorage.getItem('ai_projects');
    return stored ? JSON.parse(stored) : [];
  });
  const [contextMenu, setContextMenu] = useState({ visible: false, x: 0, y: 0, chatId: null });
  const [selectedPermission, setSelectedPermission] = useState('all');
  const [userPermissions, setUserPermissions] = useState(['all', 'leads', 'loans', 'tasks', 'reports']);
  const [isListening, setIsListening] = useState(false);
  const [dividerPosition, setDividerPosition] = useState(50); // percentage
  const [isDragging, setIsDragging] = useState(false);

  const chatAreaRef = useRef(null);
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);
  const recognitionRef = useRef(null);
  const containerRef = useRef(null);

  // Session ID for permanent memory
  const [sessionId, setSessionId] = useState(() => {
    const stored = localStorage.getItem('ai_session_id');
    if (stored) return stored;
    const newId = crypto.randomUUID();
    localStorage.setItem('ai_session_id', newId);
    return newId;
  });

  // Save chat history when messages change
  useEffect(() => {
    if (messages.length > 0) {
      const currentChat = {
        id: sessionId,
        title: messages[0]?.content?.substring(0, 50) + '...' || 'New Chat',
        messages: messages,
        timestamp: new Date().toISOString(),
        isProject: false
      };

      setChatHistory(prev => {
        const existing = prev.findIndex(c => c.id === sessionId);
        if (existing >= 0) {
          const updated = [...prev];
          updated[existing] = currentChat;
          return updated;
        }
        return [currentChat, ...prev];
      });
    }
  }, [messages, sessionId]);

  // Persist to localStorage
  useEffect(() => {
    localStorage.setItem('ai_chat_history', JSON.stringify(chatHistory));
  }, [chatHistory]);

  useEffect(() => {
    localStorage.setItem('ai_reports', JSON.stringify(reports));
  }, [reports]);

  useEffect(() => {
    localStorage.setItem('ai_projects', JSON.stringify(projects));
  }, [projects]);

  useEffect(() => {
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

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 200) + 'px';
    }
  }, [inputValue]);

  // Close context menu on click outside
  useEffect(() => {
    const handleClick = () => setContextMenu({ visible: false, x: 0, y: 0, chatId: null });
    document.addEventListener('click', handleClick);
    return () => document.removeEventListener('click', handleClick);
  }, []);

  // Handle divider drag
  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!isDragging || !containerRef.current) return;
      const container = containerRef.current;
      const rect = container.getBoundingClientRect();
      const newPosition = ((e.clientX - rect.left) / rect.width) * 100;
      setDividerPosition(Math.min(Math.max(newPosition, 20), 80));
    };

    const handleMouseUp = () => {
      setIsDragging(false);
    };

    if (isDragging) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging]);

  const handleDividerMouseDown = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleCopyContent = async () => {
    const content = messages.map(msg => {
      const prefix = msg.type === 'user' ? 'You: ' : 'Assistant: ';
      return prefix + msg.content;
    }).join('\n\n');

    try {
      await navigator.clipboard.writeText(content);
      alert('Content copied to clipboard!');
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const handleClearContent = () => {
    setMessages([]);
    setTaskListData(null);
    setSelectedTask(null);
    setConversationHistory([]);
    setActionContext({});
  };

  // Initialize speech recognition
  useEffect(() => {
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      recognitionRef.current = new SpeechRecognition();
      recognitionRef.current.continuous = true;
      recognitionRef.current.interimResults = true;
      recognitionRef.current.lang = 'en-US';

      recognitionRef.current.onresult = (event) => {
        let finalTranscript = '';
        let interimTranscript = '';

        for (let i = event.resultIndex; i < event.results.length; i++) {
          const transcript = event.results[i][0].transcript;
          if (event.results[i].isFinal) {
            finalTranscript += transcript;
          } else {
            interimTranscript += transcript;
          }
        }

        if (finalTranscript) {
          setInputValue(prev => prev + finalTranscript);
        }
      };

      recognitionRef.current.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
        setIsListening(false);
      };

      recognitionRef.current.onend = () => {
        setIsListening(false);
      };
    }

    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
    };
  }, []);

  const toggleSpeechRecognition = () => {
    if (!recognitionRef.current) {
      alert('Speech recognition is not supported in your browser. Please use Chrome or Edge.');
      return;
    }

    if (isListening) {
      recognitionRef.current.stop();
      setIsListening(false);
    } else {
      recognitionRef.current.start();
      setIsListening(true);
    }
  };

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

  const handleNewChat = () => {
    const newId = crypto.randomUUID();
    setSessionId(newId);
    localStorage.setItem('ai_session_id', newId);
    setMessages([]);
    setTaskListData(null);
    setSelectedTask(null);
    setConversationHistory([]);
    setActionContext({});
  };

  const handleLoadChat = (chat) => {
    setSessionId(chat.id);
    localStorage.setItem('ai_session_id', chat.id);
    setMessages(chat.messages || []);
  };

  const handleContextMenu = (e, chatId) => {
    e.preventDefault();
    setContextMenu({
      visible: true,
      x: e.clientX,
      y: e.clientY,
      chatId
    });
  };

  const handleSaveAsProject = () => {
    const chat = chatHistory.find(c => c.id === contextMenu.chatId);
    if (chat) {
      const projectName = prompt('Enter project name:', chat.title);
      if (projectName) {
        const project = {
          ...chat,
          title: projectName,
          isProject: true,
          savedAt: new Date().toISOString()
        };
        setProjects(prev => [project, ...prev]);
      }
    }
    setContextMenu({ visible: false, x: 0, y: 0, chatId: null });
  };

  const handleDeleteChat = () => {
    setChatHistory(prev => prev.filter(c => c.id !== contextMenu.chatId));
    setContextMenu({ visible: false, x: 0, y: 0, chatId: null });
  };

  const handleFileUpload = async (e) => {
    const files = e.target.files;
    if (files.length > 0) {
      const file = files[0];
      const isImage = file.type.startsWith('image/');

      if (isImage) {
        // Process image for lead extraction
        setIsParsingImage(true);
        addMessage(`Analyzing screenshot: ${file.name}...`, 'user');

        try {
          const result = await aiAPI.parseScreenshot(file);

          if (result.success && result.lead_data) {
            setParsedLeadData(result.lead_data);
            addMessage(
              `I found the following lead information in the screenshot. Would you like me to create this lead?`,
              'assistant',
              {
                isSpecialContent: true,
                contentType: 'lead_preview',
                leadData: result.lead_data
              }
            );
          } else {
            addMessage(
              result.message || "I couldn't extract lead information from this image. Please try a clearer screenshot.",
              'assistant'
            );
          }
        } catch (error) {
          console.error('Screenshot parsing error:', error);
          addMessage(
            "Failed to process the screenshot. Please try again or enter the lead information manually.",
            'assistant'
          );
        } finally {
          setIsParsingImage(false);
        }
      } else {
        const fileNames = Array.from(files).map(f => f.name).join(', ');
        addMessage(`Uploaded: ${fileNames}`, 'system');
      }
    }
    // Reset file input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleCreateLead = async () => {
    if (!parsedLeadData) return;

    try {
      addMessage('Creating lead...', 'assistant');
      const result = await aiAPI.createLeadFromScreenshot(parsedLeadData);

      if (result.success) {
        addMessage(
          `Lead created successfully! ${parsedLeadData.first_name} ${parsedLeadData.last_name} has been added to your pipeline in the "Attempted Contact" stage.`,
          'assistant'
        );
        setParsedLeadData(null);
      } else {
        addMessage(result.message || 'Failed to create lead. Please try again.', 'assistant');
      }
    } catch (error) {
      console.error('Lead creation error:', error);
      addMessage('Failed to create lead. Please try again.', 'assistant');
    }
  };

  const handleCancelLead = () => {
    setParsedLeadData(null);
    addMessage('Lead creation cancelled.', 'assistant');
  };

  const handleExamplePrompt = (prompt) => {
    setInputValue(prompt);
    setTimeout(() => sendMessage(prompt), 100);
  };

  const filteredChats = chatHistory.filter(chat =>
    chat.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    chat.messages?.some(m => m.content?.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const sendMessage = async (overrideMessage = null) => {
    const message = overrideMessage || inputValue.trim();
    if (!message || loading) return;

    addMessage(message, 'user');
    setInputValue('');
    setLoading(true);

    try {
      const response = await aiAPI.processCommand(message, {
        session_id: sessionId,
        conversation_context: conversationHistory.slice(-20),
        action_context: actionContext,
        permission_scope: selectedPermission,
        current_state: {
          last_action_id: Object.keys(actionContext).slice(-1)[0] || null,
          total_actions: Object.keys(actionContext).length
        }
      });

      if (response.session_id && response.session_id !== sessionId) {
        setSessionId(response.session_id);
        localStorage.setItem('ai_session_id', response.session_id);
      }

      let historyContent = response.explanation || '';

      if (response.action_id && response.preview) {
        historyContent += `\n[Action ${response.action_id}: ${response.intent} - Preview: ${JSON.stringify(response.preview)}]`;

        setActionContext(prev => ({
          ...prev,
          [response.action_id]: {
            intent: response.intent,
            preview: response.preview,
            timestamp: new Date().toISOString(),
            status: 'previewed'
          }
        }));

        // Save as report if it's a report type
        if (response.intent?.includes('REPORT') || response.intent?.includes('PIPELINE')) {
          const report = {
            id: Date.now(),
            title: message.substring(0, 50),
            data: response.preview,
            createdAt: new Date().toISOString()
          };
          setReports(prev => [report, ...prev.slice(0, 19)]);
        }
      }

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

      if (response.intent === 'DAILY_VIEW' && response.data) {
        showDailyViewWithData(response.data, response.explanation);
      } else if (response.intent === 'SEARCH' && response.data) {
        addMessage(response.explanation || "Here are your search results:", 'assistant');
        const results = response.data;
        if (results.leads?.length > 0 || results.deals?.length > 0) {
          const resultText = [
            results.leads?.length > 0 ? `Found ${results.leads.length} leads` : '',
            results.deals?.length > 0 ? `Found ${results.deals.length} deals` : ''
          ].filter(Boolean).join(', ');
          addMessage(resultText, 'assistant');
        }
      } else if (response.preview && response.action_id) {
        addMessage(response.explanation || "Here's what I can do:", 'assistant', {
          preview: response.preview,
          actionId: response.action_id,
          actionType: response.intent
        });
      } else if (response.preview) {
        addMessage(response.explanation || "Here's what I found:", 'assistant', {
          preview: response.preview,
          actionType: response.intent
        });
      } else {
        addMessage(response.explanation || "I understand your request.", 'assistant');
      }
    } catch (error) {
      console.error('AI processing error:', error);
      routeMessage(message);
    } finally {
      setLoading(false);
    }
  };

  const routeMessage = (message) => {
    const lower = message.toLowerCase();

    if ((lower.includes('done') || lower.includes('completed') || lower.includes('finished')) &&
        (lower.includes('task') || lower.includes('all'))) {
      handleTasksCompleted();
    } else if (lower.includes('next') || lower.includes("what's next") || lower.includes('whats next')) {
      if (tasksCompleted) {
        showNextPriorities();
      } else {
        showDailyView();
      }
    } else if (lower.includes('today') || lower.includes('do today') || lower.includes('task') || lower.includes('to do') || lower.includes('todo')) {
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
      addMessage("Let me show you your current tasks and priorities:", 'assistant');
      showDailyView();
    }
  };

  const handleTasksCompleted = () => {
    setTasksCompleted(true);
    setTaskListData(null);
    setSelectedTask(null);
    addMessage("Great job! I've marked all of today's tasks as completed. You're making excellent progress!", 'assistant');

    setTimeout(() => {
      addMessage("When you're ready, just ask 'what's next?' and I'll show you your upcoming priorities and opportunities.", 'assistant');
    }, 500);
  };

  const showNextPriorities = () => {
    addMessage("Now that you've completed today's tasks, here are your next priorities:", 'assistant');

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
    setTasksCompleted(false);

    setTimeout(() => {
      addMessage("These are proactive opportunities to grow your pipeline. Let me know which one you'd like to tackle first!", 'assistant');
    }, 500);
  };

  const showDailyViewWithData = (data, explanation) => {
    addMessage(explanation || "Here's your daily overview:", 'assistant');

    const tasks = [];
    let taskId = 1;

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

    if (tasks.length === 0) {
      const activeLeads = data.summary?.active_leads || data.summary?.leads_needing_attention || data.summary?.total_leads || 0;
      const loansInPipeline = data.summary?.loans_in_pipeline || data.summary?.deals_in_pipeline || data.summary?.active_deals || data.summary?.deals_in_progress || data.summary?.active_loans || 0;
      const pipelineVolume = data.summary?.pipeline_volume || data.summary?.pipeline_value || '$0';
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
    addMessage("I'll show you your daily overview including all tasks, follow-ups, and reconciliation items scheduled for today.", 'assistant');

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

    setTimeout(() => {
      addMessage("Here are your tasks for today. Complete these items and come back to let me know when you're done - I'll help you with the next steps!", 'assistant');
    }, 500);
  };

  const showEmailCampaign = () => {
    addMessage('email_campaign', 'assistant', { isSpecialContent: true, contentType: 'email_campaign' });
  };

  const showTextCampaign = (originalMessage) => {
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
      addMessage('Action executed successfully!', 'assistant');
      return;
    }

    try {
      addMessage('Executing action...', 'assistant');
      const result = await aiAPI.executeAction(actionId, modifications, sessionId);

      if (result.success) {
        addMessage(`${result.message}`, 'assistant');
      } else {
        addMessage(`${result.message || 'Action failed'}`, 'assistant');
      }
    } catch (error) {
      console.error('Action execution error:', error);
      addMessage('Failed to execute action. Please try again.', 'assistant');
    }
  };

  const executeDemoAction = (actionType) => {
    const confirmMessages = {
      email_campaign: 'Email sent successfully to 47 clients!',
      text_campaign: 'Text messages sent successfully to 12 pre-approved leads!',
      bulk_update: 'Successfully updated 14 deals. Processors have been notified.',
      voicemail_campaign: 'Voicemail drops initiated! All 10 calls are being placed now.',
      pipeline_report: 'Pipeline report generated and sent to your team!'
    };
    addMessage(confirmMessages[actionType] || 'Action completed successfully!', 'assistant');
  };

  // Task action handlers
  const handleSendViaEmail = async () => {
    if (!selectedTask) return;
    addMessage(`Sending email to ${selectedTask.client}...`, 'assistant');

    setTimeout(() => {
      addMessage(`Email sent successfully to ${selectedTask.client}!`, 'assistant');
      removeTaskFromList(selectedTask.id);
    }, 1000);
  };

  const handleApproveAIAction = async () => {
    if (!selectedTask) return;
    addMessage(`Approving AI action for "${selectedTask.title}"...`, 'assistant');

    setTimeout(() => {
      const methodMessages = {
        email: `Email sent to ${selectedTask.client}`,
        text: `Text message sent to ${selectedTask.client}`,
        phone: `Call initiated to ${selectedTask.client}`,
        voicemail: `Voicemail dropped for ${selectedTask.client}`
      };
      addMessage(`Action completed! ${methodMessages[selectedSendMethod]}`, 'assistant');
      removeTaskFromList(selectedTask.id);
    }, 1000);
  };

  const handleSnooze = () => {
    if (!selectedTask) return;
    addMessage(`Snoozing "${selectedTask.title}". When would you like to be reminded?\n\n• 1 hour\n• 3 hours\n• Tomorrow morning\n• Next week`, 'assistant');

    setTimeout(() => {
      addMessage(`Task snoozed! I'll remind you about "${selectedTask.title}" in 3 hours.`, 'assistant');
      removeTaskFromList(selectedTask.id);
    }, 1500);
  };

  const handleDelegate = () => {
    if (!selectedTask) return;
    addMessage(`Delegating "${selectedTask.title}". Select a team member:\n\n• John (Processor)\n• Maria (Assistant)\n• David (Junior LO)`, 'assistant');

    setTimeout(() => {
      addMessage(`Task delegated to Maria! She'll receive a notification with all the details.`, 'assistant');
      removeTaskFromList(selectedTask.id);
    }, 1500);
  };

  const handleDeleteTask = () => {
    if (!selectedTask) return;
    addMessage(`Are you sure you want to delete "${selectedTask.title}"? This action cannot be undone.`, 'assistant');

    setTimeout(() => {
      addMessage(`Task deleted successfully.`, 'assistant');
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
    addMessage('Message updated successfully!', 'assistant');
  };

  const removeTaskFromList = (taskId) => {
    setTaskListData(prev => {
      const updated = prev.filter(t => t.id !== taskId);
      if (updated.length === 0) {
        setSelectedTask(null);
        addMessage("Great job! You've completed all your tasks. Ask 'what's next?' for your upcoming priorities.", 'assistant');
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

    switch (message.contentType) {
      case 'lead_preview':
        return (
          <LeadPreviewComponent
            leadData={message.leadData}
            onConfirm={handleCreateLead}
            onCancel={handleCancelLead}
          />
        );
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
    <div className="ai-landing-page-new">
      {/* Collapsible Left Sidebar */}
      <div className={`ai-sidebar-new ${sidebarCollapsed ? 'collapsed' : ''}`}>
        <button
          className="ai-sidebar-toggle"
          onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
        >
          {sidebarCollapsed ? '>' : '<'}
        </button>

        {!sidebarCollapsed && (
          <>
            {/* New Chat Button */}
            <button className="ai-new-chat-btn" onClick={handleNewChat}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 5v14M5 12h14"/>
              </svg>
              New Chat
            </button>

            {/* Navigation Buttons */}
            <div className="ai-sidebar-nav">
              <button
                className={`ai-nav-btn ${sidebarView === 'chats' ? 'active' : ''}`}
                onClick={() => setSidebarView('chats')}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
                </svg>
                Chats
              </button>
              <button
                className={`ai-nav-btn ${sidebarView === 'reports' ? 'active' : ''}`}
                onClick={() => setSidebarView('reports')}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
                </svg>
                Reports
              </button>
              <button
                className={`ai-nav-btn ${sidebarView === 'suggestions' ? 'active' : ''}`}
                onClick={() => setSidebarView('suggestions')}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/>
                </svg>
                Suggestions
              </button>
            </div>

            {/* Content based on view */}
            <div className="ai-sidebar-content">
              {sidebarView === 'chats' && (
                <>
                  <div className="ai-search-box">
                    <input
                      type="text"
                      placeholder="Search chats..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                    />
                  </div>
                  <div className="ai-chat-list">
                    {filteredChats.length === 0 ? (
                      <div className="ai-empty-list">No chats yet</div>
                    ) : (
                      filteredChats.map(chat => (
                        <div
                          key={chat.id}
                          className={`ai-chat-item ${chat.id === sessionId ? 'active' : ''}`}
                          onClick={() => handleLoadChat(chat)}
                          onContextMenu={(e) => handleContextMenu(e, chat.id)}
                        >
                          <div className="ai-chat-title">{chat.title}</div>
                          <div className="ai-chat-time">
                            {new Date(chat.timestamp).toLocaleDateString()}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </>
              )}

              {sidebarView === 'reports' && (
                <div className="ai-reports-list">
                  {reports.length === 0 ? (
                    <div className="ai-empty-list">No reports yet. Generate reports from your chats!</div>
                  ) : (
                    reports.map(report => (
                      <div key={report.id} className="ai-report-item">
                        <div className="ai-report-title">{report.title}</div>
                        <div className="ai-report-time">
                          {new Date(report.createdAt).toLocaleDateString()}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}

              {sidebarView === 'suggestions' && (
                <div className="ai-suggestions-view">
                  <h3>Share Your Ideas</h3>
                  <p>Help us improve! Share your suggestions and feature requests.</p>
                  <textarea
                    className="ai-suggestion-input"
                    placeholder="Type your suggestion here..."
                    rows={4}
                  />
                  <button className="ai-submit-suggestion">Submit Suggestion</button>
                </div>
              )}
            </div>

            {/* Projects Section */}
            {projects.length > 0 && sidebarView === 'chats' && (
              <div className="ai-projects-section">
                <h4>Saved Projects</h4>
                {projects.map(project => (
                  <div
                    key={project.id}
                    className="ai-project-item"
                    onClick={() => handleLoadChat(project)}
                  >
                    <span className="ai-project-icon">📁</span>
                    {project.title}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {/* Main Content Area - Split Pane */}
      <div className="ai-main-content" ref={containerRef}>
        {/* Top Right Buttons */}
        <div className="ai-top-right-buttons">
          {messages.length > 0 && (
            <>
              <button
                className="ai-copy-btn"
                onClick={handleCopyContent}
                title="Copy content"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                  <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
                </svg>
              </button>
              <button
                className="ai-clear-btn"
                onClick={handleClearContent}
                title="Clear content"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                </svg>
              </button>
            </>
          )}
          {!sidebarCollapsed && (
            <button
              className="ai-close-sidebar-btn"
              onClick={() => setSidebarCollapsed(true)}
              title="Close sidebar"
            >
              ×
            </button>
          )}
        </div>

        {/* Left Pane - Input/Prompts */}
        <div className="ai-left-pane" style={{ width: messages.length > 0 ? `${dividerPosition}%` : '100%' }}>
          {/* Header */}
          <div className="ai-header-new">
            <div className="ai-logo-new">
              <span className="ai-logo-icon">*</span>
            </div>
            <h1>Back at it, {userName}</h1>
          </div>

          <div className="ai-welcome-state">
            <h2>What would you like to do today?</h2>
            <p>Ask me anything about your CRM data, clients, or tasks. I'll handle the rest.</p>

            <div className="ai-example-prompts-new">
              <button onClick={() => handleExamplePrompt('Daily Briefing - Get my top 3 priorities for today')}>
                <strong>Daily Briefing</strong>
                <span>Get your top 3 priorities for today</span>
              </button>
              <button onClick={() => handleExamplePrompt('Pipeline Audit - Identify bottlenecks and stalled deals')}>
                <strong>Pipeline Audit</strong>
                <span>Identify bottlenecks and stalled deals</span>
              </button>
              <button onClick={() => handleExamplePrompt('Focus Reset - Help me get back on track')}>
                <strong>Focus Reset</strong>
                <span>Get back on track when scattered</span>
              </button>
              <button onClick={() => handleExamplePrompt('What should I do next?')}>
                <strong>What Should I Do Next?</strong>
                <span>Priority decision guidance</span>
              </button>
              <button onClick={() => handleExamplePrompt('Accountability Review - Review my performance')}>
                <strong>Accountability Review</strong>
                <span>Review your performance</span>
              </button>
              <button onClick={() => handleExamplePrompt('Tough Love Mode - Call out my inefficiencies directly')}>
                <strong>Tough Love Mode</strong>
                <span>Call out inefficiencies directly</span>
              </button>
              <button onClick={() => handleExamplePrompt('Teach Me The Process - Help me learn systemic thinking')}>
                <strong>Teach Me The Process</strong>
                <span>Learn systemic thinking and execution</span>
              </button>
              <button onClick={() => handleExamplePrompt('I have a question')}>
                <strong>Ask a Question</strong>
                <span>Get specific tactical advice</span>
              </button>
            </div>
          </div>

          {/* Input Area */}
          <div className="ai-input-area">
            <div className="ai-input-container-new">
              <button
                className="ai-upload-btn"
                onClick={() => fileInputRef.current?.click()}
                title="Upload documents"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/>
                </svg>
              </button>
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileUpload}
                multiple
                style={{ display: 'none' }}
              />

              <button
                className={`ai-mic-btn ${isListening ? 'listening' : ''}`}
                onClick={toggleSpeechRecognition}
                title={isListening ? 'Stop listening' : 'Start voice input'}
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z"/>
                  <path d="M19 10v2a7 7 0 01-14 0v-2"/>
                  <line x1="12" y1="19" x2="12" y2="23"/>
                  <line x1="8" y1="23" x2="16" y2="23"/>
                </svg>
              </button>

              <textarea
                ref={textareaRef}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="Ask me to do something..."
                disabled={loading}
                rows={1}
              />

              <select
                className="ai-permission-select"
                value={selectedPermission}
                onChange={(e) => setSelectedPermission(e.target.value)}
              >
                {userPermissions.map(perm => (
                  <option key={perm} value={perm}>
                    {perm.charAt(0).toUpperCase() + perm.slice(1)}
                  </option>
                ))}
              </select>

              <button
                className="ai-send-btn-new"
                onClick={() => sendMessage()}
                disabled={!inputValue.trim() || loading}
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>
                </svg>
              </button>
            </div>
          </div>

          <button className="ai-back-to-crm-new" onClick={() => navigate('/dashboard')}>
            Back to CRM Dashboard
          </button>
        </div>

        {/* Draggable Divider */}
        {messages.length > 0 && (
          <div
            className={`ai-pane-divider ${isDragging ? 'dragging' : ''}`}
            onMouseDown={handleDividerMouseDown}
          />
        )}

        {/* Right Pane - Answers Only */}
        {messages.length > 0 && (
          <div className="ai-right-pane" style={{ width: `${100 - dividerPosition}%` }}>
            <div className="ai-messages-area" ref={chatAreaRef}>
              {messages.filter(message => message.type === 'assistant').map(message => (
                <div key={message.id} className={`ai-message-new ai-message-${message.type}`}>
                  {message.isSpecialContent ? (
                    renderSpecialContent(message)
                  ) : (
                    <div className="ai-message-content-new">{message.content}</div>
                  )}
                </div>
              ))}

              {loading && (
                <div className="ai-message-new ai-message-assistant">
                  <div className="ai-typing-indicator-new">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Context Menu */}
      {contextMenu.visible && (
        <div
          className="ai-context-menu"
          style={{ top: contextMenu.y, left: contextMenu.x }}
        >
          <button onClick={handleSaveAsProject}>Save as Project</button>
          <button onClick={handleDeleteChat}>Delete Chat</button>
        </div>
      )}

      {/* Task List Display */}
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
                  {selectedTask.source === 'Manual Priority' ? 'MANUAL PRIORITY' : selectedTask.source.toUpperCase()}
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
                  >Email</button>
                  <button
                    className={`ai-send-via-btn ${selectedSendMethod === 'text' ? 'active' : ''}`}
                    onClick={() => handleSendMethodChange('text')}
                  >Text</button>
                  <button
                    className={`ai-send-via-btn ${selectedSendMethod === 'phone' ? 'active' : ''}`}
                    onClick={() => handleSendMethodChange('phone')}
                  >Phone</button>
                  <button
                    className={`ai-send-via-btn ${selectedSendMethod === 'voicemail' ? 'active' : ''}`}
                    onClick={() => handleSendMethodChange('voicemail')}
                  >Voicemail</button>
                </div>
              </div>

              <div className="ai-train-section">
                <div className="ai-train-header">
                  <span>Train AI (Optional)</span>
                </div>
                <textarea
                  className="ai-train-input"
                  placeholder="Type instructions to teach AI how to handle similar tasks in the future..."
                />
              </div>

              {selectedTask.aiDraftedMessage && (
                <div className="ai-drafted-message">
                  <div className="ai-drafted-header">
                    <span>AI-Drafted Message</span>
                    {editingMessage ? (
                      <button className="ai-edit-message-btn" onClick={handleSaveMessage}>Save</button>
                    ) : (
                      <button className="ai-edit-message-btn" onClick={handleEditMessage}>Edit Message</button>
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
                <button className="ai-action-btn send" onClick={handleSendViaEmail}>Send via Email</button>
                <button className="ai-action-btn approve" onClick={handleApproveAIAction}>Approve AI Action</button>
                <button className="ai-action-btn snooze" onClick={handleSnooze}>Snooze</button>
                <button className="ai-action-btn delegate" onClick={handleDelegate}>Delegate</button>
                <button className="ai-action-btn delete" onClick={handleDeleteTask}>Delete</button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Email Campaign Preview Component
function EmailCampaignPreview({ preview, onExecute, onEdit }) {
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
function TextCampaignPreview({ textData, onExecute, onEdit }) {
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
function BulkUpdatePreview({ preview, onExecute, onEdit }) {
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
function VoicemailCampaignPreview({ preview, onExecute, onEdit }) {
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
function PipelineReportPreview({ preview, onExecute, onEdit }) {
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

// Lead Preview Component for Screenshot Parsing
function LeadPreviewComponent({ leadData, onConfirm, onCancel }) {
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

export default AILandingPage;
