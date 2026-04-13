/**
 * PushPermissionRecovery
 *
 * Non-intrusive recovery card shown when push notifications are denied at the OS level.
 * Explains why notifications matter for loan officers and offers a one-tap path to
 * iOS Settings to re-enable them.
 *
 * Behavior:
 *  - Only renders on native mobile (Capacitor)
 *  - Checks permission status on mount and when app resumes from background
 *  - If denied, shows a card with "Enable Notifications" -> opens iOS Settings
 *  - "Not Now" dismisses the card for 7 days (persisted in localStorage)
 *  - If permissions are granted (or get granted after returning from Settings), hides itself
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Capacitor } from '@capacitor/core';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DISMISS_KEY = 'push_recovery_dismissed_at';
const DISMISS_DURATION_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isDismissed() {
  try {
    const ts = localStorage.getItem(DISMISS_KEY);
    if (!ts) return false;
    return Date.now() - Number(ts) < DISMISS_DURATION_MS;
  } catch {
    return false;
  }
}

function setDismissed() {
  try {
    localStorage.setItem(DISMISS_KEY, String(Date.now()));
  } catch {
    // localStorage unavailable — ignore
  }
}

/**
 * Check whether push notifications are denied.
 * Uses Capacitor PushNotifications plugin on native, falls back to
 * the web Notification API on browsers (though the component only
 * renders on native).
 */
async function checkPermissionDenied() {
  // Native path — dynamic import to avoid bundler errors on web
  if (Capacitor.isNativePlatform()) {
    try {
      const { PushNotifications } = await import('@capacitor/push-notifications');
      const result = await PushNotifications.checkPermissions();
      // "denied" means the user explicitly denied; "prompt" means never asked
      return result.receive === 'denied';
    } catch (e) {
      console.warn('[PushRecovery] Could not check native permissions:', e);
      return false;
    }
  }

  // Web fallback (not expected to render, but safe)
  if (typeof Notification !== 'undefined') {
    return Notification.permission === 'denied';
  }

  return false;
}

/**
 * Open the app's iOS Settings page so the user can toggle notifications.
 */
async function openAppSettings() {
  try {
    const { App } = await import('@capacitor/app');
    // "app-settings:" is the iOS deep-link to the current app's Settings pane.
    // On Android, Capacitor handles this via App.openUrl as well.
    await App.openUrl({ url: 'app-settings:' });
  } catch (e) {
    console.warn('[PushRecovery] Could not open app settings:', e);
  }
}

// ---------------------------------------------------------------------------
// Icons (inline SVG)
// ---------------------------------------------------------------------------

function BellOffIcon() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
      <path d="M18.63 13A17.89 17.89 0 0 1 18 8" />
      <path d="M6.26 6.26A5.86 5.86 0 0 0 6 8c0 7-3 9-3 9h14" />
      <path d="M18 8a6 6 0 0 0-9.33-5" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
    >
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Styles (inline to keep component self-contained, no CSS file needed)
// ---------------------------------------------------------------------------

const styles = {
  card: {
    margin: '12px 16px',
    padding: '14px 16px',
    background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)',
    borderRadius: '14px',
    border: '1px solid rgba(255, 183, 77, 0.25)',
    display: 'flex',
    alignItems: 'flex-start',
    gap: '12px',
    position: 'relative',
    boxShadow: '0 2px 12px rgba(0, 0, 0, 0.15)',
  },
  iconWrap: {
    flexShrink: 0,
    width: '40px',
    height: '40px',
    borderRadius: '10px',
    background: 'rgba(255, 183, 77, 0.12)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#FFB74D',
  },
  content: {
    flex: 1,
    minWidth: 0,
  },
  title: {
    margin: 0,
    fontSize: '14px',
    fontWeight: 600,
    color: '#ffffff',
    lineHeight: '1.3',
  },
  description: {
    margin: '4px 0 0',
    fontSize: '12px',
    color: 'rgba(255, 255, 255, 0.6)',
    lineHeight: '1.4',
  },
  actions: {
    display: 'flex',
    gap: '8px',
    marginTop: '10px',
  },
  enableBtn: {
    padding: '7px 14px',
    fontSize: '12px',
    fontWeight: 600,
    color: '#1a1a2e',
    background: '#FFB74D',
    border: 'none',
    borderRadius: '8px',
    cursor: 'pointer',
    WebkitTapHighlightColor: 'transparent',
  },
  dismissBtn: {
    padding: '7px 14px',
    fontSize: '12px',
    fontWeight: 500,
    color: 'rgba(255, 255, 255, 0.5)',
    background: 'transparent',
    border: '1px solid rgba(255, 255, 255, 0.15)',
    borderRadius: '8px',
    cursor: 'pointer',
    WebkitTapHighlightColor: 'transparent',
  },
  closeBtn: {
    position: 'absolute',
    top: '8px',
    right: '8px',
    background: 'none',
    border: 'none',
    padding: '4px',
    color: 'rgba(255, 255, 255, 0.35)',
    cursor: 'pointer',
    WebkitTapHighlightColor: 'transparent',
  },
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function PushPermissionRecovery() {
  const [visible, setVisible] = useState(false);
  const mountedRef = useRef(true);

  // Check permission status
  const checkAndShow = useCallback(async () => {
    if (!Capacitor.isNativePlatform()) return;
    if (isDismissed()) return;

    const denied = await checkPermissionDenied();
    if (mountedRef.current) {
      setVisible(denied);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    checkAndShow();

    // Re-check when the app resumes (user may have toggled in Settings)
    let appStateListener = null;

    (async () => {
      if (!Capacitor.isNativePlatform()) return;
      try {
        const { App } = await import('@capacitor/app');
        appStateListener = await App.addListener('appStateChange', ({ isActive }) => {
          if (isActive) {
            checkAndShow();
          }
        });
      } catch (e) {
        // Plugin not available — no-op
      }
    })();

    return () => {
      mountedRef.current = false;
      if (appStateListener && typeof appStateListener.remove === 'function') {
        appStateListener.remove();
      }
    };
  }, [checkAndShow]);

  // ── Handlers ────────────────────────────────────────────────────────────

  const handleEnable = () => {
    openAppSettings();
  };

  const handleDismiss = () => {
    setDismissed();
    setVisible(false);
  };

  // ── Render ──────────────────────────────────────────────────────────────

  if (!visible) return null;

  return (
    <div style={styles.card} role="alert" aria-label="Push notifications disabled">
      <div style={styles.iconWrap}>
        <BellOffIcon />
      </div>

      <div style={styles.content}>
        <p style={styles.title}>Notifications are off</p>
        <p style={styles.description}>
          Get notified about new leads, SLA warnings, and document submissions so you never miss a deal.
        </p>

        <div style={styles.actions}>
          <button style={styles.enableBtn} onClick={handleEnable} type="button">
            Enable Notifications
          </button>
          <button style={styles.dismissBtn} onClick={handleDismiss} type="button">
            Not Now
          </button>
        </div>
      </div>

      <button
        style={styles.closeBtn}
        onClick={handleDismiss}
        type="button"
        aria-label="Dismiss"
      >
        <CloseIcon />
      </button>
    </div>
  );
}
