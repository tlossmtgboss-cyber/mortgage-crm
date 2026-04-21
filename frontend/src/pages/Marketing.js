import React, { useState, useEffect, lazy, Suspense } from 'react';
import { useSearchParams } from 'react-router-dom';
import './Marketing.css';

// Lazy load the marketing tool components
const AIOutreach = lazy(() => import('./AIOutreach'));
const CommunicationIntelligence = lazy(() => import('./CommunicationIntelligence'));
const AcquisitionDashboard = lazy(() => import('./AcquisitionDashboard'));
const ConversationIntelligence = lazy(() => import('./ConversationIntelligence'));
const AIDailyBlog = lazy(() => import('./AIDailyBlog'));
const AIReceptionistDashboard = lazy(() => import('./AIReceptionistDashboard'));
const PowerDialer = lazy(() => import('./PowerDialer'));
const LiveCallWhisper = lazy(() => import('./LiveCallWhisper'));
const DealAlertsDashboard = lazy(() => import('../components/DealAlerts').then(m => ({ default: m.DealAlertsDashboard })));

// Voice & Call Center components
const AgentStudio = lazy(() => import('../components/voice/AgentStudio'));
const LiveCallsMonitor = lazy(() => import('../components/voice/LiveCallsMonitor'));
const CallQueueDashboard = lazy(() => import('../components/voice/CallQueueDashboard'));
const ConferenceRoomDashboard = lazy(() => import('../components/voice/ConferenceRoomDashboard'));
const IVRMenuDashboard = lazy(() => import('../components/voice/IVRMenuDashboard'));
const HoldMusicDashboard = lazy(() => import('../components/voice/HoldMusicDashboard'));
const TalkToAgentPage = lazy(() => import('../components/voice/TalkToAgentPage'));
const CallAnalyticsDashboard = lazy(() => import('../components/voice/CallAnalyticsDashboard'));
const VoiceConversation = lazy(() => import('../components/voice/VoiceConversation'));

// Video OS component
const VideoOS = lazy(() => import('./VideoOS'));

// Carousel Builder component
const CarouselBuilder = lazy(() => import('./CarouselBuilder/CarouselBuilderPage'));

// Content Marketing component
const ContentMarketing = lazy(() => import('./ContentMarketing'));

// Marketing settings components
const LandingPagesSettings = lazy(() => import('./marketing/LandingPagesSettings'));
const EmailMarketingSettings = lazy(() => import('./marketing/EmailMarketingSettings'));
const TextMarketingSettings = lazy(() => import('./marketing/TextMarketingSettings'));
const VoicemailSettings = lazy(() => import('./marketing/VoicemailSettings'));
const MicrositeSettings = lazy(() => import('./marketing/MicrositeSettings'));
const PreApprovalLetterSettings = lazy(() => import('./marketing/PreApprovalLetterSettings'));
const ApplicationSlidesSettings = lazy(() => import('./marketing/ApplicationSlidesSettings'));

