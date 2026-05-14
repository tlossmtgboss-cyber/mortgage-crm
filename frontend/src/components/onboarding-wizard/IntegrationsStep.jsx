import React from 'react';
import { getToken } from '../../utils/tokenStore';
import { toast } from '../../utils/toast';

const INTEGRATIONS_LIST = [
  { id: 'calendly', name: 'Calendly', icon: '📅', category: 'Calendar', description: 'Automated appointment scheduling' },
  { id: 'google-calendar', name: 'Google Calendar', icon: '📅', category: 'Calendar', description: 'Sync your Google Calendar events' },
  { id: 'outlook-calendar', name: 'Outlook Calendar', icon: '📅', category: 'Calendar', description: 'Microsoft Outlook calendar integration' },
  { id: 'gmail', name: 'Gmail', icon: '📧', category: 'Email', description: 'Connect your Gmail account' },
  { id: 'outlook', name: 'Microsoft 365', icon: '📧', category: 'Email', description: 'Outlook and Microsoft 365 email' },
  { id: 'yahoo', name: 'Yahoo Mail', icon: '📧', category: 'Email', description: 'Yahoo email integration' },
  { id: 'telnyx', name: 'Telnyx', icon: '📞', category: 'Phone', description: 'AI calling, SMS, and voice' },
  { id: 'ringcentral', name: 'RingCentral', icon: '📞', category: 'Phone', description: 'Business phone system' },
  { id: 'dialpad', name: 'Dialpad', icon: '📞', category: 'Phone', description: 'Cloud-based phone system' },
  { id: 'docusign', name: 'DocuSign', icon: '📝', category: 'Documents', description: 'Electronic signature platform' },
  { id: 'adobe-sign', name: 'Adobe Sign', icon: '📝', category: 'Documents', description: 'Adobe document signing' },
  { id: 'dropbox', name: 'Dropbox', icon: '📁', category: 'Documents', description: 'Cloud file storage' },
  { id: 'google-drive', name: 'Google Drive', icon: '📁', category: 'Documents', description: 'Google cloud storage' },
  { id: 'encompass', name: 'Encompass', icon: '🏢', category: 'LOS', description: 'ICE Mortgage Technology LOS', optional: true },
  { id: 'calyx-point', name: 'Calyx Point', icon: '🏢', category: 'LOS', description: 'Calyx loan origination', optional: true },
  { id: 'bytepro', name: 'BytePro', icon: '🏢', category: 'LOS', description: 'BytePro LOS integration', optional: true },
  { id: 'salesforce', name: 'Salesforce', icon: '☁️', category: 'CRM', description: 'Salesforce CRM integration', optional: true },
  { id: 'hubspot', name: 'HubSpot', icon: '🎯', category: 'CRM', description: 'HubSpot marketing & CRM', optional: true },
  { id: 'experian', name: 'Experian', icon: '💳', category: 'Credit', description: 'Experian credit reports', optional: true },
  { id: 'equifax', name: 'Equifax', icon: '💳', category: 'Credit', description: 'Equifax credit data', optional: true },
  { id: 'transunion', name: 'TransUnion', icon: '💳', category: 'Credit', description: 'TransUnion credit services', optional: true },
  { id: 'slack', name: 'Slack', icon: '💬', category: 'Communication', description: 'Team messaging and alerts' },
  { id: 'teams', name: 'Microsoft Teams', icon: '💬', category: 'Communication', description: 'Microsoft Teams chat' },
  { id: 'quickbooks', name: 'QuickBooks', icon: '💰', category: 'Accounting', description: 'QuickBooks accounting', optional: true },
  { id: 'xero', name: 'Xero', icon: '💰', category: 'Accounting', description: 'Xero accounting software', optional: true }
];

