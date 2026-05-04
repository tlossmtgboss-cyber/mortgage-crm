import React, { useState, useRef, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useBiometricLogin } from '../hooks/useBiometricLogin';
import { authAPI, aiAPI } from '../services/api';
import { useDashboard, useTasks, useLeads } from '../hooks/useQueries';
import { setAuth } from '../utils/auth';
import { getItem, STORAGE_KEYS } from '../utils/storage';
import { secureFetch } from '../utils/security';
import { haptics } from '../services/nativeServices';
import useVoiceAudio from '../hooks/useVoiceAudio';
import useVoiceConnection from '../hooks/useVoiceConnection';
import useVoiceWorkflows from '../hooks/useVoiceWorkflows';
import MobileBottomNav from '../components/mobile/MobileBottomNav';
import CallIntelligenceButton from '../components/aria/CallIntelligenceButton';
import CallIntelligenceSlidePanel from '../components/aria/CallIntelligenceSlidePanel';
import CIStatusStrip from '../components/aria/CIStatusStrip';
import CILiveSidebar from '../components/aria/CILiveSidebar';
import useAriaCallIntelligence from '../hooks/useAriaCallIntelligence';
import { toast } from '../utils/toast';
import './AriaVoiceApp.css';

// White-label configuration — override per tenant
const VOICE_ASSISTANT_CONFIG = {
  name: window.__TENANT_CONFIG__?.voiceAssistantName || 'Aria',
  brandFooter: window.__TENANT_CONFIG__?.brandFooter || null,
  primaryColor: window.__TENANT_CONFIG__?.primaryColor || '#111827',
};

// H-3: Cap conversation history to prevent unbounded memory growth
const MAX_HISTORY = 50;

