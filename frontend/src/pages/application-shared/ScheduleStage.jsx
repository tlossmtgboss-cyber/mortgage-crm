/**
 * ScheduleStage - Shared consultation booking, e-consent, credit auth, and submission.
 * Used by both Purchase and Refinance applications.
 * Steps: 1) Calendar 2) E-Consent 3) Credit Auth + Submit 4) Confirmation
 */

import React from 'react';
import { toast } from 'react-toastify';

export default function ScheduleStage({
  applicationType = 'purchase',
  API_URL,
  profileData,
  calendarAssignment,
  scheduleStep,
  setScheduleStep,
  selectedTimeSlot,
  setSelectedTimeSlot,
  bookingWeekStart,
  setBookingWeekStart,
  bookingSelectedDate,
  setBookingSelectedDate,
  bookingSelectedTime,
  setBookingSelectedTime,
  bookingSlots,
  setBookingSlots,
  bookingLoading,
  setBookingLoading,
  bookingConfirmed,
  setBookingConfirmed,
  bookingError,
  setBookingError,
  eConsentAgreed,
  setEConsentAgreed,
  creditAuthAgreed,
  setCreditAuthAgreed,
  isSubmitting,
  submitError,
  handleSubmitApplication,
  showMicroWinAnimation,
  goToPrevStage,
  generateTimeSlots,
  Icon,
  nextSteps,
}) {
  const isRefi = applicationType === 'refinance';
  const optionsLabel = isRefi ? 'refinance options' : 'mortgage options';
  const timeSlots = generateTimeSlots();

  // ----- Step 1: Calendar Selection -----
  if (scheduleStep === 1) {
    const bookingSlug = calendarAssignment?.booking_link_slug;
    const calendlyUrl = calendarAssignment?.calendly_url;

    // Booking link helpers
    const getWeekDates = () => {
      const dates = [];
      const start = new Date(bookingWeekStart);
      start.setHours(0, 0, 0, 0);
      for (let i = 0; i < 7; i++) {
        const d = new Date(start);
        d.setDate(start.getDate() + i);
        dates.push(d);
      }
      return dates;
    };

    const isPastDate = (d) => {
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      return d < today;
    };

    const isTodayDate = (d) => d.toDateString() === new Date().toDateString();

    const formatDayName = (d) => d.toLocaleDateString('en-US', { weekday: 'short' }).toUpperCase();
    const formatDayNumber = (d) => d.getDate();
    const formatMonth = (d) => d.toLocaleDateString('en-US', { month: 'short' }).toUpperCase();
    const formatSlotTime = (timeStr) => {
      const dt = new Date(timeStr);
      return dt.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
    };

    const prevWeek = () => {
      const newStart = new Date(bookingWeekStart);
      newStart.setDate(bookingWeekStart.getDate() - 7);
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      if (newStart >= today) setBookingWeekStart(newStart);
    };

    const nextWeek = () => {
      const newStart = new Date(bookingWeekStart);
      newStart.setDate(bookingWeekStart.getDate() + 7);
      setBookingWeekStart(newStart);
    };

    const fetchBookingSlots = async (date) => {
      setBookingLoading(true);
      setBookingError(null);
      try {
        const dateStr = date.toISOString().split('T')[0];
        const response = await fetch(
          `${API_URL}/api/v1/scheduler/public/book/${bookingSlug}/slots?date=${dateStr}`
        );
        if (response.ok) {
          const data = await response.json();
          const slots = (data.available_slots || []).map(slot => ({
            ...slot,
            start_time: slot.start,
            display: formatSlotTime(slot.start)
          }));
          setBookingSlots(slots);
          if (slots.length > 0) setBookingSelectedTime(slots[0].start_time);
          else setBookingSelectedTime('');
        }
      } catch (err) {
        console.error('Error fetching booking slots:', err);
        setBookingError('Failed to load available times');
      } finally {
        setBookingLoading(false);
      }
    };

    const handleDateSelect = (date) => {
      setBookingSelectedDate(date);
      setBookingSelectedTime('');
      setBookingSlots([]);
      fetchBookingSlots(date);
    };

    const handleConfirmBooking = async () => {
      if (!bookingSelectedTime) return;
      setBookingLoading(true);
      setBookingError(null);
      try {
        const response = await fetch(`${API_URL}/api/v1/scheduler/public/book/${bookingSlug}/confirm`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            start_time: bookingSelectedTime,
            duration_minutes: 30,
            attendee_name: `${profileData?.firstName || ''} ${profileData?.lastName || ''}`.trim() || 'Applicant',
            attendee_email: profileData?.email || '',
            attendee_phone: profileData?.phone || '',
            notes: `Booked from ${isRefi ? 'Refinance' : 'Purchase'} Application`,
            meeting_mode: 'video'
          })
        });

        if (!response.ok) {
          const data = await response.json();
          throw new Error(data.detail || 'Failed to book appointment');
        }

        setBookingConfirmed(true);
        showMicroWinAnimation('Consultation Scheduled!');
        setScheduleStep(2);
      } catch (err) {
        console.error('Error confirming booking:', err);
        setBookingError(err.message || 'Failed to book appointment');
      } finally {
        setBookingLoading(false);
      }
    };

    const weekDates = bookingSlug ? getWeekDates() : [];

    return (
      <div className="stage-content scheduling-page">
        <div className="scheduling-header">
          <h2>Schedule Your Consultation</h2>
          <p>Let's find a time that works for you to discuss your {optionsLabel}.</p>
        </div>

        <div className="calendar-section">
          {bookingSlug ? (
            <div className="booking-slot-picker">
              <h4>Pick a Date</h4>
              <div className="booking-week-picker">
                <button className="week-nav-btn" onClick={prevWeek} disabled={isPastDate(weekDates[0])}>
                  &#8249;
                </button>
                <div className="booking-week-dates">
                  {weekDates.map((date, idx) => {
                    const disabled = isPastDate(date);
                    const selected = bookingSelectedDate && date.toDateString() === bookingSelectedDate.toDateString();
                    return (
                      <button
                        key={idx}
                        className={`booking-date-card ${selected ? 'selected' : ''} ${disabled ? 'disabled' : ''} ${isTodayDate(date) ? 'today' : ''}`}
                        onClick={() => !disabled && handleDateSelect(date)}
                        disabled={disabled}
                      >
                        <span className="booking-day-name">{formatDayName(date)}</span>
                        <span className="booking-day-number">{formatDayNumber(date)}</span>
                        <span className="booking-month">{formatMonth(date)}</span>
                      </button>
                    );
                  })}
                </div>
                <button className="week-nav-btn" onClick={nextWeek}>
                  &#8250;
                </button>
              </div>

              {bookingSelectedDate && (
                <div className="booking-time-section">
                  <h4>Pick a Time</h4>
                  {bookingLoading ? (
                    <div className="booking-loading">Loading available times...</div>
                  ) : bookingError ? (
                    <div className="booking-error">{bookingError}</div>
                  ) : bookingSlots.length === 0 ? (
                    <div className="booking-no-slots">No times available for this date. Try another day.</div>
                  ) : (
                    <>
                      <div className="booking-time-grid">
                        {bookingSlots.map((slot, idx) => (
                          <button
                            key={idx}
                            className={`booking-time-btn ${bookingSelectedTime === slot.start_time ? 'selected' : ''}`}
                            onClick={() => setBookingSelectedTime(slot.start_time)}
                          >
                            {slot.display}
                          </button>
                        ))}
                      </div>

                      <button
                        className="btn-schedule"
                        disabled={!bookingSelectedTime || bookingLoading}
                        onClick={handleConfirmBooking}
                      >
                        {bookingLoading ? 'Booking...' : 'Confirm Appointment'}
                      </button>
                    </>
                  )}
                </div>
              )}
            </div>
          ) : calendlyUrl ? (
            <div className="calendly-embed-container">
              <iframe
                src={`${calendlyUrl}?hide_gdpr_banner=1&hide_event_type_details=1`}
                width="100%"
                height="630"
                frameBorder="0"
                title="Schedule Consultation"
                style={{ minWidth: '320px', borderRadius: '8px' }}
              ></iframe>
              <div className="calendly-skip-option">
                <p>After scheduling, click Continue to proceed with your application.</p>
                <button
                  className="btn-schedule"
                  onClick={() => {
                    showMicroWinAnimation('Moving to next step!');
                    setScheduleStep(2);
                  }}
                >
                  Continue &rarr;
                </button>
              </div>
            </div>
          ) : (
            <div className="calendar-placeholder">
              <span className="cal-icon"><Icon name="calendar" size={48} /></span>
              <h4>Pick a Time That Works For You</h4>
              <p>We want to coordinate a time to review {isRefi ? 'your refinance options' : 'the application with you'}. Choose a time that is most convenient for you.</p>

              <div className="time-slots">
                {timeSlots.map(slot => (
                  <div
                    key={slot.id}
                    className={`time-slot ${selectedTimeSlot === slot.id ? 'selected' : ''}`}
                    onClick={() => setSelectedTimeSlot(slot.id)}
                  >
                    <div className="time-slot-time">{slot.time}</div>
                    <div className="time-slot-date">{slot.date}</div>
                  </div>
                ))}
              </div>

              <button
                className="btn-schedule"
                disabled={!selectedTimeSlot}
                onClick={() => {
                  showMicroWinAnimation('Consultation Scheduled!');
                  setScheduleStep(2);
                }}
              >
                {selectedTimeSlot ? 'Confirm Appointment' : 'Select a Time Slot'}
              </button>
            </div>
          )}
        </div>

        <div className="stage-navigation">
          <button className="btn-back" onClick={goToPrevStage}>&larr; Back</button>
        </div>
      </div>
    );
  }

  // ----- Step 2: E-Consent Page -----
  if (scheduleStep === 2) {
    return (
      <div className="stage-content scheduling-page">
        <div className="scheduling-header">
          <h2>E-Consent Documentation</h2>
          <p>Please review and consent to receive documents electronically.</p>
        </div>

        <div className="econsent-section econsent-full-page">
          <div className="econsent-content">
            <p className="econsent-intro">
              To use electronic signatures and receive documents electronically in connection with your use of this
              platform, you must read and consent to the terms outlined in this document, which require your ability to
              access and retain electronic documents.
            </p>

            <div className="econsent-scrollbox">
              <p>
                This eConsent, if you provide it, applies to your use of this Platform on any Access Device, including a
                desktop, laptop, tablet, mobile, or any other electronic device, and to any Document, including loan
                documents, disclosures (initial disclosures, pre-close disclosures, closing disclosures), records, and servicing
                notices, and any other loan documents that we provide to you in electronic form.
              </p>

              <p>
                If you provide eConsent, we will be able to provide electronic Documents to you within this platform, in
                other portals, and/or through other methods we may use for delivery of electronic Documents. With Your
                eConsent, You will also be able to sign and authorize these Documents electronically, rather than on paper.
                Anytime you are signing using a platform contracted with nCino Mortgage, you will be prompted to provide
                eConsent again.
              </p>

              <p>
                Before We can engage in this transaction electronically, it is important that You understand Your rights and
                responsibilities. Please read the following and affirm Your consent to conduct business with Us electronically.
                For purposes of this eConsent Agreement, 'You' and 'Your' mean the borrower(s) under the applicable loan to
                which such Documents apply, and 'We', 'Our' and 'Us' mean the applicable mortgage broker(s), loan
                processor(s), or mortgage banker(s) with whom You are transacting business for such loan(s).
              </p>

              <h4>Your Consent</h4>
              <p>
                Your consent to participate in this transaction electronically will apply to all Loan Documents for the
                applicable loans for which You are applying. If You provide Your consent by clicking the 'I agree'
                button at the bottom of the page, We will conduct this transaction electronically, instead of providing
                You with the Loan Documents in paper form.
              </p>
              <p>
                If a document related to Your loan is not available in electronic form, a paper copy will be provided to
                You free of charge.
              </p>
              <p>
                Conducting this transaction electronically is an option. If You choose not to receive Documents
                electronically, paper Documents will be mailed to You. Additionally: You will not be required to pay a
                fee for receiving paper copies of the Documents.
              </p>

              <h4>Withdrawal of Consent</h4>
              <p>
                You have the right to withdraw Your consent at any time. By declining or revoking Your consent to
                receive Documents electronically, We will provide You with the Documents in paper form.
              </p>
              <p>
                If You originally consent to receive Documents electronically, but later decide to withdraw Your
                consent, You can do so by clicking on the 'I do not agree' button, or by contacting Us by phone.
              </p>
              <p>
                If You originally consent to receive Documents electronically, but later withdraw Your consent, You
                will not be required to pay a fee for withdrawing consent and receiving paper copies of the Documents.
              </p>

              <h4>Obtaining Paper Copies</h4>
              <p>
                After Your consent is given, You may request from Us paper copies of Your Loan Documents by contacting Us.
                If You request paper copies of the Loan Documents, You will not be required to pay a fee for receiving
                paper copies of the Loan Documents.
              </p>

              <h4>System Requirements</h4>
              <p>
                In order to receive Documents electronically, You must have a computer with Internet access and an
                Internet email account and address; an Internet browser using 128-bit encryption or higher, Adobe
                Acrobat 7.0 or higher, SSL encryption and access to a printer or the ability to download information in
                order to keep copies of Your Documents electronically for Your records.
              </p>
              <p>
                If the software or hardware requirements change in the future, and You are unable to continue receiving
                Documents electronically, paper copies of such Loan Documents will be mailed to You once You
                notify Us that You are no longer able to access the Documents electronically because of the changed
                requirements. We will use commercially reasonable efforts to notify You before such requirements
                change. If You choose to withdraw Your consent upon notification of the change, You will be able to
                do so without penalty.
              </p>

              <h4>How Can We Reach You</h4>
              <p>
                You must promptly notify Us if there is a change in Your email address or in other information needed
                to contact You electronically.
              </p>
              <p>
                We will not assume liability for non-receipt of notification of the availability of Documents
                electronically in the event Your email address on file is invalid; Your email or Internet service provider
                filters the notification as 'spam' or 'junk mail'; there is a malfunction in Your computer, browser, Internet
                service and/or software; or for other reasons beyond Our control.
              </p>
            </div>

            <div className="econsent-actions">
              <button
                className={`econsent-btn agree ${eConsentAgreed ? 'selected' : ''}`}
                onClick={() => setEConsentAgreed(true)}
              >
                <Icon name="check" size={18} />
                I Agree
              </button>
              <button
                className="econsent-btn disagree"
                onClick={() => {
                  setEConsentAgreed(false);
                  toast.success('You have chosen not to consent to electronic documents. Paper documents will be mailed to you. You can still proceed with your application.');
                }}
              >
                I Do Not Agree
              </button>
            </div>
          </div>
        </div>

        <div className="stage-navigation">
          <button className="btn-back" onClick={() => setScheduleStep(1)}>&larr; Back</button>
          <button
            className="btn-continue"
            disabled={!eConsentAgreed}
            onClick={() => setScheduleStep(3)}
          >
            {eConsentAgreed ? 'Continue →' : 'Please Accept E-Consent to Continue'}
          </button>
        </div>
      </div>
    );
  }

  // ----- Step 3: Credit Authorization -----
  if (scheduleStep === 3) {
    return (
      <div className="stage-content scheduling-page">
        <div className="scheduling-header">
          <h2>Credit Authorization</h2>
          <p>Please authorize us to check your credit to provide accurate {optionsLabel}.</p>
        </div>

        <div className="econsent-section credit-auth-section econsent-full-page">
          <div className="econsent-content">
            <p className="econsent-intro">
              Your credit information will help us understand more about your personal and financial background and
              ensure we give you the most accurate {optionsLabel}. To help us, we need the following authorization:
            </p>

            <div className="credit-auth-box">
              <p>
                I authorize my Lender to perform a credit check, via either a soft or hard pull of my credit; I understand this
                may affect my credit score. I acknowledge that any owner of a completed loan, its servicers, successors and
                assigns, may verify or re-verify any information contained in this form or obtain any information or data
                relating to a completed loan, for any legitimate purpose, through any source, including a source named in this
                form or a consumer reporting agency.
              </p>
            </div>

            <div className="econsent-actions">
              <button
                className={`econsent-btn agree ${creditAuthAgreed ? 'selected' : ''}`}
                onClick={() => setCreditAuthAgreed(true)}
              >
                <Icon name="check" size={18} />
                I Authorize
              </button>
              <button
                className="econsent-btn disagree"
                onClick={() => {
                  setCreditAuthAgreed(false);
                  toast.error(`Credit authorization is required to process your ${isRefi ? 'refinance' : 'mortgage'} application. Without it, we cannot verify your creditworthiness.`);
                }}
              >
                I Do Not Authorize
              </button>
            </div>
          </div>
        </div>

        {submitError && (
          <div className="error-message" style={{
            color: '#dc3545',
            backgroundColor: '#f8d7da',
            padding: '12px 16px',
            borderRadius: '8px',
            marginBottom: '16px',
            textAlign: 'center'
          }}>
            {submitError}
          </div>
        )}

        <div className="submit-section">
          <button
            className="btn-submit"
            disabled={!creditAuthAgreed || isSubmitting}
            onClick={handleSubmitApplication}
          >
            {isSubmitting
              ? 'Submitting...'
              : creditAuthAgreed
                ? 'Submit Application'
                : 'Please Authorize Credit Check to Submit'}
          </button>
        </div>

        <div className="stage-navigation">
          <button className="btn-back" onClick={() => setScheduleStep(2)} disabled={isSubmitting}>&larr; Back</button>
        </div>
      </div>
    );
  }

  // ----- Step 4: Confirmation -----
  const defaultNextSteps = isRefi
    ? [
        { title: 'Consultation Call', description: "We'll review your refinance goals and answer questions" },
        { title: 'Rate Lock', description: 'Lock in your new rate once you\'re ready' },
        { title: 'Document Collection', description: 'Upload your documents through our secure portal' },
        { title: 'Appraisal', description: "We'll order and coordinate your home appraisal" },
        { title: 'Closing', description: 'Sign your new loan docs and start saving!' },
      ]
    : [
        { title: 'Consultation Call', description: "We'll review your application and answer any questions" },
        { title: 'Document Collection', description: 'Upload your documents through our secure portal' },
        { title: 'Pre-Approval Letter', description: 'Receive your pre-approval to make offers with confidence' },
        { title: 'Find Your Dream Home', description: 'Shop with confidence knowing your financing is ready' },
      ];

  const steps = nextSteps || defaultNextSteps;

  return (
    <div className="stage-content scheduling-page confirmation-page">
      <div className="scheduling-header">
        <div className="success-icon">
          <Icon name="check" size={48} />
        </div>
        <h2>Application Submitted!</h2>
        <p>Congratulations! Your {isRefi ? 'refinance' : 'mortgage'} application has been successfully submitted.</p>
      </div>

      {!isRefi && (
        <div className="video-section">
          <div className="video-container">
            <div className="video-placeholder">
              <span className="play-icon"><Icon name="play" size={48} /></span>
              <p>What to Expect: Your Home Buying Journey</p>
            </div>
          </div>
        </div>
      )}

      <div className="next-steps-list" style={isRefi ? { maxWidth: '600px', margin: '0 auto' } : undefined}>
        <h3><Icon name="clipboard" size={18} /> What Happens Next</h3>
        <ol>
          {steps.map((step, i) => (
            <li key={i}><strong>{step.title}</strong> - {step.description}</li>
          ))}
        </ol>
      </div>

      {!isRefi && (
        <div className="confirmation-message">
          <p><strong>Check your email</strong> for confirmation and document upload instructions.</p>
        </div>
      )}

      {isRefi && (
        <p style={{ textAlign: 'center', marginTop: '24px', color: '#666' }}>
          Redirecting you to your client portal...
        </p>
      )}
    </div>
  );
}
