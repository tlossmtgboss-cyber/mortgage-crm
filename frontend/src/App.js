import { useState, useEffect, lazy, Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { isAuthenticated } from './utils/auth';
import { ImpersonationProvider } from './contexts/ImpersonationContext';
import { PermissionProvider } from './contexts/PermissionContext';
import Navigation from './components/Navigation';
import AIAssistant from './components/AIAssistant';
import SmartAIChat from './components/SmartAIChat';
import CoachCorner from './components/CoachCorner';
import OnboardingPrompt from './components/OnboardingPrompt';
import ImpersonationBanner from './components/ImpersonationBanner';
import ErrorBoundary from './components/ErrorBoundary';
import './App.css';

// Landing/Auth pages (keep these as regular imports for faster initial load)
import LandingPage from './pages/LandingPage';
import Registration from './pages/Registration';
import EmailVerificationSent from './pages/EmailVerificationSent';
import Login from './pages/Login';
import Onboarding from './pages/Onboarding';

// Lazy load all other pages for instant navigation
const Dashboard = lazy(() => import('./pages/Dashboard'));
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
const DataUpload = lazy(() => import('./pages/DataUpload'));
const Users = lazy(() => import('./pages/Users'));
const UserProfile = lazy(() => import('./pages/UserProfile'));
const ProcessTemplates = lazy(() => import('./pages/ProcessTemplates'));
const BuyerIntake = lazy(() => import('./pages/BuyerIntake'));
const VerizonTest = lazy(() => import('./pages/VerizonTest'));
const PipelineEfficiency = lazy(() => import('./pages/PipelineEfficiency'));
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
const EmployeeOnboardingAdmin = lazy(() => import('./pages/EmployeeOnboardingAdmin'));
const AcceptInvite = lazy(() => import('./pages/AcceptInvite'));
const MortgagePlannerQuestionnaire = lazy(() => import('./pages/MortgagePlannerQuestionnaire'));

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
  ? 'https://mortgage-crm-production-7a9a.up.railway.app'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

function PrivateRoute({ children }) {
  return isAuthenticated() ? children : <Navigate to="/login" />;
}

// Wrapper to handle lazy-loaded pages with suspense
function LazyPage({ children }) {
  return (
    <Suspense fallback={<PageLoader />}>
      {children}
    </Suspense>
  );
}

// Wrapper to hide SmartAIChat on AI landing page (fixes gray overlay)
function ConditionalSmartAIChat() {
  const location = useLocation();
  // Hide on /ai route since it has its own chat interface
  if (location.pathname === '/ai') {
    return null;
  }
  return <SmartAIChat />;
}

function App() {
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [coachOpen, setCoachOpen] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [checkingOnboarding, setCheckingOnboarding] = useState(true);

  // Task counts for navigation badges (MUM = Client for Life Engine tasks)
  const [taskCounts, setTaskCounts] = useState({
    leads: 0,
    loans: 0,
    portfolio: 3,  // MUM tasks
    tasks: 0,
    urgentTasks: 0,
    partners: 0
  });

  const toggleAssistant = () => {
    setAssistantOpen(!assistantOpen);
  };

  const toggleCoach = () => {
    setCoachOpen(!coachOpen);
  };

  // Removed dismiss handler - onboarding is now mandatory until completion

  useEffect(() => {
    const checkOnboardingStatus = async () => {
      // OPTIMIZED: Don't block rendering - check localStorage first
      setCheckingOnboarding(false);

      if (!isAuthenticated()) return;

      // Check localStorage immediately (non-blocking)
      try {
        const userStr = localStorage.getItem('user');
        if (userStr) {
          const user = JSON.parse(userStr);
          if (user.onboarding_completed === undefined || user.onboarding_completed === false) {
            setShowOnboarding(true);
          }
        }
      } catch (parseError) {
        console.warn('Error parsing user data:', parseError);
      }

      // Then verify with API in background (non-blocking for UI)
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/users/me`, {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`
          }
        });

        if (response.ok) {
          const userData = await response.json();
          // Update state if different from localStorage
          if (!userData.onboarding_completed) {
            setShowOnboarding(true);
          } else {
            setShowOnboarding(false);
          }
        }
      } catch (error) {
        console.error('Error checking onboarding status:', error);
        // Already checked localStorage, so we're okay
      }
    };

    checkOnboardingStatus();
  }, []);

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
            <ImpersonationBanner />
            <div className="app">
        <Routes>
          {/* Public routes */}
          <Route path="/" element={<LandingPage />} />
          <Route path="/apply" element={<BuyerIntake />} />
          <Route path="/mortgage-planner" element={<LazyPage><MortgagePlannerQuestionnaire /></LazyPage>} />
          <Route path="/register" element={<Registration />} />
          <Route path="/verify-email-sent" element={<EmailVerificationSent />} />
          <Route path="/login" element={<Login />} />

          {/* Employee Invite Accept (public) */}
          <Route path="/invite/accept/:token" element={<LazyPage><AcceptInvite /></LazyPage>} />
          <Route path="/accept-invite" element={<LazyPage><AcceptInvite /></LazyPage>} />

          {/* Onboarding Page (old) */}
          <Route
            path="/onboarding"
            element={
              <PrivateRoute>
                <Onboarding />
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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

          {/* Market Dashboard */}
          <Route
            path="/market"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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

          {/* Profitability Intelligence Dashboard */}
          <Route
            path="/profitability"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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

          {/* Protected routes */}
          <Route
            path="/dashboard"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                    taskCounts={taskCounts}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    {/* Show onboarding prompt for users who haven't completed it - persistent until completion */}
                    {showOnboarding && !checkingOnboarding && (
                      <OnboardingPrompt />
                    )}
                    <LazyPage><Dashboard /></LazyPage>
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
            path="/leads"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
            path="/client/:type/:id"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
            path="/ai-underwriter"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <MergeCenter />
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
            path="/team-members"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <TeamMembers />
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <TeamMemberProfile />
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
            path="/admin/employee-onboarding"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
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
            path="/data-upload"
            element={
              <PrivateRoute>
                <div className="app-layout">
                  <Navigation
                    onToggleAssistant={toggleAssistant}
                    onToggleCoach={toggleCoach}
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <DataUpload />
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <VerizonTest />
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <UserProfile />
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <Users />
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <UserProfile />
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
                    assistantOpen={assistantOpen}
                    coachOpen={coachOpen}
                  />
                  <main className={`app-main ${assistantOpen ? 'with-assistant' : ''}`}>
                    <ProcessTemplates />
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
        </Routes>
        {/* Global AI Assistant */}
        <AIAssistant isOpen={assistantOpen} onClose={() => setAssistantOpen(false)} />
        <ConditionalSmartAIChat />
        </div>
      </Router>
        </PermissionProvider>
      </ImpersonationProvider>
    </ErrorBoundary>
  );
}

export default App;
