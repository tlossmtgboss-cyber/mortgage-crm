/**
 * Perennia AI - Smart Calendar Setup: Step 2 - Working Hours
 *
 * Second step of the guided calendar setup flow:
 *   - Weekly schedule editor with per-day enable/disable and time blocks
 *   - Quick presets (Standard 9-5, Extended, Weekdays Only, Custom)
 *   - Lunch break toggle that auto-splits day blocks
 *   - Buffer time before/after appointments
 *   - Daily appointment cap with info tooltip
 *   - Visual week preview bar chart
 *   - Copy schedule utility (Copy Monday to all weekdays)
 *   - Total hours/week summary
 *
 * Props (wizard integration):
 *   stepData, onChange, allStepData
 */

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import './WorkingHoursStep.css';

// ============================================================================
// Constants
// ============================================================================

const DAYS_OF_WEEK = [
  { key: 'monday', label: 'Monday', short: 'Mon' },
  { key: 'tuesday', label: 'Tuesday', short: 'Tue' },
  { key: 'wednesday', label: 'Wednesday', short: 'Wed' },
  { key: 'thursday', label: 'Thursday', short: 'Thu' },
  { key: 'friday', label: 'Friday', short: 'Fri' },
  { key: 'saturday', label: 'Saturday', short: 'Sat' },
  { key: 'sunday', label: 'Sunday', short: 'Sun' },
];

const BUFFER_OPTIONS = [
  { value: 0, label: 'No buffer' },
  { value: 5, label: '5 minutes' },
  { value: 10, label: '10 minutes' },
  { value: 15, label: '15 minutes' },
  { value: 30, label: '30 minutes' },
];

/**
 * Build time slots from 00:00 to 23:45 in 15-minute increments.
 */
function buildTimeSlots() {
  const slots = [];
  for (let h = 0; h < 24; h++) {
    for (let m = 0; m < 60; m += 15) {
      const value = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
      const hour12 = h === 0 ? 12 : h > 12 ? h - 12 : h;
      const ampm = h < 12 ? 'AM' : 'PM';
      const label = `${hour12}:${String(m).padStart(2, '0')} ${ampm}`;
      slots.push({ value, label });
    }
  }
  return slots;
}

const TIME_SLOTS = buildTimeSlots();

/**
 * Default schedule block.
 */
function defaultBlock(start = '09:00', end = '17:00') {
  return { start, end };
}

/**
 * Build default day schedule.
 */
function defaultDay(enabled = true, blocks = null) {
  return {
    enabled,
    blocks: blocks || [defaultBlock()],
  };
}

/**
 * Build a full default week schedule (Mon-Fri enabled, Sat-Sun disabled).
 */
function buildDefaultSchedule() {
  const schedule = {};
  DAYS_OF_WEEK.forEach(day => {
    const isWeekday = !['saturday', 'sunday'].includes(day.key);
    schedule[day.key] = defaultDay(isWeekday);
  });
  return schedule;
}

const PRESET_CONFIGS = [
  {
    id: 'standard',
    label: 'Standard 9-5',
    icon: 'fa-briefcase',
    description: 'Mon-Fri, 9:00 AM - 5:00 PM',
    build: () => {
      const s = {};
      DAYS_OF_WEEK.forEach(d => {
        const isWeekday = !['saturday', 'sunday'].includes(d.key);
        s[d.key] = defaultDay(isWeekday, [defaultBlock('09:00', '17:00')]);
      });
      return s;
    },
  },
  {
    id: 'extended',
    label: 'Extended Hours',
    icon: 'fa-clock',
    description: 'Mon-Fri, 8:00 AM - 7:00 PM',
    build: () => {
      const s = {};
      DAYS_OF_WEEK.forEach(d => {
        const isWeekday = !['saturday', 'sunday'].includes(d.key);
        s[d.key] = defaultDay(isWeekday, [defaultBlock('08:00', '19:00')]);
      });
      return s;
    },
  },
  {
    id: 'weekdays_only',
    label: 'Weekdays Only',
    icon: 'fa-calendar-week',
    description: 'Mon-Fri, 9:00 AM - 6:00 PM',
    build: () => {
      const s = {};
      DAYS_OF_WEEK.forEach(d => {
        const isWeekday = !['saturday', 'sunday'].includes(d.key);
        s[d.key] = defaultDay(isWeekday, [defaultBlock('09:00', '18:00')]);
      });
      return s;
    },
  },
  {
    id: 'custom',
    label: 'Custom',
    icon: 'fa-sliders-h',
    description: 'Build your own schedule',
    build: null,
  },
];

