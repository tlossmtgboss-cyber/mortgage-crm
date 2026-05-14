import React from 'react';

/**
 * Simple integration detail pages that are "coming soon" or have static forms.
 * Each is a pure presentational component receiving setActiveSection for navigation.
 */

export const TeamsDetail = () => (
  <div className="integration-detail-section">
    <h2>Microsoft Teams Integration</h2>
    <p className="section-description">Send messages, make calls, and collaborate with your team</p>
    <div className="integration-coming-soon"><h3>Coming Soon</h3><p>Microsoft Teams integration is currently in development</p></div>
  </div>
);

export const ZoomDetail = () => (
  <div className="integration-detail-section">
    <h2>Zoom Integration</h2>
    <p className="section-description">Host virtual meetings and consultations with clients</p>
    <div className="integration-connect-card">
      <h3>Connect Zoom</h3>
      <p>Connect your Zoom account to schedule and host virtual meetings with clients</p>
      <div className="connect-form">
        <div className="form-group"><label>Zoom API Key</label><input type="text" className="form-input" placeholder="Enter your Zoom API Key" /></div>
        <div className="form-group"><label>Zoom API Secret</label><input type="password" className="form-input" placeholder="Enter your Zoom API Secret" /></div>
        <button className="btn-connect">Connect Zoom</button>
      </div>
    </div>
    <div className="integration-features" style={{marginTop: '24px'}}>
      <h4>Features</h4>
      <ul><li>Schedule Zoom meetings from CRM</li><li>Auto-generate meeting links for appointments</li><li>Send meeting invites to clients</li><li>Track meeting attendance and duration</li></ul>
    </div>
    <div className="info-card" style={{marginTop: '24px'}}>
      <div className="info-content">
        <h3>How to get Zoom API credentials</h3>
        <ol>
          <li>Go to <a href="https://marketplace.zoom.us" target="_blank" rel="noopener noreferrer">Zoom App Marketplace</a></li>
          <li>Create a Server-to-Server OAuth app</li><li>Copy your API Key and Secret</li><li>Paste them in the form above</li>
        </ol>
      </div>
    </div>
  </div>
);

export const SalesforceDetail = () => (
  <div className="integration-detail-section">
    <h2>Salesforce Integration</h2>
    <p className="section-description">Sync contacts and deals with your Salesforce CRM</p>
    <div className="integration-connect-card">
      <h3>Connect Salesforce</h3>
      <p>Connect your Salesforce account to sync contacts, leads, and opportunities</p>
      <div className="connect-form">
        <div className="form-group"><label>Salesforce Instance URL</label><input type="text" className="form-input" placeholder="https://yourcompany.salesforce.com" /></div>
        <div className="form-group"><label>Consumer Key</label><input type="text" className="form-input" placeholder="Enter your Consumer Key" /></div>
        <div className="form-group"><label>Consumer Secret</label><input type="password" className="form-input" placeholder="Enter your Consumer Secret" /></div>
        <button className="btn-connect">Connect Salesforce</button>
      </div>
    </div>
    <div className="integration-features" style={{marginTop: '24px'}}>
      <h4>Features</h4>
      <ul><li>Two-way sync of contacts and leads</li><li>Sync opportunities and pipeline data</li><li>Map custom fields between systems</li><li>Real-time updates via webhooks</li></ul>
    </div>
  </div>
);

export const HubSpotDetail = () => (
  <div className="integration-detail-section">
    <h2>HubSpot Integration</h2>
    <p className="section-description">Marketing automation and lead nurturing</p>
    <div className="integration-connect-card">
      <h3>Connect HubSpot</h3>
      <p>Connect your HubSpot account to sync contacts and automate marketing</p>
      <div className="connect-form">
        <div className="form-group"><label>HubSpot API Key</label><input type="text" className="form-input" placeholder="Enter your HubSpot API Key" /></div>
        <div className="form-group"><label>Portal ID</label><input type="text" className="form-input" placeholder="Enter your Portal ID" /></div>
        <button className="btn-connect">Connect HubSpot</button>
      </div>
    </div>
    <div className="integration-features" style={{marginTop: '24px'}}>
      <h4>Features</h4>
      <ul><li>Sync email marketing campaigns</li><li>Lead scoring and nurturing</li><li>Marketing analytics integration</li><li>Contact and deal sync</li></ul>
    </div>
  </div>
);

