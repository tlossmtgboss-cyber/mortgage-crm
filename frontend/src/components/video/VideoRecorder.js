/**
 * VideoRecorder Component
 *
 * Provides webcam video recording functionality for loan officers
 * to create personalized video messages for clients and realtors.
 */

import React, { useState, useRef, useCallback, useEffect } from 'react';
import './VideoRecorder.css';

const VideoRecorder = ({
  onRecordingComplete,
  onCancel,
  maxDuration = 120, // 2 minutes default
  showPreview = true
}) => {
  const [status, setStatus] = useState('idle'); // idle, requesting, ready, recording, recorded, error
  const [error, setError] = useState(null);
  const [recordingTime, setRecordingTime] = useState(0);
  const [videoBlob, setVideoBlob] = useState(null);
  const [videoUrl, setVideoUrl] = useState(null);

  const videoRef = useRef(null);
  const previewRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);

  // Request camera access
  const requestCamera = useCallback(async () => {
    setStatus('requesting');
    setError(null);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 1280 },
          height: { ideal: 720 },
          facingMode: 'user'
        },
        audio: true
      });

      streamRef.current = stream;

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }

      setStatus('ready');
    } catch (err) {
      console.error('Camera access error:', err);
      setError(getErrorMessage(err));
      setStatus('error');
    }
  }, []);

  // Get user-friendly error message
  const getErrorMessage = (err) => {
    if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
      return 'Camera access denied. Please allow camera access in your browser settings.';
    }
    if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
      return 'No camera found. Please connect a camera and try again.';
    }
    if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
      return 'Camera is in use by another application. Please close other apps using the camera.';
    }
    return 'Unable to access camera. Please check your camera settings.';
  };

  // Start recording
  const startRecording = useCallback(() => {
    if (!streamRef.current) return;

    chunksRef.current = [];

    // Determine best supported format
    const mimeType = MediaRecorder.isTypeSupported('video/webm;codecs=vp9')
      ? 'video/webm;codecs=vp9'
      : MediaRecorder.isTypeSupported('video/webm;codecs=vp8')
        ? 'video/webm;codecs=vp8'
        : 'video/webm';

    try {
      const mediaRecorder = new MediaRecorder(streamRef.current, {
        mimeType,
        videoBitsPerSecond: 2500000 // 2.5 Mbps
      });

      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mimeType });
        setVideoBlob(blob);
        setVideoUrl(URL.createObjectURL(blob));
        setStatus('recorded');
      };

      mediaRecorderRef.current = mediaRecorder;
      mediaRecorder.start(1000); // Collect data every second

      setStatus('recording');
      setRecordingTime(0);

      // Start timer
      timerRef.current = setInterval(() => {
        setRecordingTime(prev => {
          if (prev >= maxDuration - 1) {
            stopRecording();
            return maxDuration;
          }
          return prev + 1;
        });
      }, 1000);

    } catch (err) {
      console.error('Recording error:', err);
      setError('Failed to start recording. Please try again.');
      setStatus('error');
    }
  }, [maxDuration]);

  // Stop recording
  const stopRecording = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }

    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
  }, []);

  // Discard recording and re-record
  const discardRecording = useCallback(() => {
    if (videoUrl) {
      URL.revokeObjectURL(videoUrl);
    }
    setVideoBlob(null);
    setVideoUrl(null);
    setRecordingTime(0);
    setStatus('ready');
  }, [videoUrl]);

  // Confirm and send recording
  const confirmRecording = useCallback(() => {
    if (videoBlob && onRecordingComplete) {
      onRecordingComplete(videoBlob, recordingTime);
    }
  }, [videoBlob, recordingTime, onRecordingComplete]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
      }
      if (videoUrl) {
        URL.revokeObjectURL(videoUrl);
      }
    };
  }, [videoUrl]);

  // Request camera on mount
  useEffect(() => {
    requestCamera();
  }, [requestCamera]);

  // Format time as MM:SS
  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Render based on status
  return (
    <div className="video-recorder">
      {/* Error State */}
      {status === 'error' && (
        <div className="recorder-error">
          <div className="error-icon">📹</div>
          <p>{error}</p>
          <button className="retry-btn" onClick={requestCamera}>
            Try Again
          </button>
        </div>
      )}

      {/* Requesting Camera */}
      {status === 'requesting' && (
        <div className="recorder-loading">
          <div className="loading-spinner"></div>
          <p>Requesting camera access...</p>
        </div>
      )}

      {/* Live Preview (Ready/Recording) */}
      {(status === 'ready' || status === 'recording') && (
        <div className="recorder-live">
          <div className="video-container">
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              className="live-video"
            />

            {status === 'recording' && (
              <div className="recording-indicator">
                <span className="rec-dot"></span>
                <span className="rec-time">{formatTime(recordingTime)}</span>
                <span className="rec-max">/ {formatTime(maxDuration)}</span>
              </div>
            )}
          </div>

          <div className="recorder-controls">
            {status === 'ready' && (
              <>
                <button className="cancel-btn" onClick={onCancel}>
                  Cancel
                </button>
                <button className="record-btn" onClick={startRecording}>
                  <span className="rec-icon"></span>
                  Start Recording
                </button>
              </>
            )}

            {status === 'recording' && (
              <button className="stop-btn" onClick={stopRecording}>
                <span className="stop-icon"></span>
                Stop Recording
              </button>
            )}
          </div>
        </div>
      )}

      {/* Recorded Preview */}
      {status === 'recorded' && showPreview && (
        <div className="recorder-preview">
          <div className="video-container">
            <video
              ref={previewRef}
              src={videoUrl}
              controls
              className="preview-video"
            />
            <div className="duration-badge">
              {formatTime(recordingTime)}
            </div>
          </div>

          <div className="recorder-controls">
            <button className="discard-btn" onClick={discardRecording}>
              Re-record
            </button>
            <button className="confirm-btn" onClick={confirmRecording}>
              Use This Video
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default VideoRecorder;
