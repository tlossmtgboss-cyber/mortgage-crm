/**
 * MeetingDetails - Display virtual meeting information for an appointment.
 *
 * Shows join URL, meeting ID, passcode, dial-in numbers with copy-to-clipboard
 * and "Join Meeting" button. Displays provider-specific icon and styling.
 *
 * Props:
 *   - appointmentId: number (required) - The appointment ID to fetch meeting details for
 *   - meetingData: object (optional) - Pre-loaded meeting data (skips API fetch)
 *   - compact: boolean (optional) - Compact mode for inline display
 *   - onMeetingCreated: function (optional) - Callback after meeting creation
 *   - onMeetingRemoved: function (optional) - Callback after meeting removal
 */

import React, { useState, useEffect, useCallback } from 'react';
import { getToken } from '../../utils/tokenStore';

// Provider configuration
const PROVIDER_CONFIG = {
  zoom: {
    name: 'Zoom',
    color: '#2D8CFF',
    bgColor: '#EBF5FF',
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="20" height="20" rx="4" fill="#2D8CFF"/>
        <path d="M4 7.5C4 6.67 4.67 6 5.5 6H11.5C12.33 6 13 6.67 13 7.5V12.5C13 13.33 12.33 14 11.5 14H5.5C4.67 14 4 13.33 4 12.5V7.5Z" fill="white"/>
        <path d="M13 8.5L16 6.5V13.5L13 11.5V8.5Z" fill="white"/>
      </svg>
    ),
  },
  google_meet: {
    name: 'Google Meet',
    color: '#00897B',
    bgColor: '#E0F2F1',
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="20" height="20" rx="4" fill="#00897B"/>
        <path d="M4 7L7 10L4 13V7Z" fill="white"/>
        <rect x="7" y="6" width="6" height="8" rx="1" fill="white"/>
        <path d="M13 8L16 6V14L13 12V8Z" fill="white"/>
      </svg>
    ),
  },
  teams: {
    name: 'Microsoft Teams',
    color: '#6264A7',
    bgColor: '#ECEDF7',
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="20" height="20" rx="4" fill="#6264A7"/>
        <path d="M6 6H14V14H6V6Z" fill="white" fillOpacity="0.3"/>
        <circle cx="12" cy="7" r="2" fill="white"/>
        <rect x="8" y="9" width="8" height="5" rx="1" fill="white"/>
        <circle cx="7" cy="8" r="1.5" fill="white"/>
        <rect x="4" y="10" width="6" height="4" rx="1" fill="white"/>
      </svg>
    ),
  },
  perennia: {
    name: 'Perennia Meet',
    color: '#1F3D2E',
    bgColor: '#E0F4F5',
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="20" height="20" rx="4" fill="#1F3D2E"/>
        <path d="M5 7.5C5 6.67 5.67 6 6.5 6H13.5C14.33 6 15 6.67 15 7.5V12.5C15 13.33 14.33 14 13.5 14H6.5C5.67 14 5 13.33 5 12.5V7.5Z" fill="white"/>
        <circle cx="10" cy="10" r="2" fill="#1F3D2E"/>
      </svg>
    ),
  },
  manual: {
    name: 'External Link',
    color: '#B8924A',
    bgColor: '#F3E8FF',
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="20" height="20" rx="4" fill="#B8924A"/>
        <path d="M8 7L12 10L8 13V7Z" fill="white"/>
        <rect x="4" y="5" width="12" height="10" rx="2" stroke="white" strokeWidth="1.5" fill="none"/>
      </svg>
    ),
  },
  unknown: {
    name: 'Video Meeting',
    color: '#6B7280',
    bgColor: '#F3F4F6',
    icon: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="20" height="20" rx="4" fill="#6B7280"/>
        <path d="M4 7.5C4 6.67 4.67 6 5.5 6H11.5C12.33 6 13 6.67 13 7.5V12.5C13 13.33 12.33 14 11.5 14H5.5C4.67 14 4 13.33 4 12.5V7.5Z" fill="white"/>
        <path d="M13 8.5L16 6.5V13.5L13 11.5V8.5Z" fill="white"/>
      </svg>
    ),
  },
};

const API_BASE = process.env.REACT_APP_API_URL || '';

