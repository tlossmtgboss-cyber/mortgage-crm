/**
 * useRealtorPortal Hooks
 *
 * Custom hooks for the Realtor Portal including:
 * - useLoanSync: Real-time WebSocket connection for loan updates
 * - useRealtorAuth: Authentication state management
 * - useRealtorLoan: Loan data fetching with permissions
 * - useLetterGeneration: Letter generation and management
 */

import { useState, useEffect, useCallback, useRef, useMemo } from 'react';

// =============================================================================
// API CONFIGURATION
// =============================================================================

const API_BASE = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';
const WS_BASE = process.env.REACT_APP_WS_URL || 'wss://api.perenniaai.com';
const REALTOR_API = `${API_BASE}/api/v1/realtor-portal`;

// =============================================================================
// API HELPER
// =============================================================================

async function realtorApi(endpoint, options = {}) {
  const token = localStorage.getItem('realtor_token');
  const url = `${REALTOR_API}${endpoint}`;

  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail || 'API request failed');
  }

  return response.json();
}

// =============================================================================
// useLoanSync - Real-time WebSocket Updates
// =============================================================================

/**
 * Hook for real-time loan updates via WebSocket
 *
 * @param {Object} options - Configuration options
 * @param {Function} options.onStatusChange - Callback for loan status changes
 * @param {Function} options.onDataUpdate - Callback for loan data updates
 * @param {Function} options.onMilestoneUpdate - Callback for milestone updates
 * @param {Function} options.onDocumentUpdate - Callback for document updates
 * @param {Function} options.onLetterGenerated - Callback for new letters
 * @param {boolean} options.autoReconnect - Auto reconnect on disconnect
 *
 * @returns {Object} { isConnected, subscribe, unsubscribe, sendMessage }
 */
export function useLoanSync(options = {}) {
  const {
    onStatusChange,
    onDataUpdate,
    onMilestoneUpdate,
    onDocumentUpdate,
    onConditionUpdate,
    onLetterGenerated,
    onError,
    autoReconnect = true,
  } = options;

  const [isConnected, setIsConnected] = useState(false);
  const [connectionError, setConnectionError] = useState(null);
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 5;

  // Connect to WebSocket
  const connect = useCallback(() => {
    const token = localStorage.getItem('realtor_token');
    if (!token) {
      setConnectionError('Not authenticated');
      return;
    }

    try {
      // Security: Browser WebSocket API does not support Authorization headers; token in URL is the only option.
      const ws = new WebSocket(`${WS_BASE}/api/v1/realtor-portal/ws/${token}`);

      ws.onopen = () => {
        setIsConnected(true);
        setConnectionError(null);
        reconnectAttempts.current = 0;
        console.log('Realtor portal WebSocket connected');
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          handleMessage(message);
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err);
        }
      };

      ws.onclose = (event) => {
        setIsConnected(false);
        console.log('WebSocket closed:', event.code, event.reason);

        // Attempt reconnect if enabled
        if (autoReconnect && reconnectAttempts.current < maxReconnectAttempts) {
          const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000);
          reconnectAttempts.current++;
          reconnectTimeoutRef.current = setTimeout(connect, delay);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        setConnectionError('Connection error');
        if (onError) onError(error);
      };

      wsRef.current = ws;
    } catch (err) {
      setConnectionError(err.message);
      if (onError) onError(err);
    }
  }, [autoReconnect, onError]);

  // Handle incoming messages
  const handleMessage = useCallback((message) => {
    switch (message.type) {
      case 'LOAN_STATUS_CHANGE':
        if (onStatusChange) {
          onStatusChange(message.loan_id, message.data, message.version);
        }
        break;

      case 'LOAN_DATA_UPDATE':
        if (onDataUpdate) {
          onDataUpdate(message.loan_id, message.data.updated_fields, message.version);
        }
        break;

      case 'MILESTONE_UPDATE':
        if (onMilestoneUpdate) {
          onMilestoneUpdate(message.loan_id, message.data, message.version);
        }
        break;

      case 'DOCUMENT_UPDATE':
        if (onDocumentUpdate) {
          onDocumentUpdate(message.loan_id, message.data, message.version);
        }
        break;

      case 'CONDITION_UPDATE':
        if (onConditionUpdate) {
          onConditionUpdate(message.loan_id, message.data, message.version);
        }
        break;

      case 'LETTER_GENERATED':
        if (onLetterGenerated) {
          onLetterGenerated(message.loan_id, message.data, message.version);
        }
        break;

      case 'HEARTBEAT':
        // Respond to heartbeat
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: 'PONG' }));
        }
        break;

      case 'SYNC_STATE':
        console.log('Sync state:', message.data);
        break;

      case 'ERROR':
        console.error('Server error:', message.data);
        if (onError) onError(new Error(message.data?.message || 'Server error'));
        break;

      default:
        console.log('Unknown message type:', message.type);
    }
  }, [onStatusChange, onDataUpdate, onMilestoneUpdate, onDocumentUpdate, onConditionUpdate, onLetterGenerated, onError]);

  // Subscribe to additional loans
  const subscribe = useCallback((loanId) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'SUBSCRIBE',
        loan_id: loanId,
      }));
    }
  }, []);

  // Unsubscribe from a loan
  const unsubscribe = useCallback((loanId) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'UNSUBSCRIBE',
        loan_id: loanId,
      }));
    }
  }, []);

  // Send arbitrary message
  const sendMessage = useCallback((message) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    }
  }, []);

  // Disconnect
  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    if (wsRef.current) {
      wsRef.current.close(1000, 'User disconnect');
      wsRef.current = null;
    }
    setIsConnected(false);
  }, []);

  // Connect on mount
  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  return {
    isConnected,
    connectionError,
    subscribe,
    unsubscribe,
    sendMessage,
    reconnect: connect,
    disconnect,
  };
}

