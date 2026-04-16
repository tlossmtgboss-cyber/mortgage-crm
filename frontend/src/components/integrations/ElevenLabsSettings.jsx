/**
 * ElevenLabs Integration Settings Component
 *
 * Allows users to:
 * - Connect/disconnect their ElevenLabs account with API key
 * - View connection status and available voices
 * - Select voice for AI Receptionist
 * - Test voice synthesis
 * - Configure voice settings
 */

import React, { useState, useEffect } from 'react';
import { API_BASE_URL } from '../../services/api';
import './ElevenLabsSettings.css';
import { getToken } from '../../utils/tokenStore';

const API_URL = API_BASE_URL;

const ElevenLabsSettings = () => {
  // Connection state
  const [connectionStatus, setConnectionStatus] = useState(null);
  const [apiKey, setApiKey] = useState('');
  const [connecting, setConnecting] = useState(false);

  // Voice state
  const [voices, setVoices] = useState([]);
  const [selectedVoice, setSelectedVoice] = useState('');
  const [loadingVoices, setLoadingVoices] = useState(false);

  // Settings state
  const [settings, setSettings] = useState({
    stability: 0.5,
    similarity_boost: 0.75,
    style: 0,
    use_speaker_boost: true,
  });

  // Test state
  const [testText, setTestText] = useState('Hello! This is a test of the ElevenLabs voice synthesis.');
  const [testing, setTesting] = useState(false);
  const [audioUrl, setAudioUrl] = useState(null);

  // UI state
  const [activeTab, setActiveTab] = useState('connection');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Load connection status on mount
  useEffect(() => {
    loadConnectionStatus();
  }, []);

  const getAuthHeaders = () => {
    const token = getToken();
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    };
  };

  const loadConnectionStatus = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/elevenlabs/status`, {
        headers: getAuthHeaders()
      });

      if (res.ok) {
        const data = await res.json();
        setConnectionStatus(data.data || data);

        if (data.data?.connected || data.connected) {
          loadVoices();
          if (data.data?.selected_voice_id || data.selected_voice_id) {
            setSelectedVoice(data.data?.selected_voice_id || data.selected_voice_id);
          }
          if (data.data?.settings || data.settings) {
            setSettings(prev => ({ ...prev, ...(data.data?.settings || data.settings) }));
          }
        }
      } else {
        setConnectionStatus({ connected: false });
      }
    } catch (err) {
      console.error('Failed to load ElevenLabs status:', err);
      setConnectionStatus({ connected: false });
    } finally {
      setLoading(false);
    }
  };

  const loadVoices = async () => {
    setLoadingVoices(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/elevenlabs/voices`, {
        headers: getAuthHeaders()
      });

      if (res.ok) {
        const data = await res.json();
        setVoices(data.data?.voices || data.voices || []);
      }
    } catch (err) {
      console.error('Failed to load voices:', err);
    } finally {
      setLoadingVoices(false);
    }
  };

  const handleConnect = async () => {
    if (!apiKey.trim()) {
      setError('Please enter your ElevenLabs API key');
      return;
    }

    setConnecting(true);
    setError(null);
    setSuccess(null);

    try {
      const res = await fetch(`${API_URL}/api/v1/elevenlabs/connect`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ api_key: apiKey.trim() })
      });

      const data = await res.json();

      if (res.ok) {
        setConnectionStatus({
          connected: true,
          subscription_tier: data.data?.subscription_tier || data.subscription_tier,
          character_limit: data.data?.character_limit || data.character_limit,
          character_count: data.data?.character_count || data.character_count,
        });
        setApiKey('');
        setSuccess('ElevenLabs connected successfully!');
        loadVoices();
      } else {
        setError(data.detail || data.error || 'Failed to connect ElevenLabs');
      }
    } catch (err) {
      setError(err.message || 'Failed to connect ElevenLabs');
    } finally {
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    if (!window.confirm('Are you sure you want to disconnect ElevenLabs? The AI Receptionist will use default voices.')) {
      return;
    }

    try {
      const res = await fetch(`${API_URL}/api/v1/elevenlabs/disconnect`, {
        method: 'POST',
        headers: getAuthHeaders()
      });

      if (res.ok) {
        setConnectionStatus({ connected: false });
        setVoices([]);
        setSelectedVoice('');
        setSuccess('ElevenLabs disconnected');
      } else {
        const data = await res.json();
        setError(data.detail || 'Failed to disconnect');
      }
    } catch (err) {
      setError('Failed to disconnect ElevenLabs');
    }
  };

  const handleSaveVoice = async () => {
    if (!selectedVoice) {
      setError('Please select a voice');
      return;
    }

    setError(null);
    setSuccess(null);

    try {
      const res = await fetch(`${API_URL}/api/v1/elevenlabs/settings`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          voice_id: selectedVoice,
          settings: settings
        })
      });

      if (res.ok) {
        setSuccess('Voice settings saved successfully!');
      } else {
        const data = await res.json();
        setError(data.detail || 'Failed to save settings');
      }
    } catch (err) {
      setError('Failed to save voice settings');
    }
  };

  const handleTestVoice = async () => {
    if (!selectedVoice || !testText.trim()) {
      setError('Please select a voice and enter test text');
      return;
    }

    setTesting(true);
    setError(null);
    setAudioUrl(null);

    try {
      const res = await fetch(`${API_URL}/api/v1/elevenlabs/test`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          voice_id: selectedVoice,
          text: testText,
          settings: settings
        })
      });

      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        setAudioUrl(url);
      } else {
        const data = await res.json();
        setError(data.detail || 'Failed to generate audio');
      }
    } catch (err) {
      setError('Failed to test voice');
    } finally {
      setTesting(false);
    }
  };

  const formatNumber = (num) => {
    if (!num) return '0';
    return new Intl.NumberFormat().format(num);
  };

  if (loading) {
    return (
      <div className="elevenlabs-settings">
        <div className="loading-state">Loading ElevenLabs settings...</div>
      </div>
    );
  }

  return (
    <div className="elevenlabs-settings">
      <div className="settings-header">
        <div className="header-icon">
          <img
            src="https://www.google.com/s2/favicons?domain=elevenlabs.io&sz=128"
            alt="ElevenLabs"
            onError={(e) => { e.target.style.display = 'none'; }}
          />
        </div>
        <div className="header-info">
          <h3>ElevenLabs Voice AI</h3>
          <p>Ultra-realistic AI voices for your AI Receptionist</p>
        </div>
        <div className={`status-badge ${connectionStatus?.connected ? 'connected' : 'disconnected'}`}>
          {connectionStatus?.connected ? 'Connected' : 'Not Connected'}
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {success && <div className="alert alert-success">{success}</div>}

      <div className="settings-tabs">
        <button
          className={`tab ${activeTab === 'connection' ? 'active' : ''}`}
          onClick={() => setActiveTab('connection')}
        >
          Connection
        </button>
        {connectionStatus?.connected && (
          <>
            <button
              className={`tab ${activeTab === 'voices' ? 'active' : ''}`}
              onClick={() => setActiveTab('voices')}
            >
              Voices
            </button>
            <button
              className={`tab ${activeTab === 'settings' ? 'active' : ''}`}
              onClick={() => setActiveTab('settings')}
            >
              Settings
            </button>
          </>
        )}
      </div>

      <div className="settings-content">
        {activeTab === 'connection' && (
          <div className="connection-tab">
            {!connectionStatus?.connected ? (
              <div className="connect-form">
                <p className="help-text">
                  Enter your ElevenLabs API key to enable ultra-realistic voice synthesis for your AI Receptionist.
                  Get your API key from <a href="https://elevenlabs.io/app/settings/api-keys" target="_blank" rel="noopener noreferrer">ElevenLabs Dashboard</a>.
                </p>
                <div className="form-group">
                  <label>API Key</label>
                  <input
                    type="password"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder="Enter your ElevenLabs API key"
                    disabled={connecting}
                  />
                </div>
                <button
                  className="btn-primary"
                  onClick={handleConnect}
                  disabled={connecting || !apiKey.trim()}
                >
                  {connecting ? 'Connecting...' : 'Connect ElevenLabs'}
                </button>
              </div>
            ) : (
              <div className="connection-info">
                <div className="info-grid">
                  <div className="info-item">
                    <span className="label">Status</span>
                    <span className="value connected">Connected</span>
                  </div>
                  <div className="info-item">
                    <span className="label">Subscription</span>
                    <span className="value">{connectionStatus.subscription_tier || 'Free'}</span>
                  </div>
                  <div className="info-item">
                    <span className="label">Characters Used</span>
                    <span className="value">
                      {formatNumber(connectionStatus.character_count)} / {formatNumber(connectionStatus.character_limit)}
                    </span>
                  </div>
                  {connectionStatus.character_limit && (
                    <div className="info-item full-width">
                      <span className="label">Usage</span>
                      <div className="usage-bar">
                        <div
                          className="usage-fill"
                          style={{
                            width: `${Math.min(100, (connectionStatus.character_count / connectionStatus.character_limit) * 100)}%`
                          }}
                        />
                      </div>
                    </div>
                  )}
                </div>
                <button
                  className="btn-danger"
                  onClick={handleDisconnect}
                >
                  Disconnect ElevenLabs
                </button>
              </div>
            )}
          </div>
        )}

        {activeTab === 'voices' && connectionStatus?.connected && (
          <div className="voices-tab">
            <div className="form-group">
              <label>Select Voice for AI Receptionist</label>
              {loadingVoices ? (
                <p>Loading voices...</p>
              ) : (
                <select
                  value={selectedVoice}
                  onChange={(e) => setSelectedVoice(e.target.value)}
                >
                  <option value="">Select a voice...</option>
                  {voices.map(voice => (
                    <option key={voice.voice_id} value={voice.voice_id}>
                      {voice.name} {voice.category && `(${voice.category})`}
                    </option>
                  ))}
                </select>
              )}
            </div>

            {selectedVoice && (
              <div className="voice-preview">
                <h4>Test Voice</h4>
                <div className="form-group">
                  <label>Test Text</label>
                  <textarea
                    value={testText}
                    onChange={(e) => setTestText(e.target.value)}
                    rows={3}
                    placeholder="Enter text to test the voice..."
                  />
                </div>
                <button
                  className="btn-secondary"
                  onClick={handleTestVoice}
                  disabled={testing}
                >
                  {testing ? 'Generating...' : 'Test Voice'}
                </button>
                {audioUrl && (
                  <div className="audio-player">
                    <audio controls src={audioUrl}>
                      Your browser does not support audio playback.
                    </audio>
                  </div>
                )}
              </div>
            )}

            <div className="actions">
              <button
                className="btn-primary"
                onClick={handleSaveVoice}
                disabled={!selectedVoice}
              >
                Save Voice Selection
              </button>
            </div>
          </div>
        )}

        {activeTab === 'settings' && connectionStatus?.connected && (
          <div className="settings-tab">
            <div className="form-group">
              <label>Stability ({settings.stability})</label>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={settings.stability}
                onChange={(e) => setSettings(prev => ({ ...prev, stability: parseFloat(e.target.value) }))}
              />
              <p className="help-text">Higher stability makes the voice more consistent but less expressive.</p>
            </div>

            <div className="form-group">
              <label>Similarity Boost ({settings.similarity_boost})</label>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={settings.similarity_boost}
                onChange={(e) => setSettings(prev => ({ ...prev, similarity_boost: parseFloat(e.target.value) }))}
              />
              <p className="help-text">Higher values make the voice sound more like the original speaker.</p>
            </div>

            <div className="form-group">
              <label>Style ({settings.style})</label>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={settings.style}
                onChange={(e) => setSettings(prev => ({ ...prev, style: parseFloat(e.target.value) }))}
              />
              <p className="help-text">Higher values amplify the style of the original speaker.</p>
            </div>

            <div className="form-group checkbox">
              <label>
                <input
                  type="checkbox"
                  checked={settings.use_speaker_boost}
                  onChange={(e) => setSettings(prev => ({ ...prev, use_speaker_boost: e.target.checked }))}
                />
                Use Speaker Boost
              </label>
              <p className="help-text">Enhances voice clarity and reduces latency.</p>
            </div>

            <div className="actions">
              <button
                className="btn-primary"
                onClick={handleSaveVoice}
              >
                Save Settings
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ElevenLabsSettings;
