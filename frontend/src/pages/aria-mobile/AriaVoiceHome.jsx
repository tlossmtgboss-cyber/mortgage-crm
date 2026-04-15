/**
 * AriaVoiceHome — Primary voice assistant interface for Perennia AI mobile.
 *
 * Full-screen dark layout with animated mic orb, speech recognition via
 * useAriaVoice, streaming AI responses via SSE, and sentence-chunked
 * TTS playback so Aria starts speaking within ~2s instead of waiting
 * for the full response.
 */

import React, { useState, useRef, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAriaVoice } from '../../hooks/useAriaVoice';
import { streamMessage } from '../../services/mobileAriaApi';
import api from '../../services/api';
import AriaTabNav from '../../components/mobile/AriaTabNav';
import './AriaVoiceHome.css';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getOrCreateSessionId() {
  const STORAGE_KEY = 'aria-voice-session-id';
  const EXPIRY_KEY = 'aria-voice-session-expiry';
  const SESSION_TTL_MS = 30 * 60 * 1000; // 30 minutes

  try {
    const existing = sessionStorage.getItem(STORAGE_KEY);
    const expiry = sessionStorage.getItem(EXPIRY_KEY);
    if (existing && expiry && Date.now() < Number(expiry)) {
      sessionStorage.setItem(EXPIRY_KEY, String(Date.now() + SESSION_TTL_MS));
      return existing;
    }
  } catch { /* sessionStorage unavailable */ }

  const id = 'aria-voice-' + Date.now() + '-' + Math.random().toString(36).slice(2, 9);
  try {
    sessionStorage.setItem(STORAGE_KEY, id);
    sessionStorage.setItem(EXPIRY_KEY, String(Date.now() + SESSION_TTL_MS));
  } catch { /* sessionStorage unavailable */ }
  return id;
}

// ---------------------------------------------------------------------------
// Sentence splitter — splits streaming text into speakable chunks
// Handles abbreviations, decimal numbers, and ellipsis without false splits
// ---------------------------------------------------------------------------

const ABBREVIATIONS = /(?:Mr|Mrs|Ms|Dr|Jr|Sr|St|vs|etc|e\.g|i\.e)\./gi;

function extractSentences(buffer) {
  // Protect abbreviations by replacing dots with placeholder
  let safe = buffer.replace(ABBREVIATIONS, (m) => m.replace(/\./g, '\x00'));
  // Protect decimal numbers (3.5, $1,500.00)
  safe = safe.replace(/(\d)\.(\d)/g, '$1\x00$2');
  // Protect ellipsis
  safe = safe.replace(/\.\.\./g, '\x00\x00\x00');
  // Split on sentence boundaries
  const parts = safe.split(/(?<=[.!?])\s+|(?<=\n)/);
  if (parts.length <= 1) return { sentences: [], leftover: buffer };
  const leftover = parts.pop();
  // Restore dots
  const sentences = parts.filter(Boolean).map((s) => s.replace(/\x00/g, '.'));
  return { sentences, leftover: leftover.replace(/\x00/g, '.') };
}

// ---------------------------------------------------------------------------
// TTS Queue — plays sentences back-to-back via ElevenLabs
// ---------------------------------------------------------------------------

class TTSQueue {
  constructor() {
    this._queue = [];
    this._playing = false;
    this._aborted = false;
    this._currentAudio = null;
    this._onAllDone = null;
  }

  enqueue(text) {
    if (this._aborted || !text.trim()) return;
    this._queue.push(text);
    if (!this._playing) this._playNext();
  }

  async _playNext() {
    if (this._aborted || this._queue.length === 0) {
      this._playing = false;
      this._onAllDone?.();
      return;
    }

    this._playing = true;
    const text = this._queue.shift();

    try {
      const res = await api.post('/api/v1/mobile-voice/tts/synthesize', {
        text,
        voice_settings: {
          stability: 0.45,
          similarity_boost: 0.78,
          style: 0.35,
          use_speaker_boost: true
        }
      });
      if (this._aborted) return;

      const b64 = res.data?.audio;
      if (!b64 || b64.length < 100) throw new Error('Empty audio');

      const binary = atob(b64);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      const blob = new Blob([bytes], { type: 'audio/mpeg' });
      const url = URL.createObjectURL(blob);

      await new Promise((resolve) => {
        const audio = new Audio(url);
        this._currentAudio = audio;
        audio.onended = () => { URL.revokeObjectURL(url); this._currentAudio = null; resolve(); };
        audio.onerror = () => { URL.revokeObjectURL(url); this._currentAudio = null; resolve(); };
        audio.play().catch(resolve);
      });
    } catch (err) {
      if (this._aborted) return;
      // Instead of browser SpeechSynthesis fallback, just skip audio for this chunk
      // The text is already visible in the response toast
      console.warn('[TTSQueue] TTS failed, text visible in response toast:', err.message);
    }

    if (!this._aborted) this._playNext();
  }