// Main category tabs with their tools
const MARKETING_CATEGORIES = {
  'outreach-communication': {
    id: 'outreach-communication',
    name: 'Outreach & Communication',
    icon: '💬',
    tools: [
      { id: 'ai-outreach', name: 'AI Outreach', description: 'Automated AI-powered outreach campaigns' },
      { id: 'communication', name: 'Communication Hub', description: 'Email and SMS management' },
      { id: 'deal-alerts', name: 'Deal Alerts', description: 'Proactive pipeline monitoring and alerts' },
    ]
  },
  'voice': {
    id: 'voice',
    name: 'Voice',
    icon: '🎙️',
    tools: [
      { id: 'voice-conversation', name: 'Voice Conversation', description: 'Talk to Aria with your preferred voice' },
      { id: 'voice-agents', name: 'Voice Agents', description: 'Create and manage AI voice agents' },
      { id: 'talk-to-agent', name: 'Talk to Agent', description: 'Direct call routing to agents' },
      { id: 'hold-music', name: 'Hold Music', description: 'Customize hold music and messages' },
      { id: 'ivr-menus', name: 'IVR Menus', description: 'Interactive voice response menus' },
    ]
  },
  'call-center': {
    id: 'call-center',
    name: 'Call Center',
    icon: '📞',
    tools: [
      { id: 'ai-receptionist', name: 'AI Receptionist', description: 'AI-powered phone receptionist' },
      { id: 'live-calls', name: 'Live Calls', description: 'Monitor active calls in real-time' },
      { id: 'power-dialer', name: 'Power Dialer', description: 'High-volume outbound calling' },
      { id: 'call-queues', name: 'Call Queues', description: 'Manage inbound call queues' },
      { id: 'conference-rooms', name: 'Conference Rooms', description: 'Virtual conference room management' },
      { id: 'call-analytics', name: 'Call Analytics', description: 'Call performance metrics and insights' },
      { id: 'call-intelligence', name: 'Call Intelligence', description: 'AI-powered call analysis and insights' },
      { id: 'live-call-whisper', name: 'Live Call Whisper', description: 'Real-time AI coaching during calls' },
      { id: 'call-qa', name: 'Call QA', description: 'Call quality analysis and coaching' },
    ]
  },
  'content-media': {
    id: 'content-media',
    name: 'Content & Media',
    icon: '🎬',
    tools: [
      { id: 'video-os', name: 'Video OS', description: 'Record and manage personalized video messages' },
      { id: 'ai-blog', name: 'AI Blog', description: 'AI-generated blog content' },
      { id: 'carousel-builder', name: 'Carousel Builder', description: 'Create engaging social media carousels' },
      { id: 'content-marketing', name: 'Content Marketing', description: 'Brand voice, calendars, briefs, and SEO keywords' },
    ]
  },
  'lead-generation': {
    id: 'lead-generation',
    name: 'Lead Generation',
    icon: '🎯',
    tools: [
      { id: 'acquisition', name: 'Acquisition Engine', description: 'Lead acquisition campaigns' },
      { id: 'landing-pages', name: 'Landing Pages', description: 'Create and manage landing pages' },
      { id: 'microsite', name: 'Microsite Builder', description: 'Personal marketing microsites' },
    ]
  },
  'templates-assets': {
    id: 'templates-assets',
    name: 'Templates & Assets',
    icon: '📋',
    tools: [
      { id: 'email-marketing', name: 'Email Templates', description: 'Email marketing templates' },
      { id: 'text-marketing', name: 'SMS Templates', description: 'Text message templates' },
      { id: 'voicemail', name: 'Voicemail Drops', description: 'Ringless voicemail templates' },
      { id: 'pre-approval-letter', name: 'Pre-Approval Letters', description: 'Customize pre-approval letters' },
      { id: 'application-slides', name: 'Application Slides', description: 'Loan application presentation' },
    ]
  }
};

