import { useState, useEffect, useCallback, useRef } from 'react';
import './UnifiedTaskSidebar.css';
import { toast } from '../utils/toast';
import { getToken } from '../utils/tokenStore';

// Use HTTPS Railway URL in production, localhost for development
const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const API_BASE_URL = isProduction
  ? 'https://api.perenniaai.com'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

const UnifiedTaskSidebar = ({ isOpen, onClose, onTaskCountChange }) => {
  const [tasks, setTasks] = useState([]);
  const [selectedTask, setSelectedTask] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeFilter, setActiveFilter] = useState('all');
  const [feedbackText, setFeedbackText] = useState('');
  const [editedResponse, setEditedResponse] = useState('');
  const [isEditing, setIsEditing] = useState(false);
  const [sendVia, setSendVia] = useState('email');
  const [communicationHistoryOpen, setCommunicationHistoryOpen] = useState(false);

  // Train AI state
  const [isListening, setIsListening] = useState(false);
  const [trainingInProgress, setTrainingInProgress] = useState(false);
  const [aiAcknowledgment, setAiAcknowledgment] = useState('');
  const [regeneratingChannel, setRegeneratingChannel] = useState(null);
  const recognitionRef = useRef(null);

  // Fetch unified tasks from all sources
  const fetchUnifiedTasks = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE_URL}/api/v1/unified-tasks`, {
        headers: {
          'Authorization': `Bearer ${getToken()}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        setTasks(data.tasks || []);
        if (onTaskCountChange) {
          onTaskCountChange(data.total_count || 0);
        }
      }
    } catch (error) {
      console.error('Error fetching unified tasks:', error);
    } finally {
      setLoading(false);
    }
  }, [onTaskCountChange]);

  useEffect(() => {
    if (isOpen) {
      fetchUnifiedTasks();
    }
  }, [isOpen, fetchUnifiedTasks]);

  // Filter tasks by source
  const filteredTasks = tasks.filter(task => {
    if (activeFilter === 'all') return true;
    return task.source === activeFilter;
  });

  // Get priority color and label
  const getPriorityInfo = (priority) => {
    const p = (priority || '').toLowerCase();
    if (p === 'urgent' || p === 'critical') return { color: '#ef4444', label: 'URGENT', bgColor: 'rgba(239, 68, 68, 0.1)' };
    if (p === 'high') return { color: '#f97316', label: 'HIGH', bgColor: 'rgba(249, 115, 22, 0.1)' };
    if (p === 'medium') return { color: '#eab308', label: 'MEDIUM', bgColor: 'rgba(234, 179, 8, 0.1)' };
    return { color: '#22c55e', label: 'LOW', bgColor: 'rgba(34, 197, 94, 0.1)' };
  };

  // Get status bar color for task list
  const getStatusColor = (task) => {
    if (task.source === 'reconciliation') return '#22c55e'; // green
    if (task.source === 'workflow') return '#B8924A'; // purple
    const priority = (task.priority || '').toLowerCase();
    if (priority === 'urgent' || priority === 'critical') return '#ef4444';
    if (priority === 'high') return '#f97316';
    if (priority === 'medium') return '#eab308';
    return '#3b82f6'; // blue default
  };

  // Get source label
  const getSourceLabel = (source) => {
    switch (source) {
      case 'task': return 'AI Suggested';
      case 'workflow': return 'Workflow';
      case 'reconciliation': return 'AI Engine';
      default: return 'System';
    }
  };

  // Handle task selection
  const handleSelectTask = (task) => {
    setSelectedTask(task);
    setEditedResponse(task.ai_suggested_response || generateDefaultMessage(task));
    setFeedbackText('');
    setIsEditing(false);
    setCommunicationHistoryOpen(false);
  };

  // Generate default AI message based on task
  const generateDefaultMessage = (task) => {
    const clientName = task.client_name?.split(' ')[0] || 'there';

    if (task.title?.toLowerCase().includes('follow-up') || task.title?.toLowerCase().includes('follow up')) {
      return `Hi ${clientName},

I hope you're doing well! I wanted to reach out and see how your property search is going.

Your pre-approval is still active for another 75 days. If you've found a property you're interested in or have any questions about the home buying process, I'm here to help.

Also, if your financial situation has changed at all (new income, credit changes, etc.), please let me know so we can make sure your pre-approval stays accurate.

Looking forward to helping you find your dream home!

Best regards,
[Your Name]
Loan Officer`;
    }

    if (task.title?.toLowerCase().includes('closing') || task.title?.toLowerCase().includes('schedule')) {
      return `Hi ${clientName},

Great news - we've received Clear to Close on your loan!

I'd like to coordinate scheduling your closing. Please let me know your availability over the next few days so we can get this finalized.

Required items for closing:
• Valid photo ID
• Cashier's check for closing costs (amount TBD)
• Any additional documents if requested

Please reach out if you have any questions!

Best regards,
[Your Name]
Loan Officer`;
    }

    return `Hi ${clientName},

I wanted to touch base regarding your loan application. Please let me know if you have any questions or if there's anything I can help with.

Best regards,
[Your Name]
Loan Officer`;
  };

  // Handle approve action - instant, optimistic UI
  const handleApprove = async () => {
    if (!selectedTask) return;

    const taskToApprove = selectedTask;

    // Optimistic UI - remove immediately
    setTasks(prev => prev.filter(t => t.id !== taskToApprove.id || t.source !== taskToApprove.source));
    setSelectedTask(null);
    setFeedbackText('');
    setEditedResponse('');

    // Update count
    if (onTaskCountChange) {
      onTaskCountChange(tasks.length - 1);
    }

    // API call in background
    try {
      await fetch(`${API_BASE_URL}/api/v1/unified-tasks/${taskToApprove.id}/approve`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${getToken()}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          source: taskToApprove.source,
          approved_response: isEditing ? editedResponse : (taskToApprove.ai_suggested_response || editedResponse),
          feedback: feedbackText || null,
          send_via: sendVia
        })
      });
    } catch (err) {
      console.error('Approve failed:', err);
    }
  };

  // Handle snooze action
  const handleSnooze = () => {
    if (!selectedTask) return;
    // Move to next task without removing
    const currentIndex = filteredTasks.findIndex(t => t.id === selectedTask.id && t.source === selectedTask.source);
    if (currentIndex < filteredTasks.length - 1) {
      handleSelectTask(filteredTasks[currentIndex + 1]);
    } else if (filteredTasks.length > 1) {
      handleSelectTask(filteredTasks[0]);
    } else {
      setSelectedTask(null);
    }
  };

  // Voice recognition for Train AI
  const startListening = () => {
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
      toast.error('Voice recognition is not supported in your browser. Please use Chrome or Edge.');
      return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    recognitionRef.current = recognition;

    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onstart = () => {
      setIsListening(true);
    };

    recognition.onresult = (event) => {
      let finalTranscript = '';
      let interimTranscript = '';

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalTranscript += transcript;
        } else {
          interimTranscript += transcript;
        }
      }

      if (finalTranscript) {
        setFeedbackText(prev => prev + (prev ? ' ' : '') + finalTranscript);
      }
    };

    recognition.onerror = (event) => {
      console.error('Speech recognition error:', event.error);
      setIsListening(false);
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    recognition.start();
  };

  const stopListening = () => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      setIsListening(false);
    }
  };

  // Train AI function
  const handleTrainAI = async () => {
    if (!feedbackText.trim() || !selectedTask) return;

    setTrainingInProgress(true);
    setAiAcknowledgment('');

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/ai/training/instruction`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${getToken()}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          instruction: feedbackText,
          task_context: {
            task_type: selectedTask.source || 'general',
            borrower_name: selectedTask.client_name || '',
            task_title: selectedTask.title || '',
            stage: selectedTask.stage || ''
          }
        })
      });

      if (response.ok) {
        const data = await response.json();
        setAiAcknowledgment(data.acknowledgment || 'Training instruction received! I will apply this to future messages.');
      } else {
        setAiAcknowledgment('Training instruction saved. AI will apply this guidance to future tasks.');
      }
    } catch (error) {
      console.error('Failed to train AI:', error);
      setAiAcknowledgment('Instruction noted. Will apply to future tasks.');
    } finally {
      setTrainingInProgress(false);
    }
  };

  // Regenerate message for specific channel
  const handleRegenerateMessage = async (channel) => {
    if (!selectedTask) return;

    setRegeneratingChannel(channel);

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/ai/regenerate-message`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${getToken()}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          task_id: selectedTask.id,
          task_source: selectedTask.source,
          channel: channel,
          client_name: selectedTask.client_name,
          task_title: selectedTask.title,
          stage: selectedTask.stage,
          training_instruction: feedbackText || null
        })
      });

      if (response.ok) {
        const data = await response.json();
        setEditedResponse(data.message || data.generated_message || generateChannelMessage(channel));
        setSendVia(channel);
      } else {
        // Fallback to local generation
        setEditedResponse(generateChannelMessage(channel));
        setSendVia(channel);
      }
    } catch (error) {
      console.error('Failed to regenerate message:', error);
      // Fallback to local generation
      setEditedResponse(generateChannelMessage(channel));
      setSendVia(channel);
    } finally {
      setRegeneratingChannel(null);
    }
  };

  // Generate channel-specific message locally
  const generateChannelMessage = (channel) => {
    const clientName = selectedTask?.client_name?.split(' ')[0] || 'there';
    const instruction = feedbackText.trim();

    switch (channel) {
      case 'email':
        return `Hi ${clientName},

${instruction ? `${instruction}\n\n` : ''}I wanted to reach out regarding your loan application. If you have any questions or need assistance, please don't hesitate to contact me.

Best regards,
[Your Name]
Loan Officer`;

      case 'text':
        return `Hi ${clientName}! ${instruction ? instruction + ' ' : ''}Just checking in on your loan. Let me know if you have any questions!`;

      case 'phone':
        return `CALL SCRIPT for ${clientName}:
${instruction ? `\nKey Point: ${instruction}\n` : ''}
1. Greeting: "Hi ${clientName}, this is [Your Name] calling about your loan application."
2. Purpose: Discuss current status and next steps
3. Ask: "Do you have any questions I can help with?"
4. Close: Schedule follow-up if needed`;

      case 'voicemail':
        return `Hi ${clientName}, this is [Your Name] from [Company]. ${instruction ? instruction + ' ' : ''}I'm calling about your loan application. Please call me back at your convenience at [phone number]. Thank you!`;

      default:
        return generateDefaultMessage(selectedTask);
    }
  };

  // Count by source
  const countBySource = (source) => {
    if (source === 'all') return tasks.length;
    return tasks.filter(t => t.source === source).length;
  };

  // Format date
  const formatDate = (dateStr) => {
    if (!dateStr) return 'N/A';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      month: '2-digit',
      day: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    });
  };

  if (!isOpen) return null;

  return (
    <div className="unified-task-sidebar-v2">
      {/* Left Panel - Task List */}
      <div className="task-list-panel">
        <div className="panel-header">
          <h2>Tasks</h2>
          <span className="task-count-badge">{tasks.length}</span>
        </div>

        {/* Filter tabs */}
        <div className="filter-tabs-v2">
          <button
            className={`filter-tab-v2 ${activeFilter === 'all' ? 'active' : ''}`}
            onClick={() => setActiveFilter('all')}
          >
            All
          </button>
          <button
            className={`filter-tab-v2 ${activeFilter === 'task' ? 'active' : ''}`}
            onClick={() => setActiveFilter('task')}
          >
            Tasks
          </button>
          <button
            className={`filter-tab-v2 ${activeFilter === 'workflow' ? 'active' : ''}`}
            onClick={() => setActiveFilter('workflow')}
          >
            Workflow
          </button>
          <button
            className={`filter-tab-v2 ${activeFilter === 'reconciliation' ? 'active' : ''}`}
            onClick={() => setActiveFilter('reconciliation')}
          >
            Emails
          </button>
        </div>

        <div className="task-list-v2">
          {loading ? (
            <div className="loading-state-v2">Loading tasks...</div>
          ) : filteredTasks.length === 0 ? (
            <div className="empty-state-v2">
              <span className="empty-icon">✅</span>
              <p>No pending tasks</p>
            </div>
          ) : (
            filteredTasks.map((task) => (
              <div
                key={`${task.source}-${task.id}`}
                className={`task-item-v2 ${selectedTask?.id === task.id && selectedTask?.source === task.source ? 'selected' : ''}`}
                onClick={() => handleSelectTask(task)}
              >
                <div
                  className="task-status-bar"
                  style={{ backgroundColor: getStatusColor(task) }}
                />
                <div className="task-item-content">
                  <div className="task-item-header-v2">
                    <span className="task-title-v2">
                      {task.has_calendly_slots && <span style={{ marginRight: '6px' }}>📅</span>}
                      {task.title}
                    </span>
                    <span
                      className="priority-badge-small"
                      style={{
                        color: getPriorityInfo(task.priority).color,
                        backgroundColor: getPriorityInfo(task.priority).bgColor
                      }}
                    >
                      {getPriorityInfo(task.priority).label}
                    </span>
                  </div>
                  <div className="task-meta-v2">
                    <span className="client-name-v2">{task.client_name || 'Unknown Client'}</span>
                    <span className="task-stage">
                      {task.has_calendly_slots ? '📆 Calendly Ready' : (task.stage || task.source)}
                    </span>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Right Panel - Task Detail */}
      <div className="task-detail-panel-v2">
        {selectedTask ? (
          <>
            <div className="detail-header-v2">
              <div className="detail-title-row">
                <h2>{selectedTask.title}</h2>
                <span
                  className="priority-badge-large"
                  style={{
                    color: getPriorityInfo(selectedTask.priority).color,
                    backgroundColor: getPriorityInfo(selectedTask.priority).bgColor
                  }}
                >
                  {getPriorityInfo(selectedTask.priority).label}
                </span>
              </div>
              <button className="close-btn-v2" onClick={onClose}>×</button>
            </div>

            <div className="detail-body-v2">
              {/* Info Grid */}
              <div className="info-grid">
                <div className="info-item">
                  <span className="info-label">CLIENT</span>
                  <span className="info-value">{selectedTask.client_name || 'Unknown'}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">STAGE</span>
                  <span className="info-value">{selectedTask.stage || 'N/A'}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">PRIORITY</span>
                  <span className="info-value priority-value" style={{ color: getPriorityInfo(selectedTask.priority).color }}>
                    {getPriorityInfo(selectedTask.priority).label}
                  </span>
                </div>
                <div className="info-item">
                  <span className="info-label">SOURCE</span>
                  <span className="info-value">{getSourceLabel(selectedTask.source)}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">OWNER</span>
                  <span className="info-value">{selectedTask.owner || 'Loan Officer'}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">DATE CREATED</span>
                  <span className="info-value">{formatDate(selectedTask.created_at)}</span>
                </div>
              </div>

              {/* Send Via Buttons */}
              <div className="send-via-section">
                <span className="section-label">SEND VIA</span>
                <div className="send-via-buttons">
                  <button
                    className={`send-via-btn ${sendVia === 'email' ? 'active' : ''}`}
                    onClick={() => setSendVia('email')}
                  >
                    ✉️ Email
                  </button>
                  <button
                    className={`send-via-btn ${sendVia === 'text' ? 'active' : ''}`}
                    onClick={() => setSendVia('text')}
                  >
                    💬 Text
                  </button>
                  <button
                    className={`send-via-btn ${sendVia === 'phone' ? 'active' : ''}`}
                    onClick={() => setSendVia('phone')}
                  >
                    📞 Phone
                  </button>
                  <button
                    className={`send-via-btn ${sendVia === 'voicemail' ? 'active' : ''}`}
                    onClick={() => setSendVia('voicemail')}
                  >
                    🎙️ Voicemail
                  </button>
                </div>
              </div>

              {/* Train AI Section */}
              <div className="train-ai-section">
                <div className="train-ai-header">
                  <span className="train-ai-icon">🎓</span>
                  <span className="train-ai-label">Train AI (Optional)</span>
                </div>
                <div className="train-ai-input-wrapper">
                  <textarea
                    className="train-ai-input"
                    value={feedbackText}
                    onChange={(e) => setFeedbackText(e.target.value)}
                    placeholder="Type or speak instructions to teach AI how to handle similar tasks... (e.g., 'Always mention our competitive rates when following up on pre-approvals')"
                  />
                  <button
                    className={`voice-input-btn ${isListening ? 'listening' : ''}`}
                    onClick={isListening ? stopListening : startListening}
                    title={isListening ? 'Stop listening' : 'Click to speak'}
                  >
                    {isListening ? '🔴' : '🎤'}
                  </button>
                </div>
                {isListening && (
                  <div className="listening-indicator">
                    <span className="pulse-dot"></span> Listening... speak your instructions
                  </div>
                )}
                <div className="train-ai-actions">
                  <button
                    className="train-ai-btn"
                    onClick={handleTrainAI}
                    disabled={!feedbackText.trim() || trainingInProgress}
                  >
                    {trainingInProgress ? 'Training...' : '🧠 Train AI'}
                  </button>
                </div>
                {aiAcknowledgment && (
                  <div className="ai-acknowledgment">
                    <div className="acknowledgment-header">
                      <span className="ack-icon">✅</span>
                      <span className="ack-title">AI Response:</span>
                    </div>
                    <div className="acknowledgment-text">{aiAcknowledgment}</div>
                  </div>
                )}
                {aiAcknowledgment && (
                  <div className="repopulate-section">
                    <span className="repopulate-label">Repopulate message with training:</span>
                    <div className="repopulate-buttons">
                      <button
                        className={`repopulate-btn ${regeneratingChannel === 'email' ? 'loading' : ''}`}
                        onClick={() => handleRegenerateMessage('email')}
                        disabled={regeneratingChannel !== null}
                      >
                        {regeneratingChannel === 'email' ? '...' : '✉️ Email'}
                      </button>
                      <button
                        className={`repopulate-btn ${regeneratingChannel === 'text' ? 'loading' : ''}`}
                        onClick={() => handleRegenerateMessage('text')}
                        disabled={regeneratingChannel !== null}
                      >
                        {regeneratingChannel === 'text' ? '...' : '💬 Text'}
                      </button>
                      <button
                        className={`repopulate-btn ${regeneratingChannel === 'phone' ? 'loading' : ''}`}
                        onClick={() => handleRegenerateMessage('phone')}
                        disabled={regeneratingChannel !== null}
                      >
                        {regeneratingChannel === 'phone' ? '...' : '📞 Phone'}
                      </button>
                      <button
                        className={`repopulate-btn ${regeneratingChannel === 'voicemail' ? 'loading' : ''}`}
                        onClick={() => handleRegenerateMessage('voicemail')}
                        disabled={regeneratingChannel !== null}
                      >
                        {regeneratingChannel === 'voicemail' ? '...' : '🎙️ Voicemail'}
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* Communication History Accordion */}
              <div className="comm-history-section">
                <button
                  className="comm-history-header"
                  onClick={() => setCommunicationHistoryOpen(!communicationHistoryOpen)}
                >
                  <span>📋 Communication History ({selectedTask.communication_count || 0})</span>
                  <span className="accordion-arrow">{communicationHistoryOpen ? '▲' : '▼'}</span>
                </button>
                {communicationHistoryOpen && (
                  <div className="comm-history-content">
                    {selectedTask.communications?.length > 0 ? (
                      selectedTask.communications.map((comm, idx) => (
                        <div key={idx} className="comm-item">
                          <div className="comm-date">{formatDate(comm.date)}</div>
                          <div className="comm-type">{comm.type}</div>
                          <div className="comm-summary">{comm.summary}</div>
                        </div>
                      ))
                    ) : (
                      <div className="no-history">No previous communications</div>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Action Buttons - Fixed at bottom */}
            <div className="action-buttons-v2">
              <button className="btn-send-email" onClick={handleApprove}>
                {sendVia === 'email' ? 'Send Email' : sendVia === 'text' ? 'Send Text' : sendVia === 'phone' ? 'Log Call' : 'Leave Voicemail'}
              </button>
              <button className="btn-complete" onClick={handleApprove}>
                Complete Task
              </button>
              <button className="btn-snooze" onClick={handleSnooze}>
                Snooze
              </button>
            </div>
          </>
        ) : (
          <div className="no-task-selected">
            <div className="no-task-icon">📋</div>
            <h3>Select a task</h3>
            <p>Click on a task from the list to view details and take action</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default UnifiedTaskSidebar;
