import React, { useState, useEffect, useCallback } from 'react';
import { getToken } from '../../utils/tokenStore';

const API_BASE = process.env.REACT_APP_API_URL || '';

async function apiFetch(path, options = {}) {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `API error ${res.status}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function CopyButton({ text, label }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for older browsers
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [text]);

  return (
    <button
      onClick={handleCopy}
      title={`Copy ${label || 'URL'}`}
      aria-label={`Copy ${label || 'URL'} to clipboard`}
      style={{
        padding: '6px 14px',
        borderRadius: 8,
        border: '1px solid #d1d5db',
        background: copied ? '#dcfce7' : '#fff',
        color: copied ? '#166534' : '#374151',
        cursor: 'pointer',
        fontSize: 13,
        fontWeight: 500,
        transition: 'all 0.2s',
        whiteSpace: 'nowrap',
      }}
    >
      {copied ? 'Copied!' : 'Copy'}
    </button>
  );
}

function FeedUrlDisplay({ label, url, icon }) {
  if (!url) return null;
  return (
    <div style={{ marginBottom: 12 }}>
      <label style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4, color: '#374151' }}>
        {icon && <span style={{ marginRight: 6 }}>{icon}</span>}
        {label}
      </label>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <input
          type="text"
          readOnly
          value={url}
          onFocus={e => e.target.select()}
          style={{
            flex: 1,
            padding: '8px 12px',
            borderRadius: 8,
            border: '1px solid #d1d5db',
            fontSize: 13,
            fontFamily: 'monospace',
            background: '#f9fafb',
            color: '#374151',
          }}
        />
        <CopyButton text={url} label={label} />
      </div>
    </div>
  );
}

function SetupInstructions({ feedUrl, webcalUrl }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div style={{ marginTop: 16 }}>
      <button
        onClick={() => setExpanded(!expanded)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          fontSize: 14,
          fontWeight: 500,
          color: '#3b82f6',
          padding: 0,
        }}
      >
        <span style={{
          display: 'inline-block',
          transition: 'transform 0.2s',
          transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)',
        }}>
          &#9654;
        </span>
        Setup Instructions
      </button>

      {expanded && (
        <div style={{
          marginTop: 12,
          padding: 16,
          background: '#f9fafb',
          borderRadius: 12,
          border: '1px solid #e5e7eb',
        }}>
          <div style={{ marginBottom: 16 }}>
            <h4 style={{ margin: '0 0 8px 0', fontSize: 14, color: '#111827' }}>
              Apple Calendar (macOS / iOS)
            </h4>
            <ol style={{ margin: 0, paddingLeft: 20, fontSize: 13, color: '#4b5563', lineHeight: 1.8 }}>
              <li>Click the webcal:// link above, or copy it</li>
              <li>On macOS: open Calendar app, File &gt; New Calendar Subscription, paste the URL</li>
              <li>On iOS: go to Settings &gt; Calendar &gt; Accounts &gt; Add Account &gt; Other &gt; Add Subscribed Calendar</li>
              <li>Set auto-refresh to every 15 minutes (recommended)</li>
            </ol>
          </div>

          <div style={{ marginBottom: 16 }}>
            <h4 style={{ margin: '0 0 8px 0', fontSize: 14, color: '#111827' }}>
              Google Calendar
            </h4>
            <ol style={{ margin: 0, paddingLeft: 20, fontSize: 13, color: '#4b5563', lineHeight: 1.8 }}>
              <li>Open <a href="https://calendar.google.com" target="_blank" rel="noopener noreferrer" style={{ color: '#3b82f6' }}>Google Calendar</a> in a browser</li>
              <li>On the left sidebar, find &quot;Other calendars&quot; and click the + icon</li>
              <li>Select &quot;From URL&quot;</li>
              <li>Paste the HTTPS feed URL and click &quot;Add calendar&quot;</li>
              <li>Note: Google Calendar refreshes subscribed calendars every ~12-24 hours</li>
            </ol>
          </div>

          <div>
            <h4 style={{ margin: '0 0 8px 0', fontSize: 14, color: '#111827' }}>
              Microsoft Outlook
            </h4>
            <ol style={{ margin: 0, paddingLeft: 20, fontSize: 13, color: '#4b5563', lineHeight: 1.8 }}>
              <li>Open Outlook (desktop or web)</li>
              <li>Go to Calendar view</li>
              <li>Click &quot;Add Calendar&quot; &gt; &quot;Subscribe from web&quot; (or &quot;From internet&quot;)</li>
              <li>Paste the HTTPS feed URL and give it a name</li>
              <li>Click &quot;Import&quot; or &quot;Save&quot;</li>
            </ol>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function CalendarFeedSettings() {
  const [feedStatus, setFeedStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [revoking, setRevoking] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [includeDetails, setIncludeDetails] = useState(true);

  // Fetch current feed status
  const fetchStatus = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiFetch('/api/v1/scheduler/feed/status');
      setFeedStatus(data);
      if (data.include_details !== null && data.include_details !== undefined) {
        setIncludeDetails(data.include_details);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  // Generate new token
  const handleGenerate = useCallback(async () => {
    setError('');
    setSuccess('');
    setGenerating(true);
    try {
      const data = await apiFetch('/api/v1/scheduler/feed/generate-token', {
        method: 'POST',
        body: JSON.stringify({ include_details: includeDetails }),
      });
      setFeedStatus({
        is_active: true,
        feed_url: data.feed_url,
        webcal_url: data.webcal_url,
        include_details: data.include_details,
        access_count: 0,
        last_accessed_at: null,
        created_at: data.created_at,
      });
      setSuccess('Calendar feed URL generated! Add it to your calendar app.');
      setTimeout(() => setSuccess(''), 5000);
    } catch (err) {
      setError(err.message);
    } finally {
      setGenerating(false);
    }
  }, [includeDetails]);

  // Revoke token
  const handleRevoke = useCallback(async () => {
    if (!window.confirm(
      'Revoke your calendar feed? Any calendar apps using this URL will stop receiving updates.'
    )) {
      return;
    }
    setError('');
    setSuccess('');
    setRevoking(true);
    try {
      await apiFetch('/api/v1/scheduler/feed/revoke', { method: 'DELETE' });
      setFeedStatus({
        is_active: false,
        feed_url: null,
        webcal_url: null,
        include_details: null,
        access_count: 0,
        last_accessed_at: null,
        created_at: null,
      });
      setSuccess('Calendar feed has been revoked.');
      setTimeout(() => setSuccess(''), 5000);
    } catch (err) {
      setError(err.message);
    } finally {
      setRevoking(false);
    }
  }, []);

  // Toggle include_details (regenerates token)
  const handleToggleDetails = useCallback(async (newValue) => {
    setIncludeDetails(newValue);
    // If feed is already active, regenerate with new setting
    if (feedStatus?.is_active) {
      setError('');
      setGenerating(true);
      try {
        const data = await apiFetch('/api/v1/scheduler/feed/generate-token', {
          method: 'POST',
          body: JSON.stringify({ include_details: newValue }),
        });
        setFeedStatus({
          is_active: true,
          feed_url: data.feed_url,
          webcal_url: data.webcal_url,
          include_details: data.include_details,
          access_count: 0,
          last_accessed_at: null,
          created_at: data.created_at,
        });
        setSuccess(
          newValue
            ? 'Feed updated: appointment details are now visible.'
            : 'Feed updated: only busy/free status is now visible.'
        );
        setTimeout(() => setSuccess(''), 4000);
      } catch (err) {
        setError(err.message);
        setIncludeDetails(!newValue); // revert
      } finally {
        setGenerating(false);
      }
    }
  }, [feedStatus]);

  if (loading) {
    return (
      <div style={{ maxWidth: 640, margin: '0 auto', padding: 20 }}>
        <div style={{ textAlign: 'center', color: '#6b7280', padding: 40 }}>
          Loading feed settings...
        </div>
      </div>
    );
  }

  const isActive = feedStatus?.is_active;

  return (
    <div style={{ maxWidth: 640, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <h3 style={{ margin: '0 0 6px 0', fontSize: 18, fontWeight: 600, color: '#111827' }}>
          Calendar Feed Subscription
        </h3>
        <p style={{ margin: 0, fontSize: 14, color: '#6b7280', lineHeight: 1.5 }}>
          Subscribe to your Perennia AI appointment calendar from Apple Calendar, Google Calendar, Outlook, or any app that supports iCalendar feeds.
        </p>
      </div>

      {/* Messages */}
      {error && (
        <div style={{
          padding: '10px 14px', background: '#fef2f2', color: '#dc2626',
          borderRadius: 8, marginBottom: 12, fontSize: 13, display: 'flex',
          justifyContent: 'space-between', alignItems: 'center',
        }}>
          <span>{error}</span>
          <button
            onClick={() => setError('')}
            style={{ background: 'none', border: 'none', cursor: 'pointer', fontWeight: 600, color: '#dc2626' }}
            aria-label="Dismiss error"
          >
            X
          </button>
        </div>
      )}

      {success && (
        <div style={{
          padding: '10px 14px', background: '#dcfce7', color: '#166534',
          borderRadius: 8, marginBottom: 12, fontSize: 13,
        }}>
          {success}
        </div>
      )}

      {/* Feed status card */}
      <div style={{
        border: '1px solid #e5e7eb',
        borderRadius: 12,
        padding: 20,
        background: '#fff',
      }}>
        {/* Status indicator */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
          <span style={{
            display: 'inline-block',
            width: 10,
            height: 10,
            borderRadius: '50%',
            background: isActive ? '#10b981' : '#d1d5db',
          }} />
          <span style={{ fontSize: 15, fontWeight: 500, color: '#111827' }}>
            {isActive ? 'Feed Active' : 'Feed Not Configured'}
          </span>
          {isActive && feedStatus.access_count > 0 && (
            <span style={{
              fontSize: 12, color: '#6b7280', background: '#f3f4f6',
              padding: '2px 8px', borderRadius: 12,
            }}>
              {feedStatus.access_count} sync{feedStatus.access_count !== 1 ? 's' : ''}
              {feedStatus.last_accessed_at && (
                <> &middot; last {new Date(feedStatus.last_accessed_at).toLocaleDateString()}</>
              )}
            </span>
          )}
        </div>

        {/* Active feed: show URLs */}
        {isActive && (
          <>
            <FeedUrlDisplay
              label="Webcal URL (Apple Calendar, Outlook)"
              url={feedStatus.webcal_url}
            />
            <FeedUrlDisplay
              label="HTTPS URL (Google Calendar)"
              url={feedStatus.feed_url}
            />
          </>
        )}

        {/* Detail toggle */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '12px 0',
          borderTop: isActive ? '1px solid #f3f4f6' : 'none',
          marginTop: isActive ? 8 : 0,
        }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 500, color: '#111827' }}>
              Include appointment details
            </div>
            <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
              {includeDetails
                ? 'Titles, descriptions, client names, and locations are visible'
                : 'Only busy/free time blocks are shown (privacy mode)'}
            </div>
          </div>
          <label style={{ position: 'relative', display: 'inline-block', width: 48, height: 26, flexShrink: 0 }}>
            <input
              type="checkbox"
              checked={includeDetails}
              onChange={e => handleToggleDetails(e.target.checked)}
              disabled={generating}
              style={{ opacity: 0, width: 0, height: 0 }}
              aria-label="Include appointment details in feed"
            />
            <span
              style={{
                position: 'absolute', cursor: generating ? 'wait' : 'pointer',
                top: 0, left: 0, right: 0, bottom: 0,
                backgroundColor: includeDetails ? '#3b82f6' : '#d1d5db',
                borderRadius: 26, transition: 'background-color 0.2s',
              }}
            >
              <span
                style={{
                  position: 'absolute', height: 20, width: 20,
                  left: includeDetails ? 24 : 3, bottom: 3,
                  backgroundColor: '#fff', borderRadius: '50%',
                  transition: 'left 0.2s',
                }}
              />
            </span>
          </label>
        </div>

        {/* Action buttons */}
        <div style={{
          display: 'flex', gap: 10, marginTop: 16,
          paddingTop: 16, borderTop: '1px solid #f3f4f6',
        }}>
          {!isActive ? (
            <button
              onClick={handleGenerate}
              disabled={generating}
              style={{
                flex: 1, padding: '10px 20px', borderRadius: 8, border: 'none',
                background: '#3b82f6', color: '#fff',
                cursor: generating ? 'wait' : 'pointer',
                fontSize: 14, fontWeight: 500,
                opacity: generating ? 0.7 : 1,
              }}
            >
              {generating ? 'Generating...' : 'Generate Feed URL'}
            </button>
          ) : (
            <>
              <button
                onClick={handleGenerate}
                disabled={generating}
                style={{
                  flex: 1, padding: '10px 16px', borderRadius: 8,
                  border: '1px solid #d1d5db', background: '#fff',
                  color: '#374151', cursor: generating ? 'wait' : 'pointer',
                  fontSize: 14, fontWeight: 500,
                  opacity: generating ? 0.7 : 1,
                }}
                title="Generates a new URL and invalidates the current one"
              >
                {generating ? 'Regenerating...' : 'Regenerate URL'}
              </button>
              <button
                onClick={handleRevoke}
                disabled={revoking}
                style={{
                  padding: '10px 16px', borderRadius: 8,
                  border: '1px solid #fca5a5', background: '#fef2f2',
                  color: '#dc2626', cursor: revoking ? 'wait' : 'pointer',
                  fontSize: 14, fontWeight: 500,
                  opacity: revoking ? 0.7 : 1,
                }}
              >
                {revoking ? 'Revoking...' : 'Revoke Feed'}
              </button>
            </>
          )}
        </div>

        {/* Security note */}
        <div style={{
          marginTop: 12, padding: '10px 12px',
          background: '#fffbeb', borderRadius: 8, border: '1px solid #fef3c7',
          fontSize: 12, color: '#92400e', lineHeight: 1.5,
        }}>
          <strong>Security note:</strong> Anyone with this URL can view your calendar.
          Do not share it publicly. If compromised, click &quot;Regenerate URL&quot; to
          create a new one (the old URL will stop working immediately).
        </div>
      </div>

      {/* Setup instructions */}
      {isActive && (
        <SetupInstructions
          feedUrl={feedStatus.feed_url}
          webcalUrl={feedStatus.webcal_url}
        />
      )}
    </div>
  );
}
