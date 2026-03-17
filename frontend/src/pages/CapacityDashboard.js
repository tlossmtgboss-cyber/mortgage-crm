import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { capacityDashboardAPI } from '../services/api';
import CapacityOverview from '../components/dashboard/CapacityOverview';
import HeatmapChart from '../components/dashboard/HeatmapChart';
import WeeklyTrend from '../components/dashboard/WeeklyTrend';
import LOAvailabilityList from '../components/dashboard/LOAvailabilityList';
import BookingMetrics from '../components/dashboard/BookingMetrics';
import './CapacityDashboard.css';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const formatDateISO = (d) => {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${dd}`;
};

const getStartOfWeek = (d) => {
  const out = new Date(d);
  const day = out.getDay();
  // Start on Monday (day=1). If Sunday (0), go back 6 days.
  const diff = day === 0 ? 6 : day - 1;
  out.setDate(out.getDate() - diff);
  out.setHours(0, 0, 0, 0);
  return out;
};

const getEndOfWeek = (startOfWeek) => {
  const out = new Date(startOfWeek);
  out.setDate(out.getDate() + 6);
  return out;
};

const formatDateDisplay = (d) => {
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${months[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
};

// ---------------------------------------------------------------------------
// DashboardHeader sub-component
// ---------------------------------------------------------------------------

function DashboardHeader({ dateRange, onDateChange, onRefresh, loading }) {
  const goToPreviousWeek = () => {
    const newStart = new Date(dateRange.start);
    newStart.setDate(newStart.getDate() - 7);
    onDateChange({
      start: newStart,
      end: getEndOfWeek(newStart),
    });
  };

  const goToNextWeek = () => {
    const newStart = new Date(dateRange.start);
    newStart.setDate(newStart.getDate() + 7);
    onDateChange({
      start: newStart,
      end: getEndOfWeek(newStart),
    });
  };

  const goToCurrentWeek = () => {
    const start = getStartOfWeek(new Date());
    onDateChange({
      start,
      end: getEndOfWeek(start),
    });
  };

  return (
    <div className="cd-header">
      <div className="cd-header-left">
        <h1 className="cd-title">Capacity Dashboard</h1>
        <p className="cd-subtitle">Team scheduling load and availability at a glance</p>
      </div>
      <div className="cd-header-controls">
        <div className="cd-date-nav">
          <button className="cd-nav-btn" onClick={goToPreviousWeek} title="Previous week">
            &larr;
          </button>
          <span className="cd-date-range">
            {formatDateDisplay(dateRange.start)} &ndash; {formatDateDisplay(dateRange.end)}
          </span>
          <button className="cd-nav-btn" onClick={goToNextWeek} title="Next week">
            &rarr;
          </button>
        </div>
        <button className="cd-btn cd-btn-secondary" onClick={goToCurrentWeek}>
          This Week
        </button>
        <button className="cd-btn cd-btn-primary" onClick={onRefresh} disabled={loading}>
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main CapacityDashboard component
// ---------------------------------------------------------------------------

export default function CapacityDashboard() {
  const startOfWeek = useMemo(() => getStartOfWeek(new Date()), []);
  const endOfWeek = useMemo(() => getEndOfWeek(startOfWeek), [startOfWeek]);

  const [dateRange, setDateRange] = useState({ start: startOfWeek, end: endOfWeek });
  const [overviewData, setOverviewData] = useState(null);
  const [heatmapData, setHeatmapData] = useState(null);
  const [trendData, setTrendData] = useState(null);
  const [selectedLO, setSelectedLO] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const startStr = formatDateISO(dateRange.start);
      const endStr = formatDateISO(dateRange.end);

      const [overview, heatmap, trends] = await Promise.all([
        capacityDashboardAPI.getOverview(startStr, endStr),
        capacityDashboardAPI.getHeatmap(startStr, endStr),
        capacityDashboardAPI.getTrends(4),
      ]);

      setOverviewData(overview);
      setHeatmapData(heatmap);
      setTrendData(trends);
    } catch (err) {
      console.error('Capacity dashboard fetch error:', err);
      setError(err?.response?.data?.detail || err.message || 'Failed to load capacity data');
    } finally {
      setLoading(false);
    }
  }, [dateRange]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleLOSelect = (lo) => {
    setSelectedLO(lo);
  };

  if (error) {
    return (
      <div className="cd-page">
        <DashboardHeader
          dateRange={dateRange}
          onDateChange={setDateRange}
          onRefresh={fetchData}
          loading={loading}
        />
        <div className="cd-error">
          <div className="cd-error-icon">!</div>
          <h3>Unable to load capacity data</h3>
          <p>{error}</p>
          <button className="cd-btn cd-btn-primary" onClick={fetchData}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="cd-page">
      <DashboardHeader
        dateRange={dateRange}
        onDateChange={setDateRange}
        onRefresh={fetchData}
        loading={loading}
      />

      {loading && !overviewData ? (
        <div className="cd-loading">
          <div className="cd-spinner" />
          <p>Loading capacity data...</p>
        </div>
      ) : (
        <div className="cd-grid">
          {/* Row 1: KPI metrics across the top */}
          <div className="cd-grid-metrics">
            <BookingMetrics data={overviewData} />
          </div>

          {/* Row 2: Capacity overview bar chart + Heatmap */}
          <div className="cd-grid-row-2">
            <div className="cd-grid-col-left">
              <CapacityOverview data={overviewData?.team} />
            </div>
            <div className="cd-grid-col-right">
              <HeatmapChart data={heatmapData} />
            </div>
          </div>

          {/* Row 3: Weekly trend + LO availability list */}
          <div className="cd-grid-row-3">
            <div className="cd-grid-col-left">
              <WeeklyTrend data={trendData} />
            </div>
            <div className="cd-grid-col-right">
              <LOAvailabilityList
                data={overviewData?.team}
                onSelect={handleLOSelect}
              />
            </div>
          </div>

          {/* LO detail panel (shown when an LO is selected) */}
          {selectedLO && (
            <div className="cd-lo-detail-panel">
              <div className="cd-lo-detail-header">
                <h3>{selectedLO.lo_name} - Detail</h3>
                <button className="cd-close-btn" onClick={() => setSelectedLO(null)}>
                  &times;
                </button>
              </div>
              <div className="cd-lo-detail-body">
                <div className="cd-lo-detail-stat">
                  <span className="cd-lo-detail-label">Email</span>
                  <span>{selectedLO.email || 'N/A'}</span>
                </div>
                <div className="cd-lo-detail-stat">
                  <span className="cd-lo-detail-label">Appointments</span>
                  <span>{selectedLO.appointment_count}</span>
                </div>
                <div className="cd-lo-detail-stat">
                  <span className="cd-lo-detail-label">Booked Hours</span>
                  <span>{(selectedLO.booked_minutes / 60).toFixed(1)}h</span>
                </div>
                <div className="cd-lo-detail-stat">
                  <span className="cd-lo-detail-label">Available Hours</span>
                  <span>{(selectedLO.available_minutes / 60).toFixed(1)}h</span>
                </div>
                <div className="cd-lo-detail-stat">
                  <span className="cd-lo-detail-label">Utilization</span>
                  <span className={selectedLO.utilization_pct >= 80 ? 'cd-text-red' : selectedLO.utilization_pct >= 50 ? 'cd-text-yellow' : 'cd-text-green'}>
                    {selectedLO.utilization_pct}%
                  </span>
                </div>
                <div className="cd-lo-detail-stat">
                  <span className="cd-lo-detail-label">No-Show Rate</span>
                  <span>{selectedLO.no_show_rate}%</span>
                </div>
                <div className="cd-lo-detail-stat">
                  <span className="cd-lo-detail-label">Completed</span>
                  <span>{selectedLO.completed_count}</span>
                </div>
                <div className="cd-lo-detail-stat">
                  <span className="cd-lo-detail-label">Next Available</span>
                  <span>
                    {selectedLO.next_available_slot
                      ? new Date(selectedLO.next_available_slot).toLocaleString()
                      : 'None found'}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
