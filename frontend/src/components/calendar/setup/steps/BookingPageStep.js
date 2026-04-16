/**
 * BookingPageStep.js — Step 4 of Calendar Guided Setup
 *
 * Booking page branding setup with a live preview panel.
 * Left side: profile, branding, photo, booking link settings.
 * Right side: real-time mockup of the public booking page.
 *
 * Props:
 *   onStepComplete(data) - called with saved branding data object on successful save
 *   onDirty(isDirty)     - called when the user modifies any field
 *   initialData          - optional overrides { lo_name, tagline, primary_color }
 *
 * Saves via:
 *   PUT  /api/v1/calendar-settings/booking-page  (landing_page_settings JSON)
 *   POST /api/v1/scheduler/booking-links          (booking link creation)
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import api from '../../../../services/api';
import { calendarSettingsAPI } from '../../../../services/api';
import { toast } from '../../../../utils/toast';
import './BookingPageStep.css';
import { getUserData } from '../../../../utils/tokenStore';

// ============================================================================
// Constants
// ============================================================================

const PRESET_COLORS = [
  { hex: '#218D8D', name: 'Perennia Teal' },
  { hex: '#2563eb', name: 'Blue' },
  { hex: '#7c3aed', name: 'Purple' },
  { hex: '#dc2626', name: 'Red' },
  { hex: '#ea580c', name: 'Orange' },
  { hex: '#16a34a', name: 'Green' },
  { hex: '#0891b2', name: 'Cyan' },
  { hex: '#1e293b', name: 'Slate' },
];

const SLUG_REGEX = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

const APP_BASE = process.env.REACT_APP_BASE_URL || 'https://app.perenniaai.com';

// Generate a QR-code-like grid pattern (deterministic from slug)
function generateQrPattern(slug) {
  const cells = [];
  const seed = (slug || 'demo').split('').reduce((acc, c) => acc + c.charCodeAt(0), 0);
  for (let i = 0; i < 64; i++) {
    // Corner finder patterns (top-left, top-right, bottom-left)
    const row = Math.floor(i / 8);
    const col = i % 8;
    const isFinderTL = row < 3 && col < 3;
    const isFinderTR = row < 3 && col > 4;
    const isFinderBL = row > 4 && col < 3;

    if (isFinderTL || isFinderTR || isFinderBL) {
      // Finder pattern: border and center are dark
      const isEdge = row === 0 || row === 2 || col === 0 || col === 2
        || col === 5 || col === 7;
      const isCenter = (isFinderTL && row === 1 && col === 1)
        || (isFinderTR && row === 1 && col === 6)
        || (isFinderBL && row === 6 && col === 1);
      cells.push(isEdge || isCenter);
    } else {
      // Pseudo-random data based on seed
      cells.push(((seed * (i + 7) + i * 13) % 5) < 3);
    }
  }
  return cells;
}

// Check if a hex color is "light" (needs dark checkmark)
function isLightColor(hex) {
  if (!hex || hex.length < 7) return false;
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.6;
}

// Generate slug from a name
function nameToSlug(name) {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, '')
    .replace(/\s+/g, '-')
    .substring(0, 60);
}

// ============================================================================
// Component
// ============================================================================

const BookingPageStep = ({ onStepComplete, onDirty, initialData }) => {
  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  // Profile
  const [loName, setLoName] = useState('');
  const [loTitle, setLoTitle] = useState('');
  const [tagline, setTagline] = useState('');
  const [welcomeMessage, setWelcomeMessage] = useState('Schedule a time to meet with us');

  // Branding
  const [primaryColor, setPrimaryColor] = useState('#218D8D');
  const [showPoweredBy, setShowPoweredBy] = useState(true);

  // Photo
  const [photoUrl, setPhotoUrl] = useState('');

  // Booking link
  const [slug, setSlug] = useState('');
  const [editingSlug, setEditingSlug] = useState(false);
  const [slugDraft, setSlugDraft] = useState('');
  const [slugError, setSlugError] = useState('');
  const [copied, setCopied] = useState(false);
  const [bookingLinks, setBookingLinks] = useState([]);

  // Appointment types (for preview)
  const [appointmentTypes, setAppointmentTypes] = useState([]);

  // Loading / saving
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // ---------------------------------------------------------------------------
  // Load data on mount
  // ---------------------------------------------------------------------------

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      // Load booking page settings, booking links, appointment types, and user info in parallel
      const [bpRes, linksRes, typesRes] = await Promise.all([
        calendarSettingsAPI.getBookingPage().catch(() => null),
        api.get('/api/v1/scheduler/booking-links').catch(() => null),
        api.get('/api/v1/calendar-settings/appointment-types').catch(() => null),
      ]);

      // Populate from saved branding settings
      if (bpRes?.data) {
        const branding = bpRes.data.branding || {};
        if (branding.tagline) setTagline(branding.tagline);
        if (branding.welcome_message) setWelcomeMessage(branding.welcome_message);
        if (branding.primary_color) setPrimaryColor(branding.primary_color);
        if (branding.logo_url) setPhotoUrl(branding.logo_url);
        if (branding.show_branding !== undefined) setShowPoweredBy(branding.show_branding);
        if (branding.lo_name) setLoName(branding.lo_name);
        if (branding.lo_title) setLoTitle(branding.lo_title);
      }

      // Booking links
      if (linksRes?.data) {
        const links = linksRes.data.booking_links || linksRes.data || [];
        setBookingLinks(links);
        // If there is an existing link, use its slug
        if (links.length > 0 && links[0].slug) {
          setSlug(links[0].slug);
        }
      }

      // Appointment types for the preview
      if (typesRes?.data) {
        const types = typesRes.data.appointment_types || typesRes.data || [];
        setAppointmentTypes(types);
      }

      // Populate LO name from localStorage user if not set from API
      try {
        const userStr = getUserData();
        if (userStr) {
          const user = JSON.parse(userStr);
          const fullName = [user.first_name, user.last_name].filter(Boolean).join(' ');
          setLoName(prev => prev || fullName || '');
          // Auto-generate slug from name if none exists
          if (!slug && fullName) {
            setSlug(prev => prev || nameToSlug(fullName));
          }
        }
      } catch {
        // Ignore localStorage errors
      }

      // Apply initialData overrides if provided by parent
      if (initialData) {
        if (initialData.lo_name) setLoName(initialData.lo_name);
        if (initialData.tagline) setTagline(initialData.tagline);
        if (initialData.primary_color) setPrimaryColor(initialData.primary_color);
      }
    } catch (err) {
      toast.error('Failed to load booking page settings');
    } finally {
      setLoading(false);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    loadData();
  }, [loadData]);

  // ---------------------------------------------------------------------------
  // Dirty tracking
  // ---------------------------------------------------------------------------

  const markDirty = useCallback(() => {
    if (onDirty) onDirty(true);
  }, [onDirty]);

  // ---------------------------------------------------------------------------
  // Save
  // ---------------------------------------------------------------------------

  const handleSave = async () => {
    setSaving(true);
    try {
      // Save branding settings
      const brandingPayload = {
        lo_name: loName,
        lo_title: loTitle,
        tagline,
        welcome_message: welcomeMessage,
        primary_color: primaryColor,
        logo_url: photoUrl || null,
        show_branding: showPoweredBy,
      };
      await calendarSettingsAPI.updateBookingPage(brandingPayload);

      // Create booking link if slug is set and no links exist yet
      if (slug && bookingLinks.length === 0) {
        try {
          await api.post('/api/v1/scheduler/booking-links', {
            link_name: loName || 'My Booking Page',
            slug,
            description: tagline || '',
            is_public: true,
          });
          // Refresh links
          const linksRes = await api.get('/api/v1/scheduler/booking-links').catch(() => null);
          if (linksRes?.data) {
            setBookingLinks(linksRes.data.booking_links || linksRes.data || []);
          }
        } catch (err) {
          // If link creation fails (e.g., slug taken), warn but don't block save
          const msg = err.response?.data?.detail || err.message || 'Could not create booking link';
          toast.error(`Booking link: ${msg}`);
        }
      }

      toast.success('Booking page settings saved');
      if (onDirty) onDirty(false);
      if (onStepComplete) {
        onStepComplete({
          lo_name: loName,
          lo_title: loTitle,
          tagline,
          welcome_message: welcomeMessage,
          primary_color: primaryColor,
          logo_url: photoUrl || null,
          show_branding: showPoweredBy,
          slug,
        });
      }
    } catch (err) {
      toast.error('Failed to save booking page settings');
    } finally {
      setSaving(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Slug editing
  // ---------------------------------------------------------------------------

  const startEditSlug = () => {
    setSlugDraft(slug);
    setSlugError('');
    setEditingSlug(true);
  };

  const cancelEditSlug = () => {
    setEditingSlug(false);
    setSlugError('');
  };

  const saveSlug = () => {
    const clean = slugDraft.toLowerCase().trim();
    if (!clean) {
      setSlugError('Slug cannot be empty');
      return;
    }
    if (!SLUG_REGEX.test(clean)) {
      setSlugError('Only lowercase letters, numbers, and hyphens allowed');
      return;
    }
    setSlug(clean);
    setEditingSlug(false);
    setSlugError('');
    markDirty();
  };

  // ---------------------------------------------------------------------------
  // Copy link
  // ---------------------------------------------------------------------------

  const bookingUrl = `${APP_BASE}/book/${slug}`;

  const handleCopyLink = async () => {
    try {
      await navigator.clipboard.writeText(bookingUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for non-HTTPS contexts
      const textarea = document.createElement('textarea');
      textarea.value = bookingUrl;
      textarea.style.position = 'fixed';
      textarea.style.left = '-9999px';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  // ---------------------------------------------------------------------------
  // Preview data
  // ---------------------------------------------------------------------------

  const qrCells = useMemo(() => generateQrPattern(slug), [slug]);

  // Mock date row for the preview
  const mockDates = useMemo(() => {
    const today = new Date();
    const dates = [];
    const dayNames = ['SUN', 'MON', 'TUE', 'WED', 'THU'];
    for (let i = 0; i < 5; i++) {
      const d = new Date(today);
      d.setDate(today.getDate() + i);
      dates.push({
        day: dayNames[d.getDay()] || dayNames[i],
        num: d.getDate(),
        active: i === 0,
      });
    }
    return dates;
  }, []);

  // Determine sample appointment types for preview
  const previewTypes = appointmentTypes.length > 0
    ? appointmentTypes.slice(0, 3)
    : [
      { type_name: 'Mortgage Consultation', default_duration_minutes: 30 },
      { type_name: 'Rate Review', default_duration_minutes: 15 },
    ];

  // ---------------------------------------------------------------------------
  // Color change handler
  // ---------------------------------------------------------------------------

  const handleColorChange = (hex) => {
    setPrimaryColor(hex);
    markDirty();
  };

  // ---------------------------------------------------------------------------
  // Render: Loading
  // ---------------------------------------------------------------------------

  if (loading) {
    return (
      <div className="bps-container" style={{ justifyContent: 'center', minHeight: 300 }}>
        <div style={{ textAlign: 'center', color: '#64748b', gridColumn: '1 / -1' }}>
          <div className="spinner" style={{ margin: '0 auto 12px', width: 32, height: 32, border: '3px solid #e2e8f0', borderTopColor: '#218D8D', borderRadius: '50%', animation: 'cal-spin 0.8s linear infinite' }} />
          <p>Loading booking page settings...</p>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Main
  // ---------------------------------------------------------------------------

  return (
    <div className="bps-container">
      {/* ================================================================
          LEFT: Settings Panel
          ================================================================ */}
      <div className="bps-settings">

        {/* — Profile — */}
        <div className="bps-section">
          <h3 className="bps-section-title">
            <i className="fas fa-user" aria-hidden="true"></i>
            Profile
          </h3>

          <div className="bps-field-row">
            <div className="bps-field">
              <label htmlFor="bps-lo-name">Your Name</label>
              <input
                id="bps-lo-name"
                type="text"
                value={loName}
                onChange={(e) => { setLoName(e.target.value); markDirty(); }}
                placeholder="John Smith"
              />
            </div>
            <div className="bps-field">
              <label htmlFor="bps-lo-title">Title</label>
              <input
                id="bps-lo-title"
                type="text"
                value={loTitle}
                onChange={(e) => { setLoTitle(e.target.value); markDirty(); }}
                placeholder="Loan Officer, NMLS# 123456"
              />
            </div>
          </div>

          <div className="bps-field">
            <label htmlFor="bps-tagline">Tagline</label>
            <input
              id="bps-tagline"
              type="text"
              value={tagline}
              onChange={(e) => { setTagline(e.target.value); markDirty(); }}
              placeholder="Your trusted mortgage partner"
            />
            <p className="bps-hint">Short phrase shown below your name on the booking page</p>
          </div>

          <div className="bps-field">
            <label htmlFor="bps-welcome">Welcome Message</label>
            <textarea
              id="bps-welcome"
              value={welcomeMessage}
              onChange={(e) => { setWelcomeMessage(e.target.value); markDirty(); }}
              placeholder="Schedule a time to meet with us"
              rows={2}
            />
            <p className="bps-hint">Displayed when a borrower first opens your booking page</p>
          </div>
        </div>

        {/* — Branding — */}
        <div className="bps-section">
          <h3 className="bps-section-title">
            <i className="fas fa-palette" aria-hidden="true"></i>
            Branding
          </h3>

          <div className="bps-field">
            <label>Primary Color</label>
            <div className="bps-color-presets">
              {PRESET_COLORS.map((c) => (
                <button
                  key={c.hex}
                  type="button"
                  className={`bps-color-swatch ${primaryColor === c.hex ? 'selected' : ''} ${isLightColor(c.hex) ? 'light-color' : ''}`}
                  style={{ backgroundColor: c.hex }}
                  title={c.name}
                  aria-label={`${c.name} (${c.hex})`}
                  aria-pressed={primaryColor === c.hex}
                  onClick={() => handleColorChange(c.hex)}
                />
              ))}
            </div>

            <div className="bps-color-custom">
              <input
                type="color"
                value={primaryColor}
                onChange={(e) => handleColorChange(e.target.value)}
                aria-label="Custom color picker"
              />
              <input
                type="text"
                value={primaryColor}
                onChange={(e) => {
                  const val = e.target.value;
                  if (/^#[0-9a-fA-F]{0,6}$/.test(val)) {
                    setPrimaryColor(val);
                    markDirty();
                  }
                }}
                placeholder="#218D8D"
                maxLength={7}
                aria-label="Custom color hex value"
              />
            </div>
          </div>

          <div className="bps-toggle-row">
            <span className="bps-toggle-label" id="bps-powered-by-label">Show "Powered by Perennia" badge</span>
            <label className="bps-toggle">
              <input
                type="checkbox"
                checked={showPoweredBy}
                onChange={(e) => { setShowPoweredBy(e.target.checked); markDirty(); }}
                aria-labelledby="bps-powered-by-label"
              />
              <span className="bps-toggle-track" />
            </label>
          </div>
        </div>

        {/* — Photo — */}
        <div className="bps-section">
          <h3 className="bps-section-title">
            <i className="fas fa-camera" aria-hidden="true"></i>
            Profile Photo
          </h3>

          <div className="bps-photo-area">
            <div className="bps-photo-preview">
              {photoUrl ? (
                <img
                  src={photoUrl}
                  alt="Profile"
                  onError={(e) => { e.target.style.display = 'none'; }}
                />
              ) : (
                <span className="bps-photo-placeholder" aria-hidden="true">
                  <i className="fas fa-user"></i>
                </span>
              )}
            </div>
            <div className="bps-photo-actions">
              <input
                type="url"
                value={photoUrl}
                onChange={(e) => { setPhotoUrl(e.target.value); markDirty(); }}
                placeholder="https://example.com/photo.jpg"
                aria-label="Profile photo URL"
              />
              <span className="bps-hint">Enter a URL to your profile photo</span>
            </div>
          </div>
        </div>

        {/* — Booking Link — */}
        <div className="bps-section">
          <h3 className="bps-section-title">
            <i className="fas fa-link" aria-hidden="true"></i>
            Booking Link
          </h3>

          <div className="bps-link-display">
            <i className="fas fa-globe" aria-hidden="true"></i>
            <span className="bps-link-url">
              {APP_BASE}/book/<strong>{slug || 'your-name'}</strong>
            </span>
          </div>

          {editingSlug ? (
            <>
              <div className="bps-slug-edit">
                <input
                  type="text"
                  value={slugDraft}
                  onChange={(e) => {
                    setSlugDraft(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''));
                    setSlugError('');
                  }}
                  className={slugError ? 'invalid' : ''}
                  placeholder="john-smith"
                  aria-label="Edit booking slug"
                  aria-invalid={!!slugError}
                  aria-describedby={slugError ? 'bps-slug-error' : undefined}
                  autoFocus
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') saveSlug();
                    if (e.key === 'Escape') cancelEditSlug();
                  }}
                />
                <button className="bps-btn-save" onClick={saveSlug}>Save</button>
                <button className="bps-btn-cancel" onClick={cancelEditSlug}>Cancel</button>
              </div>
              {slugError && <p className="bps-slug-validation" id="bps-slug-error" role="alert">{slugError}</p>}
            </>
          ) : (
            <div className="bps-link-actions">
              <button onClick={startEditSlug} title="Edit booking slug" aria-label="Edit booking slug">
                <i className="fas fa-pencil-alt" aria-hidden="true"></i>
                Edit Slug
              </button>
              <button
                onClick={handleCopyLink}
                className={copied ? 'copied' : ''}
                title="Copy booking link"
                aria-label={copied ? 'Link copied to clipboard' : 'Copy booking link'}
              >
                <i className={`fas ${copied ? 'fa-check' : 'fa-copy'}`} aria-hidden="true"></i>
                {copied ? 'Copied!' : 'Copy Link'}
              </button>
              <button
                onClick={() => {
                  const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(bookingUrl)}`;
                  window.open(qrUrl, '_blank', 'noopener');
                }}
                title="Download QR code"
                aria-label="Download QR code"
              >
                <i className="fas fa-qrcode" aria-hidden="true"></i>
                QR Code
              </button>
            </div>
          )}

          {/* QR Code Placeholder */}
          <div className="bps-qr-placeholder">
            <div className="bps-qr-grid" aria-hidden="true">
              {qrCells.map((dark, i) => (
                <div key={i} className={`bps-qr-cell ${dark ? '' : 'white'}`} />
              ))}
            </div>
            <span className="bps-qr-label">Scan to book</span>
          </div>
        </div>

        {/* — Save & Preview Buttons — */}
        <div style={{ display: 'flex', gap: 10 }}>
          <button
            className="btn-primary"
            onClick={handleSave}
            disabled={saving}
            style={{
              flex: 1,
              padding: '12px 24px',
              background: '#218D8D',
              color: '#fff',
              border: 'none',
              borderRadius: 8,
              fontSize: 14,
              fontWeight: 500,
              cursor: saving ? 'not-allowed' : 'pointer',
              opacity: saving ? 0.7 : 1,
            }}
          >
            {saving ? 'Saving...' : 'Save Booking Page'}
          </button>
        </div>
      </div>

      {/* ================================================================
          RIGHT: Live Preview Panel
          ================================================================ */}
      <div className="bps-preview-panel">
        <div className="bps-preview-label">Live Preview</div>

        <div className="bps-mockup-frame">
          {/* Browser chrome */}
          <div className="bps-mockup-chrome">
            <div className="bps-chrome-dots">
              <span className="bps-chrome-dot red" />
              <span className="bps-chrome-dot yellow" />
              <span className="bps-chrome-dot green" />
            </div>
            <div className="bps-chrome-url">
              {APP_BASE}/book/{slug || 'your-name'}
            </div>
          </div>

          {/* Booking page body */}
          <div className="bps-mockup-body">
            {/* Header / Profile */}
            <div className="bps-mock-header">
              {photoUrl ? (
                <img
                  className="bps-mock-photo"
                  src={photoUrl}
                  alt={loName || 'Profile'}
                  style={{ borderColor: primaryColor }}
                  onError={(e) => { e.target.style.display = 'none'; }}
                />
              ) : (
                <div
                  className="bps-mock-photo-placeholder"
                  style={{ borderColor: primaryColor, color: primaryColor }}
                >
                  <i className="fas fa-user"></i>
                </div>
              )}

              <p className="bps-mock-name">{loName || 'Your Name'}</p>

              {loTitle && (
                <p className="bps-mock-title-text">{loTitle}</p>
              )}

              {tagline && (
                <p className="bps-mock-tagline" style={{ color: primaryColor }}>
                  {tagline}
                </p>
              )}

              {welcomeMessage && (
                <p className="bps-mock-welcome">{welcomeMessage}</p>
              )}
            </div>

            {/* Appointment type buttons */}
            <div className="bps-mock-types">
              {previewTypes.map((type, i) => (
                <div
                  key={i}
                  className="bps-mock-type-btn"
                  style={{
                    borderColor: primaryColor,
                    color: primaryColor,
                  }}
                >
                  {type.type_name}
                  <span className="bps-mock-duration">{type.default_duration_minutes} min</span>
                </div>
              ))}
            </div>

            {/* Mock date row */}
            <div className="bps-mock-dates">
              {mockDates.map((d, i) => (
                <div
                  key={i}
                  className={`bps-mock-date ${d.active ? 'active' : ''}`}
                  style={d.active ? { borderColor: primaryColor, color: primaryColor } : {}}
                >
                  {d.day}
                  <span className="day-num">{d.num}</span>
                </div>
              ))}
            </div>

            {/* Powered by footer */}
            {showPoweredBy && (
              <div className="bps-mock-footer">
                Powered by <strong>Perennia AI</strong>
              </div>
            )}
          </div>
        </div>

        {/* Open actual booking page */}
        <button
          className="bps-preview-btn"
          onClick={() => {
            if (slug) {
              window.open(`/book/${slug}`, '_blank', 'noopener');
            } else {
              toast.info('Save your booking page first to preview it');
            }
          }}
          aria-label="Preview your booking page in a new tab"
        >
          <i className="fas fa-external-link-alt" aria-hidden="true"></i>
          Preview your booking page
        </button>
      </div>
    </div>
  );
};

export default BookingPageStep;
