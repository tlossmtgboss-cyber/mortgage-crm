/**
 * Call Disposition Modal Component
 * Allows agents to log call outcomes and notes after completing a call
 */

import React, { useState, useRef } from 'react';
import { X, Mic, MicOff, Loader2 } from 'lucide-react';
import axios from 'axios';
import { getToken } from '../../utils/tokenStore';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

// Disposition options
const DISPOSITION_OPTIONS = [
  'Answered - Conversation completed',
  'No Answer - Rang but no pickup',
  'Left Voicemail',
  'Wrong Number - Invalid number',
  'Wrong Person - Right number, wrong contact',
  'Do Not Call Again',
  'Busy Signal',
  'Follow-up Required',
  'Referral Opportunity',
  'Appointment Set',
  'Spanish Speaker',
  'Callback Scheduled'
];

// Dispositions that require a follow-up date
const REQUIRES_FOLLOW_UP = [
  'Follow-up Required',
  'Appointment Set',
  'Callback Scheduled'
];

/**
 * @param {Object} props
 * @param {string|number} props.taskId - Task ID (for dialer session)
 * @param {string|number} [props.sessionId] - Session ID (if part of dialer session)
 * @param {string} [props.callLogId] - Call log ID (for click-to-dial)
 * @param {string} props.contactName - Contact name
 * @param {number} [props.callDuration] - Call duration in seconds
 * @param {string} [props.callOutcome] - Call outcome from Telnyx
 * @param {function} props.onClose - Close modal callback
 * @param {function} [props.onSaved] - Callback when disposition is saved
 */
