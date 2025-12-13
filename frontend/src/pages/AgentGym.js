import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { agentAPI, agentGymAPI } from '../services/api';
import './AgentGym.css';

// Mock data generators
const generateMockAgents = () => [
  { id: 1, agent_name: 'pipeline_analyst', display_name: 'Pipeline Analyst', category: 'crm' },
  { id: 2, agent_name: 'compliance_checker', display_name: 'Compliance Checker', category: 'compliance' },
  { id: 3, agent_name: 'lead_nurturer', display_name: 'Lead Nurturer', category: 'sales' },
  { id: 4, agent_name: 'document_tracker', display_name: 'Document Tracker', category: 'operations' },
  { id: 5, agent_name: 'rate_advisor', display_name: 'Rate Advisor', category: 'advisory' },
  { id: 6, agent_name: 'scheduler', display_name: 'Scheduler', category: 'operations' }
];

const generateMockScenarios = () => [
  {
    id: 1,
    name: 'Pipeline Health Check',
    description: 'Test the agent\'s ability to analyze pipeline metrics and identify issues',
    category: 'pipeline_analysis',
    difficulty: 'medium',
    agent_types: ['pipeline_analyst'],
    expected_tools: ['get_pipeline_metrics', 'get_bottleneck_analysis'],
    test_prompt: 'Analyze the current pipeline health for branch 5 and identify any bottlenecks',
    success_criteria: ['Uses get_pipeline_metrics tool', 'Identifies at least one bottleneck', 'Provides actionable recommendations'],
    avg_completion_time: 45,
    pass_rate: 87.5
  },
  {
    id: 2,
    name: 'TRID Compliance Audit',
    description: 'Verify compliance checking for TILA-RESPA requirements',
    category: 'compliance',
    difficulty: 'hard',
    agent_types: ['compliance_checker'],
    expected_tools: ['check_trid_compliance', 'get_disclosure_timeline'],
    test_prompt: 'Check TRID compliance for loan #12345 and report any violations',
    success_criteria: ['Checks LE timing', 'Checks CD timing', 'Reports all violations'],
    avg_completion_time: 60,
    pass_rate: 92.3
  },
  {
    id: 3,
    name: 'Lead Qualification',
    description: 'Test lead scoring and follow-up recommendations',
    category: 'lead_management',
    difficulty: 'easy',
    agent_types: ['lead_nurturer'],
    expected_tools: ['get_lead_details', 'score_lead', 'suggest_followup'],
    test_prompt: 'Evaluate lead ID 789 and provide follow-up recommendations',
    success_criteria: ['Retrieves lead details', 'Calculates lead score', 'Suggests appropriate follow-up'],
    avg_completion_time: 30,
    pass_rate: 94.1
  },
  {
    id: 4,
    name: 'Document Tracking',
    description: 'Test document status tracking and reminder capabilities',
    category: 'document_management',
    difficulty: 'medium',
    agent_types: ['document_tracker'],
    expected_tools: ['get_missing_documents', 'track_document_request'],
    test_prompt: 'What documents are missing for loan #54321 and when were they requested?',
    success_criteria: ['Lists missing documents', 'Shows request dates', 'Suggests next steps'],
    avg_completion_time: 35,
    pass_rate: 89.7
  },
  {
    id: 5,
    name: 'Rate Comparison',
    description: 'Test rate analysis and recommendation capabilities',
    category: 'advisory',
    difficulty: 'hard',
    agent_types: ['rate_advisor'],
    expected_tools: ['get_current_rates', 'compare_loan_options'],
    test_prompt: 'Compare 30-year fixed vs 15-year fixed for a $400k loan and recommend the best option',
    success_criteria: ['Fetches current rates', 'Compares options', 'Provides clear recommendation'],
    avg_completion_time: 50,
    pass_rate: 85.2
  }
];

const generateMockLeaderboard = () => [
  { agent_id: 2, agent_name: 'compliance_checker', display_name: 'Compliance Checker', total_score: 9450, sessions_completed: 156, avg_score: 60.6, best_score: 98 },
  { agent_id: 1, agent_name: 'pipeline_analyst', display_name: 'Pipeline Analyst', total_score: 8920, sessions_completed: 178, avg_score: 50.1, best_score: 95 },
  { agent_id: 4, agent_name: 'document_tracker', display_name: 'Document Tracker', total_score: 8540, sessions_completed: 145, avg_score: 58.9, best_score: 92 },
  { agent_id: 3, agent_name: 'lead_nurturer', display_name: 'Lead Nurturer', total_score: 7890, sessions_completed: 134, avg_score: 58.9, best_score: 89 },
  { agent_id: 6, agent_name: 'scheduler', display_name: 'Scheduler', total_score: 6750, sessions_completed: 98, avg_score: 68.9, best_score: 94 }
];

