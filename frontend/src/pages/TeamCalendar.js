import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { toast } from '../utils/toast';
import { teamCalendarAPI, teamAPI, schedulerAPI } from '../services/api';
import './TeamCalendar.css';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const VIEW_HOURS = [];
for (let h = 7; h < 19; h++) {
  VIEW_HOURS.push({ hour: h, minute: 0 });
  VIEW_HOURS.push({ hour: h, minute: 30 });
}

const DAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const DAY_ABBR = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

const APPT_TYPE_COLORS = {
  meeting: 'tc-appt-meeting',
  custom: 'tc-appt-meeting',
  pre_purchase_consultation: 'tc-appt-pre_purchase',
  purchase_consultation: 'tc-appt-purchase',
  closing: 'tc-appt-closing',
  call: 'tc-appt-call',
  phone: 'tc-appt-call',
  video: 'tc-appt-meeting',
};

const STATUS_COLORS = {
  booked: 'tc-appt-booked',
  confirmed: 'tc-appt-booked',
  completed: 'tc-appt-completed',
  no_show: 'tc-appt-no_show',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const formatHour = (hour) => {
  if (hour === 0) return '12 AM';
  if (hour < 12) return `${hour} AM`;
  if (hour === 12) return '12 PM';
  return `${hour - 12} PM`;
};

const formatSlotLabel = (hour, minute) => {
  const h = hour > 12 ? hour - 12 : hour === 0 ? 12 : hour;
  const ampm = hour >= 12 ? 'PM' : 'AM';
  return `${h}:${minute === 0 ? '00' : minute} ${ampm}`;
};

const formatDateISO = (d) => {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${dd}`;
};

const isSameDay = (d1, d2) =>
  d1.getFullYear() === d2.getFullYear() &&
  d1.getMonth() === d2.getMonth() &&
  d1.getDate() === d2.getDate();

const getStartOfWeek = (d) => {
  const out = new Date(d);
  out.setDate(out.getDate() - out.getDay());
  out.setHours(0, 0, 0, 0);
  return out;
};

const getApptColorClass = (appt) => {
  const mt = (appt.meeting_type || '').toLowerCase();
  if (APPT_TYPE_COLORS[mt]) return APPT_TYPE_COLORS[mt];
  const st = (appt.status || '').toLowerCase();
  if (STATUS_COLORS[st]) return STATUS_COLORS[st];
  return 'tc-appt-other';
};

const capacityClass = (pct) => {
  if (pct < 50) return 'tc-capacity-green';
  if (pct < 80) return 'tc-capacity-yellow';
  return 'tc-capacity-red';
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

function TeamCalendar() {
  // State
  const [view, setView] = useState('day'); // day | week | availability
  const [currentDate, setCurrentDate] = useState(new Date());
  const [teamData, setTeamData] = useState(null);
  const [capacityData, setCapacityData] = useState(null);
  const [availabilityMatrix, setAvailabilityMatrix] = useState(null);
  const [teamMembers, setTeamMembers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filters
  const [searchTerm, setSearchTerm] = useState('');
  const [filterType, setFilterType] = useState('all');
  const [filterStatus, setFilterStatus] = useState('all');
  const [filterLoIds, setFilterLoIds] = useState([]);

  // Tooltip
  const [tooltip, setTooltip] = useState(null);

  // Modals
  const [reassignModal, setReassignModal] = useState(null);
  const [quickBookModal, setQuickBookModal] = useState(null);
  const [reassigning, setReassigning] = useState(false);

  // Drag and drop
  const dragRef = useRef(null);

  // Refs for time indicator
  const gridRef = useRef(null);
  const [nowLineTop, setNowLineTop] = useState(null);

  // -------------------------------------------------------------------------
  // Data fetching
  // -------------------------------------------------------------------------

  const dateRange = useMemo(() => {
    if (view === 'week') {
      const start = getStartOfWeek(currentDate);
      const end = new Date(start);
      end.setDate(end.getDate() + 6);
      return { start: formatDateISO(start), end: formatDateISO(end) };
    }
    const d = formatDateISO(currentDate);
    return { start: d, end: d };
  }, [currentDate, view]);

  const loIdFilter = useMemo(() => {
    return filterLoIds.length > 0 ? filterLoIds.join(',') : null;
  }, [filterLoIds]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [calResult, capResult] = await Promise.all([
        teamCalendarAPI.getTeamCalendar(dateRange.start, dateRange.end, loIdFilter),
        teamCalendarAPI.getCapacity(dateRange.start, dateRange.end, loIdFilter),
      ]);
      setTeamData(calResult);
      setCapacityData(capResult?.capacity || {});

      if (view === 'availability') {
        const availResult = await teamCalendarAPI.getAvailabilityMatrix(
          dateRange.start,
          30,
          loIdFilter,
        );
        setAvailabilityMatrix(availResult);
      }
    } catch (err) {
      console.error('Team calendar fetch error:', err);
      setError(err?.response?.data?.detail || err.message || 'Failed to load team calendar');
    } finally {
      setLoading(false);
    }
  }, [dateRange, loIdFilter, view]);

  const fetchTeamMembers = useCallback(async () => {
    try {
      const members = await teamAPI.getMembers();
      setTeamMembers(Array.isArray(members) ? members : []);
    } catch (err) {
      console.error('Failed to load team members:', err);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    fetchTeamMembers();
  }, [fetchTeamMembers]);

  // Current time indicator
  useEffect(() => {
    const updateNowLine = () => {
      const now = new Date();
      const h = now.getHours();
      const m = now.getMinutes();
      if (h >= 7 && h < 19) {
        const totalMinutes = (h - 7) * 60 + m;
        const totalSlots = 24; // 12 hours * 2 slots
        const pxPerSlot = 48; // min-height of cell
        setNowLineTop((totalMinutes / (12 * 60)) * totalSlots * pxPerSlot);
      } else {
        setNowLineTop(null);
      }
    };
    updateNowLine();
    const interval = setInterval(updateNowLine, 60000);
    return () => clearInterval(interval);
  }, []);

  // -------------------------------------------------------------------------
  // Derived data
  // -------------------------------------------------------------------------

  const loList = useMemo(() => {
    if (!teamData?.team) return [];
    return Object.values(teamData.team).sort((a, b) =>
      (a.lo_name || '').localeCompare(b.lo_name || ''),
    );
  }, [teamData]);

  // Apply search and filter
  const filteredLoList = useMemo(() => {
    return loList.map((lo) => {
      let appts = lo.appointments || [];

      // Filter by type
      if (filterType !== 'all') {
        appts = appts.filter((a) => (a.meeting_type || '').toLowerCase() === filterType);
      }

      // Filter by status
      if (filterStatus !== 'all') {
        appts = appts.filter((a) => (a.status || '').toLowerCase() === filterStatus);
      }

      // Search
      if (searchTerm) {
        const term = searchTerm.toLowerCase();
        appts = appts.filter(
          (a) =>
            (a.title || '').toLowerCase().includes(term) ||
            (a.attendee_name || '').toLowerCase().includes(term) ||
            (a.attendee_email || '').toLowerCase().includes(term) ||
            (a.attendee_phone || '').includes(term),
        );
      }

      return { ...lo, appointments: appts };
    });
  }, [loList, filterType, filterStatus, searchTerm]);

  // -------------------------------------------------------------------------
  // Navigation
  // -------------------------------------------------------------------------

  const goToday = () => setCurrentDate(new Date());

  const goPrev = () => {
    const d = new Date(currentDate);
    d.setDate(d.getDate() - (view === 'week' ? 7 : 1));
    setCurrentDate(d);
  };

  const goNext = () => {
    const d = new Date(currentDate);
    d.setDate(d.getDate() + (view === 'week' ? 7 : 1));
    setCurrentDate(d);
  };

  const dateLabel = useMemo(() => {
    if (view === 'week') {
      const start = getStartOfWeek(currentDate);
      const end = new Date(start);
      end.setDate(end.getDate() + 6);
      return `${MONTH_NAMES[start.getMonth()]} ${start.getDate()} - ${MONTH_NAMES[end.getMonth()]} ${end.getDate()}, ${end.getFullYear()}`;
    }
    return `${DAY_NAMES[currentDate.getDay()]}, ${MONTH_NAMES[currentDate.getMonth()]} ${currentDate.getDate()}, ${currentDate.getFullYear()}`;
  }, [currentDate, view]);

  // -------------------------------------------------------------------------
  // Tooltip
  // -------------------------------------------------------------------------

  const showTooltip = useCallback((e, appt) => {
    const rect = e.currentTarget.getBoundingClientRect();
    setTooltip({
      appt,
      x: rect.right + 8,
      y: rect.top,
    });
  }, []);

  const hideTooltip = useCallback(() => setTooltip(null), []);

  // -------------------------------------------------------------------------
  // Drag and Drop (reassign)
  // -------------------------------------------------------------------------

  const onDragStart = useCallback((e, appt, loId) => {
    dragRef.current = { appt, fromLoId: loId };
    e.dataTransfer.effectAllowed = 'move';
    e.currentTarget.classList.add('dragging');
  }, []);

  const onDragEnd = useCallback((e) => {
    e.currentTarget.classList.remove('dragging');
    dragRef.current = null;
  }, []);

  const onDragOver = useCallback((e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    e.currentTarget.classList.add('drag-over');
  }, []);

  const onDragLeave = useCallback((e) => {
    e.currentTarget.classList.remove('drag-over');
  }, []);

  const onDrop = useCallback(
    (e, toLoId) => {
      e.preventDefault();
      e.currentTarget.classList.remove('drag-over');
      if (!dragRef.current) return;
      const { appt, fromLoId } = dragRef.current;
      if (String(fromLoId) === String(toLoId)) return;

      // Open reassign modal with pre-filled data
      setReassignModal({
        appointmentId: appt.id,
        appointmentTitle: appt.title,
        fromLoId,
        newLoId: parseInt(toLoId, 10),
        reason: '',
      });
      dragRef.current = null;
    },
    [],
  );

  // -------------------------------------------------------------------------
  // Reassign handler
  // -------------------------------------------------------------------------

  const handleReassign = async () => {
    if (!reassignModal) return;
    setReassigning(true);
    try {
      await teamCalendarAPI.reassignAppointment(
        reassignModal.appointmentId,
        reassignModal.newLoId,
        reassignModal.reason || null,
      );
      setReassignModal(null);
      fetchData();
    } catch (err) {
      const detail = err?.response?.data?.detail || err.message;
      toast.error(`Reassign failed: ${detail}`);
    } finally {
      setReassigning(false);
    }
  };

  // -------------------------------------------------------------------------
  // Quick book handler
  // -------------------------------------------------------------------------

  const handleQuickBookClick = useCallback((loId, loName, slotHour, slotMinute) => {
    setQuickBookModal({
      loId,
      loName,
      hour: slotHour,
      minute: slotMinute,
      title: '',
      attendeeName: '',
      attendeeEmail: '',
      attendeePhone: '',
      duration: 30,
      meetingType: 'custom',
    });
  }, []);

  const handleQuickBookSubmit = async () => {
    if (!quickBookModal || !quickBookModal.title) return;
    const startDate = new Date(currentDate);
    startDate.setHours(quickBookModal.hour, quickBookModal.minute, 0, 0);
    const endDate = new Date(startDate);
    endDate.setMinutes(endDate.getMinutes() + quickBookModal.duration);

    try {
      await schedulerAPI.createAppointment({
        title: quickBookModal.title,
        assigned_user_id: quickBookModal.loId,
        scheduled_start: startDate.toISOString(),
        scheduled_end: endDate.toISOString(),
        duration_minutes: quickBookModal.duration,
        meeting_type: quickBookModal.meetingType,
        attendee_name: quickBookModal.attendeeName || undefined,
        attendee_email: quickBookModal.attendeeEmail || undefined,
        attendee_phone: quickBookModal.attendeePhone || undefined,
      });
      setQuickBookModal(null);
      fetchData();
    } catch (err) {
      const detail = err?.response?.data?.detail || err.message;
      toast.error(`Failed to create appointment: ${detail}`);
    }
  };

  // -------------------------------------------------------------------------
  // Build slot map for day view
  // -------------------------------------------------------------------------

  const slotMap = useMemo(() => {
    // { loId: { "HH:MM": [appointment, ...] } }
    const map = {};
    for (const lo of filteredLoList) {
      const loMap = {};
      for (const appt of lo.appointments) {
        if (!appt.scheduled_start) continue;
        const start = new Date(appt.scheduled_start);
        const h = start.getHours();
        const m = start.getMinutes();
        const slotKey = `${String(h).padStart(2, '0')}:${m < 30 ? '00' : '30'}`;
        if (!loMap[slotKey]) loMap[slotKey] = [];
        loMap[slotKey].push(appt);
      }
      map[lo.lo_id] = loMap;
    }
    return map;
  }, [filteredLoList]);

  // -------------------------------------------------------------------------
  // Render: Day View
  // -------------------------------------------------------------------------

  const renderDayView = () => {
    const colCount = filteredLoList.length + 1; // +1 for time gutter
    const today = new Date();
    const dayKey = formatDateISO(currentDate);

    return (
      <div className="tc-day-grid-wrapper" ref={gridRef}>
        <div
          className="tc-day-grid"
          style={{ gridTemplateColumns: `72px repeat(${filteredLoList.length}, minmax(180px, 1fr))` }}
        >
          {/* Header row */}
          <div className="tc-time-gutter-header" />
          {filteredLoList.map((lo) => {
            const cap = capacityData?.[String(lo.lo_id)]?.days?.[dayKey];
            const pct = cap?.pct ?? 0;
            return (
              <div key={lo.lo_id} className="tc-lo-col-header">
                <div className="tc-lo-name">{lo.lo_name}</div>
                <span className={`tc-lo-capacity-badge ${capacityClass(pct)}`}>
                  {Math.round(pct)}% booked
                </span>
              </div>
            );
          })}

          {/* Time slots */}
          {VIEW_HOURS.map(({ hour, minute }, idx) => {
            const slotKey = `${String(hour).padStart(2, '0')}:${minute === 0 ? '00' : '30'}`;
            return (
              <div className="tc-time-row" key={slotKey}>
                <div className={`tc-time-label ${minute === 30 ? 'tc-half-hour' : ''}`}>
                  {minute === 0 ? formatHour(hour) : ''}
                </div>
                {filteredLoList.map((lo) => {
                  const cellAppts = slotMap[lo.lo_id]?.[slotKey] || [];
                  return (
                    <div
                      key={`${lo.lo_id}-${slotKey}`}
                      className={`tc-cell ${minute === 30 ? 'tc-half-hour' : ''}`}
                      onDragOver={onDragOver}
                      onDragLeave={onDragLeave}
                      onDrop={(e) => onDrop(e, lo.lo_id)}
                      onClick={() => {
                        if (cellAppts.length === 0) {
                          handleQuickBookClick(lo.lo_id, lo.lo_name, hour, minute);
                        }
                      }}
                    >
                      {cellAppts.map((appt) => (
                        <div
                          key={appt.id}
                          className={`tc-appointment ${getApptColorClass(appt)}`}
                          draggable
                          onDragStart={(e) => onDragStart(e, appt, lo.lo_id)}
                          onDragEnd={onDragEnd}
                          onMouseEnter={(e) => showTooltip(e, appt)}
                          onMouseLeave={hideTooltip}
                        >
                          <div className="tc-appointment-title">{appt.title}</div>
                          {appt.attendee_name && (
                            <div className="tc-appointment-attendee">{appt.attendee_name}</div>
                          )}
                        </div>
                      ))}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>

        {/* Current time indicator */}
        {isSameDay(currentDate, today) && nowLineTop !== null && (
          <div className="tc-now-line" style={{ top: `${nowLineTop + 40}px` }} />
        )}
      </div>
    );
  };

  // -------------------------------------------------------------------------
  // Render: Week View (mini columns)
  // -------------------------------------------------------------------------

  const renderWeekView = () => {
    const weekStart = getStartOfWeek(currentDate);
    const days = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date(weekStart);
      d.setDate(d.getDate() + i);
      days.push(d);
    }
    const today = new Date();

    return (
      <div className="tc-week-grid-wrapper">
        <div
          className="tc-week-grid"
          style={{
            gridTemplateColumns: `140px repeat(7, minmax(100px, 1fr))`,
          }}
        >
          {/* Header row */}
          <div className="tc-week-day-header" style={{ background: 'var(--color-bg-secondary)' }}>
            LO
          </div>
          {days.map((d, i) => (
            <div
              key={i}
              className={`tc-week-day-header ${isSameDay(d, today) ? 'today' : ''}`}
            >
              {DAY_ABBR[d.getDay()]} {d.getDate()}
            </div>
          ))}

          {/* LO rows */}
          {filteredLoList.map((lo) => (
            <div className="tc-week-lo-row" key={lo.lo_id}>
              <div className="tc-week-lo-name">{lo.lo_name}</div>
              {days.map((d, dayIdx) => {
                const dayStr = formatDateISO(d);
                const dayAppts = (lo.appointments || []).filter((a) => {
                  if (!a.scheduled_start) return false;
                  return a.scheduled_start.startsWith(dayStr);
                });
                const cap = capacityData?.[String(lo.lo_id)]?.days?.[dayStr];
                const pct = cap?.pct ?? 0;
                return (
                  <div key={`${lo.lo_id}-${dayIdx}`} className="tc-week-cell">
                    {dayAppts.length > 0 && (
                      <span className={`tc-week-appt-count ${capacityClass(pct)}`}>
                        {dayAppts.length} appt{dayAppts.length > 1 ? 's' : ''}
                      </span>
                    )}
                    {dayAppts.slice(0, 3).map((a) => (
                      <div
                        key={a.id}
                        className={`tc-week-mini-event ${getApptColorClass(a)}`}
                        onMouseEnter={(e) => showTooltip(e, a)}
                        onMouseLeave={hideTooltip}
                      >
                        {a.title}
                      </div>
                    ))}
                    {dayAppts.length > 3 && (
                      <div style={{ fontSize: '10px', color: 'var(--color-text-secondary)' }}>
                        +{dayAppts.length - 3} more
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    );
  };

  // -------------------------------------------------------------------------
  // Render: Availability Overlay
  // -------------------------------------------------------------------------

  const renderAvailabilityView = () => {
    if (!availabilityMatrix?.matrix) {
      return <div className="tc-empty">Loading availability data...</div>;
    }

    const matrixEntries = Object.values(availabilityMatrix.matrix);
    if (matrixEntries.length === 0) {
      return <div className="tc-empty">No team members found.</div>;
    }

    const sampleSlots = matrixEntries[0]?.slots || [];

    return (
      <div className="tc-avail-wrapper">
        <div
          className="tc-avail-grid"
          style={{
            gridTemplateColumns: `140px repeat(${sampleSlots.length}, minmax(36px, 1fr))`,
          }}
        >
          {/* Time headers */}
          <div className="tc-week-day-header">LO</div>
          {sampleSlots.map((slot, i) => (
            <div
              key={i}
              className="tc-week-day-header"
              style={{ fontSize: '10px', padding: '4px 2px', writingMode: 'vertical-lr' }}
            >
              {slot.start}
            </div>
          ))}

          {/* LO rows */}
          {matrixEntries.map((lo) => (
            <React.Fragment key={lo.lo_id}>
              <div className="tc-week-lo-name">{lo.lo_name}</div>
              {(lo.slots || []).map((slot, i) => (
                <div
                  key={i}
                  className={`tc-avail-cell ${slot.available ? 'tc-avail-free' : 'tc-avail-busy'}`}
                  title={`${slot.start} - ${slot.end}: ${slot.available ? 'Available' : 'Busy'}`}
                  onClick={() => {
                    if (slot.available) {
                      const [h, m] = slot.start.split(':').map(Number);
                      handleQuickBookClick(lo.lo_id, lo.lo_name, h, m);
                    }
                  }}
                />
              ))}
            </React.Fragment>
          ))}
        </div>
      </div>
    );
  };

  // -------------------------------------------------------------------------
  // Main render
  // -------------------------------------------------------------------------

  return (
    <div className="team-calendar-page">
      {/* Header */}
      <div className="team-calendar-header">
        <div>
          <h1>Team Calendar</h1>
          <p>Side-by-side schedule view for all loan officers</p>
        </div>
        <div className="tc-controls">
          <div className="tc-view-switcher">
            <button className={view === 'day' ? 'active' : ''} onClick={() => setView('day')}>
              Day
            </button>
            <button className={view === 'week' ? 'active' : ''} onClick={() => setView('week')}>
              Week
            </button>
            <button
              className={view === 'availability' ? 'active' : ''}
              onClick={() => setView('availability')}
            >
              Availability
            </button>
          </div>
          <div className="tc-date-nav">
            <button onClick={goPrev}>&lsaquo;</button>
            <span className="tc-date-label">{dateLabel}</span>
            <button onClick={goNext}>&rsaquo;</button>
          </div>
          <button className="tc-today-btn" onClick={goToday}>
            Today
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="tc-filters">
        <div className="tc-search">
          <span className="tc-search-icon">&#128269;</span>
          <input
            type="text"
            placeholder="Search client name, email, or phone..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
        <select
          className="tc-filter-select"
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
        >
          <option value="all">All Types</option>
          <option value="custom">Custom</option>
          <option value="pre_purchase_consultation">Pre-Purchase</option>
          <option value="purchase_consultation">Purchase</option>
          <option value="closing">Closing</option>
          <option value="call">Call</option>
          <option value="video">Video</option>
        </select>
        <select
          className="tc-filter-select"
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
        >
          <option value="all">All Statuses</option>
          <option value="booked">Booked</option>
          <option value="confirmed">Confirmed</option>
          <option value="completed">Completed</option>
          <option value="no_show">No Show</option>
        </select>
        {teamMembers.length > 0 && (
          <select
            className="tc-filter-select"
            value={filterLoIds.length === 0 ? '' : filterLoIds[0]}
            onChange={(e) => {
              if (e.target.value === '') {
                setFilterLoIds([]);
              } else {
                setFilterLoIds([parseInt(e.target.value, 10)]);
              }
            }}
          >
            <option value="">All LOs</option>
            {teamMembers.map((m) => (
              <option key={m.id} value={m.id}>
                {m.first_name} {m.last_name}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Error banner */}
      {error && (
        <div className="tc-error-banner">
          <span>{error}</span>
          <button onClick={fetchData}>Retry</button>
        </div>
      )}

      {/* Loading */}
      {loading && <div className="tc-loading">Loading team calendar...</div>}

      {/* Content */}
      {!loading && !error && (
        <>
          {filteredLoList.length === 0 ? (
            <div className="tc-empty">
              No team members found. Make sure you have manager or admin access.
            </div>
          ) : (
            <>
              {view === 'day' && renderDayView()}
              {view === 'week' && renderWeekView()}
              {view === 'availability' && renderAvailabilityView()}
            </>
          )}
        </>
      )}

      {/* Tooltip */}
      {tooltip && (
        <div
          className="tc-tooltip"
          style={{
            left: Math.min(tooltip.x, window.innerWidth - 340),
            top: Math.min(tooltip.y, window.innerHeight - 200),
          }}
        >
          <h4>{tooltip.appt.title}</h4>
          {tooltip.appt.attendee_name && (
            <div className="tc-tooltip-row">
              <span className="tc-tooltip-label">Client:</span>
              <span>{tooltip.appt.attendee_name}</span>
            </div>
          )}
          {tooltip.appt.scheduled_start && (
            <div className="tc-tooltip-row">
              <span className="tc-tooltip-label">Time:</span>
              <span>
                {new Date(tooltip.appt.scheduled_start).toLocaleTimeString([], {
                  hour: 'numeric',
                  minute: '2-digit',
                })}
                {tooltip.appt.scheduled_end &&
                  ` - ${new Date(tooltip.appt.scheduled_end).toLocaleTimeString([], {
                    hour: 'numeric',
                    minute: '2-digit',
                  })}`}
              </span>
            </div>
          )}
          {tooltip.appt.meeting_type && (
            <div className="tc-tooltip-row">
              <span className="tc-tooltip-label">Type:</span>
              <span>{tooltip.appt.meeting_type}</span>
            </div>
          )}
          {tooltip.appt.attendee_phone && (
            <div className="tc-tooltip-row">
              <span className="tc-tooltip-label">Phone:</span>
              <span>{tooltip.appt.attendee_phone}</span>
            </div>
          )}
          {tooltip.appt.attendee_email && (
            <div className="tc-tooltip-row">
              <span className="tc-tooltip-label">Email:</span>
              <span>{tooltip.appt.attendee_email}</span>
            </div>
          )}
          {tooltip.appt.status && (
            <div className="tc-tooltip-row">
              <span className="tc-tooltip-label">Status:</span>
              <span>{tooltip.appt.status}</span>
            </div>
          )}
        </div>
      )}

      {/* Reassign Modal */}
      {reassignModal && (
        <div className="tc-modal-overlay" onClick={() => !reassigning && setReassignModal(null)}>
          <div className="tc-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Reassign Appointment</h3>
            <p style={{ fontSize: '14px', color: 'var(--color-text-secondary)', marginBottom: '16px' }}>
              Move &ldquo;{reassignModal.appointmentTitle}&rdquo; to a different loan officer.
            </p>
            <div className="form-group">
              <label>New Loan Officer</label>
              <select
                value={reassignModal.newLoId || ''}
                onChange={(e) =>
                  setReassignModal((m) => ({ ...m, newLoId: parseInt(e.target.value, 10) }))
                }
              >
                <option value="">Select LO...</option>
                {loList
                  .filter((lo) => lo.lo_id !== reassignModal.fromLoId)
                  .map((lo) => (
                    <option key={lo.lo_id} value={lo.lo_id}>
                      {lo.lo_name}
                    </option>
                  ))}
              </select>
            </div>
            <div className="form-group">
              <label>Reason (optional)</label>
              <input
                type="text"
                value={reassignModal.reason}
                onChange={(e) => setReassignModal((m) => ({ ...m, reason: e.target.value }))}
                placeholder="e.g., Vacation coverage"
              />
            </div>
            <div className="tc-modal-actions">
              <button
                className="tc-btn-cancel"
                onClick={() => setReassignModal(null)}
                disabled={reassigning}
              >
                Cancel
              </button>
              <button
                className="tc-btn-primary"
                onClick={handleReassign}
                disabled={reassigning || !reassignModal.newLoId}
              >
                {reassigning ? 'Reassigning...' : 'Reassign'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Quick Book Modal */}
      {quickBookModal && (
        <div className="tc-modal-overlay" onClick={() => setQuickBookModal(null)}>
          <div className="tc-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Quick Book Appointment</h3>
            <div className="tc-quick-book-info">
              {quickBookModal.loName} &mdash;{' '}
              {formatSlotLabel(quickBookModal.hour, quickBookModal.minute)},{' '}
              {MONTH_NAMES[currentDate.getMonth()]} {currentDate.getDate()}
            </div>
            <div className="form-group">
              <label>Title *</label>
              <input
                type="text"
                value={quickBookModal.title}
                onChange={(e) => setQuickBookModal((m) => ({ ...m, title: e.target.value }))}
                placeholder="e.g., Pre-Purchase Consultation"
              />
            </div>
            <div className="form-group">
              <label>Duration (minutes)</label>
              <select
                value={quickBookModal.duration}
                onChange={(e) =>
                  setQuickBookModal((m) => ({ ...m, duration: parseInt(e.target.value, 10) }))
                }
              >
                <option value={15}>15 min</option>
                <option value={30}>30 min</option>
                <option value={45}>45 min</option>
                <option value={60}>60 min</option>
                <option value={90}>90 min</option>
              </select>
            </div>
            <div className="form-group">
              <label>Meeting Type</label>
              <select
                value={quickBookModal.meetingType}
                onChange={(e) => setQuickBookModal((m) => ({ ...m, meetingType: e.target.value }))}
              >
                <option value="custom">Custom</option>
                <option value="pre_purchase_consultation">Pre-Purchase Consultation</option>
                <option value="purchase_consultation">Purchase Consultation</option>
                <option value="closing">Closing</option>
                <option value="call">Call</option>
              </select>
            </div>
            <div className="form-group">
              <label>Client Name</label>
              <input
                type="text"
                value={quickBookModal.attendeeName}
                onChange={(e) =>
                  setQuickBookModal((m) => ({ ...m, attendeeName: e.target.value }))
                }
                placeholder="John Smith"
              />
            </div>
            <div className="form-group">
              <label>Client Email</label>
              <input
                type="email"
                value={quickBookModal.attendeeEmail}
                onChange={(e) =>
                  setQuickBookModal((m) => ({ ...m, attendeeEmail: e.target.value }))
                }
                placeholder="john@example.com"
              />
            </div>
            <div className="form-group">
              <label>Client Phone</label>
              <input
                type="tel"
                value={quickBookModal.attendeePhone}
                onChange={(e) =>
                  setQuickBookModal((m) => ({ ...m, attendeePhone: e.target.value }))
                }
                placeholder="(555) 123-4567"
              />
            </div>
            <div className="tc-modal-actions">
              <button className="tc-btn-cancel" onClick={() => setQuickBookModal(null)}>
                Cancel
              </button>
              <button
                className="tc-btn-primary"
                onClick={handleQuickBookSubmit}
                disabled={!quickBookModal.title}
              >
                Book Appointment
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default TeamCalendar;
