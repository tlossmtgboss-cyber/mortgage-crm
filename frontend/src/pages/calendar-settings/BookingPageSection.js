/**
 * BookingPageSection - Calendar Settings
 *
 * Handles booking page branding, preview, and booking links management.
 */
import React, { useState } from 'react';
import { toast } from '../../utils/toast';

export default function BookingPageSection({
  bookingPage,
  setBookingPage,
  markChanged,
}) {
  const [copiedLink, setCopiedLink] = useState(null);

  const updateBranding = (key, value) => {
    setBookingPage(prev => ({
      ...prev,
      branding: { ...prev.branding, [key]: value },
    }));
    markChanged();
  };

  const handleCopyLink = (url) => {
    const fullUrl = `${window.location.origin}${url}`;
    navigator.clipboard.writeText(fullUrl).then(() => {
      setCopiedLink(url);
      toast.success('Link copied to clipboard');
      setTimeout(() => setCopiedLink(null), 2000);
    }).catch(() => {
      toast.error('Failed to copy link');
    });
  };

  return (
    <section className="cal-settings-section" role="tabpanel" id="panel-booking-page" aria-labelledby="calnav-booking-page">
      <h2>Booking Page</h2>
      <p className="section-description">Customize the appearance of your public booking page.</p>

      {/* Branding */}
      <div className="form-grid">
        <div className="form-field">
          <label>Logo URL</label>
          <input
            type="url"
            value={bookingPage.branding.logo_url || ''}
            onChange={(e) => updateBranding('logo_url', e.target.value || null)}
            placeholder="https://example.com/logo.png"
          />
        </div>
        <div className="form-field">
          <label>Primary Color</label>
          <div className="color-input-row">
            <input
              type="color"
              value={bookingPage.branding.primary_color}
              onChange={(e) => updateBranding('primary_color', e.target.value)}
            />
            <input
              type="text"
              value={bookingPage.branding.primary_color}
              onChange={(e) => updateBranding('primary_color', e.target.value)}
              className="color-text-input"
            />
          </div>
        </div>
        <div className="form-field">
          <label>Secondary Color</label>
          <div className="color-input-row">
            <input
              type="color"
              value={bookingPage.branding.secondary_color}
              onChange={(e) => updateBranding('secondary_color', e.target.value)}
            />
            <input
              type="text"
              value={bookingPage.branding.secondary_color}
              onChange={(e) => updateBranding('secondary_color', e.target.value)}
              className="color-text-input"
            />
          </div>
        </div>
        <div className="form-field full-width">
          <label>Tagline</label>
          <input
            type="text"
            value={bookingPage.branding.tagline || ''}
            onChange={(e) => updateBranding('tagline', e.target.value)}
            placeholder="Your trusted mortgage partner"
          />
        </div>
        <div className="form-field full-width">
          <label>Welcome Message</label>
          <textarea
            value={bookingPage.branding.welcome_message || ''}
            onChange={(e) => updateBranding('welcome_message', e.target.value)}
            rows={2}
            placeholder="Schedule a time to meet with us"
          />
        </div>
        <div className="form-field">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={bookingPage.branding.show_branding}
              onChange={(e) => updateBranding('show_branding', e.target.checked)}
            />
            Show Perennia branding
          </label>
        </div>
      </div>

      {/* Preview */}
      <h3 className="subsection-title">Preview</h3>
      <div
        className="booking-preview"
        style={{
          borderColor: bookingPage.branding.primary_color,
          backgroundColor: bookingPage.branding.secondary_color,
        }}
      >
        {bookingPage.branding.logo_url && (
          <img src={bookingPage.branding.logo_url} alt="Logo" className="preview-logo" />
        )}
        <h4 style={{ color: bookingPage.branding.primary_color }}>
          {bookingPage.branding.tagline || 'Your Booking Page'}
        </h4>
        <p>{bookingPage.branding.welcome_message || 'Schedule a time to meet with us'}</p>
        <button className="preview-cta" style={{ backgroundColor: bookingPage.branding.primary_color }}>
          Book an Appointment
        </button>
      </div>

      {/* Booking Links */}
      <h3 className="subsection-title">Booking Links</h3>
      {bookingPage.booking_links.length === 0 ? (
        <p className="empty-hint">No booking links yet. Create one in the Booking Links tab of Smart Scheduler Settings.</p>
      ) : (
        <div className="booking-links-list">
          {bookingPage.booking_links.map(link => (
            <div key={link.id} className="booking-link-row">
              <div className="link-info">
                <strong>{link.name}</strong>
                <code>{window.location.origin}{link.url}</code>
              </div>
              <div className="link-actions">
                <button
                  className="btn-secondary btn-sm"
                  onClick={() => handleCopyLink(link.url)}
                >
                  <i className={`fas ${copiedLink === link.url ? 'fa-check' : 'fa-copy'}`}></i>
                  {copiedLink === link.url ? 'Copied' : 'Copy'}
                </button>
                <button
                  className="btn-secondary btn-sm"
                  onClick={() => {
                    const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(window.location.origin + link.url)}`;
                    window.open(qrUrl, '_blank');
                  }}
                  title="Generate QR Code"
                >
                  <i className="fas fa-qrcode"></i> QR
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
