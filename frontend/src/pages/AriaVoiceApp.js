import React, { useState, useRef, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useBiometricLogin } from '../hooks/useBiometricLogin';
import { authAPI, aiAPI } from '../services/api';
import { useDashboard, useTasks, useLeads } from '../hooks/useQueries';
import { setAuth } from '../utils/auth';
import { haptics } from '../services/nativeServices';
import './AriaVoiceApp.css';

const AriaVoiceApp = () => {
  const navigate = useNavigate();
  const [status, setStatus] = useState('idle'); // idle, connecting, listening, processing, speaking, error
  const [transcript, setTranscript] = useState('');
  const [response, setResponse] = useState('');
  const [error, setError] = useState(null);
  const [conversationHistory, setConversationHistory] = useState([]);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState(null);
  const [textInput, setTextInput] = useState('');
  const [textLoading, setTextLoading] = useState(false);
  const [showFallback, setShowFallback] = useState(false);

  const {
    isAvailable: biometricAvailable,
    biometryDisplayName,
    hasStoredCredentials,
    isNative: isNativePlatform,
    authenticateWithBiometrics,
  } = useBiometricLogin();

  const wsRef = useRef(null);
  const audioContextRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const processorRef = useRef(null);
  const audioQueueRef = useRef([]);
  const isPlayingRef = useRef(false);
  const conversationRef = useRef(null);
  const wsFailCountRef = useRef(0);

  // Determine API URLs based on environment
  const isLocalDev = typeof window !== 'undefined' && (
    window.location.hostname === 'localhost' ||
    window.location.hostname === '127.0.0.1' ||
    window.location.hostname.startsWith('192.168.')
  );

  const API_BASE_URL = isLocalDev ? 'http://192.168.1.240:8000' : 'https://api.perenniaai.com';
  const WS_BASE_URL = isLocalDev ? 'ws://192.168.1.240:8000' : 'wss://api.perenniaai.com';

  // Check authentication on mount
  useEffect(() => {
    const token = localStorage.getItem('token');
    if (token) {
      setIsAuthenticated(true);
    }
  }, []);

  // Auto-attempt biometric login if available and user not authenticated
  useEffect(() => {
    if (!isAuthenticated && biometricAvailable && hasStoredCredentials) {
      handleBiometricLogin();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated, biometricAvailable, hasStoredCredentials]);

  // Auto-scroll conversation
  useEffect(() => {
    if (conversationRef.current) {
      conversationRef.current.scrollTop = conversationRef.current.scrollHeight;
    }
  }, [conversationHistory]);

  // Initialize audio context
  const initAudioContext = useCallback(() => {
    if (!audioContextRef.current) {
      audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: 16000
      });
    }
    return audioContextRef.current;
  }, []);

  // Convert Float32Array to Int16Array (linear16)
  const floatTo16BitPCM = (float32Array) => {
    const int16Array = new Int16Array(float32Array.length);
    for (let i = 0; i < float32Array.length; i++) {
      const s = Math.max(-1, Math.min(1, float32Array[i]));
      int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    return int16Array;
  };

  // Play audio from base64 linear16 data
  const playAudio = useCallback(async (base64Audio) => {
    try {
      const audioContext = initAudioContext();
      const binaryString = atob(base64Audio);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      const int16Array = new Int16Array(bytes.buffer);
      const float32Array = new Float32Array(int16Array.length);
      for (let i = 0; i < int16Array.length; i++) {
        float32Array[i] = int16Array[i] / 32768.0;
      }
      const audioBuffer = audioContext.createBuffer(1, float32Array.length, 16000);
      audioBuffer.copyToChannel(float32Array, 0);
      audioQueueRef.current.push(audioBuffer);
      if (!isPlayingRef.current) {
        playNextInQueue();
      }
    } catch (err) {
      console.error('Error playing audio:', err);
    }
  }, [initAudioContext]);

  // Play next audio in queue
  const playNextInQueue = useCallback(() => {
    if (audioQueueRef.current.length === 0) {
      isPlayingRef.current = false;
      setStatus('listening');
      return;
    }
    isPlayingRef.current = true;
    setStatus('speaking');
    const audioBuffer = audioQueueRef.current.shift();
    const audioContext = audioContextRef.current;
    const source = audioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(audioContext.destination);
    source.onended = playNextInQueue;
    source.start();
  }, []);

  // Connect to WebSocket
  const connect = useCallback(async () => {
    setStatus('connecting');
    setError(null);

    try {
      const token = localStorage.getItem('token');
      if (!token) {
        setError('Please log in first');
        setStatus('error');
        return;
      }

      const wsUrl = `${WS_BASE_URL}/api/v1/voice/ws/browser-voice?token=${token}`;
      console.log('[Aria] Connecting to:', wsUrl);

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[Aria] WebSocket connected');
        // Send initial config with CRM context
        ws.send(JSON.stringify({
          type: 'config',
          agent_name: 'Aria',
          system_prompt: `You are Aria, an AI voice assistant for a mortgage CRM. You can help users:
- Query leads, loans, and client information
- Send pre-approval letters
- Send SMS messages and emails
- Complete and manage tasks
- Check pipeline status and metrics
- Schedule appointments
- Look up borrower information

Be conversational, helpful, and concise. When users ask to perform actions, confirm the details before executing.`,
          voice: 'nova',
          language: 'en-US'
        }));
        startAudioCapture();
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log('[Aria] Message:', data.type);

        switch (data.type) {
          case 'ready':
            setStatus('listening');
            wsFailCountRef.current = 0;
            setShowFallback(false);
            break;
          case 'transcript':
            setTranscript(data.text);
            if (data.is_final) {
              setConversationHistory(prev => [...prev, { role: 'user', content: data.text }]);
              setTranscript('');
              setStatus('processing');
            }
            break;
          case 'response':
            setResponse(data.text);
            setConversationHistory(prev => [...prev, { role: 'assistant', content: data.text }]);
            break;
          case 'audio':
            playAudio(data.data);
            break;
          case 'action':
            // Handle CRM actions
            handleCRMAction(data.action, data.params);
            break;
          case 'error':
            setError(data.message);
            setStatus('error');
            break;
        }
      };

      ws.onerror = (err) => {
        console.error('[Aria] WebSocket error:', err);
        wsFailCountRef.current += 1;
        setError('Voice connection unavailable');
        setStatus('error');
        if (wsFailCountRef.current >= 1) {
          setShowFallback(true);
        }
      };

      ws.onclose = () => {
        console.log('[Aria] WebSocket closed');
        if (status !== 'idle') {
          setStatus('idle');
        }
      };

    } catch (err) {
      console.error('[Aria] Connection error:', err);
      setError(err.message);
      setStatus('error');
    }
  }, [WS_BASE_URL, playAudio, status]);

  // Handle CRM actions from voice commands
  const handleCRMAction = async (action, params) => {
    const token = localStorage.getItem('token');
    const headers = {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    };

    // Add pending action card to conversation
    const actionId = Date.now();
    const actionEntry = { role: 'action', id: actionId, action, data: params || {}, status: 'pending' };
    setConversationHistory(prev => [...prev, actionEntry]);

    try {
      switch (action) {
        case 'send_sms':
          await fetch(`${API_BASE_URL}/api/v1/communications/sms`, { method: 'POST', headers, body: JSON.stringify(params) });
          break;
        case 'send_email':
          await fetch(`${API_BASE_URL}/api/v1/communications/email`, { method: 'POST', headers, body: JSON.stringify(params) });
          break;
        case 'send_preapproval':
          await fetch(`${API_BASE_URL}/api/v1/leads/${params.lead_id}/pre-approval`, { method: 'POST', headers, body: JSON.stringify(params) });
          break;
        case 'complete_task':
          await fetch(`${API_BASE_URL}/api/v1/tasks/${params.task_id}/complete`, { method: 'POST', headers });
          break;
        case 'create_task':
          await fetch(`${API_BASE_URL}/api/v1/tasks`, { method: 'POST', headers, body: JSON.stringify(params) });
          break;
        case 'schedule_appointment':
          await fetch(`${API_BASE_URL}/api/v1/appointments`, { method: 'POST', headers, body: JSON.stringify(params) });
          break;
        default:
          console.log('[Aria] Unknown action:', action);
          break;
      }
      // Update card to success
      setConversationHistory(prev => prev.map(m => m.id === actionId ? { ...m, status: 'success' } : m));
      haptics.success();
    } catch (err) {
      console.error('[Aria] Action error:', err);
      setConversationHistory(prev => prev.map(m => m.id === actionId ? { ...m, status: 'error' } : m));
      haptics.error();
    }
  };

  // Handle text input submission
  const handleTextSubmit = async (e) => {
    e.preventDefault();
    const message = textInput.trim();
    if (!message || textLoading) return;

    setTextInput('');
    setTextLoading(true);
    setConversationHistory(prev => [...prev, { role: 'user', content: message }]);

    try {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        // WS connected — send as text message
        wsRef.current.send(JSON.stringify({ type: 'text', text: message }));
        // Response arrives via WS 'response' handler
      } else {
        // WS down — use REST smart-chat API
        const result = await aiAPI.smartChat(message, { include_context: true });
        setConversationHistory(prev => [...prev, {
          role: 'assistant',
          content: result.response || 'No response received.'
        }]);
      }
    } catch (err) {
      console.error('[Aria] Text error:', err);
      setConversationHistory(prev => [...prev, {
        role: 'assistant',
        content: 'Sorry, I couldn\'t process that. Please try again.'
      }]);
    } finally {
      setTextLoading(false);
    }
  };

  // Start audio capture
  const startAudioCapture = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });

      mediaStreamRef.current = stream;
      const audioContext = initAudioContext();

      if (audioContext.state === 'suspended') {
        await audioContext.resume();
      }

      const source = audioContext.createMediaStreamSource(stream);
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;

      processor.onaudioprocess = (e) => {
        if (wsRef.current?.readyState === WebSocket.OPEN && status === 'listening') {
          const float32Data = e.inputBuffer.getChannelData(0);
          const int16Data = floatTo16BitPCM(float32Data);
          const base64Audio = btoa(String.fromCharCode(...new Uint8Array(int16Data.buffer)));
          wsRef.current.send(JSON.stringify({
            type: 'audio',
            data: base64Audio
          }));
        }
      };

      source.connect(processor);
      processor.connect(audioContext.destination);
      setStatus('listening');

    } catch (err) {
      console.error('[Aria] Microphone error:', err);
      setError('Microphone access denied. Please allow microphone access.');
      setStatus('error');
    }
  }, [initAudioContext, status]);

  // Disconnect
  const disconnect = useCallback(() => {
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(track => track.stop());
      mediaStreamRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    audioQueueRef.current = [];
    isPlayingRef.current = false;
    setStatus('idle');
    setTranscript('');
    setResponse('');
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => disconnect();
  }, [disconnect]);

  // Handle main button click
  const handleMainButton = () => {
    if (status === 'idle' || status === 'error') {
      connect();
    } else {
      disconnect();
    }
  };

  // Biometric login - authenticate with Face ID/Touch ID
  const handleBiometricLogin = async () => {
    setLoginLoading(true);
    setLoginError(null);

    try {
      const credentials = await authenticateWithBiometrics();

      if (credentials) {
        // Use stored credentials to call login API
        const data = await authAPI.login(credentials.username, credentials.password);

        if (data.access_token) {
          await setAuth(data.access_token, data.user);
          setIsAuthenticated(true);
          haptics.success();
          return;
        }
      }
      // Biometric succeeded but no credentials or no token - fall back
      setLoginError('Biometric login failed. Please sign in manually.');
      haptics.warning();
    } catch (err) {
      console.error('Biometric login error:', err);
      setLoginError('Authentication failed. Please sign in manually.');
      haptics.error();
    } finally {
      setLoginLoading(false);
    }
  };

  // Quick login - try biometrics first, fall back to login page
  const handleQuickLogin = async () => {
    if (biometricAvailable && hasStoredCredentials) {
      await handleBiometricLogin();
    } else {
      navigate('/login?redirect=/aria');
    }
  };

  // Get status display
  const getStatusDisplay = () => {
    switch (status) {
      case 'idle': return 'Tap to start';
      case 'connecting': return 'Connecting to Aria...';
      case 'listening': return 'Listening...';
      case 'processing': return 'Thinking...';
      case 'speaking': return 'Aria is speaking...';
      case 'error': return error || 'Error occurred';
      default: return '';
    }
  };

  // Render login prompt if not authenticated
  if (!isAuthenticated) {
    return (
      <div className="aria-app">
        <div className="aria-container">
          <div className="aria-logo">
            <div className="aria-orb aria-orb-idle">
              <span className="aria-icon">A</span>
            </div>
          </div>
          <h1 className="aria-title">Aria</h1>
          <p className="aria-subtitle">Your AI Voice Assistant</p>

          {loginError && (
            <p className="aria-error" style={{ color: '#ff6b6b', fontSize: '14px', margin: '8px 0' }}>
              {loginError}
            </p>
          )}

          {/* Biometric login button (Face ID / Touch ID) */}
          {biometricAvailable && hasStoredCredentials && (
            <button
              className="aria-login-btn aria-biometric-btn"
              onClick={handleBiometricLogin}
              disabled={loginLoading}
              style={{ marginBottom: '12px' }}
            >
              {loginLoading ? 'Authenticating...' : `Sign In with ${biometryDisplayName}`}
            </button>
          )}

          {/* Standard sign in button */}
          <button
            className="aria-login-btn"
            onClick={() => navigate('/login?redirect=/aria')}
            disabled={loginLoading}
            style={biometricAvailable && hasStoredCredentials ? { opacity: 0.7, fontSize: '14px' } : {}}
          >
            {biometricAvailable && hasStoredCredentials ? 'Sign In with Email' : 'Sign In to Continue'}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="aria-app">
      <div className="aria-container">
        {/* Header */}
        <div className="aria-header">
          <h1 className="aria-title">Aria</h1>
          <p className="aria-subtitle">Your AI Voice Assistant</p>
        </div>

        {/* Main Voice Orb */}
        <div className="aria-orb-container" onClick={handleMainButton}>
          <div className={`aria-orb aria-orb-${status}`}>
            <div className="aria-orb-inner">
              {status === 'idle' && <span className="aria-mic-icon">🎙️</span>}
              {status === 'connecting' && <div className="aria-spinner"></div>}
              {status === 'listening' && <div className="aria-waves"></div>}
              {status === 'processing' && <div className="aria-dots"></div>}
              {status === 'speaking' && <div className="aria-pulse"></div>}
              {status === 'error' && <span className="aria-error-icon">⚠️</span>}
            </div>
          </div>
          <div className={`aria-ring aria-ring-${status}`}></div>
        </div>

        {/* Status Text */}
        <p className="aria-status">{getStatusDisplay()}</p>

        {/* Live Transcript */}
        {transcript && (
          <div className="aria-transcript">
            <p>{transcript}</p>
          </div>
        )}

        {/* Fallback Dashboard */}
        {showFallback && isAuthenticated && (
          <FallbackDashboard onRetry={() => {
            setShowFallback(false);
            wsFailCountRef.current = 0;
            connect();
          }} />
        )}

        {/* Conversation History */}
        <div className="aria-conversation" ref={conversationRef}>
          {conversationHistory.slice(-6).map((msg, idx) => (
            msg.role === 'action' ? (
              <ActionCard key={msg.id || idx} msg={msg} />
            ) : (
              <div key={idx} className={`aria-message aria-message-${msg.role}`}>
                <span className="aria-message-role">{msg.role === 'user' ? 'You' : 'Aria'}</span>
                <p className="aria-message-content">{msg.content}</p>
              </div>
            )
          ))}
        </div>

        {/* Action Buttons */}
        <div className="aria-actions">
          {status !== 'idle' && (
            <button className="aria-stop-btn" onClick={disconnect}>
              Stop
            </button>
          )}
        </div>

        {/* Text Input */}
        {isAuthenticated && (
          <form className="aria-text-form" onSubmit={handleTextSubmit}>
            <input
              className="aria-text-input"
              type="text"
              value={textInput}
              onChange={(e) => setTextInput(e.target.value)}
              placeholder={textLoading ? 'Sending...' : 'Type to Aria...'}
              disabled={textLoading}
              autoComplete="off"
            />
            <button
              className="aria-text-send"
              type="submit"
              disabled={!textInput.trim() || textLoading}
            >
              {textLoading ? '...' : '↑'}
            </button>
          </form>
        )}

        {/* Footer */}
        <div className="aria-footer">
          <p>Powered by Perennia AI</p>
        </div>
      </div>
    </div>
  );
};

