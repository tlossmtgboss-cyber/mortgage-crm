import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { aiAPI, leadsAPI, loansAPI, tasksAPI, reconciliationAPI, outreachAPI, API_BASE_URL } from '../services/api';
import { getCurrentUser } from '../utils/auth';
import ActionSidebar from '../components/ActionSidebar';
import './AILandingPage.css';
import { toast } from '../utils/toast';
import { getToken } from '../utils/tokenStore';
// Note: EmailDropZone wrapper removed - App.js already wraps with EmailDropZone globally

function AILandingPage() {
  const navigate = useNavigate();
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [userName, setUserName] = useState('');
  const [conversationHistory, setConversationHistory] = useState([]);
  const [taskListData, setTaskListData] = useState(null);
  const [selectedTask, setSelectedTask] = useState(null);
  const [tasksCompleted, setTasksCompleted] = useState(false);
  const [selectedSendMethod, setSelectedSendMethod] = useState('email');
  const [editingMessage, setEditingMessage] = useState(false);
  const [editedMessage, setEditedMessage] = useState('');
  const [parsedLeadData, setParsedLeadData] = useState(null);
  const [generatingMessageType, setGeneratingMessageType] = useState(null);
  const [generatedFullMessage, setGeneratedFullMessage] = useState('');

  // New state for redesigned features
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);
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
  const [draggedChat, setDraggedChat] = useState(null);
  const [dropTargetActive, setDropTargetActive] = useState(false);

  // Right sidebar for structured output (tasks, reports, lists, etc.)
  const [structuredContent, setStructuredContent] = useState(null);
  const [showRightSidebar, setShowRightSidebar] = useState(false);

  // Task selection state for checkboxes and bulk actions
  const [selectedTaskIds, setSelectedTaskIds] = useState(new Set());
  const [bulkProcessing, setBulkProcessing] = useState(false);

  // Action sidebar state (hidden by default, shown when user asks about tasks/reconciliations/calls/appointments)
  const [showActionSidebar, setShowActionSidebar] = useState(false);

  // Reconciliation sidebar state
  const [reconciliationItems, setReconciliationItems] = useState([]);
  const [selectedReconciliationItem, setSelectedReconciliationItem] = useState(null);
  const [showReconciliationSidebar, setShowReconciliationSidebar] = useState(false);
  const [reconciliationLoading, setReconciliationLoading] = useState(false);
  const [reconciliationTab, setReconciliationTab] = useState('new'); // 'new', 'auto', 'pending', 'completed'
  const [reconciliationCounts, setReconciliationCounts] = useState({ new: 0, auto: 0, pending: 0, completed: 0 });
  const [autoProcessEnabled, setAutoProcessEnabled] = useState(false);

  // Email compose state
  const [emailMode, setEmailMode] = useState(false);
  const [emailRecipient, setEmailRecipient] = useState(null);
  const [emailRecipientSearch, setEmailRecipientSearch] = useState('');
  const [emailSubject, setEmailSubject] = useState('');
  const [emailBody, setEmailBody] = useState('');
  const [recipientSuggestions, setRecipientSuggestions] = useState([]);
  const [showRecipientDropdown, setShowRecipientDropdown] = useState(false);
  const [allContacts, setAllContacts] = useState([]);
  const [emailSending, setEmailSending] = useState(false);

  // Streaming state
  const [streamingStatus, setStreamingStatus] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingMessageId, setStreamingMessageId] = useState(null);

  // Document attachment state
  const [attachedDocument, setAttachedDocument] = useState(null); // { filename, text, charCount, truncated }
  const [isExtractingDocument, setIsExtractingDocument] = useState(false);

  // AI Feedback state
  const [feedbackModal, setFeedbackModal] = useState({ visible: false, messageId: null, userQuestion: '', aiResponse: '' });
  const [feedbackType, setFeedbackType] = useState('');
  const [feedbackText, setFeedbackText] = useState('');
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);
  const [messageFeedback, setMessageFeedback] = useState({}); // Track feedback per message: { messageId: 'positive' | 'negative' | 'submitted' }

  const chatAreaRef = useRef(null);
  const scrollAnchorRef = useRef(null);
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
      // Find first user message for title
      const firstUserMessage = messages.find(m => m.type === 'user');
      const titleContent = firstUserMessage?.content || messages[0]?.content || 'New Chat';
      // Create a clean title - truncate at 40 chars without cutting words
      let title = titleContent.substring(0, 40);
      if (titleContent.length > 40) {
        title = title.substring(0, title.lastIndexOf(' ')) || title;
        title += '...';
      }

      const currentChat = {
        id: sessionId,
        title: title,
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
    try {
      localStorage.setItem('ai_chat_history', JSON.stringify(chatHistory));
    } catch (e) {
      // localStorage quota exceeded — trim oldest entries
      if (chatHistory.length > 20) {
        const trimmed = chatHistory.slice(-20);
        setChatHistory(trimmed);
      }
    }
  }, [chatHistory]);

  useEffect(() => {
    try {
      localStorage.setItem('ai_reports', JSON.stringify(reports));
    } catch (e) {
      // localStorage quota exceeded — trim oldest entries
      if (reports.length > 20) {
        const trimmed = reports.slice(-20);
        setReports(trimmed);
      }
    }
  }, [reports]);

  useEffect(() => {
    try {
      localStorage.setItem('ai_projects', JSON.stringify(projects));
    } catch (e) {
      // localStorage quota exceeded — trim oldest entries
      if (projects.length > 20) {
        const trimmed = projects.slice(-20);
        setProjects(trimmed);
      }
    }
  }, [projects]);

  useEffect(() => {
    const token = getToken();
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

  // Dynamic greeting based on time of day
  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Good morning';
    if (hour < 17) return 'Good afternoon';
    return 'Good evening';
  };

  // Format current date and time
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
  };

  const handleDeleteMessage = (messageId) => {
    setMessages(prev => prev.filter(m => m.id !== messageId));
  };

  // AI Feedback handlers
  const handlePositiveFeedback = (messageId) => {
    setMessageFeedback(prev => ({ ...prev, [messageId]: 'positive' }));
    // Positive feedback doesn't need a form - just record it silently
    console.log('Positive feedback for message:', messageId);
  };

  const handleNegativeFeedback = (messageId) => {
    // Find the AI message and the preceding user question
    const msgIndex = messages.findIndex(m => m.id === messageId);
    const aiMessage = messages[msgIndex];
    let userQuestion = '';

    // Look backward to find the user's question
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

      // Show a brief confirmation
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

  // Load contacts for email autocomplete
  useEffect(() => {
    const loadContacts = async () => {
      try {
        const [leads, loans] = await Promise.all([
          leadsAPI.getAll().catch(() => []),
          loansAPI.getAll().catch(() => [])
        ]);

        const contacts = [];

        // Add leads as contacts
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

        // Add loan borrowers as contacts
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

  // Filter recipient suggestions based on search
  useEffect(() => {
    if (emailRecipientSearch.length > 0) {
      const searchLower = emailRecipientSearch.toLowerCase();
      const filtered = allContacts.filter(contact =>
        (contact.name || '').toLowerCase().includes(searchLower) ||
        (contact.email || '').toLowerCase().includes(searchLower)
      ).slice(0, 8);
      setRecipientSuggestions(filtered);
      setShowRecipientDropdown(filtered.length > 0);
    } else {
      setRecipientSuggestions([]);
      setShowRecipientDropdown(false);
    }
  }, [emailRecipientSearch, allContacts]);

  // Handle starting email compose
  const handleStartEmail = () => {
    setEmailMode(true);
    setEmailRecipient(null);
    setEmailRecipientSearch('');

    // Auto-generate subject based on structured content type
    let autoSubject = '';
    if (structuredContent) {
      if (structuredContent.type === 'task_priorities') {
        autoSubject = 'Your Priority Tasks & Action Items';
      } else if (structuredContent.type === 'pipeline_report') {
        autoSubject = 'Pipeline Analysis Report';
      } else if (structuredContent.type === 'search_results') {
        autoSubject = 'Search Results Summary';
      } else if (structuredContent.content) {
        // Extract subject from first line or heading
        const firstLine = structuredContent.content.split('\n')[0];
        // Remove markdown formatting
        autoSubject = firstLine
          .replace(/^#+\s*/, '')  // Remove heading markers
          .replace(/\*\*/g, '')    // Remove bold markers
          .replace(/\*/g, '')      // Remove italic markers
          .trim();
        // Truncate if too long
        if (autoSubject.length > 60) {
          autoSubject = autoSubject.substring(0, 57) + '...';
        }
      }
    }
    setEmailSubject(autoSubject || 'Information from Your Mortgage CRM');

    // Pre-populate body with structured content if available
    if (structuredContent?.content) {
      setEmailBody(structuredContent.content);
    } else {
      setEmailBody('');
    }
  };

  // Handle selecting a recipient
  const handleSelectRecipient = (contact) => {
    setEmailRecipient(contact);
    setEmailRecipientSearch(contact.name);
    setShowRecipientDropdown(false);
  };

  // Handle sending the email
  const handleSendEmail = async () => {
    if (!emailRecipient || !emailSubject || !emailBody) {
      toast.error('Please fill in all fields');
      return;
    }

    setEmailSending(true);

    try {
      // Store the sent email in localStorage for now
      const sentEmails = JSON.parse(localStorage.getItem('sentEmails') || '[]');
      sentEmails.push({
        id: `email-${Date.now()}`,
        to: emailRecipient.email,
        toName: emailRecipient.name,
        subject: emailSubject,
        body: emailBody,
        sentAt: new Date().toISOString(),
        status: 'sent',
        loanId: emailRecipient.loanId || null
      });
      localStorage.setItem('sentEmails', JSON.stringify(sentEmails));

      // Reset email mode
      setEmailMode(false);
      setEmailRecipient(null);
      setEmailRecipientSearch('');
      setEmailSubject('');
      setEmailBody('');

      toast.success('Email sent successfully!');
    } catch (error) {
      console.error('Error sending email:', error);
      toast.error('Failed to send email');
    } finally {
      setEmailSending(false);
    }
  };

  // Handle canceling email compose
  const handleCancelEmail = () => {
    setEmailMode(false);
    setEmailRecipient(null);
    setEmailRecipientSearch('');
    setEmailSubject('');
    setEmailBody('');
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

  // Fetch reconciliation pending items
  const fetchReconciliationItems = async (status = null) => {
    setReconciliationLoading(true);
    try {
      // Get items for the current tab
      const tabStatus = status || reconciliationTab;
      const response = await reconciliationAPI.getPending(tabStatus === 'new' ? 'pending' : tabStatus);
      const items = response.items || [];
      setReconciliationItems(items);
      if (items.length > 0) {
        setSelectedReconciliationItem(items[0]);
      } else {
        setSelectedReconciliationItem(null);
      }

      // Update counts - we'll estimate from what we have
      // In production, you'd have a separate counts endpoint
      setReconciliationCounts(prev => ({
        ...prev,
        [tabStatus]: items.length
      }));
    } catch (error) {
      console.error('Error fetching reconciliation items:', error);
      setReconciliationItems([]);
    } finally {
      setReconciliationLoading(false);
    }
  };

  // Open reconciliation sidebar
  const openReconciliationSidebar = async () => {
    setShowReconciliationSidebar(true);
    setShowRightSidebar(false); // Close task sidebar if open
    await fetchReconciliationItems();
  };

  // Handle reconciliation approval
  const handleReconciliationApprove = async (item, updateStatusTo = null) => {
    try {
      const payload = {
        extracted_data_id: item.id,
        ...(updateStatusTo && { update_status_to: updateStatusTo })
      };
      await reconciliationAPI.approve(payload);
      // Remove from list and select next item
      const newItems = reconciliationItems.filter(i => i.id !== item.id);
      setReconciliationItems(newItems);
      if (newItems.length > 0) {
        setSelectedReconciliationItem(newItems[0]);
      } else {
        setSelectedReconciliationItem(null);
      }
    } catch (error) {
      console.error('Error approving reconciliation:', error);
      toast.error('Failed to approve: ' + (error.response?.data?.detail || error.message));
    }
  };

  // Handle reconciliation rejection
  const handleReconciliationReject = async (item, reason = 'User rejected') => {
    try {
      await reconciliationAPI.reject({ extracted_data_id: item.id, reason });
      const newItems = reconciliationItems.filter(i => i.id !== item.id);
      setReconciliationItems(newItems);
      if (newItems.length > 0) {
        setSelectedReconciliationItem(newItems[0]);
      } else {
        setSelectedReconciliationItem(null);
      }
    } catch (error) {
      console.error('Error rejecting reconciliation:', error);
      toast.error('Failed to reject: ' + (error.response?.data?.detail || error.message));
    }
  };

  const addMessage = (content, type, extraData = {}) => {
    const messageId = Date.now() + Math.random(); // Ensure unique ID

    // Check if this is structured content that should go to the right sidebar
    const structuredTypes = ['task_priorities', 'pipeline_report', 'search_results', 'report', 'analysis'];
    const hasStructuredData = extraData.isSpecialContent &&
      (structuredTypes.includes(extraData.contentType) ||
       extraData.tasks?.length > 0 ||
       extraData.preview ||
       extraData.responseData);

    // Check if content has lists (numbered or bulleted items)
    const hasListContent = content && (
      /^\d+\.\s/m.test(content) || // numbered list
      /^[-•*]\s/m.test(content) || // bulleted list
      /\n\d+\.\s/m.test(content) || // numbered list after newline
      content.includes('TODAY') ||
      content.includes('TOMORROW') ||
      content.includes('Priority:')
    );

    if (type === 'assistant' && (hasStructuredData || hasListContent)) {
      // Extract just a brief summary for the conversation
      const firstLine = content.split('\n')[0];
      const briefSummary = firstLine.length > 100 ? firstLine.substring(0, 100) + '...' : firstLine;

      // Add brief message to conversation - check for duplicates first
      setMessages(prev => {
        // Prevent adding duplicate content
        const isDuplicate = prev.some(m => m.content === briefSummary && m.type === type);
        if (isDuplicate) return prev;
        return [...prev, {
          id: messageId,
          content: briefSummary || 'Here are your results:',
          type,
          hasSidebarContent: true
        }];
      });

      // Put full structured content in right sidebar
      setStructuredContent({
        id: messageId,
        content,
        type: extraData.contentType || 'structured',
        ...extraData
      });
      setShowRightSidebar(true);
    } else {
      // Regular conversational message - check for duplicates first
      setMessages(prev => {
        // Prevent adding duplicate content
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

  // Parse AI response text to extract actionable items for the sidebar
  // userQuestion is used to determine the context/type of the sidebar content
  const parseResponseForActionItems = (responseText, userQuestion = '') => {
    const items = [];
    let itemId = 1;
    const questionLower = userQuestion.toLowerCase();

    // Determine the analysis type based on the question
    const isBottleneckQuestion = questionLower.includes('bottleneck') || questionLower.includes('stuck') || questionLower.includes('stall');
    const isPipelineQuestion = questionLower.includes('pipeline') || questionLower.includes('deal') || questionLower.includes('loan');
    const isClosingQuestion = questionLower.includes('closing') || questionLower.includes('close') || questionLower.includes('clear to close');

    // Extract tasks with due dates: "Task name" (Due: MM/DD/YYYY) or *"Task name"* (Due: ...)
    const taskPattern = /[*-•]\s*[""]([^""]+)[""][*]?\s*\(Due:\s*([^)]+)\)/gi;
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

    // Extract borrowers with dollar amounts in various formats:
    // - "**Name** - $XXX,XXX" (markdown bold with dash) - MOST COMMON
    // - "Name ($XXX,XXX)" or Name ($XXX,XXX)
    // - "Name - $XXX,XXX"
    const borrowerPatterns = [
      /\*\*([^*]+)\*\*\s*\(\$?([\d,]+)\)/g,                                        // **Name** ($amount) - MOST COMMON
      /\*\*([^*]+)\*\*\s*[-–]\s*\$([\d,]+)/g,                                      // **Name** - $amount
      /[-•]\s*\*\*([^*]+)\*\*\s*\(\$?([\d,]+)\)/g,                                 // - **Name** ($amount)
      /([A-Z][a-z]+\s+[A-Z][a-z]+)\s*\(\$?([\d,]+)\)/g,                            // Name ($amount)
      /([A-Z][a-z]+\s+[A-Z][a-z]+)\s*[-–]\s*\$([\d,]+)/g,                          // Name - $amount
    ];

    const seenBorrowers = new Set();
    // Pattern to validate person names (First Last or First M Last)
    const personNamePattern = /^[A-Z][a-z]+\s+(?:[A-Z]\.?\s+)?[A-Z][a-z]+$/;

    for (const borrowerPattern of borrowerPatterns) {
      let borrowerMatch;
      while ((borrowerMatch = borrowerPattern.exec(responseText)) !== null) {
        const name = borrowerMatch[1].trim();
        const amount = borrowerMatch[2].replace(/,/g, '');

        // Must look like a person's name (First Last pattern)
        if (!personNamePattern.test(name)) {
          continue;
        }

        // Skip duplicates and invalid names (headers, action items, etc.)
        const lowerName = name.toLowerCase();
        if (seenBorrowers.has(name) ||
            lowerName.includes('stage') ||
            lowerName.includes('review') ||
            lowerName.includes('completeness') ||
            lowerName.includes('communicate') ||
            lowerName.includes('prioritize') ||
            lowerName.includes('follow') ||
            lowerName.includes('regular') ||
            lowerName.includes('underwriting') ||
            lowerName.includes('received') ||
            lowerName.includes('actionable') ||
            lowerName === 'action' ||
            name.length < 5 ||
            name.length > 30) {
          continue;
        }
        seenBorrowers.add(name);

        // Determine stage/priority from context
        const contextStart = Math.max(0, borrowerMatch.index - 200);
        const context = responseText.substring(contextStart, borrowerMatch.index).toLowerCase();

        let stage = 'Active Loan';
        let priority = 'MEDIUM';
        if (context.includes('clear to close') || context.includes('closing')) {
          stage = 'Clear to Close';
          priority = 'URGENT';
        } else if (context.includes('underwriting')) {
          stage = 'Underwriting';
          priority = 'HIGH';
        } else if (context.includes('processing')) {
          stage = 'Processing';
          priority = 'MEDIUM';
        }

        // Create title based on question context
        let title = `Follow up - ${stage}`;
        let type = 'Pipeline Item';
        let details = `Review loan status and take necessary action`;

        if (isBottleneckQuestion) {
          title = `${stage} Bottleneck`;
          type = 'Bottleneck';
          details = `Loan stuck in ${stage.toLowerCase()} - needs attention`;
        } else if (isClosingQuestion) {
          title = `${stage} - Ready to Close`;
          type = 'Closing';
          details = `Review closing requirements and schedule`;
        } else if (isPipelineQuestion) {
          title = `${stage} Review`;
          type = 'Pipeline Review';
          details = `Check loan progress in ${stage.toLowerCase()}`;
        }

        items.push({
          id: itemId++,
          title: title,
          client: name,
          stage: stage,
          priority: priority,
          type: type,
          source: 'AI Analysis',
          owner: 'Loan Officer',
          dateCreated: new Date().toLocaleString(),
          details: details,
          dueTime: priority === 'URGENT' ? 'Today' : 'This Week',
          loanAmount: `$${parseInt(amount).toLocaleString()}`
        });
      }
    }

    // Extract leads mentioned: "for Lead Name" or "with Lead Name" patterns
    const leadPattern = /(?:for|with|contact|follow[- ]?up)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)/gi;
    let leadMatch;
    const seenLeads = new Set();
    while ((leadMatch = leadPattern.exec(responseText)) !== null) {
      const name = leadMatch[1].trim();
      if (seenLeads.has(name) || seenBorrowers.has(name) || name.length < 4) continue;
      seenLeads.add(name);

      // Only add if it looks like a person's name (2 words, proper case)
      if (/^[A-Z][a-z]+\s+[A-Z][a-z]+$/.test(name)) {
        items.push({
          id: itemId++,
          title: `Contact ${name}`,
          client: name,
          stage: 'Lead',
          priority: 'MEDIUM',
          type: 'Lead Follow-up',
          source: 'AI Analysis',
          owner: 'Loan Officer',
          dateCreated: new Date().toLocaleString(),
          details: 'Follow up with lead',
          dueTime: 'This Week',
          loanAmount: null
        });
      }
    }

    console.log('Parsed action items from response:', items);
    return items;
  };

  const handleNewChat = () => {
    const newId = crypto.randomUUID();
    setSessionId(newId);
    localStorage.setItem('ai_session_id', newId);
    setMessages([]);
    setTaskListData(null);
    setSelectedTask(null);
    setConversationHistory([]);
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

  // Drag and drop handlers for moving chats to reports
  const handleDragStart = (e, chat) => {
    setDraggedChat(chat);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', chat.id);
  };

  const handleDragEnd = () => {
    setDraggedChat(null);
    setDropTargetActive(false);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDropTargetActive(true);
  };

  const handleDragLeave = () => {
    setDropTargetActive(false);
  };

  const handleDropOnReports = (e) => {
    e.preventDefault();
    setDropTargetActive(false);

    if (draggedChat) {
      // Check if chat is already in reports
      const alreadyInReports = reports.some(r => r.id === draggedChat.id);
      if (!alreadyInReports) {
        const reportItem = {
          ...draggedChat,
          isReport: true,
          addedToReportsAt: new Date().toISOString()
        };
        setReports(prev => [reportItem, ...prev]);
      }
      setDraggedChat(null);
    }
  };

  const handleRemoveFromReports = (reportId) => {
    setReports(prev => prev.filter(r => r.id !== reportId));
  };

  const handleFileUpload = async (e) => {
    const files = e.target.files;
    if (files.length > 0) {
      const file = files[0];
      const ext = (file.name.split('.').pop() || '').toLowerCase();
      const isImage = file.type.startsWith('image/');
      const isDocument = ['pdf', 'docx', 'doc', 'txt', 'md', 'html'].includes(ext);

      if (isImage && !isDocument) {
        // Images: extract text via document endpoint (for review) OR parse as screenshot
        // If image is likely a screenshot of a lead, use parseScreenshot
        // If user wants to read/review, use extractDocument
        // Default: attach as document context so AI can read the image
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
        // Documents: extract text and attach as context
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
    // Start a new chat for each preset question
    const newId = crypto.randomUUID();
    setSessionId(newId);
    localStorage.setItem('ai_session_id', newId);
    setMessages([]);
    setTaskListData(null);
    setSelectedTask(null);
    setConversationHistory([]);
    setStructuredContent(null);
    setShowRightSidebar(false);

    // Clear inputValue and send directly with the prompt
    setInputValue('');
    setTimeout(() => sendMessage(prompt, newId), 0);
  };

  const filteredChats = chatHistory.filter(chat =>
    (chat.title || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
    chat.messages?.some(m => m.content?.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const sendMessage = async (overrideMessage = null, sessionIdOverride = null) => {
    const message = overrideMessage || inputValue.trim();
    if (!message || loading || isStreaming) return;

    // Capture document context before clearing
    const docContext = attachedDocument ? attachedDocument.text : null;

    addMessage(message, 'user');
    setInputValue('');
    setAttachedDocument(null);
    setIsStreaming(true);
    setStreamingStatus('');

    // Create a placeholder message for streaming content
    const streamMsgId = Date.now();
    setStreamingMessageId(streamMsgId);

    // Add placeholder message that will be updated as content streams in
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
        // onContent - called for each chunk of content
        (content) => {
          // Update the streaming message in place
          setMessages(prev => prev.map(msg =>
            msg.id === streamMsgId
              ? { ...msg, content: (msg.content || '') + content }
              : msg
          ));
        },
        // onStatus - called when AI is gathering data
        (status) => {
          setStreamingStatus(status);
          // Update message to show status
          setMessages(prev => prev.map(msg =>
            msg.id === streamMsgId
              ? { ...msg, statusText: status }
              : msg
          ));
        },
        // onDone - called when streaming is complete
        (fullResponse, data) => {
          setIsStreaming(false);
          setStreamingStatus('');
          setStreamingMessageId(null);

          // Finalize the message
          setMessages(prev => prev.map(msg =>
            msg.id === streamMsgId
              ? {
                  ...msg,
                  content: fullResponse,
                  isStreaming: false,
                  statusText: null
                }
              : msg
          ));

          console.log('AI Response done. Full response length:', fullResponse?.length);
          console.log('Data from backend:', data);
          console.log('Prioritized tasks from backend:', data?.prioritized_tasks);

          // ONLY show task sidebar for EXPLICIT task questions
          // NOT for general questions like "daily briefing", "pipeline audit", "what should I do next"
          const msgLower = message.toLowerCase();

          // Check if user is asking about tasks, reconciliations, calls, or appointments
          // These trigger the Action Sidebar to appear
          const shouldShowActionSidebar =
            // Task-related questions
            msgLower.includes('task') ||
            msgLower.includes('to-do') ||
            msgLower.includes('todo') ||
            // Reconciliation questions
            msgLower.includes('reconcil') ||
            // Call-related questions
            (msgLower.includes('call') && (msgLower.includes('need') || msgLower.includes('make') || msgLower.includes('who') || msgLower.includes('today'))) ||
            msgLower.includes('phone') ||
            // Appointment/schedule questions
            msgLower.includes('appointment') ||
            msgLower.includes('schedule') ||
            msgLower.includes('calendar') ||
            msgLower.includes('meeting');

          // Show the Action Sidebar when user asks relevant questions
          if (shouldShowActionSidebar) {
            setShowActionSidebar(true);
          }

          // Strict patterns - ONLY explicit task questions trigger the task sidebar
          const isExplicitTaskQuestion =
            // Explicit "what tasks" questions
            (msgLower.includes('task') && msgLower.includes('what')) ||
            (msgLower.includes('task') && msgLower.includes('need')) ||
            // "What do I need to do" - must have all three words and NOT be a briefing/pipeline question
            (msgLower.includes('what') && msgLower.includes('need') && msgLower.includes('do') && !msgLower.includes('briefing') && !msgLower.includes('pipeline') && !msgLower.includes('audit')) ||
            // Outstanding/overdue tasks explicitly
            msgLower.includes('outstanding task') ||
            msgLower.includes('overdue task') ||
            // Explicit to-do list questions
            (msgLower.includes('to-do') && (msgLower.includes('list') || msgLower.includes('what'))) ||
            (msgLower.includes('todo') && (msgLower.includes('list') || msgLower.includes('what')));

          // If prioritized_tasks are returned AND user explicitly asked about tasks, show them in the right sidebar
          if (isExplicitTaskQuestion && data && data.prioritized_tasks && data.prioritized_tasks.length > 0) {
            // Convert to task format for the sidebar
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
            // Set structured content for the right sidebar
            setStructuredContent({
              id: Date.now(),
              content: fullResponse,
              type: 'task_priorities',
              tasks: tasks
            });
            setShowRightSidebar(true);
          } else if (isExplicitTaskQuestion && fullResponse) {
            // Parse the AI response to extract actionable items for the sidebar
            const extractedItems = parseResponseForActionItems(fullResponse, message);
            if (extractedItems.length > 0) {
              setTaskListData(extractedItems);
              setSelectedTask(extractedItems[0]);

              // Set structured content for the right sidebar
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
          // For all other questions (daily briefing, pipeline audit, bottlenecks, etc.), just show the answer without sidebar

          // Update conversation history
          setConversationHistory(prev => {
            const updated = [
              ...prev,
              { role: 'user', content: message },
              { role: 'assistant', content: fullResponse }
            ];
            return updated.length > 20 ? updated.slice(-20) : updated;
          });
        },
        // onError - called if there's an error
        (error) => {
          console.error('Streaming error:', error);
          setIsStreaming(false);
          setStreamingStatus('');
          setStreamingMessageId(null);

          // Update message to show error
          setMessages(prev => prev.map(msg =>
            msg.id === streamMsgId
              ? { ...msg, content: 'Sorry, there was an error processing your request.', isStreaming: false, isError: true }
              : msg
          ));
        },
        // documentContext - text from uploaded document (6th param)
        docContext,
        // sessionId - for conversation memory continuity (7th param)
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

    // Coaching mode handlers - let the AI orchestrator handle the response
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
      // Handle "email me my tasks for tomorrow" type requests
      const isTomorrow = lower.includes('tomorrow');
      sendTaskSummaryEmail(isTomorrow);
      return; // Prevent further processing
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

  const showDailyView = async () => {
    try {
      const allTasks = [];
      const token = getToken();

      // Fetch workflow tasks (same as Tasks page) - these are the primary tasks
      try {
        const workflowResponse = await fetch(`${API_BASE_URL}/api/v1/workflow-config/all-workflow-tasks?days_ahead=14`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (workflowResponse.ok) {
          const workflowData = await workflowResponse.json();
          const workflowTasks = workflowData.tasks || [];
          workflowTasks.forEach(task => {
            // Skip phone-only tasks - those go to Power Dialer
            const preferredMethod = task.communication_methods?.includes('phone') ? 'Phone'
              : task.communication_methods?.includes('text') ? 'Text' : 'Email';
            if (preferredMethod === 'Phone') return;

            const priority = task.urgency === 'critical' ? 'URGENT'
              : task.urgency === 'high' ? 'HIGH'
              : task.urgency === 'medium' ? 'MEDIUM' : 'LOW';
            allTasks.push({
              id: task.id,
              backendId: task.id,
              taskType: 'task',
              title: task.title,
              client: task.client_name || 'Client',
              stage: task.stage,
              priority: priority,
              type: 'Workflow',
              source: 'Workflow',
              owner: 'Loan Officer',
              dateCreated: task.due_date,
              details: task.description || '',
              dueTime: task.due_date ? new Date(task.due_date).toLocaleDateString() : 'Today',
              loanId: task.client_type === 'loan' ? task.client_id : null,
              leadId: task.client_type === 'lead' ? task.client_id : null,
              workflowName: task.workflow_name,
              workflowColor: task.workflow_color,
              daysUntilDue: task.days_until_due
            });
          });
        }
      } catch (workflowError) {
        console.error('Error fetching workflow tasks:', workflowError);
      }

      // Fetch unified tasks from the API (for manual tasks not in workflows)
      try {
        const unifiedResponse = await tasksAPI.getUnified();
        // API returns { total_count, tasks, by_source } - extract the tasks array
        const unifiedTasks = unifiedResponse?.tasks || unifiedResponse || [];
        if (unifiedTasks && Array.isArray(unifiedTasks)) {
          unifiedTasks.forEach(task => {
            // Only include manual tasks (workflow tasks already fetched above)
            if (task.source !== 'task' && task.source !== 'manual') return;
            // Skip email-related tasks (those are reconciliation)
            if (task.email_from || task.email_subject) return;

            // Convert priority string to uppercase format
            const priority = task.priority?.toUpperCase() || 'MEDIUM';
            allTasks.push({
              id: task.id, // Keep real task ID for API calls
              backendId: task.id, // Store original ID
              taskType: 'task', // Mark as regular task
              title: task.title || task.description || 'Untitled Task',
              client: task.borrower_name || task.client_name || task.contact_name || 'Unknown',
              stage: task.loan_stage || task.stage || 'In Progress',
              priority: priority,
              type: task.task_type || 'Task',
              source: task.source || 'Manual',
              owner: task.assigned_to_name || 'Loan Officer',
              dateCreated: task.created_at ? new Date(task.created_at).toLocaleString() : new Date().toLocaleString(),
              details: task.description || '',
              dueTime: task.due_date ? new Date(task.due_date).toLocaleDateString() : 'Today',
              loanId: task.loan_id,
              leadId: task.lead_id,
              status: task.status
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
              id: `reconciliation-${item.id}`, // Prefix to identify reconciliation items
              backendId: item.id,
              taskType: 'reconciliation', // Mark as reconciliation item
              title: item.change_type || 'Data Reconciliation',
              client: item.borrower_name || item.contact_name || 'Unknown',
              stage: 'Pipeline Reconciliation',
              priority: 'HIGH',
              type: 'Reconciliation',
              source: 'System Alert',
              owner: 'Loan Officer',
              dateCreated: item.detected_at ? new Date(item.detected_at).toLocaleString() : new Date().toLocaleString(),
              details: `${item.field_name || 'Field'}: ${item.old_value || 'N/A'} → ${item.new_value || 'N/A'}`,
              dueTime: 'Today',
              reconItem: item // Store full reconciliation item for approval/rejection
            });
          });
        }
      } catch (reconError) {
        console.error('Error fetching reconciliation items:', reconError);
      }

      // If we have tasks, show the sidebar
      if (allTasks.length > 0) {
        // Sort by priority (URGENT > HIGH > MEDIUM > LOW)
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

      // If no tasks found, show message
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

  const showPipelineReport = async () => {
    try {
      // Query pipeline info from the AI orchestrator
      const response = await aiAPI.processCommand("Give me a pipeline audit and performance review", {
        session_id: sessionId,
        conversation_context: conversationHistory.slice(-5)
      });

      // If we got a response from the orchestrator, display it
      if (response.explanation || response.response) {
        addMessage(response.explanation || response.response, 'assistant');
        return;
      }

      // Fallback to special content panel
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

  // Send task summary email to user
  const sendTaskSummaryEmail = async (isTomorrow = false) => {
    const timeframe = isTomorrow ? 'tomorrow' : 'today';
    addMessage(`I'll send you an email with your tasks for ${timeframe}. Let me gather that information...`, 'assistant');

    try {
      const API_URL = process.env.REACT_APP_API_URL || '';

      // Fetch tasks
      const tasksResponse = await fetch(`${API_URL}/api/v1/tasks?limit=50`, {
        headers: {
          'Authorization': `Bearer ${getToken()}`,
          'Content-Type': 'application/json'
        }
      });

      if (!tasksResponse.ok) {
        throw new Error('Failed to fetch tasks');
      }

      const tasks = await tasksResponse.json();

      // Filter tasks based on timeframe
      const today = new Date();
      const targetDate = new Date(today);
      if (isTomorrow) {
        targetDate.setDate(targetDate.getDate() + 1);
      }
      const targetDateStr = targetDate.toISOString().split('T')[0];

      const filteredTasks = tasks.filter(task => {
        if (!task.due_date) return !isTomorrow; // Tasks without due dates show for today
        const taskDate = new Date(task.due_date).toISOString().split('T')[0];
        return taskDate === targetDateStr;
      });

      // Send email via backend
      const emailResponse = await fetch(`${API_URL}/api/v1/ai/send-task-summary-email`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${getToken()}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          timeframe: timeframe,
          tasks: filteredTasks
        })
      });

      if (emailResponse.ok) {
        addMessage(`✅ Email sent! Check your inbox for your ${timeframe}'s task summary with ${filteredTasks.length} items.`, 'assistant');
      } else {
        // Fallback: show tasks in chat
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

  // Task action handlers for TaskPrioritiesComponent
  const handleTaskComplete = async (task) => {
    try {
      // If task has a real ID from the backend, update it
      if (task.id && typeof task.id === 'number' && task.id > 0) {
        const API_URL = process.env.REACT_APP_API_URL || '';
        const response = await fetch(`${API_URL}/api/v1/tasks/${task.id}`, {
          method: 'PATCH',
          headers: {
            'Authorization': `Bearer ${getToken()}`,
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
      // Still mark as complete in UI even if API fails
      addMessage(`Marked complete: "${task.title}"`, 'assistant');
      return true;
    }
  };

  const handleTaskViewDetails = (task) => {
    // Set the task as selected to show in the detail panel
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

    // Make sure task list data is set so the panel shows
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

  const generateFullMessage = async (messageType) => {
    if (!selectedTask) return;

    setGeneratingMessageType(messageType);

    // Simulate AI generation with thoughtful, complete messages
    setTimeout(() => {
      let fullMessage = '';
      const clientName = selectedTask.client?.split(' ')[0] || 'there';
      const taskTitle = selectedTask.title || '';
      const taskDetails = selectedTask.details || '';

      switch (messageType) {
        case 'email':
          fullMessage = `Subject: Important Update Regarding Your ${taskTitle}

Dear ${clientName},

I hope this message finds you well. I wanted to personally reach out regarding ${taskTitle.toLowerCase()}.

${taskDetails}

As your dedicated loan officer, I understand how important this milestone is for you and your family. I want to ensure we're addressing every detail with the care and attention it deserves.

Here's what I recommend as our next steps:
1. Let's schedule a brief call to discuss your options
2. I'll prepare a detailed breakdown of the best path forward
3. We can finalize our action plan together

I'm available this week at your convenience. Would Tuesday or Wednesday work better for you? I can accommodate morning or afternoon times.

Please don't hesitate to reach out if you have any questions in the meantime. I'm here to make this process as smooth as possible for you.

Looking forward to speaking with you soon.

Warm regards,
Tim
Senior Loan Officer
TL Development, LLC
(555) 123-4567
tim@tldevelopment.com`;
          break;

        case 'text':
          fullMessage = `Hi ${clientName}! This is Tim from TL Development. I wanted to follow up on ${taskTitle.toLowerCase()}. ${taskDetails} I have some great options to discuss with you that could really benefit your situation. Do you have 10 minutes for a quick call today or tomorrow? I'm flexible with timing and want to make sure we keep things moving smoothly for you. Let me know what works best! - Tim`;
          break;

        case 'phone':
          fullMessage = `PHONE SCRIPT FOR: ${clientName}

OPENING:
"Hi ${clientName}, this is Tim from TL Development. How are you doing today? I hope I'm catching you at a good time."

[Wait for response]

PURPOSE:
"I'm calling to follow up on ${taskTitle.toLowerCase()}. ${taskDetails}"

KEY TALKING POINTS:
• Express understanding of their timeline and goals
• Explain the current status and what needs to happen next
• Present 2-3 specific options or recommendations
• Address any potential concerns proactively

VALUE PROPOSITION:
"I want to make sure we're moving forward in a way that works best for your situation. Based on what I'm seeing, I think we have some really good options here."

QUESTIONS TO ASK:
• "What questions do you have about the process so far?"
• "Is there anything specific you're concerned about?"
• "What's your ideal timeline for completing this?"

CLOSING:
"I'll send you a quick recap of what we discussed via email. Does [specific date/time] work for our next check-in? Perfect. I appreciate your time today, ${clientName}. Talk to you soon!"

OBJECTION HANDLERS:
• If busy: "I completely understand. When would be a better time for a quick 5-minute call?"
• If hesitant: "I hear you. Let me address that concern specifically..."
• If needs to think: "Absolutely, take your time. I'll follow up on [day] - does that work?"`;
          break;

        case 'voicemail':
          fullMessage = `Hi ${clientName}, this is Tim from TL Development calling.

I wanted to reach out personally about ${taskTitle.toLowerCase()}.

${taskDetails}

I have some important information to share with you and a few options I think you'll be excited about.

Please give me a call back at your earliest convenience at (555) 123-4567. I'm available today until 6 PM, or feel free to call me tomorrow morning.

If I don't hear from you, I'll try you again tomorrow afternoon.

Again, this is Tim at (555) 123-4567. I look forward to speaking with you soon. Have a great day!`;
          break;

        default:
          fullMessage = selectedTask.aiDraftedMessage || '';
      }

      setGeneratedFullMessage(fullMessage);
      setEditedMessage(fullMessage);
      setEditingMessage(true);
      setGeneratingMessageType(null);
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
      case 'accountability_review':
        return (
          <AccountabilityReviewComponent
            content={message.content}
            reviewData={message.reviewData}
          />
        );
      case 'chat_response':
        return (
          <ChatResponseComponent
            content={message.content}
            responseData={message.responseData}
          />
        );
      case 'task_priorities':
        return (
          <TaskPrioritiesComponent
            content={message.content}
            tasks={message.tasks}
            onCompleteTask={handleTaskComplete}
            onViewDetails={handleTaskViewDetails}
            onSnoozeTask={handleTaskSnooze}
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
                className={`ai-nav-btn ${sidebarView === 'reports' ? 'active' : ''} ${dropTargetActive ? 'drop-target' : ''}`}
                onClick={() => setSidebarView('reports')}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDropOnReports}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
                </svg>
                Reports
                {dropTargetActive && <span className="drop-hint">Drop here</span>}
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
                          className={`ai-chat-item ${chat.id === sessionId ? 'active' : ''} ${draggedChat?.id === chat.id ? 'dragging' : ''}`}
                          onClick={() => {
                            // Re-ask the question when clicking on a chat item
                            const firstUserMessage = chat.messages?.find(m => m.type === 'user');
                            if (firstUserMessage?.content) {
                              handleExamplePrompt(firstUserMessage.content);
                            } else {
                              handleLoadChat(chat);
                            }
                          }}
                          onContextMenu={(e) => handleContextMenu(e, chat.id)}
                          draggable
                          onDragStart={(e) => handleDragStart(e, chat)}
                          onDragEnd={handleDragEnd}
                          title={chat.title}
                        >
                          <div className="ai-chat-drag-handle">⋮⋮</div>
                          <div className="ai-chat-info">
                            <div className="ai-chat-title">{chat.title}</div>
                            <div className="ai-chat-time">
                              {new Date(chat.timestamp).toLocaleDateString()}
                            </div>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </>
              )}

              {sidebarView === 'reports' && (
                <div
                  className={`ai-reports-list ${dropTargetActive ? 'drop-target-area' : ''}`}
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDropOnReports}
                >
                  {reports.length === 0 ? (
                    <div className="ai-empty-list">
                      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{marginBottom: '8px', opacity: 0.5}}>
                        <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
                      </svg>
                      <p>No reports yet</p>
                      <p className="ai-drop-instruction">Drag a chat here to save it as a report</p>
                    </div>
                  ) : (
                    reports.map(report => (
                      <div
                        key={report.id}
                        className={`ai-report-item ${report.id === sessionId ? 'active' : ''}`}
                        onClick={() => handleLoadChat(report)}
                      >
                        <div className="ai-report-icon">📊</div>
                        <div className="ai-report-info">
                          <div className="ai-report-title">{report.title}</div>
                          <div className="ai-report-time">
                            {new Date(report.addedToReportsAt || report.timestamp).toLocaleDateString()}
                          </div>
                        </div>
                        <button
                          className="ai-report-remove"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleRemoveFromReports(report.id);
                          }}
                          title="Remove from reports"
                        >
                          ×
                        </button>
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
      <div className={`ai-main-content ${showRightSidebar ? 'with-right-sidebar' : ''}`} ref={containerRef}>
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
        <div className="ai-left-pane" style={{ width: messages.some(m => m.isSpecialContent) ? `${dividerPosition}%` : '100%' }}>
          {/* Header */}
          <div className="ai-header-new">
            <div className="ai-logo-new">
              <span className="ai-logo-icon">*</span>
            </div>
            <h1>Back at it, {userName}</h1>
          </div>

          {/* Conversation Area - Shows when there are messages */}
          {(() => {
            // Deduplicate messages by ID to prevent duplicates
            const seenIds = new Set();
            const uniqueMessages = messages.filter(m => {
              if (!m.isSpecialContent && !seenIds.has(m.id)) {
                seenIds.add(m.id);
                return true;
              }
              return false;
            });

            return uniqueMessages.length > 0 ? (
              <div className="ai-conversation-area" ref={chatAreaRef}>
                <div className="ai-conversation-messages">
                  {uniqueMessages.map((msg) => (
                    <div key={msg.id} className={`ai-conv-message ${msg.type}`}>
                      <div className="ai-conv-avatar">
                        {msg.type === 'user' ? '👤' : '🤖'}
                      </div>
                      <div className="ai-conv-content">
                        {msg.isStreaming && !msg.content ? (
                          <div className="ai-typing-indicator">
                            <span></span>
                            <span></span>
                            <span></span>
                          </div>
                        ) : (
                          <>
                            {msg.statusText && (
                              <div className="ai-status-text">{msg.statusText}</div>
                            )}
                            <div className="ai-conv-text">
                              {msg.type === 'assistant' && !msg.isStreaming ? (
                                <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>{msg.content || ''}</ReactMarkdown>
                              ) : (
                                msg.content?.split('\n').map((line, i) => (
                                  <p key={i}>{line || '\u00A0'}</p>
                                ))
                              )}
                            </div>
                            {/* Feedback buttons for assistant messages */}
                            {msg.type === 'assistant' && !msg.isStreaming && msg.content && (
                              <div className="ai-feedback-buttons">
                                {messageFeedback[msg.id] === 'submitted' ? (
                                  <span className="ai-feedback-thanks">Thanks for the feedback!</span>
                                ) : messageFeedback[msg.id] === 'positive' ? (
                                  <span className="ai-feedback-thanks">Thanks!</span>
                                ) : (
                                  <>
                                    <button
                                      className={`ai-feedback-btn ${messageFeedback[msg.id] === 'positive' ? 'active' : ''}`}
                                      onClick={() => handlePositiveFeedback(msg.id)}
                                      title="Good response"
                                    >
                                      👍
                                    </button>
                                    <button
                                      className={`ai-feedback-btn ${messageFeedback[msg.id] === 'negative' ? 'active' : ''}`}
                                      onClick={() => handleNegativeFeedback(msg.id)}
                                      title="Report issue with this response"
                                    >
                                      👎
                                    </button>
                                  </>
                                )}
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                  <div ref={scrollAnchorRef} />
                </div>
              </div>
            ) : null;
          })() || (
            /* Quick Actions - Show when no messages */
            <div className="ai-welcome-state">
              <h2>{getGreeting()}, {userName}!</h2>
              <p className="ai-datetime">{getCurrentDateTime()}</p>
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
                <button onClick={openReconciliationSidebar}>
                  <strong>Reconcile Emails</strong>
                  <span>Review and process incoming emails</span>
                </button>
                <button onClick={() => handleExamplePrompt('Show me my tasks that need to be completed')}>
                  <strong>Complete Tasks</strong>
                  <span>View and manage your pending tasks</span>
                </button>
                <button onClick={() => handleExamplePrompt('What trends do you see across my leads, loans, pipeline, and referral partners? Email me a full trend report.')}>
                  <strong>Trend Report</strong>
                  <span>Analyze KPI trends and email a report</span>
                </button>
                <button onClick={() => handleExamplePrompt('Show me my top 10 leads sorted by AI score that I should call today')}>
                  <strong>Top Leads</strong>
                  <span>Your highest-priority leads to call</span>
                </button>
                <button onClick={() => handleExamplePrompt('Check TRID compliance across my active pipeline and flag any issues')}>
                  <strong>Compliance Check</strong>
                  <span>TRID, RESPA and disclosure audit</span>
                </button>
                <button onClick={() => handleExamplePrompt('Should I lock or float on my loans closing in the next 30 days?')}>
                  <strong>Rate Advisory</strong>
                  <span>Lock vs float recommendation</span>
                </button>
                <button onClick={() => handleExamplePrompt('What documents are missing or expired across my active loans?')}>
                  <strong>Missing Docs</strong>
                  <span>Track outstanding document requests</span>
                </button>
                <button onClick={() => handleExamplePrompt('Show me my referral partner performance and who I should reach out to')}>
                  <strong>Referral Partners</strong>
                  <span>Partner volume and engagement</span>
                </button>
                <button onClick={() => handleExamplePrompt('Give me a profitability breakdown of my funded loans this month')}>
                  <strong>Profitability</strong>
                  <span>Revenue, margins, and cost per loan</span>
                </button>
                <button onClick={() => handleExamplePrompt('Show me my SLA status - any deadlines at risk of breach?')}>
                  <strong>SLA Tracker</strong>
                  <span>Deadline and service level monitoring</span>
                </button>
              </div>
            </div>
          )}

          {/* Attached Document Chip */}
          {isExtractingDocument && (
            <div className="ai-extracting-indicator">
              <svg className="ai-extracting-spinner" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
              </svg>
              Extracting document text...
            </div>
          )}
          {attachedDocument && !isExtractingDocument && (
            <div className="ai-attached-document">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
              </svg>
              <span className="ai-attached-filename">{attachedDocument.filename}</span>
              <span className="ai-attached-size">{attachedDocument.charCount.toLocaleString()} chars{attachedDocument.truncated ? ' (truncated)' : ''}</span>
              <button className="ai-attached-remove" onClick={() => setAttachedDocument(null)} title="Remove document">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
          )}

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
                accept=".pdf,.docx,.doc,.txt,.md,.html,image/*"
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
                onKeyDown={handleKeyPress}
                placeholder="Ask me to do something..."
                disabled={isStreaming}
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
                disabled={!inputValue.trim() || isStreaming}
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
        {messages.some(m => m.isSpecialContent) && (
          <div
            className={`ai-pane-divider ${isDragging ? 'dragging' : ''}`}
            onMouseDown={handleDividerMouseDown}
          />
        )}

        {/* Right Pane - Results Only (Special Content) */}
        {messages.some(m => m.isSpecialContent) && (
          <div className="ai-right-pane" style={{ width: `${100 - dividerPosition}%` }}>
            <div className="ai-messages-area">
              {messages.filter(message => message.isSpecialContent).map(message => (
                <div key={message.id} className={`ai-message-new ai-message-${message.type}`}>
                  {renderSpecialContent(message)}
                  <button
                    className="ai-delete-message-btn"
                    onClick={() => handleDeleteMessage(message.id)}
                    title="Delete message"
                  >
                    ×
                  </button>
                </div>
              ))}
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

      {/* AI Feedback Modal */}
      {feedbackModal.visible && (
        <div className="ai-feedback-modal-overlay" onClick={closeFeedbackModal}>
          <div className="ai-feedback-modal" onClick={e => e.stopPropagation()}>
            <div className="ai-feedback-modal-header">
              <h3>Report Issue with AI Response</h3>
              <button className="ai-feedback-modal-close" onClick={closeFeedbackModal}>x</button>
            </div>
            <div className="ai-feedback-modal-body">
              <div className="ai-feedback-context">
                <div className="ai-feedback-question">
                  <strong>Your question:</strong>
                  <p>{feedbackModal.userQuestion}</p>
                </div>
                <div className="ai-feedback-response">
                  <strong>AI response:</strong>
                  <p>{feedbackModal.aiResponse?.substring(0, 200)}{feedbackModal.aiResponse?.length > 200 ? '...' : ''}</p>
                </div>
              </div>

              <div className="ai-feedback-type-selector">
                <label>What was wrong with this response?</label>
                <div className="ai-feedback-type-options">
                  <button
                    className={`ai-feedback-type-btn ${feedbackType === 'wrong_answer' ? 'active' : ''}`}
                    onClick={() => setFeedbackType('wrong_answer')}
                  >
                    Wrong Answer
                  </button>
                  <button
                    className={`ai-feedback-type-btn ${feedbackType === 'incomplete' ? 'active' : ''}`}
                    onClick={() => setFeedbackType('incomplete')}
                  >
                    Incomplete
                  </button>
                  <button
                    className={`ai-feedback-type-btn ${feedbackType === 'outdated' ? 'active' : ''}`}
                    onClick={() => setFeedbackType('outdated')}
                  >
                    Outdated Info
                  </button>
                  <button
                    className={`ai-feedback-type-btn ${feedbackType === 'irrelevant' ? 'active' : ''}`}
                    onClick={() => setFeedbackType('irrelevant')}
                  >
                    Irrelevant
                  </button>
                  <button
                    className={`ai-feedback-type-btn ${feedbackType === 'other' ? 'active' : ''}`}
                    onClick={() => setFeedbackType('other')}
                  >
                    Other
                  </button>
                </div>
              </div>

              <div className="ai-feedback-text-input">
                <label>Additional details (optional):</label>
                <textarea
                  value={feedbackText}
                  onChange={e => setFeedbackText(e.target.value)}
                  placeholder="What answer were you expecting? Any additional context..."
                  rows={3}
                />
              </div>
            </div>
            <div className="ai-feedback-modal-footer">
              <button className="ai-feedback-cancel-btn" onClick={closeFeedbackModal}>Cancel</button>
              <button
                className="ai-feedback-submit-btn"
                onClick={handleSubmitFeedback}
                disabled={!feedbackType || feedbackSubmitting}
              >
                {feedbackSubmitting ? 'Submitting...' : 'Submit Feedback'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Right Sidebar - Task Completion Panel */}
      {/* Only appears when user asks about tasks to do, priorities, or daily briefing */}
      {showRightSidebar && structuredContent && structuredContent.tasks && structuredContent.tasks.length > 0 && (
        <div className="task-sidebar">
          <div className="task-sidebar-header">
            <h2>Tasks to Complete</h2>
            <span className="task-count-badge">{structuredContent.tasks.length}</span>
            <button
              className="task-sidebar-close"
              onClick={() => {
                setShowRightSidebar(false);
                setStructuredContent(null);
                setSelectedTask(null);
              }}
            >
              ×
            </button>
          </div>

          <div className="task-sidebar-content">
            {/* Task List - Email Style Layout */}
            <div className="task-email-layout">
              {/* Left: Task Inbox List */}
              <div className="task-inbox-panel">
                <div className="inbox-panel-header">
                  <div className="inbox-header-left">
                    <input
                      type="checkbox"
                      className="task-checkbox select-all-checkbox"
                      checked={structuredContent.tasks.length > 0 && structuredContent.tasks.every(t => selectedTaskIds.has(t.id))}
                      ref={(el) => {
                        if (el) el.indeterminate = structuredContent.tasks.some(t => selectedTaskIds.has(t.id)) && !structuredContent.tasks.every(t => selectedTaskIds.has(t.id));
                      }}
                      onChange={() => {
                        const allSelected = structuredContent.tasks.every(t => selectedTaskIds.has(t.id));
                        if (allSelected) {
                          setSelectedTaskIds(new Set());
                        } else {
                          setSelectedTaskIds(new Set(structuredContent.tasks.map(t => t.id)));
                        }
                      }}
                      title="Select all"
                    />
                    <h3>Tasks</h3>
                    <span className="task-count-pill">{structuredContent.tasks.length}</span>
                  </div>
                  {selectedTaskIds.size > 0 && (
                    <button
                      className="btn-bulk-delete"
                      onClick={async () => {
                        if (selectedTaskIds.size === 0) return;
                        setBulkProcessing(true);
                        try {
                          for (const taskId of selectedTaskIds) {
                            const task = structuredContent.tasks.find(t => t.id === taskId);
                            if (task?.backendId) {
                              if (task.taskType === 'reconciliation') {
                                await reconciliationAPI.delete(task.backendId);
                              } else {
                                await tasksAPI.delete(task.backendId);
                              }
                            }
                          }
                          // Remove from local state
                          const newTasks = structuredContent.tasks.filter(t => !selectedTaskIds.has(t.id));
                          if (newTasks.length > 0) {
                            setStructuredContent({ ...structuredContent, tasks: newTasks });
                            setSelectedTask(newTasks[0]);
                          } else {
                            setShowRightSidebar(false);
                            setStructuredContent(null);
                            setSelectedTask(null);
                          }
                          setSelectedTaskIds(new Set());
                          addMessage(`🗑️ Deleted ${selectedTaskIds.size} task(s)`, 'assistant');
                        } catch (error) {
                          console.error('Error bulk deleting tasks:', error);
                        } finally {
                          setBulkProcessing(false);
                        }
                      }}
                      disabled={bulkProcessing}
                    >
                      {bulkProcessing ? 'Deleting...' : `🗑️ Delete (${selectedTaskIds.size})`}
                    </button>
                  )}
                </div>
                <div className="inbox-task-list">
                  {structuredContent.tasks.map((task, idx) => {
                    const isSelected = selectedTask?.id === task.id || (!selectedTask && idx === 0);
                    const isChecked = selectedTaskIds.has(task.id);
                    const getUrgencyColor = (priority) => {
                      const colors = { 'URGENT': '#ef4444', 'HIGH': '#f97316', 'MEDIUM': '#eab308', 'LOW': '#22c55e' };
                      return colors[priority?.toUpperCase()] || '#9ca3af';
                    };
                    return (
                      <div
                        key={task.id || idx}
                        className={`inbox-task-item ${isSelected ? 'selected' : ''} ${isChecked ? 'checked' : ''}`}
                        onClick={() => setSelectedTask(task)}
                      >
                        <div className="inbox-task-header">
                          <input
                            type="checkbox"
                            className="task-checkbox"
                            checked={isChecked}
                            onChange={(e) => {
                              e.stopPropagation();
                              setSelectedTaskIds(prev => {
                                const newSet = new Set(prev);
                                if (newSet.has(task.id)) {
                                  newSet.delete(task.id);
                                } else {
                                  newSet.add(task.id);
                                }
                                return newSet;
                              });
                            }}
                            onClick={(e) => e.stopPropagation()}
                          />
                          <span className="task-source-icon">{task.taskType === 'reconciliation' ? '📧' : '⚡'}</span>
                          <span className="inbox-task-title">{task.title}</span>
                        </div>
                        <div className="inbox-task-meta">
                          <span className="inbox-task-client">{task.client || 'Client'}</span>
                          <span
                            className="urgency-indicator-dot"
                            style={{ backgroundColor: getUrgencyColor(task.priority) }}
                            title={task.priority}
                          ></span>
                        </div>
                        <div className="inbox-task-stage">{task.stage || 'Workflow'}</div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Right: Task Detail Panel */}
              {(selectedTask || structuredContent.tasks[0]) && (() => {
                const task = selectedTask || structuredContent.tasks[0];
                const getPriorityStyle = (priority) => {
                  const styles = {
                    'URGENT': { bg: '#fef2f2', text: '#dc2626' },
                    'HIGH': { bg: '#fff7ed', text: '#ea580c' },
                    'MEDIUM': { bg: '#fefce8', text: '#ca8a04' },
                    'LOW': { bg: '#f0fdf4', text: '#16a34a' }
                  };
                  return styles[priority?.toUpperCase()] || { bg: '#f3f4f6', text: '#6b7280' };
                };
                const priorityStyle = getPriorityStyle(task.priority);

                return (
                  <div className="task-detail-panel">
                    {/* Source Badge */}
                    <div className="detail-source-badge">
                      <span className="source-badge-icon">⚡</span>
                      <span className="source-badge-text">WORKFLOW</span>
                    </div>

                    {/* Task Title */}
                    <h2 className="detail-task-title">{task.title}</h2>

                    {/* Info Grid */}
                    <div className="detail-info-grid">
                      <div className="detail-info-item">
                        <span className="detail-label">CLIENT</span>
                        <span className="detail-value">{task.client || 'Client'}</span>
                      </div>
                      <div className="detail-info-item">
                        <span className="detail-label">STAGE</span>
                        <span className="detail-value">{task.stage || 'Workflow'}</span>
                      </div>
                      <div className="detail-info-item">
                        <span className="detail-label">PRIORITY</span>
                        <span
                          className="priority-badge-inline"
                          style={{ backgroundColor: priorityStyle.bg, color: priorityStyle.text }}
                        >
                          {task.priority || 'HIGH'}
                        </span>
                      </div>
                      <div className="detail-info-item">
                        <span className="detail-label">SOURCE</span>
                        <span className="detail-value">{task.source || 'Workflow'}</span>
                      </div>
                      <div className="detail-info-item">
                        <span className="detail-label">OWNER</span>
                        <span className="detail-value">{task.owner || 'Loan Officer'}</span>
                      </div>
                      <div className="detail-info-item">
                        <span className="detail-label">DATE CREATED</span>
                        <span className="detail-value">{task.dateCreated || new Date().toLocaleString()}</span>
                      </div>
                    </div>

                    {/* Send Via Options */}
                    <div className="detail-send-via">
                      <span className="send-via-label">SEND VIA</span>
                      <div className="send-via-buttons">
                        <button
                          className={`send-via-btn ${selectedSendMethod === 'email' ? 'active' : ''}`}
                          onClick={() => setSelectedSendMethod('email')}
                        >
                          📧 Email
                        </button>
                        <button
                          className={`send-via-btn ${selectedSendMethod === 'text' ? 'active' : ''}`}
                          onClick={() => setSelectedSendMethod('text')}
                        >
                          💬 Text
                        </button>
                        <button
                          className={`send-via-btn ${selectedSendMethod === 'phone' ? 'active' : ''}`}
                          onClick={() => setSelectedSendMethod('phone')}
                        >
                          📞 Phone
                        </button>
                        <button
                          className={`send-via-btn ${selectedSendMethod === 'voicemail' ? 'active' : ''}`}
                          onClick={() => setSelectedSendMethod('voicemail')}
                        >
                          📱 Voicemail
                        </button>
                      </div>
                    </div>

                    {/* Train AI Section */}
                    <div className="train-ai-section">
                      <div className="train-ai-header">
                        <span className="train-ai-icon">🤖</span>
                        <span className="train-ai-title">Train AI (Optional)</span>
                      </div>
                      <textarea
                        className="train-ai-input"
                        placeholder="Type instructions to teach AI how to handle similar tasks in the future... (e.g., 'Always mention our competitive rates when following up on pre-approvals')"
                        rows={3}
                      />
                    </div>

                    {/* AI Drafted Message */}
                    <div className="ai-drafted-section">
                      <div className="ai-drafted-header">
                        <span className="ai-drafted-icon">🤖</span>
                        <span className="ai-drafted-title">AI-Drafted Message</span>
                        <button className="edit-message-btn">
                          ✏️ Edit Message
                        </button>
                      </div>
                      <div className="ai-drafted-content">
                        Complete task: {task.title}
                      </div>
                    </div>

                    {/* Action Buttons */}
                    <div className="detail-actions">
                      <button
                        className="detail-action-btn send"
                        onClick={async () => {
                          addMessage(`Sending ${selectedSendMethod} to ${task.client}...`, 'assistant');
                          try {
                            const message = `Complete task: ${task.title}`;
                            const leadId = task.leadId || task.backendId || null;

                            switch (selectedSendMethod) {
                              case 'email':
                                await outreachAPI.sendEmail(
                                  task.clientEmail || task.email,
                                  `Follow-up: ${task.title}`,
                                  message,
                                  leadId
                                );
                                addMessage(`✅ Email sent to ${task.client}`, 'assistant');
                                break;
                              case 'text':
                                await outreachAPI.sendSMS(
                                  task.clientPhone || task.phone,
                                  message,
                                  leadId
                                );
                                addMessage(`✅ Text sent to ${task.client}`, 'assistant');
                                break;
                              case 'phone':
                                await outreachAPI.requestCall(
                                  task.clientPhone || task.phone,
                                  leadId,
                                  task.title
                                );
                                addMessage(`✅ Call request created for ${task.client}`, 'assistant');
                                break;
                              case 'voicemail':
                                await outreachAPI.sendVoicemail(
                                  task.clientPhone || task.phone,
                                  'default',
                                  leadId
                                );
                                addMessage(`✅ Voicemail dropped for ${task.client}`, 'assistant');
                                break;
                              default:
                                addMessage(`✅ Message sent to ${task.client}`, 'assistant');
                            }
                          } catch (error) {
                            console.error('Error sending message:', error);
                            addMessage(`⚠️ Could not send ${selectedSendMethod}. Please try again or use another method.`, 'assistant');
                          }
                        }}
                      >
                        🚀 Send via {selectedSendMethod.charAt(0).toUpperCase() + selectedSendMethod.slice(1)}
                      </button>
                      <button
                        className="detail-action-btn approve"
                        onClick={async () => {
                          try {
                            // Call backend to complete/approve the task
                            if (task.taskType === 'reconciliation') {
                              // Approve reconciliation item
                              await reconciliationAPI.approve({ item_id: task.backendId, action: 'approve' });
                              addMessage(`✅ Approved reconciliation: "${task.title}" for ${task.client}`, 'assistant');
                            } else if (task.backendId && typeof task.backendId === 'number') {
                              // Complete regular task via API
                              await tasksAPI.update(task.backendId, { status: 'completed' });
                              addMessage(`✅ Completed task: "${task.title}"`, 'assistant');
                            }
                          } catch (error) {
                            console.error('Error completing task:', error);
                            addMessage(`Marked complete: "${task.title}" (sync pending)`, 'assistant');
                          }

                          // Remove from local state
                          const newTasks = structuredContent.tasks.filter(t => t.id !== task.id);
                          if (newTasks.length > 0) {
                            setStructuredContent({ ...structuredContent, tasks: newTasks });
                            setSelectedTask(newTasks[0]);
                          } else {
                            setShowRightSidebar(false);
                            setStructuredContent(null);
                            setSelectedTask(null);
                          }
                        }}
                      >
                        ✅ {task.taskType === 'reconciliation' ? 'Approve' : 'Complete'}
                      </button>
                      <button
                        className="detail-action-btn snooze"
                        onClick={() => {
                          addMessage(`⏰ Snoozed "${task.title}" - I'll remind you in 3 hours.`, 'assistant');
                          // Remove from current view
                          const newTasks = structuredContent.tasks.filter(t => t.id !== task.id);
                          if (newTasks.length > 0) {
                            setStructuredContent({ ...structuredContent, tasks: newTasks });
                            setSelectedTask(newTasks[0]);
                          } else {
                            setShowRightSidebar(false);
                            setStructuredContent(null);
                            setSelectedTask(null);
                          }
                        }}
                      >
                        ⏰ Snooze
                      </button>
                      <button
                        className="detail-action-btn delegate"
                        onClick={() => {
                          addMessage(`👥 Who would you like to delegate "${task.title}" to? Type a team member's name.`, 'assistant');
                        }}
                      >
                        👥 Delegate
                      </button>
                      <button
                        className="detail-action-btn delete"
                        onClick={async () => {
                          try {
                            // Call backend to delete/reject
                            if (task.taskType === 'reconciliation') {
                              await reconciliationAPI.delete(task.backendId);
                              addMessage(`🗑️ Dismissed reconciliation item: "${task.title}"`, 'assistant');
                            } else if (task.backendId && typeof task.backendId === 'number') {
                              await tasksAPI.delete(task.backendId);
                              addMessage(`🗑️ Deleted task: "${task.title}"`, 'assistant');
                            }
                          } catch (error) {
                            console.error('Error deleting task:', error);
                            addMessage(`Removed: "${task.title}" (sync pending)`, 'assistant');
                          }

                          // Remove from local state
                          const newTasks = structuredContent.tasks.filter(t => t.id !== task.id);
                          if (newTasks.length > 0) {
                            setStructuredContent({ ...structuredContent, tasks: newTasks });
                            setSelectedTask(newTasks[0]);
                          } else {
                            setShowRightSidebar(false);
                            setStructuredContent(null);
                            setSelectedTask(null);
                          }
                        }}
                      >
                        🗑️ Delete
                      </button>
                    </div>
                  </div>
                );
              })()}
            </div>
          </div>
        </div>
      )}

      {/* Reconciliation Sidebar - Email Intelligence Style */}
      {showReconciliationSidebar && (
        <div className="email-intelligence-sidebar">
          <div className="ei-sidebar-header">
            <h2>Email Reconciliation</h2>
            <button
              className="close-sidebar-btn"
              onClick={() => setShowReconciliationSidebar(false)}
            >
              ×
            </button>
          </div>

          {/* Status Tabs */}
          <div className="ei-tabs">
            <button
              className={`ei-tab ${reconciliationTab === 'new' ? 'active' : ''}`}
              onClick={() => { setReconciliationTab('new'); fetchReconciliationItems('new'); }}
            >
              New ({reconciliationCounts.new || reconciliationItems.length})
            </button>
            <button
              className={`ei-tab ${reconciliationTab === 'auto' ? 'active' : ''}`}
              onClick={() => { setReconciliationTab('auto'); fetchReconciliationItems('auto'); }}
            >
              Auto-Processing ({reconciliationCounts.auto || 0})
            </button>
            <button
              className={`ei-tab ${reconciliationTab === 'pending' ? 'active' : ''}`}
              onClick={() => { setReconciliationTab('pending'); fetchReconciliationItems('pending'); }}
            >
              Pending Review ({reconciliationCounts.pending || 0})
            </button>
            <button
              className={`ei-tab ${reconciliationTab === 'completed' ? 'active' : ''}`}
              onClick={() => { setReconciliationTab('completed'); fetchReconciliationItems('completed'); }}
            >
              Completed ({reconciliationCounts.completed || 0})
            </button>
          </div>

          <div className="ei-main-content">
            {/* Left Column - Item List */}
            <div className="ei-item-list">
              {reconciliationLoading ? (
                <div className="ei-loading">
                  <div className="loading-spinner"></div>
                  <p>Loading items...</p>
                </div>
              ) : reconciliationItems.length === 0 ? (
                <div className="ei-empty">
                  <p>No items in this category</p>
                  <button className="ei-refresh-btn" onClick={() => fetchReconciliationItems()}>
                    Refresh
                  </button>
                </div>
              ) : (
                reconciliationItems.map((item) => {
                  // Extract loan number and name from fields
                  const loanNumber = item.fields?.loan_number?.value || item.fields?.loan_number || '';
                  const firstName = item.fields?.first_name?.value || item.fields?.first_name || '';
                  const lastName = item.fields?.last_name?.value || item.fields?.last_name || '';
                  const displayName = firstName || lastName
                    ? `${firstName} ${lastName}`.trim()
                    : (item.match_entity_name || item.borrower_name || '');
                  // Use email_subject (API field name) or fallback to nested email.subject
                  const subject = item.email_subject || item.email?.subject || item.subject || 'Loan Update';

                  // Build display title like "CMG-0154304 [Stewart-RCA00000008590]: Inspection Scheduled"
                  const displayTitle = loanNumber
                    ? `${loanNumber}${displayName ? ` [${displayName}]` : ''}: ${subject}`
                    : (displayName ? `${displayName}: ${subject}` : subject);

                  const isSelected = selectedReconciliationItem?.id === item.id;
                  const matchType = item.match_entity_type?.toUpperCase() || 'ACTIVE_LOAN';
                  // Use email_from (API field name) or fallback to nested email.sender
                  const fromEmail = item.email_from || item.email?.sender || item.from_email || '';
                  const receivedDate = item.email_received_at || item.email?.received_at || item.created_at;

                  return (
                    <div
                      key={item.id}
                      className={`ei-item ${isSelected ? 'selected' : ''}`}
                      onClick={() => setSelectedReconciliationItem(item)}
                    >
                      <div className="ei-item-header">
                        <span className="ei-item-type">{matchType}</span>
                        <span className="ei-item-badge new">NEW</span>
                      </div>
                      <div className="ei-item-title">{displayTitle}</div>
                      <div className="ei-item-from">
                        <span className="ei-from-label">From:</span> {fromEmail}
                      </div>
                      {receivedDate && (
                        <div className="ei-item-date">
                          {new Date(receivedDate).toLocaleDateString()}
                        </div>
                      )}
                      <div className="ei-item-warning">
                        This message originated from outside CML. Please use caution when opening links and attachments.
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            {/* Right Column - Detail Panel */}
            <div className="ei-detail-panel">
              {selectedReconciliationItem ? (() => {
                const item = selectedReconciliationItem;
                const firstName = item.fields?.first_name?.value || item.fields?.first_name || '';
                const lastName = item.fields?.last_name?.value || item.fields?.last_name || '';
                const displayName = firstName || lastName
                  ? `${firstName} ${lastName}`.trim()
                  : (item.match_entity_name || item.borrower_name || 'Unknown');
                // Use correct API field names
                const subject = item.email_subject || item.email?.subject || item.subject || 'Loan Update';
                const fromEmail = item.email_from || item.email?.sender || item.from_email || '';
                const receivedDate = item.email_received_at || item.email?.received_at || item.created_at;
                const emailBody = item.email_body || item.email?.body || '';

                // Organize fields into a grid
                const fieldPairs = item.fields ? Object.entries(item.fields).map(([key, val]) => ({
                  label: key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
                  value: typeof val === 'object' && val !== null ? (val.value || '') : String(val || ''),
                  confidence: typeof val === 'object' && val?.confidence ? Math.round(val.confidence * 100) : 100
                })) : [];

                return (
                  <>
                    <div className="ei-detail-header">
                      <span className="ei-new-message">NEW MESSAGE</span>
                      <h3 className="ei-detail-title">{subject}</h3>
                    </div>

                    <div className="ei-detail-meta">
                      <div className="ei-meta-row">
                        <span className="ei-meta-label">FROM</span>
                        <span className="ei-meta-value">{fromEmail}</span>
                      </div>
                      <div className="ei-meta-row">
                        <span className="ei-meta-label">SUBJECT</span>
                        <span className="ei-meta-value">{subject}</span>
                      </div>
                      <div className="ei-meta-row">
                        <span className="ei-meta-label">RECEIVED</span>
                        <span className="ei-meta-value">
                          {receivedDate ? new Date(receivedDate).toLocaleString() : '-'}
                        </span>
                      </div>
                      <div className="ei-meta-row">
                        <span className="ei-meta-label">STATUS</span>
                        <span className="ei-meta-value">Awaiting Processing</span>
                      </div>
                    </div>

                    {/* Where should this data go? */}
                    <div className="ei-match-section">
                      <h4>Where should this data go?</h4>
                      <div className="ei-match-options">
                        <div className={`ei-match-option ${item.match_entity_type === 'lead' ? 'selected' : ''}`}>
                          <span className="ei-match-icon">👤</span>
                          <span className="ei-match-label">Lead</span>
                          <span className="ei-match-status">{item.match_entity_type === 'lead' ? `#${item.match_entity_id}` : 'No match found'}</span>
                        </div>
                        <div className={`ei-match-option ${item.match_entity_type === 'loan' ? 'selected' : ''}`}>
                          <span className="ei-match-icon">📋</span>
                          <span className="ei-match-label">Active Loan</span>
                          <span className="ei-match-status">{item.match_entity_type === 'loan' ? `#${item.match_entity_id}` : 'No match found'}</span>
                        </div>
                        <div className="ei-match-option">
                          <span className="ei-match-icon">📁</span>
                          <span className="ei-match-label">Portfolio</span>
                          <span className="ei-match-status">No match found</span>
                        </div>
                        <div className="ei-match-option create-new">
                          <span className="ei-match-icon">➕</span>
                          <span className="ei-match-label">Create New Loan</span>
                          <span className="ei-match-status">{item.fields?.loan_number?.value || ''}</span>
                        </div>
                      </div>
                    </div>

                    {/* Extracted Fields */}
                    <div className="ei-fields-section">
                      <div className="ei-fields-header">
                        <h4>Extracted Fields</h4>
                        <button className="ei-add-field-btn">+ Add Field</button>
                      </div>
                      <div className="ei-fields-grid">
                        {fieldPairs.map((field, idx) => (
                          <div key={idx} className="ei-field-item">
                            <div className="ei-field-header">
                              <span className="ei-field-label">{field.label}</span>
                              <span className={`ei-field-confidence ${field.confidence >= 90 ? 'high' : field.confidence >= 70 ? 'medium' : 'low'}`}>
                                {field.confidence}%
                              </span>
                            </div>
                            <div className="ei-field-value-row">
                              <input
                                type="text"
                                className="ei-field-input"
                                value={field.value}
                                readOnly
                              />
                              <button className="ei-field-delete">Delete</button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Email Content */}
                    {emailBody && (
                      <div className="ei-email-content">
                        <h4>EMAIL CONTENT</h4>
                        <div className="ei-email-body">
                          {emailBody}
                        </div>
                      </div>
                    )}

                    {/* Auto-process option */}
                    <div className="ei-auto-process">
                      <label className="ei-checkbox-label">
                        <input
                          type="checkbox"
                          checked={autoProcessEnabled}
                          onChange={(e) => setAutoProcessEnabled(e.target.checked)}
                        />
                        Let AI auto-process similar messages
                      </label>
                      <p className="ei-auto-hint">
                        When approved, AI will automatically handle similar "Loan Update" messages in the future without requiring your review.
                      </p>
                    </div>

                    {/* Action Buttons */}
                    <div className="ei-actions">
                      <button
                        className="ei-action-btn process"
                        onClick={() => handleReconciliationApprove(item, item.ai_suggested_status)}
                      >
                        Process & Apply
                      </button>
                      <button
                        className="ei-action-btn reject"
                        onClick={() => handleReconciliationReject(item)}
                      >
                        Reject
                      </button>
                      <button
                        className="ei-action-btn delete"
                        onClick={() => handleReconciliationReject(item, 'Deleted by user')}
                      >
                        Delete
                      </button>
                    </div>
                  </>
                );
              })() : (
                <div className="ei-no-selection">
                  <p>Select an item from the list to view details</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Persistent Action Sidebar - Always visible on right */}
      {showActionSidebar && !showRightSidebar && !showReconciliationSidebar && (
        <ActionSidebar
          onTaskSelect={(item) => {
            // When a task is selected from the sidebar, add context to the chat
            if (item) {
              const contextMessage = `I'm looking at a ${item.category} item: "${item.title}" for ${item.entity_name || 'a client'}. ${item.description || ''}`;
              setInputValue(contextMessage);
            }
          }}
          onClose={() => setShowActionSidebar(false)}
        />
      )}

      {/* Toggle button to show action sidebar when hidden */}
      {!showActionSidebar && !showRightSidebar && !showReconciliationSidebar && (
        <button
          className="action-sidebar-toggle-btn"
          onClick={() => setShowActionSidebar(true)}
          title="Show Action Center"
        >
          <span className="toggle-icon">📋</span>
        </button>
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

// Chat Response Component - displays all AI responses in sidebar
function ChatResponseComponent({ content, responseData }) {
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
      color: '#7c3aed',
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
      background: '#10b981',
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
      color: '#10b981',
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
function AccountabilityReviewComponent({ content, reviewData }) {
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
