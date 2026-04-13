/**
 * AriaVoiceOnboarding.jsx
 * Perennia AI — Aria Voice Profile Enrollment (Web/Capacitor)
 *
 * First-launch conversational flow where Aria learns the user's voice.
 * Aria presents 7 spoken prompts; user records each one using the
 * MediaRecorder API (works in WKWebView via Capacitor).
 *
 * All recordings are uploaded to the voice profile API which builds
 * a speaker embedding (resemblyzer d-vector) stored against the user's account.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { voiceProfileApi } from '../../services/voiceProfileService';
import './AriaVoiceOnboarding.css';

// ─── Aria's onboarding script ───────────────────────────────────────────────
const VOICE_PROMPTS = [
  {
    id: 'intro',
    ariaSays: "Hi! I'm Aria. To give you the best experience, I'd love to learn your voice. Let's start simple — just introduce yourself.",
    userInstruction: "Say your full name and title, just like you'd introduce yourself on a call.",
    hint: 'e.g. "Hi, I\'m Sarah Chen, Senior Loan Officer at Perennia."',
    minDurationMs: 3000,
    category: 'intro',
  },
  {
    id: 'nmls',
    ariaSays: "Great! Now let me hear how you naturally say your credentials — this helps me recognize you on compliance-sensitive calls.",
    userInstruction: "Say your NMLS number and the states you're licensed in.",
    hint: 'e.g. "My NMLS is 1234567, licensed in California, Texas, and Florida."',
    minDurationMs: 4000,
    category: 'numeric',
  },
  {
    id: 'opener',
    ariaSays: "Perfect. Now — what do you actually say when a fresh lead picks up the phone? Give me your real opener.",
    userInstruction: "Say your go-to opening line when calling a new lead.",
    hint: 'Speak naturally — exactly how you sound on a real call.',
    minDurationMs: 5000,
    category: 'professional',
  },
  {
    id: 'loan_story',
    ariaSays: "I love it. Tell me about a loan you're proud of — doesn't need to be long, just describe it like you're telling a colleague.",
    userInstruction: "Describe a loan you recently closed or a client you helped.",
    hint: 'Aim for 3-5 sentences. Speak at your natural pace.',
    minDurationMs: 8000,
    category: 'emotional',
  },
  {
    id: 'read_aloud',
    ariaSays: "Almost there. I'm going to give you a sentence to read out loud — just read it naturally, don't over-pronounce.",
    userInstruction: 'Read this out loud: "I help families find the right mortgage for their unique financial situation, and I take that responsibility seriously."',
    hint: 'Read it at your natural speaking pace.',
    minDurationMs: 5000,
    category: 'natural',
  },
  {
    id: 'numbers',
    ariaSays: "One more — numbers are really helpful for voice calibration. Count for me slowly.",
    userInstruction: "Count from one to ten, slowly and clearly.",
    hint: 'Pause briefly between each number.',
    minDurationMs: 6000,
    category: 'numeric',
  },
  {
    id: 'closing',
    ariaSays: "Last one! This is your chance to say something you genuinely mean — I'll use this to calibrate your authentic voice.",
    userInstruction: 'Say: "Aria, this is my voice. Recognize me every time."',
    hint: 'Say it like you mean it.',
    minDurationMs: 3000,
    category: 'emotional',
  },
];

function formatMs(ms) {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, '0')}`;
}

// ─── Main Component ──────────────────────────────────────────────────────────
export default function AriaVoiceOnboarding({ onComplete }) {
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState(0);
  const [recordingState, setRecordingState] = useState('idle'); // idle | countdown | recording | processing | done | error
  const [countdown, setCountdown] = useState(3);
  const [recordingMs, setRecordingMs] = useState(0);
  const [results, setResults] = useState([]);
  const [enrollmentComplete, setEnrollmentComplete] = useState(false);
  const [overallError, setOverallError] = useState(null);
  const [micPermission, setMicPermission] = useState(null);

  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);
  const streamRef = useRef(null);

  const prompt = VOICE_PROMPTS[currentStep];
  const isLastStep = currentStep === VOICE_PROMPTS.length - 1;

  // ── Request microphone permission on mount ──
  useEffect(() => {
    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        stream.getTracks().forEach(t => t.stop());
        setMicPermission('granted');
      } catch {
        setMicPermission('denied');
      }
    })();
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop());
    };
  }, []);

  // ── Start recording with 3-2-1 countdown ──
  const handleMicPress = useCallback(async () => {
    if (recordingState !== 'idle' && recordingState !== 'error') return;
    if (micPermission !== 'granted') {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        stream.getTracks().forEach(t => t.stop());
        setMicPermission('granted');
      } catch {
        setMicPermission('denied');
        return;
      }
    }

    setRecordingState('countdown');
    setCountdown(3);

    let count = 3;
    const countInterval = setInterval(async () => {
      count--;
      if (count > 0) {
        setCountdown(count);
      } else {
        clearInterval(countInterval);
        startRecording();
      }
    }, 1000);
  }, [recordingState, micPermission]);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 44100,
          channelCount: 1,
          echoCancellation: false,
          noiseSuppression: false,
        },
      });
      streamRef.current = stream;
      chunksRef.current = [];

      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm';

      const recorder = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.start(250); // collect data every 250ms
      setRecordingMs(0);
      setRecordingState('recording');

      timerRef.current = setInterval(() => {
        setRecordingMs(prev => prev + 100);
      }, 100);
    } catch (err) {
      console.error('Failed to start recording', err);
      setRecordingState('error');
      setOverallError('Could not access microphone. Please check your permissions.');
    }
  };

  const handleStopRecording = useCallback(async () => {
    if (recordingState !== 'recording' || !mediaRecorderRef.current) return;

    if (timerRef.current) clearInterval(timerRef.current);

    if (recordingMs < prompt.minDurationMs) {
      mediaRecorderRef.current.stop();
      if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop());
      setOverallError(`Please speak for at least ${prompt.minDurationMs / 1000} seconds.`);
      setRecordingState('idle');
      setRecordingMs(0);
      return;
    }

    setRecordingState('processing');

    mediaRecorderRef.current.onstop = async () => {
      const audioBlob = new Blob(chunksRef.current, { type: 'audio/webm' });
      if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop());

      try {
        const result = await voiceProfileApi.uploadSample({
          promptId: prompt.id,
          audioBlob,
          category: prompt.category,
        });

        setResults(prev => [
          ...prev,
          { promptId: prompt.id, durationMs: recordingMs, uploaded: !!result },
        ]);
        setRecordingState('done');
        setOverallError(null);
      } catch (err) {
        console.error('Upload failed:', err);
        setRecordingState('error');
        setOverallError('Failed to upload recording. Please try again.');
      }
    };

    mediaRecorderRef.current.stop();
  }, [recordingState, recordingMs, prompt]);

  const handleNext = useCallback(async () => {
    if (isLastStep) {
      setRecordingState('processing');
      try {
        await voiceProfileApi.finalizeEnrollment();
        setEnrollmentComplete(true);
        if (onComplete) onComplete();
      } catch (err) {
        setOverallError('Failed to finalize your voice profile. Please try again.');
        setRecordingState('error');
      }
    } else {
      setCurrentStep(prev => prev + 1);
      setRecordingState('idle');
      setRecordingMs(0);
      setOverallError(null);
    }
  }, [isLastStep, onComplete]);

  const handleRetry = () => {
    setRecordingState('idle');
    setRecordingMs(0);
    setOverallError(null);
  };

  // ── Enrollment complete screen ──
  if (enrollmentComplete) {
    return (
      <div className="avo-root">
        <div className="avo-success">
          <div className="avo-success-icon">&#10003;</div>
          <h1 className="avo-success-title">Aria knows your voice</h1>
          <p className="avo-success-sub">
            Your voice profile has been enrolled. Aria will recognize you on every call,
            providing personalized real-time coaching, compliance alerts, and post-call
            summaries tuned to you.
          </p>
          <button className="avo-btn avo-btn--primary" onClick={() => navigate('/dashboard')}>
            Enter Perennia
          </button>
        </div>
      </div>
    );
  }

  // ── Mic permission denied ──
  if (micPermission === 'denied') {
    return (
      <div className="avo-root">
        <div className="avo-success">
          <div className="avo-success-icon" style={{ borderColor: '#F87171' }}>!</div>
          <h1 className="avo-success-title">Microphone Required</h1>
          <p className="avo-success-sub">
            Aria needs microphone access to learn your voice. Please enable it in your
            browser or device settings, then refresh.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="avo-root">
      {/* Progress dots */}
      <div className="avo-progress">
        {VOICE_PROMPTS.map((_, i) => (
          <div
            key={i}
            className={`avo-dot ${i < currentStep ? 'avo-dot--done' : ''} ${i === currentStep ? 'avo-dot--active' : ''}`}
          />
        ))}
      </div>
      <div className="avo-step-label">{currentStep + 1} of {VOICE_PROMPTS.length}</div>

      {/* Aria avatar + message */}
      <div className="avo-aria-block">
        <div className="avo-avatar">
          <div className={`avo-avatar-glow ${recordingState === 'idle' ? 'avo-avatar-glow--active' : ''}`} />
          <div className="avo-avatar-circle">A</div>
        </div>
        <div className="avo-bubble">
          <p className="avo-bubble-text">{prompt.ariaSays}</p>
        </div>
      </div>

      {/* Instruction card */}
      <div className="avo-instruction">
        <p className="avo-instruction-text">{prompt.userInstruction}</p>
        <p className="avo-instruction-hint">{prompt.hint}</p>
      </div>

      {/* Recording control */}
      <div className="avo-recording-area">
        {recordingState === 'countdown' && (
          <div className="avo-countdown">
            <span className="avo-countdown-num">{countdown}</span>
            <span className="avo-countdown-label">Get ready...</span>
          </div>
        )}

        {(recordingState === 'idle' || recordingState === 'error') && (
          <button className="avo-mic-btn" onClick={handleMicPress}>
            <div className="avo-mic-gradient">
              <span className="avo-mic-icon">&#127908;</span>
            </div>
            <span className="avo-mic-label">Tap to speak</span>
          </button>
        )}

        {recordingState === 'recording' && (
          <button className="avo-stop-btn" onClick={handleStopRecording}>
            <div className="avo-stop-gradient">
              <div className="avo-stop-icon" />
            </div>
            <div className="avo-waveform">
              {[0.4, 0.7, 1.0, 0.85, 0.6, 0.9, 0.5, 0.75, 0.95, 0.65, 0.8, 0.45, 0.7, 1.0, 0.55].map((h, i) => (
                <div key={i} className="avo-wave-bar" style={{ height: `${h * 32}px` }} />
              ))}
            </div>
            <span className="avo-duration">{formatMs(recordingMs)}</span>
            <span className="avo-tap-stop">Tap to stop</span>
          </button>
        )}

        {recordingState === 'processing' && (
          <div className="avo-processing">
            <div className="avo-spinner" />
            <span className="avo-processing-text">Processing...</span>
          </div>
        )}

        {recordingState === 'done' && (
          <div className="avo-done">
            <div className="avo-done-check">&#10003;</div>
            <span className="avo-done-text">Recorded - {formatMs(recordingMs)}</span>
            <div className="avo-done-actions">
              <button className="avo-btn avo-btn--ghost" onClick={handleRetry}>
                Re-record
              </button>
              <button className="avo-btn avo-btn--primary" onClick={handleNext}>
                {isLastStep ? 'Finish Setup' : 'Next'}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Completed prompts */}
      {results.length > 0 && (
        <div className="avo-completed">
          <div className="avo-completed-header">Recorded</div>
          {results.map((r, i) => (
            <div key={r.promptId} className="avo-completed-item">
              <span className="avo-completed-dot">&#10003;</span>
              <span className="avo-completed-label">{r.promptId}</span>
              <span className="avo-completed-duration">{formatMs(r.durationMs)}</span>
              {r.uploaded && <span className="avo-uploaded-badge">uploaded</span>}
            </div>
          ))}
        </div>
      )}

      {overallError && (
        <p className="avo-error">{overallError}</p>
      )}
    </div>
  );
}
