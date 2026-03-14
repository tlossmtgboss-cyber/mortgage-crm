/**
 * AvailabilitySection - Calendar Settings
 *
 * Handles weekly hours overview, schedule templates, holidays/blocked dates,
 * seasonal hours, override days, and booking window settings.
 */
import React, { useState, useCallback, useMemo } from 'react';
import AvailabilityPreferences from '../../components/calendar/AvailabilityPreferences';
import { toast } from '../../utils/toast';

const DAYS_OF_WEEK = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
const DAY_LABELS = {
  monday: 'Monday', tuesday: 'Tuesday', wednesday: 'Wednesday',
  thursday: 'Thursday', friday: 'Friday', saturday: 'Saturday', sunday: 'Sunday',
};

const SCHEDULE_TEMPLATES = [
  {
    id: 'standard-9-5',
    label: 'Standard 9-5 M-F',
    icon: 'fa-briefcase',
    hours: { monday: { start: '09:00', end: '17:00', enabled: true }, tuesday: { start: '09:00', end: '17:00', enabled: true }, wednesday: { start: '09:00', end: '17:00', enabled: true }, thursday: { start: '09:00', end: '17:00', enabled: true }, friday: { start: '09:00', end: '17:00', enabled: true }, saturday: { start: '10:00', end: '14:00', enabled: false }, sunday: { start: '10:00', end: '14:00', enabled: false } },
  },
  {
    id: 'extended-8-7',
    label: 'Extended 8-7 M-F',
    icon: 'fa-clock',
    hours: { monday: { start: '08:00', end: '19:00', enabled: true }, tuesday: { start: '08:00', end: '19:00', enabled: true }, wednesday: { start: '08:00', end: '19:00', enabled: true }, thursday: { start: '08:00', end: '19:00', enabled: true }, friday: { start: '08:00', end: '19:00', enabled: true }, saturday: { start: '10:00', end: '14:00', enabled: false }, sunday: { start: '10:00', end: '14:00', enabled: false } },
  },
  {
    id: 'weekend-available',
    label: 'Weekend Available',
    icon: 'fa-calendar-week',
    hours: { monday: { start: '09:00', end: '17:00', enabled: true }, tuesday: { start: '09:00', end: '17:00', enabled: true }, wednesday: { start: '09:00', end: '17:00', enabled: true }, thursday: { start: '09:00', end: '17:00', enabled: true }, friday: { start: '09:00', end: '17:00', enabled: true }, saturday: { start: '09:00', end: '15:00', enabled: true }, sunday: { start: '10:00', end: '14:00', enabled: true } },
  },
  {
    id: 'part-time',
    label: 'Part-time',
    icon: 'fa-hourglass-half',
    hours: { monday: { start: '09:00', end: '13:00', enabled: true }, tuesday: { start: '09:00', end: '13:00', enabled: true }, wednesday: { start: '09:00', end: '13:00', enabled: true }, thursday: { start: '09:00', end: '13:00', enabled: true }, friday: { start: '09:00', end: '13:00', enabled: true }, saturday: { start: '10:00', end: '14:00', enabled: false }, sunday: { start: '10:00', end: '14:00', enabled: false } },
  },
];

const COMMON_HOLIDAYS = [
  { name: "New Year's Day", date: `${new Date().getFullYear()}-01-01` },
  { name: 'MLK Day', date: `${new Date().getFullYear()}-01-20` },
  { name: 'Memorial Day', date: `${new Date().getFullYear()}-05-26` },
  { name: 'Independence Day', date: `${new Date().getFullYear()}-07-04` },
  { name: 'Labor Day', date: `${new Date().getFullYear()}-09-01` },
  { name: 'Thanksgiving', date: `${new Date().getFullYear()}-11-27` },
  { name: 'Christmas', date: `${new Date().getFullYear()}-12-25` },
];