export const MailchimpDetail = () => (
  <div className="integration-detail-section">
    <h2>Mailchimp Integration</h2>
    <p className="section-description">Email marketing campaigns for your clients</p>
    <div className="integration-connect-card">
      <h3>Connect Mailchimp</h3>
      <p>Connect your Mailchimp account to manage email campaigns</p>
      <div className="connect-form">
        <div className="form-group"><label>Mailchimp API Key</label><input type="text" className="form-input" placeholder="Enter your Mailchimp API Key" /></div>
        <div className="form-group"><label>Server Prefix</label><input type="text" className="form-input" placeholder="e.g., us1, us2, etc." /></div>
        <button className="btn-connect">Connect Mailchimp</button>
      </div>
    </div>
    <div className="integration-features" style={{marginTop: '24px'}}>
      <h4>Features</h4>
      <ul><li>Sync contacts to Mailchimp lists</li><li>Track email campaign performance</li><li>Segment audiences by lead stage</li><li>Automated email workflows</li></ul>
    </div>
  </div>
);

export const RingCentralDetail = () => (
  <div className="integration-detail-section">
    <h2>RingCentral Integration</h2>
    <p className="section-description">Click-to-call and SMS via RingCentral phone system</p>
    <div className="integration-connect-card">
      <h3>Connect RingCentral</h3>
      <p>Connect your RingCentral account for click-to-call and SMS</p>
      <div className="connect-form">
        <div className="form-group"><label>RingCentral Client ID</label><input type="text" className="form-input" placeholder="Enter your Client ID" /></div>
        <div className="form-group"><label>RingCentral Client Secret</label><input type="password" className="form-input" placeholder="Enter your Client Secret" /></div>
        <div className="form-group"><label>Server URL</label>
          <select className="form-select"><option value="https://platform.ringcentral.com">Production</option><option value="https://platform.devtest.ringcentral.com">Sandbox</option></select>
        </div>
        <button className="btn-connect">Connect RingCentral</button>
      </div>
    </div>
    <div className="integration-features" style={{marginTop: '24px'}}>
      <h4>Features</h4>
      <ul><li>Click-to-call from CRM</li><li>Send SMS via RingCentral</li><li>Call logging and analytics</li><li>Incoming call notifications</li></ul>
    </div>
  </div>
);

export const SlackDetail = () => (
  <div className="integration-detail-section">
    <h2>Slack Integration</h2>
    <p className="section-description">Get notifications and updates in your Slack workspace</p>
    <div className="integration-connect-card">
      <h3>Connect Slack</h3>
      <p>Connect your Slack workspace to receive notifications</p>
      <div className="connect-form">
        <div className="form-group"><label>Slack Webhook URL</label><input type="text" className="form-input" placeholder="https://hooks.slack.com/services/..." /></div>
        <div className="form-group"><label>Default Channel</label><input type="text" className="form-input" placeholder="#mortgage-leads" /></div>
        <button className="btn-connect">Connect Slack</button>
      </div>
    </div>
    <div className="integration-features" style={{marginTop: '24px'}}>
      <h4>Notification Types</h4>
      <ul><li>New lead notifications</li><li>Pipeline stage changes</li><li>Document uploads</li><li>Task completions</li><li>Loan closings</li></ul>
    </div>
  </div>
);

