import React, { useState, useRef, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './AriaVoiceApp.css';

const AriaVoiceApp = () => {
  const navigate = useNavigate();
  const [status, setStatus] = useState('idle'); // idle, connecting, listening, processing, speaking, error
  const [transcript, setTranscript] = useState('');
  const [response, setResponse] = useState('');
  const [error, setError] = useState(null);
  const [conversationHistory, setConversationHistory] = useState([]);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  const wsRef = useRef(null);
  const audioContextRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const processorRef = useRef(null);
  const audioQueueRef = useRef([]);
  const isPlayingRef = useRef(false);

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
        setError('Connection error. Please try again.');
        setStatus('error');
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

    try {
      switch (action) {
        case 'send_sms':
          await fetch(`${API_BASE_URL}/api/v1/communications/sms`, {
            method: 'POST',
            headers,
            body: JSON.stringify(params)
          });
          break;
        case 'send_email':
          await fetch(`${API_BASE_URL}/api/v1/communications/email`, {
            method: 'POST',
            headers,
            body: JSON.stringify(params)
          });
          break;
        case 'send_preapproval':
          await fetch(`${API_BASE_URL}/api/v1/leads/${params.lead_id}/pre-approval`, {
            method: 'POST',
            headers,
            body: JSON.stringify(params)
          });
          break;
        case 'complete_task':
          await fetch(`${API_BASE_URL}/api/v1/tasks/${params.task_id}/complete`, {
            method: 'POST',
            headers
          });
          break;
        default:
          console.log('[Aria] Unknown action:', action);
      }
    } catch (err) {
      console.error('[Aria] Action error:', err);
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

  // Quick login with stored credentials
  const handleQuickLogin = async () => {
    // For now, redirect to login page
    // TODO: Implement biometric login
    navigate('/login?redirect=/aria');
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
          <button className="aria-login-btn" onClick={handleQuickLogin}>
            Sign In to Continue
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

        {/* Conversation History */}
        <div className="aria-conversation">
          {conversationHistory.slice(-4).map((msg, idx) => (
            <div key={idx} className={`aria-message aria-message-${msg.role}`}>
              <span className="aria-message-role">{msg.role === 'user' ? 'You' : 'Aria'}</span>
              <p className="aria-message-content">{msg.content}</p>
            </div>
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

        {/* Footer */}
        <div className="aria-footer">
          <p>Powered by Perennia AI</p>
        </div>
      </div>
    </div>
  );
};

export default AriaVoiceApp;