const AriaVoiceApp = () => {
  const navigate = useNavigate();

  // --- Local UI state ---
  const [transcript, setTranscript] = useState('');
  const [response, setResponse] = useState('');
  const [conversationHistory, setConversationHistory] = useState([]);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState(null);
  const [textInput, setTextInput] = useState('');
  const [textLoading, setTextLoading] = useState(false);
  const [isOffline, setIsOffline] = useState(!navigator.onLine);
  const [showCIPanel, setShowCIPanel] = useState(false);

  const conversationRef = useRef(null);

  const {
    isAvailable: biometricAvailable,
    biometryDisplayName,
    hasStoredCredentials,
    isNative: isNativePlatform,
    authenticateWithBiometrics,
  } = useBiometricLogin();

  // --- Placeholder wsRef (populated by useVoiceConnection) ---
  const connectionWsRef = useRef(null);

  // --- Voice Audio Hook ---
  const {
    startCapture,
    stopCapture,
    playAudioChunk,
    cleanup: cleanupAudio,
    setStatusRef,
  } = useVoiceAudio({
    wsRef: connectionWsRef,
    onStatusChange: (s) => {
      voiceConnection.setStatus(s);
    },
  });

  // --- Voice Workflows Hook ---
  const API_BASE_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

  const {
    activeWorkflows,
    cancelWorkflow,
    updateWorkflowStatus,
  } = useVoiceWorkflows({ apiBaseUrl: API_BASE_URL });

  // --- Call Intelligence Hook ---
  const ci = useAriaCallIntelligence({
    onArtifactsReady: (artifacts) => {
      toast.info(`${artifacts.length} new call intelligence results`);
    },
    onSessionStarted: (sessionId) => {
      setConversationHistory(prev => [...prev, {
        role: 'assistant',
        content: `Call Intelligence recording started. I'm analyzing the conversation in real-time.`,
      }].slice(-MAX_HISTORY));
    },
    onSessionEnded: () => {
      setConversationHistory(prev => [...prev, {
        role: 'assistant',
        content: `Call recording stopped. Processing with AI agents...`,
      }].slice(-MAX_HISTORY));
    },
  });

  // --- Handle CRM actions from voice commands ---
  const handleCRMAction = useCallback(async (action, params) => {
    const token = await getItem(STORAGE_KEYS.TOKEN);
    if (!token) {
      console.warn('[Aria] No auth token available');
      return;
    }
    const headers = {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    };

    // Add pending action card to conversation
    const actionId = Date.now();
    const actionEntry = { role: 'action', id: actionId, action, data: params || {}, status: 'pending' };
    setConversationHistory(prev => [...prev, actionEntry].slice(-MAX_HISTORY));

    try {
      switch (action) {
        case 'send_sms':
          await secureFetch(`${API_BASE_URL}/api/v1/communications/sms`, { method: 'POST', headers, body: JSON.stringify(params) });
          break;
        case 'send_email':
          await secureFetch(`${API_BASE_URL}/api/v1/communications/email`, { method: 'POST', headers, body: JSON.stringify(params) });
          break;
        case 'send_preapproval':
          await secureFetch(`${API_BASE_URL}/api/v1/leads/${params.lead_id}/pre-approval`, { method: 'POST', headers, body: JSON.stringify(params) });
          break;
        case 'complete_task':
          await secureFetch(`${API_BASE_URL}/api/v1/tasks/${params.task_id}/complete`, { method: 'POST', headers });
          break;
        case 'create_task':
          await secureFetch(`${API_BASE_URL}/api/v1/tasks`, { method: 'POST', headers, body: JSON.stringify(params) });
          break;
        case 'schedule_appointment':
          await secureFetch(`${API_BASE_URL}/api/v1/appointments`, { method: 'POST', headers, body: JSON.stringify(params) });
          break;
        case 'start_scheduling_workflow':
          await secureFetch(`${API_BASE_URL}/api/v1/voice/workflows`, {
            method: 'POST', headers,
            body: JSON.stringify(params),
          });
          break;
        case 'start_call_recording':
          await ci.startRecording();
          setShowCIPanel(true);
          break;
        case 'stop_call_recording':
          await ci.stopRecording();
          break;
        case 'get_recent_call_summary':
        case 'get_call_artifacts':
        case 'approve_artifact':
        case 'execute_artifacts':
        case 'send_document_checklist':
          // These are handled server-side by voice tools — UI updates come via CI hook
          break;
        default:
          console.log(`[${VOICE_ASSISTANT_CONFIG.name}] Unknown action:`, action);
          break;
      }
      // Update card to success
      setConversationHistory(prev => prev.map(m => m.id === actionId ? { ...m, status: 'success' } : m));
      haptics.success();
    } catch (err) {
      console.error(`[Aria] Action error: ${err?.message || 'Unknown error'}`);
      setConversationHistory(prev => prev.map(m => m.id === actionId ? { ...m, status: 'error' } : m));
      haptics.error();
    }
  }, [API_BASE_URL]);

  // --- Voice Connection Hook ---
  const voiceConnection = useVoiceConnection({
    onTranscript: (data) => {
      setTranscript(data.text);
      if (data.is_final) {
        setConversationHistory(prev => [...prev, { role: 'user', content: data.text }].slice(-MAX_HISTORY));
        setTranscript('');
      }
    },
    onResponse: (data) => {
      setResponse(data.text);
      setConversationHistory(prev => [...prev, { role: 'assistant', content: data.text }].slice(-MAX_HISTORY));
    },
    onAudio: (base64Data) => {
      playAudioChunk(base64Data);
    },
    onAction: handleCRMAction,
    onWorkflowStatus: updateWorkflowStatus,
    onError: (msg) => {
      // Error state is set inside the hook; nothing additional needed here
    },
    onReady: () => {
      // Could trigger UI celebration, currently a no-op
    },
    startAudioCapture: startCapture,
    stopAudioCapture: stopCapture,
    assistantName: VOICE_ASSISTANT_CONFIG.name,
  });

  // Sync the wsRef from connection hook into the audio hook's wsRef
  // (they share the same ref object)
  useEffect(() => {
    connectionWsRef.current = voiceConnection.wsRef.current;
  });

  // Keep audio hook's statusRef in sync with connection status
  useEffect(() => {
    setStatusRef(voiceConnection.status);
  }, [voiceConnection.status, setStatusRef]);

  // Check authentication on mount (C-5: use secure storage)
  useEffect(() => {
    const checkAuth = async () => {
      const token = await getItem(STORAGE_KEYS.TOKEN);
      if (token) {
        setIsAuthenticated(true);
      }
    };
    checkAuth();
  }, []);

  // MED-2: Biometric login requires explicit user tap — no auto-trigger.
  // The biometric login button is rendered in the login prompt below.

  // Auto-scroll conversation
  useEffect(() => {
    if (conversationRef.current) {
      conversationRef.current.scrollTop = conversationRef.current.scrollHeight;
    }
  }, [conversationHistory]);

  // Cleanup audio on unmount
  useEffect(() => {
    return () => cleanupAudio();
  }, [cleanupAudio]);

  // H-10: Offline detection
  useEffect(() => {
    const handleOnline = () => setIsOffline(false);
    const handleOffline = () => setIsOffline(true);
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  // Time-ago formatting helper
  const timeAgo = (dateStr) => {
    const seconds = Math.floor((Date.now() - new Date(dateStr)) / 1000);
    if (seconds < 60) return 'just now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
  };

  // Handle main button click
  const handleMainButton = () => {
    if (voiceConnection.status === 'idle' || voiceConnection.status === 'error') {
      voiceConnection.connect();
    } else {
      voiceConnection.disconnect();
    }
  };

  // Handle main button keyboard interaction (H-8: WCAG 2.1 AA)
  const handleOrbKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleMainButton();
    }
  };

  // Get aria-label for the orb based on status (H-8)
  const getOrbAriaLabel = () => {
    const s = voiceConnection.status;
    switch (s) {
      case 'idle':
        return 'Start voice assistant';
      case 'connecting':
        return `Connecting to ${VOICE_ASSISTANT_CONFIG.name}`;
      case 'listening':
        return 'Stop voice assistant, currently listening';
      case 'processing':
        return 'Stop voice assistant, currently processing';
      case 'speaking':
        return `Stop voice assistant, ${VOICE_ASSISTANT_CONFIG.name} is speaking`;
      case 'error':
        return 'Retry voice assistant, an error occurred';
      default:
        return 'Voice assistant';
    }
  };

  // Handle text input submission
  const handleTextSubmit = async (e) => {
    e.preventDefault();
    const message = textInput.trim();
    if (!message || textLoading) return;

    setTextInput('');
    setTextLoading(true);
    setConversationHistory(prev => [...prev, { role: 'user', content: message }].slice(-MAX_HISTORY));

    try {
      const sent = voiceConnection.sendMessage({ type: 'text', text: message });
      if (!sent) {
        // WS down — use REST smart-chat API
        const result = await aiAPI.smartChat(message, { include_context: true });
        setConversationHistory(prev => [...prev, {
          role: 'assistant',
          content: result.response || 'No response received.',
        }].slice(-MAX_HISTORY));
      }
    } catch (err) {
      console.error(`[Aria] Text error: ${err?.message || 'Unknown error'}`);
      setConversationHistory(prev => [...prev, {
        role: 'assistant',
        content: 'Sorry, I couldn\'t process that. Please try again.',
      }].slice(-MAX_HISTORY));
    } finally {
      setTextLoading(false);
    }
  };

  // Biometric login - authenticate with Face ID/Touch ID
  const handleBiometricLogin = async () => {
    setLoginLoading(true);
    setLoginError(null);

    try {
      const credentials = await authenticateWithBiometrics();

      if (credentials) {
        const data = await authAPI.login(credentials.username, credentials.password);

        if (data.access_token) {
          await setAuth(data.access_token, data.user, data.refresh_token);
          setIsAuthenticated(true);
          haptics.success();
          return;
        }
      }
      setLoginError('Biometric login failed. Please sign in manually.');
      haptics.warning();
    } catch (err) {
      console.error(`[Aria] Biometric login error: ${err?.message || 'Unknown error'}`);
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

  // Get status display text
  const getStatusDisplay = () => {
    const s = voiceConnection.status;
    switch (s) {
      case 'idle': return 'Tap to start';
      case 'connecting': return `Connecting to ${VOICE_ASSISTANT_CONFIG.name}...`;
      case 'listening': return 'Listening...';
      case 'processing': return 'Thinking...';
      case 'speaking': return `${VOICE_ASSISTANT_CONFIG.name} is speaking...`;
      case 'error': return voiceConnection.error || 'Error occurred';
      default: return '';
    }
  };

  // --- Workflow Card sub-component ---
  const VALID_STATES = new Set(['initiated', 'contact_found', 'sms_sent', 'awaiting_reply', 'negotiating', 'time_confirmed', 'appointment_booked', 'completed', 'expired', 'cancelled', 'failed']);

  const WorkflowCard = ({ wf }) => {
    const safeState = VALID_STATES.has(wf.state) ? wf.state : 'unknown';
    const stateLabels = {
      initiated: 'Starting...',
      contact_found: 'Contact found',
      sms_sent: 'SMS sent',
      awaiting_reply: 'Waiting for reply',
      negotiating: 'Negotiating time',
      time_confirmed: 'Time confirmed',
      appointment_booked: 'Appointment booked!',
      completed: 'Completed',
      expired: 'Expired',
      cancelled: 'Cancelled',
      failed: 'Failed',
      unknown: 'Unknown',
    };
    const isCancellable = ['initiated', 'contact_found', 'sms_sent', 'awaiting_reply', 'negotiating'].includes(safeState);
    const isActive = !['completed', 'expired', 'cancelled', 'failed', 'appointment_booked', 'unknown'].includes(safeState);
    const isFailed = safeState === 'failed';
    const isExpired = safeState === 'expired';
    const isCancelled = safeState === 'cancelled';
    const timeDisplay = wf.updated_at ? timeAgo(wf.updated_at) : '';

    let stateClass = isActive ? 'aria-workflow--active' : 'aria-workflow--done';
    if (isFailed) stateClass = 'aria-workflow--failed';
    else if (isExpired) stateClass = 'aria-workflow--expired';
    else if (isCancelled) stateClass = 'aria-workflow--cancelled';

    return (
      <div className={`aria-workflow-card ${stateClass}`} style={{ position: 'relative' }}>
        {isCancellable && (
          <button
            className="aria-workflow-cancel-btn"
            onClick={(e) => { e.stopPropagation(); cancelWorkflow(wf.workflow_id); }}
            aria-label={`Cancel scheduling with ${wf.contact_name}`}
            style={{ minHeight: '44px', minWidth: '44px' }}
          >
            &#x2715;
          </button>
        )}
        <div className="aria-workflow-header">
          <span className="aria-workflow-icon">
            {isFailed ? '\u26A0\uFE0F' : isCancelled ? '\u274C' : '\uD83D\uDCC5'}
          </span>
          <span className="aria-workflow-title">Scheduling with {wf.contact_name}</span>
        </div>
        <div className="aria-workflow-status">
          <span className={`aria-workflow-state aria-workflow-state--${safeState}`}>
            {stateLabels[safeState] || safeState}
          </span>
          {isActive && <span className="aria-workflow-spinner" />}
          {timeDisplay && <span className="aria-workflow-time">{timeDisplay}</span>}
        </div>

        {isFailed && (
          <div className="aria-workflow-detail">
            Booking failed &mdash; please schedule manually
            <br />
            <button
              className="aria-workflow-retry-btn"
              onClick={() => {
                handleCRMAction('start_scheduling_workflow', {
                  contact_name: wf.contact_name,
                  contact_id: wf.contact_id,
                });
              }}
              aria-label={`Retry scheduling with ${wf.contact_name}`}
              style={{ minHeight: '44px', minWidth: '44px' }}
            >
              Retry
            </button>
          </div>
        )}

        {isExpired && (
          <div className="aria-workflow-detail">
            Expired &mdash; no response received
          </div>
        )}

        {isCancelled && (
          <div className="aria-workflow-detail">
            Cancelled
          </div>
        )}

        {wf.confirmed_datetime && (
          <div className="aria-workflow-detail">
            Confirmed: {new Date(wf.confirmed_datetime).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}
          </div>
        )}
      </div>
    );
  };

  // ======================================================================
  // RENDER
  // ======================================================================

  const currentStatus = voiceConnection.status;

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
          <h1 className="aria-title">{VOICE_ASSISTANT_CONFIG.name}</h1>
          <p className="aria-subtitle">Your AI Voice Assistant</p>

          {loginError && (
            <p className="aria-error" style={{ color: '#ff6b6b', fontSize: '14px', margin: '8px 0' }} role="alert">
              {loginError}
            </p>
          )}

          {biometricAvailable && hasStoredCredentials && (
            <button
              className="aria-login-btn aria-biometric-btn"
              onClick={handleBiometricLogin}
              disabled={loginLoading}
              aria-label={loginLoading ? 'Authenticating' : `Sign in with ${biometryDisplayName}`}
              style={{ marginBottom: '12px', minHeight: '44px' }}
            >
              {loginLoading ? 'Authenticating...' : `Sign In with ${biometryDisplayName}`}
            </button>
          )}

          <button
            className="aria-login-btn"
            onClick={() => navigate('/login?redirect=/aria')}
            disabled={loginLoading}
            aria-label={biometricAvailable && hasStoredCredentials ? 'Sign in with email' : 'Sign in to continue'}
            style={biometricAvailable && hasStoredCredentials ? { opacity: 0.7, fontSize: '14px', minHeight: '44px' } : { minHeight: '44px' }}
          >
            {biometricAvailable && hasStoredCredentials ? 'Sign In with Email' : 'Sign In to Continue'}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="aria-app">
      {/* CI Status Strip — compact top bar when recording */}
      <CIStatusStrip
        isActive={ci.isActive}
        isStarting={ci.isStarting}
        duration={ci.duration}
        agentStatuses={ci.agentStatuses}
        agentEvents={ci.agentEvents}
        sessionState={ci.sessionState}
        onTogglePanel={() => setShowCIPanel(prev => !prev)}
        panelOpen={showCIPanel}
      />
      <div className="aria-container">
        {/* Header */}
        <div className="aria-header">
          <h1 className="aria-title">{VOICE_ASSISTANT_CONFIG.name}</h1>
          <p className="aria-subtitle">Your AI Voice Assistant</p>
        </div>

        {/* H-10: Offline banner */}
        {isOffline && (
          <div className="aria-offline-banner" role="alert">
            You're offline — voice commands unavailable
          </div>
        )}

        {/* Main Voice Orb — H-8: full keyboard + screen-reader accessibility */}
        <div
          className="aria-orb-container"
          onClick={handleMainButton}
          onKeyDown={handleOrbKeyDown}
          role="button"
          tabIndex={0}
          aria-label={getOrbAriaLabel()}
        >
          <div className={`aria-orb aria-orb-${currentStatus}`}>
            <div className="aria-orb-inner">
              {currentStatus === 'idle' && <span className="aria-mic-icon" aria-hidden="true">🎙️</span>}
              {currentStatus === 'connecting' && <div className="aria-spinner" aria-hidden="true"></div>}
              {currentStatus === 'listening' && <div className="aria-waves" aria-hidden="true"></div>}
              {currentStatus === 'processing' && <div className="aria-dots" aria-hidden="true"></div>}
              {currentStatus === 'speaking' && <div className="aria-pulse" aria-hidden="true"></div>}
              {currentStatus === 'error' && <span className="aria-error-icon" aria-hidden="true">⚠️</span>}
            </div>
          </div>
          <div className={`aria-ring aria-ring-${currentStatus}`} aria-hidden="true"></div>
        </div>

        {/* Call Intelligence Button — positioned below the orb */}
        <div className="aria-ci-button-container">
          <CallIntelligenceButton
            onClick={() => {
              if (ci.isActive) {
                ci.stopRecording();
              } else {
                ci.startRecording();
                setShowCIPanel(true);
              }
            }}
            isRecording={ci.isActive}
            isProcessing={ci.isStopping}
            artifactCount={ci.pendingCount}
            disabled={isOffline}
          />
          {ci.hasArtifacts && !showCIPanel && (
            <button
              className="aria-ci-results-btn"
              onClick={() => setShowCIPanel(true)}
              aria-label={`View ${ci.totalArtifactCount} call intelligence results`}
            >
              View Results ({ci.totalArtifactCount})
            </button>
          )}
        </div>

        {/* Status Text — H-8: live region for screen readers */}
        <p className="aria-status" aria-live="polite">{getStatusDisplay()}</p>

        {/* Live Transcript */}
        {transcript && (
          <div className="aria-transcript" aria-live="polite">
            <p>{transcript}</p>
          </div>
        )}

        {/* Fallback Dashboard */}
        {voiceConnection.showFallback && isAuthenticated && (
          <FallbackDashboard onRetry={() => {
            voiceConnection.setShowFallback(false);
            voiceConnection.wsFailCountRef.current = 0;
            voiceConnection.connect();
          }} />
        )}

        {/* Active Workflows */}
        {activeWorkflows.length > 0 && (
          <div className="aria-workflows-section" aria-label="Active workflows">
            {activeWorkflows.map(wf => (
              <WorkflowCard key={wf.workflow_id} wf={wf} />
            ))}
          </div>
        )}

        {/* Conversation History — H-8: log role for screen readers */}
        <div
          className="aria-conversation"
          ref={conversationRef}
          role="log"
          aria-label="Conversation history"
        >
          {conversationHistory.slice(-6).map((msg, idx) => (
            msg.role === 'action' ? (
              <ActionCard key={msg.id || idx} msg={msg} />
            ) : (
              <div key={idx} className={`aria-message aria-message-${msg.role}`}>
                <span className="aria-message-role">{msg.role === 'user' ? 'You' : VOICE_ASSISTANT_CONFIG.name}</span>
                <p className="aria-message-content">{msg.content}</p>
              </div>
            )
          ))}
        </div>

        {/* Action Buttons */}
        <div className="aria-actions">
          {currentStatus !== 'idle' && (
            <button
              className="aria-stop-btn"
              onClick={voiceConnection.disconnect}
              aria-label="Stop voice assistant"
              style={{ minHeight: '44px', minWidth: '44px' }}
            >
              Stop
            </button>
          )}
        </div>

        {/* Text Input — H-8: aria-label */}
        {isAuthenticated && (
          <form className="aria-text-form" onSubmit={handleTextSubmit}>
            <input
              className="aria-text-input"
              type="text"
              value={textInput}
              onChange={(e) => setTextInput(e.target.value)}
              placeholder={textLoading ? 'Sending...' : `Type to ${VOICE_ASSISTANT_CONFIG.name}...`}
              disabled={textLoading}
              autoComplete="off"
              aria-label="Send text command"
            />
            <button
              className="aria-text-send"
              type="submit"
              disabled={!textInput.trim() || textLoading}
              aria-label="Send message"
              style={{ minHeight: '44px', minWidth: '44px' }}
            >
              {textLoading ? '...' : '\u2191'}
            </button>
          </form>
        )}

        {/* Footer */}
        {VOICE_ASSISTANT_CONFIG.brandFooter !== '' && (
          <div className="aria-footer">
            <p>{VOICE_ASSISTANT_CONFIG.brandFooter || 'Powered by Perennia AI'}</p>
          </div>
        )}
      </div>

      {/* Mobile bottom navigation */}
      {isAuthenticated && <MobileBottomNav />}

      {/* Call Intelligence Live Sidebar — 4-quadrant agent dashboard */}
      {showCIPanel && (
        <CILiveSidebar
          isActive={ci.isActive}
          isStarting={ci.isStarting}
          duration={ci.duration}
          agentStatuses={ci.agentStatuses}
          agentEvents={ci.agentEvents}
          sessionState={ci.sessionState}
          onClose={() => setShowCIPanel(false)}
        />
      )}
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
  start_scheduling_workflow: { icon: '\u{1F4C5}', label: 'Scheduling Started', color: '#8b5cf6' },
  start_call_recording:    { icon: '\u{1F9E0}', label: 'Recording Started', color: '#ef4444' },
  stop_call_recording:     { icon: '\u{1F9E0}', label: 'Recording Stopped', color: '#f59e0b' },
  approve_artifact:        { icon: '\u2705', label: 'Artifact Approved', color: '#10b981' },
  execute_artifacts:       { icon: '\u26A1', label: 'Actions Executed',  color: '#3b82f6' },
};

const ActionCard = ({ msg }) => {
  const config = ACTION_CONFIG[msg.action] || { icon: '\u26A1', label: msg.action, color: '#94a3b8' };
  const detail = msg.data?.to || msg.data?.phone || msg.data?.email
    || msg.data?.title || msg.data?.borrower_name || '';

  return (
    <div className={`aria-action-card aria-action-${msg.status}`} role="status" aria-label={`${config.label}: ${msg.status}`}>
      <span className="aria-action-icon" style={{ borderColor: config.color }} aria-hidden="true">{config.icon}</span>
      <div className="aria-action-body">
        <div className="aria-action-label">{config.label}</div>
        {detail && <div className="aria-action-detail">{detail}</div>}
      </div>
      <span className="aria-action-status">
        {msg.status === 'pending' && <span className="aria-action-spinner" aria-label="Loading" />}
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
      <button
        className="aria-fallback-retry"
        onClick={onRetry}
        aria-label={`Retry ${VOICE_ASSISTANT_CONFIG.name} voice connection`}
        style={{ minHeight: '44px' }}
      >
        Try {VOICE_ASSISTANT_CONFIG.name} Again
      </button>

      {/* Pipeline */}
      <div className="aria-fallback-section">
        <div className="aria-fallback-title">Pipeline</div>
        {isLoading ? (
          <div className="aria-fallback-shimmer" aria-label="Loading pipeline data" />
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
