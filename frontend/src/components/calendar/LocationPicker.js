import React, { useState, useEffect, useCallback, useMemo } from 'react';

const API_BASE = process.env.REACT_APP_API_URL || '';

const LOCATION_ICONS = {
  office: '\uD83C\uDFE2',
  virtual: '\uD83D\uDCF9',
  phone: '\uD83D\uDCDE',
  borrower_home: '\uD83C\uDFE0',
};

const LOCATION_TYPE_LABELS = {
  office: 'Office',
  virtual: 'Virtual',
  phone: 'Phone',
  borrower_home: "Borrower's Home",
};

async function apiFetch(path, options = {}) {
  const token = localStorage.getItem('token');
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

/**
 * LocationPicker - Inline dropdown for selecting a saved location when
 * creating or editing an appointment.
 *
 * Props:
 *   value           - currently selected location_id (number or null)
 *   onChange         - (locationId, locationData) => void
 *   meetingMode      - optional: if set, filters locations by matching type
 *                      (PHONE -> phone, VIDEO -> virtual, IN_PERSON -> office)
 *   style            - optional: additional styles for the wrapper div
 */
function LocationPicker({ value, onChange, meetingMode, style }) {
  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showQuickAdd, setShowQuickAdd] = useState(false);
  const [quickAddName, setQuickAddName] = useState('');
  const [quickAddSaving, setQuickAddSaving] = useState(false);

  // Load locations on mount
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const data = await apiFetch('/api/scheduling/locations');
        if (!cancelled) {
          setLocations(data.locations || []);
        }
      } catch (err) {
        // Silently fail - picker will show "no locations" state
        if (!cancelled) {
          setLocations([]);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  // Map meeting modes to location types for filtering
  const modeToType = useMemo(() => ({
    PHONE: 'phone',
    VIDEO: 'virtual',
    IN_PERSON: 'office',
  }), []);

  // Filter locations based on meeting mode (if provided)
  const filteredLocations = useMemo(() => {
    if (!meetingMode || !modeToType[meetingMode]) {
      return locations;
    }
    const targetType = modeToType[meetingMode];
    const matched = locations.filter(l => l.location_type === targetType);
    // If no matching locations exist for this mode, show all
    return matched.length > 0 ? matched : locations;
  }, [locations, meetingMode, modeToType]);

  // Find the currently selected location
  const selectedLocation = useMemo(() => {
    if (!value) return null;
    return locations.find(l => l.id === value) || null;
  }, [value, locations]);

  const handleSelect = useCallback((e) => {
    const selectedId = e.target.value;
    if (selectedId === '__new__') {
      setShowQuickAdd(true);
      return;
    }
    const numId = selectedId ? parseInt(selectedId, 10) : null;
    const loc = numId ? locations.find(l => l.id === numId) : null;
    onChange(numId, loc);
  }, [locations, onChange]);

  // Quick-add a new location inline
  const handleQuickAdd = useCallback(async (e) => {
    e.preventDefault();
    if (!quickAddName.trim()) return;

    // Infer type from meeting mode
    const inferredType = meetingMode ? (modeToType[meetingMode] || 'office') : 'office';

    setQuickAddSaving(true);
    try {
      const data = await apiFetch('/api/scheduling/locations', {
        method: 'POST',
        body: JSON.stringify({
          name: quickAddName.trim(),
          location_type: inferredType,
        }),
      });
      const newLoc = data.location;
      setLocations(prev => [...prev, newLoc]);
      onChange(newLoc.id, newLoc);
      setShowQuickAdd(false);
      setQuickAddName('');
    } catch (err) {
      // Fail silently for inline add
    } finally {
      setQuickAddSaving(false);
    }
  }, [quickAddName, meetingMode, modeToType, onChange]);

  // Format the detail line shown below the dropdown
  const getLocationDetail = (loc) => {
    if (!loc) return null;
    switch (loc.location_type) {
      case 'office': {
        const parts = [loc.address_line1, loc.city, loc.state].filter(Boolean);
        return parts.length > 0 ? parts.join(', ') : null;
      }
      case 'virtual':
        return loc.meeting_url
          ? (loc.meeting_url.length > 50 ? loc.meeting_url.substring(0, 50) + '...' : loc.meeting_url)
          : null;
      case 'phone':
        return loc.phone_number || null;
      case 'borrower_home':
        return "Location provided by borrower";
      default:
        return null;
    }
  };

  if (loading) {
    return (
      <div style={{ ...style, fontSize: 13, color: '#9ca3af' }}>
        Loading locations...
      </div>
    );
  }

  return (
    <div style={style}>
      <select
        value={value || ''}
        onChange={handleSelect}
        style={{
          width: '100%', padding: '8px 12px', borderRadius: 6,
          border: '1px solid #d1d5db', fontSize: 14, boxSizing: 'border-box',
          background: '#fff',
        }}
      >
        <option value="">-- Select location --</option>
        {filteredLocations.map(loc => (
          <option key={loc.id} value={loc.id}>
            {LOCATION_ICONS[loc.location_type] || ''} {loc.name}
            {loc.is_default ? ' (Default)' : ''}
          </option>
        ))}
        <option value="__new__">+ New Location...</option>
      </select>

      {/* Detail line for selected location */}
      {selectedLocation && (
        <div style={{ marginTop: 4, fontSize: 12, color: '#6b7280', display: 'flex', alignItems: 'center', gap: 4 }}>
          <span>{LOCATION_ICONS[selectedLocation.location_type] || ''}</span>
          <span style={{
            background: '#f3f4f6', padding: '1px 6px', borderRadius: 4, fontSize: 11,
          }}>
            {LOCATION_TYPE_LABELS[selectedLocation.location_type] || selectedLocation.location_type}
          </span>
          {getLocationDetail(selectedLocation) && (
            <span style={{ marginLeft: 4 }}>{getLocationDetail(selectedLocation)}</span>
          )}
          {selectedLocation.instructions && (
            <span
              title={selectedLocation.instructions}
              style={{ cursor: 'help', color: '#9ca3af' }}
            >
              {'\u2139\uFE0F'}
            </span>
          )}
        </div>
      )}

      {/* Quick-add inline form */}
      {showQuickAdd && (
        <form
          onSubmit={handleQuickAdd}
          style={{
            marginTop: 8, display: 'flex', gap: 6, alignItems: 'center',
          }}
        >
          <input
            type="text"
            value={quickAddName}
            onChange={e => setQuickAddName(e.target.value)}
            placeholder="Location name"
            autoFocus
            style={{
              flex: 1, padding: '6px 10px', borderRadius: 6,
              border: '1px solid #d1d5db', fontSize: 13,
            }}
          />
          <button
            type="submit"
            disabled={quickAddSaving || !quickAddName.trim()}
            style={{
              padding: '6px 12px', borderRadius: 6, border: 'none',
              background: '#2563eb', color: '#fff', cursor: 'pointer', fontSize: 13,
              opacity: (quickAddSaving || !quickAddName.trim()) ? 0.5 : 1,
            }}
          >
            {quickAddSaving ? '...' : 'Add'}
          </button>
          <button
            type="button"
            onClick={() => { setShowQuickAdd(false); setQuickAddName(''); }}
            style={{
              padding: '6px 10px', borderRadius: 6, border: '1px solid #d1d5db',
              background: '#fff', cursor: 'pointer', fontSize: 13,
            }}
          >
            Cancel
          </button>
        </form>
      )}
    </div>
  );
}

export default LocationPicker;
