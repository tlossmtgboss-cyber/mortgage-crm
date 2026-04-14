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
import AriaTabNav from '../../components/mobile/AriaTabNav';
import './AriaVoiceHome.css';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function generateSessionId() {
  return 'aria-voice-' + Date.now() + '-' + Math.random().toString(36).slice(2, 9);
}

// ---------------------------------------------------------------------------
// TTS — speak Aria's response aloud using the browser SpeechSynthesis API
// ---------------------------------------------------------------------------

let _ariaVoice = null;

function pickAriaVoice() {
  if (_ariaVoice) return _ariaVoice;
  const voices = window.speechSynthesis?.getVoices() || [];
  // Prefer a natural-sounding female English voice
  const preferred = [
    'Samantha', 'Karen', 'Moira', 'Tessa',         // macOS / iOS
    'Google US English', 'Google UK English Female', // Chrome
    'Microsoft Zira', 'Microsoft Jenny',             // Windows
  ];
  for (const name of preferred) {
    const match = voices.find((v) => v.name.includes(name) && v.lang.startsWith('en'));
    if (match) { _ariaVoice = match; return match; }
  }
  // Fallback: any English female voice, or first English voice
  const english = voices.filter((v) => v.lang.startsWith('en'));
  _ariaVoice = english[0] || voices[0] || null;
  return _ariaVoice;
}

function speakText(text, { onEnd } = {}) {
  const synth = window.speechSynthesis;
  if (!synth) { onEnd?.(); return null; }

  synth.cancel(); // stop any in-progress speech

  const utterance = new SpeechSynthesisUtterance(text);
  const voice = pickAriaVoice();
  if (voice) utterance.voice = voice;
  utterance.rate = 1.0;
  utterance.pitch = 1.05;
  utterance.volume = 1.0;
  utterance.onend = () => onEnd?.();
  utterance.onerror = () => onEnd?.();

  synth.speak(utterance);
  return utterance;
}

function stopSpeaking() {
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
  const [sessionId] = useState(() => generateSessionId());
  const [responseText, setResponseText] = useState(null);
  const [showToast, setShowToast] = useState(false);
  const [toastExiting, setToastExiting] = useState(false);
  const toastTimerRef = useRef(null);
  const abortRef = useRef(null);

  // Preload TTS voices (Chrome loads them asynchronously)
  useEffect(() => {
    const synth = window.speechSynthesis;
    if (!synth) return;
    pickAriaVoice();
    const handleVoicesChanged = () => { _ariaVoice = null; pickAriaVoice(); };
    synth.addEventListener('voiceschanged', handleVoicesChanged);
    return () => synth.removeEventListener('voiceschanged', handleVoicesChanged);
  }, []);

  // ---- Voice hook ----
  const handleFinalTranscript = useCallback(async (text) => {
    if (!text || !text.trim()) return;

    setVoiceState('processing');

    try {
      abortRef.current = new AbortController();
      const result = await sendMessage(text, sessionId, {}, { signal: abortRef.current.signal });

      if (result && result.response) {
        setVoiceState('speaking');
        setResponseText(result.response);
        setToastExiting(false);
        setShowToast(true);

        // Speak the response aloud
        speakText(result.response, {
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
        setVoiceState('idle');
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
      if (abortRef.current) {
        abortRef.current.abort();
      }
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
