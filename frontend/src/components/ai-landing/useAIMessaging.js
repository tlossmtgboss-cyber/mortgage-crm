import { useState, useEffect, useRef } from 'react';
import { aiAPI, leadsAPI, loansAPI, tasksAPI, reconciliationAPI, API_BASE_URL } from '../../services/api';
import { getCurrentUser } from '../../utils/auth';
import { toast } from '../../utils/toast';
import { getToken } from '../../utils/tokenStore';

export function useAIMessaging({
  messages,
  setMessages,
  sessionId,
  setSessionId,
  conversationHistory,
  updateConversationHistory
}) {
  const [inputValue, setInputValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [userName, setUserName] = useState('');
  const [taskListData, setTaskListData] = useState(null);
  const [selectedTask, setSelectedTask] = useState(null);
  const [tasksCompleted, setTasksCompleted] = useState(false);
  const [selectedSendMethod, setSelectedSendMethod] = useState('email');
  const [editingMessage, setEditingMessage] = useState(false);
  const [editedMessage, setEditedMessage] = useState('');
  const [parsedLeadData, setParsedLeadData] = useState(null);
  const [generatingMessageType, setGeneratingMessageType] = useState(null);
  const [generatedFullMessage, setGeneratedFullMessage] = useState('');

  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);
  const [sidebarView, setSidebarView] = useState('chats');
  const [selectedPermission, setSelectedPermission] = useState('all');
  const [userPermissions] = useState(['all', 'leads', 'loans', 'tasks', 'reports']);
  const [isListening, setIsListening] = useState(false);
  const [dividerPosition, setDividerPosition] = useState(50);
  const [isDragging, setIsDragging] = useState(false);

  const [structuredContent, setStructuredContent] = useState(null);
  const [showRightSidebar, setShowRightSidebar] = useState(false);

  const [selectedTaskIds, setSelectedTaskIds] = useState(new Set());
  const [bulkProcessing, setBulkProcessing] = useState(false);

  const [showActionSidebar, setShowActionSidebar] = useState(false);

  // Email compose state
  const [allContacts, setAllContacts] = useState([]);

  // Streaming state
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
  const scrollAnchorRef = useRef(null);
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);
  const recognitionRef = useRef(null);
  const containerRef = useRef(null);

  // Auth and user setup
  useEffect(() => {
    const token = getToken();
    if (!token) return; // navigate handled by parent

    const user = getCurrentUser();
    if (user) {
      const name = user.full_name?.split(' ')[0] || user.email?.split('@')[0] || 'there';
      setUserName(name.charAt(0).toUpperCase() + name.slice(1));
    } else {
      setUserName('there');
    }
  }, []);

  // Auto-scroll on new messages
  useEffect(() => {
    if (scrollAnchorRef.current) {
      scrollAnchorRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 200) + 'px';
    }
  }, [inputValue]);

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

  // Load contacts for email autocomplete
  useEffect(() => {
    const loadContacts = async () => {
      try {
        const [leads, loans] = await Promise.all([
          leadsAPI.getAll().catch(() => []),
          loansAPI.getAll().catch(() => [])
        ]);

        const contacts = [];
        leads.forEach(lead => {
          if (lead.name || lead.email) {
            contacts.push({
              id: `lead-${lead.id}`,
              name: lead.name || 'Unknown',
              email: lead.email || '',
              type: 'Lead',
              phone: lead.phone || ''
            });
          }
        });
        loans.forEach(loan => {
          if (loan.borrower_name || loan.borrower_email) {
            contacts.push({
              id: `loan-${loan.id}`,
              name: loan.borrower_name || 'Unknown',
              email: loan.borrower_email || '',
              type: 'Borrower',
              phone: loan.borrower_phone || '',
              loanId: loan.id
            });
          }
        });
        setAllContacts(contacts);
      } catch (error) {
        console.error('Error loading contacts:', error);
      }
    };
    loadContacts();
  }, []);

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
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const transcript = event.results[i][0].transcript;
          if (event.results[i].isFinal) {
            finalTranscript += transcript;
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

  const handleDividerMouseDown = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Good morning';
    if (hour < 17) return 'Good afternoon';
    return 'Good evening';
  };

  const getCurrentDateTime = () => {
    const now = new Date();
    const options = {
      weekday: 'long', year: 'numeric', month: 'long',
      day: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true
    };
    return now.toLocaleDateString('en-US', options);
  };

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

  const toggleSpeechRecognition = () => {
    if (!recognitionRef.current) {
      toast.error('Speech recognition is not supported in your browser. Please use Chrome or Edge.');
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

  // AI Feedback handlers
  const handlePositiveFeedback = (messageId) => {
    setMessageFeedback(prev => ({ ...prev, [messageId]: 'positive' }));
    console.log('Positive feedback for message:', messageId);
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
    setFeedbackModal({
      visible: true,
      messageId,
      userQuestion,
      aiResponse: aiMessage?.content || ''
    });
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

  const addMessage = (content, type, extraData = {}) => {
    const messageId = Date.now() + Math.random();

    const structuredTypes = ['task_priorities', 'pipeline_report', 'search_results', 'report', 'analysis'];
    const hasStructuredData = extraData.isSpecialContent &&
      (structuredTypes.includes(extraData.contentType) ||
       extraData.tasks?.length > 0 ||
       extraData.preview ||
       extraData.responseData);

    const hasListContent = content && (
      /^\d+\.\s/m.test(content) ||
      /^[-•*]\s/m.test(content) ||
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
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const parseResponseForActionItems = (responseText, userQuestion = '') => {
    const items = [];
    let itemId = 1;
    const questionLower = userQuestion.toLowerCase();

    const isBottleneckQuestion = questionLower.includes('bottleneck') || questionLower.includes('stuck') || questionLower.includes('stall');
    const isPipelineQuestion = questionLower.includes('pipeline') || questionLower.includes('deal') || questionLower.includes('loan');
    const isClosingQuestion = questionLower.includes('closing') || questionLower.includes('close') || questionLower.includes('clear to close');

    const taskPattern = /[*-•]\s*[""“]([^""”]+)[""”][*]?\s*\(Due:\s*([^)]+)\)/gi;
    let taskMatch;
    while ((taskMatch = taskPattern.exec(responseText)) !== null) {
      items.push({
        id: itemId++,
        title: taskMatch[1].trim(),
        client: '',
        stage: 'Task',
        priority: taskMatch[2].includes('overdue') || new Date(taskMatch[2]) < new Date() ? 'URGENT' : 'HIGH',
        type: 'Outstanding Task',
        source: 'AI Analysis',
        owner: 'Loan Officer',
        dateCreated: new Date().toLocaleString(),
        details: `Due: ${taskMatch[2]}`,
        dueTime: taskMatch[2],
        loanAmount: null
      });
    }

    const borrowerPatterns = [
      /\*\*([^*]+)\*\*\s*\(\$?([\d,]+)\)/g,
      /\*\*([^*]+)\*\*\s*[-–]\s*\$([\d,]+)/g,
      /[-•]\s*\*\*([^*]+)\*\*\s*\(\$?([\d,]+)\)/g,
      /([A-Z][a-z]+\s+[A-Z][a-z]+)\s*\(\$?([\d,]+)\)/g,
      /([A-Z][a-z]+\s+[A-Z][a-z]+)\s*[-–]\s*\$([\d,]+)/g,
    ];

    const seenBorrowers = new Set();
    const personNamePattern = /^[A-Z][a-z]+\s+(?:[A-Z]\.?\s+)?[A-Z][a-z]+$/;

    for (const borrowerPattern of borrowerPatterns) {
      let borrowerMatch;
      while ((borrowerMatch = borrowerPattern.exec(responseText)) !== null) {
        const name = borrowerMatch[1].trim();
        const amount = borrowerMatch[2].replace(/,/g, '');

        if (!personNamePattern.test(name)) continue;

        const lowerName = name.toLowerCase();
        if (seenBorrowers.has(name) ||
            lowerName.includes('stage') || lowerName.includes('review') ||
            lowerName.includes('completeness') || lowerName.includes('communicate') ||
            lowerName.includes('prioritize') || lowerName.includes('follow') ||
            lowerName.includes('regular') || lowerName.includes('underwriting') ||
            lowerName.includes('received') || lowerName.includes('actionable') ||
            lowerName === 'action' || name.length < 5 || name.length > 30) {
          continue;
        }
        seenBorrowers.add(name);

        const contextStart = Math.max(0, borrowerMatch.index - 200);
        const context = responseText.substring(contextStart, borrowerMatch.index).toLowerCase();

        let stage = 'Active Loan';
        let priority = 'MEDIUM';
        if (context.includes('clear to close') || context.includes('closing')) {
          stage = 'Clear to Close'; priority = 'URGENT';
        } else if (context.includes('underwriting')) {
          stage = 'Underwriting'; priority = 'HIGH';
        } else if (context.includes('processing')) {
          stage = 'Processing'; priority = 'MEDIUM';
        }

        let title = `Follow up - ${stage}`;
        let type = 'Pipeline Item';
        let details = `Review loan status and take necessary action`;

        if (isBottleneckQuestion) {
          title = `${stage} Bottleneck`; type = 'Bottleneck';
          details = `Loan stuck in ${stage.toLowerCase()} - needs attention`;
        } else if (isClosingQuestion) {
          title = `${stage} - Ready to Close`; type = 'Closing';
          details = `Review closing requirements and schedule`;
        } else if (isPipelineQuestion) {
          title = `${stage} Review`; type = 'Pipeline Review';
          details = `Check loan progress in ${stage.toLowerCase()}`;
        }

        items.push({
          id: itemId++, title, client: name, stage, priority, type,
          source: 'AI Analysis', owner: 'Loan Officer',
          dateCreated: new Date().toLocaleString(), details,
          dueTime: priority === 'URGENT' ? 'Today' : 'This Week',
          loanAmount: `$${parseInt(amount).toLocaleString()}`
        });
      }
    }

    const leadPattern = /(?:for|with|contact|follow[- ]?up)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)/gi;
    let leadMatch;
    const seenLeads = new Set();
    while ((leadMatch = leadPattern.exec(responseText)) !== null) {
      const name = leadMatch[1].trim();
      if (seenLeads.has(name) || seenBorrowers.has(name) || name.length < 4) continue;
      seenLeads.add(name);

      if (/^[A-Z][a-z]+\s+[A-Z][a-z]+$/.test(name)) {
        items.push({
          id: itemId++, title: `Contact ${name}`, client: name,
          stage: 'Lead', priority: 'MEDIUM', type: 'Lead Follow-up',
          source: 'AI Analysis', owner: 'Loan Officer',
          dateCreated: new Date().toLocaleString(),
          details: 'Follow up with lead', dueTime: 'This Week', loanAmount: null
        });
      }
    }

    console.log('Parsed action items from response:', items);
    return items;
  };

  const handleExamplePrompt = (prompt) => {
    const newId = crypto.randomUUID();
    setSessionId(newId);
    sessionStorage.setItem('ai_session_id', newId);
    setMessages([]);
    setTaskListData(null);
    setSelectedTask(null);
    setStructuredContent(null);
    setShowRightSidebar(false);

    setInputValue('');
    setTimeout(() => sendMessage(prompt, newId), 0);
  };

  const sendMessage = async (overrideMessage = null, sessionIdOverride = null) => {
    const message = overrideMessage || inputValue.trim();
    if (!message || loading || isStreaming) return;

    const docContext = attachedDocument ? attachedDocument.text : null;

    addMessage(message, 'user');
    setInputValue('');
    setAttachedDocument(null);
    setIsStreaming(true);
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

          console.log('AI Response done. Full response length:', fullResponse?.length);
          console.log('Data from backend:', data);
          console.log('Prioritized tasks from backend:', data?.prioritized_tasks);

          const msgLower = message.toLowerCase();

          const shouldShowActionSidebar =
            msgLower.includes('task') || msgLower.includes('to-do') || msgLower.includes('todo') ||
            msgLower.includes('reconcil') ||
            (msgLower.includes('call') && (msgLower.includes('need') || msgLower.includes('make') || msgLower.includes('who') || msgLower.includes('today'))) ||
            msgLower.includes('phone') || msgLower.includes('appointment') ||
            msgLower.includes('schedule') || msgLower.includes('calendar') || msgLower.includes('meeting');

          if (shouldShowActionSidebar) {
            setShowActionSidebar(true);
          }

          const isExplicitTaskQuestion =
            (msgLower.includes('task') && msgLower.includes('what')) ||
            (msgLower.includes('task') && msgLower.includes('need')) ||
            (msgLower.includes('what') && msgLower.includes('need') && msgLower.includes('do') && !msgLower.includes('briefing') && !msgLower.includes('pipeline') && !msgLower.includes('audit')) ||
            msgLower.includes('outstanding task') || msgLower.includes('overdue task') ||
            (msgLower.includes('to-do') && (msgLower.includes('list') || msgLower.includes('what'))) ||
            (msgLower.includes('todo') && (msgLower.includes('list') || msgLower.includes('what')));

          if (isExplicitTaskQuestion && data?.prioritized_tasks?.length > 0) {
            const tasks = data.prioritized_tasks.map((task, idx) => ({
              id: task.id || idx + 1, title: task.title,
              client: task.client || 'Unknown', stage: task.stage || task.status || 'Pending',
              priority: task.priority || 'MEDIUM', type: 'Outstanding Task',
              source: 'AI Priorities', owner: 'Loan Officer',
              dateCreated: new Date().toLocaleString(),
              details: task.description || '', dueTime: task.due_date || 'Today',
              loanAmount: task.loan_amount
            }));
            setTaskListData(tasks);
            setSelectedTask(tasks[0]);
            setStructuredContent({ id: Date.now(), content: fullResponse, type: 'task_priorities', tasks });
            setShowRightSidebar(true);
          } else if (isExplicitTaskQuestion && fullResponse) {
            const extractedItems = parseResponseForActionItems(fullResponse, message);
            if (extractedItems.length > 0) {
              setTaskListData(extractedItems);
              setSelectedTask(extractedItems[0]);
              setStructuredContent({ id: Date.now(), content: fullResponse, type: 'task_priorities', title: 'Tasks', tasks: extractedItems });
              setShowRightSidebar(true);
            }
          }

          updateConversationHistory(message, fullResponse);
        },
        (error) => {
          console.error('Streaming error:', error);
          setIsStreaming(false);
          setStreamingStatus('');
          setStreamingMessageId(null);
          setMessages(prev => prev.map(msg =>
            msg.id === streamMsgId
              ? { ...msg, content: 'Sorry, there was an error processing your request.', isStreaming: false, isError: true }
              : msg
          ));
        },
        docContext,
        sessionIdOverride || sessionId
      );
    } catch (error) {
      console.error('AI processing error:', error);
      setIsStreaming(false);
      routeMessage(message);
    }
  };

  const routeMessage = (message) => {
    const lower = message.toLowerCase();

    if (lower.includes('daily briefing') || lower.includes('top 3 priorities')) {
      showDailyView();
    } else if (lower.includes('pipeline audit') || lower.includes('bottlenecks')) {
      showPipelineReport();
    } else if (lower.includes('focus reset') || lower.includes('back on track')) {
      showDailyView();
    } else if (lower.includes('what should i do next') || lower.includes('priority decision')) {
      tasksCompleted ? showNextPriorities() : showDailyView();
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
      tasksCompleted ? showNextPriorities() : showDailyView();
    } else if (lower.includes('email') && (lower.includes('task') || lower.includes('to do') || lower.includes('todo') || lower.includes('tomorrow') || lower.includes('need to do') || lower.includes('things'))) {
      sendTaskSummaryEmail(lower.includes('tomorrow'));
    } else if ((lower.includes('today') || lower.includes('do today') || lower.includes('task') || lower.includes('to do') || lower.includes('todo')) && !lower.includes('email')) {
      showDailyView();
    } else if (lower.includes('email') && (lower.includes('all in one') || lower.includes('mortgages under management'))) {
      addMessage('email_campaign', 'assistant', { isSpecialContent: true, contentType: 'email_campaign' });
    } else if (lower.includes('text') || lower.includes('sms') || (lower.includes('message') && !lower.includes('voicemail'))) {
      showTextCampaign(message);
    } else if (lower.includes('update') && lower.includes('deals')) {
      addMessage('bulk_update', 'assistant', { isSpecialContent: true, contentType: 'bulk_update' });
    } else if (lower.includes('voicemail') || (lower.includes('call') && lower.includes('partners'))) {
      addMessage('voicemail_campaign', 'assistant', { isSpecialContent: true, contentType: 'voicemail_campaign' });
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
      { id: 101, title: 'Rate lock opportunity', client: 'Jennifer Martinez', stage: 'Pre-Approved', priority: 'HIGH', type: 'Opportunity', source: 'AI Recommendation', owner: 'Loan Officer', dateCreated: 'Just now', details: 'Rates dropped 0.25% - great time to lock for 3 pre-approved clients', dueTime: 'Tomorrow 9:00 AM', aiDraftedMessage: 'Hi Jennifer,\n\nGreat news! Interest rates have dropped, and I wanted to reach out about locking in your rate...' },
      { id: 102, title: 'Nurture cold leads', client: '8 leads inactive 30+ days', stage: 'Lead', priority: 'MEDIUM', type: 'Campaign', source: 'AI Recommendation', owner: 'Loan Officer', dateCreated: 'Just now', details: 'Re-engagement campaign for leads that have gone cold', dueTime: 'This week' },
      { id: 103, title: 'Review denied applications', client: '3 denials this month', stage: 'Review', priority: 'LOW', type: 'Analysis', source: 'Monthly Review', owner: 'Loan Officer', dateCreated: 'Just now', details: 'Analyze denial reasons and identify improvement opportunities', dueTime: 'Friday' }
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
      const token = getToken();

      try {
        const workflowResponse = await fetch(`${API_BASE_URL}/api/v1/workflow-config/all-workflow-tasks?days_ahead=14`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (workflowResponse.ok) {
          const workflowData = await workflowResponse.json();
          (workflowData.tasks || []).forEach(task => {
            const preferredMethod = task.communication_methods?.includes('phone') ? 'Phone'
              : task.communication_methods?.includes('text') ? 'Text' : 'Email';
            if (preferredMethod === 'Phone') return;
            const priority = task.urgency === 'critical' ? 'URGENT' : task.urgency === 'high' ? 'HIGH' : task.urgency === 'medium' ? 'MEDIUM' : 'LOW';
            allTasks.push({
              id: task.id, backendId: task.id, taskType: 'task', title: task.title,
              client: task.client_name || 'Client', stage: task.stage, priority, type: 'Workflow',
              source: 'Workflow', owner: 'Loan Officer', dateCreated: task.due_date,
              details: task.description || '',
              dueTime: task.due_date ? new Date(task.due_date).toLocaleDateString() : 'Today',
              loanId: task.client_type === 'loan' ? task.client_id : null,
              leadId: task.client_type === 'lead' ? task.client_id : null,
              workflowName: task.workflow_name, workflowColor: task.workflow_color, daysUntilDue: task.days_until_due
            });
          });
        }
      } catch (workflowError) { console.error('Error fetching workflow tasks:', workflowError); }

      try {
        const unifiedResponse = await tasksAPI.getUnified();
        const unifiedTasks = unifiedResponse?.tasks || unifiedResponse || [];
        if (Array.isArray(unifiedTasks)) {
          unifiedTasks.forEach(task => {
            if (task.source !== 'task' && task.source !== 'manual') return;
            if (task.email_from || task.email_subject) return;
            const priority = task.priority?.toUpperCase() || 'MEDIUM';
            allTasks.push({
              id: task.id, backendId: task.id, taskType: 'task',
              title: task.title || task.description || 'Untitled Task',
              client: task.borrower_name || task.client_name || task.contact_name || 'Unknown',
              stage: task.loan_stage || task.stage || 'In Progress', priority,
              type: task.task_type || 'Task', source: task.source || 'Manual',
              owner: task.assigned_to_name || 'Loan Officer',
              dateCreated: task.created_at ? new Date(task.created_at).toLocaleString() : new Date().toLocaleString(),
              details: task.description || '',
              dueTime: task.due_date ? new Date(task.due_date).toLocaleDateString() : 'Today',
              loanId: task.loan_id, leadId: task.lead_id, status: task.status
            });
          });
        }
      } catch (taskError) { console.error('Error fetching unified tasks:', taskError); }

      try {
        const reconData = await reconciliationAPI.getPending();
        const reconItems = reconData?.items || reconData || [];
        if (Array.isArray(reconItems)) {
          reconItems.forEach(item => {
            allTasks.push({
              id: `reconciliation-${item.id}`, backendId: item.id, taskType: 'reconciliation',
              title: item.change_type || 'Data Reconciliation',
              client: item.borrower_name || item.contact_name || 'Unknown',
              stage: 'Pipeline Reconciliation', priority: 'HIGH', type: 'Reconciliation',
              source: 'System Alert', owner: 'Loan Officer',
              dateCreated: item.detected_at ? new Date(item.detected_at).toLocaleString() : new Date().toLocaleString(),
              details: `${item.field_name || 'Field'}: ${item.old_value || 'N/A'} → ${item.new_value || 'N/A'}`,
              dueTime: 'Today', reconItem: item
            });
          });
        }
      } catch (reconError) { console.error('Error fetching reconciliation items:', reconError); }

      if (allTasks.length > 0) {
        const priorityOrder = { 'URGENT': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3 };
        allTasks.sort((a, b) => (priorityOrder[a.priority] || 2) - (priorityOrder[b.priority] || 2));
        setStructuredContent({ tasks: allTasks });
        setSelectedTask(allTasks[0]);
        setShowRightSidebar(true);

        const taskCount = allTasks.filter(t => t.taskType === 'task').length;
        const reconCount = allTasks.filter(t => t.taskType === 'reconciliation').length;
        let msg = `Found ${allTasks.length} items requiring attention`;
        if (taskCount > 0 && reconCount > 0) msg += ` (${taskCount} tasks, ${reconCount} reconciliation items)`;
        else if (reconCount > 0) msg += ` (${reconCount} reconciliation items)`;
        msg += `. Review and complete these from the panel on the right.`;
        addMessage(msg, 'assistant');
        return;
      }

      addMessage("No tasks or reconciliation items found. Great job staying on top of things! Ask me 'what's next?' to find new opportunities.", 'assistant');
    } catch (error) {
      console.error('Error fetching daily tasks:', error);
      addMessage("I couldn't fetch your tasks right now. Please try again or check your connection.", 'assistant');
    }
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

  const executeAction = async (actionId, modifications = {}) => {
    if (!actionId) {
      addMessage('Action executed successfully!', 'assistant');
      return;
    }
    try {
      addMessage('Executing action...', 'assistant');
      const result = await aiAPI.executeAction(actionId, modifications, sessionId);
      addMessage(result.success ? `${result.message}` : `${result.message || 'Action failed'}`, 'assistant');
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

  const sendTaskSummaryEmail = async (isTomorrow = false) => {
    const timeframe = isTomorrow ? 'tomorrow' : 'today';
    addMessage(`I'll send you an email with your tasks for ${timeframe}. Let me gather that information...`, 'assistant');
    try {
      const API_URL = process.env.REACT_APP_API_URL || '';
      const tasksResponse = await fetch(`${API_URL}/api/v1/tasks?limit=50`, {
        headers: { 'Authorization': `Bearer ${getToken()}`, 'Content-Type': 'application/json' }
      });
      if (!tasksResponse.ok) throw new Error('Failed to fetch tasks');
      const tasks = await tasksResponse.json();

      const today = new Date();
      const targetDate = new Date(today);
      if (isTomorrow) targetDate.setDate(targetDate.getDate() + 1);
      const targetDateStr = targetDate.toISOString().split('T')[0];

      const filteredTasks = tasks.filter(task => {
        if (!task.due_date) return !isTomorrow;
        return new Date(task.due_date).toISOString().split('T')[0] === targetDateStr;
      });

      const emailResponse = await fetch(`${API_URL}/api/v1/ai/send-task-summary-email`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${getToken()}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ timeframe, tasks: filteredTasks })
      });

      if (emailResponse.ok) {
        addMessage(`Email sent! Check your inbox for your ${timeframe}'s task summary with ${filteredTasks.length} items.`, 'assistant');
      } else {
        if (filteredTasks.length === 0) {
          addMessage(`You don't have any tasks scheduled for ${timeframe}. Great job staying ahead!`, 'assistant');
        } else {
          const taskList = filteredTasks.slice(0, 10).map(t => `• ${t.title || t.description}`).join('\n');
          addMessage(`Here are your tasks for ${timeframe} (${filteredTasks.length} items):\n\n${taskList}${filteredTasks.length > 10 ? '\n\n...and more' : ''}`, 'assistant');
        }
      }
    } catch (error) {
      console.error('Error sending task summary email:', error);
      addMessage(`I couldn't send the email right now, but let me show you your tasks for ${timeframe} instead.`, 'assistant');
      showDailyView();
    }
  };

  const handleTaskComplete = async (task) => {
    try {
      if (task.id && typeof task.id === 'number' && task.id > 0) {
        const API_URL = process.env.REACT_APP_API_URL || '';
        const response = await fetch(`${API_URL}/api/v1/tasks/${task.id}`, {
          method: 'PATCH',
          headers: { 'Authorization': `Bearer ${getToken()}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: 'completed' })
        });
        if (!response.ok) console.error('Failed to update task:', await response.text());
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
    addMessage(`Snoozing "${task.title}". When would you like to be reminded?\n\n• 1 hour\n• 3 hours\n• Tomorrow morning\n• Next week`, 'assistant');
    setTimeout(() => {
      addMessage(`Task snoozed! I'll remind you about "${task.title}" in 3 hours.`, 'assistant');
    }, 1500);
  };

  const handleCreateLead = async () => {
    if (!parsedLeadData) return;
    try {
      addMessage('Creating lead...', 'assistant');
      const result = await aiAPI.createLeadFromScreenshot(parsedLeadData);
      if (result.success) {
        addMessage(`Lead created successfully! ${parsedLeadData.first_name} ${parsedLeadData.last_name} has been added to your pipeline in the "Attempted Contact" stage.`, 'assistant');
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
            setAttachedDocument({ filename: file.name, text: result.extracted_text, charCount: result.char_count, truncated: result.truncated });
            toast.success(`Document attached: ${file.name}`);
          } else {
            toast.error('Could not extract text from this image.');
          }
        } catch (error) {
          console.error('Image extraction error:', error);
          toast.error(error.response?.data?.detail || 'Failed to process image.');
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
            setAttachedDocument({ filename: file.name, text: result.extracted_text, charCount: result.char_count, truncated: result.truncated });
            toast.success(`Document attached: ${file.name}`);
          } else {
            toast.error('Could not extract text from this document.');
          }
        } catch (error) {
          console.error('Document extraction error:', error);
          toast.error(error.response?.data?.detail || 'Failed to extract document text.');
        } finally {
          setIsExtractingDocument(false);
        }
      } else {
        toast.error(`Unsupported file type: .${ext}. Supported: PDF, DOCX, DOC, TXT, MD, HTML, and images.`);
      }
    }
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return {
    inputValue, setInputValue,
    loading, userName,
    taskListData, setTaskListData,
    selectedTask, setSelectedTask,
    selectedSendMethod, setSelectedSendMethod,
    editingMessage, setEditingMessage,
    editedMessage, setEditedMessage,
    parsedLeadData,
    sidebarCollapsed, setSidebarCollapsed,
    sidebarView, setSidebarView,
    selectedPermission, setSelectedPermission,
    userPermissions,
    isListening,
    dividerPosition, isDragging,
    structuredContent, setStructuredContent,
    showRightSidebar, setShowRightSidebar,
    selectedTaskIds, setSelectedTaskIds,
    bulkProcessing, setBulkProcessing,
    showActionSidebar, setShowActionSidebar,
    isStreaming,
    attachedDocument, setAttachedDocument,
    isExtractingDocument,
    feedbackModal, feedbackType, setFeedbackType,
    feedbackText, setFeedbackText,
    feedbackSubmitting, messageFeedback,
    chatAreaRef, scrollAnchorRef, textareaRef, fileInputRef, containerRef,
    getGreeting, getCurrentDateTime,
    handleCopyContent, handleDividerMouseDown,
    toggleSpeechRecognition,
    handlePositiveFeedback, handleNegativeFeedback,
    handleSubmitFeedback, closeFeedbackModal,
    addMessage, handleKeyPress,
    handleExamplePrompt, sendMessage,
    handleTaskComplete, handleTaskViewDetails, handleTaskSnooze,
    handleCreateLead, handleCancelLead,
    handleFileUpload,
    executeAction, executeDemoAction
  };
}
