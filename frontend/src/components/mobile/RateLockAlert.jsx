/**
 * RateLockAlert - Standalone rate lock alert banner (swipeable carousel)
 *
 * Displays a swipeable carousel of rate lock expiration warnings.
 * Uses the dedicated /api/v1/rate-lock-intelligence/alerts endpoint.
 *
 * IMPORTANT: Do NOT use this component on MobileHomeDashboard.
 * MobileHomeDashboard already displays rate lock alerts via
 * /api/v1/pipeline/alerts to avoid duplicate alert systems.
 *
 * This component is intended for desktop pipeline views or other
 * pages that do not already surface pipeline alerts.
 *
 * Features:
 *  - Red banner for expired locks, amber for < 24h, yellow for 24-48h
 *  - Swipe carousel when multiple alerts exist
 *  - Auto-refreshes every 5 minutes
 *  - Tap navigates to the loan detail page
 *  - Individual dismiss per alert (session-only, reappears on reload)
 *
 * Usage:
 *   <RateLockAlert />
 *
 * Place inside MobilePipelineView or desktop views only.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { API_BASE_URL } from '../../services/api';
import './RateLockAlert.css';

const POLL_INTERVAL_MS = 5 * 60 * 1000; // 5 minutes
const ALERTS_ENDPOINT = `${API_BASE_URL}/api/v1/rate-lock-intelligence/alerts`;

// ============================================================================
// Icons
// ============================================================================

function LockIcon({ color = 'currentColor' }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  );
}

function ClockIcon({ color = 'currentColor' }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  );
}

function AlertIcon({ color = 'currentColor' }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  );
}

function CloseIcon({ color = 'currentColor' }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

// ============================================================================
// Helpers
// ============================================================================

function getAuthHeaders() {
  const token = localStorage.getItem('token');
  return {
    Authorization: token ? `Bearer ${token}` : '',
    'Content-Type': 'application/json',
  };
}

function formatHours(hours) {
  if (hours == null) return '';
  const absHours = Math.abs(hours);
  if (absHours < 1) {
    const mins = Math.round(absHours * 60);
    return `${mins}m`;
  }
  if (absHours >= 24) {
    const days = Math.floor(absHours / 24);
    const remainingHours = Math.round(absHours % 24);
    return remainingHours > 0 ? `${days}d ${remainingHours}h` : `${days}d`;
  }
  return `${Math.round(absHours)}h`;
}

function urgencyIcon(urgency) {
  switch (urgency) {
    case 'expired':
      return <AlertIcon color="#fff" />;
    case 'critical':
      return <LockIcon color="#fff" />;
    case 'warning':
      return <ClockIcon color="#1a1a2e" />;
    default:
      return <LockIcon color="#fff" />;
  }
}

function urgencyLabel(urgency) {
  switch (urgency) {
    case 'expired':
      return 'Lock Expired';
    case 'critical':
      return 'Expiring Soon';
    case 'warning':
      return 'Lock Warning';
    default:
      return 'Rate Lock';
  }
}

function formatAlertMessage(alert) {
  const borrower = alert.borrower_name || 'Unknown';
  if (alert.urgency === 'expired') {
    return `${borrower} -- expired ${formatHours(alert.hours_expired || Math.abs(alert.hours_remaining))} ago`;
  }
  return `${borrower} -- ${formatHours(alert.hours_remaining)} remaining`;
}

function formatSubtext(alert) {
  const parts = [];
  if (alert.loan_number) parts.push(`#${alert.loan_number}`);
  if (alert.rate) parts.push(`${alert.rate}%`);
  if (alert.amount) {
    parts.push(`$${(alert.amount / 1000).toFixed(0)}K`);
  }
  return parts.join(' | ');
}

// ============================================================================
// Component
// ============================================================================

export default function RateLockAlert() {
  const navigate = useNavigate();

  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [dismissed, setDismissed] = useState(new Set());

  // Swipe state
  const touchStartX = useRef(null);
  const touchDeltaX = useRef(0);
  const carouselRef = useRef(null);

  // --------------------------------------------------
  // Fetch alerts
  // --------------------------------------------------
  const fetchAlerts = useCallback(async () => {
    try {
      const res = await fetch(ALERTS_ENDPOINT, { headers: getAuthHeaders() });
      if (!res.ok) {
        // Silently ignore auth failures -- user may not be logged in yet
        if (res.status === 401 || res.status === 403) {
          setAlerts([]);
          return;
        }
        throw new Error(`HTTP ${res.status}`);
      }
      const data = await res.json();

      // Flatten expired + critical + warning into a single ordered list
      const all = [
        ...(data.expired || []),
        ...(data.critical || []),
        ...(data.warning || []),
      ];
      setAlerts(all);
      setError(null);
    } catch (err) {
      // Don't show error on first load -- endpoint may not exist yet
      if (!loading) {
        setError(err.message);
      }
      setAlerts([]);
    } finally {
      setLoading(false);
    }
  }, [loading]);

  // Initial fetch + polling
  useEffect(() => {
    fetchAlerts();
    const interval = setInterval(fetchAlerts, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [fetchAlerts]);

  // --------------------------------------------------
  // Visible (non-dismissed) alerts
  // --------------------------------------------------
  const visibleAlerts = alerts.filter((a) => !dismissed.has(a.loan_id));

  // Reset index if it goes out of bounds
  useEffect(() => {
    if (currentIndex >= visibleAlerts.length) {
      setCurrentIndex(Math.max(0, visibleAlerts.length - 1));
    }
  }, [visibleAlerts.length, currentIndex]);

  // --------------------------------------------------
  // Swipe handlers
  // --------------------------------------------------
  const handleTouchStart = useCallback((e) => {
    touchStartX.current = e.touches[0].clientX;
    touchDeltaX.current = 0;
  }, []);

  const handleTouchMove = useCallback((e) => {
    if (touchStartX.current == null) return;
    touchDeltaX.current = e.touches[0].clientX - touchStartX.current;
  }, []);

  const handleTouchEnd = useCallback(() => {
    if (touchStartX.current == null) return;
    const threshold = 50;
    if (touchDeltaX.current < -threshold && currentIndex < visibleAlerts.length - 1) {
      setCurrentIndex((i) => i + 1);
    } else if (touchDeltaX.current > threshold && currentIndex > 0) {
      setCurrentIndex((i) => i - 1);
    }
    touchStartX.current = null;
    touchDeltaX.current = 0;
  }, [currentIndex, visibleAlerts.length]);

  // --------------------------------------------------
  // Actions
  // --------------------------------------------------
  const handleDismiss = useCallback((e, loanId) => {
    e.stopPropagation();
    setDismissed((prev) => new Set([...prev, loanId]));
  }, []);

  const handleTap = useCallback(
    (alert) => {
      if (alert.loan_id) {
        navigate(`/loans/${alert.loan_id}`);
      }
    },
    [navigate],
  );

  // --------------------------------------------------
  // Render
  // --------------------------------------------------

  // Nothing to show
  if (!loading && visibleAlerts.length === 0) {
    return null;
  }

  // Loading state (first load only)
  if (loading) {
    return (
      <div className="rate-lock-alert-container">
        <div className="rate-lock-alert-loading">
          <div className="rate-lock-alert-loading-spinner" />
          Checking rate locks...
        </div>
      </div>
    );
  }

  return (
    <div className="rate-lock-alert-container">
      {/* Badge showing total count when > 1 */}
      {visibleAlerts.length > 1 && (
        <div className="rate-lock-alert-badge">{visibleAlerts.length}</div>
      )}

      {/* Carousel */}
      <div
        ref={carouselRef}
        className="rate-lock-alert-carousel"
        style={{ transform: `translateX(-${currentIndex * 100}%)` }}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        {visibleAlerts.map((alert) => (
          <div key={alert.loan_id} className="rate-lock-alert-slide">
            <div
              className={`rate-lock-alert-banner rate-lock-alert-banner--${alert.urgency}`}
              onClick={() => handleTap(alert)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && handleTap(alert)}
            >
              {/* Icon */}
              <div className="rate-lock-alert-icon">
                {urgencyIcon(alert.urgency)}
              </div>

              {/* Content */}
              <div className="rate-lock-alert-content">
                <div className="rate-lock-alert-label">
                  {urgencyLabel(alert.urgency)}
                </div>
                <div className="rate-lock-alert-message">
                  {formatAlertMessage(alert)}
                </div>
                <div className="rate-lock-alert-sub">
                  {formatSubtext(alert)}
                </div>
              </div>

              {/* Dismiss */}
              <button
                className="rate-lock-alert-dismiss"
                onClick={(e) => handleDismiss(e, alert.loan_id)}
                aria-label="Dismiss alert"
              >
                <CloseIcon
                  color={alert.urgency === 'warning' ? '#1a1a2e' : '#fff'}
                />
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Pagination dots */}
      {visibleAlerts.length > 1 && (
        <div className="rate-lock-alert-dots">
          {visibleAlerts.map((_, idx) => (
            <div
              key={idx}
              className={`rate-lock-alert-dot ${
                idx === currentIndex ? 'rate-lock-alert-dot--active' : ''
              }`}
            />
          ))}
        </div>
      )}
    </div>
  );
}
