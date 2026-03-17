import React from 'react';

/**
 * HeatmapChart - Hour x Day grid with colored cells showing booking density.
 * Props:
 *   data: { heatmap: Array of { hour, hour_label, cells: [{ day, day_name, count, intensity }] }, max_count }
 */
function HeatmapChart({ data }) {
  if (!data || !data.heatmap || data.heatmap.length === 0) {
    return (
      <div className="cd-card cd-heatmap-chart">
        <h3 className="cd-card-title">Schedule Heatmap</h3>
        <p className="cd-empty">No heatmap data available</p>
      </div>
    );
  }

  const { heatmap, days, max_count: maxCount } = data;

  const getColor = (intensity) => {
    if (intensity === 0) return 'var(--cd-heat-0, #f0f0f0)';
    if (intensity <= 25) return 'var(--cd-heat-25, #c6e48b)';
    if (intensity <= 50) return 'var(--cd-heat-50, #7bc96f)';
    if (intensity <= 75) return 'var(--cd-heat-75, #239a3b)';
    return 'var(--cd-heat-100, #196127)';
  };

  return (
    <div className="cd-card cd-heatmap-chart">
      <h3 className="cd-card-title">Schedule Heatmap</h3>
      <p className="cd-card-subtitle">Booking density by hour and day of week</p>
      <div className="cd-heatmap-container">
        <table className="cd-heatmap-table">
          <thead>
            <tr>
              <th className="cd-heatmap-corner"></th>
              {(days || []).map((day, i) => (
                <th key={i} className="cd-heatmap-day-header">
                  {day.slice(0, 3)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {heatmap.map((row) => (
              <tr key={row.hour}>
                <td className="cd-heatmap-hour-label">{row.hour_label}</td>
                {row.cells.map((cell, i) => (
                  <td
                    key={i}
                    className="cd-heatmap-cell"
                    style={{ backgroundColor: getColor(cell.intensity) }}
                    title={`${cell.day_name} ${row.hour_label}: ${cell.count} appointment${cell.count !== 1 ? 's' : ''}`}
                  >
                    {cell.count > 0 && (
                      <span className="cd-heatmap-count">{cell.count}</span>
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        <div className="cd-heatmap-legend">
          <span className="cd-heatmap-legend-label">Less</span>
          <span className="cd-heatmap-legend-box" style={{ backgroundColor: getColor(0) }} />
          <span className="cd-heatmap-legend-box" style={{ backgroundColor: getColor(25) }} />
          <span className="cd-heatmap-legend-box" style={{ backgroundColor: getColor(50) }} />
          <span className="cd-heatmap-legend-box" style={{ backgroundColor: getColor(75) }} />
          <span className="cd-heatmap-legend-box" style={{ backgroundColor: getColor(100) }} />
          <span className="cd-heatmap-legend-label">More</span>
        </div>
        {maxCount > 0 && (
          <p className="cd-heatmap-note">Peak: {maxCount} booking{maxCount !== 1 ? 's' : ''} in a single slot</p>
        )}
      </div>
    </div>
  );
}

export default HeatmapChart;
