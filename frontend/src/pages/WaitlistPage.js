import React from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import WaitlistManager from '../components/calendar/WaitlistManager';
import { getToken } from '../utils/tokenStore';

/**
 * WaitlistPage - Standalone page wrapper for the WaitlistManager component.
 * Route: /calendar/waitlist
 *
 * Accepts an optional ?appointmentTypeId=xxx query parameter to filter
 * the waitlist to a specific appointment type.
 */
export default function WaitlistPage() {
  const [searchParams] = useSearchParams();
  const appointmentTypeId = searchParams.get('appointmentTypeId') || undefined;
  const token = getToken();

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto', padding: '24px 16px' }}>
      <div style={{ marginBottom: 16 }}>
        <Link
          to="/calendar-settings"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            fontSize: 14,
            color: '#3b82f6',
            textDecoration: 'none',
          }}
        >
          &larr; Back to Calendar Settings
        </Link>
      </div>

      <h1 style={{ fontSize: 22, fontWeight: 600, color: '#1e293b', marginBottom: 4 }}>
        Waitlist Management
      </h1>
      <p style={{ fontSize: 14, color: '#6b7280', marginBottom: 24 }}>
        Manage your appointment waitlist queue. Drag to reorder, offer available slots, or remove entries.
      </p>

      <div
        style={{
          background: '#fff',
          border: '1px solid #e5e7eb',
          borderRadius: 12,
          overflow: 'hidden',
        }}
      >
        <WaitlistManager appointmentTypeId={appointmentTypeId} token={token} />
      </div>
    </div>
  );
}
