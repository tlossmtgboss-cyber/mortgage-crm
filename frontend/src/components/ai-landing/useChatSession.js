import { useState, useEffect } from 'react';

export function useChatSession() {
  const [messages, setMessages] = useState([]);
  const [conversationHistory, setConversationHistory] = useState([]);
  const [chatHistory, setChatHistory] = useState(() => {
    const stored = localStorage.getItem('ai_chat_history');
    return stored ? JSON.parse(stored) : [];
  });
  const [reports, setReports] = useState(() => {
    const stored = localStorage.getItem('ai_reports');
    return stored ? JSON.parse(stored) : [];
  });
  const [projects, setProjects] = useState(() => {
    const stored = localStorage.getItem('ai_projects');
    return stored ? JSON.parse(stored) : [];
  });
  const [searchQuery, setSearchQuery] = useState('');
  const [contextMenu, setContextMenu] = useState({ visible: false, x: 0, y: 0, chatId: null });
  const [draggedChat, setDraggedChat] = useState(null);
  const [dropTargetActive, setDropTargetActive] = useState(false);

  // Session ID for permanent memory
  const [sessionId, setSessionId] = useState(() => {
    const stored = sessionStorage.getItem('ai_session_id');
    if (stored) return stored;
    const newId = crypto.randomUUID();
    sessionStorage.setItem('ai_session_id', newId);
    return newId;
  });

  // Save chat history when messages change
  useEffect(() => {
    if (messages.length > 0) {
      const firstUserMessage = messages.find(m => m.type === 'user');
      const titleContent = firstUserMessage?.content || messages[0]?.content || 'New Chat';
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
      if (chatHistory.length > 20) {
        setChatHistory(chatHistory.slice(-20));
      }
    }
  }, [chatHistory]);

  useEffect(() => {
    try {
      localStorage.setItem('ai_reports', JSON.stringify(reports));
    } catch (e) {
      if (reports.length > 20) {
        setReports(reports.slice(-20));
      }
    }
  }, [reports]);

  useEffect(() => {
    try {
      localStorage.setItem('ai_projects', JSON.stringify(projects));
    } catch (e) {
      if (projects.length > 20) {
        setProjects(projects.slice(-20));
      }
    }
  }, [projects]);

  // Close context menu on click outside
  useEffect(() => {
    const handleClick = () => setContextMenu({ visible: false, x: 0, y: 0, chatId: null });
    document.addEventListener('click', handleClick);
    return () => document.removeEventListener('click', handleClick);
  }, []);

  const handleNewChat = (resetExtras) => {
    const newId = crypto.randomUUID();
    setSessionId(newId);
    sessionStorage.setItem('ai_session_id', newId);
    setMessages([]);
    setConversationHistory([]);
    if (resetExtras) resetExtras();
  };

  const handleLoadChat = (chat) => {
    setSessionId(chat.id);
    sessionStorage.setItem('ai_session_id', chat.id);
    setMessages(chat.messages || []);
  };

  const handleClearContent = (resetExtras) => {
    const newId = crypto.randomUUID();
    setSessionId(newId);
    sessionStorage.setItem('ai_session_id', newId);
    setMessages([]);
    setConversationHistory([]);
    if (resetExtras) resetExtras();
  };

  const handleDeleteMessage = (messageId) => {
    setMessages(prev => prev.filter(m => m.id !== messageId));
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

  // Drag and drop handlers
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

  const filteredChats = chatHistory.filter(chat =>
    (chat.title || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
    chat.messages?.some(m => m.content?.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const updateConversationHistory = (userMessage, assistantMessage) => {
    setConversationHistory(prev => {
      const updated = [
        ...prev,
        { role: 'user', content: userMessage },
        { role: 'assistant', content: assistantMessage }
      ];
      return updated.length > 20 ? updated.slice(-20) : updated;
    });
  };

  return {
    messages,
    setMessages,
    conversationHistory,
    chatHistory,
    reports,
    projects,
    searchQuery,
    setSearchQuery,
    contextMenu,
    draggedChat,
    dropTargetActive,
    sessionId,
    setSessionId,
    filteredChats,
    handleNewChat,
    handleLoadChat,
    handleClearContent,
    handleDeleteMessage,
    handleContextMenu,
    handleSaveAsProject,
    handleDeleteChat,
    handleDragStart,
    handleDragEnd,
    handleDragOver,
    handleDragLeave,
    handleDropOnReports,
    handleRemoveFromReports,
    updateConversationHistory
  };
}
