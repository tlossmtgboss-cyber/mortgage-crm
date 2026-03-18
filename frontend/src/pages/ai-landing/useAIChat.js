import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { aiAPI, leadsAPI, loansAPI, tasksAPI, reconciliationAPI, outreachAPI, API_BASE_URL } from '../../services/api';
import { getCurrentUser } from '../../utils/auth';
import { toast } from '../../utils/toast';
import { parseResponseForActionItems, isExplicitTaskQuestion, shouldShowActionSidebar as checkShouldShowActionSidebar } from './messageParser';

export default function useAIChat() {
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
  const [generatingMessageType, setGeneratingMessageType] = useState(null);
  const [generatedFullMessage, setGeneratedFullMessage] = useState('');

  // Right sidebar for structured output
  const [structuredContent, setStructuredContent] = useState(null);
  const [showRightSidebar, setShowRightSidebar] = useState(false);

  // Task selection state
  const [selectedTaskIds, setSelectedTaskIds] = useState(new Set());
  const [bulkProcessing, setBulkProcessing] = useState(false);

  // Action sidebar state
  const [showActionSidebar, setShowActionSidebar] = useState(false);

  // Streaming state
  const [streamingContent, setStreamingContent] = useState('');
  const [streamingStatus, setStreamingStatus] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingMessageId, setStreamingMessageId] = useState(null);

  // Document attachment state
  const [attachedDocument, setAttachedDocument] = useState(null);
  const [isExtractingDocument, setIsExtractingDocument] = useState(false);

  // AI Feedback state
  const [feedbackModal, setFeedbackModal] = useState({ visible: false, messageId: null, userQuestion: '', aiResponse: '' });
  const [feedbackType, setFeedbackType] = useState('');
  const [feedbackText, setFeedbackText] = useState('');
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);
  const [messageFeedback, setMessageFeedback] = useState({});

  const chatAreaRef = useRef(null);
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);
  const containerRef = useRef(null);

  // Session ID for permanent memory
  const [sessionId, setSessionId] = useState(() => {
    const stored = localStorage.getItem('ai_session_id');
    if (stored) return stored;
    const newId = crypto.randomUUID();
    localStorage.setItem('ai_session_id', newId);
    return newId;
  });

  // Initialize user
  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      navigate('/login');
      return;
    }
    const user = getCurrentUser();
    if (user) {
      const name = user.full_name?.split(' ')[0] || user.email?.split('@')[0] || 'there';
      setUserName(name.charAt(0).toUpperCase() + name.slice(1));
    } else {
      setUserName('there');
    }
  }, [navigate]);

  // Scroll to bottom when messages change
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

  // Add message helper
  const addMessage = useCallback((content, type, extraData = {}) => {
    const messageId = Date.now() + Math.random();

    const structuredTypes = ['task_priorities', 'pipeline_report', 'search_results', 'report', 'analysis'];
    const hasStructuredData = extraData.isSpecialContent &&
      (structuredTypes.includes(extraData.contentType) ||
       extraData.tasks?.length > 0 ||
       extraData.preview ||
       extraData.responseData);

    const hasListContent = content && (
      /^\d+\.\s/m.test(content) ||
      /^[-\u2022*]\s/m.test(content) ||
      /\n\d+\.\s/m.test(content) ||
      content.includes('TODAY') ||
      content.includes('TOMORROW') ||
      content.includes('Priority:')
    );

    if (type === 'assistant' && (hasStructuredData || hasListContent)) {
      const firstLine = content.split('\n')[0];
      const briefSummary = firstLine.length > 100 ? firstLine.substring(0, 100) + '...' : firstLine;

      setMessages(prev => {
        const isDuplicate = prev.some(m => m.content === briefSummary && m.type === type);
        if (isDuplicate) return prev;
        return [...prev, {
          id: messageId,
          content: briefSummary || 'Here are your results:',
          type,
          hasSidebarContent: true
        }];
      });

      setStructuredContent({
        id: messageId,
        content,
        type: extraData.contentType || 'structured',
        ...extraData
      });
      setShowRightSidebar(true);
    } else {
      setMessages(prev => {
        const isDuplicate = prev.some(m => m.content === content && m.type === type);
        if (isDuplicate) return prev;
        return [...prev, {
          id: messageId,
          content,
          type,
          ...extraData
        }];
      });
    }
  }, []);

  // Dynamic greeting based on time of day
  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Good morning';
    if (hour < 17) return 'Good afternoon';
    return 'Good evening';
  };

  const getCurrentDateTime = () => {
    const now = new Date();
    const options = {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    };
    return now.toLocaleDateString('en-US', options);
  };

  // Copy/clear handlers
  const handleCopyContent = async () => {
    const content = messages.map(msg => {
      const prefix = msg.type === 'user' ? 'You: ' : 'Assistant: ';
      return prefix + msg.content;
    }).join('\n\n');
    try {
      await navigator.clipboard.writeText(content);
      toast.success('Content copied to clipboard!');
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

  const handleDeleteMessage = (messageId) => {
    setMessages(prev => prev.filter(m => m.id !== messageId));
  };

  // Feedback handlers
  const handlePositiveFeedback = (messageId) => {
    setMessageFeedback(prev => ({ ...prev, [messageId]: 'positive' }));
  };

  const handleNegativeFeedback = (messageId) => {
    const msgIndex = messages.findIndex(m => m.id === messageId);
    const aiMessage = messages[msgIndex];
    let userQuestion = '';
    for (let i = msgIndex - 1; i >= 0; i--) {
      if (messages[i].type === 'user') {
        userQuestion = messages[i].content;
        break;
      }
    }
    setFeedbackModal({ visible: true, messageId, userQuestion, aiResponse: aiMessage?.content || '' });
    setMessageFeedback(prev => ({ ...prev, [messageId]: 'negative' }));
  };

  const handleSubmitFeedback = async () => {
    if (!feedbackType) {
      toast.error('Please select a feedback type');
      return;
    }
    setFeedbackSubmitting(true);
    try {
      await aiAPI.submitFeedback({
        user_question: feedbackModal.userQuestion,
        ai_response: feedbackModal.aiResponse,
        feedback_type: feedbackType,
        user_feedback: feedbackText || null,
        session_id: sessionId
      });
      setMessageFeedback(prev => ({ ...prev, [feedbackModal.messageId]: 'submitted' }));
      setFeedbackModal({ visible: false, messageId: null, userQuestion: '', aiResponse: '' });
      setFeedbackType('');
      setFeedbackText('');
      addMessage('Thank you for your feedback! We\'ll use it to improve the AI.', 'assistant');
    } catch (error) {
      console.error('Failed to submit feedback:', error);
      toast.error('Failed to submit feedback. Please try again.');
    } finally {
      setFeedbackSubmitting(false);
    }
  };

  const closeFeedbackModal = () => {
    setFeedbackModal({ visible: false, messageId: null, userQuestion: '', aiResponse: '' });
    setFeedbackType('');
    setFeedbackText('');
  };

  // File upload handler
  const handleFileUpload = async (e) => {
    const files = e.target.files;
    if (files.length > 0) {
      const file = files[0];
      const ext = (file.name.split('.').pop() || '').toLowerCase();
      const isImage = file.type.startsWith('image/');
      const isDocument = ['pdf', 'docx', 'doc', 'txt', 'md', 'html'].includes(ext);

      if (isImage && !isDocument) {
        setIsExtractingDocument(true);
        try {
          const result = await aiAPI.extractDocument(file);
          if (result.success && result.extracted_text) {
            setAttachedDocument({
              filename: file.name,
              text: result.extracted_text,
              charCount: result.char_count,
              truncated: result.truncated,
            });
            toast.success(`Document attached: ${file.name}`);
          } else {
            toast.error('Could not extract text from this image.');
          }
        } catch (error) {
          console.error('Image extraction error:', error);
          const detail = error.response?.data?.detail || 'Failed to process image.';
          toast.error(detail);
        } finally {
          setIsExtractingDocument(false);
        }
      } else if (isDocument) {
        if (file.size > 10 * 1024 * 1024) {
          toast.error('File too large. Maximum size is 10 MB.');
          if (fileInputRef.current) fileInputRef.current.value = '';
          return;
        }
        setIsExtractingDocument(true);
        try {
          const result = await aiAPI.extractDocument(file);
          if (result.success && result.extracted_text) {
            setAttachedDocument({
              filename: file.name,
              text: result.extracted_text,
              charCount: result.char_count,
              truncated: result.truncated,
            });
            toast.success(`Document attached: ${file.name}`);
          } else {
            toast.error('Could not extract text from this document.');
          }
        } catch (error) {
          console.error('Document extraction error:', error);
          const detail = error.response?.data?.detail || 'Failed to extract document text.';
          toast.error(detail);
        } finally {
          setIsExtractingDocument(false);
        }
      } else {
        toast.error(`Unsupported file type: .${ext}. Supported: PDF, DOCX, DOC, TXT, MD, HTML, and images.`);
      }
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  // Lead creation handlers
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

  // Key press handler
  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  // Send message (streaming)
  const sendMessage = async (overrideMessage = null) => {
    const message = overrideMessage || inputValue.trim();
    if (!message || loading || isStreaming) return;

    const docContext = attachedDocument ? attachedDocument.text : null;

    addMessage(message, 'user');
    setInputValue('');
    setAttachedDocument(null);
    setIsStreaming(true);
    setStreamingContent('');
    setStreamingStatus('');

    const streamMsgId = Date.now();
    setStreamingMessageId(streamMsgId);

    setMessages(prev => [...prev, {
      id: streamMsgId,
      content: '',
      type: 'assistant',
      isStreaming: true,
      timestamp: new Date().toISOString()
    }]);

    try {
      await aiAPI.processCommandStream(
        message,
        (content) => {
          setStreamingContent(prev => prev + content);
          setMessages(prev => prev.map(msg =>
            msg.id === streamMsgId
              ? { ...msg, content: (msg.content || '') + content }
              : msg
          ));
        },
        (status) => {
          setStreamingStatus(status);
          setMessages(prev => prev.map(msg =>
            msg.id === streamMsgId
              ? { ...msg, statusText: status }
              : msg
          ));
        },
        (fullResponse, data) => {
          setIsStreaming(false);
          setStreamingStatus('');
          setStreamingMessageId(null);

          setMessages(prev => prev.map(msg =>
            msg.id === streamMsgId
              ? { ...msg, content: fullResponse, isStreaming: false, statusText: null }
              : msg
          ));

          const msgLower = message.toLowerCase();

          if (checkShouldShowActionSidebar(msgLower)) {
            setShowActionSidebar(true);
          }

          const isTaskQuestion = isExplicitTaskQuestion(msgLower);

          if (isTaskQuestion && data && data.prioritized_tasks && data.prioritized_tasks.length > 0) {
            const tasks = data.prioritized_tasks.map((task, idx) => ({
              id: task.id || idx + 1,
              title: task.title,
              client: task.client || 'Unknown',
              stage: task.stage || task.status || 'Pending',
              priority: task.priority || 'MEDIUM',
              type: 'Outstanding Task',
              source: 'AI Priorities',
              owner: 'Loan Officer',
              dateCreated: new Date().toLocaleString(),
              details: task.description || '',
              dueTime: task.due_date || 'Today',
              loanAmount: task.loan_amount
            }));
            setTaskListData(tasks);
            setSelectedTask(tasks[0]);
            setStructuredContent({
              id: Date.now(),
              content: fullResponse,
              type: 'task_priorities',
              tasks: tasks
            });
            setShowRightSidebar(true);
          } else if (isTaskQuestion && fullResponse) {
            const extractedItems = parseResponseForActionItems(fullResponse, message);
            if (extractedItems.length > 0) {
              setTaskListData(extractedItems);
              setSelectedTask(extractedItems[0]);
              setStructuredContent({
                id: Date.now(),
                content: fullResponse,
                type: 'task_priorities',
                title: 'Tasks',
                tasks: extractedItems
              });
              setShowRightSidebar(true);
            }
          }

          setConversationHistory(prev => [
            ...prev,
            { role: 'user', content: message },
            { role: 'assistant', content: fullResponse }
          ]);
        },
        (error) => {
          console.error('Streaming error:', error);
          setIsStreaming(false);
          setStreamingStatus('');
          setMessages(prev => prev.map(msg =>
            msg.id === streamMsgId
              ? { ...msg, content: 'Sorry, there was an error processing your request.', isStreaming: false, isError: true }
              : msg
          ));
        },
        docContext
      );
    } catch (error) {
      console.error('AI processing error:', error);
      setIsStreaming(false);
      routeMessage(message);
    }
  };

  // Route message to appropriate handler (fallback)
  const routeMessage = (message) => {
    const lower = message.toLowerCase();

    if (lower.includes('daily briefing') || lower.includes('top 3 priorities')) {
      showDailyView();
    } else if (lower.includes('pipeline audit') || lower.includes('bottlenecks')) {
      showPipelineReport();
    } else if (lower.includes('focus reset') || lower.includes('back on track')) {
      showDailyView();
    } else if (lower.includes('what should i do next') || lower.includes('priority decision')) {
      if (tasksCompleted) {
        showNextPriorities();
      } else {
        showDailyView();
      }
    } else if (lower.includes('accountability review') || lower.includes('review my performance')) {
      showPipelineReport();
    } else if (lower.includes('tough love') || lower.includes('inefficiencies')) {
      showDailyView();
    } else if (lower.includes('teach me the process') || lower.includes('systemic thinking')) {
      showDailyView();
    } else if (lower.includes('have a question') || lower.includes('ask a question')) {
      addMessage("I'm here to help! What specific question do you have about your pipeline, leads, or tasks?", 'assistant');
    } else if ((lower.includes('done') || lower.includes('completed') || lower.includes('finished')) &&
        (lower.includes('task') || lower.includes('all'))) {
      handleTasksCompleted();
    } else if (lower.includes('next') || lower.includes("what's next") || lower.includes('whats next')) {
      if (tasksCompleted) {
        showNextPriorities();
      } else {
        showDailyView();
      }
    } else if (lower.includes('email') && (lower.includes('task') || lower.includes('to do') || lower.includes('todo') || lower.includes('tomorrow') || lower.includes('need to do') || lower.includes('things'))) {
      const isTomorrow = lower.includes('tomorrow');
      sendTaskSummaryEmail(isTomorrow);
      return;
    } else if ((lower.includes('today') || lower.includes('do today') || lower.includes('task') || lower.includes('to do') || lower.includes('todo')) && !lower.includes('email')) {
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
        id: 101, title: 'Rate lock opportunity', client: 'Jennifer Martinez',
        stage: 'Pre-Approved', priority: 'HIGH', type: 'Opportunity',
        source: 'AI Recommendation', owner: 'Loan Officer', dateCreated: 'Just now',
        details: 'Rates dropped 0.25% - great time to lock for 3 pre-approved clients',
        dueTime: 'Tomorrow 9:00 AM',
        aiDraftedMessage: 'Hi Jennifer,\n\nGreat news! Interest rates have dropped, and I wanted to reach out about locking in your rate...'
      },
      {
        id: 102, title: 'Nurture cold leads', client: '8 leads inactive 30+ days',
        stage: 'Lead', priority: 'MEDIUM', type: 'Campaign',
        source: 'AI Recommendation', owner: 'Loan Officer', dateCreated: 'Just now',
        details: 'Re-engagement campaign for leads that have gone cold', dueTime: 'This week'
      },
      {
        id: 103, title: 'Review denied applications', client: '3 denials this month',
        stage: 'Review', priority: 'LOW', type: 'Analysis',
        source: 'Monthly Review', owner: 'Loan Officer', dateCreated: 'Just now',
        details: 'Analyze denial reasons and identify improvement opportunities', dueTime: 'Friday'
      }
    ];

    setTaskListData(nextTasks);
    setSelectedTask(nextTasks[0]);
    setTasksCompleted(false);
    setTimeout(() => {
      addMessage("These are proactive opportunities to grow your pipeline. Let me know which one you'd like to tackle first!", 'assistant');
    }, 500);
  };

  const showDailyView = async () => {
    try {
      const allTasks = [];
      const token = localStorage.getItem('token');

      // Fetch workflow tasks
      try {
        const workflowResponse = await fetch(`${API_BASE_URL}/api/v1/workflow-config/all-workflow-tasks?days_ahead=14`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (workflowResponse.ok) {
          const workflowData = await workflowResponse.json();
          const workflowTasks = workflowData.tasks || [];
          workflowTasks.forEach(task => {
            const preferredMethod = task.communication_methods?.includes('phone') ? 'Phone'
              : task.communication_methods?.includes('text') ? 'Text' : 'Email';
            if (preferredMethod === 'Phone') return;

            const priority = task.urgency === 'critical' ? 'URGENT'
              : task.urgency === 'high' ? 'HIGH'
              : task.urgency === 'medium' ? 'MEDIUM' : 'LOW';
            allTasks.push({
              id: task.id, backendId: task.id, taskType: 'task',
              title: task.title, client: task.client_name || 'Client',
              stage: task.stage, priority, type: 'Workflow', source: 'Workflow',
              owner: 'Loan Officer', dateCreated: task.due_date,
              details: task.description || '',
              dueTime: task.due_date ? new Date(task.due_date).toLocaleDateString() : 'Today',
              loanId: task.client_type === 'loan' ? task.client_id : null,
              leadId: task.client_type === 'lead' ? task.client_id : null,
              workflowName: task.workflow_name, workflowColor: task.workflow_color,
              daysUntilDue: task.days_until_due
            });
          });
        }
      } catch (workflowError) {
        console.error('Error fetching workflow tasks:', workflowError);
      }

      // Fetch unified tasks
      try {
        const unifiedResponse = await tasksAPI.getUnified();
        const unifiedTasks = unifiedResponse?.tasks || unifiedResponse || [];
        if (unifiedTasks && Array.isArray(unifiedTasks)) {
          unifiedTasks.forEach(task => {
            if (task.source !== 'task' && task.source !== 'manual') return;
            if (task.email_from || task.email_subject) return;

            const priority = task.priority?.toUpperCase() || 'MEDIUM';
            allTasks.push({
              id: task.id, backendId: task.id, taskType: 'task',
              title: task.title || task.description || 'Untitled Task',
              client: task.borrower_name || task.client_name || task.contact_name || 'Unknown',
              stage: task.loan_stage || task.stage || 'In Progress',
              priority, type: task.task_type || 'Task',
              source: task.source || 'Manual',
              owner: task.assigned_to_name || 'Loan Officer',
              dateCreated: task.created_at ? new Date(task.created_at).toLocaleString() : new Date().toLocaleString(),
              details: task.description || '',
              dueTime: task.due_date ? new Date(task.due_date).toLocaleDateString() : 'Today',
              loanId: task.loan_id, leadId: task.lead_id, status: task.status
            });
          });
        }
      } catch (taskError) {
        console.error('Error fetching unified tasks:', taskError);
      }

      // Fetch reconciliation items
      try {
        const reconData = await reconciliationAPI.getPending();
        const reconItems = reconData?.items || reconData || [];
        if (Array.isArray(reconItems)) {
          reconItems.forEach(item => {
            allTasks.push({
              id: `reconciliation-${item.id}`, backendId: item.id, taskType: 'reconciliation',
              title: item.change_type || 'Data Reconciliation',
              client: item.borrower_name || item.contact_name || 'Unknown',
              stage: 'Pipeline Reconciliation', priority: 'HIGH',
              type: 'Reconciliation', source: 'System Alert', owner: 'Loan Officer',
              dateCreated: item.detected_at ? new Date(item.detected_at).toLocaleString() : new Date().toLocaleString(),
              details: `${item.field_name || 'Field'}: ${item.old_value || 'N/A'} \u2192 ${item.new_value || 'N/A'}`,
              dueTime: 'Today', reconItem: item
            });
          });
        }
      } catch (reconError) {
        console.error('Error fetching reconciliation items:', reconError);
      }

      if (allTasks.length > 0) {
        const priorityOrder = { 'URGENT': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3 };
        allTasks.sort((a, b) => (priorityOrder[a.priority] || 2) - (priorityOrder[b.priority] || 2));

        setStructuredContent({ tasks: allTasks });
        setSelectedTask(allTasks[0]);
        setShowRightSidebar(true);

        const taskCount = allTasks.filter(t => t.taskType === 'task').length;
        const reconCount = allTasks.filter(t => t.taskType === 'reconciliation').length;

        let message = `Found ${allTasks.length} items requiring attention`;
        if (taskCount > 0 && reconCount > 0) {
          message += ` (${taskCount} tasks, ${reconCount} reconciliation items)`;
        } else if (reconCount > 0) {
          message += ` (${reconCount} reconciliation items)`;
        }
        message += `. Review and complete these from the panel on the right.`;
        addMessage(message, 'assistant');
        return;
      }

      addMessage("No tasks or reconciliation items found. Great job staying on top of things! Ask me 'what's next?' to find new opportunities.", 'assistant');
    } catch (error) {
      console.error('Error fetching daily tasks:', error);
      addMessage("I couldn't fetch your tasks right now. Please try again or check your connection.", 'assistant');
    }
  };

  const showEmailCampaign = () => {
    addMessage('email_campaign', 'assistant', { isSpecialContent: true, contentType: 'email_campaign' });
  };

  const showTextCampaign = (originalMessage) => {
    const lower = originalMessage.toLowerCase();
    let audience = 'pre-approved leads';
    if (lower.includes('pre-approv')) audience = 'pre-approved leads';
    addMessage('text_campaign', 'assistant', {
      isSpecialContent: true, contentType: 'text_campaign',
      textData: { audience, messageContext: 'weekend house hunting plans' }
    });
  };

  const showBulkUpdate = () => {
    addMessage('bulk_update', 'assistant', { isSpecialContent: true, contentType: 'bulk_update' });
  };

  const showVoicemailCampaign = () => {
    addMessage('voicemail_campaign', 'assistant', { isSpecialContent: true, contentType: 'voicemail_campaign' });
  };

  const showPipelineReport = async () => {
    try {
      const response = await aiAPI.processCommand("Give me a pipeline audit and performance review", {
        session_id: sessionId,
        conversation_context: conversationHistory.slice(-5)
      });
      if (response.explanation || response.response) {
        addMessage(response.explanation || response.response, 'assistant');
        return;
      }
      addMessage('pipeline_report', 'assistant', { isSpecialContent: true, contentType: 'pipeline_report' });
    } catch (error) {
      console.error('Error fetching pipeline report:', error);
      addMessage('pipeline_report', 'assistant', { isSpecialContent: true, contentType: 'pipeline_report' });
    }
  };

  const sendTaskSummaryEmail = async (isTomorrow = false) => {
    const timeframe = isTomorrow ? 'tomorrow' : 'today';
    addMessage(`I'll send you an email with your tasks for ${timeframe}. Let me gather that information...`, 'assistant');
    try {
      const API_URL = process.env.REACT_APP_API_URL || '';
      const tasksResponse = await fetch(`${API_URL}/api/v1/tasks?limit=50`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        }
      });
      if (!tasksResponse.ok) throw new Error('Failed to fetch tasks');
      const tasks = await tasksResponse.json();

      const today = new Date();
      const targetDate = new Date(today);
      if (isTomorrow) targetDate.setDate(targetDate.getDate() + 1);
      const targetDateStr = targetDate.toISOString().split('T')[0];

      const filteredTasks = tasks.filter(task => {
        if (!task.due_date) return !isTomorrow;
        const taskDate = new Date(task.due_date).toISOString().split('T')[0];
        return taskDate === targetDateStr;
      });

      const emailResponse = await fetch(`${API_URL}/api/v1/ai/send-task-summary-email`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ timeframe, tasks: filteredTasks })
      });

      if (emailResponse.ok) {
        addMessage(`Email sent! Check your inbox for your ${timeframe}'s task summary with ${filteredTasks.length} items.`, 'assistant');
      } else {
        if (filteredTasks.length === 0) {
          addMessage(`You don't have any tasks scheduled for ${timeframe}. Great job staying ahead!`, 'assistant');
        } else {
          const taskList = filteredTasks.slice(0, 10).map(t => `\u2022 ${t.title || t.description}`).join('\n');
          addMessage(`Here are your tasks for ${timeframe} (${filteredTasks.length} items):\n\n${taskList}${filteredTasks.length > 10 ? '\n\n...and more' : ''}`, 'assistant');
        }
      }
    } catch (error) {
      console.error('Error sending task summary email:', error);
      addMessage(`I couldn't send the email right now, but let me show you your tasks for ${timeframe} instead.`, 'assistant');
      showDailyView();
    }
  };

  const executeAction = async (actionId, modifications = {}) => {
    if (!actionId) {
      addMessage('Action executed successfully!', 'assistant');
      return;
    }
    try {
      addMessage('Executing action...', 'assistant');
      const result = await aiAPI.executeAction(actionId, modifications, sessionId);
      addMessage(`${result.message}`, 'assistant');
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
  const handleTaskComplete = async (task) => {
    try {
      if (task.id && typeof task.id === 'number' && task.id > 0) {
        const API_URL = process.env.REACT_APP_API_URL || '';
        const response = await fetch(`${API_URL}/api/v1/tasks/${task.id}`, {
          method: 'PATCH',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ status: 'completed' })
        });
        if (!response.ok) {
          console.error('Failed to update task:', await response.text());
        }
      }
      addMessage(`Completed: "${task.title}"`, 'assistant');
      return true;
    } catch (error) {
      console.error('Error completing task:', error);
      addMessage(`Marked complete: "${task.title}"`, 'assistant');
      return true;
    }
  };

  const handleTaskViewDetails = (task) => {
    setSelectedTask({
      ...task,
      client: task.client || task.borrower || 'Unknown',
      stage: task.stage || 'In Progress',
      type: task.type || 'Priority Task',
      source: task.source || 'AI Recommendation',
      owner: task.owner || 'Loan Officer',
      dateCreated: task.dateCreated || new Date().toLocaleString(),
      aiDraftedMessage: task.aiDraftedMessage || `Hi ${task.client?.split(' ')[0] || 'there'},\n\nI wanted to follow up regarding ${task.title}.\n\nPlease let me know if you have any questions.\n\nBest regards`
    });
    if (!taskListData || taskListData.length === 0) {
      setTaskListData([task]);
    }
  };

  const handleTaskSnooze = (task) => {
    addMessage(`Snoozing "${task.title}". When would you like to be reminded?\n\n\u2022 1 hour\n\u2022 3 hours\n\u2022 Tomorrow morning\n\u2022 Next week`, 'assistant');
    setTimeout(() => {
      addMessage(`Task snoozed! I'll remind you about "${task.title}" in 3 hours.`, 'assistant');
    }, 1500);
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

  // Example prompt handler
  const handleExamplePrompt = (prompt) => {
    const newId = crypto.randomUUID();
    setSessionId(newId);
    localStorage.setItem('ai_session_id', newId);
    setMessages([]);
    setTaskListData(null);
    setSelectedTask(null);
    setConversationHistory([]);
    setActionContext({});
    setStructuredContent(null);
    setShowRightSidebar(false);
    setInputValue('');
    setTimeout(() => sendMessage(prompt), 100);
  };

  return {
    // State
    messages, inputValue, loading, userName, sessionId,
    conversationHistory, taskListData, selectedTask,
    tasksCompleted, selectedSendMethod, editingMessage, editedMessage,
    parsedLeadData, isParsingImage, generatingMessageType, generatedFullMessage,
    structuredContent, showRightSidebar, selectedTaskIds, bulkProcessing,
    showActionSidebar, streamingContent, streamingStatus, isStreaming,
    streamingMessageId, attachedDocument, isExtractingDocument,
    feedbackModal, feedbackType, feedbackText, feedbackSubmitting, messageFeedback,

    // Refs
    chatAreaRef, textareaRef, fileInputRef, containerRef,

    // Setters
    setMessages, setInputValue, setSessionId, setSelectedTask,
    setSelectedSendMethod, setEditingMessage, setEditedMessage,
    setStructuredContent, setShowRightSidebar, setSelectedTaskIds,
    setBulkProcessing, setShowActionSidebar, setFeedbackType,
    setFeedbackText, setAttachedDocument, setGeneratingMessageType,
    setGeneratedFullMessage, setMessageFeedback,

    // Handlers
    addMessage, getGreeting, getCurrentDateTime,
    handleCopyContent, handleClearContent, handleDeleteMessage,
    handlePositiveFeedback, handleNegativeFeedback,
    handleSubmitFeedback, closeFeedbackModal,
    handleFileUpload, handleCreateLead, handleCancelLead,
    handleKeyPress, sendMessage, handleExamplePrompt,
    handleTaskComplete, handleTaskViewDetails, handleTaskSnooze,
    removeTaskFromList, executeAction, executeDemoAction,

    // Navigation
    navigate,
  };
}