// =============================================================================
// useRealtorAuth - Authentication State
// =============================================================================

/**
 * Hook for realtor authentication state
 */
export function useRealtorAuth() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [realtor, setRealtor] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Check auth on mount
  useEffect(() => {
    const checkAuth = async () => {
      const token = localStorage.getItem('realtor_token');
      if (!token) {
        setLoading(false);
        return;
      }

      try {
        const response = await realtorApi('/me');
        setRealtor(response.profile);
        setIsAuthenticated(true);
      } catch (err) {
        localStorage.removeItem('realtor_token');
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    checkAuth();
  }, []);

  // Login
  const login = useCallback(async (email, password = null, magicLinkToken = null) => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${REALTOR_API}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email,
          password,
          magic_link_token: magicLinkToken,
        }),
      });

      const data = await response.json();

      if (!data.success) {
        throw new Error(data.error || 'Login failed');
      }

      localStorage.setItem('realtor_token', data.token);
      setIsAuthenticated(true);
      setRealtor({
        id: data.realtor_id,
        name: data.name,
      });

      return data;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  // Logout
  const logout = useCallback(async () => {
    const token = localStorage.getItem('realtor_token');
    if (token) {
      try {
        await fetch(`${REALTOR_API}/auth/logout`, {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` },
        });
      } catch (err) {
        console.error('Logout error:', err);
      }
    }
    localStorage.removeItem('realtor_token');
    setIsAuthenticated(false);
    setRealtor(null);
  }, []);

  return {
    isAuthenticated,
    realtor,
    loading,
    error,
    login,
    logout,
  };
}

// =============================================================================
// useRealtorLoan - Loan Data with Permissions
// =============================================================================

/**
 * Hook for fetching loan data with permissions
 *
 * @param {number} loanId - The loan ID
 */
export function useRealtorLoan(loanId) {
  const [loan, setLoan] = useState(null);
  const [permissions, setPermissions] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchLoan = useCallback(async () => {
    if (!loanId) return;

    setLoading(true);
    setError(null);

    try {
      const response = await realtorApi(`/loans/${loanId}`);
      setLoan(response.loan);
      setPermissions(response.loan.permissions);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [loanId]);

  useEffect(() => {
    fetchLoan();
  }, [fetchLoan]);

  return {
    loan,
    permissions,
    loading,
    error,
    refetch: fetchLoan,
  };
}

/**
 * Hook for fetching all realtor loans
 */
export function useRealtorLoans() {
  const [loans, setLoans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchLoans = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await realtorApi('/loans');
      setLoans(response.loans);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLoans();
  }, [fetchLoans]);

  return {
    loans,
    loading,
    error,
    refetch: fetchLoans,
  };
}

/**
 * Hook for loan timeline
 */
export function useRealtorTimeline(loanId) {
  const [milestones, setMilestones] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchTimeline = useCallback(async () => {
    if (!loanId) return;

    setLoading(true);
    setError(null);

    try {
      const response = await realtorApi(`/loans/${loanId}/timeline`);
      setMilestones(response.milestones);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [loanId]);

  useEffect(() => {
    fetchTimeline();
  }, [fetchTimeline]);

  return {
    milestones,
    loading,
    error,
    refetch: fetchTimeline,
  };
}

/**
 * Hook for loan conditions
 */
export function useRealtorConditions(loanId) {
  const [conditions, setConditions] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchConditions = useCallback(async () => {
    if (!loanId) return;

    setLoading(true);
    setError(null);

    try {
      const response = await realtorApi(`/loans/${loanId}/conditions`);
      setConditions(response.conditions);
      setSummary(response.summary);
    } catch (err) {
      // Conditions may not be available - not an error
      if (err.message.includes('403')) {
        setConditions([]);
        setSummary(null);
      } else {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  }, [loanId]);

  useEffect(() => {
    fetchConditions();
  }, [fetchConditions]);

  return {
    conditions,
    summary,
    loading,
    error,
    refetch: fetchConditions,
  };
}

// =============================================================================
// useLetterGeneration - Letter Management
// =============================================================================

/**
 * Hook for letter generation and management
 *
 * @param {number} loanId - The loan ID
 */
export function useLetterGeneration(loanId) {
  const [letters, setLetters] = useState([]);
  const [generating, setGenerating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Fetch letters
  const fetchLetters = useCallback(async () => {
    if (!loanId) return;

    setLoading(true);
    setError(null);

    try {
      const response = await realtorApi(`/loans/${loanId}/letters`);
      setLetters(response.letters);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [loanId]);

  // Generate letter
  const generateLetter = useCallback(async (letterType, options = {}) => {
    setGenerating(true);
    setError(null);

    try {
      const response = await realtorApi(`/loans/${loanId}/letters`, {
        method: 'POST',
        body: JSON.stringify({
          letter_type: letterType,
          property_address: options.propertyAddress,
          purchase_price: options.purchasePrice,
          approved_amount: options.approvedAmount,
          custom_variables: options.customVariables,
        }),
      });

      // Refresh letters list
      await fetchLetters();

      return response;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setGenerating(false);
    }
  }, [loanId, fetchLetters]);

  // Get letter details
  const getLetter = useCallback(async (letterId) => {
    try {
      const response = await realtorApi(`/letters/${letterId}`);
      return response.letter;
    } catch (err) {
      throw err;
    }
  }, []);

  // Get PDF download URL
  const getLetterPdfUrl = useCallback((letterId) => {
    const token = localStorage.getItem('realtor_token');
    return `${REALTOR_API}/letters/${letterId}/pdf?token=${token}`;
  }, []);

  // Get share URL
  const getShareUrl = useCallback((shareToken) => {
    return `${REALTOR_API}/letters/shared/${shareToken}`;
  }, []);

  useEffect(() => {
    fetchLetters();
  }, [fetchLetters]);

  return {
    letters,
    loading,
    generating,
    error,
    generateLetter,
    getLetter,
    getLetterPdfUrl,
    getShareUrl,
    refetch: fetchLetters,
  };
}

// =============================================================================
// useRealtorMessages - Messaging
// =============================================================================

/**
 * Hook for realtor messaging
 */
export function useRealtorMessages(loanId) {
  const [messages, setMessages] = useState([]);
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Fetch messages
  const fetchMessages = useCallback(async () => {
    if (!loanId) return;

    setLoading(true);
    setError(null);

    try {
      const response = await realtorApi(`/loans/${loanId}/messages`);
      setMessages(response.messages);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [loanId]);

  // Send message
  const sendMessage = useCallback(async (message, requestCallback = false) => {
    setSending(true);
    setError(null);

    try {
      const response = await realtorApi(`/loans/${loanId}/messages`, {
        method: 'POST',
        body: JSON.stringify({
          loan_id: loanId,
          message,
          request_callback: requestCallback,
        }),
      });

      await fetchMessages();
      return response;
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setSending(false);
    }
  }, [loanId, fetchMessages]);

  useEffect(() => {
    fetchMessages();
  }, [fetchMessages]);

  return {
    messages,
    loading,
    sending,
    error,
    sendMessage,
    refetch: fetchMessages,
  };
}

// =============================================================================
// useAIAssistant - AI Assistant
// =============================================================================

/**
 * Hook for AI assistant interactions
 */
export function useAIAssistant(loanId) {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Ask question
  const askQuestion = useCallback(async (question) => {
    setLoading(true);
    setError(null);

    // Add user message to history
    const userMessage = { role: 'user', content: question };
    setHistory(prev => [...prev, userMessage]);

    try {
      const response = await realtorApi('/assistant', {
        method: 'POST',
        body: JSON.stringify({
          loan_id: loanId,
          question,
          conversation_history: history,
        }),
      });

      // Add assistant response to history
      const assistantMessage = { role: 'assistant', content: response.answer };
      setHistory(prev => [...prev, assistantMessage]);

      return response.answer;
    } catch (err) {
      setError(err.message);
      // Remove failed user message
      setHistory(prev => prev.slice(0, -1));
      throw err;
    } finally {
      setLoading(false);
    }
  }, [loanId, history]);

  // Clear history
  const clearHistory = useCallback(() => {
    setHistory([]);
    setError(null);
  }, []);

  return {
    history,
    loading,
    error,
    askQuestion,
    clearHistory,
  };
}

// =============================================================================
// EXPORTS
// =============================================================================

export default {
  useLoanSync,
  useRealtorAuth,
  useRealtorLoan,
  useRealtorLoans,
  useRealtorTimeline,
  useRealtorConditions,
  useLetterGeneration,
  useRealtorMessages,
  useAIAssistant,
};