// ============================================================================
// Helpers
// ============================================================================

/**
 * Parse "HH:MM" to total minutes since midnight.
 */
function timeToMinutes(time) {
  if (!time) return 0;
  const [h, m] = time.split(':').map(Number);
  return h * 60 + m;
}

/**
 * Calculate total available hours per week from schedule.
 */
function calcTotalHours(schedule) {
  let totalMinutes = 0;
  DAYS_OF_WEEK.forEach(day => {
    const dayData = schedule[day.key];
    if (!dayData || !dayData.enabled) return;
    (dayData.blocks || []).forEach(block => {
      const diff = timeToMinutes(block.end) - timeToMinutes(block.start);
      if (diff > 0) totalMinutes += diff;
    });
  });
  return totalMinutes / 60;
}

/**
 * Calculate available hours for a single day.
 */
function calcDayHours(dayData) {
  if (!dayData || !dayData.enabled) return 0;
  let totalMinutes = 0;
  (dayData.blocks || []).forEach(block => {
    const diff = timeToMinutes(block.end) - timeToMinutes(block.start);
    if (diff > 0) totalMinutes += diff;
  });
  return totalMinutes / 60;
}

/**
 * Format a number as "X.X" or "X" hours.
 */
function formatHours(hours) {
  if (hours === 0) return '0';
  if (hours === Math.floor(hours)) return String(Math.floor(hours));
  return hours.toFixed(1);
}

// ============================================================================
// Sub-components
// ============================================================================

/**
 * A single time block row within a day.
 */
function TimeBlockRow({ block, index, totalBlocks, onChange, onRemove }) {
  return (
    <div className="working-hours-step__time-block">
      <div className="working-hours-step__time-select-group">
        <select
          value={block.start}
          onChange={(e) => onChange(index, 'start', e.target.value)}
          aria-label={`Start time for block ${index + 1}`}
          className="working-hours-step__time-select"
        >
          {TIME_SLOTS.map(slot => (
            <option key={slot.value} value={slot.value}>{slot.label}</option>
          ))}
        </select>
        <span className="working-hours-step__time-separator">to</span>
        <select
          value={block.end}
          onChange={(e) => onChange(index, 'end', e.target.value)}
          aria-label={`End time for block ${index + 1}`}
          className="working-hours-step__time-select"
        >
          {TIME_SLOTS.map(slot => (
            <option key={slot.value} value={slot.value}>{slot.label}</option>
          ))}
        </select>
      </div>
      {totalBlocks > 1 && (
        <button
          type="button"
          className="working-hours-step__remove-block"
          onClick={() => onRemove(index)}
          aria-label={`Remove time block ${index + 1}`}
          title="Remove block"
        >
          <i className="fas fa-times" aria-hidden="true" />
        </button>
      )}
    </div>
  );
}

/**
 * A single day row in the weekly schedule editor.
 */