const MeetingDetails = ({
  appointmentId,
  meetingData: initialMeetingData = null,
  compact = false,
  onMeetingCreated,
  onMeetingRemoved,
}) => {
  const [meetingData, setMeetingData] = useState(initialMeetingData);
  const [loading, setLoading] = useState(!initialMeetingData);
  const [error, setError] = useState(null);
  const [copiedField, setCopiedField] = useState(null);
  const [showProviderPicker, setShowProviderPicker] = useState(false);
  const [creating, setCreating] = useState(false);
  const [removing, setRemoving] = useState(false);

  // Fetch meeting details from API
  const fetchMeetingDetails = useCallback(async () => {
    if (!appointmentId) return;
    setLoading(true);
    setError(null);

    try {
      const token = getToken();
      const response = await fetch(
        `${API_BASE}/api/v1/scheduler/appointments/${appointmentId}/meeting`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) {
        throw new Error(`Failed to fetch meeting details (${response.status})`);
      }

      const data = await response.json();
      setMeetingData(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [appointmentId]);

  useEffect(() => {
    if (!initialMeetingData && appointmentId) {
      fetchMeetingDetails();
    }
  }, [initialMeetingData, appointmentId, fetchMeetingDetails]);

  // Copy to clipboard
  const copyToClipboard = useCallback(async (text, fieldName) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedField(fieldName);
      setTimeout(() => setCopiedField(null), 2000);
    } catch {
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = text;
      textArea.style.position = 'fixed';
      textArea.style.left = '-9999px';
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      setCopiedField(fieldName);
      setTimeout(() => setCopiedField(null), 2000);
    }
  }, []);

  // Create meeting
  const handleCreateMeeting = useCallback(async (provider = 'auto') => {
    if (!appointmentId) return;
    setCreating(true);
    setError(null);

    try {
      const token = getToken();
      const response = await fetch(
        `${API_BASE}/api/v1/scheduler/appointments/${appointmentId}/meeting`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ provider }),
        }
      );

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `Failed to create meeting (${response.status})`);
      }

      await fetchMeetingDetails();
      if (onMeetingCreated) onMeetingCreated();
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  }, [appointmentId, fetchMeetingDetails, onMeetingCreated]);

  // Remove meeting
  const handleRemoveMeeting = useCallback(async () => {
    if (!appointmentId) return;
    setRemoving(true);
    setError(null);

    try {
      const token = getToken();
      const response = await fetch(
        `${API_BASE}/api/v1/scheduler/appointments/${appointmentId}/meeting`,
        {
          method: 'DELETE',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `Failed to remove meeting (${response.status})`);
      }

      setMeetingData({ has_meeting: false });
      if (onMeetingRemoved) onMeetingRemoved();
    } catch (err) {
      setError(err.message);
    } finally {
      setRemoving(false);
    }
  }, [appointmentId, onMeetingRemoved]);

  // Open join URL in new tab
  const handleJoinMeeting = useCallback(() => {
    if (meetingData?.join_url) {
      window.open(meetingData.join_url, '_blank', 'noopener,noreferrer');
    }
  }, [meetingData]);

  // Loading state
  if (loading) {
    return (
      <div style={styles.container}>
        <div style={styles.loadingText}>Loading meeting details...</div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div style={styles.container}>
        <div style={styles.errorBanner}>
          <span style={styles.errorText}>{error}</span>
          <button onClick={fetchMeetingDetails} style={styles.retryButton}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  // No meeting state
  if (!meetingData || !meetingData.has_meeting) {
    const providerOptions = [
      { key: 'auto', label: 'Auto-detect' },
      { key: 'zoom', label: 'Zoom' },
      { key: 'google_meet', label: 'Google Meet' },
      { key: 'teams', label: 'Microsoft Teams' },
      { key: 'perennia', label: 'Perennia Meet' },
    ];

    return (
      <div style={styles.container}>
        <div style={styles.noMeeting}>
          <span style={styles.noMeetingText}>No meeting link attached</span>
          <div style={styles.createActions}>
            <button
              onClick={() => handleCreateMeeting('auto')}
              disabled={creating}
              style={{
                ...styles.createButton,
                opacity: creating ? 0.6 : 1,
              }}
            >
              {creating ? 'Creating...' : 'Add Meeting Link'}
            </button>
            <button
              onClick={() => setShowProviderPicker(!showProviderPicker)}
              style={styles.providerPickerToggle}
              title="Choose provider"
              disabled={creating}
            >
              {showProviderPicker ? '\u25B2' : '\u25BC'}
            </button>
          </div>
        </div>
        {showProviderPicker && (
          <div style={styles.providerPickerDropdown}>
            {providerOptions.map((opt) => {
              const providerCfg = PROVIDER_CONFIG[opt.key] || PROVIDER_CONFIG.unknown;
              return (
                <button
                  key={opt.key}
                  onClick={() => {
                    setShowProviderPicker(false);
                    handleCreateMeeting(opt.key);
                  }}
                  disabled={creating}
                  style={styles.providerPickerOption}
                >
                  {opt.key !== 'auto' && (
                    <span style={styles.providerPickerIcon}>{providerCfg.icon}</span>
                  )}
                  <span>{opt.label}</span>
                </button>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  // Meeting details display
  const providerKey = meetingData.provider || 'unknown';
  const config = PROVIDER_CONFIG[providerKey] || PROVIDER_CONFIG.unknown;

  if (compact) {
    return (
      <div style={styles.compactContainer}>
        <div style={styles.compactRow}>
          <span style={styles.providerIcon}>{config.icon}</span>
          <span style={{ ...styles.providerName, color: config.color }}>{config.name}</span>
          <button onClick={handleJoinMeeting} style={styles.compactJoinButton}>
            Join
          </button>
          <button
            onClick={() => copyToClipboard(meetingData.join_url, 'link')}
            style={styles.compactCopyButton}
            title="Copy link"
          >
            {copiedField === 'link' ? 'Copied' : 'Copy'}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      {/* Provider Header */}
      <div style={{ ...styles.providerHeader, backgroundColor: config.bgColor }}>
        <div style={styles.providerHeaderLeft}>
          <span style={styles.providerIcon}>{config.icon}</span>
          <span style={{ ...styles.providerName, color: config.color }}>{config.name}</span>
        </div>
        <button
          onClick={handleRemoveMeeting}
          disabled={removing}
          style={styles.removeButton}
          title="Remove meeting"
        >
          {removing ? '...' : 'Remove'}
        </button>
      </div>

      {/* Join Button */}
      <button onClick={handleJoinMeeting} style={{ ...styles.joinButton, backgroundColor: config.color }}>
        Join Meeting
      </button>

      {/* Meeting Link */}
      <div style={styles.detailRow}>
        <span style={styles.detailLabel}>Meeting Link</span>
        <div style={styles.copyableRow}>
          <span style={styles.detailValue}>{truncateUrl(meetingData.join_url)}</span>
          <button
            onClick={() => copyToClipboard(meetingData.join_url, 'join_url')}
            style={styles.copyButton}
          >
            {copiedField === 'join_url' ? 'Copied!' : 'Copy'}
          </button>
        </div>
      </div>

      {/* Meeting ID */}
      {meetingData.meeting_id && (
        <div style={styles.detailRow}>
          <span style={styles.detailLabel}>Meeting ID</span>
          <div style={styles.copyableRow}>
            <span style={styles.detailValue}>{meetingData.meeting_id}</span>
            <button
              onClick={() => copyToClipboard(meetingData.meeting_id, 'meeting_id')}
              style={styles.copyButton}
            >
              {copiedField === 'meeting_id' ? 'Copied!' : 'Copy'}
            </button>
          </div>
        </div>
      )}

      {/* Passcode */}
      {meetingData.passcode && (
        <div style={styles.detailRow}>
          <span style={styles.detailLabel}>Passcode</span>
          <div style={styles.copyableRow}>
            <span style={styles.detailValue}>{meetingData.passcode}</span>
            <button
              onClick={() => copyToClipboard(meetingData.passcode, 'passcode')}
              style={styles.copyButton}
            >
              {copiedField === 'passcode' ? 'Copied!' : 'Copy'}
            </button>
          </div>
        </div>
      )}

      {/* Dial-in Numbers */}
      {meetingData.dial_in_numbers && meetingData.dial_in_numbers.length > 0 && (
        <div style={styles.detailRow}>
          <span style={styles.detailLabel}>Dial-in Numbers</span>
          <div style={styles.dialInList}>
            {meetingData.dial_in_numbers.map((num, idx) => (
              <div key={idx} style={styles.dialInItem}>
                <span style={styles.dialInNumber}>{num.number}</span>
                {num.country && <span style={styles.dialInCountry}>({num.country})</span>}
                <button
                  onClick={() => copyToClipboard(num.number, `dial_${idx}`)}
                  style={styles.copyButton}
                >
                  {copiedField === `dial_${idx}` ? 'Copied!' : 'Copy'}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

// Utility to truncate long URLs for display
function truncateUrl(url) {
  if (!url) return '';
  if (url.length <= 50) return url;
  return url.substring(0, 47) + '...';
}

// Inline styles
const styles = {
  container: {
    border: '1px solid #E5E7EB',
    borderRadius: '8px',
    padding: '16px',
    backgroundColor: '#FFFFFF',
  },
  compactContainer: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '8px',
  },
  compactRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  loadingText: {
    color: '#6B7280',
    fontSize: '14px',
    textAlign: 'center',
    padding: '8px 0',
  },
  errorBanner: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '8px 12px',
    backgroundColor: '#FEF2F2',
    borderRadius: '6px',
  },
  errorText: {
    color: '#DC2626',
    fontSize: '13px',
  },
  retryButton: {
    padding: '4px 12px',
    fontSize: '12px',
    color: '#DC2626',
    backgroundColor: 'transparent',
    border: '1px solid #DC2626',
    borderRadius: '4px',
    cursor: 'pointer',
  },
  noMeeting: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '4px 0',
  },
  noMeetingText: {
    color: '#9CA3AF',
    fontSize: '14px',
  },
  createActions: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
  },
  createButton: {
    padding: '6px 16px',
    fontSize: '13px',
    color: '#FFFFFF',
    backgroundColor: '#1F3D2E',
    border: 'none',
    borderRadius: '6px 0 0 6px',
    cursor: 'pointer',
    fontWeight: 500,
  },
  providerPickerToggle: {
    padding: '6px 8px',
    fontSize: '11px',
    color: '#FFFFFF',
    backgroundColor: '#1a6670',
    border: 'none',
    borderRadius: '0 6px 6px 0',
    cursor: 'pointer',
    lineHeight: 1,
  },
  providerPickerDropdown: {
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
    marginTop: '8px',
    padding: '6px',
    backgroundColor: '#F9FAFB',
    borderRadius: '6px',
    border: '1px solid #E5E7EB',
  },
  providerPickerOption: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '6px 10px',
    fontSize: '13px',
    color: '#374151',
    backgroundColor: 'transparent',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
    textAlign: 'left',
    width: '100%',
  },
  providerPickerIcon: {
    display: 'flex',
    alignItems: 'center',
    flexShrink: 0,
  },
  providerHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '8px 12px',
    borderRadius: '6px',
    marginBottom: '12px',
  },
  providerHeaderLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  providerIcon: {
    display: 'flex',
    alignItems: 'center',
  },
  providerName: {
    fontSize: '14px',
    fontWeight: 600,
  },
  removeButton: {
    padding: '4px 10px',
    fontSize: '12px',
    color: '#6B7280',
    backgroundColor: 'transparent',
    border: '1px solid #D1D5DB',
    borderRadius: '4px',
    cursor: 'pointer',
  },
  joinButton: {
    display: 'block',
    width: '100%',
    padding: '10px 0',
    fontSize: '14px',
    fontWeight: 600,
    color: '#FFFFFF',
    border: 'none',
    borderRadius: '6px',
    cursor: 'pointer',
    textAlign: 'center',
    marginBottom: '16px',
  },
  compactJoinButton: {
    padding: '4px 10px',
    fontSize: '12px',
    fontWeight: 600,
    color: '#FFFFFF',
    backgroundColor: '#1F3D2E',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
  },
  compactCopyButton: {
    padding: '4px 8px',
    fontSize: '11px',
    color: '#6B7280',
    backgroundColor: 'transparent',
    border: '1px solid #D1D5DB',
    borderRadius: '4px',
    cursor: 'pointer',
  },
  detailRow: {
    marginBottom: '12px',
  },
  detailLabel: {
    display: 'block',
    fontSize: '12px',
    color: '#6B7280',
    marginBottom: '4px',
    fontWeight: 500,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  copyableRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  detailValue: {
    fontSize: '14px',
    color: '#111827',
    wordBreak: 'break-all',
    flex: 1,
  },
  copyButton: {
    padding: '4px 10px',
    fontSize: '12px',
    color: '#6B7280',
    backgroundColor: '#F9FAFB',
    border: '1px solid #E5E7EB',
    borderRadius: '4px',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    flexShrink: 0,
  },
  dialInList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  dialInItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  dialInNumber: {
    fontSize: '14px',
    color: '#111827',
    fontFamily: 'monospace',
  },
  dialInCountry: {
    fontSize: '12px',
    color: '#9CA3AF',
  },
};

export default MeetingDetails;
