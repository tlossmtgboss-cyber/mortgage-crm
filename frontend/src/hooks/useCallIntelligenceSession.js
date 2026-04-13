/**
 * useCallIntelligenceSession - Shared session management for Call Intelligence
 *
 * Extracted from CallIntelligencePanel.js to be shared between
 * desktop (Web Speech API) and mobile (Deepgram streaming) panels.
 *
 * Manages:
 * - Session create/end via callMonitoringAPI
 * - Agent status polling (2s interval)
 * - Artifact fetching and management (approve/reject/execute)
 * - Client auto-detection from transcript text
 * - Duration timer
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { callMonitoringAPI } from '../services/api';

// Agent configuration - shared between desktop and mobile
export const AGENT_CONFIG = [
  {
    id: 'scribe',
    name: 'Scriber',
    icon: '📝',
    color: '#3b82f6',
    description: 'Transcription & Summaries',
    artifacts: ['summary', 'action_item', 'follow_up_draft'],
  },
  {
    id: 'junior_lo',
    name: 'Jr. Loan Officer',
    icon: '👔',
    color: '#8b5cf6',
    description: 'Pricing & Documents',
    artifacts: ['document_request', 'intake_field', 'pricing_scenario'],
  },
  {
    id: 'underwriter',
    name: 'AI Underwriter',
    icon: '🔍',
    color: '#ef4444',
    description: 'Risk & Compliance',
    artifacts: ['risk_flag', 'condition', 'compliance_check'],
  },
  {
    id: 'calculator',
    name: 'AI Calculator',
    icon: '🧮',
    color: '#10b981',
    description: 'Mortgage Calculations',
    artifacts: ['calculator_result', 'payment_scenario'],
  },
  {
    id: 'marketing',
    name: 'Marketer',
    icon: '📣',
    color: '#f59e0b',
    description: 'Story & Content',
    artifacts: ['borrower_story', 'testimonial_draft'],
  },
  {
    id: 'receptionist',
    name: 'AI Receptionist',
    icon: '📅',
    color: '#ec4899',
    description: 'Scheduling & Follow-ups',
    artifacts: ['appointment', 'reminder', 'follow_up'],
  },
];

// Artifact type to icon mapping
export const ARTIFACT_ICONS = {
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

export const getArtifactIcon = (type) => ARTIFACT_ICONS[type] || '📎';

// Format duration as MM:SS
export const formatDuration = (seconds) => {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
};

const useCallIntelligenceSession = ({
  initialContext = {},
  onArtifactGenerated,
  // When true, skip sending transcript chunks via REST API.
  // Use this when a WebSocket (e.g. audio-stream) already feeds
  // transcript text to the backend's process_transcript_chunk.
  skipBackendChunkSend = false,
} = {}) => {
  // Session state
  const [sessionId, setSessionId] = useState(null);
  const [isActive, setIsActive] = useState(false);
  const [duration, setDuration] = useState(0);
  const [error, setError] = useState(null);
  const [isStarting, setIsStarting] = useState(false);
  const [isStopping, setIsStopping] = useState(false);

  // Transcript state (accumulated from external source)
  const [transcript, setTranscript] = useState('');

  // Agent state
  const [agentStatuses, setAgentStatuses] = useState({});
  const [artifacts, setArtifacts] = useState([]);

  // Client detection state
  const [detectedClient, setDetectedClient] = useState(null);
  const [clientMatchStatus, setClientMatchStatus] = useState('idle');

  // Refs
  const timerRef = useRef(null);
  const pollingRef = useRef(null);
  const clientDetectionRef = useRef(null);
  const transcriptRef = useRef('');

  // Keep transcriptRef in sync
  useEffect(() => {
    transcriptRef.current = transcript;
  }, [transcript]);

  // Duration timer
  useEffect(() => {
    if (isActive) {
      timerRef.current = setInterval(() => {
        setDuration((prev) => prev + 1);
      }, 1000);
    } else {
      clearInterval(timerRef.current);
    }
    return () => clearInterval(timerRef.current);
  }, [isActive]);

  // Poll for artifacts while session is active
  useEffect(() => {
    if (sessionId && isActive) {
      pollingRef.current = setInterval(async () => {
        try {
          const result = await callMonitoringAPI.getArtifacts(sessionId);
          if (result.artifacts && result.artifacts.length > 0) {
            setArtifacts(result.artifacts);

            const newStatuses = { ...agentStatuses };
            AGENT_CONFIG.forEach((agent) => {
              const agentArtifacts = result.artifacts.filter((a) =>
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
  }, [sessionId, isActive]);

  // Extract identifiers from transcript text
  const extractIdentifiers = useCallback((text) => {
    const identifiers = { phones: [], names: [], emails: [] };

    // Phone patterns
    const phonePatterns = [
      /\b(\d{3}[-.\s]?\d{3}[-.\s]?\d{4})\b/g,
      /\((\d{3})\)\s*(\d{3})[-.\s]?(\d{4})/g,
      /\b(\d{10})\b/g,
    ];
    phonePatterns.forEach((pattern) => {
      const matches = text.match(pattern);
      if (matches) identifiers.phones.push(...matches);
    });

    // Email
    const emailMatches = text.match(
      /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b/g
    );
    if (emailMatches) identifiers.emails.push(...emailMatches);

    // Name patterns
    const namePatterns = [
      /(?:my name is|i'm|this is|i am)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)/gi,
      /(?:speaking with|talking to)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)/gi,
    ];
    namePatterns.forEach((pattern) => {
      let match;
      while ((match = pattern.exec(text)) !== null) {
        if (match[1] && match[1].length > 2) {
          identifiers.names.push(match[1]);
        }
      }
    });

    return identifiers;
  }, []);

  // Auto-detect and match client
  const autoDetectClient = useCallback(
    async (identifiers) => {
      if (clientMatchStatus === 'matched' || clientMatchStatus === 'searching')
        return;
      if (identifiers.phones.length === 0 && identifiers.names.length === 0)
        return;

      setClientMatchStatus('searching');

      try {
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
            // Name search may not be available
          }
        }

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
    },
    [clientMatchStatus]
  );

  // Append transcript text and trigger client detection
  const appendTranscript = useCallback(
    (text) => {
      setTranscript((prev) => {
        const newTranscript = prev + text + ' ';

        // Debounced client detection
        if (clientDetectionRef.current) {
          clearTimeout(clientDetectionRef.current);
        }
        clientDetectionRef.current = setTimeout(() => {
          const identifiers = extractIdentifiers(newTranscript);
          if (identifiers.phones.length > 0 || identifiers.names.length > 0) {
            autoDetectClient(identifiers);
          }
        }, 2000);

        return newTranscript;
      });

      // Send chunk to backend via REST (skip if WebSocket already handles this)
      if (sessionId && !skipBackendChunkSend) {
        callMonitoringAPI
          .appendTranscriptChunk(sessionId, {
            text,
            speaker: 'unknown',
            timestamp: new Date().toISOString(),
            process_realtime: true,
          })
          .catch((err) => console.error('Failed to send transcript chunk:', err));
      }
    },
    [sessionId, skipBackendChunkSend, extractIdentifiers, autoDetectClient]
  );

  // Start session
  const startSession = useCallback(
    async (captureMode = 'call_intelligence') => {
      try {
        setError(null);
        setIsStarting(true);
        setDetectedClient(null);
        setClientMatchStatus('idle');
        setArtifacts([]);
        setTranscript('');
        setDuration(0);

        const session = await callMonitoringAPI.createSession({
          capture_mode: captureMode,
          metadata: {
            ...initialContext,
            started_at: new Date().toISOString(),
            auto_detect_client: true,
            realtime_processing: true,
          },
        });

        const sid = session.id || session.session_id;
        setSessionId(sid);
        setIsActive(true);

        // Initialize agent statuses
        const initialStatuses = {};
        AGENT_CONFIG.forEach((agent) => {
          initialStatuses[agent.id] = {
            status: 'ready',
            artifacts: [],
            listening: true,
          };
        });
        setAgentStatuses(initialStatuses);

        // Start agents
        try {
          await callMonitoringAPI.runAgents(sid, null);
        } catch (e) {
          console.log('Agents will start on first transcript');
        }

        setIsStarting(false);
        return sid;
      } catch (err) {
        console.error('Failed to start session:', err);
        const detail = err.response?.data?.detail || err.message || 'Unknown error';
        setError(`Failed to start recording session: ${detail}`);
        setIsStarting(false);
        return null;
      }
    },
    [initialContext]
  );

  // End session
  const endSession = useCallback(async () => {
    try {
      setIsStopping(true);
      setIsActive(false);

      // Clear client detection timeout
      if (clientDetectionRef.current) {
        clearTimeout(clientDetectionRef.current);
      }

      // Final client detection
      if (clientMatchStatus !== 'matched' && transcriptRef.current) {
        const identifiers = extractIdentifiers(transcriptRef.current);
        if (identifiers.phones.length > 0 || identifiers.names.length > 0) {
          await autoDetectClient(identifiers);
        }
      }

      // Update agent statuses
      const processingStatuses = {};
      AGENT_CONFIG.forEach((agent) => {
        processingStatuses[agent.id] = { status: 'processing', artifacts: [] };
      });
      setAgentStatuses(processingStatuses);

      if (sessionId) {
        // Create new client if needed
        if (clientMatchStatus === 'new_client' && detectedClient) {
          try {
            const newClient = await callMonitoringAPI.createClientFromCall({
              name: detectedClient.name || 'New Client',
              phone: detectedClient.phone?.replace(/\D/g, '') || null,
              email: detectedClient.email || null,
              source: 'call_intelligence',
              notes: `Auto-created from call on ${new Date().toLocaleDateString()}`,
            });
            setDetectedClient((prev) => ({
              ...prev,
              id: newClient.id || newClient.client?.id,
              is_new: true,
            }));
          } catch (err) {
            console.error('Failed to create new client:', err);
          }
        }

        // End session with context
        await callMonitoringAPI.endSession(sessionId, {
          run_agents: true,
          client_id: detectedClient?.id || null,
          client_name: detectedClient?.name || null,
          is_new_client: clientMatchStatus === 'new_client',
          full_transcript: transcriptRef.current,
          instructions: {
            update_client_file: clientMatchStatus === 'matched',
            create_client_file: clientMatchStatus === 'new_client',
            generate_tasks: true,
            generate_follow_ups: true,
          },
        });

        // Poll for final results
        await pollForResults();
      }

      setIsStopping(false);
    } catch (err) {
      console.error('Failed to end session:', err);
      setError('Failed to process recording');
      setIsStopping(false);
    }
  }, [
    sessionId,
    clientMatchStatus,
    detectedClient,
    extractIdentifiers,
    autoDetectClient,
  ]);

  // Poll for agent results after ending
  const pollForResults = useCallback(async () => {
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

          const newStatuses = {};
          AGENT_CONFIG.forEach((agent) => {
            const agentArtifacts = result.artifacts.filter((a) =>
              agent.artifacts.includes(a.artifact_type)
            );
            newStatuses[agent.id] = {
              status: agentArtifacts.length > 0 ? 'complete' : 'processing',
              artifacts: agentArtifacts,
            };
          });
          setAgentStatuses(newStatuses);

          const allComplete = Object.values(newStatuses).every(
            (s) => s.status === 'complete' || s.artifacts.length > 0
          );

          if (!allComplete && attempts < maxAttempts) {
            await new Promise((r) => setTimeout(r, 2000));
            await poll();
          }
        }
      } catch (err) {
        console.error('Polling error:', err);
      }
    };

    await poll();
  }, [sessionId]);

  // Approve artifact
  const approveArtifact = useCallback(
    async (artifactId) => {
      try {
        await callMonitoringAPI.approveArtifacts(sessionId, [artifactId]);
        setArtifacts((prev) =>
          prev.map((a) =>
            a.id === artifactId ? { ...a, status: 'approved' } : a
          )
        );
        if (onArtifactGenerated) {
          onArtifactGenerated(artifacts.find((a) => a.id === artifactId));
        }
      } catch (err) {
        console.error('Failed to approve artifact:', err);
      }
    },
    [sessionId, artifacts, onArtifactGenerated]
  );

  // Reject artifact
  const rejectArtifact = useCallback(
    async (artifactId, reason) => {
      try {
        await callMonitoringAPI.rejectArtifacts(sessionId, [artifactId]);
        setArtifacts((prev) =>
          prev.map((a) =>
            a.id === artifactId ? { ...a, status: 'rejected' } : a
          )
        );
      } catch (err) {
        console.error('Failed to reject artifact:', err);
      }
    },
    [sessionId]
  );

  // Execute artifact
  const executeArtifact = useCallback(
    async (artifactId) => {
      try {
        await callMonitoringAPI.executeArtifacts(sessionId, [artifactId]);
        setArtifacts((prev) =>
          prev.map((a) =>
            a.id === artifactId ? { ...a, status: 'executed' } : a
          )
        );
      } catch (err) {
        console.error('Failed to execute artifact:', err);
      }
    },
    [sessionId]
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearInterval(timerRef.current);
      clearInterval(pollingRef.current);
      if (clientDetectionRef.current) {
        clearTimeout(clientDetectionRef.current);
      }
    };
  }, []);

  return {
    // Session
    sessionId,
    isActive,
    duration,
    isStarting,
    isStopping,
    error,

    // Transcript
    transcript,
    appendTranscript,

    // Agents
    agentStatuses,
    artifacts,

    // Client detection
    detectedClient,
    clientMatchStatus,

    // Actions
    startSession,
    endSession,
    approveArtifact,
    rejectArtifact,
    executeArtifact,
  };
};

export default useCallIntelligenceSession;
