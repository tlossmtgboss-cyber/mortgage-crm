// Use HTTPS Railway URL in production, localhost for development
const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';

export const API_BASE = isProduction
  ? 'https://api.perenniaai.com'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

// Alias used by some sections
export const API_BASE_URL = API_BASE;

export const LEAD_STAGES = [
  // Lead Stages
  { value: 'new', label: 'New Lead' },
  { value: 'contacted', label: 'Contacted' },
  { value: 'qualified', label: 'Qualified' },
  { value: 'meeting_scheduled', label: 'Meeting Scheduled' },
  // Application & Processing
  { value: 'application_started', label: 'Application Started' },
  { value: 'disclosed', label: 'Disclosed' },
  { value: 'processing', label: 'Processing' },
  { value: 'submitted', label: 'Submitted to UW' },
  { value: 'uw_received', label: 'UW Received' },
  // Underwriting Outcomes
  { value: 'approved', label: 'Approved' },
  { value: 'approved_with_conditions', label: 'Approved with Conditions' },
  { value: 'suspended', label: 'Suspended' },
  // Last Mile - Clear to Close & Closing
  { value: 'last_mile', label: 'Last Mile' },
  { value: 'ctc', label: 'Clear to Close (CTC)' },
  { value: 'closing_scheduled', label: 'Closing Scheduled' },
  { value: 'closing_docs_sent', label: 'Closing Docs Sent' },
  { value: 'closing', label: 'At Closing' },
  { value: 'funded', label: 'Funded' },
  // Post-Close
  { value: 'post_close', label: 'Post-Close' },
  { value: 'closed', label: 'Closed (Complete)' },
  // Other
  { value: 'on_hold', label: 'On Hold' },
  { value: 'lost', label: 'Lost/Withdrawn' }
];

export const AVAILABLE_INTEGRATIONS = [
  { id: 'gmail', name: 'Gmail', description: 'Sync Gmail emails and contacts with your CRM', icon: '', color: '#ea4335', category: 'Email' },
  { id: 'outlook-email', name: 'Outlook Email', description: 'Sync your Microsoft 365 / Outlook emails with loan files', icon: '', color: '#0078d4', category: 'Email' },
  { id: 'outlook-calendar', name: 'Outlook Calendar', description: 'Sync your Microsoft 365 / Outlook calendar events', icon: '', color: '#0078d4', category: 'Calendar' },
  { id: 'teams', name: 'Microsoft Teams', description: 'Send messages, make calls, and collaborate with your team', icon: '', color: '#6264a7', category: 'Communication' },
  { id: 'zoom', name: 'Zoom', description: 'Host virtual meetings and consultations with clients', icon: '', color: '#2d8cff', category: 'Communication' },
  { id: 'calendly', name: 'Calendly', description: 'Automated scheduling for client meetings', icon: '', color: '#006bff', category: 'Scheduling' },
  { id: 'docusign', name: 'DocuSign', description: 'Send and sign loan documents electronically', icon: '', color: '#ffd500', category: 'Documents' },
  { id: 'salesforce', name: 'Salesforce', description: 'Sync contacts and deals with your Salesforce CRM', icon: '', color: '#00a1e0', category: 'CRM' },
  { id: 'hubspot', name: 'HubSpot', description: 'Marketing automation and lead nurturing', icon: '', color: '#ff7a59', category: 'Marketing' },
  { id: 'mailchimp', name: 'Mailchimp', description: 'Email marketing campaigns for your clients', icon: '', color: '#ffe01b', category: 'Marketing' },
  { id: 'ringcentral', name: 'RingCentral', description: 'Click-to-call and SMS via RingCentral phone system', icon: '', color: '#0073ae', category: 'Communication' },
  { id: 'slack', name: 'Slack', description: 'Get notifications and updates in your Slack workspace', icon: '', color: '#4a154b', category: 'Communication' },
  { id: 'zapier', name: 'Zapier', description: 'Connect with 5,000+ apps through automated workflows', icon: '', color: '#ff4a00', category: 'Automation' },
  { id: 'synthflow', name: 'Synthflow AI', description: 'AI-powered voice agents for automated client calls and lead qualification', icon: '', color: '#218D8D', category: 'AI & Automation' },
  { id: 'recallai', name: 'Recall.ai', description: 'Record and transcribe meetings from Zoom, Teams, and Google Meet with AI', icon: '', color: '#10b981', category: 'AI & Automation' },
  { id: 'stripe', name: 'Stripe', description: 'Collect payments and processing fees', icon: '', color: '#635bff', category: 'Payments' },
  { id: 'quickbooks', name: 'QuickBooks', description: 'Sync financial data and commission tracking', icon: '', color: '#2ca01c', category: 'Accounting' },
  { id: 'google-calendar', name: 'Google Calendar', description: 'Sync appointments with Google Calendar', icon: '', color: '#4285f4', category: 'Calendar' },
  { id: 'google-drive', name: 'Google Drive', description: 'Store and share loan documents in Google Drive', icon: '', color: '#4285f4', category: 'Documents' }
];

