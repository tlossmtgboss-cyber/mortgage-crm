import React from 'react';

/**
 * SLA Dates tab — milestone dates and status history.
 */
function SLADatesTab({ formData, handleFieldChange, stageHistory, stageHistoryLoading }) {
  const dateFields = [
    ['New Lead', 'lead_received_date'],
    ['Attempted Contact', 'first_contact_attempt_date'],
    ['Application Complete', 'application_completed_date'],
    ['Initial Consultation', 'initial_consultation_date'],
    ['Pre-Qualified', 'lead_qualification_date'],
    ['Pre-Approved', 'preapproval_issued_date'],
  ];

  return (
    <div className="tab-content sla-dates-tab">
      <div className="sla-dates-compact">
        <div className="sla-section-header">SLA Milestone Dates</div>
        <div className="dates-grid">
          {dateFields.map(([label, key]) => (
            <div className="date-field" key={key}>
              <label>{label}</label>
              <input
                type="datetime-local"
                value={formData[key] ? formData[key].slice(0, 16) : ''}
                onChange={(e) => handleFieldChange(key, e.target.value)}
              />
            </div>
          ))}
        </div>

        <div className="sla-section-header" style={{ marginTop: '8px' }}>Status History</div>
        {stageHistoryLoading ? (
          <div className="loading-state" style={{ fontSize: '11px', padding: '6px' }}>Loading...</div>
        ) : stageHistory.length === 0 ? (
          <div className="empty-timeline">
            <p>No status changes recorded yet.</p>
          </div>
        ) : (
          <div className="status-timeline status-timeline-compact">
            {stageHistory.slice(0, 5).map((entry, index) => (
              <div key={entry.id || index} className="timeline-entry" style={{ padding: '2px 0', fontSize: '11px' }}>
                <span className="stage-change" style={{ marginRight: '8px' }}>
                  {entry.from_stage ? (
                    <>{entry.from_stage} → {entry.to_stage}</>
                  ) : (
                    <>Started: {entry.to_stage}</>
                  )}
                </span>
                <span style={{ color: '#888', fontSize: '10px' }}>
                  {new Date(entry.changed_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default SLADatesTab;