function DayRow({ dayKey, dayLabel, dayShort, dayData, onToggle, onBlockChange, onBlockRemove, onBlockAdd }) {
  const hours = calcDayHours(dayData);

  return (
    <div className={`working-hours-step__day-row ${dayData.enabled ? '' : 'working-hours-step__day-row--disabled'}`}>
      <div className="working-hours-step__day-header">
        <label className="working-hours-step__day-toggle">
          <input
            type="checkbox"
            checked={dayData.enabled}
            onChange={() => onToggle(dayKey)}
            aria-label={`${dayData.enabled ? 'Disable' : 'Enable'} ${dayLabel}`}
          />
          <span className="working-hours-step__toggle-track" />
        </label>
        <span className="working-hours-step__day-label">
          <span className="working-hours-step__day-label-full">{dayLabel}</span>
          <span className="working-hours-step__day-label-short" aria-hidden="true">{dayShort}</span>
        </span>
        {dayData.enabled && hours > 0 && (
          <span className="working-hours-step__day-hours">{formatHours(hours)}h</span>
        )}
      </div>

      {dayData.enabled && (
        <div className="working-hours-step__day-blocks">
          {dayData.blocks.map((block, idx) => (
            <TimeBlockRow
              key={idx}
              block={block}
              index={idx}
              totalBlocks={dayData.blocks.length}
              onChange={(blockIdx, field, value) => onBlockChange(dayKey, blockIdx, field, value)}
              onRemove={(blockIdx) => onBlockRemove(dayKey, blockIdx)}
            />
          ))}
          <button
            type="button"
            className="working-hours-step__add-block"
            onClick={() => onBlockAdd(dayKey)}
            aria-label={`Add time block for ${dayLabel}`}
          >
            <i className="fas fa-plus" aria-hidden="true" /> Add block
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * Visual week preview showing colored bars for each day.
 */
function WeekPreview({ schedule }) {
  // Find the maximum hours in a day for scaling
  const maxHours = Math.max(
    ...DAYS_OF_WEEK.map(d => calcDayHours(schedule[d.key])),
    1
  );

  return (
    <div className="working-hours-step__preview" role="figure" aria-label="Weekly hours preview">
      <h3 className="working-hours-step__preview-title">
        <i className="fas fa-chart-bar" aria-hidden="true" /> Weekly Preview
      </h3>
      <div className="working-hours-step__preview-chart">
        {DAYS_OF_WEEK.map(day => {
          const dayData = schedule[day.key];
          const hours = calcDayHours(dayData);
          const pct = maxHours > 0 ? (hours / maxHours) * 100 : 0;

          return (
            <div key={day.key} className="working-hours-step__preview-bar-group">
              <span className="working-hours-step__preview-day">{day.short}</span>
              <div className="working-hours-step__preview-bar-track">
                {dayData.enabled && dayData.blocks.map((block, idx) => {
                  const blockMinutes = timeToMinutes(block.end) - timeToMinutes(block.start);
                  const blockPct = maxHours > 0 ? ((blockMinutes / 60) / maxHours) * 100 : 0;
                  return (
                    <div
                      key={idx}
                      className="working-hours-step__preview-bar-fill"
                      style={{ width: `${Math.max(blockPct, 0)}%` }}
                      title={`${block.start} - ${block.end}`}
                    />
                  );
                })}
                {!dayData.enabled && (
                  <div className="working-hours-step__preview-bar-off" />
                )}
              </div>
              <span className="working-hours-step__preview-hours">
                {dayData.enabled ? `${formatHours(hours)}h` : 'Off'}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/**
 * Info tooltip component for the daily cap.
 */
function InfoTooltip({ text }) {
  const [visible, setVisible] = useState(false);
  const tooltipRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(e) {
      if (tooltipRef.current && !tooltipRef.current.contains(e.target)) {
        setVisible(false);
      }
    }
    if (visible) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [visible]);

  return (
    <span className="working-hours-step__tooltip-wrapper" ref={tooltipRef}>
      <button
        type="button"
        className="working-hours-step__tooltip-trigger"
        onClick={() => setVisible(prev => !prev)}
        aria-label="More information"
        aria-expanded={visible}
      >
        <i className="fas fa-info-circle" aria-hidden="true" />
      </button>
      {visible && (
        <div className="working-hours-step__tooltip-content" role="tooltip">
          {text}
        </div>
      )}
    </span>
  );
}

// ============================================================================
// Main component
// ============================================================================

export default function WorkingHoursStep({ stepData = {}, onChange, allStepData }) {
  // Initialize state from stepData (for resume support) or defaults
  const [schedule, setSchedule] = useState(() => {
    if (stepData.schedule) return stepData.schedule;

    // Check if WelcomeStep set a preset
    const welcomeData = allStepData?.welcome;
    if (welcomeData?.schedulePreset && welcomeData.schedulePreset !== 'custom' && welcomeData.workingHours) {
      // Build schedule from the welcome preset
      const s = {};
      DAYS_OF_WEEK.forEach(d => {
        const isWeekday = !['saturday', 'sunday'].includes(d.key);
        s[d.key] = defaultDay(isWeekday, [
          defaultBlock(welcomeData.workingHours.start, welcomeData.workingHours.end),
        ]);
      });
      return s;
    }

    return buildDefaultSchedule();
  });

  const [activePreset, setActivePreset] = useState(stepData.activePreset || 'custom');
  const [timeBlocks, setTimeBlocks] = useState(stepData.timeBlocks || []);
  const [bufferBefore, setBufferBefore] = useState(stepData.bufferBefore ?? 0);
  const [bufferAfter, setBufferAfter] = useState(stepData.bufferAfter ?? 0);
  const [dailyCap, setDailyCap] = useState(stepData.dailyCap ?? 0);

  // Calculate summary
  const totalHours = useMemo(() => calcTotalHours(schedule), [schedule]);

  // Notify parent of data changes
  useEffect(() => {
    if (onChange) {
      onChange({
        schedule,
        activePreset,
        timeBlocks,
        bufferBefore,
        bufferAfter,
        dailyCap,
        totalHoursPerWeek: totalHours,
      });
    }
  }, [schedule, activePreset, timeBlocks, bufferBefore, bufferAfter, dailyCap, totalHours, onChange]);

  // ------------------------------------------------------------------
  // Day toggle
  // ------------------------------------------------------------------
  const handleDayToggle = useCallback((dayKey) => {
    setSchedule(prev => ({
      ...prev,
      [dayKey]: {
        ...prev[dayKey],
        enabled: !prev[dayKey].enabled,
      },
    }));
    setActivePreset('custom');
  }, []);

  // ------------------------------------------------------------------
  // Block time changes
  // ------------------------------------------------------------------
  const handleBlockChange = useCallback((dayKey, blockIdx, field, value) => {
    setSchedule(prev => {
      const newBlocks = [...prev[dayKey].blocks];
      newBlocks[blockIdx] = { ...newBlocks[blockIdx], [field]: value };
      return {
        ...prev,
        [dayKey]: { ...prev[dayKey], blocks: newBlocks },
      };
    });
    setActivePreset('custom');
  }, []);

  // ------------------------------------------------------------------
  // Remove a block
  // ------------------------------------------------------------------
  const handleBlockRemove = useCallback((dayKey, blockIdx) => {
    setSchedule(prev => {
      const newBlocks = prev[dayKey].blocks.filter((_, i) => i !== blockIdx);
      return {
        ...prev,
        [dayKey]: { ...prev[dayKey], blocks: newBlocks.length ? newBlocks : [defaultBlock()] },
      };
    });
    setActivePreset('custom');
  }, []);

  // ------------------------------------------------------------------
  // Add a block
  // ------------------------------------------------------------------
  const handleBlockAdd = useCallback((dayKey) => {
    setSchedule(prev => {
      const existing = prev[dayKey].blocks;
      const lastBlock = existing[existing.length - 1];
      const lastEndMin = timeToMinutes(lastBlock.end);
      // Start new block 1 hour after last block ends, or at 13:00 if that's past end of day
      const newStartMin = Math.min(lastEndMin + 60, 23 * 60);
      const newEndMin = Math.min(newStartMin + 120, 24 * 60 - 15);
      const newStart = `${String(Math.floor(newStartMin / 60)).padStart(2, '0')}:${String(newStartMin % 60).padStart(2, '0')}`;
      const newEnd = `${String(Math.floor(newEndMin / 60)).padStart(2, '0')}:${String(newEndMin % 60).padStart(2, '0')}`;
      return {
        ...prev,
        [dayKey]: {
          ...prev[dayKey],
          blocks: [...existing, defaultBlock(newStart, newEnd)],
        },
      };
    });
    setActivePreset('custom');
  }, []);

  // ------------------------------------------------------------------
  // Preset selection
  // ------------------------------------------------------------------
  const handlePresetSelect = useCallback((preset) => {
    setActivePreset(preset.id);
    if (preset.build) {
      setSchedule(preset.build());
      setLunchBreakEnabled(false);
    }
  }, []);

  // ------------------------------------------------------------------
  // Time block handlers
  // ------------------------------------------------------------------
  const addTimeBlock = useCallback(() => {
    setTimeBlocks(prev => [
      ...prev,
      {
        id: Date.now().toString(),
        label: '',
        start: '12:00',
        end: '13:00',
        days: ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'],
        enabled: true,
      },
    ]);
    setActivePreset('custom');
  }, []);

  const updateTimeBlock = useCallback((id, field, value) => {
    setTimeBlocks(prev => prev.map(b => b.id === id ? { ...b, [field]: value } : b));
  }, []);

  const removeTimeBlock = useCallback((id) => {
    setTimeBlocks(prev => prev.filter(b => b.id !== id));
  }, []);

  // ------------------------------------------------------------------
  // Copy Monday to all weekdays
  // ------------------------------------------------------------------
  const handleCopyMonday = useCallback(() => {
    setSchedule(prev => {
      const mondayData = prev.monday;
      const updated = { ...prev };
      ['tuesday', 'wednesday', 'thursday', 'friday'].forEach(dayKey => {
        updated[dayKey] = {
          enabled: mondayData.enabled,
          blocks: mondayData.blocks.map(b => ({ ...b })),
        };
      });
      return updated;
    });
    setActivePreset('custom');
  }, []);

  // ------------------------------------------------------------------
  // Preset keyboard handler
  // ------------------------------------------------------------------
  const handlePresetKeyDown = useCallback((e, preset) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handlePresetSelect(preset);
    }
  }, [handlePresetSelect]);

  // ============================================================================
  // Render
  // ============================================================================

  return (
    <div className="working-hours-step">
      {/* Header */}
      <div className="working-hours-step__intro">
        <h2>Set Your Working Hours</h2>
        <p>
          Define when you are available for appointments each day. You can set
          multiple time blocks per day for split schedules.
        </p>
      </div>

      {/* Quick presets */}
      <section className="working-hours-step__presets" aria-label="Schedule presets">
        <h3 className="working-hours-step__section-title">Quick Presets</h3>
        <div className="working-hours-step__preset-grid" role="radiogroup" aria-label="Schedule presets">
          {PRESET_CONFIGS.map(preset => (
            <div
              key={preset.id}
              className={`working-hours-step__preset-card ${activePreset === preset.id ? 'working-hours-step__preset-card--selected' : ''}`}
              onClick={() => handlePresetSelect(preset)}
              onKeyDown={(e) => handlePresetKeyDown(e, preset)}
              role="radio"
              aria-checked={activePreset === preset.id}
              tabIndex={0}
            >
              <div className="working-hours-step__preset-icon">
                <i className={`fas ${preset.icon}`} aria-hidden="true" />
              </div>
              <div className="working-hours-step__preset-text">
                <span className="working-hours-step__preset-label">{preset.label}</span>
                <span className="working-hours-step__preset-desc">{preset.description}</span>
              </div>
              {activePreset === preset.id && (
                <div className="working-hours-step__preset-check" aria-hidden="true">
                  <i className="fas fa-check-circle" />
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Weekly schedule editor */}
      <section className="working-hours-step__schedule" aria-label="Weekly schedule">
        <div className="working-hours-step__schedule-header">
          <h3 className="working-hours-step__section-title">Weekly Schedule</h3>
          <button
            type="button"
            className="working-hours-step__copy-btn"
            onClick={handleCopyMonday}
            title="Copy Monday's schedule to Tuesday through Friday"
          >
            <i className="fas fa-copy" aria-hidden="true" /> Copy Mon to weekdays
          </button>
        </div>

        <div className="working-hours-step__day-list">
          {DAYS_OF_WEEK.map(day => (
            <DayRow
              key={day.key}
              dayKey={day.key}
              dayLabel={day.label}
              dayShort={day.short}
              dayData={schedule[day.key]}
              onToggle={handleDayToggle}
              onBlockChange={handleBlockChange}
              onBlockRemove={handleBlockRemove}
              onBlockAdd={handleBlockAdd}
            />
          ))}
        </div>
      </section>

      {/* Time Blocks */}
      <section className="working-hours-step__lunch" aria-label="Time block settings">
        <div className="working-hours-step__lunch-header">
          <div className="working-hours-step__lunch-label-group">
            <i className="fas fa-clock working-hours-step__lunch-icon" aria-hidden="true" />
            <div>
              <h3 className="working-hours-step__section-title" style={{ margin: 0 }}>Time Blocks</h3>
              <p className="working-hours-step__section-subtitle">
                Block off recurring time for tasks and activities on your calendar
              </p>
            </div>
          </div>
        </div>
        <div style={{ marginTop: 12 }}>
          {timeBlocks.map(block => (
            <div key={block.id} style={{
              display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10,
              padding: '10px 14px', background: 'var(--cal-bg-secondary, #f8fafc)',
              borderRadius: 8, border: '1px solid var(--cal-border, #e2e8f0)',
            }}>
              <input
                type="checkbox"
                checked={block.enabled}
                onChange={e => updateTimeBlock(block.id, 'enabled', e.target.checked)}
                style={{ width: 18, height: 18, accentColor: 'var(--cal-primary, #8A6D30)' }}
              />
              <input
                type="text"
                value={block.label}
                onChange={e => updateTimeBlock(block.id, 'label', e.target.value)}
                placeholder="Activity (e.g., Pipeline Review, Follow-ups)"
                style={{
                  flex: 1, padding: '6px 10px', border: '1px solid var(--cal-border, #e2e8f0)',
                  borderRadius: 6, fontSize: 14, minWidth: 0,
                }}
              />
              <select
                value={block.start}
                onChange={e => updateTimeBlock(block.id, 'start', e.target.value)}
                className="working-hours-step__time-select"
                disabled={!block.enabled}
              >
                {TIME_SLOTS.map(slot => (
                  <option key={slot.value} value={slot.value}>{slot.label}</option>
                ))}
              </select>
              <span className="working-hours-step__time-separator">to</span>
              <select
                value={block.end}
                onChange={e => updateTimeBlock(block.id, 'end', e.target.value)}
                className="working-hours-step__time-select"
                disabled={!block.enabled}
              >
                {TIME_SLOTS.map(slot => (
                  <option key={slot.value} value={slot.value}>{slot.label}</option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => removeTimeBlock(block.id)}
                style={{
                  background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer',
                  padding: 4, fontSize: 16, lineHeight: 1,
                }}
                title="Remove time block"
              >
                <i className="fas fa-times" />
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={addTimeBlock}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '8px 16px', background: 'var(--cal-bg-secondary, #f8fafc)',
              border: '1px dashed var(--cal-border, #cbd5e1)', borderRadius: 8,
              color: 'var(--cal-primary, #8A6D30)', cursor: 'pointer', fontSize: 14,
            }}
          >
            <i className="fas fa-plus" /> Add Time Block
          </button>
        </div>
      </section>

      {/* Buffer time and daily cap */}
      <section className="working-hours-step__settings" aria-label="Additional settings">
        <div className="working-hours-step__settings-grid">
          {/* Buffer before */}
          <div className="working-hours-step__setting-field">
            <label className="working-hours-step__setting-label">
              <i className="fas fa-hourglass-start" aria-hidden="true" />
              Buffer before appointments
            </label>
            <select
              value={bufferBefore}
              onChange={(e) => setBufferBefore(Number(e.target.value))}
              className="working-hours-step__setting-select"
              aria-label="Buffer time before appointments"
            >
              {BUFFER_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          {/* Buffer after */}
          <div className="working-hours-step__setting-field">
            <label className="working-hours-step__setting-label">
              <i className="fas fa-hourglass-end" aria-hidden="true" />
              Buffer after appointments
            </label>
            <select
              value={bufferAfter}
              onChange={(e) => setBufferAfter(Number(e.target.value))}
              className="working-hours-step__setting-select"
              aria-label="Buffer time after appointments"
            >
              {BUFFER_OPTIONS.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          {/* Daily appointment cap */}
          <div className="working-hours-step__setting-field">
            <label className="working-hours-step__setting-label">
              <i className="fas fa-hashtag" aria-hidden="true" />
              Daily appointment cap
              <InfoTooltip text="Set the maximum number of appointments you want to take per day. Leave at 0 for no limit. This helps prevent overbooking and ensures you have time for loan processing between meetings." />
            </label>
            <input
              type="number"
              min={0}
              max={50}
              value={dailyCap}
              onChange={(e) => setDailyCap(Math.max(0, Math.min(50, parseInt(e.target.value, 10) || 0)))}
              className="working-hours-step__setting-input"
              aria-label="Maximum appointments per day"
              placeholder="0 = no limit"
            />
            <span className="working-hours-step__setting-hint">
              {dailyCap === 0 ? 'No limit' : `Max ${dailyCap} per day`}
            </span>
          </div>
        </div>
      </section>

      {/* Visual week preview */}
      <WeekPreview schedule={schedule} />

      {/* Total hours summary */}
      <div className="working-hours-step__summary" role="status" aria-live="polite">
        <div className="working-hours-step__summary-icon">
          <i className="fas fa-calculator" aria-hidden="true" />
        </div>
        <div className="working-hours-step__summary-text">
          <span className="working-hours-step__summary-number">{formatHours(totalHours)}</span>
          <span className="working-hours-step__summary-label">hours/week available</span>
        </div>
        {bufferBefore > 0 || bufferAfter > 0 ? (
          <div className="working-hours-step__summary-buffer">
            <i className="fas fa-shield-alt" aria-hidden="true" />
            {bufferBefore > 0 && `${bufferBefore}min before`}
            {bufferBefore > 0 && bufferAfter > 0 && ' / '}
            {bufferAfter > 0 && `${bufferAfter}min after`}
            {' '}each appointment
          </div>
        ) : null}
      </div>
    </div>
  );
}
