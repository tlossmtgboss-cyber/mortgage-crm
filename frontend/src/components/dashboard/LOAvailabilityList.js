import React from 'react';

/**
 * LOAvailabilityList - Table of LOs with next available slot and booking stats.
 * Props:
 *   data: Array of { lo_id, lo_name, next_available_slot, appointment_count, avg_bookings_per_day, utilization_pct }
 *   onSelect: (lo) => void
 */
function LOAvailabilityList({ data, onSelect }) {
  if (!data || data.length === 0) {
    return (
      <div className="cd-card cd-lo-availability">
        <h3 className="cd-card-title">LO Availability</h3>
        <p className="cd-empty">No team members found</p>
      </div>
    );
  }

  const formatSlot = (isoString) => {
    if (!isoString) return 'No slots available';
    try {
      const dt = new Date(isoString);
      const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
      const dayName = dayNames[dt.getDay()];
      const hours = dt.getHours();
      const minutes = dt.getMinutes();
      const ampm = hours >= 12 ? 'PM' : 'AM';
      const h = hours % 12 || 12;
      const m = minutes.toString().padStart(2, '0');
      const month = dt.getMonth() + 1;
      const day = dt.getDate();
      return `${dayName} ${month}/${day} ${h}:${m} ${ampm}`;
    } catch {
      return isoString;
    }
  };

  const getStatusDot = (utilPct) => {
    if (utilPct >= 80) return 'cd-status-dot-red';
    if (utilPct >= 50) return 'cd-status-dot-yellow';
    return 'cd-status-dot-green';
  };

  // Sort: lowest utilization first (most available at top)
  const sorted = [...data].sort((a, b) => a.utilization_pct - b.utilization_pct);

  return (
    <div className="cd-card cd-lo-availability">
      <h3 className="cd-card-title">Upcoming Availability</h3>
      <p className="cd-card-subtitle">Next available slot per loan officer</p>
      <div className="cd-table-wrapper">
        <table className="cd-table">
          <thead>
            <tr>
              <th>Loan Officer</th>
              <th>Next Available</th>
              <th>Bookings</th>
              <th>Avg/Day</th>
              <th>Load</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((lo) => (
              <tr
                key={lo.lo_id}
                className="cd-table-row-clickable"
                onClick={() => onSelect && onSelect(lo)}
              >
                <td className="cd-lo-name-cell">
                  <span className={`cd-status-dot ${getStatusDot(lo.utilization_pct)}`} />
                  {lo.lo_name}
                </td>
                <td className="cd-next-slot">
                  {formatSlot(lo.next_available_slot)}
                </td>
                <td className="cd-center">{lo.appointment_count}</td>
                <td className="cd-center">{lo.avg_bookings_per_day}</td>
                <td className="cd-center">
                  <span className={`cd-load-badge ${lo.utilization_pct >= 80 ? 'cd-load-high' : lo.utilization_pct >= 50 ? 'cd-load-medium' : 'cd-load-low'}`}>
                    {lo.utilization_pct}%
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default LOAvailabilityList;
