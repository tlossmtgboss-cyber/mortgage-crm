import { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { usePermissions } from '../contexts/PermissionContext';
import { agentAPI, agentGymAPI, agentChatAPI } from '../services/api';
import './AgentGym.css';

// Difficulty levels
const DIFFICULTY_LEVELS = [
  { value: 'beginner', label: 'Beginner', color: '#10b981', description: 'Basic scenarios for new agents' },
  { value: 'intermediate', label: 'Intermediate', color: '#f59e0b', description: 'Moderate complexity tasks' },
  { value: 'advanced', label: 'Advanced', color: '#ef4444', description: 'Complex multi-step scenarios' },
  { value: 'expert', label: 'Expert', color: '#7c3aed', description: 'Challenging real-world simulations' },
];

// Agent category mapping for auto-selection
const AGENT_CATEGORY_MAP = {
  pipeline_analysis: ['pipeline_analyst', 'team_coach'],
  compliance: ['compliance_checker', 'regulatory_advisor'],
  lead_management: ['lead_nurturer', 'sales_coach'],
  document_management: ['document_tracker', 'processor'],
  advisory: ['mortgage_advisor', 'client_success'],
  scheduling: ['scheduler', 'coordinator'],
  underwriting: ['underwriter', 'risk_analyst'],
  communication: ['communication_specialist', 'client_success'],
};

function AgentGym() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const preselectedAgentId = searchParams.get('agent');
  const chatEndRef = useRef(null);
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();

  // Permission check - only admins can access Agent Gym
  const canAccessAgentGym = isAdmin || hasAnyPermission(['admin.manage', 'agents.manage', 'system.admin']) ||
    userRole === 'admin' || userRole === 'site_admin';

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [agents, setAgents] = useState([]);
  const [scenarios, setScenarios] = useState([]);
  const [leaderboard, setLeaderboard] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [activeTab, setActiveTab] = useState('scenarios');
  const [selectedAgent, setSelectedAgent] = useState(preselectedAgentId || '');
  const [selectedScenario, setSelectedScenario] = useState(null);
  const [runningSession, setRunningSession] = useState(null);
  const [sessionResult, setSessionResult] = useState(null);
  const [difficultyFilter, setDifficultyFilter] = useState('all');
  const [categoryFilter, setCategoryFilter] = useState('all');

  // New state for create scenario modal
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newScenario, setNewScenario] = useState({
    name: '',
    description: '',
    category: 'pipeline_analysis',
    difficulty: 'intermediate',
    test_prompt: '',
    success_criteria: [''],
    expected_tools: [''],
  });
  const [creatingScenario, setCreatingScenario] = useState(false);

  // Conversation state
  const [showConversation, setShowConversation] = useState(false);
  const [conversationMessages, setConversationMessages] = useState([]);
  const [userMessage, setUserMessage] = useState('');
  const [sendingMessage, setSendingMessage] = useState(false);
  const [autoSelectAgent, setAutoSelectAgent] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setError(null);
        const [agentsData, scenariosData, leaderboardData, sessionsData] = await Promise.all([
          agentAPI.getProfiles({ status: 'active' }),
          agentGymAPI.getScenarios(),
          agentGymAPI.getLeaderboard(),
          agentGymAPI.getSessions({ limit: 20 })
        ]);

        setAgents(agentsData.profiles || agentsData || []);
        setScenarios(scenariosData.scenarios || scenariosData || []);
        setLeaderboard(leaderboardData.leaderboard || leaderboardData || []);
        setSessions(sessionsData.sessions || sessionsData || []);
        setLoading(false);
      } catch (error) {
        console.error('Error fetching gym data:', error);
        setError('Failed to load training data. Please check your connection and try again.');
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'N/A';
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  const getDifficultyClass = (difficulty) => {
    switch (difficulty) {
      case 'beginner': return 'difficulty-badge beginner';
      case 'easy': return 'difficulty-badge beginner';
      case 'intermediate': return 'difficulty-badge intermediate';
      case 'medium': return 'difficulty-badge intermediate';
      case 'advanced': return 'difficulty-badge advanced';
      case 'hard': return 'difficulty-badge advanced';
      case 'expert': return 'difficulty-badge expert';
      default: return 'difficulty-badge intermediate';
    }
  };

  const getScoreClass = (score) => {
    if (score >= 90) return 'excellent';
    if (score >= 75) return 'good';
    if (score >= 60) return 'average';
    return 'poor';
  };

  const getCategoryIcon = (category) => {
    const icons = {
      pipeline_analysis: 'fas fa-chart-line',
      compliance: 'fas fa-shield-alt',
      lead_management: 'fas fa-user-plus',
      document_management: 'fas fa-file-alt',
      advisory: 'fas fa-lightbulb',
      scheduling: 'fas fa-calendar-alt'
    };
    return icons[category] || 'fas fa-flask';
  };

  // Filter scenarios
  const filteredScenarios = scenarios.filter(scenario => {
    const matchesDifficulty = difficultyFilter === 'all' || scenario.difficulty === difficultyFilter;
    const matchesCategory = categoryFilter === 'all' || scenario.category === categoryFilter;
    const matchesAgent = !selectedAgent || scenario.agent_types?.includes(
      agents.find(a => a.id === parseInt(selectedAgent))?.agent_name
    );
    return matchesDifficulty && matchesCategory && matchesAgent;
  });

  // Get unique categories
  const categories = [...new Set(scenarios.map(s => s.category))];

  // Auto-select best agent for scenario
  const selectBestAgent = (scenario) => {
    if (!scenario || !autoSelectAgent) return;

    const categoryAgentTypes = AGENT_CATEGORY_MAP[scenario.category] || [];

    // Find an agent that matches the category
    const matchingAgent = agents.find(agent => {
      const agentType = agent.agent_name?.toLowerCase() || '';
      return categoryAgentTypes.some(type => agentType.includes(type.toLowerCase()));
    });

    if (matchingAgent) {
      setSelectedAgent(matchingAgent.id.toString());
    } else if (agents.length > 0) {
      // Fallback to first available agent
      setSelectedAgent(agents[0].id.toString());
    }
  };

  // Handle scenario selection with auto-agent selection
  const handleScenarioSelect = (scenario) => {
    setSelectedScenario(scenario);
    setShowConversation(false);
    setConversationMessages([]);
    if (autoSelectAgent) {
      selectBestAgent(scenario);
    }
  };

  // Create new scenario
  const handleCreateScenario = async () => {
    if (!newScenario.name || !newScenario.test_prompt) return;

    setCreatingScenario(true);
    try {
      const scenarioData = {
        ...newScenario,
        success_criteria: newScenario.success_criteria.filter(c => c.trim()),
        expected_tools: newScenario.expected_tools.filter(t => t.trim()),
        pass_rate: 0,
        avg_completion_time: 0,
      };

      // Call API to create scenario (or add locally for demo)
      const result = await agentGymAPI.createScenario(scenarioData);

      if (result) {
        setScenarios(prev => [...prev, { ...scenarioData, id: result.id || Date.now() }]);
        setShowCreateModal(false);
        setNewScenario({
          name: '',
          description: '',
          category: 'pipeline_analysis',
          difficulty: 'intermediate',
          test_prompt: '',
          success_criteria: [''],
          expected_tools: [''],
        });
      }
    } catch (error) {
      console.error('Error creating scenario:', error);
      // Add locally even if API fails (for demo purposes)
      setScenarios(prev => [...prev, { ...newScenario, id: Date.now(), pass_rate: 0, avg_completion_time: 0 }]);
      setShowCreateModal(false);
    } finally {
      setCreatingScenario(false);
    }
  };

  // Send message to agent
  const sendMessageToAgent = async () => {
    if (!userMessage.trim() || !selectedAgent) return;

    const newUserMessage = {
      role: 'user',
      content: userMessage,
      timestamp: new Date().toISOString(),
    };

    setConversationMessages(prev => [...prev, newUserMessage]);
    setUserMessage('');
    setSendingMessage(true);

    try {
      // Use the agent chat API to get a response
      const context = selectedScenario
        ? { scenario: selectedScenario.name, description: selectedScenario.description, test_prompt: selectedScenario.test_prompt }
        : null;

      const response = await agentChatAPI.quickAction(
        parseInt(selectedAgent),
        userMessage,
        context
      );

      const agentMessage = {
        role: 'assistant',
        content: response.response || response.message || 'I understand. Let me help you with that.',
        timestamp: new Date().toISOString(),
        agent: response.agent_name || agents.find(a => a.id === parseInt(selectedAgent))?.display_name || 'Agent',
      };

      setConversationMessages(prev => [...prev, agentMessage]);
    } catch (error) {
      console.error('Error sending message:', error);
      const errorMessage = {
        role: 'assistant',
        content: 'I apologize, but I encountered an error processing your request. Please try again.',
        timestamp: new Date().toISOString(),
        error: true,
      };
      setConversationMessages(prev => [...prev, errorMessage]);
    } finally {
      setSendingMessage(false);
    }
  };

  // Scroll to bottom of chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [conversationMessages]);

  // Add/remove criteria and tools
  const addCriterion = () => setNewScenario(prev => ({ ...prev, success_criteria: [...prev.success_criteria, ''] }));
  const removeCriterion = (index) => setNewScenario(prev => ({ ...prev, success_criteria: prev.success_criteria.filter((_, i) => i !== index) }));
  const updateCriterion = (index, value) => setNewScenario(prev => ({ ...prev, success_criteria: prev.success_criteria.map((c, i) => i === index ? value : c) }));

  const addTool = () => setNewScenario(prev => ({ ...prev, expected_tools: [...prev.expected_tools, ''] }));
  const removeTool = (index) => setNewScenario(prev => ({ ...prev, expected_tools: prev.expected_tools.filter((_, i) => i !== index) }));
  const updateTool = (index, value) => setNewScenario(prev => ({ ...prev, expected_tools: prev.expected_tools.map((t, i) => i === index ? value : t) }));

  const startTrainingSession = async () => {
    if (!selectedAgent || !selectedScenario) return;

    setRunningSession({
      status: 'running',
      scenario: selectedScenario,
      agent: agents.find(a => a.id === parseInt(selectedAgent)),
      startedAt: new Date().toISOString()
    });
    setSessionResult(null);

    try {
      const result = await agentGymAPI.startSession({
        agent_id: parseInt(selectedAgent),
        scenario_id: selectedScenario.id
      });

      // Set the result from the API response
      setSessionResult(result);
      setRunningSession(prev => ({ ...prev, status: 'completed' }));
    } catch (error) {
      console.error('Error starting session:', error);
      setSessionResult({
        error: true,
        message: 'Failed to complete training session. Please try again.'
      });
      setRunningSession(prev => ({ ...prev, status: 'failed' }));
    }
  };

  if (loading) {
    return (
      <div className="agent-gym loading">
        <div className="loading-spinner">
          <i className="fas fa-spinner fa-spin"></i>
          <p>Loading Agent Gym...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="agent-gym">
        <div className="gym-header">
          <div className="header-left">
            <button className="back-btn" onClick={() => navigate('/agents')}>
              <i className="fas fa-arrow-left"></i> Back to Agents
            </button>
            <h1><i className="fas fa-dumbbell"></i> Agent Training Gym</h1>
          </div>
        </div>
        <div className="error-state">
          <i className="fas fa-exclamation-triangle"></i>
          <h3>Unable to Load Data</h3>
          <p>{error}</p>
          <button className="retry-btn" onClick={() => window.location.reload()}>
            <i className="fas fa-redo"></i> Retry
          </button>
        </div>
      </div>
    );
  }

  // Access denied if user doesn't have agent management permissions
  if (!canAccessAgentGym) {
    return (
      <div className="agent-gym">
        <div style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access Agent Gym.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')} style={{ marginTop: '16px' }}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="agent-gym">
      {/* Header */}
      <div className="gym-header">
        <div className="header-left">
          <button className="back-btn" onClick={() => navigate('/agents')}>
            <i className="fas fa-arrow-left"></i> Back to Agents
          </button>
          <h1><i className="fas fa-dumbbell"></i> Agent Training Gym</h1>
          <p className="subtitle">Train, test, and improve your AI agents</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="gym-tabs">
        <button
          className={`tab ${activeTab === 'scenarios' ? 'active' : ''}`}
          onClick={() => setActiveTab('scenarios')}
        >
          <i className="fas fa-flask"></i> Training Scenarios
        </button>
        <button
          className={`tab ${activeTab === 'leaderboard' ? 'active' : ''}`}
          onClick={() => setActiveTab('leaderboard')}
        >
          <i className="fas fa-trophy"></i> Leaderboard
        </button>
        <button
          className={`tab ${activeTab === 'history' ? 'active' : ''}`}
          onClick={() => setActiveTab('history')}
        >
          <i className="fas fa-history"></i> Session History
        </button>
      </div>

      {/* Training Scenarios Tab */}
      {activeTab === 'scenarios' && (
        <div className="tab-content scenarios-content">
          <div className="scenarios-layout">
            {/* Left Panel - Scenario Selection */}
            <div className="scenarios-list-panel">
              {/* Agent Selector */}
              <div className="agent-selector panel">
                <div className="panel-header">
                  <h3><i className="fas fa-robot"></i> Select Agent</h3>
                </div>
                <div className="panel-content">
                  <div className="auto-select-toggle">
                    <label className="toggle-label">
                      <input
                        type="checkbox"
                        checked={autoSelectAgent}
                        onChange={(e) => setAutoSelectAgent(e.target.checked)}
                      />
                      <span className="toggle-switch"></span>
                      <span className="toggle-text">Auto-select best agent</span>
                    </label>
                  </div>
                  <select
                    value={selectedAgent}
                    onChange={(e) => setSelectedAgent(e.target.value)}
                    className="agent-select"
                    disabled={autoSelectAgent && selectedScenario}
                  >
                    <option value="">All Agents</option>
                    {agents.map(agent => (
                      <option key={agent.id} value={agent.id}>
                        {agent.display_name}
                      </option>
                    ))}
                  </select>
                  {autoSelectAgent && selectedAgent && (
                    <div className="auto-selected-info">
                      <i className="fas fa-magic"></i> Auto-selected based on scenario category
                    </div>
                  )}
                </div>
              </div>

              {/* Filters */}
              <div className="filters-row">
                <select
                  value={difficultyFilter}
                  onChange={(e) => setDifficultyFilter(e.target.value)}
                >
                  <option value="all">All Difficulties</option>
                  {DIFFICULTY_LEVELS.map(level => (
                    <option key={level.value} value={level.value}>{level.label}</option>
                  ))}
                </select>
                <select
                  value={categoryFilter}
                  onChange={(e) => setCategoryFilter(e.target.value)}
                >
                  <option value="all">All Categories</option>
                  {categories.map(cat => (
                    <option key={cat} value={cat}>{cat.replace(/_/g, ' ')}</option>
                  ))}
                </select>
              </div>

              {/* Create Scenario Button */}
              <button className="create-scenario-btn" onClick={() => setShowCreateModal(true)}>
                <i className="fas fa-plus"></i> Create New Scenario
              </button>

              {/* Scenarios List */}
              <div className="scenarios-list">
                {filteredScenarios.map(scenario => (
                  <div
                    key={scenario.id}
                    className={`scenario-card ${selectedScenario?.id === scenario.id ? 'selected' : ''}`}
                    onClick={() => handleScenarioSelect(scenario)}
                  >
                    <div className="scenario-icon">
                      <i className={getCategoryIcon(scenario.category)}></i>
                    </div>
                    <div className="scenario-info">
                      <h4>{scenario.name}</h4>
                      <p>{scenario.description}</p>
                      <div className="scenario-meta">
                        <span className={getDifficultyClass(scenario.difficulty)}>
                          {scenario.difficulty}
                        </span>
                        <span className="pass-rate">
                          <i className="fas fa-check-circle"></i> {scenario.pass_rate}% pass rate
                        </span>
                      </div>
                    </div>
                  </div>
                ))}

                {filteredScenarios.length === 0 && (
                  <div className="empty-state">
                    <i className="fas fa-search"></i>
                    <p>No scenarios match your filters</p>
                  </div>
                )}
              </div>
            </div>

            {/* Right Panel - Scenario Details & Run */}
            <div className="scenario-detail-panel">
              {selectedScenario ? (
                <div className="panel">
                  <div className="panel-header">
                    <h3>{selectedScenario.name}</h3>
                    <span className={getDifficultyClass(selectedScenario.difficulty)}>
                      {selectedScenario.difficulty}
                    </span>
                  </div>
                  <div className="panel-content">
                    <div className="detail-section">
                      <h4>Description</h4>
                      <p>{selectedScenario.description}</p>
                    </div>

                    <div className="detail-section">
                      <h4>Test Prompt</h4>
                      <div className="prompt-box">{selectedScenario.test_prompt}</div>
                    </div>

                    <div className="detail-section">
                      <h4>Success Criteria</h4>
                      <ul className="criteria-list">
                        {selectedScenario.success_criteria?.map((criterion, idx) => (
                          <li key={idx}>
                            <i className="fas fa-check-circle"></i> {criterion}
                          </li>
                        ))}
                      </ul>
                    </div>

                    <div className="detail-section">
                      <h4>Expected Tools</h4>
                      <div className="tools-list">
                        {selectedScenario.expected_tools?.map((tool, idx) => (
                          <code key={idx} className="tool-tag">{tool}</code>
                        ))}
                      </div>
                    </div>

                    <div className="stats-row">
                      <div className="stat">
                        <span className="stat-value">{selectedScenario.avg_completion_time}s</span>
                        <span className="stat-label">Avg Time</span>
                      </div>
                      <div className="stat">
                        <span className="stat-value">{selectedScenario.pass_rate}%</span>
                        <span className="stat-label">Pass Rate</span>
                      </div>
                    </div>

                    {/* Run Section */}
                    <div className="run-section">
                      {!runningSession && !sessionResult && (
                        <button
                          className="run-btn"
                          onClick={startTrainingSession}
                          disabled={!selectedAgent}
                        >
                          <i className="fas fa-play"></i>
                          {selectedAgent ? 'Start Training Session' : 'Select an Agent First'}
                        </button>
                      )}

                      {runningSession && runningSession.status === 'running' && (
                        <div className="running-state">
                          <i className="fas fa-spinner fa-spin"></i>
                          <p>Running training session...</p>
                          <span className="agent-badge">
                            {runningSession.agent?.display_name}
                          </span>
                        </div>
                      )}

                      {sessionResult && (
                        <div className="result-section">
                          {sessionResult.error ? (
                            <div className="error-result">
                              <i className="fas fa-exclamation-triangle"></i>
                              <p>{sessionResult.message}</p>
                            </div>
                          ) : (
                            <>
                              <div className={`score-display ${getScoreClass(sessionResult.score)}`}>
                                <span className="score-value">{sessionResult.score}</span>
                                <span className="score-label">
                                  {sessionResult.passed ? 'PASSED' : 'FAILED'}
                                </span>
                              </div>

                              <div className="result-details">
                                <h4>Criteria Results</h4>
                                <ul className="results-list">
                                  {sessionResult.criteria_results?.map((result, idx) => (
                                    <li key={idx} className={result.passed ? 'passed' : 'failed'}>
                                      <i className={result.passed ? 'fas fa-check' : 'fas fa-times'}></i>
                                      {result.criterion}
                                    </li>
                                  ))}
                                </ul>

                                <h4>Tool Usage</h4>
                                <div className="tool-results">
                                  {sessionResult.tool_usage?.map((tool, idx) => (
                                    <span key={idx} className={`tool-result ${tool.success ? 'success' : 'failed'}`}>
                                      <i className={tool.success ? 'fas fa-check' : 'fas fa-times'}></i>
                                      {tool.tool}
                                    </span>
                                  ))}
                                </div>

                                {sessionResult.response_time_ms && (
                                  <div className="result-meta">
                                    <span>Response Time: {sessionResult.response_time_ms}ms</span>
                                  </div>
                                )}

                                {sessionResult.feedback && (
                                  <div className="feedback-box">
                                    <h4>Feedback</h4>
                                    <p>{sessionResult.feedback}</p>
                                  </div>
                                )}
                              </div>
                            </>
                          )}

                          <button
                            className="run-again-btn"
                            onClick={() => {
                              setRunningSession(null);
                              setSessionResult(null);
                            }}
                          >
                            <i className="fas fa-redo"></i> Run Again
                          </button>

                          <button
                            className="chat-btn"
                            onClick={() => setShowConversation(true)}
                          >
                            <i className="fas fa-comments"></i> Continue Conversation
                          </button>
                        </div>
                      )}
                    </div>

                    {/* Conversation Section */}
                    {showConversation && (
                      <div className="conversation-section">
                        <div className="conversation-header">
                          <h4><i className="fas fa-comments"></i> Conversation with Agent</h4>
                          <button className="close-chat-btn" onClick={() => setShowConversation(false)}>
                            <i className="fas fa-times"></i>
                          </button>
                        </div>
                        <div className="conversation-messages">
                          {conversationMessages.length === 0 && (
                            <div className="chat-empty-state">
                              <i className="fas fa-robot"></i>
                              <p>Start a conversation with the agent about this scenario</p>
                            </div>
                          )}
                          {conversationMessages.map((msg, idx) => (
                            <div key={idx} className={`chat-message ${msg.role}`}>
                              <div className="message-avatar">
                                {msg.role === 'user' ? (
                                  <i className="fas fa-user"></i>
                                ) : (
                                  <i className="fas fa-robot"></i>
                                )}
                              </div>
                              <div className="message-content">
                                <div className="message-header">
                                  <span className="message-sender">
                                    {msg.role === 'user' ? 'You' : msg.agent || 'Agent'}
                                  </span>
                                  <span className="message-time">
                                    {new Date(msg.timestamp).toLocaleTimeString()}
                                  </span>
                                </div>
                                <div className={`message-text ${msg.error ? 'error' : ''}`}>
                                  {msg.content}
                                </div>
                              </div>
                            </div>
                          ))}
                          {sendingMessage && (
                            <div className="chat-message assistant typing">
                              <div className="message-avatar">
                                <i className="fas fa-robot"></i>
                              </div>
                              <div className="message-content">
                                <div className="typing-indicator">
                                  <span></span><span></span><span></span>
                                </div>
                              </div>
                            </div>
                          )}
                          <div ref={chatEndRef} />
                        </div>
                        <div className="conversation-input">
                          <input
                            type="text"
                            placeholder="Type your message..."
                            value={userMessage}
                            onChange={(e) => setUserMessage(e.target.value)}
                            onKeyPress={(e) => e.key === 'Enter' && sendMessageToAgent()}
                            disabled={sendingMessage}
                          />
                          <button
                            onClick={sendMessageToAgent}
                            disabled={!userMessage.trim() || sendingMessage}
                          >
                            <i className="fas fa-paper-plane"></i>
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Start Conversation Button (when not showing results) */}
                    {!runningSession && !sessionResult && selectedAgent && (
                      <div className="start-chat-section">
                        <button
                          className="start-chat-btn"
                          onClick={() => setShowConversation(true)}
                        >
                          <i className="fas fa-comments"></i> Chat with Agent
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="panel empty-panel">
                  <div className="empty-state">
                    <i className="fas fa-hand-pointer"></i>
                    <h3>Select a Scenario</h3>
                    <p>Choose a training scenario from the list to view details and run a session</p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Leaderboard Tab */}
      {activeTab === 'leaderboard' && (
        <div className="tab-content leaderboard-content">
          <div className="panel">
            <div className="panel-header">
              <h3><i className="fas fa-trophy"></i> Agent Performance Leaderboard</h3>
            </div>
            <div className="panel-content">
              <div className="leaderboard-table">
                <table>
                  <thead>
                    <tr>
                      <th>Rank</th>
                      <th>Agent</th>
                      <th>Total Score</th>
                      <th>Sessions</th>
                      <th>Avg Score</th>
                      <th>Best Score</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {leaderboard.map((entry, idx) => (
                      <tr key={entry.agent_id} className={idx < 3 ? `rank-${idx + 1}` : ''}>
                        <td>
                          <span className={`rank-badge rank-${idx + 1}`}>
                            {idx === 0 && <i className="fas fa-crown"></i>}
                            #{idx + 1}
                          </span>
                        </td>
                        <td>
                          <div className="agent-cell">
                            <span className="agent-name">{entry.display_name}</span>
                            <span className="agent-id">@{entry.agent_name}</span>
                          </div>
                        </td>
                        <td className="score-cell">{entry.total_score.toLocaleString()}</td>
                        <td>{entry.sessions_completed}</td>
                        <td>{entry.avg_score.toFixed(1)}</td>
                        <td>
                          <span className={`best-score ${getScoreClass(entry.best_score)}`}>
                            {entry.best_score}
                          </span>
                        </td>
                        <td>
                          <button
                            className="table-action-btn"
                            onClick={() => {
                              setSelectedAgent(entry.agent_id.toString());
                              setActiveTab('scenarios');
                            }}
                            title="Train this agent"
                          >
                            <i className="fas fa-dumbbell"></i>
                          </button>
                          <button
                            className="table-action-btn"
                            onClick={() => navigate(`/agent/${entry.agent_id}`)}
                            title="View agent profile"
                          >
                            <i className="fas fa-eye"></i>
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* History Tab */}
      {activeTab === 'history' && (
        <div className="tab-content history-content">
          <div className="panel">
            <div className="panel-header">
              <h3><i className="fas fa-history"></i> Recent Training Sessions</h3>
            </div>
            <div className="panel-content">
              {sessions.length === 0 ? (
                <div className="empty-state">
                  <i className="fas fa-clipboard-list"></i>
                  <h3>No Sessions Yet</h3>
                  <p>Start your first training session to see history here</p>
                </div>
              ) : (
                <div className="sessions-table">
                  <table>
                    <thead>
                      <tr>
                        <th>Scenario</th>
                        <th>Agent</th>
                        <th>Score</th>
                        <th>Result</th>
                        <th>Duration</th>
                        <th>Date</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sessions.map(session => (
                        <tr key={session.id}>
                          <td>{session.scenario_name}</td>
                          <td>{session.agent_name}</td>
                          <td>
                            <span className={`score-badge ${getScoreClass(session.score)}`}>
                              {session.score}
                            </span>
                          </td>
                          <td>
                            <span className={`result-badge ${session.passed ? 'passed' : 'failed'}`}>
                              {session.passed ? 'Passed' : 'Failed'}
                            </span>
                          </td>
                          <td>{session.duration_seconds}s</td>
                          <td>{formatTimestamp(session.started_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Create Scenario Modal */}
      {showCreateModal && (
        <div className="modal-overlay" onClick={() => setShowCreateModal(false)}>
          <div className="create-scenario-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2><i className="fas fa-plus-circle"></i> Create New Scenario</h2>
              <button className="modal-close" onClick={() => setShowCreateModal(false)}>
                <i className="fas fa-times"></i>
              </button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label>Scenario Name *</label>
                <input
                  type="text"
                  placeholder="e.g., Complex Pipeline Analysis"
                  value={newScenario.name}
                  onChange={(e) => setNewScenario(prev => ({ ...prev, name: e.target.value }))}
                />
              </div>

              <div className="form-group">
                <label>Description</label>
                <textarea
                  placeholder="Describe what this scenario tests..."
                  value={newScenario.description}
                  onChange={(e) => setNewScenario(prev => ({ ...prev, description: e.target.value }))}
                  rows={2}
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Category</label>
                  <select
                    value={newScenario.category}
                    onChange={(e) => setNewScenario(prev => ({ ...prev, category: e.target.value }))}
                  >
                    <option value="pipeline_analysis">Pipeline Analysis</option>
                    <option value="compliance">Compliance</option>
                    <option value="lead_management">Lead Management</option>
                    <option value="document_management">Document Management</option>
                    <option value="advisory">Advisory</option>
                    <option value="scheduling">Scheduling</option>
                    <option value="underwriting">Underwriting</option>
                    <option value="communication">Communication</option>
                  </select>
                </div>

                <div className="form-group">
                  <label>Difficulty</label>
                  <select
                    value={newScenario.difficulty}
                    onChange={(e) => setNewScenario(prev => ({ ...prev, difficulty: e.target.value }))}
                  >
                    {DIFFICULTY_LEVELS.map(level => (
                      <option key={level.value} value={level.value}>{level.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="form-group">
                <label>Test Prompt *</label>
                <textarea
                  placeholder="The prompt that will be sent to the agent..."
                  value={newScenario.test_prompt}
                  onChange={(e) => setNewScenario(prev => ({ ...prev, test_prompt: e.target.value }))}
                  rows={4}
                />
              </div>

              <div className="form-group">
                <label>Success Criteria</label>
                {newScenario.success_criteria.map((criterion, index) => (
                  <div key={index} className="array-input-row">
                    <input
                      type="text"
                      placeholder="e.g., Correctly identifies at-risk loans"
                      value={criterion}
                      onChange={(e) => updateCriterion(index, e.target.value)}
                    />
                    <button
                      type="button"
                      className="remove-btn"
                      onClick={() => removeCriterion(index)}
                      disabled={newScenario.success_criteria.length <= 1}
                    >
                      <i className="fas fa-minus"></i>
                    </button>
                  </div>
                ))}
                <button type="button" className="add-btn" onClick={addCriterion}>
                  <i className="fas fa-plus"></i> Add Criterion
                </button>
              </div>

              <div className="form-group">
                <label>Expected Tools</label>
                {newScenario.expected_tools.map((tool, index) => (
                  <div key={index} className="array-input-row">
                    <input
                      type="text"
                      placeholder="e.g., get_pipeline_metrics"
                      value={tool}
                      onChange={(e) => updateTool(index, e.target.value)}
                    />
                    <button
                      type="button"
                      className="remove-btn"
                      onClick={() => removeTool(index)}
                      disabled={newScenario.expected_tools.length <= 1}
                    >
                      <i className="fas fa-minus"></i>
                    </button>
                  </div>
                ))}
                <button type="button" className="add-btn" onClick={addTool}>
                  <i className="fas fa-plus"></i> Add Tool
                </button>
              </div>
            </div>
            <div className="modal-footer">
              <button className="cancel-btn" onClick={() => setShowCreateModal(false)}>
                Cancel
              </button>
              <button
                className="create-btn"
                onClick={handleCreateScenario}
                disabled={!newScenario.name || !newScenario.test_prompt || creatingScenario}
              >
                {creatingScenario ? (
                  <><i className="fas fa-spinner fa-spin"></i> Creating...</>
                ) : (
                  <><i className="fas fa-plus"></i> Create Scenario</>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AgentGym;
