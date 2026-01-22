/**
 * Scheduling Tab
 *
 * Displays calendar and scheduling information captured by the Receptionist Agent:
 * - Scheduled appointments detected from calls
 * - Follow-up calls to schedule
 * - Calendar actions for the PA
 * - Meeting summaries
 *
 * Coordinates with the Production Assistant to manage the LO's calendar.
 */

import React, { useState } from 'react';

const SchedulingTab = ({
  appointments = [],
  followUpCalls = [],
  calendarActions = [],
  meetingSummaries = [],
  onApproveAppointment,
  onRejectAppointment,
  onCreateCalendarEvent,
}) => {
  const [expandedAppointment, setExpandedAppointment] = useState(null);

  // Format meeting type icon
  const getMeetingTypeIcon = (type) => {
    switch (type) {
      case 'phone':
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
            <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 16.92z" />
          </svg>
        );
      case 'video':
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
            <polygon points="23,7 16,12 23,17" />
            <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
          </svg>
        );
      case 'in_person':
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
            <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" />
            <circle cx="12" cy="7" r="4" />
          </svg>
        );
      default:
        return (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
            <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
            <line x1="16" y1="2" x2="16" y2="6" />
            <line x1="8" y1="2" x2="8" y2="6" />
            <line x1="3" y1="10" x2="21" y2="10" />
          </svg>
        );
    }
  };

  // Get confirmation status badge
  const getStatusBadge = (status) => {
    switch (status) {
      case 'confirmed':
        return <span className="status-badge status-confirmed">Confirmed</span>;
      case 'tentative':
        return <span className="status-badge status-tentative">Tentative</span>;
      case 'needs_confirmation':
        return <span className="status-badge status-needs-confirmation">Needs Confirmation</span>;
      default:
        return <span className="status-badge status-pending">Pending</span>;
    }
  };

  // Get priority badge
  const getPriorityBadge = (priority) => {
    if (priority === 'high') return <span className="priority-badge priority-high">High</span>;
    if (priority === 'medium') return <span className="priority-badge priority-medium">Medium</span>;
    return null;
  };

  // Format appointment type label
  const formatAppointmentType = (type) => {
    const labels = {
      follow_up_call: 'Follow-Up Call',
      application_call: 'Application Call',
      document_review: 'Document Review',
      pre_approval_call: 'Pre-Approval Call',
      closing_prep: 'Closing Prep',
      general_meeting: 'Meeting',
    };
    return labels[type] || type?.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) || 'Appointment';
  };

  // Format participant role
  const formatRole = (role) => {
    const labels = {
      loan_officer: 'LO',
      borrower: 'Borrower',
      co_borrower: 'Co-Borrower',
      realtor: 'Realtor',
      pa: 'PA',
      production_assistant: 'PA',
      processor: 'Processor',
    };
    return labels[role] || role;
  };

  const hasContent = appointments.length > 0 || followUpCalls.length > 0 ||
    calendarActions.length > 0 || meetingSummaries.length > 0;

  if (!hasContent) {
    return (
      <div className="scheduling-tab scheduling-tab-empty">
        <div className="empty-state">
          <div className="empty-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
              <line x1="16" y1="2" x2="16" y2="6" />
              <line x1="8" y1="2" x2="8" y2="6" />
              <line x1="3" y1="10" x2="21" y2="10" />
            </svg>
          </div>
          <h3>No Scheduling Detected</h3>
          <p>When appointments are discussed or agreed upon during calls, they will appear here for calendar scheduling.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="scheduling-tab">
      {/* Scheduling Summary */}
      {meetingSummaries.length > 0 && (
        <div className="scheduling-summary">
          <h4>Scheduling Summary</h4>
          <p>{meetingSummaries[0].content}</p>
        </div>
      )}

      {/* Scheduled Appointments */}
      {appointments.length > 0 && (
        <div className="scheduling-section">
          <h4>Appointments Detected</h4>
          <div className="appointments-list">
            {appointments.map((apt, index) => (
              <div
                key={index}
                className={`appointment-card ${expandedAppointment === index ? 'expanded' : ''}`}
              >
                <div
                  className="appointment-header"
                  onClick={() => setExpandedAppointment(expandedAppointment === index ? null : index)}
                >
                  <div className="apt-icon">
                    {getMeetingTypeIcon(apt.structured_data?.meeting_type)}
                  </div>
                  <div className="apt-main">
                    <span className="apt-title">{apt.title || formatAppointmentType(apt.structured_data?.appointment_type)}</span>
                    <span className="apt-type">{formatAppointmentType(apt.structured_data?.appointment_type)}</span>
                  </div>
                  <div className="apt-status">
                    {getStatusBadge(apt.structured_data?.confirmation_status)}
                  </div>
                  <div className="apt-expand">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                      <polyline points={expandedAppointment === index ? "18,15 12,9 6,15" : "6,9 12,15 18,9"} />
                    </svg>
                  </div>
                </div>

                {expandedAppointment === index && (
                  <div className="appointment-details">
                    {/* Date/Time */}
                    {apt.structured_data?.proposed_datetime && (
                      <div className="detail-row">
                        <span className="detail-label">When:</span>
                        <span className="detail-value">{apt.structured_data.proposed_datetime}</span>
                      </div>
                    )}

                    {/* Duration */}
                    <div className="detail-row">
                      <span className="detail-label">Duration:</span>
                      <span className="detail-value">{apt.structured_data?.duration_minutes || 30} minutes</span>
                    </div>

                    {/* Meeting Type */}
                    <div className="detail-row">
                      <span className="detail-label">Type:</span>
                      <span className="detail-value meeting-type">
                        {getMeetingTypeIcon(apt.structured_data?.meeting_type)}
                        {apt.structured_data?.meeting_type?.replace(/_/g, ' ') || 'Phone'}
                      </span>
                    </div>

                    {/* Participants */}
                    {apt.structured_data?.participants?.length > 0 && (
                      <div className="detail-row">
                        <span className="detail-label">Participants:</span>
                        <div className="participants-list">
                          {apt.structured_data.participants.map((p, i) => (
                            <span key={i} className={`participant ${p.required ? 'required' : 'optional'}`}>
                              {p.name || formatRole(p.role)}
                              {p.required && <span className="required-mark">*</span>}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Description */}
                    {apt.content && (
                      <div className="detail-row description">
                        <span className="detail-label">Details:</span>
                        <span className="detail-value">{apt.content}</span>
                      </div>
                    )}

                    {/* Notes */}
                    {apt.structured_data?.notes && (
                      <div className="detail-row notes">
                        <span className="detail-label">Notes:</span>
                        <span className="detail-value">{apt.structured_data.notes}</span>
                      </div>
                    )}

                    {/* Who sends invite */}
                    <div className="detail-row">
                      <span className="detail-label">Send Invite:</span>
                      <span className="detail-value">{apt.structured_data?.who_will_send_invite || 'PA'}</span>
                    </div>

                    {/* Action Buttons */}
                    {apt.approval_status === 'pending' && (
                      <div className="appointment-actions">
                        <button
                          className="btn btn-primary"
                          onClick={() => onApproveAppointment && onApproveAppointment([apt.id])}
                        >
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                            <polyline points="20,6 9,17 4,12" />
                          </svg>
                          Approve & Create Event
                        </button>
                        <button
                          className="btn btn-secondary"
                          onClick={() => onRejectAppointment && onRejectAppointment([apt.id], 'User rejected')}
                        >
                          Reject
                        </button>
                      </div>
                    )}

                    {apt.approval_status === 'approved' && (
                      <div className="approved-badge">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                          <polyline points="22,4 12,14.01 9,11.01" />
                        </svg>
                        Approved - Calendar event will be created
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Follow-Up Calls */}
      {followUpCalls.length > 0 && (
        <div className="scheduling-section">
          <h4>Follow-Up Reminders</h4>
          <div className="followup-list">
            {followUpCalls.map((followup, index) => (
              <div key={index} className="followup-card">
                <div className="followup-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="10" />
                    <polyline points="12,6 12,12 16,14" />
                  </svg>
                </div>
                <div className="followup-content">
                  <h5>{followup.title?.replace('Follow-Up: ', '') || 'Follow-Up'}</h5>
                  {followup.structured_data?.trigger && (
                    <div className="trigger">
                      <span className="label">Trigger:</span>
                      <span className="value">{followup.structured_data.trigger}</span>
                    </div>
                  )}
                  {followup.structured_data?.action && (
                    <div className="action">
                      <span className="label">Action:</span>
                      <span className="value">{followup.structured_data.action}</span>
                    </div>
                  )}
                  {followup.structured_data?.suggested_timing && (
                    <div className="timing">
                      <span className="label">When:</span>
                      <span className="value">{followup.structured_data.suggested_timing}</span>
                    </div>
                  )}
                  {followup.structured_data?.participants?.length > 0 && (
                    <div className="participants">
                      <span className="label">With:</span>
                      <span className="value">{followup.structured_data.participants.join(', ')}</span>
                    </div>
                  )}
                </div>
                {getPriorityBadge(followup.priority)}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Calendar Actions for PA */}
      {calendarActions.length > 0 && (
        <div className="scheduling-section">
          <h4>PA Calendar Actions</h4>
          <div className="calendar-actions-list">
            {calendarActions.map((action, index) => (
              <div key={index} className="calendar-action-card">
                <div className="action-type-badge">
                  {action.structured_data?.action_type?.replace(/_/g, ' ') || 'Action'}
                </div>
                <div className="action-details">
                  <p>{action.content || action.structured_data?.details}</p>
                  {action.structured_data?.assign_to && (
                    <span className="assigned-to">
                      Assigned to: {action.structured_data.assign_to}
                    </span>
                  )}
                </div>
                {getPriorityBadge(action.structured_data?.priority || action.priority)}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default SchedulingTab;
