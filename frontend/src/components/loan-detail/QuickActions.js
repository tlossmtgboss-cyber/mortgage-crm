import React from 'react';

/**
 * Quick Actions sidebar panel — SMS, email, task, appointment, video, voicemail, etc.
 */
function QuickActions({
  handleAction,
  setShowSendVideoModal,
  clientPortalWorkspaceId,
  applicationLoading,
  salesforceStatus,
  salesforcePulling,
}) {
  return (
    <div className="actions-card">
      <h3>QUICK ACTIONS</h3>
      <div className="action-buttons">
        <button className="action-btn sms" onClick={() => handleAction('sms')} title="Send SMS">
          <span>SMS Text</span>
        </button>
        <button className="action-btn email" onClick={() => handleAction('email')} title="Send email">
          <span>Send Email</span>
        </button>
        <button className="action-btn task" onClick={() => handleAction('task')} title="Create task">
          <span>Create Task</span>
        </button>
        <button className="action-btn calendar" onClick={() => handleAction('calendar')} title="Set appointment">
          <span>Set Appointment</span>
        </button>
        <button className="action-btn video" onClick={() => handleAction('video')} title="Start video call">
          <span>Video Call</span>
        </button>
        <button className="action-btn voicemail" onClick={() => handleAction('voicemail')} title="Drop voicemail">
          <span>Voicemail Drop</span>
        </button>
        <button className="action-btn record-video" onClick={() => setShowSendVideoModal(true)} disabled={!clientPortalWorkspaceId} title={clientPortalWorkspaceId ? "Record and send a video message" : "No client portal available"}>
          <span>Record Video</span>
        </button>
        <button className="action-btn application" onClick={() => handleAction('send_application')} disabled={applicationLoading} title="Send application link">
          <span>{applicationLoading ? 'Creating...' : 'Send Application'}</span>
        </button>
        <button className="action-btn portal" onClick={() => handleAction('client_portal')} title="Access portals">
          <span>Portals</span>
        </button>
        <button className="action-btn escalation" onClick={() => handleAction('escalation')} title="Escalate issue">
          <span>Escalation</span>
        </button>
        {salesforceStatus?.is_linked && (
          <button
            className={`action-btn salesforce-pull ${salesforcePulling ? 'loading' : ''}`}
            onClick={() => handleAction('salesforce-pull')}
            title={`Sync from Salesforce (${salesforceStatus.salesforce_id})`}
            disabled={salesforcePulling}
          >
            <span>{salesforcePulling ? 'Syncing...' : 'Sync from SF'}</span>
          </button>
        )}
      </div>
    </div>
  );
}

export default QuickActions;
