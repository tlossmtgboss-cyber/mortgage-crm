import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { agentAPI, agentGymAPI } from '../services/api';
import './AgentGym.css';

function AgentGym() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const preselectedAgentId = searchParams.get('agent');

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
      case 'easy': return 'difficulty-badge easy';
      case 'medium': return 'difficulty-badge medium';
      case 'hard': return 'difficulty-badge hard';
      default: return 'difficulty-badge';
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
                  <select
                    value={selectedAgent}
                    onChange={(e) => setSelectedAgent(e.target.value)}
                    className="agent-select"
                  >
                    <option value="">All Agents</option>
                    {agents.map(agent => (
                      <option key={agent.id} value={agent.id}>
                        {agent.display_name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Filters */}
              <div className="filters-row">
                <select
                  value={difficultyFilter}
                  onChange={(e) => setDifficultyFilter(e.target.value)}
                >
                  <option value="all">All Difficulties</option>
                  <option value="easy">Easy</option>
                  <option value="medium">Medium</option>
                  <option value="hard">Hard</option>
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

              {/* Scenarios List */}
              <div className="scenarios-list">
                {filteredScenarios.map(scenario => (
                  <div
                    key={scenario.id}
                    className={`scenario-card ${selectedScenario?.id === scenario.id ? 'selected' : ''}`}
                    onClick={() => setSelectedScenario(scenario)}
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
                        </div>
                      )}
                    </div>
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
    </div>
  );
}

export default AgentGym;
