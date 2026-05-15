import React, { useState, useEffect } from 'react';
import './PermissionsStep.css';

// Loan lifecycle stages - NO ICONS
const LOAN_STAGES = [
  {
    code: 'lead',
    name: 'Lead Management',
    description: 'Lead intake, qualification, pre-approval, and nurturing',
    color: '#3B82F6'
  },
  {
    code: 'active_loan',
    name: 'Active Loan',
    description: 'Processing, underwriting, closing, and rate locks',
    color: '#2D7A52'
  },
  {
    code: 'portfolio',
    name: 'Portfolio',
    description: 'Client retention, MUM, referrals, and anniversaries',
    color: '#B8924A'
  }
];

// Permission templates per stage
const TEMPLATES = {
  lead: [
    { code: 'full_access', name: 'Full Access', description: 'Complete admin control over leads', permissions: ['all'] },
    { code: 'lead_officer', name: 'Standard Loan Officer', description: 'Lead management, pipeline, clients', permissions: ['view', 'edit', 'create'] },
    { code: 'sdr', name: 'SDR / Inside Sales', description: 'Lead intake and qualification only', permissions: ['view', 'create'] },
    { code: 'read_only', name: 'Read Only', description: 'View-only access to leads', permissions: ['view'] }
  ],
  active_loan: [
    { code: 'full_access', name: 'Full Access', description: 'Complete admin control over loans', permissions: ['all'] },
    { code: 'loan_officer', name: 'Standard Loan Officer', description: 'Origination, rate locks, documents', permissions: ['view', 'edit', 'create'] },
    { code: 'processor', name: 'Processing Team', description: 'Document processing and verification', permissions: ['view', 'edit'] },
    { code: 'underwriter', name: 'Underwriter', description: 'Underwriting decisions and conditions', permissions: ['view', 'edit'] },
    { code: 'read_only', name: 'Read Only', description: 'View-only access to loans', permissions: ['view'] }
  ],
  portfolio: [
    { code: 'full_access', name: 'Full Access', description: 'Complete admin control over portfolio', permissions: ['all'] },
    { code: 'loan_officer', name: 'Standard Loan Officer', description: 'Client relationships, MUM, referrals', permissions: ['view', 'edit', 'create'] },
    { code: 'analyst', name: 'Analyst', description: 'Portfolio analytics and reporting', permissions: ['view'] },
    { code: 'read_only', name: 'Read Only', description: 'View-only access to portfolio', permissions: ['view'] }
  ]
};

// Feature toggles - ALL disabled by default - NO ICONS
const FEATURES = [
  { code: 'ai_receptionist', name: 'AI Receptionist', description: 'AI-powered call handling and routing', category: 'ai' },
  { code: 'power_dialer', name: 'Power Dialer', description: 'Automated outbound calling system', category: 'communication' },
  { code: 'ai_underwriting', name: 'AI Underwriting', description: 'AI-assisted loan underwriting', category: 'ai' },
  { code: 'partners', name: 'Partners', description: 'Partner network management', category: 'business' },
  { code: 'market', name: 'Market', description: 'Market data and analytics', category: 'business' },
  { code: 'profitability', name: 'Profitability', description: 'Financial analytics and reporting', category: 'business' },
  { code: 'voice_os', name: 'Voice OS', description: 'Voice-enabled operations', category: 'ai' },
  { code: 'marketing', name: 'Marketing', description: 'Marketing automation tools', category: 'communication' },
  { code: 'integrations', name: 'Integrations', description: 'Third-party integrations', category: 'automation' },
  { code: 'api_keys', name: 'API Keys', description: 'API access management', category: 'admin' },
  { code: 'it_help_desk', name: 'IT Help Desk', description: 'Technical support access', category: 'business' },
  { code: 'smart_scheduler', name: 'Smart Scheduler', description: 'AI-powered appointment scheduling', category: 'automation' },
  { code: 'video_meetings', name: 'Video Meetings', description: 'Video conferencing tools', category: 'communication' },
  { code: 'data_management', name: 'Data Management', description: 'Data import/export tools', category: 'automation' },
  { code: 'master_admin', name: 'Master Administrator', description: 'Full system administration', category: 'admin' }
];