// Action Card Component
const ACTION_CONFIG = {
  send_sms:              { icon: '\u{1F4AC}', label: 'Text Message Sent', color: '#10b981' },
  send_email:            { icon: '\u{1F4E7}', label: 'Email Sent',        color: '#3b82f6' },
  create_task:           { icon: '\u{1F4CB}', label: 'Task Created',      color: '#f59e0b' },
  complete_task:         { icon: '\u2713',     label: 'Task Completed',    color: '#10b981' },
  schedule_appointment:  { icon: '\u{1F4C5}', label: 'Appointment Set',   color: '#8b5cf6' },
  send_preapproval:      { icon: '\u{1F4C4}', label: 'Pre-Approval Sent', color: '#06b6d4' },
};

const ActionCard = ({ msg }) => {
  const config = ACTION_CONFIG[msg.action] || { icon: '\u26A1', label: msg.action, color: '#94a3b8' };
  const detail = msg.data?.to || msg.data?.phone || msg.data?.email
    || msg.data?.title || msg.data?.borrower_name || '';

  return (
    <div className={`aria-action-card aria-action-${msg.status}`}>
      <span className="aria-action-icon" style={{ borderColor: config.color }}>{config.icon}</span>
      <div className="aria-action-body">
        <div className="aria-action-label">{config.label}</div>
        {detail && <div className="aria-action-detail">{detail}</div>}
      </div>
      <span className="aria-action-status">
        {msg.status === 'pending' && <span className="aria-action-spinner" />}
        {msg.status === 'success' && <span style={{ color: '#10b981' }}>Done</span>}
        {msg.status === 'error' && <span style={{ color: '#ef4444' }}>Failed</span>}
      </span>
    </div>
  );
};

