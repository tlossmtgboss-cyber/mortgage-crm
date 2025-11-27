import React, { useState, useRef, useEffect, useCallback } from 'react';
import axios from 'axios';
import './ClipRecorder.css';

const ClipRecorder = ({
  onRecordingComplete,
  onClose,
  templateId = null,
  crmEntityType = null,
  crmEntityId = null,
  suggestedTitle = ''
}) => {
  // State
  const [recordingState, setRecordingState] = useState('idle'); // idle, preview, recording, processing
  const [clipType, setClipType] = useState('screen_camera');
  const [title, setTitle] = useState(suggestedTitle);
  const [description, setDescription] = useState('');
  const [duration, setDuration] = useState(0);
  const [error, setError] = useState(null);
  const [devices, setDevices] = useState({ cameras: [], microphones: [] });
  const [selectedCamera, setSelectedCamera] = useState('');
  const [selectedMic, setSelectedMic] = useState('');
  const [screenStream, setScreenStream] = useState(null);
  const [cameraStream, setCameraStream] = useState(null);
  const [recordedBlob, setRecordedBlob] = useState(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [countdown, setCountdown] = useState(0);

  // Refs
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const previewVideoRef = useRef(null);
  const cameraVideoRef = useRef(null);
  const recordedVideoRef = useRef(null);
  const timerRef = useRef(null);

  // Get available devices
  useEffect(() => {
    const getDevices = async () => {
      try {
        // Request permissions first
        await navigator.mediaDevices.getUserMedia({ video: true, audio: true });

        const deviceList = await navigator.mediaDevices.enumerateDevices();

        const cameras = deviceList.filter(d => d.kind === 'videoinput');
        const microphones = deviceList.filter(d => d.kind === 'audioinput');

        setDevices({ cameras, microphones });

        if (cameras.length > 0) setSelectedCamera(cameras[0].deviceId);
        if (microphones.length > 0) setSelectedMic(microphones[0].deviceId);
      } catch (err) {
        console.error('Error getting devices:', err);
        setError('Please allow camera and microphone access');
      }
    };

    getDevices();

    return () => {
      stopAllStreams();
    };
  }, []);

  // Clean up streams
  const stopAllStreams = useCallback(() => {
    if (screenStream) {
      screenStream.getTracks().forEach(track => track.stop());
      setScreenStream(null);
    }
    if (cameraStream) {
      cameraStream.getTracks().forEach(track => track.stop());
      setCameraStream(null);
    }
  }, [screenStream, cameraStream]);

  // Start preview
  const startPreview = async () => {
    try {
      setError(null);
      stopAllStreams();

      let streams = [];

      // Get screen stream for screen recording modes
      if (clipType === 'screen_camera' || clipType === 'screen_only') {
        const screen = await navigator.mediaDevices.getDisplayMedia({
          video: {
            cursor: 'always',
            width: { ideal: 1920 },
            height: { ideal: 1080 }
          },
          audio: true
        });
        setScreenStream(screen);
        streams.push(screen);

        // Handle user stopping screen share
        screen.getVideoTracks()[0].onended = () => {
          stopPreview();
        };
      }

      // Get camera stream
      if (clipType === 'screen_camera' || clipType === 'camera_only') {
        const camera = await navigator.mediaDevices.getUserMedia({
          video: selectedCamera ? { deviceId: selectedCamera } : true,
          audio: selectedMic ? { deviceId: selectedMic } : true
        });
        setCameraStream(camera);
        streams.push(camera);

        // Show camera preview
        if (cameraVideoRef.current) {
          cameraVideoRef.current.srcObject = camera;
        }
      }

      // Set preview video
      if (previewVideoRef.current && streams.length > 0) {
        previewVideoRef.current.srcObject = streams[0];
      }

      setRecordingState('preview');
    } catch (err) {
      console.error('Error starting preview:', err);
      if (err.name === 'NotAllowedError') {
        setError('Screen sharing was denied. Please try again.');
      } else {
        setError('Failed to start preview: ' + err.message);
      }
    }
  };

  // Stop preview
  const stopPreview = () => {
    stopAllStreams();
    setRecordingState('idle');
  };

  // Start recording with countdown
  const startRecording = () => {
    setCountdown(3);

    const countdownInterval = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) {
          clearInterval(countdownInterval);
          actuallyStartRecording();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  };

  // Actually start the recording
  const actuallyStartRecording = () => {
    try {
      chunksRef.current = [];

      // Combine streams for recording
      let combinedStream;

      if (clipType === 'screen_camera' && screenStream && cameraStream) {
        // For screen + camera, we record the screen stream with camera audio
        // In a production app, you'd use canvas to composite them
        combinedStream = screenStream;

        // Add audio from camera if screen doesn't have it
        const screenAudio = screenStream.getAudioTracks();
        const cameraAudio = cameraStream.getAudioTracks();

        if (screenAudio.length === 0 && cameraAudio.length > 0) {
          cameraAudio.forEach(track => combinedStream.addTrack(track));
        }
      } else if (clipType === 'screen_only' && screenStream) {
        combinedStream = screenStream;
      } else if (clipType === 'camera_only' && cameraStream) {
        combinedStream = cameraStream;
      }

      if (!combinedStream) {
        setError('No stream available for recording');
        return;
      }

      // Create MediaRecorder
      const mimeType = MediaRecorder.isTypeSupported('video/webm;codecs=vp9')
        ? 'video/webm;codecs=vp9'
        : 'video/webm';

      mediaRecorderRef.current = new MediaRecorder(combinedStream, {
        mimeType,
        videoBitsPerSecond: 2500000
      });

      mediaRecorderRef.current.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      mediaRecorderRef.current.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mimeType });
        setRecordedBlob(blob);
        stopAllStreams();

        // Show recorded video
        if (recordedVideoRef.current) {
          recordedVideoRef.current.src = URL.createObjectURL(blob);
        }
      };

      mediaRecorderRef.current.start(1000); // Collect data every second
      setRecordingState('recording');
      setDuration(0);

      // Start duration timer
      timerRef.current = setInterval(() => {
        setDuration(prev => prev + 1);
      }, 1000);

    } catch (err) {
      console.error('Error starting recording:', err);
      setError('Failed to start recording: ' + err.message);
    }
  };

  // Stop recording
  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }

    if (timerRef.current) {
      clearInterval(timerRef.current);
    }

    setRecordingState('processing');
  };

  // Re-record
  const reRecord = () => {
    setRecordedBlob(null);
    setRecordingState('idle');
    setDuration(0);
  };

  // Save clip
  const saveClip = async () => {
    if (!title.trim()) {
      setError('Please enter a title for your clip');
      return;
    }

    if (!recordedBlob) {
      setError('No recording available');
      return;
    }

    try {
      setRecordingState('uploading');
      setUploadProgress(0);

      // Step 1: Create clip record
      const createResponse = await axios.post('/api/v1/clips/', {
        title: title.trim(),
        description: description.trim(),
        clip_type: clipType,
        template_id: templateId,
        crm_entity_type: crmEntityType,
        crm_entity_id: crmEntityId
      });

      const { clip_id, upload_url, storage_path } = createResponse.data;

      // Step 2: Upload video
      setUploadProgress(10);

      if (upload_url.startsWith('/api/')) {
        // Mock upload for development
        await new Promise(resolve => setTimeout(resolve, 1000));
        setUploadProgress(80);
      } else {
        // Real S3 upload
        await axios.put(upload_url, recordedBlob, {
          headers: { 'Content-Type': 'video/webm' },
          onUploadProgress: (progressEvent) => {
            const progress = Math.round(
              (progressEvent.loaded * 70) / progressEvent.total
            ) + 10;
            setUploadProgress(progress);
          }
        });
      }

      // Step 3: Mark upload complete
      await axios.post(`/api/v1/clips/${clip_id}/upload-complete`, {
        file_size_bytes: recordedBlob.size,
        duration_seconds: duration,
        video_width: 1920,
        video_height: 1080
      });

      setUploadProgress(100);

      // Callback with new clip
      if (onRecordingComplete) {
        onRecordingComplete({
          id: clip_id,
          title,
          duration_seconds: duration,
          status: 'processing'
        });
      }

      // Close recorder
      if (onClose) {
        onClose();
      }

    } catch (err) {
      console.error('Error saving clip:', err);
      setError('Failed to save clip: ' + (err.response?.data?.detail || err.message));
      setRecordingState('processing');
    }
  };

  // Format duration
  const formatDuration = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="clip-recorder">
      {/* Header */}
      <div className="recorder-header">
        <h2>
          {recordingState === 'idle' && 'Create Video Clip'}
          {recordingState === 'preview' && 'Ready to Record'}
          {recordingState === 'recording' && 'Recording...'}
          {recordingState === 'processing' && 'Review Recording'}
          {recordingState === 'uploading' && 'Saving Clip...'}
        </h2>
        <button className="close-button" onClick={onClose}>×</button>
      </div>

      {/* Error display */}
      {error && (
        <div className="recorder-error">
          <span>{error}</span>
          <button onClick={() => setError(null)}>×</button>
        </div>
      )}

      {/* Main content */}
      <div className="recorder-content">
        {/* Countdown overlay */}
        {countdown > 0 && (
          <div className="countdown-overlay">
            <span className="countdown-number">{countdown}</span>
          </div>
        )}

        {/* Idle state - show options */}
        {recordingState === 'idle' && (
          <div className="recorder-setup">
            <div className="setup-section">
              <h3>Recording Type</h3>
              <div className="clip-type-options">
                <button
                  className={`type-option ${clipType === 'screen_camera' ? 'active' : ''}`}
                  onClick={() => setClipType('screen_camera')}
                >
                  <span className="option-icon">🖥️👤</span>
                  <span className="option-label">Screen + Camera</span>
                  <span className="option-desc">Best for walkthroughs</span>
                </button>
                <button
                  className={`type-option ${clipType === 'screen_only' ? 'active' : ''}`}
                  onClick={() => setClipType('screen_only')}
                >
                  <span className="option-icon">🖥️</span>
                  <span className="option-label">Screen Only</span>
                  <span className="option-desc">Share your screen</span>
                </button>
                <button
                  className={`type-option ${clipType === 'camera_only' ? 'active' : ''}`}
                  onClick={() => setClipType('camera_only')}
                >
                  <span className="option-icon">👤</span>
                  <span className="option-label">Camera Only</span>
                  <span className="option-desc">Face-to-face message</span>
                </button>
              </div>
            </div>

            <div className="setup-section">
              <h3>Device Settings</h3>
              <div className="device-selectors">
                {(clipType === 'screen_camera' || clipType === 'camera_only') && (
                  <div className="device-selector">
                    <label>Camera</label>
                    <select
                      value={selectedCamera}
                      onChange={(e) => setSelectedCamera(e.target.value)}
                    >
                      {devices.cameras.map(device => (
                        <option key={device.deviceId} value={device.deviceId}>
                          {device.label || `Camera ${devices.cameras.indexOf(device) + 1}`}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                <div className="device-selector">
                  <label>Microphone</label>
                  <select
                    value={selectedMic}
                    onChange={(e) => setSelectedMic(e.target.value)}
                  >
                    {devices.microphones.map(device => (
                      <option key={device.deviceId} value={device.deviceId}>
                        {device.label || `Mic ${devices.microphones.indexOf(device) + 1}`}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </div>

            <button className="start-preview-btn" onClick={startPreview}>
              Start Preview
            </button>
          </div>
        )}

        {/* Preview state */}
        {recordingState === 'preview' && (
          <div className="recorder-preview">
            <div className="preview-container">
              <video
                ref={previewVideoRef}
                autoPlay
                muted
                playsInline
                className="preview-video"
              />
              {clipType === 'screen_camera' && (
                <div className="camera-pip">
                  <video
                    ref={cameraVideoRef}
                    autoPlay
                    muted
                    playsInline
                  />
                </div>
              )}
            </div>
            <div className="preview-controls">
              <button className="cancel-btn" onClick={stopPreview}>
                Cancel
              </button>
              <button className="record-btn" onClick={startRecording}>
                <span className="record-icon"></span>
                Start Recording
              </button>
            </div>
          </div>
        )}

        {/* Recording state */}
        {recordingState === 'recording' && (
          <div className="recorder-recording">
            <div className="preview-container recording">
              <video
                ref={previewVideoRef}
                autoPlay
                muted
                playsInline
                className="preview-video"
              />
              {clipType === 'screen_camera' && (
                <div className="camera-pip">
                  <video
                    ref={cameraVideoRef}
                    autoPlay
                    muted
                    playsInline
                  />
                </div>
              )}
              <div className="recording-indicator">
                <span className="recording-dot"></span>
                <span className="recording-time">{formatDuration(duration)}</span>
              </div>
            </div>
            <div className="recording-controls">
              <button className="stop-btn" onClick={stopRecording}>
                <span className="stop-icon"></span>
                Stop Recording
              </button>
            </div>
          </div>
        )}

        {/* Processing/Review state */}
        {recordingState === 'processing' && recordedBlob && (
          <div className="recorder-review">
            <div className="review-container">
              <video
                ref={recordedVideoRef}
                controls
                className="review-video"
              />
            </div>
            <div className="review-form">
              <div className="form-group">
                <label>Title *</label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Give your clip a title..."
                />
              </div>
              <div className="form-group">
                <label>Description</label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Add a description (optional)..."
                  rows={3}
                />
              </div>
              <div className="review-stats">
                <span>Duration: {formatDuration(duration)}</span>
                <span>Size: {(recordedBlob.size / (1024 * 1024)).toFixed(1)} MB</span>
              </div>
            </div>
            <div className="review-controls">
              <button className="rerecord-btn" onClick={reRecord}>
                Re-record
              </button>
              <button className="save-btn" onClick={saveClip}>
                Save Clip
              </button>
            </div>
          </div>
        )}

        {/* Uploading state */}
        {recordingState === 'uploading' && (
          <div className="recorder-uploading">
            <div className="upload-progress">
              <div className="progress-bar">
                <div
                  className="progress-fill"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
              <span className="progress-text">
                {uploadProgress < 100
                  ? `Uploading... ${uploadProgress}%`
                  : 'Processing...'}
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ClipRecorder;
