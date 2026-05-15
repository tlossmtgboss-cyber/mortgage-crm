/**
 * UpdateRequiredModal
 *
 * Three presentation modes driven by props:
 *
 * 1. **Force update** (forceUpdate=true)
 *    Full-screen, non-dismissible modal. The user MUST update before
 *    they can use the app.
 *
 * 2. **Optional update** (updateAvailable=true, forceUpdate=false)
 *    Dismissible top banner offering the new version with a "Later" option.
 *
 * 3. **Maintenance mode** (maintenanceMode=true)
 *    Full-screen maintenance screen. Non-dismissible.
 *
 * Props:
 *   forceUpdate      - boolean
 *   updateAvailable  - boolean
 *   maintenanceMode  - boolean
 *   maintenanceMessage - string
 *   updateUrl        - string (App Store / Play Store deep link)
 *   recommendedVersion - string (e.g. "1.0.3")
 *   changelog        - string
 *   onDismiss        - called when the optional banner is dismissed
 */
import React, { useCallback } from 'react';
import './UpdateRequiredModal.css';

// ---------------------------------------------------------------------------
// Force-update full-screen overlay
// ---------------------------------------------------------------------------
function ForceUpdateScreen({ updateUrl, changelog }) {
  const handleUpdate = useCallback(() => {
    if (updateUrl) {
      window.open(updateUrl, '_system');
    }
  }, [updateUrl]);

  return (
    <div className="update-modal-overlay" role="dialog" aria-modal="true" aria-label="Update required">
      <div className="update-modal-card">
        {/* Logo / icon */}
        <div className="update-modal-icon">
          <svg width="64" height="64" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <rect width="64" height="64" rx="14" fill="#8A6D30" />
            <path d="M32 16L32 40M32 40L22 30M32 40L42 30" stroke="white" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M20 46H44" stroke="white" strokeWidth="3.5" strokeLinecap="round" />
          </svg>
        </div>

        <h1 className="update-modal-title">Update Required</h1>

        <p className="update-modal-body">
          A new version of Perennia AI is available with important updates.
          Please update to continue using the app.
        </p>

        {changelog && (
          <p className="update-modal-changelog">{changelog}</p>
        )}

        <button
          className="update-modal-button update-modal-button--primary"
          onClick={handleUpdate}
          type="button"
        >
          Update Now
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Maintenance full-screen overlay
// ---------------------------------------------------------------------------
function MaintenanceScreen({ maintenanceMessage }) {
  return (
    <div className="update-modal-overlay update-modal-overlay--maintenance" role="alert" aria-label="Maintenance in progress">
      <div className="update-modal-card">
        <div className="update-modal-icon">
          <svg width="64" height="64" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <rect width="64" height="64" rx="14" fill="#D97706" />
            <path d="M32 20V36M32 42V44" stroke="white" strokeWidth="3.5" strokeLinecap="round" />
            <circle cx="32" cy="32" r="18" stroke="white" strokeWidth="3" fill="none" />
          </svg>
        </div>

        <h1 className="update-modal-title">Scheduled Maintenance</h1>

        <p className="update-modal-body">
          {maintenanceMessage || "We're performing scheduled maintenance. Please try again shortly."}
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Optional update banner (dismissible)
// ---------------------------------------------------------------------------
function UpdateBanner({ recommendedVersion, updateUrl, onDismiss }) {
  const handleUpdate = useCallback(() => {
    if (updateUrl) {
      window.open(updateUrl, '_system');
    }
  }, [updateUrl]);

  return (
    <div className="update-banner" role="status" aria-label="Update available">
      <span className="update-banner-text">
        Update available: v{recommendedVersion}
      </span>
      <div className="update-banner-actions">
        <button
          className="update-banner-btn update-banner-btn--update"
          onClick={handleUpdate}
          type="button"
        >
          Update
        </button>
        <button
          className="update-banner-btn update-banner-btn--later"
          onClick={onDismiss}
          type="button"
          aria-label="Dismiss update banner"
        >
          Later
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Composite export
// ---------------------------------------------------------------------------

export default function UpdateRequiredModal({
  forceUpdate = false,
  updateAvailable = false,
  maintenanceMode = false,
  maintenanceMessage = '',
  updateUrl = '',
  recommendedVersion = '',
  changelog = '',
  onDismiss = () => {},
}) {
  // Priority order: maintenance > force update > optional banner.
  if (maintenanceMode) {
    return <MaintenanceScreen maintenanceMessage={maintenanceMessage} />;
  }

  if (forceUpdate) {
    return <ForceUpdateScreen updateUrl={updateUrl} changelog={changelog} />;
  }

  if (updateAvailable) {
    return (
      <UpdateBanner
        recommendedVersion={recommendedVersion}
        updateUrl={updateUrl}
        onDismiss={onDismiss}
      />
    );
  }

  return null;
}
