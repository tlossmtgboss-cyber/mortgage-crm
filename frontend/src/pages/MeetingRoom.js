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

  // Chat state
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [showChat, setShowChat] = useState(false);

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

  // Leave meeting
  const leaveMeeting = () => {
    if (localStream) {
      localStream.getTracks().forEach(track => track.stop());
    }
    if (recordingTimerRef.current) {
      clearInterval(recordingTimerRef.current);
    }
    navigate('/video-meetings');
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
    </div>
  );
};

export default MeetingRoom;
