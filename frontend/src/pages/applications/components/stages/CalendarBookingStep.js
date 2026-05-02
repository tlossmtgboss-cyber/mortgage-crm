import React, { useState, useCallback } from 'react';
import BookingWidget from '../../../../components/calendar/BookingWidget';

const CalendarBookingStep = ({ orgSlug, loSlug, loName, onBooked }) => {
  const [isBooked, setIsBooked] = useState(false);
  const [bookingDetails, setBookingDetails] = useState(null);

  const handleBookingComplete = useCallback((details) => {
    setIsBooked(true);
    setBookingDetails(details);
    if (onBooked) onBooked(details);
  }, [onBooked]);

  if (isBooked && bookingDetails) {
    // bookingDetails.date is a JS Date object; bookingDetails.time is a string
    const dateStr = bookingDetails.date instanceof Date
      ? bookingDetails.date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })
      : String(bookingDetails.date);

    return (
      <div className="calendar-booking-step calendar-booking-step--booked">
        <div className="booking-confirmed">
          <span className="booking-confirmed-icon">&#10003;</span>
          <div className="booking-confirmed-details">
            <strong>Consultation Scheduled</strong>
            <p>
              {dateStr} at {bookingDetails.time}
              {loName && ` with ${loName}`}
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="calendar-booking-step">
      <div className="calendar-booking-header">
        <h3 className="calendar-booking-title">Schedule a Consultation</h3>
        <p className="calendar-booking-subtitle">
          Book a time with {loName || 'your loan officer'} to review your application and discuss next steps.
        </p>
        <span className="calendar-booking-optional">Optional</span>
      </div>
      <div className="calendar-booking-widget">
        <BookingWidget
          orgSlug={orgSlug}
          loSlug={loSlug}
          onBooked={handleBookingComplete}
        />
      </div>
    </div>
  );
};

export default CalendarBookingStep;