// Get category from tool ID
const getCategoryFromTool = (toolId) => {
  for (const [categoryId, category] of Object.entries(MARKETING_CATEGORIES)) {
    if (category.tools.some(t => t.id === toolId)) {
      return categoryId;
    }
  }
  return 'outreach-communication';
};

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
  const initialTool = searchParams.get('tool') || 'ai-outreach';
  const initialCategory = searchParams.get('category') || getCategoryFromTool(initialTool);

  const [activeCategory, setActiveCategory] = useState(initialCategory);
  const [activeTool, setActiveTool] = useState(initialTool);

  // Update URL when tool changes
  useEffect(() => {
    setSearchParams({ category: activeCategory, tool: activeTool });
  }, [activeCategory, activeTool, setSearchParams]);

  // Handle category change
  const handleCategoryChange = (categoryId) => {
    setActiveCategory(categoryId);
    // Set first tool in category as active
    const firstTool = MARKETING_CATEGORIES[categoryId].tools[0];
    if (firstTool) {
      setActiveTool(firstTool.id);
    }
  };

  // Get active tool info
  const getActiveToolInfo = () => {
    const category = MARKETING_CATEGORIES[activeCategory];
    if (category) {
      return category.tools.find(t => t.id === activeTool);
    }
    return null;
  };

  const activeToolInfo = getActiveToolInfo();
  const currentCategory = MARKETING_CATEGORIES[activeCategory];

  // Render the active tool component
  const renderActiveTool = () => {
    switch (activeTool) {
      // Outreach & Communication
      case 'ai-outreach':
        return <AIOutreach />;
      case 'communication':
        return <CommunicationIntelligence />;
      case 'deal-alerts':
        return <DealAlertsDashboard embedded={true} />;

      // Voice & Call Center
      case 'ai-receptionist':
        return <AIReceptionistDashboard />;
      case 'voice-conversation':
        return <VoiceConversation />;
      case 'voice-agents':
        return <AgentStudio />;
      case 'live-calls':
        return <LiveCallsMonitor />;
      case 'power-dialer':
        return <PowerDialer />;
      case 'call-queues':
        return <CallQueueDashboard />;
      case 'conference-rooms':
        return <ConferenceRoomDashboard />;
      case 'ivr-menus':
        return <IVRMenuDashboard />;
      case 'hold-music':
        return <HoldMusicDashboard />;
      case 'talk-to-agent':
        return <TalkToAgentPage />;
      case 'call-analytics':
        return <CallAnalyticsDashboard />;
      case 'call-intelligence':
        return <ConversationIntelligence />;
      case 'live-call-whisper':
        return <LiveCallWhisper />;
      case 'call-qa':
        return <ConversationIntelligence />;

      // Content & Media
      case 'video-os':
        return <VideoOS />;
      case 'ai-blog':
        return <AIDailyBlog />;
      case 'carousel-builder':
        return <CarouselBuilder embedded={true} />;
      case 'content-marketing':
        return <ContentMarketing embedded={true} />;

      // Lead Generation
      case 'acquisition':
        return <AcquisitionDashboard />;
      case 'landing-pages':
        return <LandingPagesSettings />;
      case 'microsite':
        return <MicrositeSettings />;

      // Templates & Assets
      case 'email-marketing':
        return <EmailMarketingSettings />;
      case 'text-marketing':
        return <TextMarketingSettings />;
      case 'voicemail':
        return <VoicemailSettings />;
      case 'pre-approval-letter':
        return <PreApprovalLetterSettings />;
      case 'application-slides':
        return <ApplicationSlidesSettings />;

      default:
        return <ComingSoonPlaceholder toolName={activeToolInfo?.name || 'Unknown Tool'} />;
    }
  };

  return (
    <div className="marketing-page tabbed-layout">
      {/* Page Header */}
      <div className="marketing-header">
        <h1>Marketing Lab</h1>
      </div>

      {/* Main Category Tabs */}
      <div className="marketing-category-tabs">
        {Object.values(MARKETING_CATEGORIES).map((category) => (
          <button
            key={category.id}
            className={`category-tab ${activeCategory === category.id ? 'active' : ''}`}
            onClick={() => handleCategoryChange(category.id)}
          >
            <span className="tab-icon">{category.icon}</span>
            <span className="tab-name">{category.name}</span>
          </button>
        ))}
      </div>

      {/* Sub-Navigation Bar */}
      <div className="marketing-sub-nav">
        <div className="sub-nav-scroll">
          {currentCategory?.tools.map((tool) => (
            <button
              key={tool.id}
              className={`sub-nav-item ${activeTool === tool.id ? 'active' : ''}`}
              onClick={() => setActiveTool(tool.id)}
              title={tool.description}
            >
              {tool.name}
            </button>
          ))}
        </div>
      </div>

      {/* Tool Description */}
      {activeToolInfo && (
        <div className="tool-description-bar">
          <span className="tool-desc">{activeToolInfo.description}</span>
        </div>
      )}

      {/* Main Content */}
      <main className="marketing-main tabbed">
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
