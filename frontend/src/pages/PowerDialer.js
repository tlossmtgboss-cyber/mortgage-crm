import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { getAuthHeaders } from '../utils/auth';
import './PowerDialer.css';

const API_BASE = process.env.REACT_APP_API_URL || '';

// Dial Pad Component
const DialPad = ({ onDigitPress, disabled }) => {
  const digits = [
    { num: '1', letters: '' },
    { num: '2', letters: 'ABC' },
    { num: '3', letters: 'DEF' },
    { num: '4', letters: 'GHI' },
    { num: '5', letters: 'JKL' },
    { num: '6', letters: 'MNO' },
    { num: '7', letters: 'PQRS' },
    { num: '8', letters: 'TUV' },
    { num: '9', letters: 'WXYZ' },
    { num: '*', letters: '' },
    { num: '0', letters: '+' },
    { num: '#', letters: '' },
  ];

  return (
    <div className="dial-pad">
      {digits.map(({ num, letters }) => (
        <button
          key={num}
          className="dial-pad-btn"
          onClick={() => onDigitPress(num)}
          disabled={disabled}
        >
          <span className="dial-num">{num}</span>
          {letters && <span className="dial-letters">{letters}</span>}
        </button>
      ))}
    </div>
  );
};

// Phone Input Component
const PhoneInput = ({ label, value, onChange, onDial, onSms, highlight }) => (
  <div className={`phone-input-group ${highlight ? 'highlight' : ''}`}>
    <label>{label}</label>
    <div className="phone-input-row">
      <input
        type="tel"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="(___) ___-____"
      />
      <button className="phone-action-btn dial" onClick={onDial} title="Dial">
        📞
      </button>
      <button className="phone-action-btn sms" onClick={onSms} title="SMS">
        💬
      </button>
    </div>
  </div>
);

// Call Control Button Component
const CallControlBtn = ({ icon, label, onClick, variant = 'default', active, disabled }) => (
  <button
    className={`call-control-btn ${variant} ${active ? 'active' : ''}`}
    onClick={onClick}
    disabled={disabled}
  >
    <span className="control-icon">{icon}</span>
    <span className="control-label">{label}</span>
  </button>
);

// Disposition Button Component
const DispositionBtn = ({ label, variant, onClick, active }) => (
  <button
    className={`disposition-btn ${variant} ${active ? 'active' : ''}`}
    onClick={onClick}
  >
    {label}
  </button>
);

// Call Note Entry Component
const CallNoteEntry = ({ note }) => (
  <div className="call-note-entry">
    <p className="note-text">{note.text}</p>
    <span className="note-timestamp">{note.timestamp}</span>
  </div>
);