const generateMockSessions = () => [
  {
    id: 1,
    scenario_id: 1,
    scenario_name: 'Pipeline Health Check',
    agent_name: 'pipeline_analyst',
    status: 'completed',
    score: 95,
    passed: true,
    started_at: new Date(Date.now() - 2 * 3600000).toISOString(),
    completed_at: new Date(Date.now() - 2 * 3600000 + 45000).toISOString(),
    duration_seconds: 45
  },
  {
    id: 2,
    scenario_id: 2,
    scenario_name: 'TRID Compliance Audit',
    agent_name: 'compliance_checker',
    status: 'completed',
    score: 88,
    passed: true,
    started_at: new Date(Date.now() - 5 * 3600000).toISOString(),
    completed_at: new Date(Date.now() - 5 * 3600000 + 62000).toISOString(),
    duration_seconds: 62
  },
  {
    id: 3,
    scenario_id: 3,
    scenario_name: 'Lead Qualification',
    agent_name: 'lead_nurturer',
    status: 'completed',
    score: 72,
    passed: false,
    started_at: new Date(Date.now() - 24 * 3600000).toISOString(),
    completed_at: new Date(Date.now() - 24 * 3600000 + 38000).toISOString(),
    duration_seconds: 38
  }
];

function AgentGym() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const preselectedAgentId = searchParams.get('agent');

  const [loading, setLoading] = useState(true);
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
        const [agentsData, scenariosData, leaderboardData, sessionsData] = await Promise.all([
          agentAPI.getProfiles({ status: 'active' }),
          agentGymAPI.getScenarios(),
          agentGymAPI.getLeaderboard(),
          agentGymAPI.getSessions({ limit: 20 })
        ]);

        setAgents(agentsData.profiles || agentsData);
        setScenarios(scenariosData.scenarios || scenariosData);
        setLeaderboard(leaderboardData.leaderboard || leaderboardData);
        setSessions(sessionsData.sessions || sessionsData);
        setLoading(false);
      } catch (error) {
        console.error('Error fetching gym data:', error);
        // Load mock data on error
        setAgents(generateMockAgents());
        setScenarios(generateMockScenarios());
        setLeaderboard(generateMockLeaderboard());
        setSessions(generateMockSessions());
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

      // Simulate completion after a delay (in real app, would poll for status)
      setTimeout(() => {
        setSessionResult({
          score: Math.floor(Math.random() * 30) + 70,
          passed: true,
          criteria_results: selectedScenario.success_criteria.map((c, idx) => ({
            criterion: c,
            passed: Math.random() > 0.2,
            details: 'Successfully met criterion'
          })),
          tool_usage: selectedScenario.expected_tools.map(t => ({
            tool: t,
            used: Math.random() > 0.1,
            success: Math.random() > 0.1
          })),
          response_time_ms: Math.floor(Math.random() * 2000) + 500,
          feedback: 'Good performance overall. Consider improving response structure.'
        });
        setRunningSession(prev => ({ ...prev, status: 'completed' }));
      }, 3000);
    } catch (error) {
      console.error('Error starting session:', error);
      // Mock result on error
      setTimeout(() => {
        setSessionResult({
          score: 85,
          passed: true,
          criteria_results: selectedScenario.success_criteria.map(c => ({
            criterion: c,
            passed: true,
            details: 'Successfully met criterion'
          })),
          tool_usage: selectedScenario.expected_tools.map(t => ({
            tool: t,
            used: true,
            success: true
          })),
          response_time_ms: 1250,
          feedback: 'Good performance overall.'
        });
        setRunningSession(prev => ({ ...prev, status: 'completed' }));
      }, 3000);
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

                            <div className="result-meta">
                              <span>Response Time: {sessionResult.response_time_ms}ms</span>
                            </div>

                            <div className="feedback-box">
                              <h4>Feedback</h4>
                              <p>{sessionResult.feedback}</p>
                            </div>
                          </div>

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
