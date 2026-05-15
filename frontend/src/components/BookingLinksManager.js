/**
 * Booking Links Manager
 *
 * Manage shareable booking pages with custom slugs.
 * Self-contained component with own state, loading, and API calls.
 */

import React, { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import './BookingLinksManager.css';

const BookingLinksManager = () => {
  const [links, setLinks] = useState([]);
  const [appointmentTypes, setAppointmentTypes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [copiedId, setCopiedId] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [form, setForm] = useState({
    link_name: '',
    slug: '',
    description: '',
    appointment_type_ids: [],
    is_public: true,
  });

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [linksRes, typesRes] = await Promise.all([
        api.get('/api/v1/scheduler/booking-links'),
        api.get('/api/v1/scheduler/appointment-types').catch(() => null),
      ]);

      const linksData = linksRes.data;
      setLinks(linksData.booking_links || linksData || []);

      if (typesRes) {
        const typesData = typesRes.data;
        setAppointmentTypes(typesData.appointment_types || typesData || []);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Focus trap for modal
  useEffect(() => {
    if (!showModal) return;
    const modal = document.querySelector('.scheduler-modal');
    if (!modal) return;
    const focusableSelector = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
    const focusable = modal.querySelectorAll(focusableSelector);
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const previousFocus = document.activeElement;
    first?.focus();

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') { setShowModal(false); return; }
      if (e.key !== 'Tab') return;
      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last?.focus(); }
      } else {
        if (document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }
    };
    modal.addEventListener('keydown', handleKeyDown);
    return () => {
      modal.removeEventListener('keydown', handleKeyDown);
      previousFocus?.focus();
    };
  }, [showModal]);

  const generateSlug = (name) => {
    return name
      .toLowerCase()
      .replace(/[^a-z0-9\s-]/g, '')
      .replace(/\s+/g, '-')
      .substring(0, 60);
  };

  const handleNameChange = (value) => {
    setForm(prev => ({
      ...prev,
      link_name: value,
      slug: generateSlug(value),
    }));
  };

  const toggleAppointmentType = (id) => {
    setForm(prev => {
      const ids = prev.appointment_type_ids.includes(id)
        ? prev.appointment_type_ids.filter(t => t !== id)
        : [...prev.appointment_type_ids, id];
      return { ...prev, appointment_type_ids: ids };
    });
  };

  const handleCopy = async (link) => {
    const bookingUrl = `${window.location.origin}/book/${link.slug}`;
    try {
      await navigator.clipboard.writeText(bookingUrl);
      setCopiedId(link.id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      // Fallback
      const textarea = document.createElement('textarea');
      textarea.value = bookingUrl;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopiedId(link.id);
      setTimeout(() => setCopiedId(null), 2000);
    }
  };

  const openCreate = () => {
    setForm({
      link_name: '',
      slug: '',
      description: '',
      appointment_type_ids: [],
      is_public: true,
    });
    setShowModal(true);
  };

  const handleSave = async () => {
    if (!form.link_name.trim()) return;
    setSaving(true);
    try {
      const payload = { ...form };
      if (!payload.slug) {
        payload.slug = generateSlug(payload.link_name);
      }

      await api.post('/api/v1/scheduler/booking-links', payload);

      setShowModal(false);
      await loadData();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id) => {
    try {
      await api.delete(`/api/v1/scheduler/booking-links/${id}`);
      setDeleteConfirm(null);
      await loadData();
    } catch (err) {
      setError(err.message);
    }
  };

  if (loading) {
    return (
      <div className="blm-container">
        <div className="blm-loading" role="status">
          <div className="blm-spinner"></div>
          <p>Loading booking links...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="blm-container">
      <div className="blm-header">
        <div>
          <h2>Booking Links</h2>
          <p className="blm-subtitle">Create shareable booking pages for clients to schedule appointments.</p>
        </div>
        <button className="blm-btn-primary" onClick={openCreate} aria-label="Create new booking link">
          <i className="fas fa-plus"></i> New Link
        </button>
      </div>

      {error && (
        <div className="blm-error" role="alert">
          <i className="fas fa-exclamation-circle"></i>
          {error}
          <button onClick={() => setError(null)} aria-label="Dismiss error">&times;</button>
        </div>
      )}

      {links.length === 0 ? (
        <div className="blm-empty">
          <i className="fas fa-link"></i>
          <h3>No Booking Links</h3>
          <p>Create a booking link to share with clients.</p>
          <button className="blm-btn-primary" onClick={openCreate}>
            <i className="fas fa-plus"></i> Create Booking Link
          </button>
        </div>
      ) : (
        <div className="blm-list">
          {links.map(link => (
            <div key={link.id} className="blm-card">
              <div className="blm-card-body">
                <div className="blm-card-top">
                  <div className="blm-card-info">
                    <h3>{link.link_name}</h3>
                    <div className="blm-slug">
                      <i className="fas fa-link"></i>
                      /book/{link.slug}
                    </div>
                    {link.description && <p className="blm-card-desc">{link.description}</p>}
                  </div>
                  <div className="blm-card-actions">
                    <button
                      className={`blm-btn-copy ${copiedId === link.id ? 'copied' : ''}`}
                      onClick={() => handleCopy(link)}
                      title="Copy booking URL"
                      aria-label={copiedId === link.id ? "URL copied" : "Copy booking URL"}
                    >
                      <i className={`fas ${copiedId === link.id ? 'fa-check' : 'fa-copy'}`}></i>
                      {copiedId === link.id ? 'Copied!' : 'Copy'}
                    </button>
                    {deleteConfirm === link.id ? (
                      <span className="blm-delete-confirm">
                        <button className="blm-btn-danger-sm" onClick={() => handleDelete(link.id)}>
                          Confirm
                        </button>
                        <button className="blm-btn-cancel-sm" onClick={() => setDeleteConfirm(null)}>
                          Cancel
                        </button>
                      </span>
                    ) : (
                      <button
                        className="blm-btn-icon danger"
                        onClick={() => setDeleteConfirm(link.id)}
                        title="Delete"
                        aria-label="Delete this booking link"
                      >
                        <i className="fas fa-trash"></i>
                      </button>
                    )}
                  </div>
                </div>
                {(link.total_views != null || link.total_bookings != null) && (
                  <div className="blm-stats">
                    {link.total_views != null && (
                      <span className="blm-stat">
                        <i className="fas fa-eye"></i> {link.total_views} views
                      </span>
                    )}
                    {link.total_bookings != null && (
                      <span className="blm-stat">
                        <i className="fas fa-calendar-check"></i> {link.total_bookings} bookings
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modal */}
      {showModal && (
        <div className="scheduler-modal-overlay" onClick={() => setShowModal(false)}>
          <div className="scheduler-modal" onClick={e => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="blm-modal-title">
            <div className="scheduler-modal-header">
              <h3 id="blm-modal-title">New Booking Link</h3>
              <button className="scheduler-modal-close" onClick={() => setShowModal(false)} aria-label="Close">
                <i className="fas fa-times"></i>
              </button>
            </div>
            <div className="scheduler-modal-body">
              {/* Link Name */}
              <div className="blm-form-group">
                <label htmlFor="blm-name">Link Name <span className="required">*</span></label>
                <input
                  id="blm-name"
                  type="text"
                  value={form.link_name}
                  onChange={e => handleNameChange(e.target.value)}
                  placeholder="e.g., Schedule a Consultation"
                />
              </div>

              {/* Slug */}
              <div className="blm-form-group">
                <label htmlFor="blm-slug">URL Slug</label>
                <div className="blm-slug-input">
                  <span className="blm-slug-prefix">/book/</span>
                  <input
                    id="blm-slug"
                    type="text"
                    value={form.slug}
                    onChange={e => setForm(prev => ({ ...prev, slug: e.target.value }))}
                    placeholder="consultation"
                  />
                </div>
                <span className="blm-preview">
                  Preview: {window.location.origin}/book/{form.slug || '...'}
                </span>
              </div>

              {/* Description */}
              <div className="blm-form-group">
                <label htmlFor="blm-description">Description</label>
                <textarea
                  id="blm-description"
                  value={form.description}
                  onChange={e => setForm(prev => ({ ...prev, description: e.target.value }))}
                  placeholder="Brief description of this booking page..."
                  rows={2}
                />
              </div>

              {/* Appointment Types */}
              {appointmentTypes.length > 0 && (
                <div className="blm-form-group">
                  <label>Appointment Types</label>
                  <div className="blm-types-list">
                    {appointmentTypes.filter(t => t.is_active).map(type => (
                      <label
                        key={type.id}
                        className={`blm-type-check ${form.appointment_type_ids.includes(type.id) ? 'selected' : ''}`}
                      >
                        <input
                          type="checkbox"
                          checked={form.appointment_type_ids.includes(type.id)}
                          onChange={() => toggleAppointmentType(type.id)}
                        />
                        <span className="blm-type-dot" style={{ backgroundColor: type.color || '#1F3D2E' }} />
                        <span>{type.type_name}</span>
                        <span className="blm-type-duration">{type.duration_minutes} min</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}

              {/* Public */}
              <div className="blm-form-group">
                <label className="blm-checkbox" htmlFor="blm-public">
                  <input
                    id="blm-public"
                    type="checkbox"
                    checked={form.is_public}
                    onChange={e => setForm(prev => ({ ...prev, is_public: e.target.checked }))}
                  />
                  Public Link
                  <span className="blm-checkbox-hint">Anyone with the link can view and book</span>
                </label>
              </div>
            </div>

            <div className="scheduler-modal-footer">
              <button className="blm-btn-secondary" onClick={() => setShowModal(false)}>
                Cancel
              </button>
              <button
                className="blm-btn-primary"
                onClick={handleSave}
                disabled={saving || !form.link_name.trim()}
              >
                {saving ? (
                  <><i className="fas fa-spinner fa-spin"></i> Creating...</>
                ) : (
                  'Create Link'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default BookingLinksManager;
