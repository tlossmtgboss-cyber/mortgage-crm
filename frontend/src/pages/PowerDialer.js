import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import './PowerDialer.css';

const API_BASE = process.env.REACT_APP_API_URL || '';

const PowerDialer = () => {
  const navigate = useNavigate();
  const [session, setSession] = useState(null);
  const [currentTask, setCurrentTask] = useState(null);
  const [callStatus, setCallStatus] = useState('idle'); // idle, dialing, ringing, in-progress, disposition
  const [tasks, setTasks] = useState([]);
  const [contacts, setContacts] = useState([]);
  const [activeTab, setActiveTab] = useState('tasks'); // 'tasks' or 'contacts'
  const [selectedTasks, setSelectedTasks] = useState([]);
  const [settings, setSettings] = useState(null);
  const [callLogs, setCallLogs] = useState([]);
  const [showDisposition, setShowDisposition] = useState(false);
  const [dispositionForm, setDispositionForm] = useState({ disposition: '', notes: '', scheduleCallback: null });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const callTimerRef = useRef(null);
  const [callDuration, setCallDuration] = useState(0);

  const getAuthHeaders = () => {
    const token = localStorage.getItem('token');
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    };
  };

  // Fetch dialer settings
  const fetchSettings = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/dialer/settings`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setSettings(data);
      }
    } catch (err) {
      console.error('Error fetching settings:', err);
    }
  }, []);

  // Fetch available tasks for dialing
  const fetchTasks = useCallback(async () => {
    try {
      // Use the dedicated call-tasks endpoint that returns tasks with phone numbers
      const response = await fetch(`${API_BASE}/api/v1/dialer/call-tasks`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        // Tasks already filtered by backend to only include those with phone numbers
        setTasks(data.tasks || []);
      }
    } catch (err) {
      console.error('Error fetching tasks:', err);
    }
  }, []);

  // Fetch all callable contacts (leads and loans with phone numbers)
  const fetchContacts = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/dialer/callable-contacts`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setContacts(data.contacts || []);
      }
    } catch (err) {
      console.error('Error fetching contacts:', err);
    }
  }, []);

  // Check for active session
  const checkActiveSession = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/dialer/sessions/active`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        if (data.active_session) {
          setSession(data.active_session);
          if (data.active_session.current_task) {
            setCurrentTask(data.active_session.current_task);
            setCallStatus('in-progress');
          }
        }
      }
    } catch (err) {
      console.error('Error checking active session:', err);
    }
  }, []);

  // Fetch call logs
  const fetchCallLogs = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/dialer/call-logs?limit=20`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setCallLogs(data.call_logs || []);
      }
    } catch (err) {
      console.error('Error fetching call logs:', err);
    }
  }, []);

  // Initial load
  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await Promise.all([
        fetchSettings(),
        fetchTasks(),
        fetchContacts(),
        checkActiveSession(),
        fetchCallLogs()
      ]);
      setLoading(false);
    };
    init();
  }, [fetchSettings, fetchTasks, fetchContacts, checkActiveSession, fetchCallLogs]);

  // Create new dialer session
  const startSession = async () => {
    if (selectedTasks.length === 0) {
      setError('Please select at least one task');
      return;
    }

    try {
      setLoading(true);
      const response = await fetch(`${API_BASE}/api/v1/dialer/sessions`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ task_ids: selectedTasks })
      });

      if (response.ok) {
        const data = await response.json();
        setSession({ session_id: data.session_id, ...data });
        setSelectedTasks([]);
        // Get first task
        await getNextTask(data.session_id);
      } else {
        const err = await response.json();
        setError(err.detail || 'Failed to start session');
      }
    } catch (err) {
      setError('Error starting session: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  // Get next task in session
  const getNextTask = async (sessionId) => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/dialer/sessions/${sessionId}/next-task`, {
        headers: getAuthHeaders()
      });

      if (response.ok) {
        const data = await response.json();
        if (data.next_task) {
          setCurrentTask(data.next_task);
          setCallStatus('idle');
        } else {
          // No more tasks
          setCurrentTask(null);
          setCallStatus('idle');
          await refreshSession(sessionId);
        }
      }
    } catch (err) {
      console.error('Error getting next task:', err);
    }
  };

  // Initiate call
  const initiateCall = async () => {
    if (!session || !currentTask) return;

    try {
      setCallStatus('dialing');
      const response = await fetch(
        `${API_BASE}/api/v1/dialer/sessions/${session.session_id}/call/${currentTask.id}`,
        {
          method: 'POST',
          headers: getAuthHeaders()
        }
      );

      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          setCallStatus('ringing');
          startCallTimer();
        } else if (data.skipped) {
          // Task was skipped due to compliance
          setError(`Skipped: ${data.issues?.join(', ')}`);
          await getNextTask(session.session_id);
        }
      } else {
        const err = await response.json();
        setError(err.detail || 'Failed to initiate call');
        setCallStatus('idle');
      }
    } catch (err) {
      setError('Error initiating call: ' + err.message);
      setCallStatus('idle');
    }
  };

  // Start call timer
  const startCallTimer = () => {
    setCallDuration(0);
    callTimerRef.current = setInterval(() => {
      setCallDuration(prev => prev + 1);
    }, 1000);
  };

  // Stop call timer
  const stopCallTimer = () => {
    if (callTimerRef.current) {
      clearInterval(callTimerRef.current);
      callTimerRef.current = null;
    }
  };

  // Format duration
  const formatDuration = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // End call (show disposition)
  const endCall = () => {
    stopCallTimer();
    setShowDisposition(true);
    setCallStatus('disposition');
  };

  // Submit disposition
  const submitDisposition = async () => {
    if (!session || !currentTask) return;

    try {
      const response = await fetch(
        `${API_BASE}/api/v1/dialer/sessions/${session.session_id}/tasks/${currentTask.id}/disposition`,
        {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({
            disposition: dispositionForm.disposition,
            notes: dispositionForm.notes,
            schedule_callback: dispositionForm.scheduleCallback
          })
        }
      );

      if (response.ok) {
        setShowDisposition(false);
        setDispositionForm({ disposition: '', notes: '', scheduleCallback: null });
        // Get next task or check if session is complete
        await getNextTask(session.session_id);
        await fetchCallLogs();
      } else {
        const err = await response.json();
        setError(err.detail || 'Failed to save disposition');
      }
    } catch (err) {
      setError('Error saving disposition: ' + err.message);
    }
  };

  // Skip current task
  const skipTask = async () => {
    if (!session || !currentTask) return;

    try {
      const response = await fetch(
        `${API_BASE}/api/v1/dialer/sessions/${session.session_id}/tasks/${currentTask.id}/skip`,
        {
          method: 'POST',
          headers: getAuthHeaders()
        }
      );

      if (response.ok) {
        await getNextTask(session.session_id);
      }
    } catch (err) {
      console.error('Error skipping task:', err);
    }
  };

  // Pause session
  const pauseSession = async () => {
    if (!session) return;

    try {
      const response = await fetch(
        `${API_BASE}/api/v1/dialer/sessions/${session.session_id}/pause`,
        {
          method: 'POST',
          headers: getAuthHeaders()
        }
      );

      if (response.ok) {
        await refreshSession(session.session_id);
      }
    } catch (err) {
      console.error('Error pausing session:', err);
    }
  };

  // Resume session
  const resumeSession = async () => {
    if (!session) return;

    try {
      const response = await fetch(
        `${API_BASE}/api/v1/dialer/sessions/${session.session_id}/resume`,
        {
          method: 'POST',
          headers: getAuthHeaders()
        }
      );

      if (response.ok) {
        await refreshSession(session.session_id);
      }
    } catch (err) {
      console.error('Error resuming session:', err);
    }
  };

  // Stop session
  const stopSession = async () => {
    if (!session) return;

    if (!window.confirm('Are you sure you want to stop this session?')) return;

    try {
      stopCallTimer();
      const response = await fetch(
        `${API_BASE}/api/v1/dialer/sessions/${session.session_id}/stop`,
        {
          method: 'POST',
          headers: getAuthHeaders()
        }
      );

      if (response.ok) {
        setSession(null);
        setCurrentTask(null);
        setCallStatus('idle');
        await fetchTasks();
        await fetchCallLogs();
      }
    } catch (err) {
      console.error('Error stopping session:', err);
    }
  };

  // Refresh session status
  const refreshSession = async (sessionId) => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/dialer/sessions/${sessionId}`, {
        headers: getAuthHeaders()
      });

      if (response.ok) {
        const data = await response.json();
        setSession(data);
      }
    } catch (err) {
      console.error('Error refreshing session:', err);
    }
  };

  // Toggle task selection
  const toggleTaskSelection = (taskId) => {
    setSelectedTasks(prev =>
      prev.includes(taskId)
        ? prev.filter(id => id !== taskId)
        : [...prev, taskId]
    );
  };

  // Select all tasks or contacts based on active tab
  const selectAllTasks = () => {
    const items = activeTab === 'tasks' ? tasks : contacts;
    if (selectedTasks.length === items.length) {
      setSelectedTasks([]);
    } else {
      setSelectedTasks(items.map(t => t.id));
    }
  };

  if (loading && !session) {
    return (
      <div className="power-dialer">
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading Power Dialer...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="power-dialer">
      {/* Header */}
      <div className="dialer-header">
        <div className="header-left">
          <h1>Power Dialer</h1>
          {session && (
            <span className={`session-badge ${session.status}`}>
              Session: {session.status}
            </span>
          )}
        </div>
        <div className="header-right">
          <button
            className="settings-btn"
            onClick={() => navigate('/settings?tab=dialer')}
          >
            Settings
          </button>
        </div>
      </div>

      {/* Error message */}
      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <button onClick={() => setError(null)}>×</button>
        </div>
      )}

      {/* Settings check */}
      {!settings?.business_caller_id && (
        <div className="warning-banner">
          <span>⚠️ No caller ID configured. Please set up your business phone number in settings.</span>
          <button onClick={() => navigate('/settings?tab=dialer')}>Configure</button>
        </div>
      )}

      <div className="dialer-content">
        {/* Left panel - Task Selection / Session Progress */}
        <div className="dialer-left-panel">
          {!session ? (
            <>
              {/* Tab Navigation */}
              <div className="dialer-tabs">
                <button
                  className={`dialer-tab ${activeTab === 'tasks' ? 'active' : ''}`}
                  onClick={() => { setActiveTab('tasks'); setSelectedTasks([]); }}
                >
                  Call Tasks ({tasks.length})
                </button>
                <button
                  className={`dialer-tab ${activeTab === 'contacts' ? 'active' : ''}`}
                  onClick={() => { setActiveTab('contacts'); setSelectedTasks([]); }}
                >
                  All Contacts ({contacts.length})
                </button>
              </div>

              <div className="panel-header">
                <h2>{activeTab === 'tasks' ? 'Select Tasks to Dial' : 'Select Contacts to Dial'}</h2>
                <button
                  className="select-all-btn"
                  onClick={selectAllTasks}
                >
                  {selectedTasks.length === (activeTab === 'tasks' ? tasks : contacts).length ? 'Deselect All' : 'Select All'}
                </button>
              </div>

              <div className="task-list">
                {activeTab === 'tasks' ? (
                  // Tasks tab
                  tasks.length === 0 ? (
                    <div className="empty-state">
                      <p>No call tasks available</p>
                      <p className="empty-hint">Switch to "All Contacts" to dial leads or borrowers directly</p>
                    </div>
                  ) : (
                    tasks.map(task => (
                      <div
                        key={task.id}
                        className={`task-item ${selectedTasks.includes(task.id) ? 'selected' : ''}`}
                        onClick={() => toggleTaskSelection(task.id)}
                      >
                        <input
                          type="checkbox"
                          checked={selectedTasks.includes(task.id)}
                          onChange={() => {}}
                        />
                        <div className="task-info">
                          <span className="task-title">{task.title}</span>
                          <span className="task-contact">
                            {task.contact_name || task.lead_name || task.loan_borrower_name || 'Unknown'}
                          </span>
                          <span className="task-phone">
                            {task.contact_phone || task.lead_phone || task.loan_borrower_phone}
                          </span>
                        </div>
                      </div>
                    ))
                  )
                ) : (
                  // Contacts tab
                  contacts.length === 0 ? (
                    <div className="empty-state">
                      <p>No contacts with phone numbers found</p>
                    </div>
                  ) : (
                    contacts.map(contact => (
                      <div
                        key={contact.id}
                        className={`task-item ${selectedTasks.includes(contact.id) ? 'selected' : ''}`}
                        onClick={() => toggleTaskSelection(contact.id)}
                      >
                        <input
                          type="checkbox"
                          checked={selectedTasks.includes(contact.id)}
                          onChange={() => {}}
                        />
                        <div className="task-info">
                          <span className="task-title">{contact.contact_name}</span>
                          <span className={`task-type-badge ${contact.entity_type}`}>
                            {contact.entity_type === 'lead' ? 'Lead' : 'Loan'}
                          </span>
                          <span className="task-phone">{contact.contact_phone}</span>
                          {contact.stage && <span className="task-stage">{contact.stage}</span>}
                        </div>
                      </div>
                    ))
                  )
                )}
              </div>

              <div className="panel-footer">
                <button
                  className="start-session-btn"
                  onClick={startSession}
                  disabled={selectedTasks.length === 0 || !settings?.business_caller_id}
                >
                  Start Power Dialer ({selectedTasks.length} {activeTab === 'tasks' ? 'tasks' : 'contacts'})
                </button>
              </div>
            </>
          ) : (
            <>
              <div className="panel-header">
                <h2>Session Progress</h2>
              </div>

              <div className="session-stats">
                <div className="stat">
                  <span className="stat-value">{session.completed_tasks || 0}</span>
                  <span className="stat-label">Completed</span>
                </div>
                <div className="stat">
                  <span className="stat-value">{session.pending_tasks || 0}</span>
                  <span className="stat-label">Remaining</span>
                </div>
                <div className="stat">
                  <span className="stat-value">{session.no_answer_tasks || 0}</span>
                  <span className="stat-label">No Answer</span>
                </div>
                <div className="stat">
                  <span className="stat-value">{session.skipped_tasks || 0}</span>
                  <span className="stat-label">Skipped</span>
                </div>
              </div>

              <div className="progress-bar">
                <div
                  className="progress-fill"
                  style={{
                    width: `${((session.completed_tasks || 0) / (session.total_tasks || 1)) * 100}%`
                  }}
                />
              </div>

              <div className="session-controls">
                {session.status === 'active' ? (
                  <button className="pause-btn" onClick={pauseSession}>
                    Pause Session
                  </button>
                ) : session.status === 'paused' ? (
                  <button className="resume-btn" onClick={resumeSession}>
                    Resume Session
                  </button>
                ) : null}
                <button className="stop-btn" onClick={stopSession}>
                  Stop Session
                </button>
              </div>
            </>
          )}
        </div>

        {/* Center panel - Active Call */}
        <div className="dialer-center-panel">
          {session && currentTask ? (
            <div className="active-call-card">
              <div className="call-header">
                <span className={`call-status ${callStatus}`}>
                  {callStatus === 'idle' && 'Ready to call'}
                  {callStatus === 'dialing' && 'Dialing...'}
                  {callStatus === 'ringing' && 'Ringing...'}
                  {callStatus === 'in-progress' && 'On Call'}
                  {callStatus === 'disposition' && 'Enter Disposition'}
                </span>
                {(callStatus === 'ringing' || callStatus === 'in-progress') && (
                  <span className="call-timer">{formatDuration(callDuration)}</span>
                )}
              </div>

              <div className="contact-info">
                <div className="contact-avatar">
                  {(currentTask.contact_name || 'U')[0].toUpperCase()}
                </div>
                <h3>{currentTask.contact_name || 'Unknown Contact'}</h3>
                <p className="phone-number">{currentTask.contact_phone}</p>
                {currentTask.lead_id && (
                  <span className="contact-type lead">Lead</span>
                )}
                {currentTask.loan_id && (
                  <span className="contact-type loan">Loan</span>
                )}
              </div>

              {!showDisposition ? (
                <div className="call-actions">
                  {callStatus === 'idle' && (
                    <>
                      <button className="dial-btn" onClick={initiateCall}>
                        <span className="icon">📞</span>
                        Dial
                      </button>
                      <button className="skip-btn" onClick={skipTask}>
                        Skip
                      </button>
                    </>
                  )}
                  {(callStatus === 'ringing' || callStatus === 'in-progress') && (
                    <button className="hangup-btn" onClick={endCall}>
                      <span className="icon">📵</span>
                      End Call
                    </button>
                  )}
                </div>
              ) : (
                <div className="disposition-form">
                  <h4>Call Disposition</h4>
                  <select
                    value={dispositionForm.disposition}
                    onChange={(e) => setDispositionForm({...dispositionForm, disposition: e.target.value})}
                  >
                    <option value="">Select disposition...</option>
                    <option value="connected">Connected - Spoke with contact</option>
                    <option value="voicemail">Left Voicemail</option>
                    <option value="callback_scheduled">Callback Scheduled</option>
                    <option value="not_interested">Not Interested</option>
                    <option value="wrong_number">Wrong Number</option>
                    <option value="do_not_call">Do Not Call Request</option>
                  </select>

                  {dispositionForm.disposition === 'callback_scheduled' && (
                    <input
                      type="datetime-local"
                      value={dispositionForm.scheduleCallback || ''}
                      onChange={(e) => setDispositionForm({...dispositionForm, scheduleCallback: e.target.value})}
                      placeholder="Schedule callback"
                    />
                  )}

                  <textarea
                    placeholder="Notes (optional)"
                    value={dispositionForm.notes}
                    onChange={(e) => setDispositionForm({...dispositionForm, notes: e.target.value})}
                    rows={3}
                  />

                  <div className="disposition-actions">
                    <button
                      className="save-btn"
                      onClick={submitDisposition}
                      disabled={!dispositionForm.disposition}
                    >
                      Save & Next
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : session ? (
            <div className="no-tasks-state">
              <h3>Session Complete</h3>
              <p>All tasks have been processed</p>
              <button onClick={stopSession}>Close Session</button>
            </div>
          ) : (
            <div className="no-session-state">
              <div className="dialer-illustration">
                <span className="big-icon">📞</span>
              </div>
              <h3>No Active Session</h3>
              <p>Select tasks from the left panel to start a dialing session</p>
            </div>
          )}
        </div>

        {/* Right panel - Call History */}
        <div className="dialer-right-panel">
          <div className="panel-header">
            <h2>Recent Calls</h2>
          </div>

          <div className="call-logs">
            {callLogs.length === 0 ? (
              <div className="empty-state">
                <p>No recent calls</p>
              </div>
            ) : (
              callLogs.map(log => (
                <div key={log.id} className="call-log-item">
                  <div className="log-icon">
                    {log.outcome === 'completed' ? '✅' :
                     log.outcome === 'no-answer' ? '📵' :
                     log.outcome === 'busy' ? '⏸️' : '❌'}
                  </div>
                  <div className="log-info">
                    <span className="log-name">{log.contact_name || 'Unknown'}</span>
                    <span className="log-phone">{log.contact_phone}</span>
                    <span className="log-time">
                      {log.started_at && new Date(log.started_at).toLocaleString()}
                    </span>
                  </div>
                  <div className="log-duration">
                    {log.duration_seconds ? formatDuration(log.duration_seconds) : '--:--'}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default PowerDialer;
