/**
 * SendVideoModal Component
 *
 * Modal for loan officers to record and send video messages
 * to clients (via PURL workspace) or realtors.
 */

import React, { useState, useCallback } from 'react';
import VideoRecorder from './VideoRecorder';
import './SendVideoModal.css';
import { getToken } from '../../utils/tokenStore';

const API_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

const SendVideoModal = ({
  isOpen,
  onClose,
  recipientType = 'client', // 'client' or 'realtor'
  recipientId, // workspace_id for client, partner_id for realtor
  recipientName = 'Client',
  onSuccess
}) => {
  const [step, setStep] = useState('record'); // record, message, uploading, success, error
  const [videoBlob, setVideoBlob] = useState(null);
  const [videoDuration, setVideoDuration] = useState(0);
  const [message, setMessage] = useState('');
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState(null);

  // Handle recording complete
  const handleRecordingComplete = useCallback((blob, duration) => {
    setVideoBlob(blob);
    setVideoDuration(duration);
    setStep('message');
  }, []);

  // Get auth token
  const getAuthToken = () => {
    return getToken();
  };

  // Upload video to S3 and save metadata
  const handleSendVideo = async () => {
    if (!videoBlob || !recipientId) return;

    setStep('uploading');
    setUploadProgress(0);
    setError(null);

    try {
      const token = getAuthToken();

      // Step 1: Get presigned upload URL
      const uploadUrlResponse = await fetch(`${API_URL}/api/v1/portal-video/upload-url`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          portal_type: recipientType,
          recipient_id: recipientId,
          content_type: 'video/webm',
          filename: `video_${Date.now()}.webm`
        })
      });

      if (!uploadUrlResponse.ok) {
        throw new Error('Failed to get upload URL');
      }

      const { upload_url, video_key } = await uploadUrlResponse.json();
      setUploadProgress(20);

      // Step 2: Upload video to S3
      const uploadResponse = await fetch(upload_url, {
        method: 'PUT',
        headers: {
          'Content-Type': 'video/webm'
        },
        body: videoBlob
      });

      if (!uploadResponse.ok) {
        throw new Error('Failed to upload video');
      }

      setUploadProgress(70);

      // Step 3: Complete upload and save metadata
      const completeResponse = await fetch(`${API_URL}/api/v1/portal-video/complete`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          portal_type: recipientType,
          recipient_id: recipientId,
          video_key: video_key,
          message: message.trim() || null,
          send_notification: true,
          duration_seconds: videoDuration
        })
      });

      if (!completeResponse.ok) {
        throw new Error('Failed to save video');
      }

      setUploadProgress(100);
      setStep('success');

      if (onSuccess) {
        onSuccess();
      }

    } catch (err) {
      console.error('Upload error:', err);
      setError(err.message || 'Failed to send video');
      setStep('error');
    }
  };

  // Reset and close
  const handleClose = () => {
    setStep('record');
    setVideoBlob(null);
    setVideoDuration(0);
    setMessage('');
    setUploadProgress(0);
    setError(null);
    onClose();
  };

  // Go back to recording
  const handleReRecord = () => {
    setVideoBlob(null);
    setVideoDuration(0);
    setStep('record');
  };

  if (!isOpen) return null;

  return (
    <div className="send-video-modal-overlay" onClick={handleClose}>
      <div className="send-video-modal" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="modal-header">
          <h2>
            {step === 'record' && 'Record Video Message'}
            {step === 'message' && 'Add a Message'}
            {step === 'uploading' && 'Sending Video...'}
            {step === 'success' && 'Video Sent!'}
            {step === 'error' && 'Upload Failed'}
          </h2>
          <button className="close-btn" onClick={handleClose}>×</button>
        </div>

        {/* Recipient Info */}
        {step !== 'success' && (
          <div className="recipient-info">
            <span className="recipient-label">To:</span>
            <span className="recipient-name">{recipientName}</span>
            <span className="recipient-type">
              ({recipientType === 'client' ? 'Client Portal' : 'Realtor Portal'})
            </span>
          </div>
        )}

        {/* Content */}
        <div className="modal-content">
          {/* Recording Step */}
          {step === 'record' && (
            <VideoRecorder
              onRecordingComplete={handleRecordingComplete}
              onCancel={handleClose}
              maxDuration={120}
              showPreview={true}
            />
          )}

          {/* Message Step */}
          {step === 'message' && (
            <div className="message-step">
              <div className="video-preview-thumb">
                <video
                  src={URL.createObjectURL(videoBlob)}
                  controls
                  className="preview-video"
                />
                <div className="duration-badge">
                  {Math.floor(videoDuration / 60)}:{(videoDuration % 60).toString().padStart(2, '0')}
                </div>
              </div>

              <div className="message-input-container">
                <label htmlFor="video-message">Add a message (optional)</label>
                <textarea
                  id="video-message"
                  value={message}
                  onChange={e => setMessage(e.target.value)}
                  placeholder="Add a note to accompany your video..."
                  maxLength={500}
                  rows={3}
                />
                <span className="char-count">{message.length}/500</span>
              </div>

              <div className="message-actions">
                <button className="back-btn" onClick={handleReRecord}>
                  Re-record
                </button>
                <button className="send-btn" onClick={handleSendVideo}>
                  Send Video
                </button>
              </div>
            </div>
          )}

          {/* Uploading Step */}
          {step === 'uploading' && (
            <div className="uploading-step">
              <div className="upload-animation">
                <div className="upload-icon">📤</div>
                <div className="progress-bar">
                  <div
                    className="progress-fill"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
                <p className="upload-status">
                  {uploadProgress < 20 && 'Preparing upload...'}
                  {uploadProgress >= 20 && uploadProgress < 70 && 'Uploading video...'}
                  {uploadProgress >= 70 && uploadProgress < 100 && 'Finalizing...'}
                  {uploadProgress === 100 && 'Complete!'}
                </p>
              </div>
            </div>
          )}

          {/* Success Step */}
          {step === 'success' && (
            <div className="success-step">
              <div className="success-icon">✓</div>
              <h3>Video Sent Successfully!</h3>
              <p>
                {recipientName} will see your video message in their{' '}
                {recipientType === 'client' ? 'client portal' : 'realtor portal'}.
              </p>
              <button className="done-btn" onClick={handleClose}>
                Done
              </button>
            </div>
          )}

          {/* Error Step */}
          {step === 'error' && (
            <div className="error-step">
              <div className="error-icon">!</div>
              <h3>Upload Failed</h3>
              <p>{error || 'Something went wrong. Please try again.'}</p>
              <div className="error-actions">
                <button className="retry-btn" onClick={handleSendVideo}>
                  Try Again
                </button>
                <button className="cancel-btn" onClick={handleClose}>
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SendVideoModal;