  stop() {
    this._aborted = true;
    this._queue = [];
    if (this._currentAudio) {
      this._currentAudio.pause();
      this._currentAudio.currentTime = 0;
      this._currentAudio = null;
    }
  }

  onAllDone(fn) { this._onAllDone = fn; }
}

// ---------------------------------------------------------------------------
// Inline SVG: microphone icon
// ---------------------------------------------------------------------------

function MicIcon() {
  return (
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="1" width="6" height="12" rx="3" />
      <path d="M19 10v1a7 7 0 0 1-14 0v-1" />
      <line x1="12" y1="18" x2="12" y2="23" />
      <line x1="8" y1="23" x2="16" y2="23" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AriaVoiceHome() {
  const navigate = useNavigate();

  // Voice state: 'idle' | 'listening' | 'processing' | 'speaking'
  const [voiceState, setVoiceState] = useState('idle');
  const [sessionId] = useState(() => getOrCreateSessionId());
  const [responseText, setResponseText] = useState(null);
  const [showToast, setShowToast] = useState(false);
  const [toastExiting, setToastExiting] = useState(false);
  const toastTimerRef = useRef(null);
  const [actionToast, setActionToast] = useState(null);
  const actionToastTimerRef = useRef(null);

  const streamRef = useRef(null);   // { abort } from streamMessage
  const ttsQueueRef = useRef(null); // TTSQueue instance
  const bufferRef = useRef('');     // streaming text buffer for sentence splitting

  // ---- Voice hook ----
  const handleFinalTranscript = useCallback((text) => {
    if (!text || !text.trim()) return;

    setVoiceState('processing');
    setResponseText(null);
    setToastExiting(false);
    setShowToast(false);
    bufferRef.current = '';

    // Stop any previous stream/TTS
    streamRef.current?.abort();
    ttsQueueRef.current?.stop();

    const queue = new TTSQueue();
    ttsQueueRef.current = queue;

    // When all queued audio finishes playing, dismiss toast
    queue.onAllDone(() => {
      setVoiceState('idle');
      setToastExiting(true);
      setTimeout(() => {
        setShowToast(false);
        setToastExiting(false);
        setResponseText(null);
      }, 250);
    });

    let firstChunk = true;

    streamRef.current = streamMessage(text, sessionId, {
      onChunk: (_chunk, fullText) => {
        // Show toast and switch to speaking on first content
        if (firstChunk) {
          firstChunk = false;
          setVoiceState('speaking');
          setShowToast(true);
        }
        setResponseText(fullText);

        // Buffer text, extract complete sentences, enqueue for TTS
        bufferRef.current = fullText;

        // Find sentences in the full accumulated text that we haven't spoken yet
        const { sentences, leftover } = extractSentences(fullText);
        // Queue any new complete sentences
        // We track what's already been queued by the queue length + what's playing
        // Simpler: re-extract from fullText each time, only queue new ones
        // Use a separate counter
        const alreadyQueued = queue._sentenceCount || 0;
        for (let i = alreadyQueued; i < sentences.length; i++) {
          queue.enqueue(sentences[i]);
        }
        queue._sentenceCount = sentences.length;
      },

      onDone: (fullText) => {
        setResponseText(fullText);
        // Flush any remaining text that didn't end with punctuation
        const { leftover } = extractSentences(fullText);
        if (leftover && leftover.trim()) {
          queue.enqueue(leftover);
        }
        // If nothing was queued at all (very short response), queue the whole thing
        if (!queue._sentenceCount && fullText.trim()) {
          queue.enqueue(fullText);
        }
      },

      onError: (errMsg) => {
        setResponseText(errMsg || 'Sorry, something went wrong. Try again.');
        setShowToast(true);
        setVoiceState('idle');
        clearTimeout(toastTimerRef.current);
        toastTimerRef.current = setTimeout(() => {
          setToastExiting(true);
          setTimeout(() => { setShowToast(false); setToastExiting(false); setResponseText(null); }, 250);
        }, 5000);
      },

      onAction: (action) => {
        const tool = (action.tool || '').toLowerCase();
        const result = action.result || {};

        let actionMessage = null;
        if (tool.includes('sms') || tool.includes('send_notification') || tool.includes('text')) {
          const name = result.recipient_name || result.borrower_name || '';
          actionMessage = name ? `SMS sent to ${name}` : 'SMS sent';
        } else if (tool.includes('email')) {
          actionMessage = 'Email sent';
        } else if (tool.includes('create_task')) {
          actionMessage = 'Task created';
        }

        if (actionMessage) {
          clearTimeout(actionToastTimerRef.current);
          setActionToast(actionMessage);
          actionToastTimerRef.current = setTimeout(() => setActionToast(null), 6000);
        }
      },
    });
  }, [sessionId]);

  const {
    isRecording,
    transcript,
    error: voiceError,
    toggleRecording,
  } = useAriaVoice({
    onFinalTranscript: handleFinalTranscript,
  });

  // Sync recording state to voiceState
  useEffect(() => {
    if (isRecording && voiceState === 'idle') {
      setVoiceState('listening');
    } else if (!isRecording && voiceState === 'listening') {
      setVoiceState((prev) => (prev === 'listening' ? 'idle' : prev));
    }
  }, [isRecording, voiceState]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearTimeout(toastTimerRef.current);
      clearTimeout(actionToastTimerRef.current);
      streamRef.current?.abort();
      ttsQueueRef.current?.stop();
    };
  }, []);

  // ---- Handlers ----
  const handleMicTap = useCallback(() => {
    if (voiceState === 'processing') return;
    if (voiceState === 'speaking') {
      streamRef.current?.abort();
      ttsQueueRef.current?.stop();
      setVoiceState('idle');
      return;
    }
    toggleRecording();
  }, [voiceState, toggleRecording]);

  const handleCallIntelligence = useCallback(() => {
    navigate('/mobile-ci');
  }, [navigate]);

  // ---- Orb CSS class ----
  const orbContainerClass = [
    'avh-orb-container',
    voiceState !== 'idle' ? `avh-orb-container--${voiceState}` : '',
  ].filter(Boolean).join(' ');

  // ---- Tap label text ----
  const tapLabelText = (() => {
    if (voiceError && voiceState === 'idle') return voiceError;
    switch (voiceState) {
      case 'listening': return 'Listening...';
      case 'processing': return 'Thinking...';
      case 'speaking': return 'Aria is responding';
      default: return 'Tap to speak';
    }
  })();

  return (
    <div className="aria-voice-home">
      {/* Safe-area top padding */}
      <div className="avh-status-bar" />

      {/* Top bar with Call Intelligence button */}
      <div className="avh-top-bar">
        <button
          className="avh-ci-button"
          onClick={handleCallIntelligence}
          type="button"
          aria-label="Call Intelligence"
        >
          <span className="avh-ci-icon">
            <span className="avh-ci-icon-dot" />
          </span>
          Call Intelligence
        </button>
      </div>

      {/* Center content */}
      <div className="avh-center">
        {/* Live transcript overlay — visible during listening and briefly during processing */}
        {(voiceState === 'listening' || voiceState === 'processing') && transcript && (
          <div className={`avh-transcript-overlay ${voiceState === 'processing' ? 'avh-transcript-overlay--processing' : ''}`}>
            <p className="avh-transcript-text">
              {voiceState === 'listening' && <span className="avh-listening-dot" />}
              {transcript}
            </p>
          </div>
        )}

        <h1 className="avh-title">Aria</h1>
        <p className="avh-subtitle">Your AI Voice Assistant</p>

        {/* Mic orb */}
        <div className={orbContainerClass}>
          <div className="avh-ring avh-ring--outer" />
          <div className="avh-ring avh-ring--mid" />
          <button
            className="avh-ring avh-ring--inner"
            onClick={handleMicTap}
            aria-label={voiceState === 'listening' ? 'Stop listening' : 'Start voice input'}
            type="button"
          >
            <span className="avh-mic-icon">
              <MicIcon />
            </span>
          </button>
        </div>

        <span className="avh-tap-label">{tapLabelText}</span>
      </div>

      {/* Response toast — shows streaming text as it arrives */}
      {showToast && responseText && (
        <div className={`avh-response-toast ${toastExiting ? 'avh-response-toast--exiting' : ''}`}>
          <div className="avh-response-toast-inner">
            {responseText}
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="avh-footer">
        <span className="avh-powered">Powered by Perennia AI</span>
      </div>

      {/* Action confirmation toast — persistent green bar for SMS/email/task */}
      {actionToast && (
        <div className="avh-action-toast">
          <span className="avh-action-toast-icon">{'\u2713'}</span>
          <span className="avh-action-toast-text">{actionToast}</span>
        </div>
      )}

      {/* Bottom tab navigation */}
      <AriaTabNav variant="dark" activeTab="home" />
    </div>
  );
}
