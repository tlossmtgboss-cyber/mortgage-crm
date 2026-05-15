/**
 * Call Intelligence Panel
 *
 * One-button activation - hit REC and the system automatically:
 * 1. Starts recording and transcribing
 * 2. Identifies client from conversation (name, phone mentions)
 * 3. Matches to existing client or creates new profile
 * 4. Runs 6 AI agents to process the call
 * 5. Updates client file OR creates new one
 * 6. Generates tasks and instructions for CRM users
 *
 * AI Agents:
 * - Scriber: Transcription & summaries
 * - Jr. Loan Officer: Pricing, documents, intake fields
 * - AI Underwriter: Risk flags, conditions, compliance
 * - AI Calculator: Mortgage calculations from conversation
 * - Marketer: Borrower story capture
 * - AI Receptionist: Scheduling and follow-ups
 */

import React, { useState, useEffect, useRef } from 'react';
import { callMonitoringAPI } from '../services/api';
import './CallIntelligencePanel.css';

const AGENT_CONFIG = [
  {
    id: 'scribe',
    name: 'Scriber',
    icon: '📝',
    color: '#3b82f6',
    description: 'Transcription & Summaries',
    artifacts: ['summary', 'action_item', 'follow_up_draft']
  },
  {
    id: 'junior_lo',
    name: 'Jr. Loan Officer',
    icon: '👔',
    color: '#B8924A',
    description: 'Pricing & Documents',
    artifacts: ['document_request', 'intake_field', 'pricing_scenario']
  },
  {
    id: 'underwriter',
    name: 'AI Underwriter',
    icon: '🔍',
    color: '#ef4444',
    description: 'Risk & Compliance',
    artifacts: ['risk_flag', 'condition', 'compliance_check']
  },
  {
    id: 'calculator',
    name: 'AI Calculator',
    icon: '🧮',
    color: '#2D7A52',
    description: 'Mortgage Calculations',
    artifacts: ['calculator_result', 'payment_scenario']
  },
  {
    id: 'marketing',
    name: 'Marketer',
    icon: '📣',
    color: '#f59e0b',
    description: 'Story & Content',
    artifacts: ['borrower_story', 'testimonial_draft']
  },
  {
    id: 'receptionist',
    name: 'AI Receptionist',
    icon: '📅',
    color: '#ec4899',
    description: 'Scheduling & Follow-ups',
    artifacts: ['appointment', 'reminder', 'follow_up']
  },
];

