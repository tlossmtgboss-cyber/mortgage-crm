import React from 'react';

/**
 * WeeklyTrend - CSS-based line chart showing booking counts over time.
 * Props:
 *   data: { trends: Array of { week_label, total_appointments, utilization_pct, show_rate, no_show_rate } }
 */
function WeeklyTrend({ data }) {
  if (!data || !data.trends || data.trends.length === 0) {
    return (
      <div className="cd-card cd-weekly-trend">
        <h3 className="cd-card-title">Weekly Booking Trend</h3>
        <p className="cd-empty">No trend data available</p>
      </div>
    );
  }

  const { trends } = data;
  const maxAppts = Math.max(...trends.map((t) => t.total_appointments), 1);

  return (
    <div className="cd-card cd-weekly-trend">
      <h3 className="cd-card-title">Weekly Booking Trend</h3>
      <p className="cd-card-subtitle">Appointments per week over the past {trends.length} weeks</p>

      {/* CSS bar chart (vertical bars for each week) */}
      <div className="cd-trend-chart">
        <div className="cd-trend-bars">
          {trends.map((week, i) => {
            const heightPct = (week.total_appointments / maxAppts) * 100;
            const isCurrentWeek = i === trends.length - 1;

            return (
              <div className="cd-trend-bar-group" key={i}>
                <div className="cd-trend-bar-wrapper">
                  <span className="cd-trend-bar-count">{week.total_appointments}</span>
                  <div
                    className={`cd-trend-bar ${isCurrentWeek ? 'cd-trend-bar-current' : ''}`}
                    style={{ height: `${Math.max(heightPct, 4)}%` }}
                    title={`${week.week_label}: ${week.total_appointments} appointments, ${week.utilization_pct}% utilization`}
                  />
                </div>
                <div className="cd-trend-bar-label" title={week.week_label}>
                  {week.week_label.split(' - ')[0]}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Show rate / no-show rate summary for latest week */}
      {trends.length > 0 && (
        <div className="cd-trend-summary">
          <div className="cd-trend-stat">
            <span className="cd-trend-stat-label">Latest Show Rate</span>
            <span className="cd-trend-stat-value cd-trend-stat-good">
              {trends[trends.length - 1].show_rate}%
            </span>
          </div>
          <div className="cd-trend-stat">
            <span className="cd-trend-stat-label">Latest No-Show Rate</span>
            <span className={`cd-trend-stat-value ${trends[trends.length - 1].no_show_rate > 15 ? 'cd-trend-stat-bad' : 'cd-trend-stat-ok'}`}>
              {trends[trends.length - 1].no_show_rate}%
            </span>
          </div>
          <div className="cd-trend-stat">
            <span className="cd-trend-stat-label">Avg/Day</span>
            <span className="cd-trend-stat-value">
              {trends[trends.length - 1].avg_bookings_per_day}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

export default WeeklyTrend;
