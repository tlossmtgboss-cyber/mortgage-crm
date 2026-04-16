import React, { useState, useRef, useCallback, useEffect } from 'react';
import './VideoRecorder.css';
import { getToken } from '../../utils/tokenStore';

const VideoRecorder = ({ candidateId, candidateName, onVideoSent, onClose }) => {
  const [isRecording, setIsRecording] = useState(false);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [countdown, setCountdown] = useState(null);
  const [recordingTime, setRecordingTime] = useState(0);
  const [recordedBlob, setRecordedBlob] = useState(null);
  const [recordedUrl, setRecordedUrl] = useState(null);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState(null);
  const [stream, setStream] = useState(null);
  const [message, setMessage] = useState('');
  const [sendNotification, setSendNotification] = useState(true);

  const videoRef = useRef(null);
  const previewRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);

  // Initialize camera
  const startCamera = useCallback(async () => {
    try {
      const mediaStream = await navigator.mediaDevices.getUserMedia({
        video: { width: 1280, height: 720, facingMode: 'user' },
        audio: true
      });
      setStream(mediaStream);
      if (videoRef.current) {
        videoRef.current.srcObject = mediaStream;
      }
    } catch (err) {
      setError('Unable to access camera. Please ensure you have granted camera permissions.');
      console.error('Camera error:', err);
    }
  }, []);

  // Stop camera
  const stopCamera = useCallback(() => {
    if (stream) {
      stream.getTracks().forEach(track => track.stop());
      setStream(null);
    }
  }, [stream]);

  useEffect(() => {
    startCamera();
    return () => stopCamera();
  }, []);

  // Start recording with countdown
  const startRecording = useCallback(() => {
    setCountdown(3);
    const countdownInterval = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) {
          clearInterval(countdownInterval);
          beginRecording();
          return null;
        }
        return prev - 1;
      });
    }, 1000);
  }, [stream]);

  // Begin actual recording
  const beginRecording = useCallback(() => {
    if (!stream) return;

    chunksRef.current = [];
    const mediaRecorder = new MediaRecorder(stream, {
      mimeType: 'video/webm;codecs=vp9,opus'
    });

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        chunksRef.current.push(event.data);
      }
    };

    mediaRecorder.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: 'video/webm' });
      setRecordedBlob(blob);
      setRecordedUrl(URL.createObjectURL(blob));
      setIsPreviewing(true);
    };

    mediaRecorderRef.current = mediaRecorder;
    mediaRecorder.start(1000); // Collect data every second
    setIsRecording(true);
    setRecordingTime(0);

    // Start timer
    timerRef.current = setInterval(() => {
      setRecordingTime(prev => prev + 1);
    }, 1000);
  }, [stream]);

  // Stop recording
  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    }
  }, [isRecording]);

  // Discard and re-record
  const discardRecording = useCallback(() => {
    setRecordedBlob(null);
    setRecordedUrl(null);
    setIsPreviewing(false);
    setRecordingTime(0);
    // Restart camera if needed
    if (!stream) {
      startCamera();
    }
  }, [stream, startCamera]);

  // Send video to candidate
  const sendVideo = async () => {
    if (!recordedBlob) return;

    setIsSending(true);
    setError(null);

    try {
      const token = getToken();
      const API_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

      // Get upload URL
      const uploadResponse = await fetch(`${API_URL}/api/v1/recruiting/video/upload-url`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          candidate_id: candidateId,
          content_type: 'video/webm',
          filename: `recruit-video-${candidateId}-${Date.now()}.webm`
        })
      });

      if (!uploadResponse.ok) {
        throw new Error('Failed to get upload URL');
      }

      const { upload_url, video_key } = await uploadResponse.json();

      // Upload video to S3
      await fetch(upload_url, {
        method: 'PUT',
        headers: {
          'Content-Type': 'video/webm'
        },
        body: recordedBlob
      });

      // Complete upload and notify candidate
      const completeResponse = await fetch(`${API_URL}/api/v1/recruiting/video/complete`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          candidate_id: candidateId,
          video_key,
          message: message || 'Check out this personalized message from your recruiter!',
          send_notification: sendNotification,
          duration_seconds: recordingTime
        })
      });

      if (!completeResponse.ok) {
        throw new Error('Failed to save video');
      }

      const result = await completeResponse.json();

      if (onVideoSent) {
        onVideoSent(result);
      }

      // Close the modal
      if (onClose) {
        onClose();
      }

    } catch (err) {
      setError(err.message || 'Failed to send video');
      console.error('Video send error:', err);
    } finally {
      setIsSending(false);
    }
  };

  // Format time display
  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="video-recorder-overlay" onClick={onClose}>
      <div className="video-recorder-modal" onClick={e => e.stopPropagation()}>
        <div className="video-recorder-header">
          <h3>Personal Message for {candidateName}</h3>
          <span className="subtitle">Make them feel special with a personal touch ✨</span>
          <button className="video-close-btn" onClick={onClose}>×</button>
        </div>

        <div className="video-recorder-content">
          {/* Camera/Preview View */}
          <div className="video-viewport">
            {!isPreviewing ? (
              <>
                <video
                  ref={videoRef}
                  autoPlay
                  muted
                  playsInline
                  className="video-live-feed"
                />
                {countdown && (
                  <div className="video-countdown">
                    <span>{countdown}</span>
                  </div>
                )}
                {isRecording && (
                  <div className="video-recording-indicator">
                    <span className="recording-dot"></span>
                    <span className="recording-time">{formatTime(recordingTime)}</span>
                  </div>
                )}
              </>
            ) : (
              <video
                ref={previewRef}
                src={recordedUrl}
                controls
                className="video-preview"
              />
            )}
          </div>

          {/* Controls */}
          <div className="video-controls">
            {!isPreviewing ? (
              <>
                {!isRecording ? (
                  <button
                    className="video-record-btn"
                    onClick={startRecording}
                    disabled={!stream || countdown !== null}
                  >
                    <span className="record-icon"></span>
                    Start Recording
                  </button>
                ) : (
                  <button
                    className="video-stop-btn"
                    onClick={stopRecording}
                  >
                    <span className="stop-icon"></span>
                    Done Recording
                  </button>
                )}
              </>
            ) : (
              <div className="video-preview-controls">
                <button
                  className="video-discard-btn"
                  onClick={discardRecording}
                  disabled={isSending}
                >
                  Try Again
                </button>
                <button
                  className="video-send-btn"
                  onClick={sendVideo}
                  disabled={isSending}
                >
                  {isSending ? 'Sending...' : `Send to ${candidateName.split(' ')[0]} 🚀`}
                </button>
              </div>
            )}
          </div>

          {/* Message Input */}
          {isPreviewing && (
            <div className="video-message-section">
              <label htmlFor="videoMessage">Add a personal note</label>
              <textarea
                id="videoMessage"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder={`Hey ${candidateName.split(' ')[0]}! I'm excited to connect with you...`}
                rows={3}
              />
              <label className="video-notify-checkbox">
                <input
                  type="checkbox"
                  checked={sendNotification}
                  onChange={(e) => setSendNotification(e.target.checked)}
                />
                <span>Notify {candidateName.split(' ')[0]} in their portal</span>
              </label>
            </div>
          )}

          {/* Error Display */}
          {error && (
            <div className="video-error">
              <span>{error}</span>
            </div>
          )}

          {/* Tips */}
          {!isPreviewing && !isRecording && (
            <div className="video-tips">
              <h4>Make it memorable</h4>
              <ul>
                <li>Smile! Your energy is contagious</li>
                <li>Keep it brief - 30-60 seconds is perfect</li>
                <li>Use {candidateName.split(' ')[0]}'s name</li>
                <li>Share why you're excited about them</li>
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default VideoRecorder;