// Feature categories - NO ICONS
const FEATURE_CATEGORIES = [
  { code: 'ai', name: 'AI Capabilities' },
  { code: 'communication', name: 'Communication' },
  { code: 'business', name: 'Business Tools' },
  { code: 'automation', name: 'Automation' },
  { code: 'admin', name: 'Administration' }
];

function PermissionsStep({
  userId,
  isAdminMode = true,
  initialStages,
  initialFeatures,
  onComplete,
  onBack
}) {
  const [mode, setMode] = useState('simple');
  const [selectedStages, setSelectedStages] = useState(initialStages || []);
  const [enabledFeatures, setEnabledFeatures] = useState(new Set(initialFeatures ? Object.keys(initialFeatures).filter(k => initialFeatures[k]) : []));
  const [expandedStages, setExpandedStages] = useState(new Set());

  useEffect(() => {
    if (initialStages) {
      setSelectedStages(initialStages);
    }
  }, [initialStages]);

  useEffect(() => {
    if (initialFeatures) {
      setEnabledFeatures(new Set(Object.keys(initialFeatures).filter(k => initialFeatures[k])));
    }
  }, [initialFeatures]);

  const handleStageToggle = (stageCode) => {
    setSelectedStages(prev => {
      const existing = prev.find(s => s.stageCode === stageCode);
      if (existing) {
        return prev.filter(s => s.stageCode !== stageCode);
      } else {
        return [...prev, { stageCode, templateCode: null, dataScope: 'assigned' }];
      }
    });
  };

  const handleTemplateSelect = (stageCode, templateCode) => {
    setSelectedStages(prev => {
      // Check if stage exists in selection
      const existing = prev.find(s => s.stageCode === stageCode);
      if (existing) {
        // Update existing stage with template
        return prev.map(s =>
          s.stageCode === stageCode ? { ...s, templateCode } : s
        );
      } else {
        // Add stage with template if not already selected
        return [...prev, { stageCode, templateCode, dataScope: 'assigned' }];
      }
    });
  };

  const handleFeatureToggle = (featureCode) => {
    setEnabledFeatures(prev => {
      const newSet = new Set(prev);
      if (newSet.has(featureCode)) {
        newSet.delete(featureCode);
      } else {
        newSet.add(featureCode);
      }
      return newSet;
    });
  };

  const toggleStageExpand = (stageCode) => {
    setExpandedStages(prev => {
      const newSet = new Set(prev);
      if (newSet.has(stageCode)) {
        newSet.delete(stageCode);
      } else {
        newSet.add(stageCode);
      }
      return newSet;
    });
  };

  const isStageSelected = (stageCode) => selectedStages.some(s => s.stageCode === stageCode);
  const getStageSelection = (stageCode) => selectedStages.find(s => s.stageCode === stageCode);

  const handleContinue = () => {
    const featuresObj = {};
    FEATURES.forEach(f => {
      featuresObj[f.code] = enabledFeatures.has(f.code);
    });

    onComplete({
      stages: selectedStages,
      features: featuresObj,
      customPermissions: {}
    });
  };

  const canContinue = selectedStages.length > 0 && selectedStages.every(s => s.templateCode);

  return (
    <div className="permissions-step">
      <div className="permissions-header">
        <h1>Configure Permissions</h1>
        <p className="permissions-subtitle">
          Select loan stages and permission templates for this user
        </p>
      </div>

      {/* Mode Toggle */}
      <div className="permissions-mode-toggle">
        <button
          className={`mode-btn ${mode === 'simple' ? 'active' : ''}`}
          onClick={() => setMode('simple')}
        >
          Simple
        </button>
        <button
          className={`mode-btn ${mode === 'custom' ? 'active' : ''}`}
          onClick={() => setMode('custom')}
        >
          Custom
        </button>
      </div>

      {/* Stages Section */}
      <div className="stages-section">
        <h2 className="section-title">Loan Stages</h2>
        <p className="section-description">
          Select which loan lifecycle stages this user can access
        </p>

        <div className="stages-grid">
          {LOAN_STAGES.map(stage => {
            const isSelected = isStageSelected(stage.code);
            const selection = getStageSelection(stage.code);
            const templates = TEMPLATES[stage.code] || [];

            return (
              <div
                key={stage.code}
                className={`stage-card ${isSelected ? 'selected' : ''}`}
                style={{ '--stage-color': stage.color }}
              >
                <div
                  className="stage-card-header"
                  onClick={() => handleStageToggle(stage.code)}
                >
                  <div className="stage-info">
                    <h3>{stage.name}</h3>
                    <p>{stage.description}</p>
                  </div>
                  <div className={`stage-checkbox ${isSelected ? 'checked' : ''}`}>
                    {isSelected && <span>✓</span>}
                  </div>
                </div>

                {isSelected && (
                  <div className="stage-templates">
                    <div className="templates-label">Select Permission Template</div>
                    <div className="templates-grid">
                      {templates.map(template => (
                        <div
                          key={template.code}
                          className={`template-card ${selection?.templateCode === template.code ? 'selected' : ''}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            handleTemplateSelect(stage.code, template.code);
                          }}
                        >
                          <div className="template-name">{template.name}</div>
                          <div className="template-description">{template.description}</div>
                          <div className="template-tags">
                            {template.permissions.map(p => (
                              <span key={p} className="template-tag">{p}</span>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Features Section */}
      <div className="features-section">
        <div className="features-header">
          <h2 className="section-title">Feature Access</h2>
          <p className="section-description">
            Enable specific features for this user. Disabled features will be completely hidden.
          </p>
          <div className="features-badge">
            {enabledFeatures.size} of {FEATURES.length} features enabled
          </div>
        </div>

        <div className="features-categories">
          {FEATURE_CATEGORIES.map(category => {
            const categoryFeatures = FEATURES.filter(f => f.category === category.code);
            const enabledCount = categoryFeatures.filter(f => enabledFeatures.has(f.code)).length;

            return (
              <div key={category.code} className="feature-category">
                <div className="category-header">
                  <span className="category-name">{category.name}</span>
                  <span className="category-count">{enabledCount}/{categoryFeatures.length}</span>
                </div>
                <div className="features-grid">
                  {categoryFeatures.map(feature => (
                    <div
                      key={feature.code}
                      className={`feature-card ${enabledFeatures.has(feature.code) ? 'enabled' : ''}`}
                      onClick={() => handleFeatureToggle(feature.code)}
                    >
                      <div className="feature-checkbox">
                        <input
                          type="checkbox"
                          checked={enabledFeatures.has(feature.code)}
                          onChange={() => handleFeatureToggle(feature.code)}
                          onClick={(e) => e.stopPropagation()}
                        />
                      </div>
                      <div className="feature-info">
                        <div className="feature-name">{feature.name}</div>
                        <div className="feature-description">{feature.description}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Summary */}
      {selectedStages.length > 0 && selectedStages.every(s => s.templateCode) && (
        <div className="permissions-summary">
          <h3>Permission Summary</h3>
          <div className="summary-items">
            {selectedStages.map(s => {
              const stage = LOAN_STAGES.find(st => st.code === s.stageCode);
              const template = TEMPLATES[s.stageCode]?.find(t => t.code === s.templateCode);
              return (
                <div key={s.stageCode} className="summary-item">
                  <span className="summary-stage">{stage?.name}</span>
                  <span className="summary-arrow">-</span>
                  <span className="summary-template">{template?.name}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Navigation */}
      <div className="permissions-navigation">
        {onBack && (
          <button className="nav-btn back-btn" onClick={onBack}>
            Back
          </button>
        )}
        <button
          className="nav-btn continue-btn"
          onClick={handleContinue}
          disabled={!canContinue}
        >
          Continue
        </button>
      </div>
    </div>
  );
}

export default PermissionsStep;
