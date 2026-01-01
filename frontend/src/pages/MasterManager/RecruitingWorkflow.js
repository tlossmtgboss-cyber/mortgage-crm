import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  loadDashboardData,
  getPeople,
  getHotLeads,
  getTasks,
  getCadencesDue,
  getObjectionsDueForRevisit,
  getPlaybookRuns,
  createPerson,
  updatePerson,
  createSignal,
  createObjection,
  updateObjection,
  createTask,
  completeTask,
  enrollInCadence,
  advanceCadenceStep,
  pauseCadence,
  createNote,
  PERSON_TYPES,
  RELATIONSHIP_STAGES,
  SIGNAL_TYPES,
  OBJECTION_CATEGORIES,
  COMM_CHANNELS,
  TASK_PRIORITIES,
  getTimingGrade,
  getStageInfo,
  getObjectionInfo
} from '../../services/recruitingWorkflowApi';
import './MasterManager.css';

const RecruitingWorkflow = () => {
  const navigate = useNavigate();

  // Tab state
  const [activeTab, setActiveTab] = useState('overview');

  // Data state
  const [stats, setStats] = useState(null);
  const [hotLeads, setHotLeads] = useState([]);
  const [people, setPeople] = useState({ data: [], total: 0 });
  const [tasks, setTasks] = useState([]);
  const [cadencesDue, setCadencesDue] = useState([]);
  const [objectionsDue, setObjectionsDue] = useState([]);
  const [playbookRuns, setPlaybookRuns] = useState([]);

  // Loading and error state
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filters
  const [personTypeFilter, setPersonTypeFilter] = useState('');
  const [stageFilter, setStageFilter] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  // Modal states
  const [showAddPerson, setShowAddPerson] = useState(false);
  const [showAddSignal, setShowAddSignal] = useState(false);
  const [showAddObjection, setShowAddObjection] = useState(false);
  const [showAddTask, setShowAddTask] = useState(false);
  const [selectedPerson, setSelectedPerson] = useState(null);

  // Form states
  const [newPerson, setNewPerson] = useState({
    person_type: 'LOAN_OFFICER',
    first_name: '',
    last_name: '',
    primary_email: '',
    primary_phone: '',
    title: '',
    location_city: '',
    location_state: '',
    source: ''
  });

  const [newSignal, setNewSignal] = useState({
    person_id: '',
    signal_type: 'MEETING_INTENT',
    evidence: '',
    confidence: 0.8
  });

  const [newObjection, setNewObjection] = useState({
    person_id: '',
    category: 'TIMING',
    severity: 3,
    statement: '',
    context: ''
  });

  const [newTask, setNewTask] = useState({
    person_id: '',
    title: '',
    description: '',
    priority: 'MEDIUM',
    due_at: ''
  });

  // Load initial data
  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const data = await loadDashboardData();
      setStats(data.stats);
      setHotLeads(data.hotLeads || []);
      setTasks(data.tasksDue || []);
      setCadencesDue(data.cadencesDue || []);
      setObjectionsDue(data.objectionsDue || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  // Load people list
  const loadPeople = useCallback(async () => {
    try {
      const data = await getPeople({
        person_type: personTypeFilter || undefined,
        relationship_stage: stageFilter || undefined,
        search: searchQuery || undefined,
        limit: 50,
        order_by: 'timing_score DESC'
      });
      setPeople(data);
    } catch (err) {
      console.error('Failed to load people:', err);
    }
  }, [personTypeFilter, stageFilter, searchQuery]);

  // Load playbook runs
  const loadPlaybookRuns = useCallback(async () => {
    try {
      const data = await getPlaybookRuns({ limit: 20 });
      setPlaybookRuns(data || []);
    } catch (err) {
      console.error('Failed to load playbook runs:', err);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    if (activeTab === 'people') {
      loadPeople();
    } else if (activeTab === 'playbooks') {
      loadPlaybookRuns();
    }
  }, [activeTab, loadPeople, loadPlaybookRuns]);

  // Handlers
  const handleCreatePerson = async (e) => {
    e.preventDefault();
    try {
      await createPerson(newPerson);
      setShowAddPerson(false);
      setNewPerson({
        person_type: 'LOAN_OFFICER',
        first_name: '',
        last_name: '',
        primary_email: '',
        primary_phone: '',
        title: '',
        location_city: '',
        location_state: '',
        source: ''
      });
      loadPeople();
      loadData();
    } catch (err) {
      alert('Failed to create person: ' + err.message);
    }
  };

  const handleCreateSignal = async (e) => {
    e.preventDefault();
    try {
      await createSignal(newSignal);
      setShowAddSignal(false);
      setNewSignal({
        person_id: '',
        signal_type: 'MEETING_INTENT',
        evidence: '',
        confidence: 0.8
      });
      loadData();
    } catch (err) {
      alert('Failed to create signal: ' + err.message);
    }
  };

  const handleCreateObjection = async (e) => {
    e.preventDefault();
    try {
      await createObjection(newObjection);
      setShowAddObjection(false);
      setNewObjection({
        person_id: '',
        category: 'TIMING',
        severity: 3,
        statement: '',
        context: ''
      });
      loadData();
    } catch (err) {
      alert('Failed to create objection: ' + err.message);
    }
  };

  const handleCreateTask = async (e) => {
    e.preventDefault();
    try {
      await createTask(newTask);
      setShowAddTask(false);
      setNewTask({
        person_id: '',
        title: '',
        description: '',
        priority: 'MEDIUM',
        due_at: ''
      });
      loadData();
    } catch (err) {
      alert('Failed to create task: ' + err.message);
    }
  };

  const handleCompleteTask = async (taskId) => {
    try {
      await completeTask(taskId);
      loadData();
    } catch (err) {
      alert('Failed to complete task: ' + err.message);
    }
  };

  const handleAdvanceCadence = async (enrollmentId) => {
    try {
      await advanceCadenceStep(enrollmentId);
      loadData();
    } catch (err) {
      alert('Failed to advance cadence: ' + err.message);
    }
  };

  const handlePauseCadence = async (enrollmentId) => {
    try {
      await pauseCadence(enrollmentId, 'Manually paused');
      loadData();
    } catch (err) {
      alert('Failed to pause cadence: ' + err.message);
    }
  };

  const handleResolveObjection = async (objectionId) => {
    try {
      await updateObjection(objectionId, { status: 'RESOLVED' });
      loadData();
    } catch (err) {
      alert('Failed to resolve objection: ' + err.message);
    }
  };

  const handleViewPerson = (personId) => {
    navigate(`/master-manager/recruiting-workflow/${personId}`);
  };

  // Render timing score badge
  const renderTimingBadge = (score) => {
    const grade = getTimingGrade(score || 0);
    return (
      <span
        className="timing-badge"
        style={{ backgroundColor: grade.color, color: 'white' }}
      >
        {score || 0} - {grade.label}
      </span>
    );
  };

  // Render stage badge
  const renderStageBadge = (stage) => {
    const info = getStageInfo(stage);
    return (
      <span
        className="stage-badge"
        style={{ backgroundColor: info.color, color: 'white' }}
      >
        {info.icon} {info.label}
      </span>
    );
  };

  if (loading && !stats) {
    return (
      <div className="master-manager-container">
        <div className="loading-spinner">Loading Recruiting Workflow...</div>
      </div>
    );
  }

  return (
    <div className="master-manager-container">
      {/* Header */}
      <div className="mm-header">
        <div className="mm-header-content">
          <h1>Recruiting Workflow CRM</h1>
          <p>Multi-year relationship development for LOs and Realtors</p>
        </div>
        <div className="mm-header-actions">
          <button
            className="mm-btn mm-btn-primary"
            onClick={() => setShowAddPerson(true)}
          >
            + Add Person
          </button>
          <button
            className="mm-btn mm-btn-secondary"
            onClick={() => setShowAddSignal(true)}
          >
            + Log Signal
          </button>
        </div>
      </div>

      {error && (
        <div className="mm-error-banner">
          {error}
          <button onClick={loadData}>Retry</button>
        </div>
      )}

      {/* Stats Overview */}
      {stats && (
        <div className="mm-stats-grid">
          <div className="mm-stat-card">
            <div className="mm-stat-value">{stats.total_people || 0}</div>
            <div className="mm-stat-label">Total People</div>
            <div className="mm-stat-breakdown">
              <span>LOs: {stats.by_type?.LOAN_OFFICER || 0}</span>
              <span>Realtors: {stats.by_type?.REALTOR || 0}</span>
            </div>
          </div>
          <div className="mm-stat-card mm-stat-hot">
            <div className="mm-stat-value">{stats.hot_leads || 0}</div>
            <div className="mm-stat-label">Hot Leads</div>
            <div className="mm-stat-sublabel">Score 70+</div>
          </div>
          <div className="mm-stat-card mm-stat-warm">
            <div className="mm-stat-value">{stats.warm_leads || 0}</div>
            <div className="mm-stat-label">Warm Leads</div>
            <div className="mm-stat-sublabel">Score 50-69</div>
          </div>
          <div className="mm-stat-card">
            <div className="mm-stat-value">{stats.cadences_active || 0}</div>
            <div className="mm-stat-label">Active Cadences</div>
          </div>
          <div className="mm-stat-card">
            <div className="mm-stat-value">{stats.tasks_pending || 0}</div>
            <div className="mm-stat-label">Pending Tasks</div>
            {stats.tasks_overdue > 0 && (
              <div className="mm-stat-warning">{stats.tasks_overdue} overdue</div>
            )}
          </div>
          <div className="mm-stat-card">
            <div className="mm-stat-value">{stats.objections_open || 0}</div>
            <div className="mm-stat-label">Open Objections</div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="mm-tabs">
        <button
          className={`mm-tab ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button
          className={`mm-tab ${activeTab === 'people' ? 'active' : ''}`}
          onClick={() => setActiveTab('people')}
        >
          People
        </button>
        <button
          className={`mm-tab ${activeTab === 'hot-leads' ? 'active' : ''}`}
          onClick={() => setActiveTab('hot-leads')}
        >
          Hot Leads
        </button>
        <button
          className={`mm-tab ${activeTab === 'tasks' ? 'active' : ''}`}
          onClick={() => setActiveTab('tasks')}
        >
          Tasks
        </button>
        <button
          className={`mm-tab ${activeTab === 'cadences' ? 'active' : ''}`}
          onClick={() => setActiveTab('cadences')}
        >
          Cadences Due
        </button>
        <button
          className={`mm-tab ${activeTab === 'objections' ? 'active' : ''}`}
          onClick={() => setActiveTab('objections')}
        >
          Objections
        </button>
        <button
          className={`mm-tab ${activeTab === 'playbooks' ? 'active' : ''}`}
          onClick={() => setActiveTab('playbooks')}
        >
          Playbooks
        </button>
      </div>

      {/* Tab Content */}
      <div className="mm-tab-content">
        {/* Overview Tab */}
        {activeTab === 'overview' && (
          <div className="mm-overview-grid">
            {/* Hot Leads Section */}
            <div className="mm-section">
              <div className="mm-section-header">
                <h3>🔥 Hot Leads (Action Required)</h3>
                <button
                  className="mm-btn mm-btn-small"
                  onClick={() => setActiveTab('hot-leads')}
                >
                  View All
                </button>
              </div>
              <div className="mm-list">
                {hotLeads.slice(0, 5).map((lead) => (
                  <div
                    key={lead.id}
                    className="mm-list-item mm-list-item-clickable"
                    onClick={() => handleViewPerson(lead.id)}
                  >
                    <div className="mm-list-item-main">
                      <span className="mm-list-item-title">
                        {lead.display_name || `${lead.first_name} ${lead.last_name}`}
                      </span>
                      <span className="mm-list-item-subtitle">
                        {PERSON_TYPES.find(t => t.value === lead.person_type)?.label || lead.person_type}
                        {lead.title && ` • ${lead.title}`}
                      </span>
                    </div>
                    <div className="mm-list-item-meta">
                      {renderTimingBadge(lead.timing_score)}
                    </div>
                  </div>
                ))}
                {hotLeads.length === 0 && (
                  <div className="mm-empty-state">No hot leads at the moment</div>
                )}
              </div>
            </div>

            {/* Tasks Due Section */}
            <div className="mm-section">
              <div className="mm-section-header">
                <h3>📋 Overdue Tasks</h3>
                <button
                  className="mm-btn mm-btn-small"
                  onClick={() => setActiveTab('tasks')}
                >
                  View All
                </button>
              </div>
              <div className="mm-list">
                {tasks.slice(0, 5).map((task) => (
                  <div key={task.id} className="mm-list-item">
                    <div className="mm-list-item-main">
                      <span className="mm-list-item-title">{task.title}</span>
                      <span className="mm-list-item-subtitle">
                        {task.person_name || 'No person assigned'}
                      </span>
                    </div>
                    <div className="mm-list-item-actions">
                      <button
                        className="mm-btn mm-btn-small mm-btn-success"
                        onClick={() => handleCompleteTask(task.id)}
                      >
                        Complete
                      </button>
                    </div>
                  </div>
                ))}
                {tasks.length === 0 && (
                  <div className="mm-empty-state">No overdue tasks</div>
                )}
              </div>
            </div>

            {/* Cadences Due Section */}
            <div className="mm-section">
              <div className="mm-section-header">
                <h3>📧 Cadences Due</h3>
                <button
                  className="mm-btn mm-btn-small"
                  onClick={() => setActiveTab('cadences')}
                >
                  View All
                </button>
              </div>
              <div className="mm-list">
                {cadencesDue.slice(0, 5).map((item) => (
                  <div key={item.enrollment_id} className="mm-list-item">
                    <div className="mm-list-item-main">
                      <span className="mm-list-item-title">{item.person_name}</span>
                      <span className="mm-list-item-subtitle">
                        {item.cadence_name} • Step {item.current_step}
                      </span>
                      <span className="mm-list-item-meta">
                        {COMM_CHANNELS.find(c => c.value === item.next_channel)?.icon} {item.next_template}
                      </span>
                    </div>
                    <div className="mm-list-item-actions">
                      <button
                        className="mm-btn mm-btn-small mm-btn-primary"
                        onClick={() => handleAdvanceCadence(item.enrollment_id)}
                      >
                        Execute
                      </button>
                      <button
                        className="mm-btn mm-btn-small"
                        onClick={() => handlePauseCadence(item.enrollment_id)}
                      >
                        Pause
                      </button>
                    </div>
                  </div>
                ))}
                {cadencesDue.length === 0 && (
                  <div className="mm-empty-state">No cadences due</div>
                )}
              </div>
            </div>

            {/* Objections Due Section */}
            <div className="mm-section">
              <div className="mm-section-header">
                <h3>⚠️ Objections to Revisit</h3>
                <button
                  className="mm-btn mm-btn-small"
                  onClick={() => setActiveTab('objections')}
                >
                  View All
                </button>
              </div>
              <div className="mm-list">
                {objectionsDue.slice(0, 5).map((obj) => (
                  <div key={obj.id} className="mm-list-item">
                    <div className="mm-list-item-main">
                      <span className="mm-list-item-title">
                        {getObjectionInfo(obj.category).icon} {obj.category}
                      </span>
                      <span className="mm-list-item-subtitle">
                        {obj.person_name} • Severity: {obj.severity}/5
                      </span>
                      {obj.statement && (
                        <span className="mm-list-item-quote">"{obj.statement}"</span>
                      )}
                    </div>
                    <div className="mm-list-item-actions">
                      <button
                        className="mm-btn mm-btn-small mm-btn-success"
                        onClick={() => handleResolveObjection(obj.id)}
                      >
                        Resolve
                      </button>
                    </div>
                  </div>
                ))}
                {objectionsDue.length === 0 && (
                  <div className="mm-empty-state">No objections due for revisit</div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* People Tab */}
        {activeTab === 'people' && (
          <div className="mm-section">
            <div className="mm-filters">
              <select
                value={personTypeFilter}
                onChange={(e) => setPersonTypeFilter(e.target.value)}
                className="mm-filter-select"
              >
                <option value="">All Types</option>
                {PERSON_TYPES.map((type) => (
                  <option key={type.value} value={type.value}>
                    {type.icon} {type.label}
                  </option>
                ))}
              </select>
              <select
                value={stageFilter}
                onChange={(e) => setStageFilter(e.target.value)}
                className="mm-filter-select"
              >
                <option value="">All Stages</option>
                {RELATIONSHIP_STAGES.map((stage) => (
                  <option key={stage.value} value={stage.value}>
                    {stage.icon} {stage.label}
                  </option>
                ))}
              </select>
              <input
                type="text"
                placeholder="Search by name, email, phone..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="mm-search-input"
              />
              <button className="mm-btn mm-btn-primary" onClick={loadPeople}>
                Search
              </button>
            </div>

            <div className="mm-table-container">
              <table className="mm-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Type</th>
                    <th>Stage</th>
                    <th>Timing Score</th>
                    <th>Location</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {people.data?.map((person) => (
                    <tr key={person.id}>
                      <td>
                        <div className="mm-person-cell">
                          <strong>{person.display_name || `${person.first_name} ${person.last_name}`}</strong>
                          {person.title && <span className="mm-person-title">{person.title}</span>}
                          {person.primary_email && <span className="mm-person-email">{person.primary_email}</span>}
                        </div>
                      </td>
                      <td>
                        {PERSON_TYPES.find(t => t.value === person.person_type)?.icon}{' '}
                        {PERSON_TYPES.find(t => t.value === person.person_type)?.label}
                      </td>
                      <td>{renderStageBadge(person.relationship_stage)}</td>
                      <td>{renderTimingBadge(person.timing_score)}</td>
                      <td>
                        {person.location_city && person.location_state
                          ? `${person.location_city}, ${person.location_state}`
                          : '-'}
                      </td>
                      <td>
                        <button
                          className="mm-btn mm-btn-small"
                          onClick={() => handleViewPerson(person.id)}
                        >
                          View
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {people.data?.length === 0 && (
                <div className="mm-empty-state">No people found</div>
              )}
            </div>
            <div className="mm-pagination">
              <span>Showing {people.data?.length || 0} of {people.total || 0}</span>
            </div>
          </div>
        )}

        {/* Hot Leads Tab */}
        {activeTab === 'hot-leads' && (
          <div className="mm-section">
            <div className="mm-section-header">
              <h3>🔥 Hot Leads - Timing Score 70+</h3>
              <p>These people are showing strong intent signals. Prioritize outreach!</p>
            </div>
            <div className="mm-cards-grid">
              {hotLeads.map((lead) => (
                <div key={lead.id} className="mm-card mm-card-hot">
                  <div className="mm-card-header">
                    <div className="mm-card-title">
                      {lead.display_name || `${lead.first_name} ${lead.last_name}`}
                    </div>
                    {renderTimingBadge(lead.timing_score)}
                  </div>
                  <div className="mm-card-body">
                    <p>
                      <strong>Type:</strong>{' '}
                      {PERSON_TYPES.find(t => t.value === lead.person_type)?.label}
                    </p>
                    <p>
                      <strong>Stage:</strong>{' '}
                      {renderStageBadge(lead.relationship_stage)}
                    </p>
                    {lead.title && <p><strong>Title:</strong> {lead.title}</p>}
                    {lead.last_signal_type && (
                      <p>
                        <strong>Last Signal:</strong> {lead.last_signal_type}
                      </p>
                    )}
                    {lead.next_best_action && (
                      <p className="mm-next-action">
                        <strong>Next Action:</strong> {lead.next_best_action}
                      </p>
                    )}
                  </div>
                  <div className="mm-card-footer">
                    <button
                      className="mm-btn mm-btn-primary"
                      onClick={() => handleViewPerson(lead.id)}
                    >
                      Take Action
                    </button>
                  </div>
                </div>
              ))}
              {hotLeads.length === 0 && (
                <div className="mm-empty-state-large">
                  <h4>No Hot Leads</h4>
                  <p>People with timing scores of 70+ will appear here.</p>
                  <p>Log signals to boost timing scores!</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Tasks Tab */}
        {activeTab === 'tasks' && (
          <div className="mm-section">
            <div className="mm-section-header">
              <h3>📋 Tasks</h3>
              <button
                className="mm-btn mm-btn-primary"
                onClick={() => setShowAddTask(true)}
              >
                + Add Task
              </button>
            </div>
            <div className="mm-list">
              {tasks.map((task) => (
                <div key={task.id} className="mm-list-item">
                  <div className="mm-list-item-main">
                    <div className="mm-list-item-header">
                      <span
                        className="mm-priority-badge"
                        style={{
                          backgroundColor: TASK_PRIORITIES.find(p => p.value === task.priority)?.color
                        }}
                      >
                        {task.priority}
                      </span>
                      <span className="mm-list-item-title">{task.title}</span>
                    </div>
                    <span className="mm-list-item-subtitle">
                      {task.person_name || 'No person'} • {task.task_type || 'General'}
                    </span>
                    {task.description && (
                      <span className="mm-list-item-desc">{task.description}</span>
                    )}
                    {task.due_at && (
                      <span className="mm-list-item-due">
                        Due: {new Date(task.due_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                  <div className="mm-list-item-actions">
                    <button
                      className="mm-btn mm-btn-small mm-btn-success"
                      onClick={() => handleCompleteTask(task.id)}
                    >
                      Complete
                    </button>
                  </div>
                </div>
              ))}
              {tasks.length === 0 && (
                <div className="mm-empty-state">No pending tasks</div>
              )}
            </div>
          </div>
        )}

        {/* Cadences Tab */}
        {activeTab === 'cadences' && (
          <div className="mm-section">
            <div className="mm-section-header">
              <h3>📧 Cadences Due for Execution</h3>
              <p>These cadence steps are ready to be sent</p>
            </div>
            <div className="mm-list">
              {cadencesDue.map((item) => (
                <div key={item.enrollment_id} className="mm-list-item">
                  <div className="mm-list-item-main">
                    <span className="mm-list-item-title">{item.person_name}</span>
                    <span className="mm-list-item-subtitle">
                      <strong>{item.cadence_name}</strong> • Step {item.current_step}
                    </span>
                    <div className="mm-cadence-details">
                      <span className="mm-channel-badge">
                        {COMM_CHANNELS.find(c => c.value === item.next_channel)?.icon}{' '}
                        {item.next_channel}
                      </span>
                      <span className="mm-template-name">{item.next_template}</span>
                      {item.next_goal && (
                        <span className="mm-goal">Goal: {item.next_goal}</span>
                      )}
                    </div>
                  </div>
                  <div className="mm-list-item-actions">
                    <button
                      className="mm-btn mm-btn-primary"
                      onClick={() => handleAdvanceCadence(item.enrollment_id)}
                    >
                      Execute & Advance
                    </button>
                    <button
                      className="mm-btn mm-btn-secondary"
                      onClick={() => handlePauseCadence(item.enrollment_id)}
                    >
                      Pause
                    </button>
                  </div>
                </div>
              ))}
              {cadencesDue.length === 0 && (
                <div className="mm-empty-state">No cadences due for execution</div>
              )}
            </div>
          </div>
        )}

        {/* Objections Tab */}
        {activeTab === 'objections' && (
          <div className="mm-section">
            <div className="mm-section-header">
              <h3>⚠️ Objections Due for Revisit</h3>
              <button
                className="mm-btn mm-btn-primary"
                onClick={() => setShowAddObjection(true)}
              >
                + Log Objection
              </button>
            </div>
            <div className="mm-list">
              {objectionsDue.map((obj) => (
                <div key={obj.id} className="mm-list-item">
                  <div className="mm-list-item-main">
                    <div className="mm-objection-header">
                      <span className="mm-objection-category">
                        {getObjectionInfo(obj.category).icon} {obj.category}
                      </span>
                      <span className="mm-severity-badge">
                        Severity: {obj.severity}/5
                      </span>
                    </div>
                    <span className="mm-list-item-title">{obj.person_name}</span>
                    {obj.statement && (
                      <blockquote className="mm-objection-quote">
                        "{obj.statement}"
                      </blockquote>
                    )}
                    {obj.context && (
                      <span className="mm-objection-context">{obj.context}</span>
                    )}
                  </div>
                  <div className="mm-list-item-actions">
                    <button
                      className="mm-btn mm-btn-small"
                      onClick={() => handleViewPerson(obj.person_id)}
                    >
                      View Person
                    </button>
                    <button
                      className="mm-btn mm-btn-small mm-btn-success"
                      onClick={() => handleResolveObjection(obj.id)}
                    >
                      Mark Resolved
                    </button>
                  </div>
                </div>
              ))}
              {objectionsDue.length === 0 && (
                <div className="mm-empty-state">No objections due for revisit</div>
              )}
            </div>
          </div>
        )}

        {/* Playbooks Tab */}
        {activeTab === 'playbooks' && (
          <div className="mm-section">
            <div className="mm-section-header">
              <h3>🎯 Active Playbook Runs</h3>
              <p>Playbooks triggered by timing scores or signals</p>
            </div>
            <div className="mm-list">
              {playbookRuns.map((run) => (
                <div key={run.id} className="mm-list-item">
                  <div className="mm-list-item-main">
                    <span className="mm-list-item-title">{run.playbook_name}</span>
                    <span className="mm-list-item-subtitle">
                      {run.person_name} • {run.status}
                    </span>
                    <div className="mm-playbook-progress">
                      <span>Actions: {run.actions_completed}/{run.actions_total}</span>
                      <div className="mm-progress-bar">
                        <div
                          className="mm-progress-fill"
                          style={{
                            width: `${(run.actions_completed / run.actions_total) * 100}%`
                          }}
                        />
                      </div>
                    </div>
                  </div>
                  <div className="mm-list-item-meta">
                    <span className={`mm-status-badge mm-status-${run.status.toLowerCase()}`}>
                      {run.status}
                    </span>
                  </div>
                </div>
              ))}
              {playbookRuns.length === 0 && (
                <div className="mm-empty-state">No active playbook runs</div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Add Person Modal */}
      {showAddPerson && (
        <div className="mm-modal-overlay" onClick={() => setShowAddPerson(false)}>
          <div className="mm-modal" onClick={(e) => e.stopPropagation()}>
            <div className="mm-modal-header">
              <h2>Add New Person</h2>
              <button className="mm-modal-close" onClick={() => setShowAddPerson(false)}>×</button>
            </div>
            <form onSubmit={handleCreatePerson}>
              <div className="mm-form-grid">
                <div className="mm-form-group">
                  <label>Type *</label>
                  <select
                    value={newPerson.person_type}
                    onChange={(e) => setNewPerson({ ...newPerson, person_type: e.target.value })}
                    required
                  >
                    {PERSON_TYPES.map((type) => (
                      <option key={type.value} value={type.value}>
                        {type.icon} {type.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="mm-form-group">
                  <label>Source</label>
                  <input
                    type="text"
                    value={newPerson.source}
                    onChange={(e) => setNewPerson({ ...newPerson, source: e.target.value })}
                    placeholder="e.g., LinkedIn, Referral, Conference"
                  />
                </div>
                <div className="mm-form-group">
                  <label>First Name *</label>
                  <input
                    type="text"
                    value={newPerson.first_name}
                    onChange={(e) => setNewPerson({ ...newPerson, first_name: e.target.value })}
                    required
                  />
                </div>
                <div className="mm-form-group">
                  <label>Last Name *</label>
                  <input
                    type="text"
                    value={newPerson.last_name}
                    onChange={(e) => setNewPerson({ ...newPerson, last_name: e.target.value })}
                    required
                  />
                </div>
                <div className="mm-form-group">
                  <label>Email</label>
                  <input
                    type="email"
                    value={newPerson.primary_email}
                    onChange={(e) => setNewPerson({ ...newPerson, primary_email: e.target.value })}
                  />
                </div>
                <div className="mm-form-group">
                  <label>Phone</label>
                  <input
                    type="tel"
                    value={newPerson.primary_phone}
                    onChange={(e) => setNewPerson({ ...newPerson, primary_phone: e.target.value })}
                  />
                </div>
                <div className="mm-form-group">
                  <label>Title</label>
                  <input
                    type="text"
                    value={newPerson.title}
                    onChange={(e) => setNewPerson({ ...newPerson, title: e.target.value })}
                    placeholder="e.g., Senior Loan Officer"
                  />
                </div>
                <div className="mm-form-group">
                  <label>City</label>
                  <input
                    type="text"
                    value={newPerson.location_city}
                    onChange={(e) => setNewPerson({ ...newPerson, location_city: e.target.value })}
                  />
                </div>
                <div className="mm-form-group">
                  <label>State</label>
                  <input
                    type="text"
                    value={newPerson.location_state}
                    onChange={(e) => setNewPerson({ ...newPerson, location_state: e.target.value })}
                    placeholder="e.g., CA"
                    maxLength={2}
                  />
                </div>
              </div>
              <div className="mm-modal-footer">
                <button type="button" className="mm-btn" onClick={() => setShowAddPerson(false)}>
                  Cancel
                </button>
                <button type="submit" className="mm-btn mm-btn-primary">
                  Add Person
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Add Signal Modal */}
      {showAddSignal && (
        <div className="mm-modal-overlay" onClick={() => setShowAddSignal(false)}>
          <div className="mm-modal" onClick={(e) => e.stopPropagation()}>
            <div className="mm-modal-header">
              <h2>Log Signal</h2>
              <button className="mm-modal-close" onClick={() => setShowAddSignal(false)}>×</button>
            </div>
            <form onSubmit={handleCreateSignal}>
              <div className="mm-form-group">
                <label>Person ID *</label>
                <input
                  type="text"
                  value={newSignal.person_id}
                  onChange={(e) => setNewSignal({ ...newSignal, person_id: e.target.value })}
                  required
                  placeholder="Enter person UUID"
                />
              </div>
              <div className="mm-form-group">
                <label>Signal Type *</label>
                <select
                  value={newSignal.signal_type}
                  onChange={(e) => setNewSignal({ ...newSignal, signal_type: e.target.value })}
                  required
                >
                  {SIGNAL_TYPES.map((type) => (
                    <option key={type.value} value={type.value}>
                      {type.label} (+{type.weight} points)
                    </option>
                  ))}
                </select>
              </div>
              <div className="mm-form-group">
                <label>Evidence</label>
                <textarea
                  value={newSignal.evidence}
                  onChange={(e) => setNewSignal({ ...newSignal, evidence: e.target.value })}
                  placeholder="What indicates this signal? (e.g., 'Clicked calendar link in email')"
                  rows={3}
                />
              </div>
              <div className="mm-form-group">
                <label>Confidence (0-1)</label>
                <input
                  type="number"
                  min="0"
                  max="1"
                  step="0.1"
                  value={newSignal.confidence}
                  onChange={(e) => setNewSignal({ ...newSignal, confidence: parseFloat(e.target.value) })}
                />
              </div>
              <div className="mm-modal-footer">
                <button type="button" className="mm-btn" onClick={() => setShowAddSignal(false)}>
                  Cancel
                </button>
                <button type="submit" className="mm-btn mm-btn-primary">
                  Log Signal
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Add Objection Modal */}
      {showAddObjection && (
        <div className="mm-modal-overlay" onClick={() => setShowAddObjection(false)}>
          <div className="mm-modal" onClick={(e) => e.stopPropagation()}>
            <div className="mm-modal-header">
              <h2>Log Objection</h2>
              <button className="mm-modal-close" onClick={() => setShowAddObjection(false)}>×</button>
            </div>
            <form onSubmit={handleCreateObjection}>
              <div className="mm-form-group">
                <label>Person ID *</label>
                <input
                  type="text"
                  value={newObjection.person_id}
                  onChange={(e) => setNewObjection({ ...newObjection, person_id: e.target.value })}
                  required
                  placeholder="Enter person UUID"
                />
              </div>
              <div className="mm-form-group">
                <label>Category *</label>
                <select
                  value={newObjection.category}
                  onChange={(e) => setNewObjection({ ...newObjection, category: e.target.value })}
                  required
                >
                  {OBJECTION_CATEGORIES.map((cat) => (
                    <option key={cat.value} value={cat.value}>
                      {cat.icon} {cat.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="mm-form-group">
                <label>Severity (1-5)</label>
                <input
                  type="range"
                  min="1"
                  max="5"
                  value={newObjection.severity}
                  onChange={(e) => setNewObjection({ ...newObjection, severity: parseInt(e.target.value) })}
                />
                <span>{newObjection.severity}/5</span>
              </div>
              <div className="mm-form-group">
                <label>Their Statement</label>
                <textarea
                  value={newObjection.statement}
                  onChange={(e) => setNewObjection({ ...newObjection, statement: e.target.value })}
                  placeholder="What exactly did they say?"
                  rows={2}
                />
              </div>
              <div className="mm-form-group">
                <label>Context</label>
                <textarea
                  value={newObjection.context}
                  onChange={(e) => setNewObjection({ ...newObjection, context: e.target.value })}
                  placeholder="When/where did this come up?"
                  rows={2}
                />
              </div>
              <div className="mm-modal-footer">
                <button type="button" className="mm-btn" onClick={() => setShowAddObjection(false)}>
                  Cancel
                </button>
                <button type="submit" className="mm-btn mm-btn-primary">
                  Log Objection
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Add Task Modal */}
      {showAddTask && (
        <div className="mm-modal-overlay" onClick={() => setShowAddTask(false)}>
          <div className="mm-modal" onClick={(e) => e.stopPropagation()}>
            <div className="mm-modal-header">
              <h2>Create Task</h2>
              <button className="mm-modal-close" onClick={() => setShowAddTask(false)}>×</button>
            </div>
            <form onSubmit={handleCreateTask}>
              <div className="mm-form-group">
                <label>Person ID (optional)</label>
                <input
                  type="text"
                  value={newTask.person_id}
                  onChange={(e) => setNewTask({ ...newTask, person_id: e.target.value })}
                  placeholder="Enter person UUID"
                />
              </div>
              <div className="mm-form-group">
                <label>Title *</label>
                <input
                  type="text"
                  value={newTask.title}
                  onChange={(e) => setNewTask({ ...newTask, title: e.target.value })}
                  required
                  placeholder="What needs to be done?"
                />
              </div>
              <div className="mm-form-group">
                <label>Description</label>
                <textarea
                  value={newTask.description}
                  onChange={(e) => setNewTask({ ...newTask, description: e.target.value })}
                  placeholder="Additional details..."
                  rows={3}
                />
              </div>
              <div className="mm-form-group">
                <label>Priority</label>
                <select
                  value={newTask.priority}
                  onChange={(e) => setNewTask({ ...newTask, priority: e.target.value })}
                >
                  {TASK_PRIORITIES.map((p) => (
                    <option key={p.value} value={p.value}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="mm-form-group">
                <label>Due Date</label>
                <input
                  type="datetime-local"
                  value={newTask.due_at}
                  onChange={(e) => setNewTask({ ...newTask, due_at: e.target.value })}
                />
              </div>
              <div className="mm-modal-footer">
                <button type="button" className="mm-btn" onClick={() => setShowAddTask(false)}>
                  Cancel
                </button>
                <button type="submit" className="mm-btn mm-btn-primary">
                  Create Task
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default RecruitingWorkflow;
