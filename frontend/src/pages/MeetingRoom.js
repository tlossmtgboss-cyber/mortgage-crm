import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { sanitizeText } from '../utils/sanitize';
import { getAuthHeaders } from '../utils/auth';
import { toast } from '../utils/toast';
import './MeetingRoom.css';
import { getToken } from '../utils/tokenStore';

// API Base URL
const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const API_BASE = isProduction
  ? 'https://api.perenniaai.com'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

// Configurable constants
const WS_PING_INTERVAL_MS = 30000;       // WebSocket keepalive ping
const BANDWIDTH_CHECK_INTERVAL_MS = 10000; // Remote stream quality monitoring
const MAX_RECONNECT_ATTEMPTS = 5;

const MeetingRoom = () => {
  const { roomCode } = useParams();
  const navigate = useNavigate();

  // Host detection - determine from user ID and meeting data (not URL param)
  const [isHost, setIsHost] = useState(false);
  const [currentUserId, setCurrentUserId] = useState(null);

  // State
  const [meeting, setMeeting] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [joined, setJoined] = useState(false);
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');
  const [inWaitingRoom, setInWaitingRoom] = useState(false);

  // Media state
  const [localStream, setLocalStream] = useState(null);
  const [audioEnabled, setAudioEnabled] = useState(true);
  const [videoEnabled, setVideoEnabled] = useState(true);
  const [screenSharing, setScreenSharing] = useState(false);
  const [participants, setParticipants] = useState([]);

  // Recording state
  const [isRecording, setIsRecording] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [currentRecordingId, setCurrentRecordingId] = useState(null);

  // Recording consent state
  const [showConsentDialog, setShowConsentDialog] = useState(false);
  const [consentState, setConsentState] = useState(null); // state disclosure data
  const [consentLoading, setConsentLoading] = useState(false);

  // Recording banner for non-hosts (recording indicator)
  const [recordingBanner, setRecordingBanner] = useState(false);
  const [recordingStartedBy, setRecordingStartedBy] = useState('');

  // Non-host consent dialog (when host starts recording)
  const [showParticipantConsentDialog, setShowParticipantConsentDialog] = useState(false);
  const [participantConsentData, setParticipantConsentData] = useState(null);

  // WebSocket reconnection state
  const [wsConnectionLost, setWsConnectionLost] = useState(false);
  const wsReconnectAttemptsRef = useRef(0);
  const wsReconnectTimeoutRef = useRef(null);
  const wsIntentionalCloseRef = useRef(false);

  // Screen recording state
  const [isScreenRecording, setIsScreenRecording] = useState(false);
  const [screenRecordingTime, setScreenRecordingTime] = useState(0);
  const [screenRecorder, setScreenRecorder] = useState(null);
  const [recordedChunks, setRecordedChunks] = useState([]);
  const [showScreenRecordingModal, setShowScreenRecordingModal] = useState(false);
  const [screenRecordingUrl, setScreenRecordingUrl] = useState('');
  const [screenRecordingUploading, setScreenRecordingUploading] = useState(false);
  const [recipientName, setRecipientName] = useState('');
  const [recipientEmail, setRecipientEmail] = useState('');
  const [generatingEmailSummary, setGeneratingEmailSummary] = useState(false);
  const [emailSummaryGenerated, setEmailSummaryGenerated] = useState(false);
  const screenRecordingTimerRef = useRef(null);
  const screenStreamRef = useRef(null);

  // Chat state
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [showChat, setShowChat] = useState(false);

  // Invite user state
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteName, setInviteName] = useState('');
  const [inviteSending, setInviteSending] = useState(false);
  const [inviteSuccess, setInviteSuccess] = useState(false);

  // Waiting room state
  const [participantId, setParticipantId] = useState(null);
  const [waitingParticipants, setWaitingParticipants] = useState([]);
  const [admissionRejected, setAdmissionRejected] = useState(false);
  const admissionPollRef = useRef(null);
  const waitingRoomPollRef = useRef(null);

  // Virtual background state
  const [virtualBgMode, setVirtualBgMode] = useState('none'); // 'none', 'blur', 'heavy-blur'
  const canvasRef = useRef(null);
  const canvasStreamRef = useRef(null);
  const bgAnimFrameRef = useRef(null);

  // Breakout room state
  const [showBreakoutPanel, setShowBreakoutPanel] = useState(false);
  const [breakoutRooms, setBreakoutRooms] = useState([]);
  const [currentBreakoutRoom, setCurrentBreakoutRoom] = useState(null);
  const [newBreakoutName, setNewBreakoutName] = useState('');

  // Breakout room media isolation: maps participantId -> breakoutRoomId or null
  const [participantBreakoutMap, setParticipantBreakoutMap] = useState({});

  // Refs
  const localVideoRef = useRef(null);
  const recordingTimerRef = useRef(null);

  // WebRTC refs
  const wsRef = useRef(null);
  const peerConnectionsRef = useRef({}); // {participantId: RTCPeerConnection}
  const remoteStreamsRef = useRef({}); // {participantId: MediaStream}
  const remoteVideoRefs = useRef({}); // {participantId: HTMLVideoElement ref}
  const localParticipantIdRef = useRef(null);
  const audioContextRef = useRef(null); // AudioContext for screen recording audio mixing
  const iceCandidateQueueRef = useRef([]); // Queued ICE candidates during WS disconnect

  // Remote streams state (for rendering)
  const [remoteStreams, setRemoteStreams] = useState({}); // {participantId: {stream, displayName, audioEnabled, videoEnabled}}

  // WebRTC configuration - fetched from server
  const [rtcConfig, setRtcConfig] = useState({
    iceServers: [
      { urls: 'stun:stun.l.google.com:19302' },
      { urls: 'stun:stun1.l.google.com:19302' },
    ]
  });

  // Fetch ICE servers (including TURN) from backend
  useEffect(() => {
    const fetchIceServers = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/v1/meetings/ice-servers`);
        if (response.ok) {
          const data = await response.json();
          if (data.iceServers && data.iceServers.length > 0) {
            setRtcConfig({ iceServers: data.iceServers });
            console.log('Loaded ICE servers:', data.iceServers.length, 'servers');
          }
        }
      } catch (err) {
        console.warn('Could not fetch ICE servers, using defaults:', err);
      }
    };
    fetchIceServers();
  }, []);

  // Cleanup blob URLs to prevent memory leaks (Issue 8)
  useEffect(() => {
    return () => {
      if (screenRecordingUrl && screenRecordingUrl.startsWith('blob:')) {
        URL.revokeObjectURL(screenRecordingUrl);
      }
    };
  }, [screenRecordingUrl]);

  // Fetch meeting info
  useEffect(() => {
    const fetchMeeting = async () => {
      try {
        setLoading(true);

        // First, get current user info from API if logged in
        let userId = null;
        let userName = 'Guest';
        const token = getToken();
        if (token) {
          try {
            // Get actual user ID from /users/me endpoint
            const userResponse = await fetch(`${API_BASE}/api/v1/users/me`, {
              headers: { 'Authorization': `Bearer ${token}` }
            });
            if (userResponse.ok) {
              const userData = await userResponse.json();
              userId = userData.id;
              userName = userData.full_name?.split(' ')[0] || userData.email?.split('@')[0] || 'Guest';
              setCurrentUserId(userId);
              setDisplayName(userName);
            } else {
              setDisplayName('Guest');
            }
          } catch {
            setDisplayName('Guest');
          }
        }

        const response = await fetch(`${API_BASE}/api/v1/meetings/join/${roomCode}`);

        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || 'Meeting not found');
        }

        const data = await response.json();
        setMeeting(data.meeting);

        // Determine if current user is the host by comparing user IDs
        const userIsHost = userId && data.meeting.host_user_id && userId === data.meeting.host_user_id;
        setIsHost(userIsHost);

        // Check if waiting room is enabled - only for non-hosts
        if (data.meeting.waiting_room_enabled && !userIsHost) {
          setInWaitingRoom(true);
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchMeeting();
  }, [roomCode]);

  // Initialize media on join
  const initializeMedia = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: true,
        audio: true
      });
      setLocalStream(stream);

      if (localVideoRef.current) {
        localVideoRef.current.srcObject = stream;
      }
      return stream;
    } catch (err) {
      console.error('Error accessing media devices:', err);
      // Try audio only
      try {
        const audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        setLocalStream(audioStream);
        setVideoEnabled(false);
        return audioStream;
      } catch (audioErr) {
        console.error('Error accessing audio:', audioErr);
        return null;
      }
    }
  };

  // ============================================================================
  // WEBRTC SIGNALING FUNCTIONS
  // ============================================================================

  // Connect to WebSocket signaling server
  const connectSignaling = useCallback((stream) => {
    // Reuse existing participant ID on reconnect, generate new one only on first connect
    const participantId = localParticipantIdRef.current || `p-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    localParticipantIdRef.current = participantId;

    // Determine WebSocket URL
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsHost = isProduction
      ? 'api.perenniaai.com'
      : (process.env.REACT_APP_API_URL?.replace(/^https?:\/\//, '') || 'localhost:8000');
    const token = getToken() || '';
    const wsUrl = `${wsProtocol}//${wsHost}/api/v1/meetings/ws/${roomCode}/${participantId}?name=${encodeURIComponent(displayName)}&token=${encodeURIComponent(token)}`;

    console.log('Connecting to signaling server:', wsUrl);

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('Connected to signaling server');
      // Flush queued ICE candidates from during disconnect
      if (iceCandidateQueueRef.current.length > 0) {
        console.log(`Flushing ${iceCandidateQueueRef.current.length} queued ICE candidates`);
        iceCandidateQueueRef.current.forEach(msg => {
          try { ws.send(JSON.stringify(msg)); } catch (e) { /* ignore */ }
        });
        iceCandidateQueueRef.current = [];
      }
      // Start ping to keep connection alive
      const pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, WS_PING_INTERVAL_MS);
      ws._pingInterval = pingInterval;
    };

    ws.onmessage = async (event) => {
      try {
        const message = JSON.parse(event.data);
        console.log('Signaling message:', message.type);

        switch (message.type) {
          case 'participants_list':
            // When we join, we receive the current participant list
            // Create offers to connect to existing participants
            for (const participant of message.participants) {
              if (participant.id !== participantId) {
                console.log('Creating offer for existing participant:', participant.id);
                await createPeerConnection(participant.id, participant.display_name, stream, true);
              }
            }
            break;

          case 'participant_joined':
            // New participant joined - they will send us an offer
            console.log('New participant joined:', message.participant_id);
            break;

          case 'participant_left':
            // Participant left - cleanup their connection
            console.log('Participant left:', message.participant_id);
            closePeerConnection(message.participant_id);
            break;

          case 'request_offer':
            // Another participant is requesting an offer from us
            console.log('Offer requested by:', message.from);
            await createPeerConnection(message.from, null, stream, true);
            break;

          case 'offer':
            // Received an offer - create answer
            console.log('Received offer from:', message.from);
            await handleOffer(message.from, message.sdp, stream);
            break;

          case 'answer':
            // Received an answer to our offer
            console.log('Received answer from:', message.from);
            await handleAnswer(message.from, message.sdp);
            break;

          case 'ice_candidate':
            // Received ICE candidate
            await handleIceCandidate(message.from, message.candidate);
            break;

          case 'participant_media_state':
            // Update participant's media state
            setRemoteStreams(prev => {
              if (prev[message.participant_id]) {
                return {
                  ...prev,
                  [message.participant_id]: {
                    ...prev[message.participant_id],
                    audioEnabled: message.audio ?? prev[message.participant_id].audioEnabled,
                    videoEnabled: message.video ?? prev[message.participant_id].videoEnabled
                  }
                };
              }
              return prev;
            });
            break;

          case 'chat':
            // Chat message received — skip if from self (already added locally)
            if (message.from !== localParticipantIdRef.current) {
              setChatMessages(prev => [...prev, {
                id: Date.now(),
                sender: message.sender_name,
                text: message.message,
                timestamp: new Date(message.timestamp)
              }]);
            }
            break;

          case 'connection_ack':
            // Server-verified host status
            console.log('Connection acknowledged, is_host:', message.is_host);
            setIsHost(message.is_host);
            break;

          case 'recording_state_changed':
            // Recording state broadcast from host via server
            if (message.recording) {
              setRecordingBanner(true);
              setRecordingStartedBy(message.started_by_name || 'Host');
              setIsRecording(true);
              // Show consent dialog for non-hosts
              if (!isHost) {
                setParticipantConsentData({
                  recording_id: message.recording_id,
                  consent_type: message.consent_type,
                  disclosure_script: message.disclosure_script
                });
                setShowParticipantConsentDialog(true);
              }
            } else {
              setRecordingBanner(false);
              setRecordingStartedBy('');
              setIsRecording(false);
              setShowParticipantConsentDialog(false);
            }
            break;

          case 'breakout_update':
            // Breakout room state changed - refresh the list
            fetchBreakoutRooms();
            if (message.action === 'closed' && currentBreakoutRoom === message.room_id) {
              setCurrentBreakoutRoom(null);
            }
            // Update participant-to-breakout mapping for media isolation
            if (message.action === 'participant_joined' && message.participant_id && message.room_id) {
              setParticipantBreakoutMap(prev => ({ ...prev, [message.participant_id]: message.room_id }));
            } else if (message.action === 'participant_left' && message.participant_id) {
              setParticipantBreakoutMap(prev => ({ ...prev, [message.participant_id]: null }));
            } else if (message.action === 'closed' && message.room_id) {
              // Clear all participants from this breakout room
              setParticipantBreakoutMap(prev => {
                const updated = { ...prev };
                Object.keys(updated).forEach(pid => {
                  if (updated[pid] === message.room_id) updated[pid] = null;
                });
                return updated;
              });
            }
            break;

          case 'pong':
            // Ping response - ignore
            break;

          default:
            console.log('Unknown message type:', message.type);
        }
      } catch (err) {
        console.error('Error handling signaling message:', err);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    ws.onclose = (event) => {
      console.log('WebSocket disconnected, code:', event.code);
      if (ws._pingInterval) {
        clearInterval(ws._pingInterval);
      }

      // Don't reconnect if intentional close (code 1000) or component unmounting
      if (event.code === 1000 || wsIntentionalCloseRef.current) {
        return;
      }

      // Exponential backoff reconnection
      const delays = [2000, 4000, 8000, 16000, 16000];

      if (wsReconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
        const delay = delays[Math.min(wsReconnectAttemptsRef.current, delays.length - 1)];
        console.log(`Reconnecting in ${delay/1000}s (attempt ${wsReconnectAttemptsRef.current + 1}/${MAX_RECONNECT_ATTEMPTS})`);
        setWsConnectionLost(true);

        wsReconnectTimeoutRef.current = setTimeout(() => {
          wsReconnectAttemptsRef.current += 1;
          if (stream) {
            connectSignaling(stream);
          }
        }, delay);
      } else {
        console.error('Max reconnection attempts reached');
        setWsConnectionLost(true);
      }
    };

    // Reset reconnect counter on successful connection
    wsReconnectAttemptsRef.current = 0;
    setWsConnectionLost(false);

    return ws;
  }, [roomCode, displayName, isHost]);

  // Create a peer connection to another participant
  const createPeerConnection = async (remoteParticipantId, remoteName, stream, createOffer = false) => {
    // Check if connection already exists
    if (peerConnectionsRef.current[remoteParticipantId]) {
      console.log('Peer connection already exists for:', remoteParticipantId);
      return peerConnectionsRef.current[remoteParticipantId];
    }

    console.log('Creating peer connection for:', remoteParticipantId);
    const pc = new RTCPeerConnection(rtcConfig);
    peerConnectionsRef.current[remoteParticipantId] = pc;

    // Add local tracks to the connection with simulcast for video
    if (stream) {
      stream.getTracks().forEach(track => {
        const sender = pc.addTrack(track, stream);

        // Configure simulcast encodings for video tracks (3 quality layers)
        if (track.kind === 'video' && sender) {
          try {
            const params = sender.getParameters();
            if (!params.encodings || params.encodings.length === 0) {
              params.encodings = [{}];
            }
            // Set up simulcast layers: low, medium, high
            params.encodings = [
              { rid: 'low', maxBitrate: 150000, scaleResolutionDownBy: 4.0 },
              { rid: 'medium', maxBitrate: 500000, scaleResolutionDownBy: 2.0 },
              { rid: 'high', maxBitrate: 1500000 },
            ];
            sender.setParameters(params).catch(err => {
              // Simulcast not supported in all browsers - fall back to single layer
              console.warn('Simulcast not supported, using single encoding:', err.message);
            });
          } catch (e) {
            console.warn('Could not configure simulcast:', e.message);
          }
        }
      });
    }

    // Handle incoming tracks (remote video/audio)
    pc.ontrack = (event) => {
      console.log('Received remote track from:', remoteParticipantId);
      const remoteStream = event.streams[0];
      remoteStreamsRef.current[remoteParticipantId] = remoteStream;

      setRemoteStreams(prev => ({
        ...prev,
        [remoteParticipantId]: {
          stream: remoteStream,
          displayName: remoteName || `Participant`,
          audioEnabled: true,
          videoEnabled: true
        }
      }));

      // Attach stream to video element if it exists
      setTimeout(() => {
        const videoEl = document.getElementById(`remote-video-${remoteParticipantId}`);
        if (videoEl && remoteStream) {
          videoEl.srcObject = remoteStream;
        }
      }, 100);

      // Monitor bandwidth and adapt quality for incoming streams
      if (pc.getReceivers) {
        const videoReceiver = pc.getReceivers().find(r => r.track?.kind === 'video');
        if (videoReceiver) {
          const monitorBandwidth = async () => {
            try {
              const stats = await pc.getStats(videoReceiver.track);
              stats.forEach(report => {
                if (report.type === 'inbound-rtp' && report.kind === 'video') {
                  const bitrate = report.bytesReceived ? (report.bytesReceived * 8) : 0;
                  // If bitrate is very low, the connection is struggling
                  if (bitrate > 0 && bitrate < 50000 && report.framesDecoded > 10) {
                    console.warn(`Low bandwidth from ${remoteParticipantId}: ${Math.round(bitrate/1000)}kbps`);
                  }
                }
              });
            } catch (e) { /* stats not available */ }
          };
          const bandwidthInterval = setInterval(monitorBandwidth, BANDWIDTH_CHECK_INTERVAL_MS);
          pc._bandwidthInterval = bandwidthInterval;
        }
      }
    };

    // Handle ICE candidates - queue if WebSocket not connected
    pc.onicecandidate = (event) => {
      if (event.candidate) {
        const candidateMsg = {
          type: 'ice_candidate',
          target: remoteParticipantId,
          candidate: event.candidate
        };
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify(candidateMsg));
        } else {
          // Queue for sending after reconnect
          iceCandidateQueueRef.current.push(candidateMsg);
        }
      }
    };

    // Handle connection state changes
    pc.onconnectionstatechange = () => {
      console.log(`Connection state with ${remoteParticipantId}:`, pc.connectionState);
      if (pc.connectionState === 'failed' || pc.connectionState === 'disconnected' || pc.connectionState === 'closed') {
        // Connection ended - cleanup (closePeerConnection also clears bandwidth interval)
        closePeerConnection(remoteParticipantId);
      }
    };

    // Create and send offer if we're initiating
    if (createOffer) {
      try {
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);

        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({
            type: 'offer',
            target: remoteParticipantId,
            sdp: pc.localDescription
          }));
        }
      } catch (err) {
        console.error('Error creating offer:', err);
      }
    }

    return pc;
  };

  // Handle incoming offer
  const handleOffer = async (fromParticipantId, sdp, stream) => {
    let pc = peerConnectionsRef.current[fromParticipantId];

    if (!pc) {
      pc = await createPeerConnection(fromParticipantId, null, stream, false);
    }

    try {
      await pc.setRemoteDescription(new RTCSessionDescription(sdp));
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);

      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({
          type: 'answer',
          target: fromParticipantId,
          sdp: pc.localDescription
        }));
      }
    } catch (err) {
      console.error('Error handling offer:', err);
    }
  };

  // Handle incoming answer
  const handleAnswer = async (fromParticipantId, sdp) => {
    const pc = peerConnectionsRef.current[fromParticipantId];
    if (pc) {
      try {
        await pc.setRemoteDescription(new RTCSessionDescription(sdp));
      } catch (err) {
        console.error('Error handling answer:', err);
      }
    }
  };

  // Handle incoming ICE candidate
  const handleIceCandidate = async (fromParticipantId, candidate) => {
    const pc = peerConnectionsRef.current[fromParticipantId];
    if (pc && candidate) {
      try {
        await pc.addIceCandidate(new RTCIceCandidate(candidate));
      } catch (err) {
        console.error('Error adding ICE candidate:', err);
      }
    }
  };

  // Close peer connection
  const closePeerConnection = (participantId) => {
    const pc = peerConnectionsRef.current[participantId];
    if (pc) {
      if (pc._bandwidthInterval) clearInterval(pc._bandwidthInterval);
      pc.close();
      delete peerConnectionsRef.current[participantId];
    }

    if (remoteStreamsRef.current[participantId]) {
      delete remoteStreamsRef.current[participantId];
    }

    setRemoteStreams(prev => {
      const newStreams = { ...prev };
      delete newStreams[participantId];
      return newStreams;
    });
  };

  // Send media state update via WebSocket
  const sendMediaState = (audio, video) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'media_state',
        audio,
        video
      }));
    }
  };

  // Cleanup WebRTC connections
  const cleanupWebRTC = useCallback(() => {
    // Close all peer connections
    Object.keys(peerConnectionsRef.current).forEach(participantId => {
      closePeerConnection(participantId);
    });

    // Close WebSocket
    if (wsRef.current) {
      if (wsRef.current._pingInterval) {
        clearInterval(wsRef.current._pingInterval);
      }
      wsRef.current.close();
      wsRef.current = null;
    }

    // Close AudioContext (safety net for screen recording cleanup)
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }

    // Clear ICE candidate queue
    iceCandidateQueueRef.current = [];
  }, []);

  // ============================================================================
  // END WEBRTC FUNCTIONS
  // ============================================================================

  // Join meeting
  const handleJoin = async () => {
    if (!displayName.trim()) {
      toast.warning('Please enter your name');
      return;
    }

    if (meeting?.password_protected && !password) {
      toast.warning('Please enter the meeting password');
      return;
    }

    // Initialize media
    const stream = await initializeMedia();
    setJoined(true);
    setInWaitingRoom(false);

    // Add self to participants
    setParticipants([{
      id: 'local',
      name: displayName,
      isLocal: true,
      audioEnabled: true,
      videoEnabled: true
    }]);

    // Verify password with backend before joining
    try {
      const passwordParam = password ? `?password=${encodeURIComponent(password)}` : '';
      const verifyResponse = await fetch(`${API_BASE}/api/v1/meetings/join/${roomCode}${passwordParam}`);
      if (!verifyResponse.ok) {
        const errorData = await verifyResponse.json();
        toast.error(errorData.detail || 'Failed to join meeting');
        setJoined(false);
        return;
      }
    } catch (err) {
      console.warn('Could not verify meeting access:', err);
    }

    // Notify backend of join (if authenticated)
    const token = getToken();
    if (token) {
      try {
        await fetch(`${API_BASE}/api/v1/meetings/rooms/${roomCode}/join`, {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({ display_name: displayName })
        });
      } catch (err) {
        console.warn('Could not notify backend of join:', err);
      }
    }

    // Connect to WebRTC signaling server
    if (stream) {
      connectSignaling(stream);
    }
  };

  // Toggle audio
  const toggleAudio = () => {
    if (!localStream) {
      toast.warning('Microphone not available. Check device permissions.');
      return;
    }
    const audioTrack = localStream.getAudioTracks()[0];
    if (audioTrack) {
      audioTrack.enabled = !audioTrack.enabled;
      setAudioEnabled(audioTrack.enabled);
      sendMediaState(audioTrack.enabled, videoEnabled);
    } else {
      toast.warning('No microphone detected.');
    }
  };

  // Toggle video
  const toggleVideo = () => {
    if (!localStream) {
      toast.warning('Camera not available. Check device permissions.');
      return;
    }
    const videoTrack = localStream.getVideoTracks()[0];
    if (videoTrack) {
      videoTrack.enabled = !videoTrack.enabled;
      setVideoEnabled(videoTrack.enabled);
      sendMediaState(audioEnabled, videoTrack.enabled);
    } else {
      toast.warning('No camera detected.');
    }
  };

  // Replace tracks on all active peer connections (for screen share toggle)
  const replaceTrackOnPeers = (oldTrack, newTrack) => {
    Object.values(peerConnectionsRef.current).forEach(pc => {
      const senders = pc.getSenders();
      const sender = senders.find(s => s.track && s.track.kind === oldTrack.kind);
      if (sender) {
        sender.replaceTrack(newTrack).catch(err => {
          console.error('Error replacing track on peer:', err);
        });
      }
    });
  };

  // Toggle screen share - replaces video track on all peer connections
  const toggleScreenShare = async () => {
    if (screenSharing) {
      // Stop screen sharing - switch back to camera
      try {
        const cameraStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        const cameraTrack = cameraStream.getVideoTracks()[0];

        // Replace screen track with camera track on all peers
        if (localStream) {
          const screenTrack = localStream.getVideoTracks()[0];
          if (screenTrack) {
            replaceTrackOnPeers(screenTrack, cameraTrack);
            screenTrack.stop();
          }

          // Update local stream: keep audio, replace video
          const audioTrack = localStream.getAudioTracks()[0];
          const newStream = new MediaStream();
          if (audioTrack) newStream.addTrack(audioTrack);
          newStream.addTrack(cameraTrack);
          setLocalStream(newStream);
          if (localVideoRef.current) {
            localVideoRef.current.srcObject = newStream;
          }
        }

        setScreenSharing(false);

        // Notify peers of media state change
        sendMediaState(audioEnabled, true);
      } catch (err) {
        console.error('Error reverting to camera:', err);
        // Fallback: full re-init
        await initializeMedia();
        setScreenSharing(false);
      }
    } else {
      try {
        const screenStream = await navigator.mediaDevices.getDisplayMedia({
          video: { cursor: 'always' }
        });
        const screenTrack = screenStream.getVideoTracks()[0];

        // Replace camera track with screen track on all peers
        if (localStream) {
          const cameraTrack = localStream.getVideoTracks()[0];
          if (cameraTrack) {
            replaceTrackOnPeers(cameraTrack, screenTrack);
          }

          // Update local stream: keep audio, replace video
          const audioTrack = localStream.getAudioTracks()[0];
          const newStream = new MediaStream();
          if (audioTrack) newStream.addTrack(audioTrack);
          newStream.addTrack(screenTrack);
          setLocalStream(newStream);
          if (localVideoRef.current) {
            localVideoRef.current.srcObject = newStream;
          }
        }

        setScreenSharing(true);

        // Handle when user stops sharing via browser UI
        screenTrack.onended = () => {
          toggleScreenShare();
        };
      } catch (err) {
        console.error('Error sharing screen:', err);
      }
    }
  };

  // Toggle recording (host only) - shows consent dialog before starting
  const toggleRecording = async () => {
    if (!isRecording) {
      // Fetch state recording rules to show consent dialog
      setConsentLoading(true);
      try {
        // Default to user's state or fall back to CA
        const stateCode = meeting?.state_code || 'CA';
        const response = await fetch(`${API_BASE}/api/v1/state-recording-rules/by-state/${stateCode}`);
        if (response.ok) {
          const stateData = await response.json();
          setConsentState(stateData);
        } else {
          // Default one-party consent
          setConsentState({
            state: stateCode,
            consent_type: 'one_party',
            script: 'This meeting may be recorded for quality and compliance purposes.',
            recording_required: true,
            requires_verbal_ack: false
          });
        }
        setShowConsentDialog(true);
      } catch (err) {
        console.error('Error fetching state recording rules:', err);
        // Show dialog with default
        setConsentState({
          state: 'unknown',
          consent_type: 'one_party',
          script: 'This meeting may be recorded for quality and compliance purposes.',
          recording_required: true,
          requires_verbal_ack: false
        });
        setShowConsentDialog(true);
      } finally {
        setConsentLoading(false);
      }
    } else {
      // Stop recording
      try {
        if (currentRecordingId) {
          await fetch(`${API_BASE}/api/v1/meetings/rooms/${meeting?.id}/recordings/${currentRecordingId}/stop`, {
            method: 'POST',
            headers: getAuthHeaders()
          });
        }

        // Broadcast recording stopped to all participants
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: 'recording_stopped' }));
        }
      } catch (err) {
        console.error('Error stopping recording:', err);
      }

      setIsRecording(false);
      setRecordingBanner(false);
      setCurrentRecordingId(null);
      if (recordingTimerRef.current) {
        clearInterval(recordingTimerRef.current);
      }
      setRecordingTime(0);
    }
  };

  // Start recording after consent acknowledged
  const startRecordingWithConsent = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/meetings/rooms/${meeting?.id}/recordings/start-with-consent`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          consent_type: consentState?.consent_type || 'one_party',
          state_code: consentState?.state || null,
          disclosure_script: consentState?.script || null
        })
      });

      const data = await response.json();

      if (response.ok && data.success) {
        setIsRecording(true);
        setCurrentRecordingId(data.recording.id);
        setShowConsentDialog(false);
        recordingTimerRef.current = setInterval(() => {
          setRecordingTime(t => t + 1);
        }, 1000);

        // Broadcast recording started to all participants via WebSocket
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({
            type: 'recording_started',
            recording_id: data.recording.id,
            consent_type: consentState?.consent_type,
            disclosure_script: consentState?.script
          }));
        }
      } else if (data.error === 'all_party_consent_required') {
        toast.warning(`Recording requires consent from all participants. Waiting for: ${data.pending_consent.map(p => p.display_name).join(', ')}`);
      } else {
        toast.error(data.message || 'Failed to start recording');
      }
    } catch (err) {
      console.error('Error starting recording with consent:', err);
      toast.error('Failed to start recording');
    }
  };

  // Submit participant consent (non-host)
  const submitParticipantConsent = async (consentGiven) => {
    try {
      if (participantConsentData?.recording_id) {
        await fetch(`${API_BASE}/api/v1/meetings/rooms/${meeting?.id}/recordings/${participantConsentData.recording_id}/consent`, {
          method: 'POST',
          headers: {
            ...getAuthHeaders(),
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            consent_given: consentGiven,
            method: 'dialog_click'
          })
        });
      }
    } catch (err) {
      console.error('Error submitting consent:', err);
    }
    setShowParticipantConsentDialog(false);
  };

  // ========================================================================
  // VIRTUAL BACKGROUND
  // ========================================================================

  const applyVirtualBackground = useCallback((mode) => {
    setVirtualBgMode(mode);

    if (mode === 'none') {
      // Stop canvas processing, revert to original camera stream
      if (bgAnimFrameRef.current) {
        cancelAnimationFrame(bgAnimFrameRef.current);
        bgAnimFrameRef.current = null;
      }
      if (canvasStreamRef.current) {
        canvasStreamRef.current.getTracks().forEach(t => t.stop());
        canvasStreamRef.current = null;
      }
      // Revert peer connections to original video track
      if (localStream) {
        const originalTrack = localStream.getVideoTracks()[0];
        if (originalTrack) {
          replaceTrackOnPeers(originalTrack, originalTrack); // no-op but ensures consistency
          if (localVideoRef.current) {
            localVideoRef.current.srcObject = localStream;
          }
        }
      }
      return;
    }

    // Start canvas processing
    if (!localStream) return;
    const videoTrack = localStream.getVideoTracks()[0];
    if (!videoTrack) return;

    const video = document.createElement('video');
    video.srcObject = new MediaStream([videoTrack]);
    video.muted = true;
    video.play();

    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');

    const blurAmount = mode === 'heavy-blur' ? '20px' : '8px';

    const processFrame = () => {
      if (!videoTrack.enabled || videoTrack.readyState === 'ended') {
        bgAnimFrameRef.current = requestAnimationFrame(processFrame);
        return;
      }

      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;

      // Apply blur filter to canvas context
      ctx.filter = `blur(${blurAmount})`;
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

      // Draw center portion sharp (rough person mask - center 60%)
      ctx.filter = 'none';
      const cx = canvas.width * 0.2;
      const cy = canvas.height * 0.05;
      const cw = canvas.width * 0.6;
      const ch = canvas.height * 0.9;
      ctx.drawImage(video, cx, cy, cw, ch, cx, cy, cw, ch);

      bgAnimFrameRef.current = requestAnimationFrame(processFrame);
    };

    video.onloadedmetadata = () => {
      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;

      // Capture the processed canvas as a stream
      const captureMethod = canvas.captureStream || canvas.mozCaptureStream;
      const processedStream = captureMethod.call(canvas, 30);
      canvasStreamRef.current = processedStream;
      const processedTrack = processedStream.getVideoTracks()[0];

      // Replace video track on all peers with processed track
      replaceTrackOnPeers(videoTrack, processedTrack);

      // Update local preview to show processed video
      const previewStream = new MediaStream();
      const audioTrack = localStream.getAudioTracks()[0];
      if (audioTrack) previewStream.addTrack(audioTrack);
      previewStream.addTrack(processedTrack);
      if (localVideoRef.current) {
        localVideoRef.current.srcObject = previewStream;
      }

      processFrame();
    };
  }, [localStream]);

  // Cleanup virtual background on unmount
  useEffect(() => {
    return () => {
      if (bgAnimFrameRef.current) {
        cancelAnimationFrame(bgAnimFrameRef.current);
      }
      if (canvasStreamRef.current) {
        canvasStreamRef.current.getTracks().forEach(t => t.stop());
      }
    };
  }, []);

  // Cycle through virtual background modes
  const cycleVirtualBg = () => {
    const modes = ['none', 'blur', 'heavy-blur'];
    const currentIdx = modes.indexOf(virtualBgMode);
    const nextMode = modes[(currentIdx + 1) % modes.length];
    applyVirtualBackground(nextMode);
  };

  // ========================================================================
  // BREAKOUT ROOMS
  // ========================================================================

  const fetchBreakoutRooms = useCallback(async () => {
    if (!meeting?.id) return;
    try {
      const response = await fetch(`${API_BASE}/api/v1/meetings/rooms/${meeting.id}/breakout-rooms`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setBreakoutRooms(data.breakout_rooms || []);
      }
    } catch (err) {
      console.error('Error fetching breakout rooms:', err);
    }
  }, [meeting?.id]);

  const createBreakoutRoom = async () => {
    if (!newBreakoutName.trim() || !meeting?.id) return;
    try {
      const response = await fetch(`${API_BASE}/api/v1/meetings/rooms/${meeting.id}/breakout-rooms`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ room_name: newBreakoutName.trim() })
      });
      if (response.ok) {
        const data = await response.json();
        setNewBreakoutName('');
        fetchBreakoutRooms();

        // Broadcast via WebSocket
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({
            type: 'breakout_created',
            room: data.breakout_room
          }));
        }
      }
    } catch (err) {
      console.error('Error creating breakout room:', err);
    }
  };

  const joinBreakoutRoom = async (breakoutId) => {
    if (!meeting?.id) return;
    try {
      const response = await fetch(`${API_BASE}/api/v1/meetings/rooms/${meeting.id}/breakout-rooms/${breakoutId}/join`, {
        method: 'POST',
        headers: getAuthHeaders()
      });
      if (response.ok) {
        setCurrentBreakoutRoom(breakoutId);
        fetchBreakoutRooms();

        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({
            type: 'breakout_join',
            room_id: breakoutId
          }));
        }
      }
    } catch (err) {
      console.error('Error joining breakout room:', err);
    }
  };

  const leaveBreakoutRoom = async () => {
    if (!meeting?.id || !currentBreakoutRoom) return;
    try {
      await fetch(`${API_BASE}/api/v1/meetings/rooms/${meeting.id}/breakout-rooms/${currentBreakoutRoom}/leave`, {
        method: 'POST',
        headers: getAuthHeaders()
      });

      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({
          type: 'breakout_leave',
          room_id: currentBreakoutRoom
        }));
      }

      setCurrentBreakoutRoom(null);
      fetchBreakoutRooms();
    } catch (err) {
      console.error('Error leaving breakout room:', err);
    }
  };

  const closeBreakoutRoom = async (breakoutId) => {
    if (!meeting?.id) return;
    try {
      await fetch(`${API_BASE}/api/v1/meetings/rooms/${meeting.id}/breakout-rooms/${breakoutId}/close`, {
        method: 'POST',
        headers: getAuthHeaders()
      });

      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({
          type: 'breakout_closed',
          room_id: breakoutId
        }));
      }

      if (currentBreakoutRoom === breakoutId) {
        setCurrentBreakoutRoom(null);
      }
      fetchBreakoutRooms();
    } catch (err) {
      console.error('Error closing breakout room:', err);
    }
  };

  // ========================================================================
  // SFU MODE DETECTION (informational only — no UI badge)
  // ========================================================================

  // Log SFU recommendation when participant count is high (no UI state changes)
  useEffect(() => {
    const participantCount = 1 + Object.keys(remoteStreams).length;
    if (participantCount >= 5) {
      console.info(`Meeting has ${participantCount} participants — SFU mode would improve performance if available`);
    }
  }, [Object.keys(remoteStreams).length]);

  // ========================================================================
  // BREAKOUT ROOM MEDIA ISOLATION
  // ========================================================================

  // Filter remote streams to only show participants in the same breakout room (or main room)
  const visibleStreams = useMemo(() => {
    // If not in any breakout room, show all participants NOT in a breakout room
    // If in a breakout room, show only participants in the same breakout room
    if (!currentBreakoutRoom) {
      // In main room: show participants who are not in any breakout room
      const filtered = {};
      Object.entries(remoteStreams).forEach(([pid, data]) => {
        if (!participantBreakoutMap[pid]) {
          filtered[pid] = data;
        }
      });
      return filtered;
    } else {
      // In a breakout room: show only participants in the same breakout room
      const filtered = {};
      Object.entries(remoteStreams).forEach(([pid, data]) => {
        if (participantBreakoutMap[pid] === currentBreakoutRoom) {
          filtered[pid] = data;
        }
      });
      return filtered;
    }
  }, [remoteStreams, currentBreakoutRoom, participantBreakoutMap]);

  // Mute audio tracks for participants not in our visible set
  useEffect(() => {
    Object.entries(remoteStreams).forEach(([pid, data]) => {
      const isVisible = pid in visibleStreams;
      if (data.stream) {
        data.stream.getAudioTracks().forEach(track => {
          track.enabled = isVisible;
        });
      }
    });
  }, [visibleStreams, remoteStreams]);

  // Send chat message
  const sendChatMessage = () => {
    if (!chatInput.trim()) return;

    // Send via WebSocket if connected
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'chat',
        message: chatInput
      }));
    }

    // Also add to local state immediately for responsiveness
    setChatMessages(prev => [...prev, {
      id: Date.now(),
      sender: displayName,
      text: chatInput,
      timestamp: new Date()
    }]);
    setChatInput('');
  };

  // Send meeting invite via email
  const sendMeetingInvite = async () => {
    if (!inviteEmail.trim()) return;

    setInviteSending(true);
    setInviteSuccess(false);

    try {
      const token = getToken();
      const joinUrl = `${window.location.origin}/meeting/${roomCode}`;

      const response = await fetch(`${API_BASE}/api/v1/meetings/rooms/${meeting?.id}/invite`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          email: inviteEmail,
          name: inviteName || inviteEmail.split('@')[0],
          join_url: joinUrl,
          meeting_name: meeting?.room_name || 'Video Meeting',
          host_name: displayName
        })
      });

      if (response.ok) {
        setInviteSuccess(true);
        setTimeout(() => {
          setShowInviteModal(false);
          setInviteEmail('');
          setInviteName('');
          setInviteSuccess(false);
        }, 2000);
      } else {
        let errorMessage = 'Failed to send invite';
        try {
          const errorData = await response.json();
          errorMessage = errorData.detail || errorData.message || errorData.error || JSON.stringify(errorData);
        } catch (parseErr) {
          errorMessage = `Server error (${response.status})`;
        }
        toast.error(errorMessage);
      }
    } catch (err) {
      console.error('Error sending invite:', err);
      toast.error('Failed to send invite: ' + (err.message || 'Network error'));
    } finally {
      setInviteSending(false);
    }
  };

  // Pre-fill invite from meeting's linked lead/loan
  useEffect(() => {
    if (meeting?.lead_email) {
      setInviteEmail(meeting.lead_email);
      setInviteName(meeting.lead_name || '');
    } else if (meeting?.borrower_email) {
      setInviteEmail(meeting.borrower_email);
      setInviteName(meeting.borrower_name || '');
    }
  }, [meeting]);

  // Request to join waiting room (for guests)
  const requestToJoin = async () => {
    if (!displayName.trim()) {
      toast.warning('Please enter your name');
      return;
    }

    try {
      const response = await fetch(`${API_BASE}/api/v1/meetings/rooms/${meeting?.id}/waiting-room/join`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          display_name: displayName,
          email: null
        })
      });

      if (response.ok) {
        const data = await response.json();
        setParticipantId(data.participant_id);
        setInWaitingRoom(true);
        // Start polling for admission
        startAdmissionPolling(data.participant_id);
      } else {
        const errorData = await response.json();
        toast.error(errorData.detail || 'Failed to join waiting room');
      }
    } catch (err) {
      console.error('Error requesting to join:', err);
      toast.error('Failed to join meeting');
    }
  };

  // Poll for admission status (guest side)
  const startAdmissionPolling = (pId) => {
    if (admissionPollRef.current) {
      clearInterval(admissionPollRef.current);
    }

    const pollStartTime = Date.now();
    const ADMISSION_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes

    admissionPollRef.current = setInterval(async () => {
      // Timeout after 5 minutes of waiting
      if (Date.now() - pollStartTime > ADMISSION_TIMEOUT_MS) {
        clearInterval(admissionPollRef.current);
        setInWaitingRoom(false);
        toast.error('Waiting room request timed out. Please try joining again.');
        return;
      }

      try {
        const response = await fetch(
          `${API_BASE}/api/v1/meetings/rooms/${meeting?.id}/waiting-room/status/${pId}`
        );
        if (response.ok) {
          const data = await response.json();
          if (data.admitted) {
            // Admitted! Join the meeting
            clearInterval(admissionPollRef.current);
            const stream = await initializeMedia();
            setJoined(true);
            setInWaitingRoom(false);
            setParticipants([{
              id: 'local',
              name: displayName,
              isLocal: true,
              audioEnabled: true,
              videoEnabled: true
            }]);
            // Connect to WebRTC signaling server
            if (stream) {
              connectSignaling(stream);
            }
          } else if (data.rejected) {
            clearInterval(admissionPollRef.current);
            setAdmissionRejected(true);
            setInWaitingRoom(false);
          }
        }
      } catch (err) {
        console.error('Error polling admission status:', err);
      }
    }, 2000); // Poll every 2 seconds
  };

  // Poll for waiting participants (host side)
  const startWaitingRoomPolling = useCallback(() => {
    if (waitingRoomPollRef.current) {
      clearInterval(waitingRoomPollRef.current);
    }

    const poll = async () => {
      try {
        const response = await fetch(
          `${API_BASE}/api/v1/meetings/rooms/${meeting?.id}/waiting-room`,
          { headers: getAuthHeaders() }
        );
        if (response.ok) {
          const data = await response.json();
          setWaitingParticipants(data.participants || []);
        }
      } catch (err) {
        console.error('Error polling waiting room:', err);
      }
    };

    poll(); // Initial poll
    waitingRoomPollRef.current = setInterval(poll, 3000); // Poll every 3 seconds
  }, [meeting?.id, getAuthHeaders]);

  // Start polling when host joins
  useEffect(() => {
    if (isHost && joined && meeting?.id) {
      startWaitingRoomPolling();
    }
    return () => {
      if (waitingRoomPollRef.current) {
        clearInterval(waitingRoomPollRef.current);
      }
    };
  }, [isHost, joined, meeting?.id, startWaitingRoomPolling]);

  // Cleanup admission polling on unmount
  useEffect(() => {
    return () => {
      if (admissionPollRef.current) {
        clearInterval(admissionPollRef.current);
      }
    };
  }, []);

  // Admit a participant
  const admitParticipant = async (pId) => {
    try {
      const response = await fetch(
        `${API_BASE}/api/v1/meetings/rooms/${meeting?.id}/waiting-room/${pId}`,
        {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({ action: 'admit' })
        }
      );
      if (response.ok) {
        setWaitingParticipants(prev => prev.filter(p => p.id !== pId));
      }
    } catch (err) {
      console.error('Error admitting participant:', err);
    }
  };

  // Reject a participant
  const rejectParticipant = async (pId) => {
    try {
      const response = await fetch(
        `${API_BASE}/api/v1/meetings/rooms/${meeting?.id}/waiting-room/${pId}`,
        {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({ action: 'reject' })
        }
      );
      if (response.ok) {
        setWaitingParticipants(prev => prev.filter(p => p.id !== pId));
      }
    } catch (err) {
      console.error('Error rejecting participant:', err);
    }
  };

  // Admit all waiting participants
  const admitAllParticipants = async () => {
    try {
      const response = await fetch(
        `${API_BASE}/api/v1/meetings/rooms/${meeting?.id}/waiting-room/admit-all`,
        {
          method: 'POST',
          headers: getAuthHeaders()
        }
      );
      if (response.ok) {
        setWaitingParticipants([]);
      }
    } catch (err) {
      console.error('Error admitting all participants:', err);
    }
  };

  // Start screen recording
  const startScreenRecording = async () => {
    try {
      // Get screen capture with audio
      const screenStream = await navigator.mediaDevices.getDisplayMedia({
        video: {
          cursor: 'always'
        },
        audio: true
      });

      // Try to get microphone audio separately
      let audioStream;
      try {
        audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch (e) {
        console.warn('Could not capture microphone audio:', e);
      }

      // Combine streams if both available
      let combinedStream;
      if (audioStream) {
        // Close any previous AudioContext to prevent leaks
        if (audioContextRef.current) {
          audioContextRef.current.close().catch(() => {});
        }
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        const audioContext = new AudioCtx();
        audioContextRef.current = audioContext;
        const destination = audioContext.createMediaStreamDestination();

        // Add screen audio if present
        const screenAudioTracks = screenStream.getAudioTracks();
        if (screenAudioTracks.length > 0) {
          const screenSource = audioContext.createMediaStreamSource(new MediaStream([screenAudioTracks[0]]));
          screenSource.connect(destination);
        }

        // Add microphone audio
        const micSource = audioContext.createMediaStreamSource(audioStream);
        micSource.connect(destination);

        combinedStream = new MediaStream([
          ...screenStream.getVideoTracks(),
          ...destination.stream.getAudioTracks()
        ]);
      } else {
        combinedStream = screenStream;
      }

      screenStreamRef.current = screenStream;

      // Setup MediaRecorder with browser-compatible mimeType
      const mimeType = MediaRecorder.isTypeSupported('video/webm;codecs=vp9,opus')
        ? 'video/webm;codecs=vp9,opus'
        : MediaRecorder.isTypeSupported('video/webm;codecs=vp8,opus')
          ? 'video/webm;codecs=vp8,opus'
          : MediaRecorder.isTypeSupported('video/webm')
            ? 'video/webm'
            : 'video/mp4';
      const recorder = new MediaRecorder(combinedStream, { mimeType });

      const chunks = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunks.push(e.data);
        }
      };

      recorder.onstop = async () => {
        // Clear timer
        if (screenRecordingTimerRef.current) {
          clearInterval(screenRecordingTimerRef.current);
        }

        // Create blob from recorded chunks
        const blob = new Blob(chunks, { type: recorder.mimeType || 'video/webm' });
        setRecordedChunks(chunks);

        // Upload the recording
        await uploadScreenRecording(blob);
      };

      // Handle stream ended (user clicked "Stop sharing" in browser)
      screenStream.getVideoTracks()[0].onended = () => {
        stopScreenRecording();
      };

      recorder.start(1000); // Collect data every second
      setScreenRecorder(recorder);
      setIsScreenRecording(true);

      // Start timer
      screenRecordingTimerRef.current = setInterval(() => {
        setScreenRecordingTime(t => t + 1);
      }, 1000);

    } catch (err) {
      console.error('Error starting screen recording:', err);
      toast.error('Failed to start screen recording. Please make sure you allowed screen sharing.');
    }
  };

  // Stop screen recording
  const stopScreenRecording = () => {
    if (screenRecorder && screenRecorder.state !== 'inactive') {
      screenRecorder.stop();
    }
    if (screenStreamRef.current) {
      screenStreamRef.current.getTracks().forEach(track => track.stop());
    }
    // Close AudioContext to prevent memory leak
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    setIsScreenRecording(false);
    setScreenRecordingUploading(true);
  };

  // Upload screen recording and get shareable link
  const uploadScreenRecording = async (blob) => {
    // Revoke previous blob URL if any to prevent memory leak
    if (screenRecordingUrl && screenRecordingUrl.startsWith('blob:')) {
      URL.revokeObjectURL(screenRecordingUrl);
    }
    try {
      const token = getToken();
      const formData = new FormData();
      formData.append('file', blob, `screen-recording-${Date.now()}.webm`);
      formData.append('meeting_id', meeting?.id || '');
      formData.append('room_code', roomCode);

      const response = await fetch(`${API_BASE}/api/v1/meetings/screen-recordings/upload`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData
      });

      if (response.ok) {
        const data = await response.json();
        setScreenRecordingUrl(data.share_url);
        setShowScreenRecordingModal(true);
      } else {
        // Fallback: create local blob URL
        const localUrl = URL.createObjectURL(blob);
        setScreenRecordingUrl(localUrl);
        setShowScreenRecordingModal(true);
      }
    } catch (err) {
      console.error('Error uploading screen recording:', err);
      // Fallback: create local blob URL
      const localUrl = URL.createObjectURL(new Blob(recordedChunks, { type: 'video/webm' }));
      setScreenRecordingUrl(localUrl);
      setShowScreenRecordingModal(true);
    } finally {
      setScreenRecordingUploading(false);
      setScreenRecordingTime(0);
    }
  };

  // Copy screen recording link and log to conversation
  const copyScreenRecordingLink = async () => {
    try {
      await navigator.clipboard.writeText(screenRecordingUrl);

      // Log to conversation/activity if recipient name provided
      if (recipientName.trim()) {
        const token = getToken();
        try {
          await fetch(`${API_BASE}/api/v1/activities/`, {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({
              activity_type: 'screen_recording',
              description: `Screen recording sent to ${recipientName}`,
              loan_id: meeting?.loan_id,
              lead_id: meeting?.lead_id,
              metadata: {
                recording_url: screenRecordingUrl,
                recipient_name: recipientName,
                meeting_room: roomCode
              }
            })
          });
        } catch (e) {
          console.warn('Could not log activity:', e);
        }

        // Also add to local chat
        setChatMessages(prev => [...prev, {
          id: Date.now(),
          sender: 'System',
          text: `Screen recording sent to ${recipientName}`,
          timestamp: new Date()
        }]);
      }

      toast.success('Link copied to clipboard!');
    } catch (err) {
      console.error('Failed to copy link:', err);
      toast.error('Failed to copy link. Please copy manually from the input above.');
    }
  };

  // Download screen recording locally
  const downloadScreenRecording = () => {
    const meetingName = (meeting?.room_name || 'meeting').replace(/[^a-zA-Z0-9-_ ]/g, '').replace(/\s+/g, '-');
    const datestamp = new Date().toISOString().slice(0, 10);
    const a = document.createElement('a');
    a.href = screenRecordingUrl;
    a.download = `${meetingName}-recording-${datestamp}.webm`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  // Generate AI email summary from recording
  const generateEmailSummary = async () => {
    if (!recipientEmail) {
      toast.warning('Please enter a recipient email address');
      return;
    }

    setGeneratingEmailSummary(true);
    try {
      const token = getToken();
      const response = await fetch(`${API_BASE}/api/v1/email-drafts/generate-call-summary`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          lead_id: meeting?.lead_id || null,
          loan_id: meeting?.loan_id || null,
          recipient_email: recipientEmail,
          recipient_name: recipientName || 'Valued Client',
          meeting_name: meeting?.name || 'Video Call',
          recording_url: screenRecordingUrl,
          call_duration_seconds: screenRecordingTime
        })
      });

      if (response.ok) {
        const data = await response.json();
        setEmailSummaryGenerated(true);
        toast.success('Email summary draft created! Check the Email tab of the borrower\'s profile page.');

        // Log the activity
        try {
          await fetch(`${API_BASE}/api/v1/activities/`, {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({
              activity_type: 'email_draft',
              description: `Call summary email draft created for ${recipientName || recipientEmail}`,
              loan_id: meeting?.loan_id,
              lead_id: meeting?.lead_id,
              metadata: {
                draft_id: data.draft_id,
                subject: data.subject,
                recording_url: screenRecordingUrl
              }
            })
          });
        } catch (e) {
          console.warn('Could not log activity:', e);
        }
      } else {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to generate email summary');
      }
    } catch (err) {
      console.error('Error generating email summary:', err);
      toast.error('Failed to generate email summary: ' + err.message);
    } finally {
      setGeneratingEmailSummary(false);
    }
  };

  // Leave meeting
  const leaveMeeting = () => {
    // Signal intentional close to prevent reconnection
    wsIntentionalCloseRef.current = true;
    if (wsReconnectTimeoutRef.current) {
      clearTimeout(wsReconnectTimeoutRef.current);
    }

    // Close WebSocket with code 1000 (intentional)
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.close(1000, 'User left meeting');
    }

    // Cleanup WebRTC connections
    cleanupWebRTC();

    if (localStream) {
      localStream.getTracks().forEach(track => track.stop());
    }
    if (screenStreamRef.current) {
      screenStreamRef.current.getTracks().forEach(track => track.stop());
    }
    if (recordingTimerRef.current) {
      clearInterval(recordingTimerRef.current);
    }
    if (screenRecordingTimerRef.current) {
      clearInterval(screenRecordingTimerRef.current);
    }

    // Try to close the browser tab/window
    // window.close() only works if the window was opened by JavaScript
    // For tabs opened directly, we'll fallback to navigation
    try {
      window.close();
      // If window.close() didn't work (tab wasn't opened by script),
      // fallback to navigation after a brief delay
      setTimeout(() => {
        if (!window.closed) {
          navigate('/video-meetings');
        }
      }, 100);
    } catch (e) {
      navigate('/video-meetings');
    }
  };

  // Format recording time
  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  // Attach stream to video element when stream or joined state changes
  useEffect(() => {
    if (localStream && localVideoRef.current) {
      localVideoRef.current.srcObject = localStream;
    }
  }, [localStream, joined]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      wsIntentionalCloseRef.current = true;
      if (wsReconnectTimeoutRef.current) {
        clearTimeout(wsReconnectTimeoutRef.current);
      }

      // Cleanup WebRTC
      cleanupWebRTC();

      if (localStream) {
        localStream.getTracks().forEach(track => track.stop());
      }
      if (recordingTimerRef.current) {
        clearInterval(recordingTimerRef.current);
      }
    };
  }, [localStream, cleanupWebRTC]);

  // Loading state
  if (loading) {
    return (
      <div className="meeting-room-container">
        <div className="meeting-loading">
          <div className="loading-spinner"></div>
          <p>Loading meeting...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="meeting-room-container">
        <div className="meeting-error">
          <span className="error-icon">!</span>
          <h2>Unable to Join Meeting</h2>
          <p>{error}</p>
          <button className="back-btn" onClick={() => navigate('/video-meetings')}>
            Back to Meetings
          </button>
        </div>
      </div>
    );
  }

  // Rejected state
  if (admissionRejected) {
    return (
      <div className="meeting-room-container">
        <div className="meeting-error">
          <span className="error-icon">!</span>
          <h2>Access Denied</h2>
          <p>The host has not admitted you to this meeting.</p>
          <button className="back-btn" onClick={() => window.close()}>
            Close
          </button>
        </div>
      </div>
    );
  }

  // Waiting room
  if (inWaitingRoom && !joined) {
    return (
      <div className="meeting-room-container">
        <div className="waiting-room">
          <div className="waiting-room-content">
            <div className="meeting-info">
              <h2>{sanitizeText(meeting?.room_name)}</h2>
              <span className="meeting-status">Waiting Room</span>
            </div>

            <div className="waiting-message">
              <div className="waiting-spinner"></div>
              <p>Please wait for the host to admit you</p>
            </div>

            <div className="preview-section">
              <div className="video-preview">
                <video ref={localVideoRef} autoPlay muted playsInline />
                {!videoEnabled && (
                  <div className="video-off-placeholder">
                    <span className="avatar">{displayName?.[0]?.toUpperCase() || '?'}</span>
                  </div>
                )}
              </div>
              <div className="preview-controls">
                <button
                  className={`control-btn ${!audioEnabled ? 'off' : ''}`}
                  onClick={toggleAudio}
                >
                  {audioEnabled ? '🎤' : '🔇'}
                </button>
                <button
                  className={`control-btn ${!videoEnabled ? 'off' : ''}`}
                  onClick={toggleVideo}
                >
                  {videoEnabled ? '📹' : '📵'}
                </button>
              </div>
            </div>

            <button className="leave-btn" onClick={() => navigate('/video-meetings')}>
              Leave
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Pre-join screen
  if (!joined) {
    return (
      <div className="meeting-room-container">
        <div className="pre-join">
          <div className="pre-join-content">
            <div className="meeting-info">
              <h2>{sanitizeText(meeting?.room_name)}</h2>
              <p className="meeting-type">{meeting?.meeting_type?.replace(/_/g, ' ')}</p>
            </div>

            <div className="preview-section">
              <div className="video-preview large">
                <video ref={localVideoRef} autoPlay muted playsInline />
                {!videoEnabled && (
                  <div className="video-off-placeholder">
                    <span className="avatar">{displayName?.[0]?.toUpperCase() || '?'}</span>
                  </div>
                )}
              </div>
              <div className="preview-controls">
                <button
                  className={`control-btn ${!audioEnabled ? 'off' : ''}`}
                  onClick={() => {
                    initializeMedia().then(() => toggleAudio());
                  }}
                >
                  {audioEnabled ? '🎤' : '🔇'}
                </button>
                <button
                  className={`control-btn ${!videoEnabled ? 'off' : ''}`}
                  onClick={() => {
                    initializeMedia().then(() => toggleVideo());
                  }}
                >
                  {videoEnabled ? '📹' : '📵'}
                </button>
              </div>
            </div>

            <div className="join-form">
              <div className="form-group">
                <label>Your Name</label>
                <input
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="Enter your name"
                />
              </div>

              {meeting?.password_protected && (
                <div className="form-group">
                  <label>Meeting Password</label>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter meeting password"
                  />
                </div>
              )}

              {isHost ? (
                <button className="join-btn" onClick={handleJoin}>
                  Start Meeting
                </button>
              ) : (
                <button className="join-btn" onClick={requestToJoin}>
                  Request to Join
                </button>
              )}
              {!isHost && (
                <p className="join-note">You will be placed in a waiting room until the host admits you.</p>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // In-meeting view
  return (
    <div className="meeting-room-container in-meeting">
      {/* Header */}
      <div className="meeting-header">
        <div className="header-left">
          <h3>{sanitizeText(meeting?.room_name)}</h3>
          <span className="room-code">{roomCode}</span>
        </div>
        <div className="header-center">
          {isRecording && (
            <div className="recording-indicator">
              <span className="rec-dot"></span>
              REC {formatTime(recordingTime)}
            </div>
          )}
          {isScreenRecording && (
            <div className="recording-indicator screen-rec">
              <span className="rec-dot"></span>
              SCREEN REC {formatTime(screenRecordingTime)}
            </div>
          )}
        </div>
        <div className="header-right">
          <span className="participant-count">
            👥 {1 + Object.keys(visibleStreams).length}
          </span>
        </div>
      </div>

      {/* Connection Lost Banner */}
      {wsConnectionLost && (
        <div className="connection-lost-banner" style={{
          background: '#ef4444', color: 'white', padding: '8px 16px',
          textAlign: 'center', fontSize: '14px', fontWeight: '600'
        }}>
          {wsReconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS
            ? `Connection lost — checking connection... (attempt ${wsReconnectAttemptsRef.current + 1}/${MAX_RECONNECT_ATTEMPTS})`
            : 'Unable to reconnect. Please check your internet and refresh the page.'}
        </div>
      )}

      {/* Recording Banner for ALL participants */}
      {recordingBanner && !isHost && (
        <div className="recording-banner" style={{
          background: '#dc2626', color: 'white', padding: '8px 16px',
          textAlign: 'center', fontSize: '14px', fontWeight: '600',
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px'
        }}>
          <span className="rec-dot" style={{
            width: '10px', height: '10px', borderRadius: '50%',
            background: 'white', display: 'inline-block',
            animation: 'pulse 1.5s infinite'
          }}></span>
          Recording in progress — started by {recordingStartedBy}
        </div>
      )}

      {/* Video Grid */}
      <div className="video-grid">
        <div className="video-container local">
          <video
            ref={localVideoRef}
            autoPlay
            muted
            playsInline
          />
          {!videoEnabled && (
            <div className="video-off-overlay">
              <span className="avatar large">{displayName?.[0]?.toUpperCase()}</span>
            </div>
          )}
          <div className="video-label">
            <span>{displayName} (You)</span>
            {!audioEnabled && <span className="muted-icon">🔇</span>}
          </div>
        </div>

        {/* Remote participants with WebRTC video streams */}
        {Object.entries(visibleStreams).map(([participantId, participantData]) => (
          <div key={participantId} className="video-container remote">
            <video
              id={`remote-video-${participantId}`}
              autoPlay
              playsInline
              ref={el => {
                if (el && participantData.stream) {
                  el.srcObject = participantData.stream;
                }
              }}
            />
            {!participantData.videoEnabled && (
              <div className="video-off-overlay">
                <span className="avatar large">
                  {participantData.displayName?.[0]?.toUpperCase() || '?'}
                </span>
              </div>
            )}
            <div className="video-label">
              <span>{sanitizeText(participantData.displayName || 'Participant')}</span>
              {!participantData.audioEnabled && <span className="muted-icon">🔇</span>}
            </div>
          </div>
        ))}
      </div>

      {/* Controls */}
      <div className="meeting-controls">
        <div className="controls-left">
          <button
            className={`control-btn ${!audioEnabled ? 'off' : ''}`}
            onClick={toggleAudio}
            title={audioEnabled ? 'Mute' : 'Unmute'}
          >
            {audioEnabled ? '🎤' : '🔇'}
            <span className="btn-label">{audioEnabled ? 'Mute' : 'Unmute'}</span>
          </button>

          <button
            className={`control-btn ${!videoEnabled ? 'off' : ''}`}
            onClick={toggleVideo}
            title={videoEnabled ? 'Stop Video' : 'Start Video'}
          >
            {videoEnabled ? '📹' : '📵'}
            <span className="btn-label">{videoEnabled ? 'Stop' : 'Start'}</span>
          </button>
        </div>

        <div className="controls-center">
          <button
            className={`control-btn ${screenSharing ? 'active' : ''}`}
            onClick={toggleScreenShare}
            title="Share Screen"
          >
            🖥️
            <span className="btn-label">{screenSharing ? 'Stop Share' : 'Share'}</span>
          </button>

          {isHost && meeting?.recording_enabled && (
            <button
              className={`control-btn ${isRecording ? 'recording' : ''}`}
              onClick={toggleRecording}
              title={isRecording ? 'Stop Recording' : 'Start Recording'}
            >
              {isRecording ? '⏹️' : '🔴'}
              <span className="btn-label">{isRecording ? 'Stop Rec' : 'Record'}</span>
            </button>
          )}

          <button
            className={`control-btn ${showChat ? 'active' : ''}`}
            onClick={() => setShowChat(!showChat)}
            title="Chat"
          >
            💬
            <span className="btn-label">Chat</span>
          </button>

          <button
            className="control-btn invite"
            onClick={() => setShowInviteModal(true)}
            title="Add User"
          >
            👤+
            <span className="btn-label">Add User</span>
          </button>

          <button
            className={`control-btn screen-record ${isScreenRecording ? 'recording' : ''}`}
            onClick={isScreenRecording ? stopScreenRecording : startScreenRecording}
            title={isScreenRecording ? 'Stop Screen Recording' : 'Record Screen'}
            disabled={screenRecordingUploading}
          >
            {screenRecordingUploading ? '⏳' : isScreenRecording ? '⏹️' : '⏺️'}
            <span className="btn-label">
              {screenRecordingUploading ? 'Processing...' : isScreenRecording ? 'Stop' : 'Record'}
            </span>
          </button>

          <button
            className={`control-btn virtual-bg ${virtualBgMode !== 'none' ? 'active' : ''}`}
            onClick={cycleVirtualBg}
            title={virtualBgMode === 'none' ? 'Enable Background Blur' : virtualBgMode === 'blur' ? 'Heavy Blur' : 'Disable Blur'}
          >
            {virtualBgMode === 'none' ? '🌄' : virtualBgMode === 'blur' ? '🔵' : '🟣'}
            <span className="btn-label">
              {virtualBgMode === 'none' ? 'BG Blur' : virtualBgMode === 'blur' ? 'Blur+' : 'BG Off'}
            </span>
          </button>

          {isHost && (
            <button
              className={`control-btn ${showBreakoutPanel ? 'active' : ''}`}
              onClick={() => { setShowBreakoutPanel(!showBreakoutPanel); if (!showBreakoutPanel) fetchBreakoutRooms(); }}
              title="Breakout Rooms"
            >
              🏠
              <span className="btn-label">Breakout</span>
            </button>
          )}
        </div>

        <div className="controls-right">
          <button
            className="control-btn leave"
            onClick={leaveMeeting}
            title="Leave Meeting"
          >
            📞
            <span className="btn-label">Leave</span>
          </button>
        </div>
      </div>

      {/* Chat Panel */}
      {showChat && (
        <div className="chat-panel">
          <div className="chat-header">
            <h4>Chat</h4>
            <button className="close-chat" onClick={() => setShowChat(false)}>x</button>
          </div>
          <div className="chat-messages">
            {chatMessages.length === 0 ? (
              <p className="no-messages">No messages yet</p>
            ) : (
              chatMessages.map(msg => (
                <div key={msg.id} className="chat-message">
                  <span className="message-sender">{sanitizeText(msg.sender)}</span>
                  <p className="message-text">{sanitizeText(msg.text)}</p>
                  <span className="message-time">
                    {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>
              ))
            )}
          </div>
          <div className="chat-input-container">
            <input
              type="text"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && sendChatMessage()}
              placeholder="Type a message..."
            />
            <button onClick={sendChatMessage}>Send</button>
          </div>
        </div>
      )}

      {/* Waiting Room Panel (Host only) */}
      {isHost && waitingParticipants.length > 0 && (
        <div className="waiting-room-panel">
          <div className="waiting-panel-header">
            <h4>Waiting Room ({waitingParticipants.length})</h4>
            {waitingParticipants.length > 1 && (
              <button className="admit-all-btn" onClick={admitAllParticipants}>
                Admit All
              </button>
            )}
          </div>
          <div className="waiting-list">
            {waitingParticipants.map(p => (
              <div key={p.id} className="waiting-participant">
                <span className="participant-avatar">{p.display_name?.[0]?.toUpperCase() || '?'}</span>
                <span className="participant-name">{sanitizeText(p.display_name)}</span>
                <div className="participant-actions">
                  <button
                    className="admit-btn"
                    onClick={() => admitParticipant(p.id)}
                    title="Admit"
                  >
                    Admit
                  </button>
                  <button
                    className="reject-btn"
                    onClick={() => rejectParticipant(p.id)}
                    title="Reject"
                  >
                    Reject
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Breakout Rooms Panel */}
      {showBreakoutPanel && (
        <div className="breakout-panel">
          <div className="breakout-panel-header">
            <h4>Breakout Rooms</h4>
            <button className="close-chat" onClick={() => setShowBreakoutPanel(false)}>x</button>
          </div>
          <div style={{ maxHeight: '280px', overflowY: 'auto' }}>
            {breakoutRooms.length === 0 ? (
              <p style={{ padding: '16px 20px', color: '#888', fontSize: '13px', margin: 0 }}>
                No breakout rooms yet. Create one below.
              </p>
            ) : (
              breakoutRooms.map(room => (
                <div key={room.id} className="breakout-room-item">
                  <div>
                    <span className="breakout-room-name">{sanitizeText(room.room_name)}</span>
                    <span className="breakout-room-count">({room.participant_count}/{room.max_participants})</span>
                  </div>
                  <div style={{ display: 'flex', gap: '6px' }}>
                    {currentBreakoutRoom === room.id ? (
                      <button className="breakout-join-btn" onClick={leaveBreakoutRoom} style={{ background: '#ef4444' }}>
                        Leave
                      </button>
                    ) : (
                      <button className="breakout-join-btn" onClick={() => joinBreakoutRoom(room.id)}>
                        Join
                      </button>
                    )}
                    {isHost && (
                      <button
                        className="breakout-join-btn"
                        onClick={() => closeBreakoutRoom(room.id)}
                        style={{ background: '#6b7280', fontSize: '11px' }}
                      >
                        Close
                      </button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
          {isHost && (
            <div style={{ padding: '12px 20px', borderTop: '1px solid #353535', display: 'flex', gap: '8px' }}>
              <input
                type="text"
                value={newBreakoutName}
                onChange={(e) => setNewBreakoutName(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && createBreakoutRoom()}
                placeholder="Room name..."
                style={{
                  flex: 1, padding: '8px 12px', background: '#1a1a1a', border: '1px solid #404040',
                  borderRadius: '6px', color: 'white', fontSize: '13px'
                }}
              />
              <button className="breakout-join-btn" onClick={createBreakoutRoom}>
                Create
              </button>
            </div>
          )}
        </div>
      )}

      {/* Current Breakout Room Indicator */}
      {currentBreakoutRoom && (
        <div style={{
          position: 'fixed', bottom: '100px', left: '50%', transform: 'translateX(-50%)',
          background: '#8b5cf6', color: 'white', padding: '8px 20px', borderRadius: '20px',
          fontSize: '13px', fontWeight: '600', zIndex: 99, display: 'flex', alignItems: 'center', gap: '10px'
        }}>
          <span>In Breakout: {breakoutRooms.find(r => r.id === currentBreakoutRoom)?.room_name || 'Room'}</span>
          <button onClick={leaveBreakoutRoom} style={{
            background: 'rgba(255,255,255,0.2)', border: 'none', color: 'white',
            padding: '4px 10px', borderRadius: '12px', cursor: 'pointer', fontSize: '12px'
          }}>
            Return to Main
          </button>
        </div>
      )}

      {/* Invite User Modal */}
      {showInviteModal && (
        <div className="invite-modal-overlay" onClick={() => setShowInviteModal(false)}>
          <div className="invite-modal" onClick={(e) => e.stopPropagation()}>
            <div className="invite-modal-header">
              <h3>Invite to Meeting</h3>
              <button className="close-modal" onClick={() => setShowInviteModal(false)}>×</button>
            </div>
            <div className="invite-modal-body">
              {inviteSuccess ? (
                <div className="invite-success">
                  <span className="success-icon">✓</span>
                  <p>Invitation sent successfully!</p>
                </div>
              ) : (
                <>
                  <div className="invite-form-group">
                    <label>Email Address *</label>
                    <input
                      type="email"
                      value={inviteEmail}
                      onChange={(e) => setInviteEmail(e.target.value)}
                      placeholder="Enter email address"
                      autoFocus
                    />
                  </div>
                  <div className="invite-form-group">
                    <label>Name (optional)</label>
                    <input
                      type="text"
                      value={inviteName}
                      onChange={(e) => setInviteName(e.target.value)}
                      placeholder="Enter name"
                    />
                  </div>
                  <div className="invite-info">
                    <p>An email will be sent with a link to join this meeting.</p>
                  </div>
                </>
              )}
            </div>
            {!inviteSuccess && (
              <div className="invite-modal-footer">
                <button
                  className="cancel-btn"
                  onClick={() => setShowInviteModal(false)}
                >
                  Cancel
                </button>
                <button
                  className="send-invite-btn"
                  onClick={sendMeetingInvite}
                  disabled={!inviteEmail.trim() || inviteSending}
                >
                  {inviteSending ? 'Sending...' : 'Send Invite'}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Screen Recording Share Modal */}
      {showScreenRecordingModal && (
        <div className="invite-modal-overlay" onClick={() => {
          setShowScreenRecordingModal(false);
          if (screenRecordingUrl?.startsWith('blob:')) URL.revokeObjectURL(screenRecordingUrl);
        }}>
          <div className="screen-recording-modal" onClick={(e) => e.stopPropagation()}>
            <div className="invite-modal-header">
              <h3>Screen Recording Ready</h3>
              <button className="close-modal" onClick={() => {
                setShowScreenRecordingModal(false);
                if (screenRecordingUrl?.startsWith('blob:')) URL.revokeObjectURL(screenRecordingUrl);
              }}>×</button>
            </div>
            <div className="screen-recording-modal-body">
              <div className="recording-success-icon">🎬</div>
              <p className="recording-ready-text">Your screen recording is ready to share!</p>

              <div className="invite-form-group">
                <label>Recipient Name</label>
                <input
                  type="text"
                  value={recipientName}
                  onChange={(e) => setRecipientName(e.target.value)}
                  placeholder="e.g., John Smith"
                />
              </div>

              <div className="invite-form-group">
                <label>Recipient Email (for summary email)</label>
                <input
                  type="email"
                  value={recipientEmail}
                  onChange={(e) => setRecipientEmail(e.target.value)}
                  placeholder="e.g., john@example.com"
                />
              </div>

              <div className="share-link-container">
                <label>Share Link</label>
                <div className="share-link-input">
                  <input
                    type="text"
                    value={screenRecordingUrl}
                    readOnly
                  />
                  <button
                    className="copy-link-btn"
                    onClick={copyScreenRecordingLink}
                    title="Copy link"
                  >
                    📋
                  </button>
                </div>
              </div>

              <div className="recording-actions">
                <button
                  className="download-recording-btn"
                  onClick={downloadScreenRecording}
                >
                  Download Recording
                </button>
                <button
                  className="send-invite-btn"
                  onClick={copyScreenRecordingLink}
                >
                  Copy & Log Activity
                </button>
              </div>

              <div className="email-summary-section">
                <div className="section-divider">
                  <span>Email Summary</span>
                </div>
                <p className="email-summary-description">
                  Generate an AI-powered email summary with action items for the recipient.
                  The draft will be saved to the borrower's Email tab for review before sending.
                </p>
                <button
                  className={`generate-summary-btn ${emailSummaryGenerated ? 'generated' : ''}`}
                  onClick={generateEmailSummary}
                  disabled={!recipientEmail || generatingEmailSummary || emailSummaryGenerated}
                >
                  {generatingEmailSummary ? 'Generating...' :
                   emailSummaryGenerated ? 'Draft Created!' :
                   'Generate Email Summary'}
                </button>
                {emailSummaryGenerated && (
                  <p className="email-summary-success">
                    Email draft saved! View it in the Email tab of the borrower's profile.
                  </p>
                )}
              </div>

              {recipientName && !emailSummaryGenerated && (
                <p className="activity-log-note">
                  Activity will be logged as: "Screen recording sent to {recipientName}"
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Host Consent Dialog - shown before starting recording */}
      {showConsentDialog && (
        <div className="invite-modal-overlay" onClick={() => setShowConsentDialog(false)}>
          <div className="invite-modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '500px' }}>
            <div className="invite-modal-header">
              <h3>Recording Consent Required</h3>
              <button className="close-modal" onClick={() => setShowConsentDialog(false)}>×</button>
            </div>
            <div className="invite-modal-body" style={{ padding: '20px' }}>
              {consentState && (
                <>
                  <div style={{
                    background: consentState.consent_type === 'all_party' ? '#fef3c7' : '#dbeafe',
                    border: `1px solid ${consentState.consent_type === 'all_party' ? '#f59e0b' : '#3b82f6'}`,
                    borderRadius: '8px', padding: '16px', marginBottom: '16px'
                  }}>
                    <p style={{ margin: '0 0 8px', fontWeight: '600', fontSize: '14px' }}>
                      {consentState.consent_type === 'all_party'
                        ? '⚠️ All-Party Consent State'
                        : 'One-Party Consent State'}
                      {consentState.state ? ` (${consentState.state})` : ''}
                    </p>
                    {consentState.consent_type === 'all_party' && (
                      <p style={{ margin: '0', fontSize: '13px', color: '#92400e' }}>
                        All participants must consent before recording can begin.
                      </p>
                    )}
                  </div>

                  <div style={{
                    background: '#f9fafb', borderRadius: '8px', padding: '16px',
                    marginBottom: '16px', fontStyle: 'italic', fontSize: '14px',
                    lineHeight: '1.5', borderLeft: '4px solid #6b7280'
                  }}>
                    <p style={{ margin: '0 0 8px', fontWeight: '600', fontStyle: 'normal' }}>Disclosure Script:</p>
                    <p style={{ margin: 0 }}>{consentState.script}</p>
                  </div>

                  <p style={{ fontSize: '13px', color: '#6b7280', margin: '0' }}>
                    By clicking "Start Recording", you acknowledge that you will read the disclosure
                    script to all participants before the recording begins.
                  </p>
                </>
              )}
            </div>
            <div className="invite-modal-footer" style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', padding: '16px 20px' }}>
              <button
                className="cancel-btn"
                onClick={() => setShowConsentDialog(false)}
                style={{ padding: '8px 20px', borderRadius: '6px', border: '1px solid #d1d5db', background: 'white', cursor: 'pointer' }}
              >
                Cancel
              </button>
              <button
                onClick={startRecordingWithConsent}
                disabled={consentLoading}
                style={{
                  padding: '8px 20px', borderRadius: '6px', border: 'none',
                  background: '#dc2626', color: 'white', fontWeight: '600', cursor: 'pointer'
                }}
              >
                {consentLoading ? 'Loading...' : 'Start Recording'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Participant Consent Dialog - shown to non-hosts when recording starts */}
      {showParticipantConsentDialog && participantConsentData && (
        <div className="invite-modal-overlay">
          <div className="invite-modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '450px' }}>
            <div className="invite-modal-header" style={{ background: '#dc2626', color: 'white' }}>
              <h3 style={{ margin: 0 }}>Recording Started</h3>
            </div>
            <div className="invite-modal-body" style={{ padding: '20px' }}>
              <p style={{ fontSize: '15px', lineHeight: '1.6', margin: '0 0 16px' }}>
                The host has started recording this meeting.
              </p>

              {participantConsentData.disclosure_script && (
                <div style={{
                  background: '#f9fafb', borderRadius: '8px', padding: '16px',
                  marginBottom: '16px', fontStyle: 'italic', fontSize: '14px',
                  lineHeight: '1.5', borderLeft: '4px solid #dc2626'
                }}>
                  <p style={{ margin: 0 }}>{participantConsentData.disclosure_script}</p>
                </div>
              )}

              {participantConsentData.consent_type === 'all_party' && (
                <p style={{ fontSize: '13px', color: '#92400e', margin: '0 0 8px', fontWeight: '600' }}>
                  Your consent is required to continue recording.
                </p>
              )}
            </div>
            <div className="invite-modal-footer" style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', padding: '16px 20px' }}>
              <button
                onClick={() => submitParticipantConsent(false)}
                style={{ padding: '8px 20px', borderRadius: '6px', border: '1px solid #d1d5db', background: 'white', cursor: 'pointer' }}
              >
                Decline
              </button>
              <button
                onClick={() => submitParticipantConsent(true)}
                style={{
                  padding: '8px 20px', borderRadius: '6px', border: 'none',
                  background: '#10b981', color: 'white', fontWeight: '600', cursor: 'pointer'
                }}
              >
                I Agree
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default MeetingRoom;
