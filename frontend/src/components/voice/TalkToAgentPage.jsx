// Talk to Agent Page - Standalone page for browser-based voice conversations
import React, { useState, useEffect, useCallback } from 'react';
import TalkToAgent from './TalkToAgent';
import './TalkToAgentPage.css';
import { getToken } from '../../utils/tokenStore';

const TalkToAgentPage = () => {
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [isConversationOpen, setIsConversationOpen] = useState(false);

  // API base URL
  const API_BASE_URL = typeof window !== 'undefined' &&
    (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1')
    ? 'https://api.perenniaai.com'
    : 'http://localhost:8000';

  // Fetch available agents
  const fetchAgents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/voice/agents`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error('Failed to fetch agents');
      }

      const data = await response.json();
      // Filter to only show active agents
      const activeAgents = (data.agents || data || []).filter(a => a.status === 'active');
      setAgents(activeAgents);
    } catch (err) {
      console.error('Error fetching agents:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [API_BASE_URL]);

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  // Start conversation with agent
  const handleStartConversation = (agent) => {
    setSelectedAgent(agent);
    setIsConversationOpen(true);
  };

  // Close conversation
  const handleCloseConversation = () => {
    setIsConversationOpen(false);
    setSelectedAgent(null);
  };

  // Quick start with default/first agent
  const handleQuickStart = () => {
    const defaultAgent = agents.find(a => a.is_default) || agents[0];
    if (defaultAgent) {
      handleStartConversation(defaultAgent);
    }
  };

  // Get voice emoji
  const getVoiceEmoji = (voice) => {
    const voiceEmojis = {
      'alloy': '🎭',
      'echo': '🔊',
      'fable': '📖',
      'onyx': '🖤',
      'nova': '⭐',
      'shimmer': '✨'
    };
    return voiceEmojis[voice?.toLowerCase()] || '🎙️';
  };

  // Get language flag
  const getLanguageFlag = (language) => {
    const flags = {
      'en': '🇺🇸',
      'en-US': '🇺🇸',
      'en-GB': '🇬🇧',
      'es': '🇪🇸',
      'es-MX': '🇲🇽',
      'fr': '🇫🇷',
      'de': '🇩🇪',
      'it': '🇮🇹',
      'pt': '🇵🇹',
      'zh': '🇨🇳',
      'ja': '🇯🇵',
      'ko': '🇰🇷'
    };
    return flags[language] || '🌐';
  };

  if (loading) {
    return (
      <div className="tta-page">
        <div className="tta-loading">
          <div className="tta-spinner"></div>
          <p>Loading agents...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="tta-page">
      {/* Hero Section */}
      <div className="tta-hero">
        <div className="tta-hero-content">
          <div className="tta-hero-icon">🎙️</div>
          <h1>Talk to an AI Agent</h1>
          <p>Have a real-time voice conversation with our AI-powered mortgage assistants. Get instant answers about rates, loan options, and the application process.</p>

          <div className="tta-hero-actions">
            <button
              className="tta-btn tta-btn-primary tta-btn-large"
              onClick={handleQuickStart}
              disabled={agents.length === 0}
            >
              <span className="tta-btn-icon">📞</span>
              Start Conversation
            </button>
          </div>

          <div className="tta-hero-features">
            <div className="tta-feature">
              <span className="tta-feature-icon">⚡</span>
              <span>Instant Responses</span>
            </div>
            <div className="tta-feature">
              <span className="tta-feature-icon">🔒</span>
              <span>Secure & Private</span>
            </div>
            <div className="tta-feature">
              <span className="tta-feature-icon">🕐</span>
              <span>Available 24/7</span>
            </div>
          </div>
        </div>

        <div className="tta-hero-visual">
          <div className="tta-orb-container">
            <div className="tta-orb tta-orb-1"></div>
            <div className="tta-orb tta-orb-2"></div>
            <div className="tta-orb tta-orb-3"></div>
            <div className="tta-center-icon">🤖</div>
          </div>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="tta-error-banner">
          <span>⚠️ {error}</span>
          <button onClick={fetchAgents}>Retry</button>
        </div>
      )}

      {/* Agents Section */}
      <div className="tta-section">
        <div className="tta-section-header">
          <h2>Available Agents</h2>
          <p>Choose an agent to start your conversation</p>
        </div>

        {agents.length === 0 ? (
          <div className="tta-empty">
            <span className="tta-empty-icon">🤖</span>
            <h3>No Agents Available</h3>
            <p>There are no active agents at the moment. Please check back later.</p>
          </div>
        ) : (
          <div className="tta-agents-grid">
            {agents.map(agent => (
              <div
                key={agent.id}
                className={`tta-agent-card ${agent.is_default ? 'default' : ''}`}
              >
                <div className="tta-agent-header">
                  <div className="tta-agent-avatar">
                    {agent.name?.charAt(0) || '🤖'}
                  </div>
                  <div className="tta-agent-badges">
                    {agent.is_default && (
                      <span className="tta-badge tta-badge-default">Default</span>
                    )}
                  </div>
                </div>

                <div className="tta-agent-body">
                  <h3>{agent.name || 'AI Agent'}</h3>
                  <p className="tta-agent-desc">
                    {agent.system_prompt?.substring(0, 120) ||
                     'AI-powered assistant ready to help with your mortgage questions.'}
                    {agent.system_prompt?.length > 120 ? '...' : ''}
                  </p>

                  <div className="tta-agent-meta">
                    <div className="tta-meta-item">
                      <span className="tta-meta-icon">{getVoiceEmoji(agent.voice)}</span>
                      <span>{agent.voice || 'alloy'}</span>
                    </div>
                    <div className="tta-meta-item">
                      <span className="tta-meta-icon">{getLanguageFlag(agent.language)}</span>
                      <span>{agent.language || 'English'}</span>
                    </div>
                  </div>
                </div>

                <div className="tta-agent-footer">
                  <button
                    className="tta-btn tta-btn-talk"
                    onClick={() => handleStartConversation(agent)}
                  >
                    <span className="tta-btn-icon">🎙️</span>
                    Talk Now
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* How It Works Section */}
      <div className="tta-section tta-how-it-works">
        <div className="tta-section-header">
          <h2>How It Works</h2>
          <p>Get started in three simple steps</p>
        </div>

        <div className="tta-steps">
          <div className="tta-step">
            <div className="tta-step-number">1</div>
            <h4>Click Start</h4>
            <p>Select an agent and click "Talk Now" to begin</p>
          </div>
          <div className="tta-step-arrow">→</div>
          <div className="tta-step">
            <div className="tta-step-number">2</div>
            <h4>Allow Microphone</h4>
            <p>Grant microphone access when prompted by your browser</p>
          </div>
          <div className="tta-step-arrow">→</div>
          <div className="tta-step">
            <div className="tta-step-number">3</div>
            <h4>Start Talking</h4>
            <p>Speak naturally and get real-time responses</p>
          </div>
        </div>
      </div>

      {/* Tips Section */}
      <div className="tta-section tta-tips">
        <div className="tta-section-header">
          <h2>Tips for Best Experience</h2>
        </div>

        <div className="tta-tips-grid">
          <div className="tta-tip">
            <span className="tta-tip-icon">🎧</span>
            <h4>Use Headphones</h4>
            <p>For the best audio quality and to prevent echo</p>
          </div>
          <div className="tta-tip">
            <span className="tta-tip-icon">🔇</span>
            <h4>Quiet Environment</h4>
            <p>Find a quiet space for clearer communication</p>
          </div>
          <div className="tta-tip">
            <span className="tta-tip-icon">🗣️</span>
            <h4>Speak Clearly</h4>
            <p>Speak at a normal pace for accurate transcription</p>
          </div>
          <div className="tta-tip">
            <span className="tta-tip-icon">⏸️</span>
            <h4>Pause Between</h4>
            <p>Wait for the agent to finish before responding</p>
          </div>
        </div>
      </div>

      {/* FAQ Section */}
      <div className="tta-section tta-faq">
        <div className="tta-section-header">
          <h2>Frequently Asked Questions</h2>
        </div>

        <div className="tta-faq-list">
          <div className="tta-faq-item">
            <h4>Is my conversation private?</h4>
            <p>Yes, all conversations are encrypted and private. We do not store audio recordings.</p>
          </div>
          <div className="tta-faq-item">
            <h4>What can I ask the agent?</h4>
            <p>You can ask about mortgage rates, loan types, application requirements, and general mortgage questions.</p>
          </div>
          <div className="tta-faq-item">
            <h4>What browsers are supported?</h4>
            <p>We support Chrome, Firefox, Safari, and Edge. Make sure your browser has microphone permissions enabled.</p>
          </div>
          <div className="tta-faq-item">
            <h4>Can I interrupt the agent?</h4>
            <p>Yes, you can click the "Interrupt" button while the agent is speaking to ask a new question.</p>
          </div>
        </div>
      </div>

      {/* Talk to Agent Modal */}
      <TalkToAgent
        agent={selectedAgent}
        isOpen={isConversationOpen}
        onClose={handleCloseConversation}
      />
    </div>
  );
};

export default TalkToAgentPage;
