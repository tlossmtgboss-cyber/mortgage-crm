import React from 'react';
import { toast } from '../../utils/toast';
import { API_BASE_URL } from './shared/constants';
import { getToken } from '../../utils/tokenStore';

const ClearDataSection = () => {
  return (
    <div className="clear-data-section">
      <div className="page-header">
        <div>
          <h2>Clear Dummy Data</h2>
          <p className="section-description">
            Remove all sample/test data to prepare for workflow-based tasks
          </p>
        </div>
      </div>

      <div className="warning-card" style={{background: '#fff3cd', border: '2px solid #ffc107', padding: '24px', borderRadius: '8px', marginBottom: '24px'}}>
        <div style={{display: 'flex', alignItems: 'start', gap: '16px'}}>
          <div>
            <h3 style={{margin: '0 0 12px 0', color: '#856404'}}>Warning: This action cannot be undone!</h3>
            <p style={{margin: '0 0 12px 0', color: '#856404'}}>This will permanently delete:</p>
            <ul style={{margin: '0', paddingLeft: '20px', color: '#856404'}}>
              <li>All outstanding tasks (AI tasks, regular tasks, process tasks)</li>
              <li>All pending approval reconciliation events</li>
              <li>All unified messages (SMS, Email, Teams)</li>
              <li>All loans and leads</li>
              <li>All activities, conversations, and referral partners</li>
              <li>Client for Life data (closed loans)</li>
            </ul>
            <p style={{margin: '12px 0 0 0', fontWeight: 'bold', color: '#856404'}}>
              Your user accounts and settings will be preserved.
            </p>
          </div>
        </div>
      </div>

      <div className="info-card" style={{marginBottom: '24px'}}>
        <div className="info-content">
          <h3>What happens after clearing?</h3>
          <p>After clearing all dummy data, you'll have a clean slate to:</p>
          <ul>
            <li>Create tasks based on your actual loan workflow</li>
            <li>Import real leads and loans</li>
            <li>Start with production-ready data</li>
            <li>Test your workflow from scratch</li>
          </ul>
        </div>
      </div>

      <div style={{display: 'flex', gap: '16px', justifyContent: 'center', padding: '32px'}}>
        <button
          className="btn-danger"
          onClick={async () => {
            try {
              const response = await fetch(`${API_BASE_URL}/api/v1/admin/clear-sample-data`, {
                method: 'POST',
                headers: {
                  'Authorization': `Bearer ${getToken()}`,
                  'Content-Type': 'application/json'
                }
              });

              if (response.ok) {
                const result = await response.json();
                toast.success(`Success! Cleared:\n` +
                  `- ${result.deleted.tasks || 0} tasks\n` +
                  `- ${result.deleted.ai_tasks || 0} AI tasks\n` +
                  `- ${result.deleted.process_tasks || 0} process tasks\n` +
                  `- ${result.deleted.reconciliation_events || 0} reconciliation events\n` +
                  `- ${result.deleted.sms_messages || 0} SMS messages\n` +
                  `- ${result.deleted.email_messages || 0} emails\n` +
                  `- ${result.deleted.teams_messages || 0} Teams messages\n` +
                  `- ${result.deleted.loans || 0} loans\n` +
                  `- ${result.deleted.leads || 0} leads\n` +
                  `- ${result.deleted.activities || 0} activities\n\n` +
                  `Your CRM is now ready for workflow-based tasks!`);
              } else {
                const error = await response.json();
                toast.error(`Error: ${error.detail || 'Failed to clear data'}`);
              }
            } catch (error) {
              console.error('Error clearing data:', error);
              toast.error(`Error clearing data: ${error.message}`);
            }
          }}
          style={{
            padding: '16px 48px', fontSize: '18px', fontWeight: 'bold',
            background: '#dc3545', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer'
          }}
        >
          Clear All Dummy Data
        </button>
      </div>
    </div>
  );
};

export default ClearDataSection;