export const ZapierDetail = ({ setActiveSection }) => (
  <div className="integration-detail-section">
    <h2>Zapier Integration</h2>
    <p className="section-description">Connect with 5,000+ apps through automated workflows</p>
    <div className="integration-connect-card">
      <h3>Connect Zapier</h3>
      <p>Use your API key to connect this CRM with Zapier</p>
      <div className="info-box">
        <p>Go to <strong>Settings &rarr; API Keys</strong> to generate an API key for Zapier integration.</p>
        <button className="btn-secondary" onClick={() => setActiveSection('api-keys')}>Go to API Keys</button>
      </div>
    </div>
    <div className="integration-features" style={{marginTop: '24px'}}>
      <h4>Popular Zaps</h4>
      <ul><li>Create lead from new email</li><li>Add lead to Google Sheets</li><li>Send SMS when lead stage changes</li><li>Create calendar event for appointments</li><li>Notify team on Slack for new leads</li></ul>
    </div>
    <div className="info-card" style={{marginTop: '24px'}}>
      <div className="info-content">
        <h3>How to use with Zapier</h3>
        <ol>
          <li>Generate an API key in Settings &rarr; API Keys</li>
          <li>Go to <a href="https://zapier.com" target="_blank" rel="noopener noreferrer">Zapier</a> and create a new Zap</li>
          <li>Use "Webhooks by Zapier" as the trigger or action</li>
          <li>Use your API key in the Authorization header</li>
        </ol>
      </div>
    </div>
  </div>
);

export const SynthflowDetail = () => (
  <div className="integration-detail-section">
    <h2>Synthflow AI Integration</h2>
    <p className="section-description">AI-powered voice agents for automated client calls and lead qualification</p>
    <div className="integration-connect-card">
      <h3>Connect Synthflow AI</h3>
      <p>Connect your Synthflow account to enable AI voice agents</p>
      <div className="connect-form">
        <div className="form-group"><label>Synthflow API Key</label><input type="text" className="form-input" placeholder="Enter your Synthflow API Key" /></div>
        <div className="form-group"><label>Workspace ID</label><input type="text" className="form-input" placeholder="Enter your Workspace ID" /></div>
        <button className="btn-connect">Connect Synthflow</button>
      </div>
    </div>
    <div className="integration-features" style={{marginTop: '24px'}}>
      <h4>Features</h4>
      <ul><li>AI voice agents for outbound calls</li><li>Automated lead qualification</li><li>Call transcription and analysis</li><li>CRM sync for call outcomes</li><li>Schedule appointments via AI</li></ul>
    </div>
  </div>
);

export const RecallAIDetail = () => (
  <div className="integration-detail-section">
    <h2>Recall.ai Integration</h2>
    <p className="section-description">Record and transcribe meetings from Zoom, Teams, and Google Meet with AI</p>
    <div className="integration-connect-card">
      <h3>Connect Recall.ai</h3>
      <p>Connect your Recall.ai account to record and transcribe meetings</p>
      <div className="connect-form">
        <div className="form-group"><label>Recall.ai API Key</label><input type="text" className="form-input" placeholder="Enter your Recall.ai API Key" /></div>
        <button className="btn-connect">Connect Recall.ai</button>
      </div>
    </div>
    <div className="integration-features" style={{marginTop: '24px'}}>
      <h4>Features</h4>
      <ul><li>Auto-record Zoom, Teams, Meet calls</li><li>AI transcription</li><li>Meeting summaries and action items</li><li>Searchable meeting archives</li><li>Sync notes to CRM</li></ul>
    </div>
  </div>
);

export const StripeDetail = () => (
  <div className="integration-detail-section">
    <h2>Stripe Integration</h2>
    <p className="section-description">Collect payments and processing fees</p>
    <div className="integration-connect-card">
      <h3>Connect Stripe</h3>
      <p>Connect your Stripe account to collect payments</p>
      <div className="connect-form">
        <div className="form-group"><label>Stripe Publishable Key</label><input type="text" className="form-input" placeholder="pk_live_..." /></div>
        <div className="form-group"><label>Stripe Secret Key</label><input type="password" className="form-input" placeholder="sk_live_..." /></div>
        <button className="btn-connect">Connect Stripe</button>
      </div>
    </div>
    <div className="integration-features" style={{marginTop: '24px'}}>
      <h4>Features</h4>
      <ul><li>Collect application fees</li><li>Track payment history</li><li>Automated payment receipts</li><li>Sync with accounting</li></ul>
    </div>
  </div>
);