export const DEFAULT_SIDEBAR_ITEMS = [
  { id: 'user-profile', label: 'User Profile', type: 'parent', section: 'userProfile' },
  { id: 'organizational', label: 'Organizational Settings', type: 'parent', section: 'organizational', adminOnly: true },
  { id: 'workflow', label: 'Workflow', type: 'standalone', section: 'workflow', navigate: '/workflow', adminOnly: true },
  { id: 'sla-tracking', label: 'SLA Tracking', type: 'standalone', section: 'sla-tracking', navigate: '/sla-tracking', adminOnly: true },
  { id: 'agent-governance', label: 'Agent Governance', type: 'parent', section: 'agentGovernance', adminOnly: true },
  { id: 'document-intake', label: 'Document Intake', type: 'standalone', section: 'document-intake', adminOnly: true },
  { id: 'email-monitor', label: 'Email Monitor', type: 'standalone', section: 'email-monitor', adminOnly: true },
  { id: 'it-helpdesk', label: 'IT Helpdesk', type: 'standalone', section: 'it-helpdesk' },
  { id: 'production', label: 'Production Widgets', type: 'parent', section: 'production' },
  { id: 'client-portals', label: 'Client Portals (PURL)', type: 'standalone', section: 'client-portals', adminOnly: true },
  { id: 'client-portal-settings', label: 'Client Portal Settings', type: 'standalone', section: 'client-portal-settings', navigate: '/settings/client-portal', adminOnly: true },
  { id: 'lead-capture', label: 'Lead Capture', type: 'standalone', section: 'lead-capture', navigate: '/settings/lead-capture', adminOnly: true },
  { id: 'communication-preferences', label: 'Communication Preferences', type: 'standalone', section: 'communication-preferences', navigate: '/settings/communication', adminOnly: true },
  { id: 'integration-settings', label: 'Integrations', type: 'standalone', section: 'integration-settings' },
  { id: 'api-keys-settings', label: 'API Keys & Webhooks', type: 'standalone', section: 'api-keys-settings', navigate: '/settings/api-keys', adminOnly: true },
  { id: 'company-branding', label: 'Company & Branding', type: 'standalone', section: 'company-branding', navigate: '/settings/company-branding', adminOnly: true },
  { id: 'data-management', label: 'Data Management', type: 'standalone', section: 'data-management', navigate: '/data-upload', adminOnly: true },
  { id: 'master-admin', label: 'Master Administrator', type: 'parent', section: 'masterAdmin', adminOnly: true },
  { id: 'admin-settings', label: 'Admin Settings', type: 'standalone', section: 'admin-settings', navigate: '/admin/settings', adminOnly: true },
  { id: 'custom-domains', label: 'Custom Domains', type: 'standalone', section: 'custom-domains', navigate: '/admin/domains', adminOnly: true },
  { id: 'call-routing', label: 'Call Routing', type: 'standalone', section: 'call-routing', navigate: '/call-routing-config', adminOnly: true }
];

export const STATUS_BADGE_STYLES = {
  'Success': { background: '#dcfce7', color: '#166534' },
  'Created': { background: '#dbeafe', color: '#1e40af' },
  'Modified': { background: '#fef3c7', color: '#92400e' },
  'Deleted': { background: '#fee2e2', color: '#991b1b' },
  'Enabled': { background: '#dcfce7', color: '#166534' },
  'Disabled': { background: '#fee2e2', color: '#991b1b' },
  'Completed': { background: '#dbeafe', color: '#1e40af' },
  'Sent': { background: '#e0e7ff', color: '#3730a3' },
  'Reset': { background: '#fef3c7', color: '#92400e' },
  'Changed': { background: '#fef3c7', color: '#92400e' },
  'Revoked': { background: '#fee2e2', color: '#991b1b' },
  'Suspended': { background: '#fee2e2', color: '#991b1b' },
  'Reinstated': { background: '#dcfce7', color: '#166534' },
  'Started': { background: '#e0e7ff', color: '#3730a3' },
  'Ended': { background: '#f1f5f9', color: '#475569' },
};

export function getStatusBadgeStyle(status) {
  return STATUS_BADGE_STYLES[status] || { background: '#f1f5f9', color: '#475569' };
}

export function formatDate(dateString) {
  if (!dateString) return 'N/A';
  const date = new Date(dateString);
  return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
}
