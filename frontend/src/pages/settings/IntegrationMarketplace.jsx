import React, { useState } from 'react';
import { AVAILABLE_INTEGRATIONS } from './shared/constants';

const IntegrationMarketplace = ({ connectedIntegrations, setActiveSection }) => {
  const [searchTerm, setSearchTerm] = useState('');

  const filteredIntegrations = AVAILABLE_INTEGRATIONS.filter(integration =>
    integration.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    integration.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
    integration.category.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="integrations-marketplace">
      <div className="marketplace-header">
        <div className="header-text">
          <h2>Integrations & Apps</h2>
          <p className="section-description">
            Discover ({AVAILABLE_INTEGRATIONS.length}) | Manage ({connectedIntegrations.size})
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

      <div className="all-integrations-section">
        <div className="integrations-grid">
          {filteredIntegrations.map(integration => (
            <div
              key={integration.id}
              className="integration-grid-card"
              onClick={() => setActiveSection(integration.id)}
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
  );
};

export default IntegrationMarketplace;
