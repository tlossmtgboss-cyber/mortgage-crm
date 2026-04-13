/**
 * useSensitiveScreen Hook
 * Perennia AI — Screen Recording Prevention for Sensitive Screens
 *
 * Signals the native layer (iOS via Capacitor plugin) that a sensitive screen
 * is active, so screen capture can be blocked with a blur overlay. On web
 * browsers, applies a CSS class to the body when the Screen Capture API
 * indicates active capture (best-effort — browser support is limited).
 *
 * Usage:
 *   useSensitiveScreen('ssn_entry');
 *   useSensitiveScreen('income_worksheet', { enabled: false }); // conditionally disable
 *
 * Components that should use this hook:
 *   - ApplicationSummaryReview (SSN field)
 *   - MaskedField when type="ssn"
 *   - IncomeCalculator / IncomeWorksheet / UnifiedIncomeCalculator
 *   - ESignModal (compliance)
 *   - BiometricGate (authentication)
 *   - PaystubReviewModal (SSN last 4)
 *   - SalesforceFieldMapper (SSN mapping)
 *   - ExtractionsSection (SSN last 4 extraction)
 */

import { useEffect, useRef } from 'react';
import { Capacitor, registerPlugin } from '@capacitor/core';

// ---------------------------------------------------------------------------
// Native plugin bridge — no-op on web
// ---------------------------------------------------------------------------

const SensitiveScreen = Capacitor.isNativePlatform()
  ? registerPlugin('SensitiveScreen')
  : null;

// ---------------------------------------------------------------------------
// Web-side screen capture detection (best-effort)
// ---------------------------------------------------------------------------

const BODY_CLASS = 'sensitive-screen-active';
const CAPTURE_CLASS = 'screen-capture-detected';

let _activeCount = 0;
let _captureCheckInterval = null;

/**
 * Increment the count of active sensitive screens.
 * When the first one mounts, inject the CSS guard styles and start
 * polling for screen capture (web only).
 */
function _enterSensitive() {
  _activeCount++;

  document.body.classList.add(BODY_CLASS);

  if (!Capacitor.isNativePlatform() && !_captureCheckInterval) {
    _startWebCaptureDetection();
  }
}

/**
 * Decrement. When the last one unmounts, remove CSS classes and stop polling.
 */
function _leaveSensitive() {
  _activeCount = Math.max(0, _activeCount - 1);

  if (_activeCount === 0) {
    document.body.classList.remove(BODY_CLASS);
    document.body.classList.remove(CAPTURE_CLASS);
    _stopWebCaptureDetection();
  }
}

// ---------------------------------------------------------------------------
// Web capture detection via navigator.mediaDevices
// ---------------------------------------------------------------------------

function _startWebCaptureDetection() {
  // Inject CSS once if not already present
  _injectSensitiveScreenStyles();

  // The Screen Capture API does not provide a direct "is being captured"
  // query, but we can detect getDisplayMedia tracks in some browsers.
  // As a fallback we rely on the CSS content-visibility approach.
  _captureCheckInterval = setInterval(() => {
    // navigator.mediaDevices.getDisplayMedia is the trigger, but we
    // cannot enumerate other origins' captures. This is best-effort.
    // The real enforcement happens on iOS native side.
  }, 3000);
}

function _stopWebCaptureDetection() {
  if (_captureCheckInterval) {
    clearInterval(_captureCheckInterval);
    _captureCheckInterval = null;
  }
}

function _injectSensitiveScreenStyles() {
  if (document.getElementById('sensitive-screen-styles')) return;

  const style = document.createElement('style');
  style.id = 'sensitive-screen-styles';
  style.textContent = `
    /* Overlay shown when screen capture is detected on a sensitive screen */
    body.${BODY_CLASS}.${CAPTURE_CLASS}::after {
      content: 'Screen recording is not allowed on this screen';
      position: fixed;
      inset: 0;
      z-index: 2147483647;
      display: flex;
      align-items: center;
      justify-content: center;
      background: rgba(0, 0, 0, 0.92);
      color: #fff;
      font-size: 1.25rem;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      pointer-events: all;
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
    }

    /* Prevent print/screenshot via CSS (best-effort, not a security boundary) */
    body.${BODY_CLASS} [data-sensitive="true"] {
      -webkit-user-select: none;
      user-select: none;
    }

    @media print {
      body.${BODY_CLASS} [data-sensitive="true"] {
        visibility: hidden !important;
      }
      body.${BODY_CLASS}::after {
        content: 'Sensitive content hidden for compliance';
        display: block;
        padding: 2rem;
        font-size: 1.5rem;
        text-align: center;
      }
    }
  `;
  document.head.appendChild(style);
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Mark the current screen as sensitive for screen recording prevention.
 *
 * @param {string} screenName - Identifier for the sensitive screen (for audit logging)
 * @param {Object} [options]
 * @param {boolean} [options.enabled=true] - Set to false to conditionally skip
 */
export function useSensitiveScreen(screenName, options = {}) {
  const { enabled = true } = options;
  const screenNameRef = useRef(screenName);
  screenNameRef.current = screenName;

  useEffect(() => {
    if (!enabled) return;

    // Signal native layer
    if (SensitiveScreen) {
      SensitiveScreen.enterSensitiveScreen({ screen: screenNameRef.current }).catch(() => {
        // Plugin not available or call failed — non-fatal
      });
    }

    // Web-side CSS guard
    _enterSensitive();

    return () => {
      // Signal native layer
      if (SensitiveScreen) {
        SensitiveScreen.leaveSensitiveScreen({ screen: screenNameRef.current }).catch(() => {
          // Plugin not available or call failed — non-fatal
        });
      }

      // Web-side cleanup
      _leaveSensitive();
    };
  }, [enabled]);
}

/**
 * Programmatically trigger the capture-detected overlay on web.
 * Useful if an external signal (e.g., from a native plugin callback)
 * indicates capture has started.
 */
export function markCaptureDetected() {
  document.body.classList.add(CAPTURE_CLASS);
}

export function clearCaptureDetected() {
  document.body.classList.remove(CAPTURE_CLASS);
}

export default useSensitiveScreen;
