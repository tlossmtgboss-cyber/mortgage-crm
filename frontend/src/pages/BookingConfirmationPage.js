/**
 * BookingConfirmationPage - Standalone public page for viewing a booking confirmation.
 *
 * Route: /booking/confirmation/:appointmentId?token=xxx
 *
 * Reads appointmentId from URL params and token from query string,
 * then renders the BookingConfirmation component which fetches data from the API.
 */

import React from 'react';
import { useParams, useSearchParams, useNavigate } from 'react-router-dom';
import BookingConfirmation from '../components/calendar/BookingConfirmation';
import '../pages/PublicBooking.css';

const BookingConfirmationPage = () => {
  const { appointmentId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const token = searchParams.get('token');
  const parsedId = parseInt(appointmentId, 10);

  if (!token || isNaN(parsedId)) {
    return (
      <div className="redfin-booking">
        <div className="booking-container confirmation-container" style={{ textAlign: 'center' }}>
          <h2 style={{ fontSize: '20px', fontWeight: 600, color: '#1a1a1a', marginBottom: '12px' }}>
            Invalid Confirmation Link
          </h2>
          <p style={{ color: '#666', fontSize: '14px', marginBottom: '24px' }}>
            This confirmation link is missing required information. Please check
            your email for the correct link.
          </p>
          <button
            className="primary-button"
            style={{ maxWidth: '240px', margin: '0 auto' }}
            onClick={() => navigate('/')}
          >
            Go to Home
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="redfin-booking">
      <div className="booking-container confirmation-container">
        <BookingConfirmation
          appointmentId={parsedId}
          token={token}
          onGoHome={() => navigate('/')}
          onReschedule={null}
          onCancel={null}
        />

        {/* Footer */}
        <div className="booking-footer">
          <p>
            Powered by <strong>Perennia AI</strong>
          </p>
        </div>
      </div>
    </div>
  );
};

export default BookingConfirmationPage;
