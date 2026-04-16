import React, { useState, useEffect, useCallback } from 'react';
import { getToken } from '../../utils/tokenStore';

const API_BASE = process.env.REACT_APP_API_URL || '';

const LOCATION_TYPE_OPTIONS = [
  { value: 'office', label: 'Office' },
  { value: 'virtual', label: 'Virtual Meeting' },
  { value: 'phone', label: 'Phone' },
  { value: 'borrower_home', label: "Borrower's Home" },
];

const LOCATION_ICONS = {
  office: '\uD83C\uDFE2',
  virtual: '\uD83D\uDCF9',
  phone: '\uD83D\uDCDE',
  borrower_home: '\uD83C\uDFE0',
};

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
// Location Card
// ---------------------------------------------------------------------------

function LocationCard({ location, onEdit, onSetDefault, onToggleActive }) {
  const icon = LOCATION_ICONS[location.location_type] || '';
  const typeLabel = LOCATION_TYPE_OPTIONS.find(o => o.value === location.location_type)?.label || location.location_type;

  const addressParts = [
    location.address_line1,
    location.address_line2,
    [location.city, location.state, location.zip_code].filter(Boolean).join(', '),
  ].filter(Boolean);

  return (
    <div
      style={{
        border: '1px solid #e5e7eb',
        borderRadius: 12,
        padding: 16,
        marginBottom: 12,
        opacity: location.is_active ? 1 : 0.55,
        background: location.is_active ? '#fff' : '#f9fafb',
        transition: 'opacity 0.2s',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span style={{ fontSize: 18 }}>{icon}</span>
            <strong style={{ fontSize: 15 }}>{location.name}</strong>
            {location.is_default && (
              <span style={{
                padding: '1px 8px', borderRadius: 12, fontSize: 11, fontWeight: 600,
                background: '#dbeafe', color: '#1e40af',
              }}>
                Default
              </span>
            )}
            {!location.is_active && (
              <span style={{
                padding: '1px 8px', borderRadius: 12, fontSize: 11, fontWeight: 600,
                background: '#fee2e2', color: '#991b1b',
              }}>
                Inactive
              </span>
            )}
          </div>
          <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 2 }}>
            {typeLabel}
          </div>
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', gap: 6 }}>
          <button
            onClick={() => onEdit(location)}
            style={{
              padding: '4px 10px', fontSize: 12, borderRadius: 6,
              border: '1px solid #d1d5db', background: '#fff', cursor: 'pointer',
            }}
            title="Edit location"
          >
            Edit
          </button>
          {location.is_active && !location.is_default && (
            <button
              onClick={() => onSetDefault(location.id)}
              style={{
                padding: '4px 10px', fontSize: 12, borderRadius: 6,
                border: '1px solid #93c5fd', background: '#eff6ff', color: '#1d4ed8',
                cursor: 'pointer',
              }}
              title="Set as default"
            >
              Set Default
            </button>
          )}
          <button
            onClick={() => onToggleActive(location)}
            style={{
              padding: '4px 10px', fontSize: 12, borderRadius: 6,
              border: '1px solid #d1d5db',
              background: location.is_active ? '#fff' : '#ecfdf5',
              color: location.is_active ? '#991b1b' : '#065f46',
              cursor: 'pointer',
            }}
            title={location.is_active ? 'Deactivate' : 'Reactivate'}
          >
            {location.is_active ? 'Deactivate' : 'Activate'}
          </button>
        </div>
      </div>

      {/* Details */}
      <div style={{ fontSize: 13, color: '#374151' }}>
        {location.location_type === 'office' && addressParts.length > 0 && (
          <div style={{ marginBottom: 4 }}>
            {addressParts.map((line, i) => <div key={i}>{line}</div>)}
          </div>
        )}
        {location.location_type === 'virtual' && location.meeting_url && (
          <div style={{ marginBottom: 4 }}>
            <span style={{ color: '#6b7280' }}>Link: </span>
            <a href={location.meeting_url} target="_blank" rel="noopener noreferrer"
               style={{ color: '#2563eb', textDecoration: 'none' }}>
              {location.meeting_url.length > 60
                ? location.meeting_url.substring(0, 60) + '...'
                : location.meeting_url}
            </a>
          </div>
        )}
        {location.location_type === 'phone' && location.phone_number && (
          <div style={{ marginBottom: 4 }}>
            <span style={{ color: '#6b7280' }}>Phone: </span>
            {location.phone_number}
          </div>
        )}
        {location.instructions && (
          <div style={{ marginTop: 4, fontStyle: 'italic', color: '#6b7280', fontSize: 12 }}>
            {location.instructions}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Location Form Modal
// ---------------------------------------------------------------------------

const EMPTY_FORM = {
  name: '',
  location_type: 'office',
  address_line1: '',
  address_line2: '',
  city: '',
  state: '',
  zip_code: '',
  meeting_url: '',
  phone_number: '',
  instructions: '',
  is_default: false,
};

function LocationFormModal({ location, onSave, onClose, saving }) {
  const isEdit = !!location?.id;
  const [form, setForm] = useState(() => {
    if (isEdit) {
      return {
        name: location.name || '',
        location_type: location.location_type || 'office',
        address_line1: location.address_line1 || '',
        address_line2: location.address_line2 || '',
        city: location.city || '',
        state: location.state || '',
        zip_code: location.zip_code || '',
        meeting_url: location.meeting_url || '',
        phone_number: location.phone_number || '',
        instructions: location.instructions || '',
        is_default: location.is_default || false,
      };
    }
    return { ...EMPTY_FORM };
  });

  const handleChange = (field, value) => {
    setForm(prev => ({ ...prev, [field]: value }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    onSave(form, isEdit ? location.id : null);
  };

  const showAddress = form.location_type === 'office' || form.location_type === 'borrower_home';
  const showMeetingUrl = form.location_type === 'virtual';
  const showPhone = form.location_type === 'phone';

  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: '#fff', borderRadius: 12, padding: 24, width: 500, maxWidth: '95vw',
          maxHeight: '90vh', overflowY: 'auto',
        }}
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="location-modal-title"
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 id="location-modal-title" style={{ margin: 0, fontSize: 18 }}>
            {isEdit ? 'Edit Location' : 'Add Location'}
          </h3>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: '#6b7280' }}
            aria-label="Close dialog"
          >
            &times;
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          {/* Name */}
          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4, color: '#374151' }}>
              Location Name *
            </label>
            <input
              type="text"
              required
              value={form.name}
              onChange={e => handleChange('name', e.target.value)}
              placeholder="e.g., Main Office, Zoom Room"
              style={{
                width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #d1d5db',
                fontSize: 14, boxSizing: 'border-box',
              }}
            />
          </div>

          {/* Type */}
          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4, color: '#374151' }}>
              Location Type
            </label>
            <select
              value={form.location_type}
              onChange={e => handleChange('location_type', e.target.value)}
              style={{
                width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #d1d5db',
                fontSize: 14, boxSizing: 'border-box',
              }}
            >
              {LOCATION_TYPE_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>
                  {LOCATION_ICONS[opt.value]} {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Address fields (office / borrower_home) */}
          {showAddress && (
            <fieldset style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 12, marginBottom: 12 }}>
              <legend style={{ fontSize: 13, fontWeight: 600, color: '#374151', padding: '0 4px' }}>
                Address
              </legend>
              <div style={{ marginBottom: 8 }}>
                <input
                  type="text"
                  value={form.address_line1}
                  onChange={e => handleChange('address_line1', e.target.value)}
                  placeholder="Street address"
                  style={{
                    width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #d1d5db',
                    fontSize: 14, boxSizing: 'border-box',
                  }}
                />
              </div>
              <div style={{ marginBottom: 8 }}>
                <input
                  type="text"
                  value={form.address_line2}
                  onChange={e => handleChange('address_line2', e.target.value)}
                  placeholder="Suite, floor, etc."
                  style={{
                    width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #d1d5db',
                    fontSize: 14, boxSizing: 'border-box',
                  }}
                />
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  type="text"
                  value={form.city}
                  onChange={e => handleChange('city', e.target.value)}
                  placeholder="City"
                  style={{
                    flex: 2, padding: '8px 12px', borderRadius: 6, border: '1px solid #d1d5db',
                    fontSize: 14, boxSizing: 'border-box',
                  }}
                />
                <input
                  type="text"
                  value={form.state}
                  onChange={e => handleChange('state', e.target.value)}
                  placeholder="State"
                  style={{
                    flex: 1, padding: '8px 12px', borderRadius: 6, border: '1px solid #d1d5db',
                    fontSize: 14, boxSizing: 'border-box',
                  }}
                />
                <input
                  type="text"
                  value={form.zip_code}
                  onChange={e => handleChange('zip_code', e.target.value)}
                  placeholder="ZIP"
                  style={{
                    flex: 1, padding: '8px 12px', borderRadius: 6, border: '1px solid #d1d5db',
                    fontSize: 14, boxSizing: 'border-box',
                  }}
                />
              </div>
            </fieldset>
          )}

          {/* Meeting URL (virtual) */}
          {showMeetingUrl && (
            <div style={{ marginBottom: 12 }}>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4, color: '#374151' }}>
                Meeting URL
              </label>
              <input
                type="url"
                value={form.meeting_url}
                onChange={e => handleChange('meeting_url', e.target.value)}
                placeholder="https://zoom.us/j/... or https://meet.google.com/..."
                style={{
                  width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #d1d5db',
                  fontSize: 14, boxSizing: 'border-box',
                }}
              />
            </div>
          )}

          {/* Phone number (phone) */}
          {showPhone && (
            <div style={{ marginBottom: 12 }}>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4, color: '#374151' }}>
                Phone Number
              </label>
              <input
                type="tel"
                value={form.phone_number}
                onChange={e => handleChange('phone_number', e.target.value)}
                placeholder="(555) 123-4567"
                style={{
                  width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #d1d5db',
                  fontSize: 14, boxSizing: 'border-box',
                }}
              />
            </div>
          )}

          {/* Instructions */}
          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4, color: '#374151' }}>
              Instructions
            </label>
            <textarea
              value={form.instructions}
              onChange={e => handleChange('instructions', e.target.value)}
              placeholder="Parking info, entry code, lobby directions..."
              rows={3}
              style={{
                width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #d1d5db',
                fontSize: 14, boxSizing: 'border-box', resize: 'vertical',
              }}
            />
          </div>

          {/* Default toggle */}
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={form.is_default}
                onChange={e => handleChange('is_default', e.target.checked)}
              />
              Set as default location
            </label>
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <button
              type="button"
              onClick={onClose}
              style={{
                padding: '8px 16px', borderRadius: 6, border: '1px solid #d1d5db',
                background: '#fff', cursor: 'pointer', fontSize: 14,
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              style={{
                padding: '8px 16px', borderRadius: 6, border: 'none',
                background: '#2563eb', color: '#fff', cursor: 'pointer', fontSize: 14,
                opacity: saving ? 0.6 : 1,
              }}
            >
              {saving ? 'Saving...' : isEdit ? 'Save Changes' : 'Add Location'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Location Manager (main exported component)
// ---------------------------------------------------------------------------

function LocationManager() {
  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [editingLocation, setEditingLocation] = useState(null);
  const [saving, setSaving] = useState(false);
  const [showInactive, setShowInactive] = useState(false);

  const loadLocations = useCallback(async () => {
    try {
      setLoading(true);
      const data = await apiFetch(
        `/api/scheduling/locations?include_inactive=${showInactive}`
      );
      setLocations(data.locations || []);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [showInactive]);

  useEffect(() => {
    loadLocations();
  }, [loadLocations]);

  const handleSave = useCallback(async (formData, locationId) => {
    setSaving(true);
    try {
      if (locationId) {
        await apiFetch(`/api/scheduling/locations/${locationId}`, {
          method: 'PUT',
          body: JSON.stringify(formData),
        });
      } else {
        await apiFetch('/api/scheduling/locations', {
          method: 'POST',
          body: JSON.stringify(formData),
        });
      }
      setShowModal(false);
      setEditingLocation(null);
      await loadLocations();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }, [loadLocations]);

  const handleEdit = useCallback((location) => {
    setEditingLocation(location);
    setShowModal(true);
  }, []);

  const handleAdd = useCallback(() => {
    setEditingLocation(null);
    setShowModal(true);
  }, []);

  const handleSetDefault = useCallback(async (locationId) => {
    try {
      await apiFetch(`/api/scheduling/locations/${locationId}/default`, {
        method: 'PUT',
      });
      await loadLocations();
    } catch (err) {
      setError(err.message);
    }
  }, [loadLocations]);

  const handleToggleActive = useCallback(async (location) => {
    try {
      if (location.is_active) {
        // Deactivate
        await apiFetch(`/api/scheduling/locations/${location.id}`, {
          method: 'DELETE',
        });
      } else {
        // Reactivate
        await apiFetch(`/api/scheduling/locations/${location.id}`, {
          method: 'PUT',
          body: JSON.stringify({ is_active: true }),
        });
      }
      await loadLocations();
    } catch (err) {
      setError(err.message);
    }
  }, [loadLocations]);

  const handleCloseModal = useCallback(() => {
    setShowModal(false);
    setEditingLocation(null);
  }, []);

  if (loading && locations.length === 0) {
    return <div style={{ padding: 20, color: '#6b7280' }}>Loading locations...</div>;
  }

  return (
    <div style={{ maxWidth: 700 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h3 style={{ margin: 0, fontSize: 18 }}>Meeting Locations</h3>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <label style={{ fontSize: 13, display: 'flex', alignItems: 'center', gap: 4, color: '#6b7280' }}>
            <input
              type="checkbox"
              checked={showInactive}
              onChange={e => setShowInactive(e.target.checked)}
            />
            Show inactive
          </label>
          <button
            onClick={handleAdd}
            style={{
              padding: '6px 14px', borderRadius: 6, border: 'none',
              background: '#2563eb', color: '#fff', cursor: 'pointer', fontSize: 13, fontWeight: 600,
            }}
          >
            + Add Location
          </button>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div style={{
          padding: '8px 12px', background: '#fef2f2', color: '#991b1b', borderRadius: 8,
          marginBottom: 12, fontSize: 13,
        }}>
          {error}
          <button
            onClick={() => setError(null)}
            style={{ marginLeft: 8, background: 'none', border: 'none', color: '#991b1b', cursor: 'pointer', fontWeight: 600 }}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Location list */}
      {locations.length === 0 ? (
        <div style={{
          padding: 32, textAlign: 'center', color: '#9ca3af', border: '2px dashed #e5e7eb',
          borderRadius: 12,
        }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>{'\uD83D\uDCCD'}</div>
          <div style={{ fontSize: 14, marginBottom: 4 }}>No locations yet</div>
          <div style={{ fontSize: 13 }}>
            Add your office, virtual meeting link, or phone number to quickly select when creating appointments.
          </div>
        </div>
      ) : (
        locations.map(loc => (
          <LocationCard
            key={loc.id}
            location={loc}
            onEdit={handleEdit}
            onSetDefault={handleSetDefault}
            onToggleActive={handleToggleActive}
          />
        ))
      )}

      {/* Modal */}
      {showModal && (
        <LocationFormModal
          location={editingLocation}
          onSave={handleSave}
          onClose={handleCloseModal}
          saving={saving}
        />
      )}
    </div>
  );
}

export default LocationManager;
