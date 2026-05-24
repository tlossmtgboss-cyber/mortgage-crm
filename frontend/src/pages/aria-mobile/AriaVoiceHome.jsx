/**
 * AriaVoiceHome — Primary voice assistant interface for Perennia AI mobile.
 *
 * Dual-mode voice agent:
 *   1. LiveKit (primary): WebRTC real-time voice via LiveKit Cloud.
 *      STT (Deepgram Nova-3), LLM (Claude), TTS (Cartesia Sonic 3) all
 *      run server-side. Frontend just sends/receives audio. ~300-500ms latency.
 *   2. SSE fallback: If LiveKit isn't configured, falls back to the original
 *      Web Speech API + SSE streaming + ElevenLabs TTS pipeline.
 *
 * The LiveKit agent worker (aria/voice_agent.py) auto-joins the room when
 * a user connects. The frontend gets a token from POST /api/v1/livekit/token.
 */

import React, { useState, useRef, useCallback, useEffect } from 'react';
import { useNetworkStatus } from '../../hooks/useNetworkStatus';
import { useAriaVoice } from '../../hooks/useAriaVoice';
import api from '../../services/api';
import AriaTabNav from '../../components/mobile/AriaTabNav';
import { OfflineIndicator } from '../../components/mobile/OfflineIndicator';
import CallIntelligenceSlidePanel from '../../components/aria/CallIntelligenceSlidePanel';
import AriaCalendarSheet from './AriaCalendarSheet';
import './AriaVoiceHome.css';

// LiveKit + SSE imports — resolved dynamically to allow graceful fallback.
// Module-level variables are set once by the init effect and remain stable
// for the lifetime of the page. This avoids require() in ESM context.
let LiveKitRoom, RoomAudioRenderer, useVoiceAssistant, BarVisualizer, useRoomContext;
let _lkLoadAttempted = false;
let _lkLoadPromise = null;

function _loadLiveKit() {
  if (_lkLoadPromise) return _lkLoadPromise;
  _lkLoadPromise = import('@livekit/components-react')
    .then((mod) => {
      LiveKitRoom = mod.LiveKitRoom;
      RoomAudioRenderer = mod.RoomAudioRenderer;
      useVoiceAssistant = mod.useVoiceAssistant;
      BarVisualizer = mod.BarVisualizer;
      useRoomContext = mod.useRoomContext;
      return import('@livekit/components-styles');
    })
    .then(() => {
      _lkLoadAttempted = true;
      return true;
    })
    .catch(() => {
      _lkLoadAttempted = true;
      return false;
    });
  return _lkLoadPromise;
}

// SSE fallback: streamMessage loaded lazily (only if LiveKit unavailable).
let _sseModules = null;
let _sseLoadPromise = null;