const PowerDialer = () => {
  const navigate = useNavigate();
  const [session, setSession] = useState(null);
  const [currentTask, setCurrentTask] = useState(null);
  const [callStatus, setCallStatus] = useState('idle');
  const [tasks, setTasks] = useState([]);
  const [contacts, setContacts] = useState([]);
  const [activeTab, setActiveTab] = useState('tasks');
  const [selectedTasks, setSelectedTasks] = useState([]);
  const [settings, setSettings] = useState(null);
  const [callLogs, setCallLogs] = useState([]);
  const [showDisposition, setShowDisposition] = useState(false);
  const [dispositionForm, setDispositionForm] = useState({ disposition: '', notes: '', scheduleCallback: null });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const callTimerRef = useRef(null);
  const [callDuration, setCallDuration] = useState(0);

  // New states for enhanced dialer
  const [phoneNumbers, setPhoneNumbers] = useState({ cell: '', home: '', work: '' });
  const [activePhoneType, setActivePhoneType] = useState('cell');
  const [isHold, setIsHold] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [scriptTab, setScriptTab] = useState('script'); // 'script', 'interaction', 'activities'
  const [callNote, setCallNote] = useState('');
  const [callNotes, setCallNotes] = useState([]);
  const [sessionStats, setSessionStats] = useState({
    calls: 0,
    talks: 0,
    emails: 0,
    voicemails: 0
  });

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
      const response = await fetch(`${API_BASE}/api/v1/dialer/call-tasks`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setTasks(data.tasks || []);
      }
    } catch (err) {
      console.error('Error fetching tasks:', err);
    }
  }, []);

  // Fetch all callable contacts
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

  // Update phone numbers when current task changes
  useEffect(() => {
    if (currentTask) {
      setPhoneNumbers({
        cell: currentTask.contact_phone || currentTask.lead_phone || currentTask.loan_borrower_phone || '',
        home: currentTask.home_phone || '',
        work: currentTask.work_phone || ''
      });
    }
  }, [currentTask]);

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
        if (data.success) {
          setSession({ session_id: data.session_id, ...data });
          setSelectedTasks([]);
          await getNextTask(data.session_id);
        } else {
          setError(data.error || 'Failed to start session');
        }
      } else {
        const err = await response.json();
        setError(err.detail || err.error || 'Failed to start session');
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
          setCallNotes([]);
          setCallNote('');
        } else {
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
  const initiateCall = async (phoneType = activePhoneType) => {
    if (!session || !currentTask) return;
    const phoneNumber = phoneNumbers[phoneType];
    if (!phoneNumber) {
      setError(`No ${phoneType} phone number available`);
      return;
    }

    try {
      setCallStatus('dialing');
      setActivePhoneType(phoneType);
      const response = await fetch(
        `${API_BASE}/api/v1/dialer/sessions/${session.session_id}/call/${currentTask.id}`,
        {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({ phone_number: phoneNumber })
        }
      );

      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          setCallStatus('ringing');
          startCallTimer();
          setSessionStats(prev => ({ ...prev, calls: prev.calls + 1 }));
        } else if (data.skipped) {
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
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  // End call (show disposition)
  const endCall = () => {
    stopCallTimer();
    setShowDisposition(true);
    setCallStatus('disposition');
  };

  // Quick disposition
  const quickDisposition = async (disposition) => {
    if (!session || !currentTask) return;

    try {
      const response = await fetch(
        `${API_BASE}/api/v1/dialer/sessions/${session.session_id}/tasks/${currentTask.id}/disposition`,
        {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({
            disposition: disposition,
            notes: callNotes.map(n => n.text).join('\n'),
            schedule_callback: dispositionForm.scheduleCallback
          })
        }
      );

      if (response.ok) {
        if (disposition === 'connected') {
          setSessionStats(prev => ({ ...prev, talks: prev.talks + 1 }));
        } else if (disposition === 'voicemail') {
          setSessionStats(prev => ({ ...prev, voicemails: prev.voicemails + 1 }));
        }
        setShowDisposition(false);
        setDispositionForm({ disposition: '', notes: '', scheduleCallback: null });
        stopCallTimer();
        setCallStatus('idle');
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
        setSessionStats({ calls: 0, talks: 0, emails: 0, voicemails: 0 });
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

  // Select all tasks
  const selectAllTasks = () => {
    const items = activeTab === 'tasks' ? tasks : contacts;
    if (selectedTasks.length === items.length) {
      setSelectedTasks([]);
    } else {
      setSelectedTasks(items.map(t => t.id));
    }
  };

  // Add call note
  const addCallNote = () => {
    if (!callNote.trim()) return;
    const newNote = {
      id: Date.now(),
      text: callNote,
      timestamp: new Date().toLocaleString()
    };
    setCallNotes(prev => [...prev, newNote]);
    setCallNote('');
  };

  // Handle digit press from dial pad
  const handleDigitPress = (digit) => {
    // In a real implementation, this would send DTMF tones
    console.log('Digit pressed:', digit);
  };

  // Get current time
  const getCurrentTime = () => {
    return new Date().toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      timeZoneName: 'short'
    });
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
              {session.status === 'active' ? '● Live' : session.status}
            </span>
          )}
        </div>
        <div className="header-actions">
          <button className="header-btn" onClick={() => navigate('/settings?tab=dialer')}>
            ⚙️ Settings
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

      {/* Main Content */}
      {!session ? (
        /* Pre-Session: Task Selection */
        <div className="pre-session-layout">
          <div className="task-selection-panel">
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
              <button className="select-all-btn" onClick={selectAllTasks}>
                {selectedTasks.length === (activeTab === 'tasks' ? tasks : contacts).length ? 'Deselect All' : 'Select All'}
              </button>
            </div>

            <div className="task-list">
              {activeTab === 'tasks' ? (
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
                🚀 Start Power Dialer ({selectedTasks.length} {activeTab === 'tasks' ? 'tasks' : 'contacts'})
              </button>
            </div>
          </div>

          {/* Recent Calls Preview */}
          <div className="recent-calls-preview">
            <h3>Recent Calls</h3>
            <div className="call-logs-mini">
              {callLogs.slice(0, 5).map(log => (
                <div key={log.id} className="call-log-mini-item">
                  <span className="log-status-icon">
                    {log.outcome === 'completed' ? '✅' : log.outcome === 'no-answer' ? '📵' : '❌'}
                  </span>
                  <span className="log-contact">{log.contact_name || 'Unknown'}</span>
                  <span className="log-duration-mini">
                    {log.duration_seconds ? formatDuration(log.duration_seconds) : '--:--'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        /* Active Session: Dial Interface */
        <div className="dial-session-layout">
          {/* Dial Session Header */}
          <div className="dial-session-header">
            <div className="session-title">
              <h2>Dial Session</h2>
              <span className="contact-counter">
                Contacts: {session.completed_tasks || 0} of {session.total_tasks || 0}
              </span>
            </div>
            <div className="session-header-actions">
              <button className="session-action-btn" title="Actions">
                ▼ Actions
              </button>
              <button className="nav-btn" onClick={skipTask} disabled={!currentTask}>‹</button>
              <button className="nav-btn" onClick={() => getNextTask(session.session_id)}>›</button>
            </div>
          </div>

          <div className="dial-session-content">
            {/* Left Column: Controls & Dial Pad */}
            <div className="dial-controls-column">
              {/* Phone Number Inputs */}
              <div className="phone-inputs-section">
                <PhoneInput
                  label="Cell Phone"
                  value={phoneNumbers.cell}
                  onChange={(val) => setPhoneNumbers(prev => ({ ...prev, cell: val }))}
                  onDial={() => initiateCall('cell')}
                  onSms={() => {}}
                  highlight={activePhoneType === 'cell' && callStatus !== 'idle'}
                />
                <PhoneInput
                  label="Home Phone"
                  value={phoneNumbers.home}
                  onChange={(val) => setPhoneNumbers(prev => ({ ...prev, home: val }))}
                  onDial={() => initiateCall('home')}
                  onSms={() => {}}
                  highlight={activePhoneType === 'home' && callStatus !== 'idle'}
                />
                <PhoneInput
                  label="Work Phone"
                  value={phoneNumbers.work}
                  onChange={(val) => setPhoneNumbers(prev => ({ ...prev, work: val }))}
                  onDial={() => initiateCall('work')}
                  onSms={() => {}}
                  highlight={activePhoneType === 'work' && callStatus !== 'idle'}
                />
              </div>

              {/* Call Control Buttons */}
              <div className="call-controls-section">
                <div className="call-controls-row">
                  <CallControlBtn
                    icon="⏸"
                    label="Hold"
                    onClick={() => setIsHold(!isHold)}
                    active={isHold}
                    disabled={callStatus === 'idle'}
                  />
                  <CallControlBtn
                    icon="🔇"
                    label="Mute"
                    onClick={() => setIsMuted(!isMuted)}
                    active={isMuted}
                    disabled={callStatus === 'idle'}
                  />
                </div>
                <CallControlBtn
                  icon="📵"
                  label="Hangup the Call"
                  onClick={endCall}
                  variant="hangup"
                  disabled={callStatus === 'idle'}
                />
                <CallControlBtn
                  icon="🎤"
                  label="Play Voice Mail"
                  onClick={() => {}}
                  variant="voicemail"
                  disabled={callStatus === 'idle'}
                />
                <div className="session-control-btns">
                  {session.status === 'active' ? (
                    <CallControlBtn
                      icon="⏸"
                      label="Pause Dialing Session"
                      onClick={pauseSession}
                      variant="pause"
                    />
                  ) : (
                    <CallControlBtn
                      icon="▶"
                      label="Resume Dialing Session"
                      onClick={resumeSession}
                      variant="resume"
                    />
                  )}
                  <CallControlBtn
                    icon="⏹"
                    label="End Dialing Session"
                    onClick={stopSession}
                    variant="end"
                  />
                </div>
              </div>

              {/* Dial Pad */}
              <DialPad
                onDigitPress={handleDigitPress}
                disabled={callStatus === 'idle'}
              />
            </div>

            {/* Center Column: Script & Dispositions */}
            <div className="script-column">
              {/* Script Tabs */}
              <div className="script-tabs">
                <button
                  className={`script-tab ${scriptTab === 'interaction' ? 'active' : ''}`}
                  onClick={() => setScriptTab('interaction')}
                >
                  Interaction
                </button>
                <button
                  className={`script-tab ${scriptTab === 'script' ? 'active' : ''}`}
                  onClick={() => setScriptTab('script')}
                >
                  Phone Scripts
                </button>
                <button
                  className={`script-tab ${scriptTab === 'activities' ? 'active' : ''}`}
                  onClick={() => setScriptTab('activities')}
                >
                  Activities
                </button>
              </div>

              {/* Script Content */}
              <div className="script-content">
                {scriptTab === 'script' && (
                  <div className="phone-script">
                    <p>Hi <strong>{currentTask?.contact_name?.split(' ')[0] || 'there'}</strong>, this is <strong>[Your Name]</strong> from <strong>[Company]</strong>.</p>
                    <p>I'm getting back with you because you expressed an interest in our mortgage services.</p>
                    <p>I wanted to give you a quick call to find out how I may be of service.</p>
                    <p>I know you weren't expecting my phone call, could I confirm your email address and shoot you over a quick link to our website?</p>
                    <p>Our website will give you all the details if you'd like to check it out...</p>
                    <p>Would it be OK for me to give you a follow-up call to see if you have any questions?</p>
                    <p><em>Great, thank you for your time.</em></p>
                  </div>
                )}
                {scriptTab === 'interaction' && (
                  <div className="interaction-content">
                    <div className="contact-card">
                      <div className="contact-avatar-large">
                        {(currentTask?.contact_name || 'U')[0].toUpperCase()}
                      </div>
                      <h3>{currentTask?.contact_name || 'Unknown Contact'}</h3>
                      <p className="contact-phone-display">{phoneNumbers.cell || phoneNumbers.home || phoneNumbers.work || 'No phone'}</p>
                      {currentTask?.lead_id && <span className="contact-badge lead">Lead</span>}
                      {currentTask?.loan_id && <span className="contact-badge loan">Loan</span>}
                    </div>
                  </div>
                )}
                {scriptTab === 'activities' && (
                  <div className="activities-content">
                    <p className="empty-activities">No recent activities for this contact</p>
                  </div>
                )}
              </div>

              {/* Disposition Buttons */}
              <div className="disposition-buttons">
                <div className="disposition-row primary">
                  <DispositionBtn
                    label="Live Answer"
                    variant="success"
                    onClick={() => quickDisposition('connected')}
                  />
                  <DispositionBtn
                    label="Voice Mail"
                    variant="default"
                    onClick={() => quickDisposition('voicemail')}
                  />
                  <DispositionBtn
                    label="Follow up VM"
                    variant="default"
                    onClick={() => quickDisposition('followup_vm')}
                  />
                  <DispositionBtn
                    label="Leave English VM"
                    variant="default"
                    onClick={() => quickDisposition('english_vm')}
                  />
                </div>
                <div className="disposition-row secondary">
                  <DispositionBtn
                    label="Leave Spanish VM"
                    variant="outline"
                    onClick={() => quickDisposition('spanish_vm')}
                  />
                  <DispositionBtn
                    label="Left Live Voice Mail"
                    variant="outline"
                    onClick={() => quickDisposition('left_vm')}
                  />
                  <DispositionBtn
                    label="No Answer"
                    variant="outline"
                    onClick={() => quickDisposition('no_answer')}
                  />
                </div>
                <div className="disposition-row tertiary">
                  <DispositionBtn
                    label="Busy Signal"
                    variant="dark"
                    onClick={() => quickDisposition('busy')}
                  />
                  <DispositionBtn
                    label="Bad Number"
                    variant="dark"
                    onClick={() => quickDisposition('bad_number')}
                  />
                </div>
              </div>
            </div>

            {/* Right Column: Notes & Activity Log */}
            <div className="notes-column">
              <div className="call-note-section">
                <h3>Call Note</h3>
                <div className="note-input-area">
                  <textarea
                    value={callNote}
                    onChange={(e) => setCallNote(e.target.value)}
                    placeholder="Add Content"
                    rows={4}
                  />
                  <div className="note-toolbar">
                    <button title="Bold">B</button>
                    <button title="Italic">I</button>
                    <button title="Underline">U</button>
                    <button title="List">≡</button>
                    <button title="Link">🔗</button>
                  </div>
                  <button className="add-note-btn" onClick={addCallNote}>
                    Add Note
                  </button>
                </div>
              </div>

              <div className="activity-log-section">
                <h3>Activity Log</h3>
                <div className="activity-log">
                  {callNotes.length === 0 ? (
                    <p className="empty-log">No notes yet for this call</p>
                  ) : (
                    callNotes.map(note => (
                      <CallNoteEntry key={note.id} note={note} />
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Footer Stats Bar */}
          <div className="dial-session-footer">
            <div className="footer-stat">
              <span className="footer-label">Caller ID</span>
              <span className="footer-value">{settings?.business_caller_id || '(000)000-0000'}</span>
            </div>
            <div className="footer-stat">
              <span className="footer-label">Duration</span>
              <span className="footer-value">{formatDuration(callDuration)}</span>
            </div>
            <div className="footer-stat">
              <span className="footer-label">Contacts</span>
              <span className="footer-value">{session.completed_tasks || 0} of {session.total_tasks || 0}</span>
            </div>
            <div className="footer-stat">
              <span className="footer-label">Calls</span>
              <span className="footer-value">{sessionStats.calls}</span>
            </div>
            <div className="footer-stat">
              <span className="footer-label">Talks</span>
              <span className="footer-value">{sessionStats.talks}</span>
            </div>
            <div className="footer-stat">
              <span className="footer-label">Emails</span>
              <span className="footer-value">{sessionStats.emails}</span>
            </div>
            <div className="footer-stat">
              <span className="footer-label">Voicemails</span>
              <span className="footer-value">{sessionStats.voicemails}</span>
            </div>
            <div className="footer-stat recording">
              <span className="rec-indicator">●</span>
              <span className="footer-label">Rec</span>
            </div>
            <div className="footer-stat">
              <span className="footer-value time">{getCurrentTime()}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default PowerDialer;