export const QuickBooksDetail = () => (
  <div className="integration-detail-section">
    <h2>QuickBooks Integration</h2>
    <p className="section-description">Sync financial data and commission tracking</p>
    <div className="integration-connect-card">
      <h3>Connect QuickBooks</h3>
      <p>Connect your QuickBooks account to sync financial data</p>
      <div className="connect-form">
        <div className="form-group"><label>QuickBooks Client ID</label><input type="text" className="form-input" placeholder="Enter your Client ID" /></div>
        <div className="form-group"><label>QuickBooks Client Secret</label><input type="password" className="form-input" placeholder="Enter your Client Secret" /></div>
        <button className="btn-connect">Connect QuickBooks</button>
      </div>
    </div>
    <div className="integration-features" style={{marginTop: '24px'}}>
      <h4>Features</h4>
      <ul><li>Track commissions and income</li><li>Sync invoices and payments</li><li>Expense tracking</li><li>Financial reporting</li></ul>
    </div>
  </div>
);

export const GoogleCalendarDetail = () => (
  <div className="integration-detail-section">
    <h2>Google Calendar Integration</h2>
    <p className="section-description">Sync appointments with Google Calendar</p>
    <div className="integration-connect-card">
      <h3>Connect Google Calendar</h3>
      <p>Connect your Google account to sync calendar events</p>
      <button className="btn-connect">Connect with Google</button>
    </div>
    <div className="integration-features" style={{marginTop: '24px'}}>
      <h4>Features</h4>
      <ul><li>Two-way calendar sync</li><li>Appointment reminders</li><li>Schedule availability</li><li>Auto-add meeting links</li></ul>
    </div>
  </div>
);

export const GoogleDriveDetail = () => (
  <div className="integration-detail-section">
    <h2>Google Drive Integration</h2>
    <p className="section-description">Store and share loan documents in Google Drive</p>
    <div className="integration-connect-card">
      <h3>Connect Google Drive</h3>
      <p>Connect your Google account to store documents</p>
      <button className="btn-connect">Connect with Google</button>
    </div>
    <div className="integration-features" style={{marginTop: '24px'}}>
      <h4>Features</h4>
      <ul><li>Auto-upload loan documents</li><li>Organized folder structure per loan</li><li>Share documents with clients</li><li>Version history tracking</li></ul>
    </div>
  </div>
);

export const DocuSignDetail = () => (
  <div className="integration-detail-section">
    <h2>DocuSign Integration</h2>
    <p className="section-description">Send and sign loan documents electronically</p>
    <div className="integration-connect-card">
      <h3>Connect DocuSign</h3>
      <p>Connect your DocuSign account for electronic signatures</p>
      <div className="connect-form">
        <div className="form-group"><label>DocuSign Integration Key</label><input type="text" className="form-input" placeholder="Enter your Integration Key" /></div>
        <div className="form-group"><label>DocuSign Secret Key</label><input type="password" className="form-input" placeholder="Enter your Secret Key" /></div>
        <div className="form-group"><label>Account ID</label><input type="text" className="form-input" placeholder="Enter your Account ID" /></div>
        <button className="btn-connect">Connect DocuSign</button>
      </div>
    </div>
    <div className="integration-features" style={{marginTop: '24px'}}>
      <h4>Features</h4>
      <ul><li>Send documents for signature</li><li>Track signing status</li><li>Automated reminders</li><li>Auto-save signed documents</li></ul>
    </div>
  </div>
);