function _loadSSEModules() {
  if (_sseLoadPromise) return _sseLoadPromise;
  _sseLoadPromise = import('../../services/mobileAriaApi')
    .then((apiMod) => {
      _sseModules = { streamMessage: apiMod.streamMessage };
      return _sseModules;
    }).catch(() => null);
  return _sseLoadPromise;
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

function DisconnectIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="1" y1="1" x2="23" y2="23" />
      <path d="M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V4a3 3 0 0 0-5.94-.6" />
      <path d="M17 16.95A7 7 0 0 1 5 12v-2m14 0v2c0 .76-.13 1.49-.36 2.18" />
      <line x1="12" y1="19" x2="12" y2="23" />
      <line x1="8" y1="23" x2="16" y2="23" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// LiveKit Voice Agent UI — renders inside LiveKitRoom context
// ---------------------------------------------------------------------------

function LiveKitVoiceUI({ onDisconnect, onAgentMissing, ciPanelOpen, setCiPanelOpen }) {
  const voiceAssistant = useVoiceAssistant();
  const room = useRoomContext();

  // Map LiveKit agent state to our UI states
  const agentState = voiceAssistant?.state || 'idle';

  // Watchdog: if no agent audio track shows up within 8s of connecting,
  // assume the aria-voice worker isn't running (or Cartesia is misconfigured)
  // and fall back to SSE mode so the user gets a working assistant.
  useEffect(() => {
    if (voiceAssistant?.audioTrack) return;
    const t = setTimeout(() => {
      if (!voiceAssistant?.audioTrack) {
        console.warn('[LiveKit] No agent audio track after 8s — falling back to SSE');
        onAgentMissing?.();
      }
    }, 8000);
    return () => clearTimeout(t);
  }, [voiceAssistant?.audioTrack, onAgentMissing]);

  // voiceAssistant.state can be: 'idle' | 'listening' | 'thinking' | 'speaking'
  const voiceState = (() => {
    switch (agentState) {
      case 'listening': return 'listening';
      case 'thinking': return 'processing';
      case 'speaking': return 'speaking';
      default: return 'connected';
    }
  })();

  const orbContainerClass = [
    'avh-orb-container',
    voiceState !== 'connected' ? `avh-orb-container--${voiceState}` : 'avh-orb-container--connected',
  ].filter(Boolean).join(' ');

  const tapLabelText = (() => {
    switch (voiceState) {
      case 'listening': return 'Listening...';
      case 'processing': return 'Thinking...';
      case 'speaking': return 'Aria is speaking';
      case 'connected': return 'Tap to disconnect';
      default: return 'Connected';
    }
  })();

  const handleOrbTap = useCallback(() => {
    // Tapping while connected disconnects
    if (onDisconnect) onDisconnect();
  }, [onDisconnect]);

  return (
    <>
      {/* LiveKit handles audio rendering via WebRTC */}
      <RoomAudioRenderer />

      {/* Center content */}
      <div className="avh-center">
        <h1 className="avh-title">Aria</h1>
        <p className="avh-subtitle">
          {voiceState === 'connected' ? 'Voice Connected' : 'Your AI Voice Assistant'}
        </p>

        {/* Mic orb — shows agent state via animations */}
        <div className={orbContainerClass}>
          <div className="avh-ring avh-ring--outer" />
          <div className="avh-ring avh-ring--mid" />
          <button
            className="avh-ring avh-ring--inner"
            onClick={handleOrbTap}
            aria-label="Disconnect voice session"
            type="button"
          >
            <span className="avh-mic-icon">
              {voiceState === 'connected' ? <DisconnectIcon /> : <MicIcon />}
            </span>
          </button>
        </div>

        {/* LiveKit audio visualizer */}
        {voiceState === 'speaking' && BarVisualizer && (
          <div className="avh-livekit-visualizer">
            <BarVisualizer
              state={agentState}
              barCount={5}
              trackRef={voiceAssistant?.audioTrack}
            />
          </div>
        )}

        <span className="avh-tap-label">{tapLabelText}</span>

        {/* Connection indicator */}
        <div className="avh-connection-badge">
          <span className="avh-connection-dot" />
          <span className="avh-connection-text">LiveKit WebRTC</span>
        </div>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// SSE Fallback helpers (only loaded when LiveKit unavailable)
// ---------------------------------------------------------------------------

const ABBREVIATIONS = /(?:Mr|Mrs|Ms|Dr|Jr|Sr|St|vs|etc|e\.g|i\.e)\./gi;

function extractSentences(buffer) {
  let safe = buffer.replace(ABBREVIATIONS, (m) => m.replace(/\./g, '\x00'));
  safe = safe.replace(/(\d)\.(\d)/g, '$1\x00$2');
  safe = safe.replace(/\.\.\./g, '\x00\x00\x00');
  const parts = safe.split(/(?<=[.!?])\s+|(?<=\n)/);
  if (parts.length <= 1) return { sentences: [], leftover: buffer };
  const leftover = parts.pop();
  const sentences = parts.filter(Boolean).map((s) => s.replace(/\x00/g, '.'));
  return { sentences, leftover: leftover.replace(/\x00/g, '.') };
}

// Shared <audio> element kept hot from the user gesture so iOS Safari /
// mobile Chrome don't reject playback later when the TTS response arrives.
// A single element reused across plays keeps the autoplay grant alive.
let _sharedAudioEl = null;

function _getSharedAudio() {
  if (_sharedAudioEl) return _sharedAudioEl;
  const a = new Audio();
  a.preload = 'auto';
  a.playsInline = true;
  a.setAttribute('playsinline', 'true');
  a.setAttribute('webkit-playsinline', 'true');
  _sharedAudioEl = a;
  return a;
}

// Call from inside a user gesture (mic tap). Plays a silent data URI to
// satisfy mobile autoplay policy so subsequent .play() calls succeed.
function unlockAudioPlayback() {
  try {
    const a = _getSharedAudio();
    // Tiny silent MP3 (44 bytes) — enough to mark the element as user-activated.
    a.src = 'data:audio/mp3;base64,SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjU4Ljc2LjEwMAAAAAAAAAAAAAAA//tQxAADB8AhSmxhIIEVCSiJrDCQBTcu3UrAIwUdkRgQbFAZC1CQEwTJ9mjRvBA4UOLD8nKVOWfh+UlK3z/177OXrfOdKl7097LFr89j9xC0fXmHkxpe/2T29c8w1+t4Hgv/0M3l+B+f/r8eHQEoBgAEoCwAAQ8AAAAA//tQxAQAB+wTKsCEYDDfA+ToEMwIA8AAAAA';
    a.muted = true;
    const p = a.play();
    if (p && typeof p.then === 'function') {
      p.then(() => {
        a.pause();
        a.muted = false;
        try { a.currentTime = 0; } catch { /* noop */ }
      }).catch(() => {
        a.muted = false;
      });
    }
  } catch { /* best effort */ }
}

function _speakViaBrowser(text, abortedRef) {
  return new Promise((resolve) => {
    if (!window.speechSynthesis || typeof SpeechSynthesisUtterance === 'undefined') {
      resolve(false);
      return;
    }
    try {
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 1.0;
      utterance.pitch = 1.0;
      let settled = false;
      const finish = (ok) => { if (!settled) { settled = true; resolve(ok); } };
      utterance.onend = () => finish(true);
      utterance.onerror = () => finish(false);
      if (abortedRef?.()) { finish(false); return; }
      window.speechSynthesis.speak(utterance);
    } catch {
      resolve(false);
    }
  });
}

class TTSQueue {
  constructor({ onFailure } = {}) {
    this._queue = [];
    this._playing = false;
    this._aborted = false;
    this._currentBlobUrl = null;
    this._onAllDone = null;
    this._onFailure = onFailure;
    this._failureNotified = false;
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
    const batch = this._queue.splice(0, Math.min(2, this._queue.length));
    const text = batch.join(' ');
    let playedViaApi = false;
    try {
      const res = await api.post('/api/v1/mobile-voice/tts/synthesize', {
        text,
        voice_settings: { stability: 0.45, similarity_boost: 0.78, style: 0.35, use_speaker_boost: true }
      });
      if (this._aborted) return;
      const b64 = res.data?.audio;
      if (!b64 || b64.length < 100) throw new Error('Empty audio');
      const binary = atob(b64);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      const blob = new Blob([bytes], { type: 'audio/mpeg' });
      const url = URL.createObjectURL(blob);
      this._currentBlobUrl = url;
      const audio = _getSharedAudio();
      audio.muted = false;
      audio.volume = 1.0;
      audio.src = url;
      try { audio.load(); } catch { /* noop */ }
      const playOk = await new Promise((resolve) => {
        const cleanup = () => {
          URL.revokeObjectURL(url);
          if (this._currentBlobUrl === url) this._currentBlobUrl = null;
          audio.onended = null;
          audio.onerror = null;
        };
        audio.onended = () => { cleanup(); resolve(true); };
        audio.onerror = () => { cleanup(); resolve(false); };
        const p = audio.play();
        if (p && typeof p.then === 'function') {
          p.catch((err) => {
            console.warn('[TTSQueue] audio.play() rejected:', err?.name || err);
            cleanup();
            resolve(false);
          });
        }
      });
      playedViaApi = playOk;
    } catch (err) {
      if (this._aborted) return;
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail || err?.message || 'unknown';
      console.warn(`[TTSQueue] TTS API failed (status=${status}):`, detail);
      if (!this._failureNotified && this._onFailure) {
        this._failureNotified = true;
        this._onFailure({ status, detail });
      }
    }
    if (!this._aborted && !playedViaApi) {
      // Fall through to browser speechSynthesis when API failed OR audio
      // playback was blocked (mobile autoplay policy).
      const spokeOk = await _speakViaBrowser(text, () => this._aborted);
      if (!spokeOk && !this._failureNotified && this._onFailure) {
        this._failureNotified = true;
        this._onFailure({ status: 0, detail: 'Audio playback blocked and no speech synthesis available' });
      }
    }
    if (!this._aborted) this._playNext();
  }

  stop() {
    this._aborted = true;
    this._queue = [];
    if (_sharedAudioEl) {
      try {
        _sharedAudioEl.pause();
        _sharedAudioEl.currentTime = 0;
      } catch { /* noop */ }
    }
    if (this._currentBlobUrl) {
      URL.revokeObjectURL(this._currentBlobUrl);
      this._currentBlobUrl = null;
    }
    if (window.speechSynthesis) {
      try { window.speechSynthesis.cancel(); } catch { /* noop */ }
    }
  }

  onAllDone(fn) { this._onAllDone = fn; }
}

function getOrCreateSessionId() {
  const STORAGE_KEY = 'aria-voice-session-id';
  const EXPIRY_KEY = 'aria-voice-session-expiry';
  const SESSION_TTL_MS = 30 * 60 * 1000;
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
// Main Component
// ---------------------------------------------------------------------------

export default function AriaVoiceHome() {
  const { isOnline } = useNetworkStatus();

  // LiveKit state
  const [lkToken, setLkToken] = useState(null);
  const [lkUrl, setLkUrl] = useState(null);
  const [lkConnecting, setLkConnecting] = useState(false);
  const [lkConnected, setLkConnected] = useState(false);
  const [lkAvailable, setLkAvailable] = useState(null); // null = checking, true/false
  const [lkError, setLkError] = useState(null);

  // SSE fallback state
  const [voiceState, setVoiceState] = useState('idle');
  const [sessionId] = useState(() => getOrCreateSessionId());
  const [responseText, setResponseText] = useState(null);
  const [showToast, setShowToast] = useState(false);
  const [toastExiting, setToastExiting] = useState(false);
  const toastTimerRef = useRef(null);
  const [actionToast, setActionToast] = useState(null);
  const actionToastTimerRef = useRef(null);
  const streamRef = useRef(null);
  const ttsQueueRef = useRef(null);
  const transcriptRef = useRef([]);
  const sessionStartRef = useRef(null);

  // Call Intelligence slide panel
  const [ciPanelOpen, setCiPanelOpen] = useState(false);
  const [calendarOpen, setCalendarOpen] = useState(false);

  // ---- Check LiveKit availability on mount ----
  useEffect(() => {
    let cancelled = false;
    async function init() {
      const lkLoaded = await _loadLiveKit();
      if (cancelled) return;
      if (!lkLoaded || !LiveKitRoom) {
        setLkAvailable(false);
        return;
      }
      try {
        const res = await api.get('/api/v1/livekit/health', { timeout: 5000 });
        if (cancelled) return;
        setLkAvailable(res.data?.configured === true);
        if (res.data?.url) setLkUrl(res.data.url);
      } catch {
        if (!cancelled) setLkAvailable(false);
      }
    }
    init();
    return () => { cancelled = true; };
  }, []);

  // ---- Load SSE modules lazily if LiveKit not available ----
  const [sseMods, setSseMods] = useState(_sseModules);
  useEffect(() => {
    if (lkAvailable === false && !sseMods) {
      _loadSSEModules().then((mods) => { if (mods) setSseMods(mods); });
    }
  }, [lkAvailable, sseMods]);

  // ---- LiveKit: fetch token and connect ----
  const lkConnectingRef = useRef(false);
  const connectLiveKit = useCallback(async () => {
    if (lkConnectingRef.current || lkConnected) return;
    lkConnectingRef.current = true;
    setLkConnecting(true);
    setLkError(null);

    try {
      const res = await api.post('/api/v1/livekit/token');
      setLkToken(res.data.token);
      setLkUrl(res.data.url);
      setLkConnected(true);
    } catch (err) {
      console.error('[AriaVoiceHome] LiveKit token fetch failed:', err);
      setLkError('Voice service unavailable — using text mode');
      setLkConnected(false);
      setLkAvailable(false);
    } finally {
      lkConnectingRef.current = false;
      setLkConnecting(false);
    }
  }, [lkConnected]);

  const disconnectLiveKit = useCallback(() => {
    setLkConnected(false);
    setLkToken(null);
    setLkUrl(null);
  }, []);

  // ---- SSE fallback handlers ----
  const saveSession = useCallback(() => {
    if (transcriptRef.current.length < 2) return;
    const transcript = [...transcriptRef.current];
    api.post('/api/v1/mobile-voice/sessions/save', {
      session_id: sessionId,
      transcript,
      started_at: sessionStartRef.current,
      voice_mode: 'sse',
    }).catch((err) => console.warn('[AriaVoiceHome] Failed to save session:', err));
  }, [sessionId]);

  const handleFinalTranscript = useCallback((text) => {
    if (!text || !text.trim() || !sseMods?.streamMessage) return;
    if (!sessionStartRef.current) sessionStartRef.current = new Date().toISOString();
    transcriptRef.current.push({ role: 'user', content: text, timestamp: new Date().toISOString() });

    setVoiceState('processing');
    setResponseText(null);
    setToastExiting(false);
    setShowToast(false);

    streamRef.current?.abort();
    ttsQueueRef.current?.stop();

    const queue = new TTSQueue({
      onFailure: ({ status, detail }) => {
        const msg = status === 502
          ? 'Voice service is down — showing text response.'
          : status === 401
            ? 'Voice service auth error — showing text response.'
            : `Audio failed (${detail || 'unknown'}) — showing text response.`;
        clearTimeout(actionToastTimerRef.current);
        setActionToast(msg);
        actionToastTimerRef.current = setTimeout(() => setActionToast(null), 8000);
      },
    });
    ttsQueueRef.current = queue;
    queue.onAllDone(() => {
      setVoiceState('idle');
      setToastExiting(true);
      setTimeout(() => { setShowToast(false); setToastExiting(false); setResponseText(null); }, 250);
    });

    let firstChunk = true;
    streamRef.current = sseMods.streamMessage(text, sessionId, {
      onChunk: (_chunk, fullText) => {
        if (firstChunk) { firstChunk = false; setVoiceState('speaking'); setShowToast(true); }
        setResponseText(fullText);
        const { sentences } = extractSentences(fullText);
        const alreadyQueued = queue._sentenceCount || 0;
        for (let i = alreadyQueued; i < sentences.length; i++) queue.enqueue(sentences[i]);
        queue._sentenceCount = sentences.length;
      },
      onDone: (fullText) => {
        setResponseText(fullText);
        if (fullText) transcriptRef.current.push({ role: 'assistant', content: fullText, timestamp: new Date().toISOString() });
        const { leftover } = extractSentences(fullText);
        if (leftover?.trim()) queue.enqueue(leftover);
        if (!queue._sentenceCount && fullText?.trim()) queue.enqueue(fullText);
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
        let msg = null;
        if (tool.includes('sms') || tool.includes('send_notification') || tool.includes('text')) {
          const name = result.recipient_name || result.borrower_name || '';
          msg = name ? `SMS sent to ${name}` : 'SMS sent';
        } else if (tool.includes('email')) msg = 'Email sent';
        else if (tool.includes('create_task')) msg = 'Task created';
        if (msg) {
          clearTimeout(actionToastTimerRef.current);
          setActionToast(msg);
          actionToastTimerRef.current = setTimeout(() => setActionToast(null), 6000);
        }
      },
    });
  }, [sessionId, sseMods]);

  // SSE voice hook — always called unconditionally (Rules of Hooks).
  // Output is ignored when LiveKit is active.
  const sseVoice = useAriaVoice({ onFinalTranscript: handleFinalTranscript });

  // Sync SSE recording state
  useEffect(() => {
    if (lkAvailable !== false) return;
    if (sseVoice.isRecording && voiceState === 'idle') setVoiceState('listening');
    else if (!sseVoice.isRecording && voiceState === 'listening') setVoiceState((prev) => prev === 'listening' ? 'idle' : prev);
  }, [sseVoice.isRecording, voiceState, lkAvailable]);

  // Abort SSE on network loss
  useEffect(() => {
    if (!isOnline && voiceState !== 'idle') {
      streamRef.current?.abort();
      ttsQueueRef.current?.stop();
      setVoiceState('idle');
      setResponseText('Connection lost.');
      setShowToast(true);
      clearTimeout(toastTimerRef.current);
      toastTimerRef.current = setTimeout(() => {
        setToastExiting(true);
        setTimeout(() => { setShowToast(false); setToastExiting(false); setResponseText(null); }, 250);
      }, 5000);
    }
  }, [isOnline, voiceState]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearTimeout(toastTimerRef.current);
      clearTimeout(actionToastTimerRef.current);
      streamRef.current?.abort();
      ttsQueueRef.current?.stop();
      if (transcriptRef.current.length >= 2) saveSession();
    };
  }, [saveSession]);

  // ---- Mic tap handler ----
  const handleMicTap = useCallback(() => {
    // Unlock audio inside the user gesture so iOS Safari / mobile Chrome
    // permit the deferred TTS playback that arrives later via SSE.
    unlockAudioPlayback();

    // LiveKit mode
    if (lkAvailable) {
      if (lkConnected) {
        disconnectLiveKit();
      } else {
        connectLiveKit();
      }
      return;
    }
    // SSE mode
    if (voiceState === 'processing') return;
    if (voiceState === 'speaking') {
      streamRef.current?.abort();
      ttsQueueRef.current?.stop();
      setVoiceState('idle');
      return;
    }
    sseVoice.toggleRecording();
  }, [lkAvailable, lkConnected, connectLiveKit, disconnectLiveKit, voiceState, sseVoice]);

  // ---- Orb class ----
  const currentVoiceState = lkConnected ? 'connected' : voiceState;
  const orbContainerClass = [
    'avh-orb-container',
    currentVoiceState !== 'idle' ? `avh-orb-container--${currentVoiceState}` : '',
  ].filter(Boolean).join(' ');

  // ---- Tap label ----
  const tapLabelText = (() => {
    if (lkConnecting) return 'Connecting...';
    if (lkError) return lkError;
    if (lkConnected) return 'Voice session active';
    if (lkAvailable === null) return 'Checking voice service...';
    if (sseVoice.error && voiceState === 'idle') return sseVoice.error;
    switch (voiceState) {
      case 'listening': return 'Listening...';
      case 'processing': return 'Thinking...';
      case 'speaking': return 'Aria is responding';
      default: return 'Tap to speak';
    }
  })();

  // ---- Render ----
  const innerContent = (
    <div className="aria-voice-home">
      <OfflineIndicator />
      <div className="avh-status-bar" />

      {/* Top bar */}
      <div className="avh-top-bar">
        {/* LiveKit indicator */}
        {lkAvailable && (
          <span className={`avh-lk-badge ${lkConnected ? 'avh-lk-badge--active' : ''}`}>
            {lkConnected ? 'LIVE' : 'WebRTC'}
          </span>
        )}
      </div>

      {/* Call Intelligence action bar — full width, prominent */}
      <button
        className={`avh-ci-action-bar ${ciPanelOpen ? 'avh-ci-action-bar--active' : ''}`}
        onClick={() => setCiPanelOpen((prev) => !prev)}
        type="button"
        aria-label={ciPanelOpen ? 'Close Call Intelligence panel' : 'Open Call Intelligence'}
        aria-expanded={ciPanelOpen}
      >
        <span className="avh-ci-action-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <path d="M12 2C8.13 2 5 5.13 5 9c0 2.38 1.19 4.47 3 5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.87-3.13-7-7-7z" fill="#7EB8F7" opacity="0.9" />
            <path d="M9 21v1c0 .55.45 1 1 1h4c.55 0 1-.45 1-1v-1H9z" fill="#7EB8F7" opacity="0.6" />
          </svg>
          <span className={`avh-ci-action-dot ${ciPanelOpen ? 'avh-ci-action-dot--active' : ''}`} />
        </span>
        <span className="avh-ci-action-label">
          {ciPanelOpen ? 'Call Intelligence Active' : 'Activate Call Intelligence'}
        </span>
        <svg className="avh-ci-action-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="rgba(126,184,247,0.6)" strokeWidth="2" strokeLinecap="round">
          <polyline points="9 18 15 12 9 6" />
        </svg>
      </button>

      {ciPanelOpen && (
        <CallIntelligenceSlidePanel onClose={() => setCiPanelOpen(false)} />
      )}

      {/* LiveKit mode — connected UI (guard must match LiveKitRoom wrapper at bottom) */}
      {lkConnected && LiveKitRoom && lkToken && lkUrl ? (
        <LiveKitVoiceUI
          onDisconnect={disconnectLiveKit}
          onAgentMissing={() => {
            disconnectLiveKit();
            setLkAvailable(false);
            setLkError('Voice agent unavailable — using text-to-speech mode');
          }}
          ciPanelOpen={ciPanelOpen}
          setCiPanelOpen={setCiPanelOpen}
        />
      ) : (
        <>
          {/* SSE mode or idle */}
          <div className="avh-center">
            {(voiceState === 'listening' || voiceState === 'processing') && sseVoice.transcript && (
              <div className={`avh-transcript-overlay ${voiceState === 'processing' ? 'avh-transcript-overlay--processing' : ''}`}>
                <p className="avh-transcript-text">
                  {voiceState === 'listening' && <span className="avh-listening-dot" />}
                  {sseVoice.transcript}
                </p>
              </div>
            )}

            <h1 className="avh-title">Aria</h1>
            <p className="avh-subtitle">Your AI Voice Assistant</p>

            <div className={orbContainerClass}>
              <div className="avh-ring avh-ring--outer" />
              <div className="avh-ring avh-ring--mid" />
              <button
                className="avh-ring avh-ring--inner"
                onClick={handleMicTap}
                aria-label={voiceState === 'listening' ? 'Stop listening' : 'Start voice input'}
                aria-pressed={voiceState === 'listening'}
                aria-busy={voiceState === 'processing' || lkConnecting}
                type="button"
              >
                <span className="avh-mic-icon">
                  <MicIcon />
                </span>
              </button>
            </div>

            <span className="avh-tap-label">{tapLabelText}</span>
          </div>

          {showToast && responseText && (
            <div className={`avh-response-toast ${toastExiting ? 'avh-response-toast--exiting' : ''}`}>
              <div className="avh-response-toast-inner">{responseText}</div>
            </div>
          )}
        </>
      )}

      <div className="avh-footer">
        <span className="avh-powered">Powered by Perennia AI</span>
      </div>

      {actionToast && (
        <div className="avh-action-toast">
          <span className="avh-action-toast-icon">{'\u2713'}</span>
          <span className="avh-action-toast-text">{actionToast}</span>
        </div>
      )}

      <AriaTabNav
        variant="dark"
        activeTab={calendarOpen ? 'calendar' : 'home'}
        onCalendarPress={() => setCalendarOpen(true)}
      />
      <AriaCalendarSheet
        open={calendarOpen}
        onClose={() => setCalendarOpen(false)}
      />
    </div>
  );

  // Wrap in LiveKitRoom when connected
  if (lkConnected && LiveKitRoom && lkToken && lkUrl) {
    return (
      <LiveKitRoom
        serverUrl={lkUrl}
        token={lkToken}
        connect={true}
        audio={true}
        video={false}
        onDisconnected={disconnectLiveKit}
        onError={(err) => {
          console.error('[LiveKit] Room error:', err);
          setLkError('Voice connection lost — switching to text mode');
          disconnectLiveKit();
          setLkAvailable(false);
        }}
      >
        {innerContent}
      </LiveKitRoom>
    );
  }

  return innerContent;
}