const DispositionModal = ({
  taskId,
  sessionId,
  callLogId,
  contactName,
  callDuration,
  callOutcome,
  onClose,
  onSaved
}) => {
  const [disposition, setDisposition] = useState('');
  const [notes, setNotes] = useState('');
  const [followUpDate, setFollowUpDate] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [audioBlob, setAudioBlob] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);

  // Audio recording refs
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);

  // Check if follow-up date is required
  const requiresFollowUpDate = REQUIRES_FOLLOW_UP.includes(disposition);

  // Determine flags from disposition
  const getFlags = () => ({
    follow_up_required: requiresFollowUpDate,
    referral_opportunity: disposition === 'Referral Opportunity',
    appointment_set: disposition === 'Appointment Set'
  });

  // Format duration
  const formatDuration = (seconds) => {
    if (!seconds) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Start voice recording
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorderRef.current = new MediaRecorder(stream);
      audioChunksRef.current = [];

      mediaRecorderRef.current.ondataavailable = (event) => {
        audioChunksRef.current.push(event.data);
      };

      mediaRecorderRef.current.onstop = () => {
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        setAudioBlob(blob);
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorderRef.current.start();
      setIsRecording(true);
    } catch (err) {
      console.error('Error starting recording:', err);
      setError('Could not access microphone');
    }
  };

  // Stop voice recording
  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  // Convert blob to base64
  const blobToBase64 = (blob) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        const base64 = reader.result.split(',')[1];
        resolve(base64);
      };
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  };

  // Submit disposition
  const handleSubmit = async () => {
    if (!disposition) {
      setError('Please select a disposition');
      return;
    }

    if (requiresFollowUpDate && !followUpDate) {
      setError('Please select a follow-up date');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      let voiceNoteBase64 = null;
      if (audioBlob) {
        voiceNoteBase64 = await blobToBase64(audioBlob);
      }

      // Determine endpoint based on whether this is a session task or standalone call
      const endpoint = sessionId && taskId
        ? `${API_BASE}/api/v1/dialer/task/${taskId}/disposition`
        : `${API_BASE}/api/v1/dialer/call-log/${callLogId}/disposition`;

      const flags = getFlags();

      const response = await axios.post(
        endpoint,
        {
          disposition,
          notes: notes || null,
          follow_up_date: followUpDate || null,
          voice_note_audio: voiceNoteBase64,
          follow_up_required: flags.follow_up_required,
          referral_opportunity: flags.referral_opportunity
        },
        {
          headers: {
            Authorization: `Bearer ${getToken()}`,
            'Content-Type': 'application/json'
          },
          params: sessionId ? { session_id: sessionId } : {}
        }
      );

      if (response.data.success) {
        // Show AI summary if available
        if (response.data.ai_note_summary) {
          console.log('AI Summary:', response.data.ai_note_summary);
        }

        // Call callbacks
        onSaved?.();
        onClose();
      } else {
        setError(response.data.error || 'Failed to save disposition');
      }
    } catch (err) {
      console.error('Error saving disposition:', err);
      setError(err.response?.data?.detail || 'Failed to save disposition');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-md mx-4">
        {/* Header */}
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold">Call Disposition</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
            disabled={isSubmitting}
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Contact Info */}
        <div className="mb-4 pb-4 border-b">
          <div className="text-sm text-gray-600">Contact</div>
          <div className="text-lg font-semibold">{contactName}</div>
          {callDuration !== undefined && (
            <div className="text-sm text-gray-500 mt-1">
              Duration: {formatDuration(callDuration)}
            </div>
          )}
        </div>

        <div className="space-y-4">
          {/* Disposition Dropdown */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Disposition <span className="text-red-500">*</span>
            </label>
            <select
              value={disposition}
              onChange={(e) => setDisposition(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={isSubmitting}
            >
              <option value="">Select disposition...</option>
              {DISPOSITION_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>

          {/* Follow-up Date (conditional) */}
          {requiresFollowUpDate && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Follow-up Date <span className="text-red-500">*</span>
              </label>
              <input
                type="datetime-local"
                value={followUpDate}
                onChange={(e) => setFollowUpDate(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                disabled={isSubmitting}
              />
            </div>
          )}

          {/* Notes */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Notes
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="Add any relevant notes about the call..."
              disabled={isSubmitting}
            />
          </div>

          {/* Voice Note */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Voice Note (optional)
            </label>
            <div className="flex items-center gap-3">
              {!audioBlob ? (
                <button
                  onClick={isRecording ? stopRecording : startRecording}
                  disabled={isSubmitting}
                  className={`flex items-center gap-2 px-4 py-2 rounded-md transition-colors ${
                    isRecording
                      ? 'bg-red-500 text-white hover:bg-red-600'
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  } disabled:opacity-50`}
                >
                  {isRecording ? (
                    <>
                      <MicOff className="w-4 h-4" />
                      Stop
                    </>
                  ) : (
                    <>
                      <Mic className="w-4 h-4" />
                      Record
                    </>
                  )}
                </button>
              ) : (
                <div className="flex items-center gap-2">
                  <span className="text-sm text-green-600">✓ Recorded</span>
                  <button
                    onClick={() => setAudioBlob(null)}
                    className="text-sm text-red-600 hover:text-red-700"
                    disabled={isSubmitting}
                  >
                    Remove
                  </button>
                </div>
              )}
              {isRecording && (
                <div className="flex items-center text-red-500 text-sm">
                  <div className="w-2 h-2 bg-red-500 rounded-full animate-pulse mr-2" />
                  Recording...
                </div>
              )}
            </div>
            <p className="text-xs text-gray-500 mt-1">
              Voice notes are transcribed and summarized by AI
            </p>
          </div>

          {/* Error */}
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
              {error}
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex space-x-3">
            <button
              onClick={handleSubmit}
              disabled={isSubmitting}
              className="flex-1 bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center justify-center"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                  Submitting...
                </>
              ) : (
                'Submit'
              )}
            </button>
            <button
              onClick={onClose}
              disabled={isSubmitting}
              className="px-4 py-2 border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50"
            >
              Cancel
            </button>
          </div>

          {/* Helper text */}
          <div className="text-xs text-gray-500 text-center">
            Submission required before next call begins
          </div>
        </div>
      </div>
    </div>
  );
};

export default DispositionModal;
