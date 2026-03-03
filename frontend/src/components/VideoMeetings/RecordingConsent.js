/**
 * RecordingConsent — Host and participant consent dialogs for recording.
 *
 * Extracted from MeetingRoom.js recording consent logic.
 * Handles:
 * - Host consent dialog (state recording rules, disclosure script)
 * - Participant consent dialog (agree/decline when host starts recording)
 * - Recording banner/indicator
 */
import React, { useState, useCallback } from 'react';
import { getAuthHeaders } from '../../utils/auth';
import { toast } from '../../utils/toast';

const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const API_BASE = isProduction
  ? 'https://api.perenniaai.com'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

// Host Consent Dialog — shown before recording starts
export function HostConsentDialog({ meetingId, onRecordingStarted, onClose }) {
  const [consentState, setConsentState] = useState(null);
  const [loading, setLoading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [stateCode, setStateCode] = useState('');

  const fetchStateRules = useCallback(async (state) => {
    if (!state || state.length !== 2) return;
    setLoading(true);
    try {
      const response = await fetch(
        `${API_BASE}/api/v1/state-recording-rules/by-state/${state.toUpperCase()}`,
        { headers: getAuthHeaders() }
      );
      if (response.ok) {
        const data = await response.json();
        setConsentState(data);
      } else {
        setConsentState({
          state_code: state.toUpperCase(),
          consent_type: 'one_party',
          disclosure_script: 'This meeting may be recorded.',
        });
      }
    } catch {
      toast.error('Could not fetch state recording rules');
    } finally {
      setLoading(false);
    }
  }, []);

  const startRecordingWithConsent = useCallback(async () => {
    setStarting(true);
    try {
      const response = await fetch(
        `${API_BASE}/api/v1/meetings/rooms/${meetingId}/recordings/start-with-consent`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
          body: JSON.stringify({
            consent_type: consentState?.consent_type || 'one_party',
            state_code: consentState?.state_code || stateCode,
            disclosure_script: consentState?.disclosure_script || '',
          }),
        }
      );
      if (response.ok) {
        const data = await response.json();
        onRecordingStarted(data);
        onClose();
        toast.success('Recording started');
      } else {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to start recording');
      }
    } catch (err) {
      toast.error(err.message);
    } finally {
      setStarting(false);
    }
  }, [meetingId, consentState, stateCode, onRecordingStarted, onClose]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="consent-dialog" onClick={(e) => e.stopPropagation()}>
        <h3>Recording Consent Required</h3>

        <div className="consent-state-input">
          <label>Borrower's State:</label>
          <input
            type="text"
            value={stateCode}
            onChange={(e) => {
              const val = e.target.value.toUpperCase().slice(0, 2);
              setStateCode(val);
              if (val.length === 2) fetchStateRules(val);
            }}
            placeholder="CA"
            maxLength={2}
            className="state-input"
          />
        </div>

        {loading && <p>Loading state rules...</p>}

        {consentState && (
          <div className="consent-info">
            <div className={`consent-type-badge ${consentState.consent_type === 'all_party' ? 'warning' : 'info'}`}>
              {consentState.consent_type === 'all_party' ? 'All-Party Consent' : 'One-Party Consent'}
              {' '}({consentState.state_code})
            </div>

            {consentState.disclosure_script && (
              <div className="disclosure-box">
                <strong>Disclosure Script:</strong>
                <p>{consentState.disclosure_script}</p>
              </div>
            )}

            <p className="consent-instruction">
              {consentState.consent_type === 'all_party'
                ? 'All participants will be notified and must consent before recording begins.'
                : 'You may record with one-party consent. Participants will be notified.'}
            </p>
          </div>
        )}

        <div className="consent-actions">
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button
            className="btn-primary"
            onClick={startRecordingWithConsent}
            disabled={!consentState || starting}
          >
            {starting ? 'Starting...' : 'Start Recording'}
          </button>
        </div>
      </div>
    </div>
  );
}

// Participant Consent Dialog — shown when host starts recording
export function ParticipantConsentDialog({ meetingId, recordingId, consentData, onClose }) {
  const [submitting, setSubmitting] = useState(false);

  const submitConsent = useCallback(async (agreed) => {
    setSubmitting(true);
    try {
      const response = await fetch(
        `${API_BASE}/api/v1/meetings/rooms/${meetingId}/recordings/${recordingId}/consent`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
          body: JSON.stringify({ agreed }),
        }
      );
      if (response.ok) {
        toast.info(agreed ? 'Consent recorded' : 'You declined recording consent');
      }
    } catch (err) {
      console.error('Failed to submit consent:', err);
    } finally {
      setSubmitting(false);
      onClose(agreed);
    }
  }, [meetingId, recordingId, onClose]);

  return (
    <div className="modal-overlay">
      <div className="consent-dialog participant-consent">
        <h3>Recording Notice</h3>
        <p>The host has started recording this meeting.</p>

        {consentData?.disclosure_script && (
          <div className="disclosure-box">
            <p>{consentData.disclosure_script}</p>
          </div>
        )}

        <div className="consent-type-info">
          {consentData?.consent_type === 'all_party'
            ? 'Your consent is required to continue in this recorded meeting.'
            : 'This meeting is being recorded with one-party consent.'}
        </div>

        <div className="consent-actions">
          <button
            className="btn-secondary"
            onClick={() => submitConsent(false)}
            disabled={submitting}
          >
            Decline
          </button>
          <button
            className="btn-primary"
            onClick={() => submitConsent(true)}
            disabled={submitting}
          >
            {submitting ? 'Submitting...' : 'I Agree'}
          </button>
        </div>
      </div>
    </div>
  );
}

// Recording Banner — shown to all participants when recording is active
export function RecordingBanner({ startedBy }) {
  return (
    <div className="recording-banner">
      <span className="recording-dot" />
      Recording in progress
      {startedBy && <span className="recording-by"> (started by {startedBy})</span>}
    </div>
  );
}
