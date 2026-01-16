import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePermissions } from '../../contexts/PermissionContext';
import './MarketingSettings.css';

function LandingPagesSettings() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();
  const canAccessMarketing = isAdmin || hasAnyPermission(['marketing.view', 'marketing.manage', 'admin.manage']) || userRole === 'admin' || userRole === 'sales' || userRole === 'loan_officer';

  const [activeTab, setActiveTab] = useState('pages'); // pages, embed-generator
  const [embedConfig, setEmbedConfig] = useState({
    partnerId: '',
    realtorEmail: '',
    source: 'follow-up-boss',
    width: '100%',
    height: '800',
    borderRadius: '12'
  });
  const [copied, setCopied] = useState(false);

  const landingPages = [
    {
      id: 1,
      name: 'Mortgage Planning Questionnaire',
      description: 'Detailed questionnaire for mortgage planning',
      path: '/questionnaire',
      status: 'active'
    },
    {
      id: 2,
      name: 'Estimate Comparison',
      description: 'Compare loan estimates from different lenders',
      path: '/estimate-comparison',
      status: 'active'
    },
    {
      id: 3,
      name: 'Purchase Application',
      description: 'Full mortgage application for home purchase',
      path: '/apply/purchase',
      status: 'active'
    },
    {
      id: 4,
      name: 'Refinance Application',
      description: 'Full mortgage application for refinancing',
      path: '/apply/refinance',
      status: 'active'
    },
    {
      id: 5,
      name: 'Purchase Pre-Qualification',
      description: 'Quick 3-minute pre-qualification form for realtors',
      path: '/prequal/purchase',
      status: 'active',
      isNew: true,
      embeddable: true
    }
  ];

  // Generate embed code
  const generateEmbedCode = () => {
    const baseUrl = window.location.origin;
    const params = new URLSearchParams();

    if (embedConfig.partnerId) params.append('partner_id', embedConfig.partnerId);
    if (embedConfig.realtorEmail) params.append('realtor_email', embedConfig.realtorEmail);
    params.append('source', embedConfig.source);
    params.append('embedded', 'true');

    const embedUrl = `${baseUrl}/prequal/purchase?${params.toString()}`;

    return `<!-- Perennia AI Pre-Qualification Form -->
<div id="perennia-prequal-container">
  <iframe
    src="${embedUrl}"
    width="${embedConfig.width}"
    height="${embedConfig.height}px"
    frameborder="0"
    style="border: none; border-radius: ${embedConfig.borderRadius}px; box-shadow: 0 4px 20px rgba(0,0,0,0.1);"
    allow="geolocation"
    title="Pre-Qualification Form"
  ></iframe>
</div>
<!-- End Perennia AI Form -->`;
  };

  // Generate script embed code (alternative)
  const generateScriptEmbed = () => {
    const baseUrl = window.location.origin;
    return `<!-- Perennia AI Pre-Qualification Form (Script Version) -->
<div id="perennia-prequal-form"></div>
<script>
  (function() {
    var container = document.getElementById('perennia-prequal-form');
    var iframe = document.createElement('iframe');
    iframe.src = '${baseUrl}/prequal/purchase?partner_id=${embedConfig.partnerId}&realtor_email=${encodeURIComponent(embedConfig.realtorEmail)}&source=${embedConfig.source}&embedded=true';
    iframe.width = '${embedConfig.width}';
    iframe.height = '${embedConfig.height}px';
    iframe.style.border = 'none';
    iframe.style.borderRadius = '${embedConfig.borderRadius}px';
    iframe.style.boxShadow = '0 4px 20px rgba(0,0,0,0.1)';
    iframe.title = 'Pre-Qualification Form';
    container.appendChild(iframe);
  })();
</script>
<!-- End Perennia AI Form -->`;
  };

  // Copy to clipboard
  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  if (!canAccessMarketing) {
    return (
      <div className="marketing-settings-page">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access Marketing Settings.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="marketing-settings-page">
      <div className="settings-header">
        <h2>Landing Pages & Embeds</h2>
        <p>Manage landing pages and generate embed codes for partner integrations</p>
      </div>

      {/* Tab Navigation */}
      <div className="landing-tabs">
        <button
          className={`tab-btn ${activeTab === 'pages' ? 'active' : ''}`}
          onClick={() => setActiveTab('pages')}
        >
          Active Pages
        </button>
        <button
          className={`tab-btn ${activeTab === 'embed-generator' ? 'active' : ''}`}
          onClick={() => setActiveTab('embed-generator')}
        >
          Embed Code Generator
        </button>
      </div>

      {/* Landing Pages Tab */}
      {activeTab === 'pages' && (
        <>
          <div className="landing-pages-grid">
            {landingPages.map((page) => (
              <div key={page.id} className={`landing-page-card ${page.isNew ? 'highlight' : ''}`}>
                <div className="card-header">
                  <h4>
                    {page.name}
                    {page.isNew && <span className="new-badge">NEW</span>}
                  </h4>
                  <span className={`status-badge ${page.status}`}>
                    {page.status === 'active' ? 'Active' : 'Inactive'}
                  </span>
                </div>
                <p className="card-description">{page.description}</p>
                <div className="card-actions">
                  <button
                    className="btn-primary"
                    onClick={() => navigate(page.path)}
                  >
                    View Page
                  </button>
                  <button
                    className="btn-secondary"
                    onClick={() => window.open(page.path, '_blank')}
                  >
                    ↗
                  </button>
                  {page.embeddable && (
                    <button
                      className="btn-embed"
                      onClick={() => setActiveTab('embed-generator')}
                    >
                      &lt;/&gt;
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>

          <div className="add-page-section">
            <button className="btn-add">
              + Create New Landing Page
            </button>
          </div>
        </>
      )}

      {/* Embed Code Generator Tab */}
      {activeTab === 'embed-generator' && (
        <div className="embed-generator">
          <div className="embed-info-banner">
            <div className="info-icon">i</div>
            <div className="info-content">
              <h4>Embed the Pre-Qualification Form</h4>
              <p>
                Generate an embed code to add the pre-qualification form to Follow Up Boss,
                your website, or any other platform that supports HTML embeds.
              </p>
            </div>
          </div>

          <div className="embed-config-section">
            <h3>Configuration</h3>

            <div className="config-grid">
              <div className="config-item">
                <label>Partner ID (Optional)</label>
                <input
                  type="text"
                  value={embedConfig.partnerId}
                  onChange={(e) => setEmbedConfig({ ...embedConfig, partnerId: e.target.value })}
                  placeholder="e.g., your-realtor-id"
                />
                <span className="config-help">Used for tracking and routing leads</span>
              </div>

              <div className="config-item">
                <label>Realtor Email (Optional)</label>
                <input
                  type="email"
                  value={embedConfig.realtorEmail}
                  onChange={(e) => setEmbedConfig({ ...embedConfig, realtorEmail: e.target.value })}
                  placeholder="realtor@example.com"
                />
                <span className="config-help">Receives notification when form is submitted</span>
              </div>

              <div className="config-item">
                <label>Source</label>
                <select
                  value={embedConfig.source}
                  onChange={(e) => setEmbedConfig({ ...embedConfig, source: e.target.value })}
                >
                  <option value="follow-up-boss">Follow Up Boss</option>
                  <option value="website">Website</option>
                  <option value="realtor-partner">Realtor Partner</option>
                  <option value="email-campaign">Email Campaign</option>
                  <option value="social-media">Social Media</option>
                  <option value="other">Other</option>
                </select>
                <span className="config-help">Helps track lead sources</span>
              </div>

              <div className="config-item">
                <label>Width</label>
                <input
                  type="text"
                  value={embedConfig.width}
                  onChange={(e) => setEmbedConfig({ ...embedConfig, width: e.target.value })}
                  placeholder="100%"
                />
                <span className="config-help">Use % or px (e.g., 100% or 600px)</span>
              </div>

              <div className="config-item">
                <label>Height (px)</label>
                <input
                  type="number"
                  value={embedConfig.height}
                  onChange={(e) => setEmbedConfig({ ...embedConfig, height: e.target.value })}
                  placeholder="800"
                />
                <span className="config-help">Recommended: 800px minimum</span>
              </div>

              <div className="config-item">
                <label>Border Radius (px)</label>
                <input
                  type="number"
                  value={embedConfig.borderRadius}
                  onChange={(e) => setEmbedConfig({ ...embedConfig, borderRadius: e.target.value })}
                  placeholder="12"
                />
                <span className="config-help">Rounded corners</span>
              </div>
            </div>
          </div>

          <div className="embed-preview-section">
            <h3>Preview URL</h3>
            <div className="preview-url-box">
              <code>
                {window.location.origin}/prequal/purchase?partner_id={embedConfig.partnerId || 'YOUR_ID'}&source={embedConfig.source}
              </code>
              <button
                className="btn-copy-small"
                onClick={() => copyToClipboard(`${window.location.origin}/prequal/purchase?partner_id=${embedConfig.partnerId}&realtor_email=${embedConfig.realtorEmail}&source=${embedConfig.source}`)}
              >
                Copy URL
              </button>
            </div>
          </div>

          <div className="embed-code-section">
            <h3>Embed Code (iframe)</h3>
            <p className="section-desc">Copy and paste this HTML code where you want the form to appear:</p>
            <div className="code-box">
              <pre>{generateEmbedCode()}</pre>
              <button
                className={`btn-copy ${copied ? 'copied' : ''}`}
                onClick={() => copyToClipboard(generateEmbedCode())}
              >
                {copied ? 'Copied!' : 'Copy Code'}
              </button>
            </div>
          </div>

          <div className="embed-code-section">
            <h3>Alternative: Script Embed</h3>
            <p className="section-desc">Use this if you need more flexibility:</p>
            <div className="code-box">
              <pre>{generateScriptEmbed()}</pre>
              <button
                className="btn-copy"
                onClick={() => copyToClipboard(generateScriptEmbed())}
              >
                Copy Code
              </button>
            </div>
          </div>

          <div className="embed-instructions">
            <h3>How to Embed in Follow Up Boss</h3>
            <ol>
              <li>Go to your Follow Up Boss account</li>
              <li>Navigate to <strong>Settings → Websites</strong> or the custom page builder</li>
              <li>Add an <strong>HTML/Embed block</strong> or <strong>Custom Code</strong> section</li>
              <li>Paste the embed code from above</li>
              <li>Save and publish your changes</li>
            </ol>

            <div className="tip-box">
              <strong>Tip:</strong> The form will automatically route leads based on credit score,
              employment type, and timeline. Complex cases are flagged for senior review.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default LandingPagesSettings;
