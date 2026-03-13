/**
 * AvailabilityPreferences
 *
 * Full availability management page for Loan Officers.
 * Two sections:
 *   1. Weekly Schedule  -- recurring weekly time blocks (via PUT /api/v1/scheduler/availability/schedule)
 *   2. Date Overrides   -- date-specific exceptions (POST/DELETE /api/v1/scheduler/availability/exceptions)
 *
 * Integrates with the recurring availability backend endpoints and renders a
 * visual weekly preview showing available hours.
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { toast } from '../../utils/toast';
import AvailabilityDayRow from './AvailabilityDayRow';
import AvailabilityOverrides from './AvailabilityOverrides';
import '../../styles/availability.css';

// Import api instance for making requests
import api from '../../services/api';

// ============================================================================
// Constants
// ============================================================================

const DAY_LABELS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const DAY_ABBREV = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

const COMMON_TIMEZONES = [
  { value: 'America/New_York', label: 'Eastern (ET)' },
  { value: 'America/Chicago', label: 'Central (CT)' },
  { value: 'America/Denver', label: 'Mountain (MT)' },
  { value: 'America/Los_Angeles', label: 'Pacific (PT)' },
  { value: 'America/Anchorage', label: 'Alaska (AKT)' },
  { value: 'Pacific/Honolulu', label: 'Hawaii (HST)' },
];

const DEFAULT_BLOCK = { start: '09:00', end: '17:00' };

// Build the default weekly schedule: Mon-Fri enabled with 9-5, Sat-Sun disabled
function buildDefaultSchedule() {
  const schedule = {};
  for (let i = 0; i < 7; i++) {
    schedule[i] = {
      enabled: i < 5, // Mon-Fri enabled
      blocks: i < 5 ? [{ ...DEFAULT_BLOCK }] : [{ start: '10:00', end: '14:00' }],
    };
  }
  return schedule;
}

// ============================================================================
// API helpers
// ============================================================================

const availabilityAPI = {
  getSchedule: async () => {
    const response = await api.get('/api/v1/scheduler/availability/schedule');
    return response.data;
  },
  updateSchedule: async (schedule, timezone) => {
    const response = await api.put('/api/v1/scheduler/availability/schedule', {
      schedule,
      timezone,
    });
    return response.data;
  },
  getExceptions: async () => {
    const response = await api.get('/api/v1/scheduler/availability/exceptions');
    return response.data;
  },
  addException: async (data) => {
    const response = await api.post('/api/v1/scheduler/availability/exceptions', data);
    return response.data;
  },
  removeException: async (id) => {
    const response = await api.delete(`/api/v1/scheduler/availability/exceptions/${id}`);
    return response.data;
  },
};

// ============================================================================
// Component
// ============================================================================

function AvailabilityPreferences() {
  const [schedule, setSchedule] = useState(buildDefaultSchedule);
  const [timezone, setTimezone] = useState('America/Chicago');
  const [overrides, setOverrides] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const [overridesLoading, setOverridesLoading] = useState(false);

  // ------------------------------------------------------------------
  // Data loading
  // ------------------------------------------------------------------

  const loadSchedule = useCallback(async () => {
    try {
      const res = await availabilityAPI.getSchedule();
      const blocks = res.schedule || [];

      if (blocks.length > 0) {
        // Convert flat list of blocks into day-indexed schedule
        const newSchedule = buildDefaultSchedule();
        // First mark all days as disabled
        for (let i = 0; i < 7; i++) {
          newSchedule[i] = { enabled: false, blocks: [{ ...DEFAULT_BLOCK }] };
        }
        // Group blocks by day_of_week
        const byDay = {};
        for (const block of blocks) {
          const dow = block.day_of_week;
          if (!byDay[dow]) byDay[dow] = [];
          byDay[dow].push({ start: block.start_time, end: block.end_time });
        }
        for (const [dow, dayBlocks] of Object.entries(byDay)) {
          newSchedule[Number(dow)] = { enabled: true, blocks: dayBlocks };
        }
        // Extract timezone from first block
        if (blocks[0]?.timezone) {
          setTimezone(blocks[0].timezone);
        }
        setSchedule(newSchedule);
      }
    } catch (err) {
      // If 404 or no data, use defaults (already set)
      if (err.response?.status !== 404) {
        console.error('Failed to load availability schedule:', err);
      }
    }
  }, []);

  const loadOverrides = useCallback(async () => {
    try {
      const res = await availabilityAPI.getExceptions();
      setOverrides(res.exceptions || []);
    } catch (err) {
      if (err.response?.status !== 404) {
        console.error('Failed to load overrides:', err);
      }
    }
  }, []);

  useEffect(() => {
    const loadAll = async () => {
      setLoading(true);
      await Promise.all([loadSchedule(), loadOverrides()]);
      setLoading(false);
    };
    loadAll();
  }, [loadSchedule, loadOverrides]);

  // ------------------------------------------------------------------
  // Schedule mutation handlers
  // ------------------------------------------------------------------

  const handleToggleDay = useCallback((dayIndex, enabled) => {
    setSchedule((prev) => ({
      ...prev,
      [dayIndex]: {
        ...prev[dayIndex],
        enabled,
        // Reset to default block when re-enabling
        blocks: enabled && prev[dayIndex].blocks.length === 0
          ? [{ ...DEFAULT_BLOCK }]
          : prev[dayIndex].blocks,
      },
    }));
    setHasChanges(true);
  }, []);

  const handleBlockChange = useCallback((dayIndex, blockIndex, field, value) => {
    setSchedule((prev) => {
      const newBlocks = [...prev[dayIndex].blocks];
      newBlocks[blockIndex] = { ...newBlocks[blockIndex], [field]: value };
      return { ...prev, [dayIndex]: { ...prev[dayIndex], blocks: newBlocks } };
    });
    setHasChanges(true);
  }, []);

  const handleAddBlock = useCallback((dayIndex) => {
    setSchedule((prev) => {
      const existing = prev[dayIndex].blocks;
      // Default the new block to start after the last block's end time
      const lastEnd = existing[existing.length - 1]?.end || '12:00';
      const [h, m] = lastEnd.split(':').map(Number);
      const newStart = `${String(Math.min(h + 1, 23)).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
      const newEndH = Math.min(h + 5, 23);
      const newEnd = `${String(newEndH).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
      return {
        ...prev,
        [dayIndex]: {
          ...prev[dayIndex],
          blocks: [...existing, { start: newStart, end: newEnd }],
        },
      };
    });
    setHasChanges(true);
  }, []);

  const handleRemoveBlock = useCallback((dayIndex, blockIndex) => {
    setSchedule((prev) => {
      const newBlocks = prev[dayIndex].blocks.filter((_, i) => i !== blockIndex);
      return {
        ...prev,
        [dayIndex]: {
          ...prev[dayIndex],
          blocks: newBlocks.length > 0 ? newBlocks : [{ ...DEFAULT_BLOCK }],
        },
      };
    });
    setHasChanges(true);
  }, []);

  const handleTimezoneChange = useCallback((e) => {
    setTimezone(e.target.value);
    setHasChanges(true);
  }, []);

  // ------------------------------------------------------------------
  // Save schedule
  // ------------------------------------------------------------------

  const handleSave = useCallback(async () => {
    // Validate blocks
    for (let i = 0; i < 7; i++) {
      const day = schedule[i];
      if (!day.enabled) continue;
      for (let j = 0; j < day.blocks.length; j++) {
        const block = day.blocks[j];
        if (block.start >= block.end) {
          toast.error(`${DAY_LABELS[i]}: Block ${j + 1} start time must be before end time`);
          return;
        }
      }
    }

    setSaving(true);
    try {
      // Convert schedule to API format: { "0": [{"start": "09:00", "end": "17:00"}], ... }
      const apiSchedule = {};
      for (let i = 0; i < 7; i++) {
        const day = schedule[i];
        if (day.enabled) {
          apiSchedule[String(i)] = day.blocks.map((b) => ({ start: b.start, end: b.end }));
        }
        // Disabled days are omitted (no blocks sent)
      }

      await availabilityAPI.updateSchedule(apiSchedule, timezone);
      toast.success('Availability schedule saved');
      setHasChanges(false);
    } catch (err) {
      const detail = err.response?.data?.detail || 'Failed to save availability schedule';
      toast.error(detail);
    } finally {
      setSaving(false);
    }
  }, [schedule, timezone]);

  // ------------------------------------------------------------------
  // Override handlers
  // ------------------------------------------------------------------

  const handleAddOverride = useCallback(async (data) => {
    setOverridesLoading(true);
    try {
      await availabilityAPI.addException(data);
      toast.success('Override added');
      await loadOverrides();
    } catch (err) {
      const detail = err.response?.data?.detail || 'Failed to add override';
      toast.error(detail);
    } finally {
      setOverridesLoading(false);
    }
  }, [loadOverrides]);

  const handleRemoveOverride = useCallback(async (id) => {
    setOverridesLoading(true);
    try {
      await availabilityAPI.removeException(id);
      toast.success('Override removed');
      await loadOverrides();
    } catch (err) {
      toast.error('Failed to remove override');
    } finally {
      setOverridesLoading(false);
    }
  }, [loadOverrides]);

  // ------------------------------------------------------------------
  // Visual preview computation
  // ------------------------------------------------------------------

  const previewData = useMemo(() => {
    // For each day, compute total hours and bar positions
    // Bar represents time on a 0-24 hour scale, mapped to bar height
    return DAY_LABELS.map((_, i) => {
      const day = schedule[i];
      if (!day.enabled || day.blocks.length === 0) {
        return { totalHours: 0, blocks: [] };
      }

      let totalMinutes = 0;
      const barBlocks = [];

      for (const block of day.blocks) {
        const [sh, sm] = block.start.split(':').map(Number);
        const [eh, em] = block.end.split(':').map(Number);
        const startMin = sh * 60 + sm;
        const endMin = eh * 60 + em;
        const duration = endMin - startMin;
        if (duration > 0) {
          totalMinutes += duration;
          // Map to percentage of 24-hour scale for bar positioning
          // Bar represents 6 AM to 10 PM (16 hours = 960 minutes) for better visualization
          const barStart = Math.max(0, startMin - 360); // offset from 6 AM
          const barEnd = Math.min(960, endMin - 360);
          barBlocks.push({
            topPct: (Math.max(0, barStart) / 960) * 100,
            heightPct: (Math.max(0, barEnd - Math.max(0, barStart)) / 960) * 100,
          });
        }
      }

      const totalHours = totalMinutes / 60;
      return { totalHours: Math.round(totalHours * 10) / 10, blocks: barBlocks };
    });
  }, [schedule]);

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------

  if (loading) {
    return (
      <div className="cal-settings-loading" role="status">
        <div className="spinner" />
        <p>Loading availability...</p>
      </div>
    );
  }

  return (
    <div>
      {/* Weekly Schedule Section */}
      <section className="cal-settings-section">
        <div className="section-header-row">
          <div>
            <h2>Weekly Schedule</h2>
            <p className="section-description">
              Set your recurring weekly availability. Clients can only book during these hours.
            </p>
          </div>
          <button
            onClick={handleSave}
            disabled={saving || !hasChanges}
            className="btn-primary"
          >
            {saving ? (
              <><i className="fas fa-spinner fa-spin" /> Saving...</>
            ) : (
              <><i className="fas fa-save" /> Save Schedule</>
            )}
          </button>
        </div>

        {/* Timezone selector */}
        <div className="avail-timezone-row">
          <label htmlFor="avail-tz">Timezone</label>
          <select
            id="avail-tz"
            value={timezone}
            onChange={handleTimezoneChange}
          >
            {COMMON_TIMEZONES.map((tz) => (
              <option key={tz.value} value={tz.value}>
                {tz.label}
              </option>
            ))}
          </select>
        </div>

        {/* Day rows */}
        <div className="availability-grid">
          {DAY_LABELS.map((label, i) => (
            <AvailabilityDayRow
              key={i}
              dayIndex={i}
              dayLabel={label}
              enabled={schedule[i].enabled}
              blocks={schedule[i].blocks}
              onToggle={handleToggleDay}
              onBlockChange={handleBlockChange}
              onAddBlock={handleAddBlock}
              onRemoveBlock={handleRemoveBlock}
            />
          ))}
        </div>

        {/* Visual Preview */}
        <div className="avail-preview-section">
          <h3>Weekly Overview</h3>
          <div className="avail-preview-grid">
            {DAY_ABBREV.map((abbr, i) => (
              <div key={i} className="avail-preview-day">
                <span className="avail-preview-day-label">{abbr}</span>
                <div className="avail-preview-bar-track">
                  {previewData[i].blocks.map((block, j) => (
                    <div
                      key={j}
                      className="avail-preview-bar-fill"
                      style={{
                        top: `${block.topPct}%`,
                        height: `${Math.max(block.heightPct, 2)}%`,
                      }}
                      title={schedule[i].blocks[j]
                        ? `${schedule[i].blocks[j].start} - ${schedule[i].blocks[j].end}`
                        : ''}
                    />
                  ))}
                </div>
                <span className="avail-preview-hours">
                  {previewData[i].totalHours > 0 ? `${previewData[i].totalHours}h` : '--'}
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Date Overrides Section */}
      <section className="cal-settings-section">
        <h2>Date Overrides</h2>
        <p className="section-description">
          Override your regular schedule for specific dates. Use this for vacation days, holidays, or special hours.
        </p>
        <AvailabilityOverrides
          overrides={overrides}
          onAddOverride={handleAddOverride}
          onRemoveOverride={handleRemoveOverride}
          loading={overridesLoading}
        />
      </section>
    </div>
  );
}

export default AvailabilityPreferences;