// Fallback Dashboard Component
const FallbackDashboard = ({ onRetry }) => {
  const { data: dashboard, isLoading: dLoading } = useDashboard();
  const { data: tasksData, isLoading: tLoading } = useTasks();
  const { data: leadsData, isLoading: lLoading } = useLeads();

  const pipeline = dashboard?.pipeline_stats || [];
  const tasks = (tasksData?.tasks || (Array.isArray(tasksData) ? tasksData : []))
    .filter(t => t.status !== 'completed').slice(0, 5);
  const leads = (Array.isArray(leadsData) ? leadsData : leadsData?.leads || []).slice(0, 5);
  const isLoading = dLoading && tLoading && lLoading;

  return (
    <div className="aria-fallback">
      <button className="aria-fallback-retry" onClick={onRetry}>
        Try Aria Again
      </button>

      {/* Pipeline */}
      <div className="aria-fallback-section">
        <div className="aria-fallback-title">Pipeline</div>
        {isLoading ? (
          <div className="aria-fallback-shimmer" />
        ) : (
          <div className="aria-fallback-pipeline">
            {pipeline.map(s => (
              <div key={s.id} className="aria-fallback-pill">
                <span className="aria-fallback-pill-count">{s.count}</span>
                <span className="aria-fallback-pill-label">{s.name}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Tasks */}
      <div className="aria-fallback-section">
        <div className="aria-fallback-title">Tasks ({tasks.length})</div>
        {tasks.length === 0 ? (
          <div className="aria-fallback-empty">No pending tasks</div>
        ) : tasks.map((t, i) => (
          <div key={i} className="aria-fallback-row">
            <span className={`aria-fallback-priority ${t.priority || 'medium'}`} />
            <span className="aria-fallback-row-text">{t.title}</span>
          </div>
        ))}
      </div>

      {/* Recent Leads */}
      <div className="aria-fallback-section">
        <div className="aria-fallback-title">Recent Leads</div>
        {leads.length === 0 ? (
          <div className="aria-fallback-empty">No leads</div>
        ) : leads.map((l, i) => (
          <div key={i} className="aria-fallback-row">
            <span className="aria-fallback-row-text">{l.name || `${l.first_name || ''} ${l.last_name || ''}`.trim()}</span>
            <span className="aria-fallback-badge">{l.stage || l.status}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default AriaVoiceApp;
