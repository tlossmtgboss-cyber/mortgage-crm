import React from 'react';
import CalendarAnalytics from '../components/calendar/CalendarAnalytics';

/**
 * CalendarAnalyticsPage - Thin page wrapper for the CalendarAnalytics component.
 * Route: /calendar/analytics
 */
export default function CalendarAnalyticsPage() {
  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: '24px 16px' }}>
      <CalendarAnalytics />
    </div>
  );
}
