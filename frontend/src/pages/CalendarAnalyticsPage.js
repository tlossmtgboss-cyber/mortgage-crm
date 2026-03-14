/**
 * CalendarAnalyticsPage - Page wrapper for the CalendarAnalytics component.
 * Route: /calendar/analytics
 *
 * Provides a consistent page-level topbar with back navigation (matching
 * CalendarSettings pattern), then renders the full CalendarAnalytics dashboard.
 */

import React from 'react';
import { useNavigate, Link } from 'react-router-dom';
import CalendarAnalytics from '../components/calendar/CalendarAnalytics';
import '../styles/calendar-settings.css';

export default function CalendarAnalyticsPage() {
  const navigate = useNavigate();

  return (
    <div className="cal-settings-page">
      {/* Top Bar - consistent with CalendarSettings */}
      <header className="cal-settings-topbar">
        <div className="cal-settings-topbar-inner">
          <div className="topbar-left">
            <button
              onClick={() => navigate('/calendar')}
              className="back-btn"
              aria-label="Back to calendar"
            >
              <i className="fas fa-arrow-left"></i>
            </button>
            <h1>Calendar Analytics</h1>
          </div>

          <div className="topbar-right">
            <Link to="/calendar-settings" className="btn-outline">
              <i className="fas fa-cog"></i>
              <span>Settings</span>
            </Link>
          </div>
        </div>
      </header>

      {/* Analytics Dashboard */}
      <CalendarAnalytics />
    </div>
  );
}
