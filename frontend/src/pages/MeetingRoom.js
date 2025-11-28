import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { sanitizeText } from '../utils/sanitize';
import './MeetingRoom.css';

// API Base URL
const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const API_BASE = isProduction
  ? 'https://mortgage-crm-production-7a9a.up.railway.app'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

const MeetingRoom = () => {
  const { roomCode } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const isHost = searchParams.get('host') === 'true';

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

  // Refs
  const localVideoRef = useRef(null);
  const recordingTimerRef = useRef(null);

  const getAuthHeaders = useCallback(() => {
    const token = localStorage.getItem('token');
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    };
  }, []);

  // Fetch meeting info
  useEffect(() => {
    const fetchMeeting = async () => {
      try {
        setLoading(true);
        const response = await fetch(`${API_BASE}/api/v1/meetings/join/${roomCode}`);

        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || 'Meeting not found');
        }

        const data = await response.json();
        setMeeting(data.meeting);

        // Check if waiting room is enabled
        if (data.meeting.waiting_room_enabled && !isHost) {
          setInWaitingRoom(true);
        }

        // Auto-set display name if logged in
        const token = localStorage.getItem('token');
        if (token) {
          try {
            const payload = JSON.parse(atob(token.split('.')[1]));
            setDisplayName(payload.sub?.split('@')[0] || 'Guest');
          } catch {
            setDisplayName('Guest');
          }
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchMeeting();
  }, [roomCode, isHost]);

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
    } catch (err) {
      console.error('Error accessing media devices:', err);
      // Try audio only
      try {
        const audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        setLocalStream(audioStream);
        setVideoEnabled(false);
      } catch (audioErr) {
        console.error('Error accessing audio:', audioErr);
      }
    }
  };

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
    await initializeMedia();
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
  };

  // Toggle audio
  const toggleAudio = () => {
    if (localStream) {
      const audioTrack = localStream.getAudioTracks()[0];
      if (audioTrack) {
        audioTrack.enabled = !audioTrack.enabled;
        setAudioEnabled(audioTrack.enabled);
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
        const errorData = await response.json();
        alert(errorData.detail || 'Failed to send invite');
      }
    } catch (err) {
      console.error('Error sending invite:', err);
      alert('Failed to send invite. Please try again.');
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

  // Leave meeting
  const leaveMeeting = () => {
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
      if (localStream) {
        localStream.getTracks().forEach(track => track.stop());
      }
      if (recordingTimerRef.current) {
        clearInterval(recordingTimerRef.current);
      }
    };
  }, [localStream]);

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

              <button className="join-btn" onClick={handleJoin}>
                Join Meeting
              </button>
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
            👥 {participants.length}
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

        {/* Other participants would go here */}
        {participants.filter(p => !p.isLocal).map(participant => (
          <div key={participant.id} className="video-container">
            <div className="video-placeholder">
              <span className="avatar large">{participant.name?.[0]?.toUpperCase()}</span>
            </div>
            <div className="video-label">
              <span>{sanitizeText(participant.name)}</span>
              {!participant.audioEnabled && <span className="muted-icon">🔇</span>}
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
                <label>Recipient Name (for activity log)</label>
                <input
                  type="text"
                  value={recipientName}
                  onChange={(e) => setRecipientName(e.target.value)}
                  placeholder="e.g., John Smith"
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
                  ⬇️ Download Recording
                </button>
                <button
                  className="send-invite-btn"
                  onClick={copyScreenRecordingLink}
                >
                  📋 Copy & Log Activity
                </button>
              </div>

              {recipientName && (
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
