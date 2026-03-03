/**
 * WaitingRoom — Pre-join screen with camera/mic preview and device selection.
 *
 * Handles:
 * - Device preview (camera + mic)
 * - Display name input
 * - Password input (if room is password-protected)
 * - Waiting room polling for guest admission
 * - Join button → backend join → Chime join
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  useVideoInputs,
  useAudioInputs,
  useMeetingManager,
} from 'amazon-chime-sdk-component-library-react';
import { getAuthHeaders } from '../../utils/auth';
import { toast } from '../../utils/toast';

const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const API_BASE = isProduction
  ? 'https://api.perenniaai.com'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

const ADMISSION_POLL_INTERVAL = 2000;
const ADMISSION_TIMEOUT = 300000; // 5 minutes

export default function WaitingRoom({
  roomCode,
  meeting,
  onJoin,
  initialDisplayName,
}) {
  const meetingManager = useMeetingManager();
  const { devices: videoDevices, selectedDevice: selectedVideo } = useVideoInputs();
  const { devices: audioDevices, selectedDevice: selectedAudio } = useAudioInputs();

  const [displayName, setDisplayName] = useState(initialDisplayName || '');
  const [password, setPassword] = useState('');
  const [joining, setJoining] = useState(false);
  const [inWaitingRoom, setInWaitingRoom] = useState(false);
  const [rejected, setRejected] = useState(false);
  const [participantId, setParticipantId] = useState(null);
  const [previewStream, setPreviewStream] = useState(null);

  const videoPreviewRef = useRef(null);
  const admissionPollRef = useRef(null);
  const admissionTimeoutRef = useRef(null);

  // Start camera preview
  useEffect(() => {
    let stream = null;
    const startPreview = async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
        setPreviewStream(stream);
        if (videoPreviewRef.current) {
          videoPreviewRef.current.srcObject = stream;
        }
      } catch (err) {
        console.warn('Camera preview unavailable:', err);
      }
    };
    startPreview();

    return () => {
      if (stream) {
        stream.getTracks().forEach(t => t.stop());
      }
    };
  }, []);

  // Bind stream to video element when ref or stream changes
  useEffect(() => {
    if (videoPreviewRef.current && previewStream) {
      videoPreviewRef.current.srcObject = previewStream;
    }
  }, [previewStream]);

  // Device selection handlers
  const handleVideoDeviceChange = async (deviceId) => {
    try {
      await meetingManager.selectVideoInputDevice(deviceId);
    } catch (err) {
      console.warn('Failed to select video device:', err);
    }
  };

  const handleAudioDeviceChange = async (deviceId) => {
    try {
      await meetingManager.selectAudioInputDevice(deviceId);
    } catch (err) {
      console.warn('Failed to select audio device:', err);
    }
  };

  // Poll for admission status (waiting room flow)
  const startAdmissionPolling = useCallback((pId) => {
    if (admissionPollRef.current) clearInterval(admissionPollRef.current);
    if (admissionTimeoutRef.current) clearTimeout(admissionTimeoutRef.current);

    admissionPollRef.current = setInterval(async () => {
      try {
        const response = await fetch(
          `${API_BASE}/api/v1/meetings/rooms/${meeting?.id}/waiting-room/status/${pId}`,
          { headers: getAuthHeaders() }
        );
        if (response.ok) {
          const data = await response.json();
          if (data.status === 'admitted') {
            clearInterval(admissionPollRef.current);
            clearTimeout(admissionTimeoutRef.current);
            setInWaitingRoom(false);
            onJoin({ participantId: pId, displayName });
          } else if (data.status === 'rejected') {
            clearInterval(admissionPollRef.current);
            clearTimeout(admissionTimeoutRef.current);
            setInWaitingRoom(false);
            setRejected(true);
            toast.error('Your request to join was declined');
          }
        }
      } catch {
        // Polling failure, will retry
      }
    }, ADMISSION_POLL_INTERVAL);

    admissionTimeoutRef.current = setTimeout(() => {
      clearInterval(admissionPollRef.current);
      setInWaitingRoom(false);
      toast.error('Waiting room timed out');
    }, ADMISSION_TIMEOUT);
  }, [meeting, displayName, onJoin]);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (admissionPollRef.current) clearInterval(admissionPollRef.current);
      if (admissionTimeoutRef.current) clearTimeout(admissionTimeoutRef.current);
    };
  }, []);

  const handleJoin = async () => {
    if (!displayName.trim()) {
      toast.error('Please enter your name');
      return;
    }

    setJoining(true);
    try {
      const headers = { 'Content-Type': 'application/json', ...getAuthHeaders() };
      const response = await fetch(`${API_BASE}/api/v1/meetings/join/${roomCode}`, {
        method: 'GET',
        headers,
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        if (response.status === 403 && data.detail?.includes('waiting')) {
          // Put into waiting room
          const wrResponse = await fetch(
            `${API_BASE}/api/v1/meetings/rooms/${meeting?.id}/waiting-room/join`,
            {
              method: 'POST',
              headers,
              body: JSON.stringify({ display_name: displayName, password }),
            }
          );
          if (wrResponse.ok) {
            const wrData = await wrResponse.json();
            setParticipantId(wrData.participant_id);
            setInWaitingRoom(true);
            startAdmissionPolling(wrData.participant_id);
            // Stop preview stream since we're waiting
            if (previewStream) {
              previewStream.getTracks().forEach(t => t.stop());
            }
          } else {
            throw new Error('Could not join waiting room');
          }
        } else {
          throw new Error(data.detail || 'Failed to join meeting');
        }
      } else {
        const data = await response.json();
        // Stop preview stream before Chime takes over media
        if (previewStream) {
          previewStream.getTracks().forEach(t => t.stop());
        }
        onJoin(data);
      }
    } catch (err) {
      toast.error(err.message || 'Failed to join meeting');
    } finally {
      setJoining(false);
    }
  };

  if (rejected) {
    return (
      <div className="waiting-room">
        <div className="waiting-room-card">
          <h2>Access Denied</h2>
          <p>The host has declined your request to join this meeting.</p>
          <button className="btn-primary" onClick={() => window.history.back()}>
            Go Back
          </button>
        </div>
      </div>
    );
  }

  if (inWaitingRoom) {
    return (
      <div className="waiting-room">
        <div className="waiting-room-card">
          <h2>Waiting Room</h2>
          <p>Please wait while the host admits you to the meeting...</p>
          <div className="waiting-spinner" />
          <p className="waiting-name">Joining as: <strong>{displayName}</strong></p>
        </div>
      </div>
    );
  }

  return (
    <div className="waiting-room">
      <div className="waiting-room-card">
        <h2>{meeting?.title || 'Join Meeting'}</h2>

        <div className="preview-container">
          <video
            ref={videoPreviewRef}
            autoPlay
            playsInline
            muted
            className="preview-video"
          />
        </div>

        <div className="device-selectors">
          {videoDevices.length > 0 && (
            <div className="device-select">
              <label>Camera</label>
              <select
                value={selectedVideo || ''}
                onChange={(e) => handleVideoDeviceChange(e.target.value)}
              >
                {videoDevices.map(d => (
                  <option key={d.deviceId} value={d.deviceId}>{d.label || 'Camera'}</option>
                ))}
              </select>
            </div>
          )}
          {audioDevices.length > 0 && (
            <div className="device-select">
              <label>Microphone</label>
              <select
                value={selectedAudio || ''}
                onChange={(e) => handleAudioDeviceChange(e.target.value)}
              >
                {audioDevices.map(d => (
                  <option key={d.deviceId} value={d.deviceId}>{d.label || 'Microphone'}</option>
                ))}
              </select>
            </div>
          )}
        </div>

        <div className="join-form">
          <input
            type="text"
            placeholder="Your name"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className="name-input"
            maxLength={50}
          />
          {meeting?.has_password && (
            <input
              type="password"
              placeholder="Meeting password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="password-input"
            />
          )}
          <button
            className="btn-primary join-btn"
            onClick={handleJoin}
            disabled={joining || !displayName.trim()}
          >
            {joining ? 'Joining...' : 'Join Meeting'}
          </button>
        </div>
      </div>
    </div>
  );
}
