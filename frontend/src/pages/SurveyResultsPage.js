import React from 'react';
import { Link } from 'react-router-dom';
import SurveyResults from '../components/calendar/SurveyResults';

/**
 * SurveyResultsPage - Thin page wrapper for the SurveyResults component.
 * Route: /calendar/surveys
 */
export default function SurveyResultsPage() {
  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: '24px 16px' }}>
      <div style={{ marginBottom: 16 }}>
        <Link
          to="/calendar"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            fontSize: 14,
            color: '#3b82f6',
            textDecoration: 'none',
          }}
        >
          &larr; Back to Calendar
        </Link>
      </div>
      <SurveyResults />
    </div>
  );
}
