/**
 * AriaVoiceHome — Primary voice assistant interface for Perennia AI mobile.
 *
 * Full-screen dark layout with animated mic orb, speech recognition via
 * useAriaVoice, and AI responses via the orchestrator chat endpoint.
 */

import React, { useState, useRef, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAriaVoice } from '../../hooks/useAriaVoice';
import { sendMessage } from '../../services/mobileAriaApi';
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
      // Refresh expiry on use
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
// TTS — speak Aria's response via ElevenLabs (backend-proxied)
// Falls back to browser SpeechSynthesis if the API call fails.
// ---------------------------------------------------------------------------

let _currentAudio = null;

async function speakText(text, { onEnd, signal } = {}) {
  stopSpeaking();

  try {
    const res = await api.post('/api/v1/mobile-voice/tts/synthesize', {
      text,
    }, { signal });

    if (signal?.aborted) return;

    const b64 = res.data?.audio;
    if (!b64 || b64.length < 100) {
      throw new Error('Empty audio response from TTS API');
    }

    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const blob = new Blob([bytes], { type: 'audio/mpeg' });
    const url = URL.createObjectURL(blob);

    const audio = new Audio(url);
    _currentAudio = audio;
    audio.onended = () => { URL.revokeObjectURL(url); _currentAudio = null; onEnd?.(); };
    audio.onerror = () => { URL.revokeObjectURL(url); _currentAudio = null; onEnd?.(); };
    await audio.play();
  } catch (err) {
    if (err?.name === 'CanceledError' || signal?.aborted) return;
    console.warn('[AriaVoice] TTS API failed, using browser voice:', err.message);
    // Fallback to browser SpeechSynthesis
    const synth = window.speechSynthesis;
    if (!synth) { onEnd?.(); return; }
    synth.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.0;
    utterance.onend = () => onEnd?.();
    utterance.onerror = () => onEnd?.();
    synth.speak(utterance);
  }
}

function stopSpeaking() {
  if (_currentAudio) {
    _currentAudio.pause();
    _currentAudio.currentTime = 0;
    _currentAudio = null;
  }
  window.speechSynthesis?.cancel();
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
  const abortRef = useRef(null);

  const ttsAbortRef = useRef(null);

  // ---- Voice hook ----
  const handleFinalTranscript = useCallback(async (text) => {
    if (!text || !text.trim()) return;

    setVoiceState('processing');

    try {
      abortRef.current = new AbortController();
      const result = await sendMessage(text, sessionId, {}, { signal: abortRef.current.signal });

      // Extract response text — handle both success and error shapes
      const responseText = result?.response || result?.final_response || result?.message;

      if (responseText) {
        setVoiceState('speaking');
        setResponseText(responseText);
        setToastExiting(false);
        setShowToast(true);

        // Speak the response aloud via TTS
        ttsAbortRef.current = new AbortController();
        speakText(responseText, {
          signal: ttsAbortRef.current.signal,
          onEnd: () => {
            setVoiceState('idle');
            // Dismiss toast shortly after speech ends
            setToastExiting(true);
            setTimeout(() => {
              setShowToast(false);
              setToastExiting(false);
              setResponseText(null);
            }, 250);
          },
        });
      } else {
        // Show error feedback instead of silently going idle
        const errMsg = result?.error || 'Sorry, I couldn\'t process that. Try again.';
        setResponseText(errMsg);
        setToastExiting(false);
        setShowToast(true);
        setVoiceState('idle');
        // Auto-dismiss error toast
        clearTimeout(toastTimerRef.current);
        toastTimerRef.current = setTimeout(() => {
          setToastExiting(true);
          setTimeout(() => { setShowToast(false); setToastExiting(false); setResponseText(null); }, 250);
        }, 5000);
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        console.error('[AriaVoiceHome] sendMessage error:', err);
      }
      setVoiceState('idle');
    }
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
      // Only go idle if not transitioning to processing
      setVoiceState((prev) => (prev === 'listening' ? 'idle' : prev));
    }
  }, [isRecording, voiceState]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearTimeout(toastTimerRef.current);
      stopSpeaking();
      if (abortRef.current) abortRef.current.abort();
      if (ttsAbortRef.current) ttsAbortRef.current.abort();
    };
  }, []);

  // ---- Handlers ----
  const handleMicTap = useCallback(() => {
    if (voiceState === 'processing') return;
    // If Aria is speaking, stop her and go idle
    if (voiceState === 'speaking') {
      stopSpeaking();
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
        {/* Live transcript overlay */}
        {voiceState === 'listening' && transcript && (
          <div className="avh-transcript-overlay">
            <p className="avh-transcript-text">{transcript}</p>
          </div>
        )}

        <h1 className="avh-title">Aria</h1>
        <p className="avh-subtitle">Your AI Voice Assistant</p>

        {/* Mic orb */}
        <div className={orbContainerClass}>
          {/* Outer ring */}
          <div className="avh-ring avh-ring--outer" />
          {/* Middle ring */}
          <div className="avh-ring avh-ring--mid" />
          {/* Inner ring — tappable */}
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

      {/* Response toast */}
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

      {/* Bottom tab navigation */}
      <AriaTabNav variant="dark" activeTab="home" />
    </div>
  );
}
