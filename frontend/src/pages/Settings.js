import React, { useState } from 'react';
import './Settings.css';

function Settings() {
  const [activeSection, setActiveSection] = useState('integrations');
  const [integrations, setIntegrations] = useState({
    microsoft: {
      connected: false,
      email: '',
      features: {
        teams: false,
        calendar: false,
        email: false,
        phone: false
      }
    },
    calendly: {
      connected: false,
      apiKey: ''
    },
    other: []
  });

  const handleMicrosoftConnect = () => {
    // In a real app, this would initiate OAuth flow
    alert('Microsoft 365 OAuth integration coming soon!\n\nThis will allow you to:\n- Send SMS via Teams\n- Sync calendar appointments\n- Make phone calls through Teams\n- Send and receive emails');
  };

  const handleMicrosoftDisconnect = () => {
    setIntegrations({
      ...integrations,
      microsoft: {
        connected: false,
        email: '',
        features: {
          teams: false,
          calendar: false,
          email: false,
          phone: false
        }
      }
    });
  };

  const handleCalendlyConnect = (apiKey) => {
    setIntegrations({
      ...integrations,
      calendly: {
        connected: true,
        apiKey: apiKey
      }
    });
  };

  const handleCalendlyDisconnect = () => {
    setIntegrations({
      ...integrations,
      calendly: {
        connected: false,
        apiKey: ''
      }
    });
  };

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
        </div>

        {/* Main Content */}
        <div className="settings-main">
          {activeSection === 'integrations' && (
            <div className="integrations-section">
              <h2>Integrations</h2>
              <p className="section-description">
                Connect your favorite tools to streamline your workflow
              </p>

              {/* Microsoft 365 Integration */}
              <div className="integration-card">
                <div className="integration-header">
                  <div className="integration-info">
                    <div className="integration-icon microsoft">
                      <span>M</span>
                    </div>
                    <div>
                      <h3>Microsoft 365</h3>
                      <p>Teams, Calendar, Email, and Phone integration</p>
                    </div>
                  </div>
                  {integrations.microsoft.connected ? (
                    <button className="btn-disconnect" onClick={handleMicrosoftDisconnect}>
                      Disconnect
                    </button>
                  ) : (
                    <button className="btn-connect" onClick={handleMicrosoftConnect}>
                      Connect
                    </button>
                  )}
                </div>

                {integrations.microsoft.connected && (
                  <div className="integration-details">
                    <div className="connected-account">
                      <span className="label">Connected Account:</span>
                      <span className="value">{integrations.microsoft.email}</span>
                    </div>
                    <div className="features-list">
                      <h4>Enabled Features:</h4>
                      <label className="feature-checkbox">
                        <input
                          type="checkbox"
                          checked={integrations.microsoft.features.teams}
                          onChange={(e) => setIntegrations({
                            ...integrations,
                            microsoft: {
                              ...integrations.microsoft,
                              features: {...integrations.microsoft.features, teams: e.target.checked}
                            }
                          })}
                        />
                        <span>Microsoft Teams (SMS & Chat)</span>
                      </label>
                      <label className="feature-checkbox">
                        <input
                          type="checkbox"
                          checked={integrations.microsoft.features.calendar}
                          onChange={(e) => setIntegrations({
                            ...integrations,
                            microsoft: {
                              ...integrations.microsoft,
                              features: {...integrations.microsoft.features, calendar: e.target.checked}
                            }
                          })}
                        />
                        <span>Calendar Sync</span>
                      </label>
                      <label className="feature-checkbox">
                        <input
                          type="checkbox"
                          checked={integrations.microsoft.features.email}
                          onChange={(e) => setIntegrations({
                            ...integrations,
                            microsoft: {
                              ...integrations.microsoft,
                              features: {...integrations.microsoft.features, email: e.target.checked}
                            }
                          })}
                        />
                        <span>Email Integration</span>
                      </label>
                      <label className="feature-checkbox">
                        <input
                          type="checkbox"
                          checked={integrations.microsoft.features.phone}
                          onChange={(e) => setIntegrations({
                            ...integrations,
                            microsoft: {
                              ...integrations.microsoft,
                              features: {...integrations.microsoft.features, phone: e.target.checked}
                            }
                          })}
                        />
                        <span>Teams Phone System</span>
                      </label>
                    </div>
                  </div>
                )}

                <div className="integration-description">
                  <strong>What you can do:</strong>
                  <ul>
                    <li>Send SMS messages directly from Teams</li>
                    <li>Sync calendar appointments automatically</li>
                    <li>Make phone calls through Teams Phone</li>
                    <li>Send and receive emails from Outlook</li>
                  </ul>
                </div>
              </div>

              {/* Calendly Integration */}
              <div className="integration-card">
                <div className="integration-header">
                  <div className="integration-info">
                    <div className="integration-icon calendly">
                      <span>C</span>
                    </div>
                    <div>
                      <h3>Calendly</h3>
                      <p>Automated scheduling for client meetings</p>
                    </div>
                  </div>
                  {integrations.calendly.connected ? (
                    <button className="btn-disconnect" onClick={handleCalendlyDisconnect}>
                      Disconnect
                    </button>
                  ) : (
                    <button className="btn-connect" onClick={() => {
                      const apiKey = prompt('Enter your Calendly API Key:');
                      if (apiKey) handleCalendlyConnect(apiKey);
                    }}>
                      Connect
                    </button>
                  )}
                </div>

                {integrations.calendly.connected && (
                  <div className="integration-details">
                    <div className="connected-account">
                      <span className="label">API Key:</span>
                      <span className="value">••••••••{integrations.calendly.apiKey.slice(-4)}</span>
                    </div>
                  </div>
                )}

                <div className="integration-description">
                  <strong>What you can do:</strong>
                  <ul>
                    <li>Share scheduling links with clients</li>
                    <li>Automatically create appointments</li>
                    <li>Sync with your CRM calendar</li>
                  </ul>
                </div>
              </div>

              {/* Coming Soon Section */}
              <div className="coming-soon">
                <h3>More Integrations Coming Soon</h3>
                <div className="coming-soon-grid">
                  <div className="coming-soon-item">
                    <span className="icon">📧</span>
                    <span>Mailchimp</span>
                  </div>
                  <div className="coming-soon-item">
                    <span className="icon">📱</span>
                    <span>Twilio SMS</span>
                  </div>
                  <div className="coming-soon-item">
                    <span className="icon">💼</span>
                    <span>Salesforce</span>
                  </div>
                  <div className="coming-soon-item">
                    <span className="icon">📊</span>
                    <span>HubSpot</span>
                  </div>
                </div>
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
        </div>
      </div>
    </div>
  );
}

export default Settings;
