import React, { useState, useEffect } from 'react';
import OnboardingWizard from './OnboardingWizard';
import './Settings.css';

function Settings() {
  const [activeSection, setActiveSection] = useState('integrations');
  const [expandedSections, setExpandedSections] = useState({
    organizational: false,
    scheduling: false
  });
  const [searchTerm, setSearchTerm] = useState('');
  const [connectedIntegrations, setConnectedIntegrations] = useState(new Set(['outlook']));
  const [calendlyEventTypes, setCalendlyEventTypes] = useState([]);
  const [calendarMappings, setCalendarMappings] = useState([]);
  const [loadingCalendly, setLoadingCalendly] = useState(false);
  const [selectedStage, setSelectedStage] = useState('');
  const [selectedEventType, setSelectedEventType] = useState('');

  const toggleSection = (section) => {
    setExpandedSections({
      ...expandedSections,
      [section]: !expandedSections[section]
    });
  };

  const leadStages = [
    { value: 'new', label: 'New Lead' },
    { value: 'contacted', label: 'Contacted' },
    { value: 'qualified', label: 'Qualified' },
    { value: 'meeting_scheduled', label: 'Meeting Scheduled' },
    { value: 'application_started', label: 'Application Started' },
    { value: 'processing', label: 'Processing' },
    { value: 'approved', label: 'Approved' },
    { value: 'closed', label: 'Closed' },
    { value: 'lost', label: 'Lost' }
  ];

  const fetchCalendlyEventTypes = async () => {
    setLoadingCalendly(true);
    try {
      const response = await fetch('/api/v1/calendly/event-types', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      const data = await response.json();
      setCalendlyEventTypes(data.event_types || []);
    } catch (error) {
      console.error('Error fetching Calendly event types:', error);
    } finally {
      setLoadingCalendly(false);
    }
  };

  const fetchCalendarMappings = async () => {
    try {
      const response = await fetch('/api/v1/calendly/calendar-mappings', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      const data = await response.json();
      setCalendarMappings(data.mappings || []);
    } catch (error) {
      console.error('Error fetching calendar mappings:', error);
    }
  };

  const createCalendarMapping = async () => {
    if (!selectedStage || !selectedEventType) {
      alert('Please select both a lead stage and a calendar type');
      return;
    }

    const eventType = calendlyEventTypes.find(et => et.uri.includes(selectedEventType));
    if (!eventType) {
      alert('Event type not found');
      return;
    }

    try {
      const response = await fetch('/api/v1/calendly/calendar-mappings', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          stage: selectedStage,
          event_type_uuid: selectedEventType,
          event_type_name: eventType.name,
          event_type_url: eventType.scheduling_url
        })
      });

      if (response.ok) {
        alert('Calendar mapping saved successfully!');
        setSelectedStage('');
        setSelectedEventType('');
        fetchCalendarMappings();
      } else {
        alert('Failed to save calendar mapping');
      }
    } catch (error) {
      console.error('Error creating calendar mapping:', error);
      alert('Error saving calendar mapping');
    }
  };

  const availableIntegrations = [
    {
      id: 'outlook',
      name: 'Outlook Email',
      description: 'Sync emails and automatically extract lead information with AI',
      icon: '📧',
      color: '#0078d4',
      category: 'Email'
    },
    {
      id: 'outlook-calendar',
      name: 'Outlook Calendar',
      description: 'Sync calendar events and schedule appointments',
      icon: '📅',
      color: '#0078d4',
      category: 'Calendar'
    },
    {
      id: 'teams',
      name: 'Microsoft Teams',
      description: 'Send messages, make calls, and collaborate with your team',
      icon: '💬',
      color: '#6264a7',
      category: 'Communication'
    },
    {
      id: 'zoom',
      name: 'Zoom',
      description: 'Host virtual meetings and consultations with clients',
      icon: '📹',
      color: '#2d8cff',
      category: 'Communication'
    },
    {
      id: 'calendly',
      name: 'Calendly',
      description: 'Automated scheduling for client meetings',
      icon: '🗓️',
      color: '#006bff',
      category: 'Scheduling'
    },
    {
      id: 'docusign',
      name: 'DocuSign',
      description: 'Send and sign loan documents electronically',
      icon: '📝',
      color: '#ffd500',
      category: 'Documents'
    },
    {
      id: 'salesforce',
      name: 'Salesforce',
      description: 'Sync contacts and deals with your Salesforce CRM',
      icon: '☁️',
      color: '#00a1e0',
      category: 'CRM'
    },
    {
      id: 'hubspot',
      name: 'HubSpot',
      description: 'Marketing automation and lead nurturing',
      icon: '🎯',
      color: '#ff7a59',
      category: 'Marketing'
    },
    {
      id: 'mailchimp',
      name: 'Mailchimp',
      description: 'Email marketing campaigns for your clients',
      icon: '✉️',
      color: '#ffe01b',
      category: 'Marketing'
    },
    {
      id: 'twilio',
      name: 'Twilio SMS',
      description: 'Send SMS messages to leads and clients',
      icon: '📱',
      color: '#f22f46',
      category: 'Communication'
    },
    {
      id: 'slack',
      name: 'Slack',
      description: 'Get notifications and updates in your Slack workspace',
      icon: '💼',
      color: '#4a154b',
      category: 'Communication'
    },
    {
      id: 'zapier',
      name: 'Zapier',
      description: 'Connect with 5,000+ apps through automated workflows',
      icon: '⚡',
      color: '#ff4a00',
      category: 'Automation'
    },
    {
      id: 'stripe',
      name: 'Stripe',
      description: 'Collect payments and processing fees',
      icon: '💳',
      color: '#635bff',
      category: 'Payments'
    },
    {
      id: 'quickbooks',
      name: 'QuickBooks',
      description: 'Sync financial data and commission tracking',
      icon: '💰',
      color: '#2ca01c',
      category: 'Accounting'
    },
    {
      id: 'google-calendar',
      name: 'Google Calendar',
      description: 'Sync appointments with Google Calendar',
      icon: '📆',
      color: '#4285f4',
      category: 'Calendar'
    },
    {
      id: 'google-drive',
      name: 'Google Drive',
      description: 'Store and share loan documents in Google Drive',
      icon: '📂',
      color: '#4285f4',
      category: 'Documents'
    }
  ];

  const toggleIntegration = (integrationId) => {
    const newConnected = new Set(connectedIntegrations);
    if (newConnected.has(integrationId)) {
      newConnected.delete(integrationId);
    } else {
      newConnected.add(integrationId);
    }
    setConnectedIntegrations(newConnected);
  };

  const filteredIntegrations = availableIntegrations.filter(integration =>
    integration.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    integration.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
    integration.category.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const featuredIntegrations = filteredIntegrations.filter(i =>
    ['outlook', 'outlook-calendar', 'teams', 'zoom', 'docusign', 'calendly'].includes(i.id)
  );

  useEffect(() => {
    if (activeSection === 'calendar-settings') {
      fetchCalendlyEventTypes();
      fetchCalendarMappings();
    }
  }, [activeSection]);

  return (
    <div className="settings-page">
      <div className="settings-header">
        <h1>Settings</h1>
        <p>Manage your integrations and preferences</p>
      </div>

      <div className="settings-content">
        {/* Sidebar */}
        <div className="settings-sidebar">
          <button
            className={`sidebar-btn ${activeSection === 'integrations' ? 'active' : ''}`}
            onClick={() => setActiveSection('integrations')}
          >
            <span className="icon">🔌</span>
            <span>Integrations</span>
          </button>

          {/* Organizational Settings - Expandable */}
          <button
            className={`sidebar-btn parent ${expandedSections.organizational ? 'expanded' : ''}`}
            onClick={() => toggleSection('organizational')}
          >
            <span className="icon">🏢</span>
            <span>Organizational Settings</span>
            <span className="expand-icon">{expandedSections.organizational ? '▼' : '▶'}</span>
          </button>
          {expandedSections.organizational && (
            <div className="sidebar-children">
              <button
                className={`sidebar-btn child ${activeSection === 'company-info' ? 'active' : ''}`}
                onClick={() => setActiveSection('company-info')}
              >
                <span>Company Info</span>
              </button>
              <button
                className={`sidebar-btn child ${activeSection === 'team-members' ? 'active' : ''}`}
                onClick={() => setActiveSection('team-members')}
              >
                <span>Team Members</span>
              </button>
              <button
                className={`sidebar-btn child ${activeSection === 'roles-permissions' ? 'active' : ''}`}
                onClick={() => setActiveSection('roles-permissions')}
              >
                <span>Roles & Permissions</span>
              </button>
              <button
                className={`sidebar-btn child ${activeSection === 'branding' ? 'active' : ''}`}
                onClick={() => setActiveSection('branding')}
              >
                <span>Branding</span>
              </button>
            </div>
          )}

          {/* Scheduling Settings - Expandable */}
          <button
            className={`sidebar-btn parent ${expandedSections.scheduling ? 'expanded' : ''}`}
            onClick={() => toggleSection('scheduling')}
          >
            <span className="icon">📅</span>
            <span>Scheduling Settings</span>
            <span className="expand-icon">{expandedSections.scheduling ? '▼' : '▶'}</span>
          </button>
          {expandedSections.scheduling && (
            <div className="sidebar-children">
              <button
                className={`sidebar-btn child ${activeSection === 'business-hours' ? 'active' : ''}`}
                onClick={() => setActiveSection('business-hours')}
              >
                <span>Business Hours</span>
              </button>
              <button
                className={`sidebar-btn child ${activeSection === 'appointment-types' ? 'active' : ''}`}
                onClick={() => setActiveSection('appointment-types')}
              >
                <span>Appointment Types</span>
              </button>
              <button
                className={`sidebar-btn child ${activeSection === 'calendar-settings' ? 'active' : ''}`}
                onClick={() => setActiveSection('calendar-settings')}
              >
                <span>Calendar Settings</span>
              </button>
              <button
                className={`sidebar-btn child ${activeSection === 'availability' ? 'active' : ''}`}
                onClick={() => setActiveSection('availability')}
              >
                <span>Availability</span>
              </button>
            </div>
          )}

          <button
            className={`sidebar-btn ${activeSection === 'profile' ? 'active' : ''}`}
            onClick={() => setActiveSection('profile')}
          >
            <span className="icon">👤</span>
            <span>Profile</span>
          </button>
          <button
            className={`sidebar-btn ${activeSection === 'notifications' ? 'active' : ''}`}
            onClick={() => setActiveSection('notifications')}
          >
            <span className="icon">🔔</span>
            <span>Notifications</span>
          </button>
          <button
            className={`sidebar-btn ${activeSection === 'onboarding' ? 'active' : ''}`}
            onClick={() => setActiveSection('onboarding')}
          >
            <span className="icon">🚀</span>
            <span>Onboarding</span>
          </button>
        </div>

        {/* Main Content */}
        <div className="settings-main">
          {activeSection === 'integrations' && (
            <div className="integrations-marketplace">
              <div className="marketplace-header">
                <div className="header-text">
                  <h2>Integrations & Apps</h2>
                  <p className="section-description">
                    Discover ({availableIntegrations.length}) | Manage ({connectedIntegrations.size})
                  </p>
                </div>
                <div className="search-box">
                  <input
                    type="text"
                    placeholder="Find integrations, apps, and more"
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="integration-search"
                  />
                </div>
              </div>

              {/* Featured Section */}
              {featuredIntegrations.length > 0 && !searchTerm && (
                <div className="featured-section">
                  <h3>Featured</h3>
                  <div className="featured-grid">
                    {featuredIntegrations.slice(0, 2).map(integration => (
                      <div
                        key={integration.id}
                        className="featured-card"
                        onClick={() => toggleIntegration(integration.id)}
                      >
                        <div className="featured-icon" style={{background: integration.color}}>
                          <span>{integration.icon}</span>
                        </div>
                        <div className="featured-info">
                          <h4>{integration.name}</h4>
                          <p>{integration.description}</p>
                          <span className={`status-badge ${connectedIntegrations.has(integration.id) ? 'connected' : ''}`}>
                            {connectedIntegrations.has(integration.id) ? 'Connected' : 'Connect'}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* All Integrations Grid */}
              <div className="all-integrations-section">
                <div className="integrations-grid">
                  {filteredIntegrations.map(integration => (
                    <div
                      key={integration.id}
                      className="integration-grid-card"
                      onClick={() => toggleIntegration(integration.id)}
                    >
                      <div className="card-icon" style={{background: integration.color}}>
                        {integration.icon}
                      </div>
                      <div className="card-content">
                        <div className="card-header">
                          <h4>{integration.name}</h4>
                          {connectedIntegrations.has(integration.id) && (
                            <span className="connected-badge">Connected</span>
                          )}
                        </div>
                        <p className="card-description">{integration.description}</p>
                      </div>
                    </div>
                  ))}
                </div>

                {filteredIntegrations.length === 0 && (
                  <div className="no-results">
                    <p>No integrations found matching "{searchTerm}"</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {activeSection === 'profile' && (
            <div className="profile-section">
              <h2>Profile Settings</h2>
              <p>Coming soon...</p>
            </div>
          )}

          {activeSection === 'notifications' && (
            <div className="notifications-section">
              <h2>Notification Preferences</h2>
              <p>Coming soon...</p>
            </div>
          )}

          {activeSection === 'onboarding' && (
            <div className="onboarding-section">
              <h2>Setup Wizard</h2>
              <p className="section-description">
                Complete the onboarding process to set up your CRM
              </p>
              <div className="onboarding-wrapper">
                <OnboardingWizard />
              </div>
            </div>
          )}

          {/* Organizational Settings Sections */}
          {activeSection === 'company-info' && (
            <div className="company-info-section">
              <h2>Company Information</h2>
              <p className="section-description">
                Manage your company profile and contact information
              </p>
              <p>Coming soon...</p>
            </div>
          )}

          {activeSection === 'team-members' && (
            <div className="team-members-section">
              <h2>Team Members</h2>
              <p className="section-description">
                Add and manage your team members
              </p>
              <p>Coming soon...</p>
            </div>
          )}

          {activeSection === 'roles-permissions' && (
            <div className="roles-permissions-section">
              <h2>Roles & Permissions</h2>
              <p className="section-description">
                Configure user roles and access levels
              </p>
              <p>Coming soon...</p>
            </div>
          )}

          {activeSection === 'branding' && (
            <div className="branding-section">
              <h2>Branding</h2>
              <p className="section-description">
                Customize your company's branding and appearance
              </p>
              <p>Coming soon...</p>
            </div>
          )}

          {/* Scheduling Settings Sections */}
          {activeSection === 'business-hours' && (
            <div className="business-hours-section">
              <h2>Business Hours</h2>
              <p className="section-description">
                Set your operating hours and holidays
              </p>
              <p>Coming soon...</p>
            </div>
          )}

          {activeSection === 'appointment-types' && (
            <div className="appointment-types-section">
              <h2>Appointment Types</h2>
              <p className="section-description">
                Configure different types of appointments and their durations
              </p>
              <p>Coming soon...</p>
            </div>
          )}

          {activeSection === 'calendar-settings' && (
            <div className="calendar-settings-section">
              <h2>AI Scheduling - Calendar Mappings</h2>
              <p className="section-description">
                Map each lead stage to a specific Calendly event type for automatic AI scheduling
              </p>

              {/* Explanation Card */}
              <div className="info-card">
                <div className="info-icon">🤖</div>
                <div className="info-content">
                  <h3>How AI Scheduling Works</h3>
                  <p>When AI schedules appointments with leads, it automatically selects the right calendar based on the lead's current stage. For example:</p>
                  <ul>
                    <li><strong>New Lead</strong> → Discovery Call (30 min)</li>
                    <li><strong>Qualified</strong> → Consultation (60 min)</li>
                    <li><strong>Application Started</strong> → Application Review (45 min)</li>
                  </ul>
                  <p>Configure your mappings below to tell the AI which calendar to use for each stage.</p>
                </div>
              </div>

              {/* Create New Mapping */}
              <div className="mapping-form-card">
                <h3>Create Calendar Mapping</h3>
                <div className="mapping-form">
                  <div className="form-row">
                    <div className="form-group">
                      <label>Lead Stage</label>
                      <select
                        value={selectedStage}
                        onChange={(e) => setSelectedStage(e.target.value)}
                        className="form-select"
                      >
                        <option value="">Select a stage...</option>
                        {leadStages.map(stage => (
                          <option key={stage.value} value={stage.value}>
                            {stage.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="form-group">
                      <label>Calendly Event Type</label>
                      {loadingCalendly ? (
                        <div className="loading-spinner">Loading calendars...</div>
                      ) : (
                        <select
                          value={selectedEventType}
                          onChange={(e) => setSelectedEventType(e.target.value)}
                          className="form-select"
                        >
                          <option value="">Select a calendar...</option>
                          {calendlyEventTypes.map(eventType => {
                            const uuid = eventType.uri.split('/').pop();
                            return (
                              <option key={uuid} value={uuid}>
                                {eventType.name} ({eventType.duration} min)
                              </option>
                            );
                          })}
                        </select>
                      )}
                    </div>

                    <div className="form-actions">
                      <button
                        onClick={createCalendarMapping}
                        disabled={!selectedStage || !selectedEventType}
                        className="btn-save-mapping"
                      >
                        Save Mapping
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              {/* Current Mappings */}
              <div className="current-mappings-card">
                <h3>Current Mappings</h3>
                {calendarMappings.length === 0 ? (
                  <div className="empty-state">
                    <div className="empty-icon">📅</div>
                    <p>No calendar mappings configured yet.</p>
                    <p className="empty-hint">Create your first mapping above to get started.</p>
                  </div>
                ) : (
                  <div className="mappings-table">
                    <table>
                      <thead>
                        <tr>
                          <th>Lead Stage</th>
                          <th>Calendar Type</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {calendarMappings.map(mapping => {
                          const stageLabel = leadStages.find(s => s.value === mapping.stage)?.label || mapping.stage;
                          return (
                            <tr key={mapping.id}>
                              <td>
                                <div className="stage-cell">
                                  <span className="stage-badge">{stageLabel}</span>
                                </div>
                              </td>
                              <td>
                                <div className="calendar-cell">
                                  <strong>{mapping.event_type_name}</strong>
                                  <br />
                                  <span className="calendar-uuid">{mapping.event_type_uuid}</span>
                                </div>
                              </td>
                              <td>
                                <span className="status-badge active">✓ Active</span>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Help Section */}
              <div className="help-card">
                <h4>Need Help?</h4>
                <p>To get your Calendly event types:</p>
                <ol>
                  <li>Go to <a href="https://calendly.com/event_types/user/me" target="_blank" rel="noopener noreferrer">calendly.com/event_types</a></li>
                  <li>Create different event types for each stage (e.g., "Discovery Call", "Consultation")</li>
                  <li>Come back here and map each stage to the appropriate event type</li>
                  <li>The AI will automatically use the right calendar when scheduling!</li>
                </ol>
              </div>
            </div>
          )}

          {activeSection === 'availability' && (
            <div className="availability-section">
              <h2>Availability</h2>
              <p className="section-description">
                Set your personal availability and time-off
              </p>
              <p>Coming soon...</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default Settings;
