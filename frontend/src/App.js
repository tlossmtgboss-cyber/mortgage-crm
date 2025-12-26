import { useState, useEffect, lazy, Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { Capacitor } from '@capacitor/core';
import { isAuthenticatedSync as isAuthenticated } from './utils/auth';
import { ImpersonationProvider } from './contexts/ImpersonationContext';
import { PermissionProvider } from './contexts/PermissionContext';
import Navigation from './components/Navigation';
import AIAssistant from './components/AIAssistant';
import CoachCorner from './components/CoachCorner';
import OnboardingPrompt from './components/OnboardingPrompt';
import ImpersonationBanner from './components/ImpersonationBanner';
import ErrorBoundary from './components/ErrorBoundary';
import UnifiedTaskSidebar from './components/UnifiedTaskSidebar';
import EmailDropZone from './components/EmailDropZone';
import GlobalLayoutFix from './components/GlobalLayoutFix';
import GlobalSearch from './components/GlobalSearch';
import './App.css';

// Landing/Auth pages (keep these as regular imports for faster initial load)
import LandingPage from './pages/LandingPage';
import Registration from './pages/Registration';
import AccountVerification from './pages/AccountVerification';
import EmailVerificationSent from './pages/EmailVerificationSent';
import Login from './pages/Login';
import Onboarding from './pages/Onboarding';
import ApplicationSubmitted from './pages/ApplicationSubmitted';

// Lazy load all other pages for instant navigation
const Dashboard = lazy(() => import('./pages/Dashboard'));
const CommandCenter = lazy(() => import('./pages/CommandCenter'));
const OnboardingWizard = lazy(() => import('./components/onboarding/OnboardingWizard'));
const Leads = lazy(() => import('./pages/Leads'));
const LeadDetail = lazy(() => import('./pages/LeadDetail'));
const Loans = lazy(() => import('./pages/Loans'));
const LoanDetail = lazy(() => import('./pages/LoanDetail'));
const Portfolio = lazy(() => import('./pages/Portfolio'));
const PortfolioDetail = lazy(() => import('./pages/PortfolioDetail'));
const MumClientDetail = lazy(() => import('./pages/MumClientDetail'));
const YearOverYear = lazy(() => import('./pages/YearOverYear'));
const Tasks = lazy(() => import('./pages/Tasks'));
const Calendar = lazy(() => import('./pages/Calendar'));
const Scorecard = lazy(() => import('./pages/Scorecard'));
const Assistant = lazy(() => import('./pages/Assistant'));
const ClientProfile = lazy(() => import('./pages/ClientProfile'));
const ReferralPartners = lazy(() => import('./pages/ReferralPartners'));
const ReferralPartnerDetail = lazy(() => import('./pages/ReferralPartnerDetail'));
const PartnerDashboardPortal = lazy(() => import('./pages/PartnerDashboardPortal'));
const PartnerClientDetail = lazy(() => import('./pages/PartnerClientDetail'));
const AIUnderwriter = lazy(() => import('./pages/AIUnderwriter'));
const GoalTracker = lazy(() => import('./pages/GoalTracker'));
const Coach = lazy(() => import('./pages/Coach'));
const ReconciliationCenter = lazy(() => import('./pages/ReconciliationCenter'));
const MergeCenter = lazy(() => import('./pages/MergeCenter'));
const Settings = lazy(() => import('./pages/Settings'));
const TeamMembers = lazy(() => import('./pages/TeamMembers'));
const TeamMemberProfile = lazy(() => import('./pages/TeamMemberProfile'));
const MyProfile = lazy(() => import('./pages/MyProfile'));
const MyPermissions = lazy(() => import('./pages/MyPermissions'));
const ComplianceDashboard = lazy(() => import('./pages/ComplianceDashboard'));
const AdminSettings = lazy(() => import('./pages/AdminSettings'));
const AdminCustomDomains = lazy(() => import('./pages/AdminCustomDomains'));
const DataUpload = lazy(() => import('./pages/DataUpload'));
const EstimateComparison = lazy(() => import('./pages/EstimateComparison'));
const Users = lazy(() => import('./pages/Users'));
const UserProfile = lazy(() => import('./pages/UserProfile'));
const ProcessTemplates = lazy(() => import('./pages/ProcessTemplates'));
const BuyerIntake = lazy(() => import('./pages/BuyerIntake'));
const VerizonTest = lazy(() => import('./pages/VerizonTest'));
const PipelineEfficiency = lazy(() => import('./pages/PipelineEfficiency'));
const StageEmployees = lazy(() => import('./pages/StageEmployees'));
const EmployeeLoans = lazy(() => import('./pages/EmployeeLoans'));
const TeamRoleEmployees = lazy(() => import('./pages/TeamRoleEmployees'));
const BottleneckLoans = lazy(() => import('./pages/BottleneckLoans'));
const AIReceptionistDashboard = lazy(() => import('./pages/AIReceptionistDashboard'));
const VoiceOSDashboard = lazy(() => import('./pages/VoiceOSDashboard'));
const AILandingPage = lazy(() => import('./pages/AILandingPage'));
const WorkflowDashboard = lazy(() => import('./pages/WorkflowDashboard'));
const WorkflowStagePage = lazy(() => import('./pages/WorkflowStagePage'));
const MarketDashboard = lazy(() => import('./pages/MarketDashboard'));
const MorningCheckin = lazy(() => import('./pages/MorningCheckin'));
const PartnerROIDashboard = lazy(() => import('./pages/PartnerROIDashboard'));
const ProfitabilityDashboard = lazy(() => import('./pages/ProfitabilityDashboard'));
const ScenarioModeling = lazy(() => import('./pages/ScenarioModeling'));
const SLASettings = lazy(() => import('./pages/SLASettings'));
const EmployeeOnboardingAdmin = lazy(() => import('./pages/EmployeeOnboardingAdmin'));
const AcceptInvite = lazy(() => import('./pages/AcceptInvite'));
const MortgagePlannerQuestionnaire = lazy(() => import('./pages/MortgagePlannerQuestionnaire'));
const KnowledgeBase = lazy(() => import('./pages/KnowledgeBase'));
const PowerDialer = lazy(() => import('./pages/PowerDialer'));
const UserCreationWizard = lazy(() => import('./pages/UserCreationWizard'));
const UserBulkUpload = lazy(() => import('./pages/UserBulkUpload'));
const ActivateAccount = lazy(() => import('./pages/ActivateAccount'));
const MeetingRoom = lazy(() => import('./pages/MeetingRoom'));
const OAuthCallback = lazy(() => import('./pages/OAuthCallback'));
const WorkflowStatusDetail = lazy(() => import('./pages/WorkflowStatusDetail'));
const EmailIntelligence = lazy(() => import('./pages/EmailIntelligence'));
const CommunicationIntelligence = lazy(() => import('./pages/CommunicationIntelligence'));
const AIOutreach = lazy(() => import('./pages/AIOutreach'));
const ConversationIntelligence = lazy(() => import('./pages/ConversationIntelligence'));
const ConversationIntelligenceRecordingDetail = lazy(() => import('./pages/ConversationIntelligenceRecordingDetail'));
const SmartDocs = lazy(() => import('./pages/SmartDocs'));
const SmartDocsClientDetail = lazy(() => import('./pages/SmartDocsClientDetail'));
const SmartDocsDashboard = lazy(() => import('./pages/SmartDocsDashboard'));
const AIDailyBlog = lazy(() => import('./pages/AIDailyBlog'));
const PublicBooking = lazy(() => import('./pages/PublicBooking'));
const BorrowerApplication = lazy(() => import('./pages/BorrowerApplication'));
const AdaptiveURLA = lazy(() => import('./pages/AdaptiveURLA'));
const PurchaseApplication = lazy(() => import('./pages/PurchaseApplication'));
const RefinanceApplication = lazy(() => import('./pages/RefinanceApplication'));
const CoborrowerApplication = lazy(() => import('./pages/CoborrowerApplication'));
const BorrowerLogin = lazy(() => import('./pages/BorrowerLogin'));
const BorrowerOAuthCallback = lazy(() => import('./pages/BorrowerOAuthCallback'));
const ApplicationAnalytics = lazy(() => import('./pages/ApplicationAnalytics'));
const BorrowerPortal = lazy(() => import('./pages/BorrowerPortal'));
const LOMicrosite = lazy(() => import('./pages/microsites/LOMicrosite'));
const ThemeRenderer = lazy(() => import('./pages/microsites/ThemeRenderer'));
const ThemePreview = lazy(() => import('./pages/microsites/ThemePreview'));
const MicrositePreview = lazy(() => import('./pages/microsites/MicrositePreview'));
const MicrositeWizard = lazy(() => import('./components/microsites/MicrositeWizard'));
const MicrositeEditor = lazy(() => import('./pages/MicrositeEditor'));
const LODashboard = lazy(() => import('./pages/LODashboard'));
const RealtorDashboard = lazy(() => import('./pages/RealtorDashboard'));
const RealtorPortal = lazy(() => import('./pages/RealtorPortal'));
const AdminPanel = lazy(() => import('./pages/AdminPanel'));
const AgentDashboard = lazy(() => import('./pages/AgentDashboard'));
const AgentProfile = lazy(() => import('./pages/AgentProfile'));
const AgentGym = lazy(() => import('./pages/AgentGym'));
const AgentGovernanceSettings = lazy(() => import('./pages/AgentGovernanceSettings'));
const SmartSchedulerSettings = lazy(() => import('./pages/SmartSchedulerSettings'));
const EmailIntegrationSettings = lazy(() => import('./pages/EmailIntegrationSettings'));
const UserProfileSettings = lazy(() => import('./pages/UserProfileSettings'));
const DocumentUploadSettings = lazy(() => import('./pages/DocumentUploadSettings'));
const LeadCaptureSettings = lazy(() => import('./pages/LeadCaptureSettings'));
const ClientPortalSettings = lazy(() => import('./pages/ClientPortalSettings'));
const CommunicationPreferences = lazy(() => import('./pages/CommunicationPreferences'));
const IntegrationSettings = lazy(() => import('./pages/IntegrationSettings'));
const APIKeysSettings = lazy(() => import('./pages/APIKeysSettings'));
const CompanyBrandingSettings = lazy(() => import('./pages/CompanyBrandingSettings'));
const PURLDashboard = lazy(() => import('./pages/PURLDashboard'));
const PURLPortal = lazy(() => import('./pages/PURLPortal'));
const PURLApplication = lazy(() => import('./pages/PURLApplication'));
const PortalContainer = lazy(() => import('./pages/portal/PortalContainer'));
const AdminDocumentReviewQueue = lazy(() => import('./pages/AdminDocumentReviewQueue'));

// Portal Components - Real-time borrower and partner portals
const ActiveLoanPortalComplete = lazy(() => import('./components/portal/ActiveLoanPortalComplete'));
const PartnerPortalView = lazy(() => import('./components/portal/PartnerPortalView'));
const PerenniaClientPortalUltimate = lazy(() => import('./components/portal/PerenniaClientPortalUltimate'));
const HomeValueIntelligence = lazy(() => import('./components/portal/HomeValueIntelligence'));
const PresentationEngine = lazy(() => import('./components/portal/PresentationEngine'));
const TotalCostAnalysis = lazy(() => import('./components/portal/TotalCostAnalysis'));

// Simple loading component
const PageLoader = () => (
  <div style={{
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center',
    height: '100vh',
    fontSize: '14px',
    color: '#666'
  }}>
    Loading...
  </div>
);

// Use HTTPS Railway URL in production, localhost for development
const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const API_BASE_URL = isProduction
  ? 'https://api.perenniaai.com'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

function PrivateRoute({ children }) {
  if (!isAuthenticated()) {
    return <Navigate to="/login" />;
  }

  return children;
}

// Wrapper to handle lazy-loaded pages with suspense
function LazyPage({ children }) {
  return (
    <Suspense fallback={<PageLoader />}>
      {children}
    </Suspense>
  );
}

function App() {
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [coachOpen, setCoachOpen] = useState(false);
  const [taskSidebarOpen, setTaskSidebarOpen] = useState(false);

  // Task counts for navigation badges (MUM = Client for Life Engine tasks)
  const [taskCounts, setTaskCounts] = useState({
    leads: 0,
    loans: 0,
    portfolio: 3,  // MUM tasks
    tasks: 0,
    urgentTasks: 0,
    partners: 0,
    unifiedTasks: 0  // New unified task count
  });

  const toggleAssistant = () => {
    setAssistantOpen(!assistantOpen);
  };

  const toggleCoach = () => {
    setCoachOpen(!coachOpen);
  };

  const toggleTaskSidebar = () => {
    setTaskSidebarOpen(!taskSidebarOpen);
  };

  const handleUnifiedTaskCountChange = (count) => {
    setTaskCounts(prev => ({ ...prev, unifiedTasks: count }));
  };

  // Fetch task counts for navigation badges
  useEffect(() => {
    const fetchTaskCounts = async () => {
      if (!isAuthenticated()) return;

      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/tasks`, {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`
          }
        });

        if (response.ok) {
          const tasks = await response.json();
          // Count outstanding tasks (not completed)
          const outstandingTasks = tasks.filter(t => t.status !== 'completed' && t.status !== 'done').length;
          // Count urgent tasks (high priority and not completed)
          const urgentTasks = tasks.filter(t => t.priority === 'high' && t.status !== 'completed' && t.status !== 'done').length;
          setTaskCounts(prev => ({
            ...prev,
            tasks: outstandingTasks,
            urgentTasks: urgentTasks
          }));
        }
      } catch (error) {
        console.error('Error fetching task counts:', error);
      }
    };

    // OPTIMIZED: Delay initial fetch by 1 second to not block page load
    const initialTimeout = setTimeout(fetchTaskCounts, 1000);
    // Refresh task counts every 5 minutes (reduced frequency)
    const interval = setInterval(fetchTaskCounts, 300000);
    return () => {
      clearTimeout(initialTimeout);
      clearInterval(interval);
    };
  }, []);

  return (
    <ErrorBoundary>
      <ImpersonationProvider>
        <PermissionProvider>
          <Router>
            <GlobalLayoutFix />
            <EmailDropZone>
            <ImpersonationBanner />
            <div className="app">
        <Routes>
          {/* Public routes - Mobile app skips landing page */}
          <Route path="/" element={
            Capacitor.isNativePlatform()
              ? (isAuthenticated() ? <Navigate to="/dashboard" /> : <Navigate to="/login" />)
              : <LandingPage />
          } />
          <Route path="/apply" element={<BuyerIntake />} />
          <Route path="/mortgage-planner" element={<LazyPage><MortgagePlannerQuestionnaire /></LazyPage>} />
          <Route path="/questionnaire" element={<LazyPage><MortgagePlannerQuestionnaire /></LazyPage>} />
          <Route path="/estimate-comparison" element={<LazyPage><EstimateComparison /></LazyPage>} />
          <Route path="/register" element={<Registration />} />
          <Route path="/verify-account" element={<AccountVerification />} />
          <Route path="/verify-email-sent" element={<EmailVerificationSent />} />
          <Route path="/login" element={<Login />} />
          <Route path="/application-submitted" element={<ApplicationSubmitted />} />

          {/* Realtor Portal (public - token-based auth) */}
          <Route path="/realtor-portal" element={<LazyPage><RealtorPortal /></LazyPage>} />

          {/* Employee Invite Accept (public) */}
          <Route path="/invite/accept/:token" element={<LazyPage><AcceptInvite /></LazyPage>} />
          <Route path="/accept-invite" element={<LazyPage><AcceptInvite /></LazyPage>} />

          {/* User Activation (public) */}
          <Route path="/activate" element={<LazyPage><ActivateAccount /></LazyPage>} />

          {/* Video Meeting Room (public/private) */}
          <Route path="/meeting/:roomCode" element={<LazyPage><MeetingRoom /></LazyPage>} />

          {/* Public Booking Page */}
          <Route path="/book/:slug" element={<LazyPage><PublicBooking /></LazyPage>} />

          {/* Loan Officer Microsite (public) - Uses ThemeRenderer for dynamic themes */}
          <Route path="/lo/:slug" element={<LazyPage><ThemeRenderer /></LazyPage>} />
          <Route path="/lo/:slug/:pageSlug" element={<LazyPage><ThemeRenderer /></LazyPage>} />
          <Route path="/microsite/loan-officer/:userId" element={<LazyPage><ThemeRenderer /></LazyPage>} />
          <Route path="/microsite/preview" element={<LazyPage><MicrositePreview /></LazyPage>} />

          {/* Theme Preview (public) - Preview themes with sample data */}
          <Route path="/preview/theme/:themeSlug" element={<LazyPage><ThemePreview /></LazyPage>} />

          {/* Borrower Login (public - social login for applicants) */}
          <Route path="/apply/login" element={<LazyPage><BorrowerLogin /></LazyPage>} />

          {/* Borrower Application Start (after social login) - New Adaptive URLA */}
          <Route path="/apply/start" element={<LazyPage><AdaptiveURLA /></LazyPage>} />

          {/* Purpose-specific applications */}
          <Route path="/apply/purchase" element={<LazyPage><PurchaseApplication /></LazyPage>} />
          <Route path="/apply/refinance" element={<LazyPage><RefinanceApplication /></LazyPage>} />

          {/* Borrower OAuth Callbacks */}
          <Route path="/apply/oauth/:provider/callback" element={<LazyPage><BorrowerOAuthCallback /></LazyPage>} />
          <Route path="/apply/verify" element={<LazyPage><BorrowerOAuthCallback /></LazyPage>} />

          {/* Borrower Application (public - token-based access) */}
          <Route path="/apply/:token" element={<LazyPage><BorrowerApplication /></LazyPage>} />

          {/* Co-borrower Application (public - token-based access) */}
          <Route path="/coborrower/:token" element={<LazyPage><CoborrowerApplication /></LazyPage>} />

          {/* Legacy Borrower Portal - moved to /borrower-portal to avoid conflict with PURL /portal/:slug route */}
          <Route path="/borrower-portal/:token" element={<LazyPage><BorrowerPortal /></LazyPage>} />
          <Route path="/borrower-portal" element={<LazyPage><BorrowerPortal /></LazyPage>} />

          {/* Active Loan Portal - Real-time borrower dashboard with WebSocket updates */}
          <Route path="/portal/loan/:loanId" element={<LazyPage><ActiveLoanPortalComplete /></LazyPage>} />
          <Route path="/portal/active/:token" element={<LazyPage><ActiveLoanPortalComplete /></LazyPage>} />

          {/* Perennia Client Portal Ultimate - Production-ready lifecycle portal */}
          <Route path="/portal/ultimate/:loanId" element={<LazyPage><PerenniaClientPortalUltimate /></LazyPage>} />
          <Route path="/portal/ultimate/token/:token" element={<LazyPage><PerenniaClientPortalUltimate /></LazyPage>} />

          {/* Total Cost Analysis - Mortgage Coach style comparison tool */}
          <Route path="/portal/tca/:loanId" element={<LazyPage><TotalCostAnalysis /></LazyPage>} />
          <Route path="/analysis/:token" element={<LazyPage><TotalCostAnalysis /></LazyPage>} />

          {/* Partner Portal - Realtor/Partner view with magic link access */}
          <Route path="/partner/:token" element={<LazyPage><PartnerPortalView /></LazyPage>} />

          {/* OAuth Callback (public) */}
          <Route path="/oauth/callback" element={<LazyPage><OAuthCallback /></LazyPage>} />

          {/* Onboarding redirect to wizard */}
          <Route
            path="/onboarding"
            element={
              <PrivateRoute>
                <Navigate to="/onboarding/welcome" replace />
              </PrivateRoute>
            }
          />

          {/* New Onboarding Wizard with steps */}
          <Route
            path="/onboarding/:step"
            element={
              <PrivateRoute>
                <LazyPage>
                  <OnboardingWizard />
                </LazyPage>
              </PrivateRoute>
            }
          />

          {/* AI Landing Page - standalone interface */}
          <Route
            path="/ai"
            element={
              <PrivateRoute>
                <LazyPage><AILandingPage /></LazyPage>
              </PrivateRoute>
            }
          />

          {/* Workflow Dashboard */}
          <Route
            path="/workflow"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><WorkflowDashboard /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />

          {/* Workflow Stage Management */}
          <Route
            path="/workflow/:stage"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><WorkflowStagePage /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />

          {/* Workflow Status Detail (drill-down from dashboard) */}
          <Route
            path="/workflow/status/:statusId"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><WorkflowStatusDetail /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />

          {/* Market Dashboard */}
          <Route
            path="/market"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><MarketDashboard /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />

          {/* Morning Check-in */}
          <Route
            path="/checkin"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><MorningCheckin /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />

          {/* Partner ROI Dashboard */}
          <Route
            path="/partner-roi"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><PartnerROIDashboard /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />

          {/* Application Analytics Dashboard */}
          <Route
            path="/analytics/applications"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><ApplicationAnalytics /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />

          {/* Profitability Intelligence Dashboard */}
          <Route
            path="/profitability"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><ProfitabilityDashboard /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />

          {/* Scenario Modeling */}
          <Route
            path="/profitability/scenarios"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><ScenarioModeling /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />

          {/* SLA Tracking Dashboard */}
          <Route
            path="/sla-tracking"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><SLASettings /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />

          {/* Protected routes */}
          <Route
            path="/dashboard"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''} ${taskSidebarOpen ? 'with-task-sidebar' : ''}`}>
                    <LazyPage><Dashboard /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/command-center"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''} ${taskSidebarOpen ? 'with-task-sidebar' : ''}`}>
                    <LazyPage><CommandCenter /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/dashboard/efficiency"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><PipelineEfficiency /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/efficiency"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><PipelineEfficiency /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/efficiency/stage/:stageSlug"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><StageEmployees /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/efficiency/stage/:stageSlug/employee/:employeeId"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><EmployeeLoans /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/efficiency/team/:roleSlug"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><TeamRoleEmployees /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/efficiency/team/:roleSlug/employee/:employeeId"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><EmployeeLoans /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/efficiency/bottleneck/:bottleneckId"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><BottleneckLoans /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/leads"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><Leads /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/leads/:id"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><LeadDetail /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/loans"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><Loans /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/loans/:id"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><LoanDetail /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/portfolio"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><Portfolio /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/portfolio/detail"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><PortfolioDetail /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/portfolio/year-over-year"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><YearOverYear /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/portfolio/:id"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><MumClientDetail /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/tasks"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><Tasks /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/calendar"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><Calendar /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/scorecard"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><Scorecard /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/assistant"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><Assistant /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/ai-receptionist-dashboard"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><AIReceptionistDashboard /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/voice-os-dashboard"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><VoiceOSDashboard /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/agents"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><AgentDashboard /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/agent/:agentId/settings"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><AgentGovernanceSettings /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/settings/smart-scheduler"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><SmartSchedulerSettings /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/settings/email-integration"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><EmailIntegrationSettings /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/settings/user-profile"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><UserProfileSettings /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/settings/document-upload"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><DocumentUploadSettings /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/settings/lead-capture"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><LeadCaptureSettings /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/settings/client-portal"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><ClientPortalSettings /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/settings/communication"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><CommunicationPreferences /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/settings/integrations"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><IntegrationSettings /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/settings/api-keys"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><APIKeysSettings /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/settings/company-branding"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><CompanyBrandingSettings /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/agent/:id"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><AgentProfile /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/agent-gym"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><AgentGym /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          {/* PURL Client Portal Routes */}
          <Route
            path="/client-portals"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><PURLDashboard /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          {/* Public PURL Portal - Smart Container Routes to Lead/Active/MUM stages */}
          <Route
            path="/portal/:slug"
            element={
              <LazyPage><PortalContainer /></LazyPage>
            }
          />
          <Route
            path="/portal/:slug/apply"
            element={
              <LazyPage><PURLApplication /></LazyPage>
            }
          />
          <Route
            path="/client/:type/:id"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><ClientProfile /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/referral-partners"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><ReferralPartners /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/referral-partners/:id"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><ReferralPartnerDetail /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/partner-portal/:id"
            element={
              <PrivateRoute>
                <LazyPage><PartnerDashboardPortal /></LazyPage>
              </PrivateRoute>
            }
          />
          <Route
            path="/partner-portal/:partnerId/client/:clientId"
            element={
              <PrivateRoute>
                <LazyPage><PartnerClientDetail /></LazyPage>
              </PrivateRoute>
            }
          />
          <Route
            path="/ai-underwriter"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><AIUnderwriter /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/goal-tracker"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><GoalTracker /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/coach"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><Coach /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/reconciliation"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><ReconciliationCenter /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/merge"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><MergeCenter /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/communication-intelligence"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><CommunicationIntelligence /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/email-intelligence"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><CommunicationIntelligence /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/ai-outreach"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><AIOutreach /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/conversation-intelligence"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><ConversationIntelligence /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/smart-docs"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><SmartDocs /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/smart-docs/dashboard"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><SmartDocsDashboard /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/smart-docs/client/:loanId"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><SmartDocsClientDetail /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/ai-blog"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><AIDailyBlog /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/conversation-intelligence/recording/:id"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><ConversationIntelligenceRecordingDetail /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/settings"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><Settings /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/microsite/wizard"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><MicrositeWizard /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/microsite/editor"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><MicrositeEditor /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/team-members"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><TeamMembers /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/team-members/:id"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><TeamMemberProfile /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/my-profile"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><MyProfile /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/my-permissions"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><MyPermissions /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/compliance"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><ComplianceDashboard /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/admin/settings"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><AdminSettings /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/admin/domains"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><AdminCustomDomains /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/admin/employee-onboarding"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><EmployeeOnboardingAdmin /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/admin/documents"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><AdminDocumentReviewQueue /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/knowledge-base"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><KnowledgeBase /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/dialer"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><PowerDialer /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/data-upload"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><DataUpload /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/compare-estimates"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><EstimateComparison /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/verizon-test"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><VerizonTest /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/team/:userId"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><UserProfile /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/users"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><Users /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/users/create"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><UserCreationWizard /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/users/bulk-upload"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><UserBulkUpload /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/users/:id"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><UserProfile /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/process-templates"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><ProcessTemplates /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/dashboard/loan-officer"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><LODashboard /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/dashboard/realtor"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><RealtorDashboard /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/admin"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    onToggleTaskSidebar={toggleTaskSidebar}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskSidebarOpen={taskSidebarOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <LazyPage><AdminPanel /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
        </Routes>
        {/* Global AI Assistant */}
        <AIAssistant isOpen={assistantOpen} onClose={() => setAssistantOpen(false)} />
        {/* Unified Task Sidebar */}
        <UnifiedTaskSidebar
          isOpen={taskSidebarOpen}
          onClose={() => setTaskSidebarOpen(false)}
          onTaskCountChange={handleUnifiedTaskCountChange}
        />
        {/* Global Search - floating, triggered by Cmd+K */}
        <GlobalSearch />
        </div>
            </EmailDropZone>
      </Router>
        </PermissionProvider>
      </ImpersonationProvider>
    </ErrorBoundary>
  );
}

export default App;
