import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { sanitizeText } from '../utils/sanitize';
import { getAuthHeaders } from '../utils/auth';
import './MeetingRoom.css';

// API Base URL
const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const API_BASE = isProduction
  ? 'https://api.perenniaai.com'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

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

  // Refs
  const localVideoRef = useRef(null);
  const recordingTimerRef = useRef(null);

  // WebRTC refs
  const wsRef = useRef(null);
  const peerConnectionsRef = useRef({}); // {participantId: RTCPeerConnection}
  const remoteStreamsRef = useRef({}); // {participantId: MediaStream}
  const remoteVideoRefs = useRef({}); // {participantId: HTMLVideoElement ref}
  const localParticipantIdRef = useRef(null);

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

  // Fetch meeting info
  useEffect(() => {
    const fetchMeeting = async () => {
      try {
        setLoading(true);

        // First, get current user info from API if logged in
        let userId = null;
        let userName = 'Guest';
        const token = localStorage.getItem('token');
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
              // Fallback to JWT parsing for display name
              const payload = JSON.parse(atob(token.split('.')[1]));
              userName = payload.sub?.split('@')[0] || 'Guest';
              setDisplayName(userName);
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
    // Generate unique participant ID
    const participantId = `p-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    localParticipantIdRef.current = participantId;

    // Determine WebSocket URL
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsHost = isProduction
      ? 'api.perenniaai.com'
      : (process.env.REACT_APP_API_URL?.replace(/^https?:\/\//, '') || 'localhost:8000');
    const wsUrl = `${wsProtocol}//${wsHost}/api/v1/meetings/ws/${roomCode}/${participantId}?name=${encodeURIComponent(displayName)}&host=${isHost}`;

    console.log('Connecting to signaling server:', wsUrl);

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('Connected to signaling server');
      // Start ping to keep connection alive
      const pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, 30000);
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
            // Chat message received
            setChatMessages(prev => [...prev, {
              id: Date.now(),
              sender: message.sender_name,
              text: message.message,
              timestamp: new Date(message.timestamp)
            }]);
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

    ws.onclose = () => {
      console.log('WebSocket disconnected');
      if (ws._pingInterval) {
        clearInterval(ws._pingInterval);
      }
    };

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

    // Add local tracks to the connection
    if (stream) {
      stream.getTracks().forEach(track => {
        pc.addTrack(track, stream);
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
    };

    // Handle ICE candidates
    pc.onicecandidate = (event) => {
      if (event.candidate && wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({
          type: 'ice_candidate',
          target: remoteParticipantId,
          candidate: event.candidate
        }));
      }
    };

    // Handle connection state changes
    pc.onconnectionstatechange = () => {
      console.log(`Connection state with ${remoteParticipantId}:`, pc.connectionState);
      if (pc.connectionState === 'failed' || pc.connectionState === 'disconnected') {
        // Connection failed - cleanup
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
  }, []);

  // ============================================================================
  // END WEBRTC FUNCTIONS
  // ============================================================================

  // Join meeting
  const handleJoin = async () => {
    if (!displayName.trim()) {
      alert('Please enter your name');
      return;
    }

    if (meeting?.password_protected && !password) {
      alert('Please enter the meeting password');
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

    // Notify backend of join (if authenticated)
    const token = localStorage.getItem('token');
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
    if (localStream) {
      const audioTrack = localStream.getAudioTracks()[0];
      if (audioTrack) {
        audioTrack.enabled = !audioTrack.enabled;
        setAudioEnabled(audioTrack.enabled);
        // Notify other participants of state change
        sendMediaState(audioTrack.enabled, videoEnabled);
      }
    }
  };

  // Toggle video
  const toggleVideo = () => {
    if (localStream) {
      const videoTrack = localStream.getVideoTracks()[0];
      if (videoTrack) {
        videoTrack.enabled = !videoTrack.enabled;
        setVideoEnabled(videoTrack.enabled);
        // Notify other participants of state change
        sendMediaState(audioEnabled, videoTrack.enabled);
      }
    }
  };

  // Toggle screen share
  const toggleScreenShare = async () => {
    if (screenSharing) {
      // Stop screen sharing
      if (localStream) {
        localStream.getTracks().forEach(track => track.stop());
      }
      await initializeMedia();
      setScreenSharing(false);
    } else {
      try {
        const screenStream = await navigator.mediaDevices.getDisplayMedia({
          video: true
        });
        setLocalStream(screenStream);
        if (localVideoRef.current) {
          localVideoRef.current.srcObject = screenStream;
        }
        setScreenSharing(true);

        // Handle when user stops sharing via browser UI
        screenStream.getVideoTracks()[0].onended = () => {
          toggleScreenShare();
        };
      } catch (err) {
        console.error('Error sharing screen:', err);
      }
    }
  };

  // Toggle recording (host only)
  const toggleRecording = async () => {
    if (!isRecording) {
      try {
        const response = await fetch(`${API_BASE}/api/v1/meetings/rooms/${meeting?.id}/recordings/start`, {
          method: 'POST',
          headers: getAuthHeaders()
        });

        if (response.ok) {
          setIsRecording(true);
          recordingTimerRef.current = setInterval(() => {
            setRecordingTime(t => t + 1);
          }, 1000);
        }
      } catch (err) {
        console.error('Error starting recording:', err);
      }
    } else {
      // Stop recording would need recording_id from start response
      setIsRecording(false);
      if (recordingTimerRef.current) {
        clearInterval(recordingTimerRef.current);
      }
      setRecordingTime(0);
    }
  };

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
      const token = localStorage.getItem('token');
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
        alert(errorMessage);
      }
    } catch (err) {
      console.error('Error sending invite:', err);
      alert('Failed to send invite: ' + (err.message || 'Network error'));
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
      alert('Please enter your name');
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
        alert(errorData.detail || 'Failed to join waiting room');
      }
    } catch (err) {
      console.error('Error requesting to join:', err);
      alert('Failed to join meeting');
    }
  };

  // Poll for admission status (guest side)
  const startAdmissionPolling = (pId) => {
    if (admissionPollRef.current) {
      clearInterval(admissionPollRef.current);
    }

    admissionPollRef.current = setInterval(async () => {
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
        const audioContext = new AudioContext();
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

      // Setup MediaRecorder
      const recorder = new MediaRecorder(combinedStream, {
        mimeType: 'video/webm;codecs=vp9,opus'
      });

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
        const blob = new Blob(chunks, { type: 'video/webm' });
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
      alert('Failed to start screen recording. Please make sure you allowed screen sharing.');
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
    setIsScreenRecording(false);
    setScreenRecordingUploading(true);
  };

  // Upload screen recording and get shareable link
  const uploadScreenRecording = async (blob) => {
    try {
      const token = localStorage.getItem('token');
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
        const token = localStorage.getItem('token');
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

      alert('Link copied to clipboard!');
    } catch (err) {
      console.error('Failed to copy link:', err);
      alert('Failed to copy link. Please copy manually: ' + screenRecordingUrl);
    }
  };

  // Download screen recording locally
  const downloadScreenRecording = () => {
    const a = document.createElement('a');
    a.href = screenRecordingUrl;
    a.download = `screen-recording-${new Date().toISOString().slice(0, 10)}.webm`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  // Generate AI email summary from recording
  const generateEmailSummary = async () => {
    if (!recipientEmail) {
      alert('Please enter a recipient email address');
      return;
    }

    setGeneratingEmailSummary(true);
    try {
      const token = localStorage.getItem('token');
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
        alert(`Email summary draft created! You can find it in the Email tab of the borrower's profile page.`);

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
      alert('Failed to generate email summary: ' + err.message);
    } finally {
      setGeneratingEmailSummary(false);
    }
  };

  // Leave meeting
  const leaveMeeting = () => {
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
            👥 {1 + Object.keys(remoteStreams).length}
          </span>
        </div>
      </div>

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
        {Object.entries(remoteStreams).map(([participantId, participantData]) => (
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
        <div className="invite-modal-overlay" onClick={() => setShowScreenRecordingModal(false)}>
          <div className="screen-recording-modal" onClick={(e) => e.stopPropagation()}>
            <div className="invite-modal-header">
              <h3>Screen Recording Ready</h3>
              <button className="close-modal" onClick={() => setShowScreenRecordingModal(false)}>×</button>
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
    </div>
  );
};

export default MeetingRoom;
