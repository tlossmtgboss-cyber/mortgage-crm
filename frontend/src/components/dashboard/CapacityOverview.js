import React from 'react';

/**
 * CapacityOverview - Horizontal bar chart showing booked vs available per LO.
 * Props:
 *   data: Array of { lo_name, booked_minutes, available_minutes, total_capacity_minutes, utilization_pct }
 */
function CapacityOverview({ data }) {
  if (!data || data.length === 0) {
    return (
      <div className="cd-card cd-capacity-overview">
        <h3 className="cd-card-title">Team Capacity Overview</h3>
        <p className="cd-empty">No team data available</p>
      </div>
    );
  }

  const sorted = [...data].sort((a, b) => b.utilization_pct - a.utilization_pct);

  return (
    <div className="cd-card cd-capacity-overview">
      <h3 className="cd-card-title">Team Capacity Overview</h3>
      <div className="cd-bar-chart">
        {sorted.map((lo) => {
          const pct = lo.utilization_pct || 0;
          let barClass = 'cd-bar-fill-green';
          if (pct >= 80) barClass = 'cd-bar-fill-red';
          else if (pct >= 50) barClass = 'cd-bar-fill-yellow';

          return (
            <div className="cd-bar-row" key={lo.lo_id}>
              <div className="cd-bar-label" title={lo.lo_name}>
                {lo.lo_name}
              </div>
              <div className="cd-bar-track">
                <div
                  className={`cd-bar-fill ${barClass}`}
                  style={{ width: `${Math.min(pct, 100)}%` }}
                />
              </div>
              <div className="cd-bar-value">
                {pct}%
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default CapacityOverview;
