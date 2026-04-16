// Talk to Agent - Browser-based voice conversation with AI agents
import React, { useState, useRef, useCallback, useEffect } from 'react';
import { getToken } from '../../utils/tokenStore';

const TalkToAgent = ({ agent, isOpen, onClose }) => {
  const [status, setStatus] = useState('idle'); // idle, connecting, ready, listening, processing, speaking, error
  const [transcript, setTranscript] = useState('');
  const [response, setResponse] = useState('');
  const [error, setError] = useState(null);
  const [conversationHistory, setConversationHistory] = useState([]);

  const wsRef = useRef(null);
  const audioContextRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const processorRef = useRef(null);
  const audioQueueRef = useRef([]);
  const isPlayingRef = useRef(false);

  // API base URL - use voice endpoint with browser-voice WebSocket
  const isLocalDev = typeof window !== 'undefined' && (
    window.location.hostname === 'localhost' ||
    window.location.hostname === '127.0.0.1' ||
    window.location.hostname.startsWith('192.168.')
  );
  const API_BASE_URL = isLocalDev ? 'ws://192.168.1.240:8000' : 'wss://api.perenniaai.com';

  // WebSocket endpoint for browser voice
  const WS_ENDPOINT = '/api/v1/voice/ws/browser-voice';

  // Initialize audio context
  // OpenAI Realtime API uses 24000 Hz sample rate for PCM16 audio
  const OPENAI_SAMPLE_RATE = 24000;

  const initAudioContext = useCallback(() => {
    if (!audioContextRef.current) {
      audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: OPENAI_SAMPLE_RATE
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

      // Decode base64 to ArrayBuffer
      const binaryString = atob(base64Audio);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      // Convert Int16 to Float32 for Web Audio API
      const int16Array = new Int16Array(bytes.buffer);
      const float32Array = new Float32Array(int16Array.length);
      for (let i = 0; i < int16Array.length; i++) {
        float32Array[i] = int16Array[i] / 32768.0;
      }

      // Create audio buffer at OpenAI's sample rate (24kHz)
      const audioBuffer = audioContext.createBuffer(1, float32Array.length, OPENAI_SAMPLE_RATE);
      audioBuffer.copyToChannel(float32Array, 0);

      // Queue the audio
      audioQueueRef.current.push(audioBuffer);

      // Play if not already playing
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
      return;
    }

    isPlayingRef.current = true;
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
      const token = getToken();
      // Security: Browser WebSocket API does not support Authorization headers; token in URL is the only option.
      const wsUrl = `${API_BASE_URL}${WS_ENDPOINT}?token=${token}`;

      console.log('[TalkToAgent] Connecting to:', wsUrl);

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[TalkToAgent] WebSocket connected');
      };

      ws.onmessage = async (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log('[TalkToAgent] Received:', data.type, data);

          switch (data.type) {
            case 'ready':
              setStatus('ready');
              // Start capturing audio
              startAudioCapture();
              break;

            case 'transcript':
              // Handle transcripts from both user and assistant
              if (data.role === 'user') {
                setTranscript(data.text);
                if (data.is_final && data.text) {
                  setConversationHistory(prev => [...prev, { role: 'user', text: data.text }]);
                }
              } else if (data.role === 'assistant') {
                setResponse(prev => data.is_final ? data.text : prev + data.text);
                if (data.is_final && data.text) {
                  setConversationHistory(prev => [...prev, { role: 'assistant', text: data.text }]);
                }
              }
              break;

            case 'speaking':
              // Handle speaking status for both user and assistant
              if (data.who === 'user') {
                setStatus(data.is_speaking ? 'listening' : 'ready');
              } else if (data.who === 'assistant') {
                setStatus(data.is_speaking ? 'speaking' : 'ready');
              }
              break;

            case 'audio':
              await playAudio(data.data);
              if (status !== 'speaking') {
                setStatus('speaking');
              }
              break;

            case 'error':
              setError(data.message);
              setStatus('error');
              break;

            default:
              console.log('[TalkToAgent] Unhandled message type:', data.type);
          }
        } catch (err) {
          console.error('[TalkToAgent] Error parsing message:', err);
        }
      };

      ws.onerror = (err) => {
        console.error('[TalkToAgent] WebSocket error:', err);
        setError('Connection error');
        setStatus('error');
      };

      ws.onclose = () => {
        console.log('[TalkToAgent] WebSocket closed');
        if (status !== 'idle') {
          setStatus('idle');
        }
      };

    } catch (err) {
      console.error('[TalkToAgent] Connection error:', err);
      setError(err.message);
      setStatus('error');
    }
  }, [API_BASE_URL, playAudio, status]);

  // Start audio capture from microphone
  const startAudioCapture = useCallback(async () => {
    try {
      console.log('[TalkToAgent] Starting audio capture...');

      // Request audio - the AudioContext will resample to match its sample rate (24kHz)
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: OPENAI_SAMPLE_RATE,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });

      mediaStreamRef.current = stream;
      const audioContext = initAudioContext();

      // Resume audio context if suspended
      if (audioContext.state === 'suspended') {
        await audioContext.resume();
      }

      const source = audioContext.createMediaStreamSource(stream);
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;

      processor.onaudioprocess = (e) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
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

      console.log('[TalkToAgent] Audio capture started');

    } catch (err) {
      console.error('[TalkToAgent] Microphone error:', err);
      setError('Microphone access denied. Please allow microphone access and try again.');
      setStatus('error');
    }
  }, [initAudioContext]);

  // Stop the conversation
  const disconnect = useCallback(() => {
    console.log('[TalkToAgent] Disconnecting...');

    // Stop audio capture
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }

    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(track => track.stop());
      mediaStreamRef.current = null;
    }

    // Close WebSocket
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    // Clear audio queue
    audioQueueRef.current = [];
    isPlayingRef.current = false;

    setStatus('idle');
    setTranscript('');
    setResponse('');
  }, []);

  // Interrupt the agent
  const interrupt = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'interrupt' }));
      audioQueueRef.current = [];
      isPlayingRef.current = false;
    }
  }, []);

  // Cleanup on unmount or close
  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  // Handle close
  useEffect(() => {
    if (!isOpen) {
      disconnect();
    }
  }, [isOpen, disconnect]);

  if (!isOpen) return null;

  const getStatusText = () => {
    switch (status) {
      case 'idle': return 'Click Start to begin';
      case 'connecting': return 'Connecting...';
      case 'ready': return 'Listening...';
      case 'listening': return 'You are speaking...';
      case 'processing': return `${agent?.name || 'Agent'} is thinking...`;
      case 'speaking': return `${agent?.name || 'Agent'} is speaking...`;
      case 'error': return 'Error occurred';
      default: return '';
    }
  };

  const getStatusColor = () => {
    switch (status) {
      case 'listening': return '#22c55e';
      case 'processing': return '#f59e0b';
      case 'speaking': return '#3b82f6';
      case 'error': return '#ef4444';
      default: return '#6b7280';
    }
  };

  return (
    <div className="talk-to-agent-overlay" onClick={onClose}>
      <div className="talk-to-agent-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Talk to {agent?.name || 'Agent'}</h2>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </div>

        <div className="modal-content">
          {/* Status Indicator */}
          <div className="status-section">
            <div
              className={`status-orb ${status}`}
              style={{ backgroundColor: getStatusColor() }}
            />
            <span className="status-text">{getStatusText()}</span>
          </div>

          {/* Error Display */}
          {error && (
            <div className="error-message">
              {error}
            </div>
          )}

          {/* Conversation History */}
          <div className="conversation-history">
            {conversationHistory.map((msg, idx) => (
              <div key={idx} className={`message ${msg.role}`}>
                <span className="role">{msg.role === 'user' ? 'You' : agent?.name || 'Agent'}:</span>
                <span className="text">{msg.text}</span>
              </div>
            ))}

            {/* Current transcript */}
            {transcript && status === 'listening' && (
              <div className="message user current">
                <span className="role">You:</span>
                <span className="text">{transcript}</span>
              </div>
            )}

            {/* Current response */}
            {response && status === 'speaking' && (
              <div className="message assistant current">
                <span className="role">{agent?.name || 'Agent'}:</span>
                <span className="text">{response}</span>
              </div>
            )}
          </div>

          {/* Controls */}
          <div className="controls">
            {status === 'idle' || status === 'error' ? (
              <button className="btn-start" onClick={connect}>
                Start Conversation
              </button>
            ) : (
              <>
                <button
                  className="btn-interrupt"
                  onClick={interrupt}
                  disabled={status !== 'speaking'}
                >
                  Interrupt
                </button>
                <button className="btn-end" onClick={disconnect}>
                  End Call
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      <style>{`
        .talk-to-agent-overlay {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0, 0, 0, 0.6);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1000;
        }

        .talk-to-agent-modal {
          background: white;
          border-radius: 16px;
          width: 500px;
          max-width: 90vw;
          max-height: 80vh;
          display: flex;
          flex-direction: column;
          box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
        }

        .modal-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 20px 24px;
          border-bottom: 1px solid #e5e7eb;
        }

        .modal-header h2 {
          margin: 0;
          font-size: 20px;
        }

        .close-btn {
          background: none;
          border: none;
          font-size: 28px;
          cursor: pointer;
          color: #6b7280;
          line-height: 1;
        }

        .modal-content {
          padding: 24px;
          flex: 1;
          overflow: hidden;
          display: flex;
          flex-direction: column;
        }

        .status-section {
          display: flex;
          align-items: center;
          gap: 12px;
          margin-bottom: 20px;
          padding: 16px;
          background: #f9fafb;
          border-radius: 12px;
        }

        .status-orb {
          width: 16px;
          height: 16px;
          border-radius: 50%;
          animation: pulse 2s infinite;
        }

        .status-orb.listening,
        .status-orb.speaking {
          animation: pulse 1s infinite;
        }

        @keyframes pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.7; transform: scale(1.1); }
        }

        .status-text {
          font-size: 14px;
          color: #374151;
        }

        .error-message {
          background: #fef2f2;
          border: 1px solid #fee2e2;
          color: #dc2626;
          padding: 12px 16px;
          border-radius: 8px;
          margin-bottom: 16px;
          font-size: 14px;
        }

        .conversation-history {
          flex: 1;
          overflow-y: auto;
          min-height: 200px;
          max-height: 300px;
          border: 1px solid #e5e7eb;
          border-radius: 12px;
          padding: 16px;
          margin-bottom: 20px;
          background: #fafafa;
        }

        .message {
          margin-bottom: 12px;
          padding: 10px 14px;
          border-radius: 12px;
          font-size: 14px;
        }

        .message.user {
          background: #e0e7ff;
          margin-left: 20px;
        }

        .message.assistant {
          background: #ecfdf5;
          margin-right: 20px;
        }

        .message.current {
          opacity: 0.7;
        }

        .message .role {
          font-weight: 600;
          display: block;
          margin-bottom: 4px;
          font-size: 12px;
          color: #6b7280;
        }

        .message .text {
          color: #1f2937;
        }

        .controls {
          display: flex;
          gap: 12px;
          justify-content: center;
        }

        .btn-start {
          background: #22c55e;
          color: white;
          border: none;
          padding: 14px 32px;
          border-radius: 30px;
          font-size: 16px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s;
        }

        .btn-start:hover {
          background: #16a34a;
          transform: scale(1.02);
        }

        .btn-interrupt {
          background: #f59e0b;
          color: white;
          border: none;
          padding: 12px 24px;
          border-radius: 8px;
          font-size: 14px;
          font-weight: 500;
          cursor: pointer;
        }

        .btn-interrupt:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .btn-end {
          background: #ef4444;
          color: white;
          border: none;
          padding: 12px 24px;
          border-radius: 8px;
          font-size: 14px;
          font-weight: 500;
          cursor: pointer;
        }

        .btn-end:hover {
          background: #dc2626;
        }
      `}</style>
    </div>
  );
};

export default TalkToAgent;