const CallIntelligencePanel = ({
  isOpen,
  onClose,
  initialContext = {},
  onArtifactGenerated,
}) => {
  // Client identification state (auto-detected from conversation)
  const [detectedClient, setDetectedClient] = useState(null);
  const [clientMatchStatus, setClientMatchStatus] = useState('idle'); // idle, searching, matched, new_client

  // Session state
  const [sessionId, setSessionId] = useState(null);
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [duration, setDuration] = useState(0);

  // Transcript state
  const [transcript, setTranscript] = useState('');
  const [isTranscribing, setIsTranscribing] = useState(false);

  // Agent state
  const [agentStatuses, setAgentStatuses] = useState({});
  const [artifacts, setArtifacts] = useState([]);
  const [selectedArtifact, setSelectedArtifact] = useState(null);

  // UI state
  const [activeTab, setActiveTab] = useState('live');
  const [error, setError] = useState(null);

  // Refs
  const transcriptRef = useRef(null);
  const timerRef = useRef(null);
  const recognitionRef = useRef(null);
  const pollingRef = useRef(null);
  const clientDetectionRef = useRef(null);

  // Format phone number for display
  const formatPhoneDisplay = (phone) => {
    if (!phone) return '';
    const cleaned = phone.replace(/\D/g, '');
    if (cleaned.length === 10) {
      return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6)}`;
    }
    if (cleaned.length === 11 && cleaned[0] === '1') {
      return `+1 (${cleaned.slice(1, 4)}) ${cleaned.slice(4, 7)}-${cleaned.slice(7)}`;
    }
    return phone;
  };

  // Extract potential identifiers from transcript (runs automatically)
  const extractIdentifiersFromTranscript = (text) => {
    const identifiers = { phones: [], names: [], emails: [] };

    // Phone number patterns
    const phonePatterns = [
      /\b(\d{3}[-.\s]?\d{3}[-.\s]?\d{4})\b/g,
      /\((\d{3})\)\s*(\d{3})[-.\s]?(\d{4})/g,
      /\b(\d{10})\b/g,
    ];
    phonePatterns.forEach(pattern => {
      const matches = text.match(pattern);
      if (matches) identifiers.phones.push(...matches);
    });

    // Email pattern
    const emailPattern = /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b/g;
    const emailMatches = text.match(emailPattern);
    if (emailMatches) identifiers.emails.push(...emailMatches);

    // Name patterns (common introductions)
    const namePatterns = [
      /(?:my name is|i'm|this is|i am)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)/gi,
      /(?:speaking with|talking to)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)/gi,
    ];
    namePatterns.forEach(pattern => {
      let match;
      while ((match = pattern.exec(text)) !== null) {
        if (match[1] && match[1].length > 2) {
          identifiers.names.push(match[1]);
        }
      }
    });

    return identifiers;
  };

  // Auto-detect and match client from transcript
  const autoDetectClient = async (identifiers) => {
    if (clientMatchStatus === 'matched' || clientMatchStatus === 'searching') return;

    // Need at least a phone or name to search
    if (identifiers.phones.length === 0 && identifiers.names.length === 0) return;

    setClientMatchStatus('searching');

    try {
      // Try phone first (most reliable)
      if (identifiers.phones.length > 0) {
        const phone = identifiers.phones[0].replace(/\D/g, '');
        const result = await callMonitoringAPI.lookupCaller(phone);

        if (result.found) {
          setDetectedClient({
            ...result.client,
            detected_via: 'phone',
            detected_value: phone,
          });
          setClientMatchStatus('matched');
          return;
        }
      }

      // Try name search if phone didn't match
      if (identifiers.names.length > 0) {
        const name = identifiers.names[0];
        try {
          const result = await callMonitoringAPI.searchClients({ name });
          if (result.clients && result.clients.length > 0) {
            setDetectedClient({
              ...result.clients[0],
              detected_via: 'name',
              detected_value: name,
            });
            setClientMatchStatus('matched');
            return;
          }
        } catch (e) {
          // Name search API may not exist yet
        }
      }

      // No match found - will create new client on call end
      setDetectedClient({
        name: identifiers.names[0] || 'New Client',
        phone: identifiers.phones[0] || null,
        email: identifiers.emails[0] || null,
        is_new: true,
      });
      setClientMatchStatus('new_client');

    } catch (err) {
      console.error('Client detection failed:', err);
      setClientMatchStatus('idle');
    }
  };

  // Initialize speech recognition
  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      const recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = 'en-US';

      recognition.onresult = (event) => {
        let finalTranscript = '';
        let interimTranscript = '';

        for (let i = event.resultIndex; i < event.results.length; i++) {
          const result = event.results[i];
          if (result.isFinal) {
            finalTranscript += result[0].transcript + ' ';
          } else {
            interimTranscript += result[0].transcript;
          }
        }

        if (finalTranscript) {
          setTranscript(prev => {
            const newTranscript = prev + finalTranscript;

            // Auto-detect client from transcript (debounced)
            if (clientDetectionRef.current) {
              clearTimeout(clientDetectionRef.current);
            }
            clientDetectionRef.current = setTimeout(() => {
              const identifiers = extractIdentifiersFromTranscript(newTranscript);
              if (identifiers.phones.length > 0 || identifiers.names.length > 0) {
                autoDetectClient(identifiers);
              }
            }, 2000); // Wait 2 seconds of no new speech before detecting

            return newTranscript;
          });

          // Send chunk to backend
          if (sessionId) {
            sendTranscriptChunk(finalTranscript);
          }
        }
      };

      recognition.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
        if (event.error !== 'no-speech') {
          setError(`Speech recognition error: ${event.error}`);
        }
      };

      recognitionRef.current = recognition;
    }

    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
    };
  }, [sessionId]);

  // Timer for duration
  useEffect(() => {
    if (isRecording && !isPaused) {
      timerRef.current = setInterval(() => {
        setDuration(prev => prev + 1);
      }, 1000);
    } else {
      clearInterval(timerRef.current);
    }

    return () => clearInterval(timerRef.current);
  }, [isRecording, isPaused]);

  // Auto-scroll transcript
  useEffect(() => {
    if (transcriptRef.current) {
      transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
    }
  }, [transcript]);

  // Poll for artifacts and agent status in real-time while recording
  useEffect(() => {
    if (sessionId && isRecording) {
      // Poll every 2 seconds for real-time updates
      pollingRef.current = setInterval(async () => {
        try {
          // Get latest artifacts from all agents
          const result = await callMonitoringAPI.getArtifacts(sessionId);
          if (result.artifacts && result.artifacts.length > 0) {
            setArtifacts(result.artifacts);

            // Update agent statuses based on artifacts they've produced
            const newStatuses = { ...agentStatuses };
            AGENT_CONFIG.forEach(agent => {
              const agentArtifacts = result.artifacts.filter(a =>
                agent.artifacts.includes(a.artifact_type)
              );
              if (agentArtifacts.length > 0) {
                newStatuses[agent.id] = {
                  status: 'active',
                  artifacts: agentArtifacts,
                  lastUpdate: new Date().toISOString(),
                };
              }
            });
            setAgentStatuses(newStatuses);
          }
        } catch (err) {
          console.error('Failed to fetch artifacts:', err);
        }
      }, 2000);
    }

    return () => clearInterval(pollingRef.current);
  }, [sessionId, isRecording, agentStatuses]);

  // Send transcript chunk to backend - triggers real-time agent processing
  const sendTranscriptChunk = async (text) => {
    if (!sessionId) return;

    try {
      // Send chunk with instruction to process in real-time
      await callMonitoringAPI.appendTranscriptChunk(sessionId, {
        text,
        speaker: 'unknown',
        timestamp: new Date().toISOString(),
        process_realtime: true, // Trigger agents to analyze this chunk immediately
      });

      // Mark agents as actively processing
      const activeStatuses = { ...agentStatuses };
      AGENT_CONFIG.forEach(agent => {
        if (activeStatuses[agent.id]?.status === 'ready') {
          activeStatuses[agent.id] = {
            ...activeStatuses[agent.id],
            status: 'listening',
          };
        }
      });
      setAgentStatuses(activeStatuses);

    } catch (err) {
      console.error('Failed to send transcript chunk:', err);
    }
  };

  // Start recording session - one button, automatic everything, real-time processing
  const startRecording = async () => {
    try {
      setError(null);
      setIsTranscribing(true);

      // Reset state
      setDetectedClient(null);
      setClientMatchStatus('idle');
      setArtifacts([]);

      // Create session with real-time agent processing enabled
      const session = await callMonitoringAPI.createSession({
        capture_mode: 'call_intelligence',
        metadata: {
          ...initialContext,
          started_at: new Date().toISOString(),
          auto_detect_client: true,
          realtime_processing: true, // Enable real-time agent processing
        },
      });

      setSessionId(session.id || session.session_id);
      setIsRecording(true);
      setDuration(0);
      setTranscript('');

      // Initialize all agents as ready and listening
      const initialStatuses = {};
      AGENT_CONFIG.forEach(agent => {
        initialStatuses[agent.id] = {
          status: 'ready',
          artifacts: [],
          listening: true,
        };
      });
      setAgentStatuses(initialStatuses);

      // Start real-time agent processing on backend
      try {
        await callMonitoringAPI.runAgents(session.id || session.session_id, null);
      } catch (e) {
        // Agents will start when first transcript arrives
        console.log('Agents will start on first transcript');
      }

      // Start speech recognition
      if (recognitionRef.current) {
        recognitionRef.current.start();
      }

      setIsTranscribing(false);
    } catch (err) {
      console.error('Failed to start recording:', err);
      setError('Failed to start recording session');
      setIsTranscribing(false);
    }
  };

  // Stop recording and process - automatically handles client matching/creation
  const stopRecording = async () => {
    try {
      // Stop speech recognition
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }

      // Clear any pending client detection
      if (clientDetectionRef.current) {
        clearTimeout(clientDetectionRef.current);
      }

      setIsRecording(false);

      // Final client detection attempt if not yet matched
      if (clientMatchStatus !== 'matched' && transcript) {
        const identifiers = extractIdentifiersFromTranscript(transcript);
        if (identifiers.phones.length > 0 || identifiers.names.length > 0) {
          await autoDetectClient(identifiers);
        }
      }

      // Update agent statuses to processing
      const processingStatuses = {};
      AGENT_CONFIG.forEach(agent => {
        processingStatuses[agent.id] = { status: 'processing', artifacts: [] };
      });
      setAgentStatuses(processingStatuses);

      // End session with client info and run all agents
      if (sessionId) {
        // If new client detected, create them first
        if (clientMatchStatus === 'new_client' && detectedClient) {
          try {
            const newClient = await callMonitoringAPI.createClientFromCall({
              name: detectedClient.name || 'New Client',
              phone: detectedClient.phone?.replace(/\D/g, '') || null,
              email: detectedClient.email || null,
              source: 'call_intelligence',
              notes: `Auto-created from call on ${new Date().toLocaleDateString()}`,
            });
            setDetectedClient({
              ...detectedClient,
              id: newClient.id || newClient.client?.id,
              is_new: true,
            });
          } catch (err) {
            console.error('Failed to create new client:', err);
          }
        }

        // End session with all context for agents to process
        await callMonitoringAPI.endSession(sessionId, {
          run_agents: true,
          client_id: detectedClient?.id || null,
          client_name: detectedClient?.name || null,
          is_new_client: clientMatchStatus === 'new_client',
          full_transcript: transcript,
          instructions: {
            update_client_file: clientMatchStatus === 'matched',
            create_client_file: clientMatchStatus === 'new_client',
            generate_tasks: true,
            generate_follow_ups: true,
          },
        });

        // Poll for results
        await pollForResults();
      }
    } catch (err) {
      console.error('Failed to stop recording:', err);
      setError('Failed to process recording');
    }
  };

  // Poll for agent results
  const pollForResults = async () => {
    const maxAttempts = 30;
    let attempts = 0;

    const poll = async () => {
      if (attempts >= maxAttempts) {
        setError('Processing timeout - some agents may not have completed');
        return;
      }

      attempts++;

      try {
        const result = await callMonitoringAPI.getArtifacts(sessionId);

        if (result.artifacts) {
          setArtifacts(result.artifacts);

          // Update agent statuses based on artifacts
          const newStatuses = {};
          AGENT_CONFIG.forEach(agent => {
            const agentArtifacts = result.artifacts.filter(a =>
              agent.artifacts.includes(a.artifact_type)
            );
            newStatuses[agent.id] = {
              status: agentArtifacts.length > 0 ? 'complete' : 'processing',
              artifacts: agentArtifacts,
            };
          });
          setAgentStatuses(newStatuses);

          // Check if all agents are done
          const allComplete = Object.values(newStatuses).every(
            s => s.status === 'complete' || s.artifacts.length > 0
          );

          if (!allComplete && attempts < maxAttempts) {
            setTimeout(poll, 2000);
          }
        }
      } catch (err) {
        console.error('Polling error:', err);
      }
    };

    await poll();
  };

  // Pause/Resume recording
  const togglePause = () => {
    if (isPaused) {
      if (recognitionRef.current) {
        recognitionRef.current.start();
      }
    } else {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
    }
    setIsPaused(!isPaused);
  };

  // Format duration
  const formatDuration = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  // Approve artifact
  const handleApproveArtifact = async (artifactId) => {
    try {
      await callMonitoringAPI.approveArtifact(sessionId, { artifact_id: artifactId });
      setArtifacts(prev => prev.map(a =>
        a.id === artifactId ? { ...a, status: 'approved' } : a
      ));
      if (onArtifactGenerated) {
        onArtifactGenerated(artifacts.find(a => a.id === artifactId));
      }
    } catch (err) {
      console.error('Failed to approve artifact:', err);
    }
  };

  // Execute artifact
  const handleExecuteArtifact = async (artifactId) => {
    try {
      await callMonitoringAPI.executeArtifact(sessionId, { artifact_id: artifactId });
      setArtifacts(prev => prev.map(a =>
        a.id === artifactId ? { ...a, status: 'executed' } : a
      ));
    } catch (err) {
      console.error('Failed to execute artifact:', err);
    }
  };

  // Get artifact icon
  const getArtifactIcon = (type) => {
    const icons = {
      summary: '📋',
      action_item: '✅',
      follow_up_draft: '✉️',
      document_request: '📄',
      intake_field: '📝',
      pricing_scenario: '💰',
      risk_flag: '⚠️',
      condition: '📌',
      compliance_check: '✓',
      calculator_result: '🧮',
      payment_scenario: '💵',
      borrower_story: '📖',
      testimonial_draft: '⭐',
      appointment: '📅',
      reminder: '🔔',
      follow_up: '📞',
    };
    return icons[type] || '📎';
  };

  if (!isOpen) return null;

  return (
    <div className="call-intelligence-panel">
      {/* Header */}
      <div className="cip-header">
        <div className="cip-header-left">
          <div className="cip-title">
            <span className="cip-icon">🎯</span>
            <span>Call Intelligence</span>
          </div>
          {isRecording && (
            <div className="cip-recording-badge">
              <span className="rec-dot"></span>
              <span>{formatDuration(duration)}</span>
            </div>
          )}
        </div>
        <button className="cip-close-btn" onClick={onClose}>×</button>
      </div>

      {/* One-Button Recording Control */}
      <div className="cip-controls">
        {!isRecording ? (
          <button
            className="cip-record-btn"
            onClick={startRecording}
            disabled={isTranscribing}
          >
            <span className="rec-circle"></span>
            <span>{isTranscribing ? 'Starting...' : 'Start Recording'}</span>
          </button>
        ) : (
          <div className="cip-active-controls">
            <button
              className={`cip-pause-btn ${isPaused ? 'paused' : ''}`}
              onClick={togglePause}
            >
              {isPaused ? '▶️ Resume' : '⏸️ Pause'}
            </button>
            <button
              className="cip-stop-btn"
              onClick={stopRecording}
            >
              ⏹️ Stop & Process
            </button>
          </div>
        )}

        {!isRecording && !isTranscribing && (
          <p className="cip-instructions">
            Hit record to start. Client identification, transcription, and all AI processing happens automatically.
          </p>
        )}
      </div>

      {/* Auto-Detected Client Display */}
      {(isRecording || detectedClient) && (
        <div className="cip-client-detection">
          <div className="detection-header">
            <span className="detection-icon">
              {clientMatchStatus === 'searching' && '🔍'}
              {clientMatchStatus === 'matched' && '✓'}
              {clientMatchStatus === 'new_client' && '➕'}
              {clientMatchStatus === 'idle' && '👤'}
            </span>
            <span className="detection-label">
              {clientMatchStatus === 'idle' && 'Listening for client info...'}
              {clientMatchStatus === 'searching' && 'Searching for client...'}
              {clientMatchStatus === 'matched' && 'Client Matched'}
              {clientMatchStatus === 'new_client' && 'New Client Detected'}
            </span>
          </div>

          {detectedClient && (
            <div className="detected-client-card">
              <div className="client-avatar">
                {detectedClient.name?.charAt(0)?.toUpperCase() || '?'}
              </div>
              <div className="client-info">
                <div className="client-name">
                  {detectedClient.name || 'Unknown'}
                  {detectedClient.is_new && <span className="new-badge">NEW</span>}
                </div>
                {detectedClient.phone && (
                  <div className="client-phone">{formatPhoneDisplay(detectedClient.phone)}</div>
                )}
                {detectedClient.email && (
                  <div className="client-email">{detectedClient.email}</div>
                )}
                {detectedClient.loan_status && (
                  <div className="client-loan-status">
                    <span className="status-dot"></span>
                    {detectedClient.loan_status}
                  </div>
                )}
                {detectedClient.detected_via && (
                  <div className="detected-via">
                    Detected via {detectedClient.detected_via}: {detectedClient.detected_value}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Error Display */}
      {error && (
        <div className="cip-error">
          <span>⚠️</span>
          <span>{error}</span>
          <button onClick={() => setError(null)}>×</button>
        </div>
      )}

      {/* Agent Status Grid - Real-time Processing */}
      <div className="cip-agents-section">
        <div className="cip-section-header">
          <h3>AI Agents</h3>
          {isRecording && (
            <span className="realtime-badge">
              <span className="pulse-dot"></span>
              Real-time
            </span>
          )}
        </div>
        <div className="cip-agents-grid">
          {AGENT_CONFIG.map(agent => {
            const status = agentStatuses[agent.id] || { status: 'idle', artifacts: [] };
            const artifactCount = status.artifacts?.length || 0;
            return (
              <div
                key={agent.id}
                className={`cip-agent-card ${status.status} ${isRecording ? 'live' : ''}`}
                style={{ '--agent-color': agent.color }}
              >
                <div className="agent-icon">{agent.icon}</div>
                <div className="agent-info">
                  <div className="agent-name">{agent.name}</div>
                  <div className="agent-desc">
                    {status.status === 'active' && artifactCount > 0
                      ? `${artifactCount} item${artifactCount > 1 ? 's' : ''} captured`
                      : agent.description
                    }
                  </div>
                </div>
                <div className="agent-status">
                  {status.status === 'idle' && <span className="status-idle">●</span>}
                  {(status.status === 'ready' || status.status === 'listening') && isRecording && (
                    <span className="status-listening">
                      <span className="listening-wave"></span>
                    </span>
                  )}
                  {status.status === 'ready' && !isRecording && <span className="status-ready">●</span>}
                  {status.status === 'processing' && (
                    <span className="status-processing">
                      <span className="spinner"></span>
                    </span>
                  )}
                  {status.status === 'active' && (
                    <span className="status-active">
                      {artifactCount > 0 ? `✓ ${artifactCount}` : <span className="spinner"></span>}
                    </span>
                  )}
                  {status.status === 'complete' && (
                    <span className="status-complete">
                      ✓ {artifactCount}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Tabs */}
      <div className="cip-tabs">
        <button
          className={activeTab === 'live' ? 'active' : ''}
          onClick={() => setActiveTab('live')}
        >
          📝 Live Transcript
        </button>
        <button
          className={activeTab === 'artifacts' ? 'active' : ''}
          onClick={() => setActiveTab('artifacts')}
        >
          📦 Artifacts ({artifacts.length})
        </button>
      </div>

      {/* Tab Content */}
      <div className="cip-content">
        {activeTab === 'live' && (
          <div className="cip-transcript" ref={transcriptRef}>
            {transcript ? (
              <div className="transcript-text">{transcript}</div>
            ) : (
              <div className="transcript-empty">
                {isRecording ? (
                  <>
                    <div className="listening-animation">
                      <span></span><span></span><span></span>
                    </div>
                    <p>Listening for conversation...</p>
                  </>
                ) : (
                  <p>Press "Start Recording" to begin capturing the call</p>
                )}
              </div>
            )}
          </div>
        )}

        {activeTab === 'artifacts' && (
          <div className="cip-artifacts">
            {artifacts.length === 0 ? (
              <div className="artifacts-empty">
                <span>📦</span>
                <p>Artifacts will appear here after processing</p>
              </div>
            ) : (
              <div className="artifacts-list">
                {artifacts.map(artifact => (
                  <div
                    key={artifact.id}
                    className={`artifact-card ${artifact.status || 'pending'}`}
                    onClick={() => setSelectedArtifact(artifact)}
                  >
                    <div className="artifact-icon">
                      {getArtifactIcon(artifact.artifact_type)}
                    </div>
                    <div className="artifact-content">
                      <div className="artifact-type">{artifact.artifact_type.replace(/_/g, ' ')}</div>
                      <div className="artifact-preview">
                        {typeof artifact.content === 'string'
                          ? artifact.content.substring(0, 100) + '...'
                          : artifact.content?.title || artifact.content?.summary || 'View details'
                        }
                      </div>
                    </div>
                    <div className="artifact-actions">
                      {artifact.status !== 'approved' && artifact.status !== 'executed' && (
                        <>
                          <button
                            className="approve-btn"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleApproveArtifact(artifact.id);
                            }}
                            title="Approve"
                          >
                            ✓
                          </button>
                          <button
                            className="execute-btn"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleExecuteArtifact(artifact.id);
                            }}
                            title="Execute"
                          >
                            ▶
                          </button>
                        </>
                      )}
                      {artifact.status === 'approved' && (
                        <span className="status-badge approved">Approved</span>
                      )}
                      {artifact.status === 'executed' && (
                        <span className="status-badge executed">Executed</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Artifact Detail Modal */}
      {selectedArtifact && (
        <div className="artifact-modal-overlay" onClick={() => setSelectedArtifact(null)}>
          <div className="artifact-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <span className="modal-icon">{getArtifactIcon(selectedArtifact.artifact_type)}</span>
              <h3>{selectedArtifact.artifact_type.replace(/_/g, ' ')}</h3>
              <button onClick={() => setSelectedArtifact(null)}>×</button>
            </div>
            <div className="modal-content">
              <pre>{JSON.stringify(selectedArtifact.content, null, 2)}</pre>
            </div>
            <div className="modal-actions">
              {selectedArtifact.status !== 'approved' && selectedArtifact.status !== 'executed' && (
                <>
                  <button
                    className="modal-approve-btn"
                    onClick={() => {
                      handleApproveArtifact(selectedArtifact.id);
                      setSelectedArtifact(null);
                    }}
                  >
                    ✓ Approve
                  </button>
                  <button
                    className="modal-execute-btn"
                    onClick={() => {
                      handleExecuteArtifact(selectedArtifact.id);
                      setSelectedArtifact(null);
                    }}
                  >
                    ▶ Execute
                  </button>
                </>
              )}
              <button
                className="modal-close-btn"
                onClick={() => setSelectedArtifact(null)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default CallIntelligencePanel;