export default function AvailabilitySection({
  availability,
  setAvailability,
  seasonalHours,
  setSeasonalHours,
  overrideDays,
  setOverrideDays,
  expandedSections,
  toggleExpandedSection,
  markChanged,
}) {
  // ---- Local form state ----
  const [newBlockedRange, setNewBlockedRange] = useState({
    start_date: '', end_date: '', reason: '',
  });
  const [newSeason, setNewSeason] = useState({
    name: '', start_date: '', end_date: '', hours: { start: '09:00', end: '17:00' }, active: true,
  });
  const [newOverride, setNewOverride] = useState({
    date: '', start: '09:00', end: '17:00', enabled: true, copy_from: '',
  });

  // ---- Computed data ----
  const calcDayHours = useCallback((dayConfig) => {
    if (!dayConfig || !dayConfig.enabled) return 0;
    const [startH, startM] = (dayConfig.start || '09:00').split(':').map(Number);
    const [endH, endM] = (dayConfig.end || '17:00').split(':').map(Number);
    const hours = (endH + endM / 60) - (startH + startM / 60);
    return Math.max(0, hours);
  }, []);

  const weekOverviewData = useMemo(() => {
    const bh = availability.business_hours;
    const days = DAYS_OF_WEEK.map(day => ({
      day,
      label: DAY_LABELS[day],
      hours: calcDayHours(bh[day]),
      enabled: bh[day]?.enabled || false,
    }));
    const totalHours = days.reduce((sum, d) => sum + d.hours, 0);
    const maxHours = Math.max(...days.map(d => d.hours), 1);
    return { days, totalHours, maxHours };
  }, [availability.business_hours, calcDayHours]);

  // ---- Handlers ----
  const applyScheduleTemplate = useCallback((template) => {
    setAvailability(prev => ({
      ...prev,
      business_hours: { ...template.hours },
    }));
    markChanged();
    toast.success(`Applied "${template.label}" schedule`);
  }, [setAvailability, markChanged]);

  const addBlockedDateRange = useCallback(() => {
    if (!newBlockedRange.start_date || !newBlockedRange.end_date) {
      toast.error('Please select both start and end dates');
      return;
    }
    if (newBlockedRange.start_date > newBlockedRange.end_date) {
      toast.error('End date must be after start date');
      return;
    }
    setAvailability(prev => ({
      ...prev,
      custom_blocked_dates: [
        ...(prev.custom_blocked_dates || []),
        {
          id: Date.now().toString(),
          start_date: newBlockedRange.start_date,
          end_date: newBlockedRange.end_date,
          reason: newBlockedRange.reason || 'Blocked',
        },
      ],
    }));
    setNewBlockedRange({ start_date: '', end_date: '', reason: '' });
    markChanged();
  }, [newBlockedRange, setAvailability, markChanged]);

  const removeBlockedDateRange = useCallback((id) => {
    setAvailability(prev => ({
      ...prev,
      custom_blocked_dates: (prev.custom_blocked_dates || []).filter(d => d.id !== id),
    }));
    markChanged();
  }, [setAvailability, markChanged]);

  const addHolidayBlock = useCallback((holiday) => {
    const existing = (availability.custom_blocked_dates || []).find(
      d => d.start_date === holiday.date && d.end_date === holiday.date
    );
    if (existing) {
      toast.info(`${holiday.name} is already blocked`);
      return;
    }
    setAvailability(prev => ({
      ...prev,
      custom_blocked_dates: [
        ...(prev.custom_blocked_dates || []),
        {
          id: Date.now().toString(),
          start_date: holiday.date,
          end_date: holiday.date,
          reason: holiday.name,
        },
      ],
    }));
    markChanged();
    toast.success(`Blocked ${holiday.name}`);
  }, [availability.custom_blocked_dates, setAvailability, markChanged]);

  const addSeasonalHours = useCallback(() => {
    if (!newSeason.name || !newSeason.start_date || !newSeason.end_date) {
      toast.error('Please fill in season name and date range');
      return;
    }
    setSeasonalHours(prev => [
      ...prev,
      { ...newSeason, id: Date.now().toString() },
    ]);
    setNewSeason({ name: '', start_date: '', end_date: '', hours: { start: '09:00', end: '17:00' }, active: true });
    markChanged();
  }, [newSeason, setSeasonalHours, markChanged]);

  const removeSeasonalHours = useCallback((id) => {
    setSeasonalHours(prev => prev.filter(s => s.id !== id));
    markChanged();
  }, [setSeasonalHours, markChanged]);

  const toggleSeasonActive = useCallback((id) => {
    setSeasonalHours(prev => prev.map(s => s.id === id ? { ...s, active: !s.active } : s));
    markChanged();
  }, [setSeasonalHours, markChanged]);

  const addOverrideDay = useCallback(() => {
    if (!newOverride.date) {
      toast.error('Please select a date');
      return;
    }
    const existing = overrideDays.find(o => o.date === newOverride.date);
    if (existing) {
      toast.error('An override already exists for that date');
      return;
    }
    setOverrideDays(prev => [
      ...prev,
      { ...newOverride, id: Date.now().toString() },
    ]);
    setNewOverride({ date: '', start: '09:00', end: '17:00', enabled: true, copy_from: '' });
    markChanged();
  }, [newOverride, overrideDays, setOverrideDays, markChanged]);

  const removeOverrideDay = useCallback((id) => {
    setOverrideDays(prev => prev.filter(o => o.id !== id));
    markChanged();
  }, [setOverrideDays, markChanged]);

  const copyFromDay = useCallback((day) => {
    const bh = availability.business_hours[day];
    if (bh) {
      setNewOverride(prev => ({
        ...prev,
        start: bh.start || '09:00',
        end: bh.end || '17:00',
        enabled: bh.enabled !== false,
        copy_from: day,
      }));
    }
  }, [availability.business_hours]);

  return (
    <div role="tabpanel" id="panel-availability" aria-labelledby="calnav-availability">

      {/* ---- Visual Week Overview ---- */}
      <section className="cal-settings-section avail-week-overview">
        <button
          type="button"
          className="collapsible-header"
          onClick={() => toggleExpandedSection('week-overview')}
          aria-expanded={expandedSections['week-overview']}
        >
          <div className="collapsible-header-left">
            <i className={`fas fa-chevron-${expandedSections['week-overview'] ? 'down' : 'right'} collapsible-chevron`}></i>
            <div>
              <h2>Weekly Hours Overview</h2>
              <p className="section-description">
                Visual summary of your available hours each day -- {weekOverviewData.totalHours.toFixed(1)} hours per week
              </p>
            </div>
          </div>
          <span className="week-total-badge">{weekOverviewData.totalHours.toFixed(1)}h / week</span>
        </button>
        {expandedSections['week-overview'] && (
          <div className="collapsible-body">
            <div className="week-bar-chart" role="img" aria-label={`Weekly hours: ${weekOverviewData.totalHours.toFixed(1)} total`}>
              {weekOverviewData.days.map(d => (
                <div key={d.day} className={`week-bar-row ${!d.enabled ? 'week-bar-disabled' : ''}`}>
                  <span className="week-bar-label">{d.label.substring(0, 3)}</span>
                  <div className="week-bar-track">
                    <div
                      className="week-bar-fill"
                      style={{ width: `${d.enabled ? (d.hours / weekOverviewData.maxHours) * 100 : 0}%` }}
                      title={`${d.hours.toFixed(1)} hours`}
                    />
                  </div>
                  <span className="week-bar-value">{d.enabled ? `${d.hours.toFixed(1)}h` : 'Off'}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* ---- Schedule Templates ---- */}
      <section className="cal-settings-section">
        <button
          type="button"
          className="collapsible-header"
          onClick={() => toggleExpandedSection('schedule-templates')}
          aria-expanded={expandedSections['schedule-templates']}
        >
          <div className="collapsible-header-left">
            <i className={`fas fa-chevron-${expandedSections['schedule-templates'] ? 'down' : 'right'} collapsible-chevron`}></i>
            <div>
              <h2>Schedule Templates</h2>
              <p className="section-description">Quick-apply a common schedule to all days at once.</p>
            </div>
          </div>
          <span className="collapsible-badge"><i className="fas fa-magic"></i></span>
        </button>
        {expandedSections['schedule-templates'] && (
          <div className="collapsible-body">
            <div className="schedule-template-grid">
              {SCHEDULE_TEMPLATES.map(tpl => (
                <button
                  key={tpl.id}
                  type="button"
                  className="schedule-template-btn"
                  onClick={() => applyScheduleTemplate(tpl)}
                >
                  <i className={`fas ${tpl.icon}`}></i>
                  <span className="schedule-template-label">{tpl.label}</span>
                  <span className="schedule-template-hint">
                    {DAYS_OF_WEEK.filter(day => tpl.hours[day]?.enabled).length} days,{' '}
                    {DAYS_OF_WEEK.reduce((sum, day) => sum + calcDayHours(tpl.hours[day]), 0).toFixed(0)}h/wk
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* Recurring weekly schedule + date overrides (self-contained save) */}
      <AvailabilityPreferences />

      {/* ---- Holidays / Blocked Dates ---- */}
      <section className="cal-settings-section">
        <button
          type="button"
          className="collapsible-header"
          onClick={() => toggleExpandedSection('holidays')}
          aria-expanded={expandedSections['holidays']}
        >
          <div className="collapsible-header-left">
            <i className={`fas fa-chevron-${expandedSections['holidays'] ? 'down' : 'right'} collapsible-chevron`}></i>
            <div>
              <h2>Holidays &amp; Blocked Dates</h2>
              <p className="section-description">
                Block off date ranges or common holidays when you are unavailable.
                {(availability.custom_blocked_dates || []).length > 0 && (
                  <span className="inline-count"> ({(availability.custom_blocked_dates || []).length} blocked)</span>
                )}
              </p>
            </div>
          </div>
          <span className="collapsible-badge"><i className="fas fa-calendar-times"></i></span>
        </button>
        {expandedSections['holidays'] && (
          <div className="collapsible-body">
            {/* Quick-add holidays */}
            <div className="holiday-quick-add">
              <h4 className="avail-subsection-title">Quick-Add Holidays</h4>
              <div className="holiday-chips">
                {COMMON_HOLIDAYS.map(h => {
                  const isBlocked = (availability.custom_blocked_dates || []).some(
                    d => d.start_date === h.date && d.end_date === h.date
                  );
                  return (
                    <button
                      key={h.name}
                      type="button"
                      className={`holiday-chip ${isBlocked ? 'holiday-chip-blocked' : ''}`}
                      onClick={() => addHolidayBlock(h)}
                      disabled={isBlocked}
                      title={isBlocked ? 'Already blocked' : `Block ${h.name} (${h.date})`}
                    >
                      <i className={`fas ${isBlocked ? 'fa-check' : 'fa-plus'}`}></i>
                      <span>{h.name}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Custom blocked date range */}
            <div className="blocked-date-form">
              <h4 className="avail-subsection-title">Add Blocked Date Range</h4>
              <div className="blocked-date-inputs">
                <div className="form-field">
                  <label>Start Date</label>
                  <input
                    type="date"
                    value={newBlockedRange.start_date}
                    onChange={(e) => setNewBlockedRange(prev => ({ ...prev, start_date: e.target.value }))}
                  />
                </div>
                <div className="form-field">
                  <label>End Date</label>
                  <input
                    type="date"
                    value={newBlockedRange.end_date}
                    onChange={(e) => setNewBlockedRange(prev => ({ ...prev, end_date: e.target.value }))}
                  />
                </div>
                <div className="form-field blocked-reason-field">
                  <label>Reason</label>
                  <input
                    type="text"
                    value={newBlockedRange.reason}
                    onChange={(e) => setNewBlockedRange(prev => ({ ...prev, reason: e.target.value }))}
                    placeholder="e.g., Vacation, Conference"
                  />
                </div>
                <button
                  type="button"
                  className="btn-primary btn-sm blocked-date-add-btn"
                  onClick={addBlockedDateRange}
                  disabled={!newBlockedRange.start_date || !newBlockedRange.end_date}
                >
                  <i className="fas fa-plus"></i> Add
                </button>
              </div>
            </div>

            {/* List of blocked dates */}
            {(availability.custom_blocked_dates || []).length > 0 && (
              <div className="blocked-dates-list">
                <h4 className="avail-subsection-title">Blocked Dates</h4>
                {(availability.custom_blocked_dates || []).map(bd => (
                  <div key={bd.id} className="blocked-date-item">
                    <div className="blocked-date-info">
                      <i className="fas fa-ban"></i>
                      <div>
                        <span className="blocked-date-range">
                          {bd.start_date === bd.end_date
                            ? new Date(bd.start_date + 'T12:00:00').toLocaleDateString()
                            : `${new Date(bd.start_date + 'T12:00:00').toLocaleDateString()} - ${new Date(bd.end_date + 'T12:00:00').toLocaleDateString()}`
                          }
                        </span>
                        {bd.reason && <span className="blocked-date-reason">{bd.reason}</span>}
                      </div>
                    </div>
                    <button
                      type="button"
                      className="icon-btn danger"
                      onClick={() => removeBlockedDateRange(bd.id)}
                      title="Remove blocked date"
                      aria-label="Remove blocked date"
                    >
                      <i className="fas fa-times"></i>
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </section>

      {/* ---- Seasonal Hours ---- */}
      <section className="cal-settings-section">
        <button
          type="button"
          className="collapsible-header"
          onClick={() => toggleExpandedSection('seasonal-hours')}
          aria-expanded={expandedSections['seasonal-hours']}
        >
          <div className="collapsible-header-left">
            <i className={`fas fa-chevron-${expandedSections['seasonal-hours'] ? 'down' : 'right'} collapsible-chevron`}></i>
            <div>
              <h2>Seasonal Hours</h2>
              <p className="section-description">Set different hours for specific date ranges (e.g., summer hours, holiday season).</p>
            </div>
          </div>
          <span className="collapsible-badge"><i className="fas fa-sun"></i></span>
        </button>
        {expandedSections['seasonal-hours'] && (
          <div className="collapsible-body">
            {/* Add new season form */}
            <div className="seasonal-form">
              <div className="seasonal-form-row">
                <div className="form-field">
                  <label>Season Name</label>
                  <input
                    type="text"
                    value={newSeason.name}
                    onChange={(e) => setNewSeason(prev => ({ ...prev, name: e.target.value }))}
                    placeholder="e.g., Summer Hours"
                  />
                </div>
                <div className="form-field">
                  <label>Start Date</label>
                  <input
                    type="date"
                    value={newSeason.start_date}
                    onChange={(e) => setNewSeason(prev => ({ ...prev, start_date: e.target.value }))}
                  />
                </div>
                <div className="form-field">
                  <label>End Date</label>
                  <input
                    type="date"
                    value={newSeason.end_date}
                    onChange={(e) => setNewSeason(prev => ({ ...prev, end_date: e.target.value }))}
                  />
                </div>
              </div>
              <div className="seasonal-form-row">
                <div className="form-field">
                  <label>Modified Start Time</label>
                  <input
                    type="time"
                    value={newSeason.hours.start}
                    onChange={(e) => setNewSeason(prev => ({ ...prev, hours: { ...prev.hours, start: e.target.value } }))}
                  />
                </div>
                <div className="form-field">
                  <label>Modified End Time</label>
                  <input
                    type="time"
                    value={newSeason.hours.end}
                    onChange={(e) => setNewSeason(prev => ({ ...prev, hours: { ...prev.hours, end: e.target.value } }))}
                  />
                </div>
                <button
                  type="button"
                  className="btn-primary btn-sm seasonal-add-btn"
                  onClick={addSeasonalHours}
                  disabled={!newSeason.name || !newSeason.start_date || !newSeason.end_date}
                >
                  <i className="fas fa-plus"></i> Add Season
                </button>
              </div>
            </div>

            {/* Seasonal hours list */}
            {seasonalHours.length > 0 && (
              <div className="seasonal-list">
                {seasonalHours.map(season => (
                  <div key={season.id} className={`seasonal-item ${season.active ? '' : 'seasonal-inactive'}`}>
                    <div className="seasonal-item-left">
                      <label className="toggle-switch">
                        <input
                          type="checkbox"
                          checked={season.active}
                          onChange={() => toggleSeasonActive(season.id)}
                        />
                        <span className="toggle-slider"></span>
                      </label>
                      <div className="seasonal-item-info">
                        <strong>{season.name}</strong>
                        <span className="seasonal-item-dates">
                          {new Date(season.start_date + 'T12:00:00').toLocaleDateString()} - {new Date(season.end_date + 'T12:00:00').toLocaleDateString()}
                        </span>
                        <span className="seasonal-item-hours">
                          <i className="fas fa-clock"></i> {season.hours.start} - {season.hours.end}
                        </span>
                      </div>
                    </div>
                    <div className="seasonal-item-actions">
                      <span className={`seasonal-status-badge ${season.active ? 'active' : 'inactive'}`}>
                        {season.active ? 'Active' : 'Inactive'}
                      </span>
                      <button
                        type="button"
                        className="icon-btn danger"
                        onClick={() => removeSeasonalHours(season.id)}
                        title="Remove season"
                        aria-label="Remove seasonal hours"
                      >
                        <i className="fas fa-trash"></i>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {seasonalHours.length === 0 && (
              <p className="empty-hint">No seasonal hours configured. Add a season above to modify hours for a date range.</p>
            )}
          </div>
        )}
      </section>

      {/* ---- Override Day ---- */}
      <section className="cal-settings-section">
        <button
          type="button"
          className="collapsible-header"
          onClick={() => toggleExpandedSection('override-days')}
          aria-expanded={expandedSections['override-days']}
        >
          <div className="collapsible-header-left">
            <i className={`fas fa-chevron-${expandedSections['override-days'] ? 'down' : 'right'} collapsible-chevron`}></i>
            <div>
              <h2>Override Day</h2>
              <p className="section-description">
                Set one-off custom hours for specific dates that differ from your regular schedule.
                {overrideDays.length > 0 && (
                  <span className="inline-count"> ({overrideDays.length} override{overrideDays.length !== 1 ? 's' : ''})</span>
                )}
              </p>
            </div>
          </div>
          <span className="collapsible-badge"><i className="fas fa-calendar-day"></i></span>
        </button>
        {expandedSections['override-days'] && (
          <div className="collapsible-body">
            <div className="override-form">
              <div className="override-form-row">
                <div className="form-field">
                  <label>Date</label>
                  <input
                    type="date"
                    value={newOverride.date}
                    onChange={(e) => setNewOverride(prev => ({ ...prev, date: e.target.value }))}
                    min={new Date().toISOString().split('T')[0]}
                  />
                </div>
                <div className="form-field">
                  <label>Start Time</label>
                  <input
                    type="time"
                    value={newOverride.start}
                    onChange={(e) => setNewOverride(prev => ({ ...prev, start: e.target.value }))}
                    disabled={!newOverride.enabled}
                  />
                </div>
                <div className="form-field">
                  <label>End Time</label>
                  <input
                    type="time"
                    value={newOverride.end}
                    onChange={(e) => setNewOverride(prev => ({ ...prev, end: e.target.value }))}
                    disabled={!newOverride.enabled}
                  />
                </div>
                <div className="form-field override-copy-field">
                  <label>Copy From</label>
                  <select
                    value={newOverride.copy_from}
                    onChange={(e) => { if (e.target.value) copyFromDay(e.target.value); }}
                  >
                    <option value="">-- Select day --</option>
                    {DAYS_OF_WEEK.map(day => (
                      <option key={day} value={day}>{DAY_LABELS[day]}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="override-form-actions">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={newOverride.enabled}
                    onChange={(e) => setNewOverride(prev => ({ ...prev, enabled: e.target.checked }))}
                  />
                  Available (uncheck to mark as day off)
                </label>
                <button
                  type="button"
                  className="btn-primary btn-sm"
                  onClick={addOverrideDay}
                  disabled={!newOverride.date}
                >
                  <i className="fas fa-plus"></i> Add Override
                </button>
              </div>
            </div>

            {/* Override list */}
            {overrideDays.length > 0 && (
              <div className="override-list">
                {overrideDays
                  .sort((a, b) => a.date.localeCompare(b.date))
                  .map(ov => (
                  <div key={ov.id} className={`override-item ${ov.enabled ? '' : 'override-dayoff'}`}>
                    <div className="override-item-info">
                      <i className={`fas ${ov.enabled ? 'fa-calendar-check' : 'fa-calendar-minus'}`}></i>
                      <div>
                        <span className="override-item-date">
                          {new Date(ov.date + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric', year: 'numeric' })}
                        </span>
                        <span className="override-item-hours">
                          {ov.enabled ? `${ov.start} - ${ov.end}` : 'Day Off'}
                        </span>
                      </div>
                    </div>
                    <button
                      type="button"
                      className="icon-btn danger"
                      onClick={() => removeOverrideDay(ov.id)}
                      title="Remove override"
                      aria-label="Remove override"
                    >
                      <i className="fas fa-times"></i>
                    </button>
                  </div>
                ))}
              </div>
            )}

            {overrideDays.length === 0 && (
              <p className="empty-hint">No date overrides configured. Add one above to customize a specific day.</p>
            )}
          </div>
        )}
      </section>

      {/* Booking Window settings */}
      <section className="cal-settings-section">
        <h2>Booking Window</h2>
        <p className="section-description">Control how clients can book appointments on your calendar.</p>
        <div className="form-grid">
          <div className="form-field">
            <label htmlFor="buffer">Buffer Between Meetings (min)</label>
            <input
              id="buffer"
              type="number"
              min="0"
              max="60"
              value={availability.buffer_minutes}
              onChange={(e) => { setAvailability(prev => ({ ...prev, buffer_minutes: parseInt(e.target.value) || 0 })); markChanged(); }}
            />
            <span className="field-hint">Break time between consecutive meetings</span>
          </div>
          <div className="form-field">
            <label htmlFor="min-notice">Minimum Notice (hours)</label>
            <input
              id="min-notice"
              type="number"
              min="0"
              max="168"
              value={availability.min_booking_notice_hours}
              onChange={(e) => { setAvailability(prev => ({ ...prev, min_booking_notice_hours: parseInt(e.target.value) || 0 })); markChanged(); }}
            />
            <span className="field-hint">How far in advance bookings must be made</span>
          </div>
          <div className="form-field">
            <label htmlFor="max-advance">Max Advance Booking (days)</label>
            <input
              id="max-advance"
              type="number"
              min="1"
              max="365"
              value={availability.max_advance_booking_days}
              onChange={(e) => { setAvailability(prev => ({ ...prev, max_advance_booking_days: parseInt(e.target.value) || 1 })); markChanged(); }}
            />
            <span className="field-hint">How far into the future clients can book</span>
          </div>
        </div>
      </section>
    </div>
  );
}
