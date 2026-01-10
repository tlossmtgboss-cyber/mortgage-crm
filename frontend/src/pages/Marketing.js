import React, { useState, useEffect, lazy, Suspense } from 'react';
import { useSearchParams } from 'react-router-dom';
import './Marketing.css';

// Lazy load the marketing tool components
const AIOutreach = lazy(() => import('./AIOutreach'));
const AvatarStudio = lazy(() => import('./AvatarStudio'));
const CommunicationIntelligence = lazy(() => import('./CommunicationIntelligence'));
const AcquisitionDashboard = lazy(() => import('./AcquisitionDashboard'));
const ConversationIntelligence = lazy(() => import('./ConversationIntelligence'));
const AIDailyBlog = lazy(() => import('./AIDailyBlog'));
const AIReceptionistDashboard = lazy(() => import('./AIReceptionistDashboard'));
const PowerDialer = lazy(() => import('./PowerDialer'));
const LiveCallWhisper = lazy(() => import('./LiveCallWhisper'));

// Marketing settings components (inline for now, can be extracted)
const LandingPagesSettings = lazy(() => import('./marketing/LandingPagesSettings'));
const EmailMarketingSettings = lazy(() => import('./marketing/EmailMarketingSettings'));
const TextMarketingSettings = lazy(() => import('./marketing/TextMarketingSettings'));
const VoicemailSettings = lazy(() => import('./marketing/VoicemailSettings'));
const MicrositeSettings = lazy(() => import('./marketing/MicrositeSettings'));
const PreApprovalLetterSettings = lazy(() => import('./marketing/PreApprovalLetterSettings'));
const ApplicationSlidesSettings = lazy(() => import('./marketing/ApplicationSlidesSettings'));

// Tool categories and items
const MARKETING_TOOLS = [
  {
    category: 'Outreach & Communication',
    tools: [
      { id: 'ai-outreach', name: 'AI Outreach', description: 'Automated AI-powered outreach campaigns' },
      { id: 'ai-receptionist', name: 'AI Receptionist', description: 'AI-powered phone receptionist' },
      { id: 'power-dialer', name: 'Power Dialer', description: 'High-volume outbound calling' },
      { id: 'communication', name: 'Communication Hub', description: 'Email and SMS management' },
      { id: 'call-intelligence', name: 'Call Intelligence', description: 'AI-powered call analysis and insights' },
      { id: 'live-call-whisper', name: 'Live Call Whisper', description: 'Real-time AI coaching during calls' },
      { id: 'call-qa', name: 'Call QA', description: 'Call quality analysis and coaching' },
    ]
  },
  {
    category: 'Content & Media',
    tools: [
      { id: 'avatar-studio', name: 'Avatar Studio', description: 'AI video avatar creation' },
      { id: 'ai-blog', name: 'AI Blog', description: 'AI-generated blog content' },
    ]
  },
  {
    category: 'Lead Generation',
    tools: [
      { id: 'acquisition', name: 'Acquisition Engine', description: 'Lead acquisition campaigns' },
      { id: 'landing-pages', name: 'Landing Pages', description: 'Create and manage landing pages' },
      { id: 'microsite', name: 'Microsite Builder', description: 'Personal marketing microsites' },
    ]
  },
  {
    category: 'Templates & Assets',
    tools: [
      { id: 'email-marketing', name: 'Email Templates', description: 'Email marketing templates' },
      { id: 'text-marketing', name: 'SMS Templates', description: 'Text message templates' },
      { id: 'voicemail', name: 'Voicemail Drops', description: 'Ringless voicemail templates' },
      { id: 'pre-approval-letter', name: 'Pre-Approval Letters', description: 'Customize pre-approval letters' },
      { id: 'application-slides', name: 'Application Slides', description: 'Loan application presentation' },
    ]
  }
];

// Loading spinner component
const LoadingSpinner = () => (
  <div className="marketing-loading">
    <div className="spinner"></div>
    <p>Loading...</p>
  </div>
);

// Placeholder for tools that need to be migrated
const ComingSoonPlaceholder = ({ toolName }) => (
  <div className="marketing-placeholder">
    <div className="placeholder-icon">🚧</div>
    <h2>{toolName}</h2>
    <p>This tool is being migrated to the Marketing Hub.</p>
  </div>
);

function Marketing() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTool, setActiveTool] = useState(searchParams.get('tool') || 'ai-outreach');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // Update URL when tool changes
  useEffect(() => {
    setSearchParams({ tool: activeTool });
  }, [activeTool, setSearchParams]);

  // Get active tool info
  const getActiveToolInfo = () => {
    for (const category of MARKETING_TOOLS) {
      const tool = category.tools.find(t => t.id === activeTool);
      if (tool) return tool;
    }
    return null;
  };

  const activeToolInfo = getActiveToolInfo();

  // Render the active tool component
  const renderActiveTool = () => {
    switch (activeTool) {
      case 'ai-outreach':
        return <AIOutreach />;
      case 'ai-receptionist':
        return <AIReceptionistDashboard />;
      case 'power-dialer':
        return <PowerDialer />;
      case 'avatar-studio':
        return <AvatarStudio />;
      case 'communication':
        return <CommunicationIntelligence />;
      case 'acquisition':
        return <AcquisitionDashboard />;
      case 'call-qa':
        return <ConversationIntelligence />;
      case 'call-intelligence':
        return <ConversationIntelligence />;
      case 'live-call-whisper':
        return <LiveCallWhisper />;
      case 'ai-blog':
        return <AIDailyBlog />;
      case 'landing-pages':
        return <LandingPagesSettings />;
      case 'email-marketing':
        return <EmailMarketingSettings />;
      case 'text-marketing':
        return <TextMarketingSettings />;
      case 'voicemail':
        return <VoicemailSettings />;
      case 'microsite':
        return <MicrositeSettings />;
      case 'pre-approval-letter':
        return <PreApprovalLetterSettings />;
      case 'application-slides':
        return <ApplicationSlidesSettings />;
      default:
        return <ComingSoonPlaceholder toolName={activeToolInfo?.name || 'Unknown Tool'} />;
    }
  };

  return (
    <div className={`marketing-page ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      {/* Sidebar */}
      <aside className="marketing-sidebar">
        <div className="sidebar-header">
          <h2>Marketing Lab</h2>
          <button
            className="collapse-btn"
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {sidebarCollapsed ? '→' : '←'}
          </button>
        </div>

        <nav className="sidebar-nav">
          {MARKETING_TOOLS.map((category) => (
            <div key={category.category} className="nav-category">
              <h3 className="category-title">{category.category}</h3>
              <ul className="category-tools">
                {category.tools.map((tool) => (
                  <li key={tool.id}>
                    <button
                      className={`tool-btn ${activeTool === tool.id ? 'active' : ''}`}
                      onClick={() => setActiveTool(tool.id)}
                      title={tool.description}
                    >
                      <span className="tool-name">{tool.name}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
      </aside>

      {/* Main Content */}
      <main className="marketing-main">
        <div className="main-header">
          <div className="header-info">
            <div>
              <h1>{activeToolInfo?.name}</h1>
              <p className="header-description">{activeToolInfo?.description}</p>
            </div>
          </div>
        </div>

        <div className="main-content">
          <Suspense fallback={<LoadingSpinner />}>
            {renderActiveTool()}
          </Suspense>
        </div>
      </main>
    </div>
  );
}

export default Marketing;
