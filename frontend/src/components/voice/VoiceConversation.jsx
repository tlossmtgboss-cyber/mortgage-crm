// Voice Conversation - Voice picker + conversation with Aria
import React, { useState, useEffect, useCallback, useRef } from 'react';
import useVoiceWebSocket from './hooks/useVoiceWebSocket';
import useAudioRecorder from './hooks/useAudioRecorder';
import './VoiceConversation.css';
import { toast } from '../../utils/toast';

const VoiceConversation = () => {
  // Section toggle
  const [activeSection, setActiveSection] = useState('picker'); // 'picker' | 'conversation'

  // Voice picker state
  const [voices, setVoices] = useState([]);
  const [loadingVoices, setLoadingVoices] = useState(true);
  const [selectedVoice, setSelectedVoice] = useState(null);
  const [savedVoice, setSavedVoice] = useState(null);
  const [playingVoice, setPlayingVoice] = useState(null);
  const [saving, setSaving] = useState(false);

  // Conversation state
  const [conversationHistory, setConversationHistory] = useState([]);
  const [currentTranscript, setCurrentTranscript] = useState('');
  const [isPushToTalk, setIsPushToTalk] = useState(false);
  const [textInput, setTextInput] = useState('');
  const [sttEnabled, setSttEnabled] = useState(true);

  const conversationEndRef = useRef(null);

  // API base URL
  const API_BASE_URL = (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1')
    ? 'https://api.perenniaai.com'
    : 'http://localhost:8000';

  // Handle transcript updates
  const handleTranscript = useCallback((data) => {
    if (data.role === 'user') {
      setCurrentTranscript(data.text);
      if (data.isFinal && data.text) {
        setConversationHistory(prev => [...prev, { role: 'user', text: data.text }]);
        setCurrentTranscript('');
      }
    } else if (data.role === 'assistant') {
      if (data.isFinal && data.text) {
        setConversationHistory(prev => [...prev, { role: 'assistant', text: data.text }]);
      }
    }
  }, []);

  // Handle status changes
  const handleStatusChange = useCallback((newStatus) => {
    console.log('[VoiceConversation] Status:', newStatus);
  }, []);

  // Handle errors
  const handleError = useCallback((error) => {
    console.error('[VoiceConversation] Error:', error);
  }, []);

  // WebSocket hook
  const {
    status: wsStatus,
    sttEnabled: _wsSttEnabled,
    connect,
    disconnect,
    startListening,
    stopListening,
    sendAudio,
    sendText,
    interrupt,
    isConnected
  } = useVoiceWebSocket({
    onTranscript: handleTranscript,
    onAudio: (data) => {
      playAudio(data.data, data.format);
    },
    onStatusChange: handleStatusChange,
    onError: handleError,
    onSessionInfo: (info) => {
      setSttEnabled(info.sttEnabled);
    }
  });

  // Handle text input submission
  const handleTextSubmit = useCallback((e) => {
    e.preventDefault();
    if (!textInput.trim() || !isConnected) return;

    // Add user message to history
    setConversationHistory(prev => [...prev, { role: 'user', text: textInput.trim() }]);

    // Send via WebSocket
    sendText(textInput.trim());
    setTextInput('');
  }, [textInput, isConnected, sendText]);

  // Audio recorder hook
  const {
    isRecording: _isRecording,
    hasPermission: _hasPermission,
    error: audioError,
    startRecording,
    stopRecording,
    playAudio,
    stopPlayback
  } = useAudioRecorder({
    onAudioChunk: (base64Audio) => {
      if (isConnected && isPushToTalk) {
        sendAudio(base64Audio);
      }
    },
    enabled: activeSection === 'conversation'
  });

  // Load available voices
  useEffect(() => {
    const loadVoices = async () => {
      setLoadingVoices(true);
      try {
        const token = localStorage.getItem('token');
        const response = await fetch(`${API_BASE_URL}/api/v1/mobile-voice/voices`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await response.json();
        setVoices(data.voices || []);
      } catch (error) {
        console.error('Error loading voices:', error);
      } finally {
        setLoadingVoices(false);
      }
    };

    loadVoices();
  }, [API_BASE_URL]);

  // Load user's saved voice preference
  useEffect(() => {
    const loadPreference = async () => {
      try {
        const token = localStorage.getItem('token');
        const response = await fetch(`${API_BASE_URL}/api/v1/mobile-voice/user-voice-preference`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await response.json();
        if (data.has_preference) {
          setSavedVoice({ voice_id: data.voice_id, provider: data.provider });
          setSelectedVoice({ voice_id: data.voice_id, provider: data.provider });
        }
      } catch (error) {
        console.error('Error loading voice preference:', error);
      }
    };

    loadPreference();
  }, [API_BASE_URL]);

  // Auto-scroll conversation to bottom
  useEffect(() => {
    conversationEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [conversationHistory, currentTranscript]);

  // Play voice sample
  const handlePlayVoice = async (voice) => {
    setPlayingVoice(voice.id);

    try {
      const token = localStorage.getItem('token');
      const sampleText = "Hello! I'm Aria, your AI assistant. How can I help you today?";

      const response = await fetch(`${API_BASE_URL}/api/v1/mobile-voice/tts/synthesize`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          text: sampleText,
          voice_id: voice.id,
          provider: voice.provider
        })
      });

      const data = await response.json();

      if (data.audio) {
        const audio = new Audio(`data:audio/mp3;base64,${data.audio}`);
        audio.play();
        audio.onended = () => setPlayingVoice(null);
      } else {
        setPlayingVoice(null);
      }
    } catch (error) {
      console.error('Error playing voice sample:', error);
      setPlayingVoice(null);
    }
  };

  // Save voice preference
  const handleSaveVoice = async () => {
    if (!selectedVoice) return;

    setSaving(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/mobile-voice/user-voice-preference`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          voice_id: selectedVoice.voice_id,
          provider: selectedVoice.provider
        })
      });

      const data = await response.json();

      if (data.success) {
        setSavedVoice(selectedVoice);
        toast.success('Voice preference saved! Aria will now use this voice.');
      } else {
        toast.error('Failed to save voice preference');
      }
    } catch (error) {
      console.error('Error saving voice:', error);
      toast.error('Error saving voice preference');
    } finally {
      setSaving(false);
    }
  };

  // Handle push-to-talk press
  const handlePushToTalkStart = async () => {
    if (!isConnected) {
      await connect();
    }

    setIsPushToTalk(true);
    startListening();
    startRecording();
  };

  // Handle push-to-talk release
  const handlePushToTalkEnd = () => {
    setIsPushToTalk(false);
    stopRecording();
    stopListening();
  };

  // Handle interrupt
  const handleInterrupt = () => {
    interrupt();
    stopPlayback();
  };

  // Start conversation
  const handleStartConversation = async () => {
    setActiveSection('conversation');
    await connect();
  };

  // End conversation
  const handleEndConversation = () => {
    disconnect();
    stopRecording();
    stopPlayback();
    setConversationHistory([]);
    setCurrentTranscript('');
    setActiveSection('picker');
  };

  // Get status display
  const getStatusDisplay = () => {
    switch (wsStatus) {
      case 'idle': return { text: 'Not connected', color: '#6b7280' };
      case 'connecting': return { text: 'Connecting...', color: '#f59e0b' };
      case 'connected': return { text: 'Connected - Hold to speak', color: '#22c55e' };
      case 'listening': return { text: 'Listening...', color: '#22c55e' };
      case 'processing': return { text: 'Processing...', color: '#f59e0b' };
      case 'speaking': return { text: 'Aria is speaking...', color: '#3b82f6' };
      case 'error': return { text: 'Connection error', color: '#ef4444' };
      default: return { text: '', color: '#6b7280' };
    }
  };

  // Group voices by provider
  const voicesByProvider = voices.reduce((acc, voice) => {
    if (!acc[voice.provider]) {
      acc[voice.provider] = [];
    }
    acc[voice.provider].push(voice);
    return acc;
  }, {});

  const providerNames = {
    google: 'Google Cloud TTS',
    elevenlabs: 'ElevenLabs',
    openai: 'OpenAI'
  };

  const statusDisplay = getStatusDisplay();

  return (
    <div className="voice-conversation">
      {/* Section Toggle */}
      <div className="section-toggle">
        <button
          className={`toggle-btn ${activeSection === 'picker' ? 'active' : ''}`}
          onClick={() => setActiveSection('picker')}
        >
          Choose Voice
        </button>
        <button
          className={`toggle-btn ${activeSection === 'conversation' ? 'active' : ''}`}
          onClick={handleStartConversation}
        >
          Talk to Aria
        </button>
      </div>

      {/* Voice Picker Section */}
      {activeSection === 'picker' && (
        <div className="voice-picker-section">
          <div className="picker-header">
            <h2>Select Your Preferred Voice</h2>
            <p>Choose a voice for Aria to use during conversations. Click play to preview.</p>
          </div>

          {loadingVoices ? (
            <div className="loading-state">
              <div className="loading-spinner"></div>
              <p>Loading voices...</p>
            </div>
          ) : (
            <>
              {Object.entries(voicesByProvider).map(([provider, providerVoices]) => (
                <div key={provider} className="provider-section">
                  <h3 className="provider-title">{providerNames[provider] || provider}</h3>
                  <div className="voices-grid">
                    {providerVoices.map((voice) => (
                      <div
                        key={voice.id}
                        className={`voice-card ${
                          selectedVoice?.voice_id === voice.id ? 'selected' : ''
                        } ${playingVoice === voice.id ? 'playing' : ''}`}
                        onClick={() => setSelectedVoice({ voice_id: voice.id, provider: voice.provider })}
                      >
                        <div className="voice-header">
                          <div className="voice-name-section">
                            <h4>{voice.name}</h4>
                            {savedVoice?.voice_id === voice.id && (
                              <span className="current-badge">Current</span>
                            )}
                            {selectedVoice?.voice_id === voice.id && savedVoice?.voice_id !== voice.id && (
                              <span className="selected-badge">Selected</span>
                            )}
                          </div>
                          <button
                            className="play-btn"
                            onClick={(e) => {
                              e.stopPropagation();
                              handlePlayVoice(voice);
                            }}
                            disabled={playingVoice !== null}
                          >
                            {playingVoice === voice.id ? '...' : '\u25B6'}
                          </button>
                        </div>

                        <p className="voice-description">{voice.description}</p>

                        {voice.language && (
                          <div className="voice-language">
                            <span className="language-tag">{voice.language}</span>
                          </div>
                        )}

                        {playingVoice === voice.id && (
                          <div className="playing-indicator">
                            <div className="audio-wave">
                              <span></span>
                              <span></span>
                              <span></span>
                              <span></span>
                            </div>
                            <span className="playing-text">Playing...</span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ))}

              <div className="voice-actions">
                <button
                  className="btn-save"
                  onClick={handleSaveVoice}
                  disabled={
                    !selectedVoice ||
                    (savedVoice?.voice_id === selectedVoice?.voice_id) ||
                    saving
                  }
                >
                  {saving ? 'Saving...' : 'Save Voice Selection'}
                </button>
                {selectedVoice && savedVoice?.voice_id !== selectedVoice?.voice_id && (
                  <p className="change-notice">
                    Click save to update your voice preference.
                  </p>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* Conversation Section */}
      {activeSection === 'conversation' && (
        <div className="conversation-section">
          {/* Status Bar */}
          <div className="status-bar">
            <div className="status-indicator" style={{ backgroundColor: statusDisplay.color }}>
              <span className="status-dot"></span>
              <span className="status-text">{statusDisplay.text}</span>
            </div>
            {savedVoice && (
              <div className="selected-voice-badge">
                Voice: {voices.find(v => v.id === savedVoice.voice_id)?.name || 'Default'}
              </div>
            )}
          </div>

          {/* Error Display */}
          {audioError && (
            <div className="error-message">
              {audioError}
            </div>
          )}

          {/* Conversation History */}
          <div className="conversation-history">
            {conversationHistory.length === 0 && !currentTranscript && (
              <div className="empty-state">
                <p>Press and hold the microphone button to start talking to Aria.</p>
              </div>
            )}

            {conversationHistory.map((msg, idx) => (
              <div key={idx} className={`message ${msg.role}`}>
                <span className="role">{msg.role === 'user' ? 'You' : 'Aria'}:</span>
                <span className="text">{msg.text}</span>
              </div>
            ))}

            {currentTranscript && (
              <div className="message user current">
                <span className="role">You:</span>
                <span className="text">{currentTranscript}</span>
              </div>
            )}

            <div ref={conversationEndRef} />
          </div>

          {/* Controls */}
          <div className="conversation-controls">
            {isConnected ? (
              <>
                {/* Text Input - always available as fallback */}
                <form className="text-input-form" onSubmit={handleTextSubmit}>
                  <input
                    type="text"
                    value={textInput}
                    onChange={(e) => setTextInput(e.target.value)}
                    placeholder={sttEnabled ? "Or type your message..." : "Type your message to Aria..."}
                    disabled={wsStatus === 'speaking'}
                    className="text-input"
                  />
                  <button
                    type="submit"
                    disabled={!textInput.trim() || wsStatus === 'speaking'}
                    className="btn-send"
                  >
                    Send
                  </button>
                </form>

                <div className="voice-controls">
                  {sttEnabled && (
                    <button
                      className={`btn-mic ${isPushToTalk ? 'active' : ''}`}
                      onMouseDown={handlePushToTalkStart}
                      onMouseUp={handlePushToTalkEnd}
                      onMouseLeave={handlePushToTalkEnd}
                      onTouchStart={handlePushToTalkStart}
                      onTouchEnd={handlePushToTalkEnd}
                      disabled={wsStatus === 'speaking'}
                    >
                      <span className="mic-icon">{isPushToTalk ? '🎤' : '🎙'}</span>
                      <span className="mic-label">
                        {isPushToTalk ? 'Listening...' : 'Hold to Talk'}
                      </span>
                    </button>
                  )}

                  {!sttEnabled && (
                    <div className="stt-disabled-notice">
                      Voice input not available. Please type your message above.
                    </div>
                  )}

                  {wsStatus === 'speaking' && (
                    <button className="btn-interrupt" onClick={handleInterrupt}>
                      Stop
                    </button>
                  )}

                  <button className="btn-end" onClick={handleEndConversation}>
                    End Call
                  </button>
                </div>
              </>
            ) : (
              <button className="btn-start" onClick={connect}>
                Start Conversation
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default VoiceConversation;
