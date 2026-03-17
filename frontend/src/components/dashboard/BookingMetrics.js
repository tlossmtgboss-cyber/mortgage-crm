import React from 'react';

/**
 * BookingMetrics - KPI cards showing utilization %, no-show rate, avg bookings/day, team size.
 * Props:
 *   data: {
 *     summary: { avg_utilization, total_appointments, total_no_shows, working_days, team_size, total_booked_minutes, total_capacity_minutes },
 *     team: Array (for per-LO stats)
 *   }
 */
function BookingMetrics({ data }) {
  if (!data || !data.summary) {
    return (
      <div className="cd-card cd-booking-metrics">
        <h3 className="cd-card-title">Booking Metrics</h3>
        <p className="cd-empty">No metrics available</p>
      </div>
    );
  }

  const { summary, team } = data;
  const noShowRate = summary.total_appointments > 0
    ? ((summary.total_no_shows / summary.total_appointments) * 100).toFixed(1)
    : '0.0';

  const avgBookingsPerDay = summary.working_days > 0
    ? (summary.total_appointments / summary.working_days).toFixed(1)
    : '0.0';

  const totalHoursBooked = (summary.total_booked_minutes / 60).toFixed(0);

  // Busiest LO
  const busiestLO = team && team.length > 0
    ? [...team].sort((a, b) => b.utilization_pct - a.utilization_pct)[0]
    : null;

  // Most available LO
  const mostAvailableLO = team && team.length > 0
    ? [...team].sort((a, b) => a.utilization_pct - b.utilization_pct)[0]
    : null;

  const metrics = [
    {
      label: 'Avg Utilization',
      value: `${summary.avg_utilization}%`,
      detail: 'Across all LOs',
      color: summary.avg_utilization >= 80 ? 'cd-metric-red' : summary.avg_utilization >= 50 ? 'cd-metric-yellow' : 'cd-metric-green',
    },
    {
      label: 'Total Appointments',
      value: summary.total_appointments,
      detail: `${totalHoursBooked} hours booked`,
      color: 'cd-metric-blue',
    },
    {
      label: 'No-Show Rate',
      value: `${noShowRate}%`,
      detail: `${summary.total_no_shows} no-shows`,
      color: parseFloat(noShowRate) > 15 ? 'cd-metric-red' : 'cd-metric-green',
    },
    {
      label: 'Avg Bookings/Day',
      value: avgBookingsPerDay,
      detail: `${summary.working_days} working days`,
      color: 'cd-metric-blue',
    },
    {
      label: 'Team Size',
      value: summary.team_size,
      detail: 'Active LOs',
      color: 'cd-metric-neutral',
    },
  ];

  return (
    <div className="cd-card cd-booking-metrics">
      <h3 className="cd-card-title">Booking Metrics</h3>
      <div className="cd-metrics-grid">
        {metrics.map((m, i) => (
          <div className={`cd-metric-card ${m.color}`} key={i}>
            <div className="cd-metric-value">{m.value}</div>
            <div className="cd-metric-label">{m.label}</div>
            <div className="cd-metric-detail">{m.detail}</div>
          </div>
        ))}
      </div>

      {(busiestLO || mostAvailableLO) && (
        <div className="cd-metrics-highlights">
          {busiestLO && (
            <div className="cd-highlight">
              <span className="cd-highlight-label">Busiest:</span>
              <span className="cd-highlight-value">{busiestLO.lo_name} ({busiestLO.utilization_pct}%)</span>
            </div>
          )}
          {mostAvailableLO && (
            <div className="cd-highlight">
              <span className="cd-highlight-label">Most Available:</span>
              <span className="cd-highlight-value">{mostAvailableLO.lo_name} ({mostAvailableLO.utilization_pct}%)</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default BookingMetrics;