const IntegrationsStep = ({ formData, setFormData, setConnectionModal }) => {
  const handleConnectIntegration = async (integration) => {
    if (integration.id === 'salesforce') {
      try {
        const token = getToken();
        const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
        const API_BASE_URL = isProduction ? 'https://api.perenniaai.com' : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

        const response = await fetch(`${API_BASE_URL}/api/v1/salesforce/oauth/start`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });

        if (!response.ok) throw new Error('Failed to initiate Salesforce OAuth');
        const data = await response.json();

        const width = 600, height = 700;
        const left = (window.screen.width - width) / 2;
        const top = (window.screen.height - height) / 2;
        const popup = window.open(data.auth_url, 'Salesforce OAuth', `width=${width},height=${height},left=${left},top=${top}`);

        const checkPopup = setInterval(() => {
          if (popup && popup.closed) {
            clearInterval(checkPopup);
            checkConnection('salesforce', `${API_BASE_URL}/api/v1/salesforce/status`, token);
          }
        }, 1000);
      } catch (error) {
        console.error('Salesforce OAuth error:', error);
        toast.error('Failed to connect to Salesforce. Please ensure the integration is configured in your environment.');
      }
    } else if (integration.id === 'outlook') {
      try {
        const token = getToken();
        const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
        const API_BASE_URL = isProduction ? 'https://api.perenniaai.com' : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

        const response = await fetch(`${API_BASE_URL}/api/v1/microsoft/oauth/start`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });

        if (!response.ok) throw new Error('Failed to initiate Microsoft 365 OAuth');
        const data = await response.json();

        const width = 600, height = 700;
        const left = (window.screen.width - width) / 2;
        const top = (window.screen.height - height) / 2;
        const popup = window.open(data.auth_url, 'Microsoft 365 Login', `width=${width},height=${height},left=${left},top=${top}`);

        const checkPopup = setInterval(() => {
          if (popup && popup.closed) {
            clearInterval(checkPopup);
            checkConnection('microsoft', `${API_BASE_URL}/api/v1/microsoft/status`, token);
          }
        }, 1000);
      } catch (error) {
        console.error('Microsoft 365 OAuth error:', error);
        toast.success('Microsoft 365 integration is being configured. Please go to Settings > Integrations to complete the connection with proper OAuth authentication.');
      }
    } else {
      setConnectionModal(integration);
    }
  };

  const checkConnection = async (type, statusUrl, token) => {
    try {
      const response = await fetch(statusUrl, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const data = await response.json();
        if (data.connected) {
          const label = type === 'salesforce' ? 'Salesforce' : 'Microsoft 365';
          const extra = type === 'microsoft' && data.email_address ? ` Your email: ${data.email_address}` : '';
          toast.success(`${label} connected successfully!${extra}`);
          setFormData(prevData => ({
            ...prevData,
            [`${type}Connected`]: true
          }));
        }
      }
    } catch (error) {
      console.error(`Error checking ${type} status:`, error);
    }
  };

  const categories = [...new Set(INTEGRATIONS_LIST.map(i => i.category))];

  return (
    <div className="step-content">
      <div className="step-header">
        <div className="step-icon">🔗</div>
        <h2>Integrations</h2>
        <p className="step-description">Connect your tools and services</p>
      </div>

      {categories.map(category => (
        <div key={category} className="integration-category">
          <h3 className="category-title">{category}</h3>
          <div className="integrations-grid">
            {INTEGRATIONS_LIST
              .filter(integration => integration.category === category)
              .map(integration => (
                <div key={integration.id} className={`integration-card ${integration.optional ? 'optional' : ''}`}>
                  <div className="integration-header">
                    <span className="integration-icon">{integration.icon}</span>
                    <h4>{integration.name}</h4>
                    {integration.optional && <span className="optional-badge">Optional</span>}
                  </div>
                  <p className="integration-description">{integration.description}</p>
                  <button
                    className="btn-connect"
                    onClick={() => handleConnectIntegration(integration)}
                  >
                    Connect {integration.name}
                  </button>
                </div>
              ))}
          </div>
        </div>
      ))}
    </div>
  );
};

export default IntegrationsStep;
