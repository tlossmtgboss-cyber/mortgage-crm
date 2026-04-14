import { useState, useEffect, lazy, Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Capacitor } from '@capacitor/core';
import { App as CapApp } from '@capacitor/app';
import { SplashScreen } from '@capacitor/splash-screen';
import { isAuthenticatedSync as isAuthenticated, migrateAuthTokens } from './utils/auth';
import { ImpersonationProvider } from './contexts/ImpersonationContext';
import { PermissionProvider, usePermissions } from './contexts/PermissionContext';
import { ModuleProvider, useModules } from './contexts/ModuleContext';
import { BrandingProvider } from './contexts/BrandingContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { getUserEffectiveRole, getDefaultRouteForRole } from './config/roleConfig';
import Navigation from './components/Navigation';
import AIAssistant from './components/AIAssistant';
import CoachCorner from './components/CoachCorner';
import ImpersonationBanner from './components/ImpersonationBanner';
import ErrorBoundary from './components/ErrorBoundary';
import UnifiedTaskSidebar from './components/UnifiedTaskSidebar';
import GlobalLayoutFix from './components/GlobalLayoutFix';
import GlobalSearch from './components/GlobalSearch';
import { OfflineIndicator } from './components/OfflineIndicator';
import UpdateRequiredModal from './components/mobile/UpdateRequiredModal';
import SessionTimeoutModal from './components/mobile/SessionTimeoutModal';
import { checkForUpdate, clearVersionCache } from './services/appVersionCheck';
import { initializePushNotifications, teardownPushNotifications } from './services/pushNotificationService';
import { initNotificationActions } from './services/notificationActions';
import { initDeepLinkRouter, consumePendingDeepLink } from './services/deepLinkRouter';
import { API_BASE_URL } from './services/api';
import './App.css';

// Landing/Auth pages (keep these as regular imports for faster initial load)
import LandingPage from './pages/LandingPage';
import Registration from './pages/Registration';
import AccountVerification from './pages/AccountVerification';
import EmailVerificationSent from './pages/EmailVerificationSent';
import Login from './pages/Login';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import AdminOnboarding from './pages/AdminOnboarding';
import ApplicationSubmitted from './pages/ApplicationSubmitted';

// Redirect to an external URL (outside React Router)
function ExternalRedirect({ to }) {
  useEffect(() => { window.location.href = to; }, [to]);
  return null;
}

/**
 * Invisible component that initializes push notifications and notification
 * action routing inside the Router context (so useNavigate is available).
 * Renders nothing.
 */
function PushNotificationInitializer() {
  const navigate = useNavigate();

  useEffect(() => {
    // Wire up notification action routing with the router's navigate function
    initNotificationActions(navigate);

    // Initialize deep link router (listens for appUrlOpen, custom scheme, cold launch)
    const cleanupDeepLinks = initDeepLinkRouter(navigate);

    // Auto-initialize push if user is already authenticated
    if (isAuthenticated()) {
      // Consume any pending deep link that was queued before login
      const pendingRoute = consumePendingDeepLink();
      if (pendingRoute) {
        navigate(pendingRoute);
      }

      // Delay to avoid blocking initial render
      const timer = setTimeout(() => {
        initializePushNotifications().catch((err) =>
          console.warn('Push notification auto-init failed:', err)
        );
      }, 3000);
      return () => {
        clearTimeout(timer);
        if (cleanupDeepLinks) cleanupDeepLinks();
      };
    }

    return () => {
      if (cleanupDeepLinks) cleanupDeepLinks();
    };
  }, [navigate]);

  return null;
}

// Retry dynamic imports on failure (handles stale chunks after deploys)
function lazyRetry(importFn) {
  return lazy(() =>
    importFn().catch(() => {
      const hasReloaded = sessionStorage.getItem('chunk_reload');
      if (!hasReloaded) {
        sessionStorage.setItem('chunk_reload', '1');
        window.location.reload();
        return new Promise(() => {});
      }
      sessionStorage.removeItem('chunk_reload');
      return { default: () => (
        <div style={{ textAlign: 'center', padding: '2rem' }}>
          <p>Failed to load page. Please try refreshing.</p>
          <button onClick={() => { sessionStorage.removeItem('chunk_reload'); window.location.reload(); }}>
            Reload
          </button>
        </div>
      )};
    })
  );
}

// Clear chunk reload flag on successful load
sessionStorage.removeItem('chunk_reload');

// Lazy load all other pages for instant navigation
const Dashboard = lazyRetry(() => import('./pages/Dashboard'));
const CommandCenter = lazyRetry(() => import('./pages/CommandCenter'));
const OnboardingWizard = lazyRetry(() => import('./components/onboarding/OnboardingWizard'));
const Leads = lazyRetry(() => import('./pages/Leads'));
const LeadDetail = lazyRetry(() => import('./pages/LeadDetail'));
const Loans = lazyRetry(() => import('./pages/Loans'));
const LoanDetail = lazyRetry(() => import('./pages/LoanDetail'));
const Portfolio = lazyRetry(() => import('./pages/Portfolio'));
const ClosedLoans = lazyRetry(() => import('./pages/ClosedLoans'));
const PortfolioDetail = lazyRetry(() => import('./pages/PortfolioDetail'));
const MumClientDetail = lazyRetry(() => import('./pages/MumClientDetail'));
const YearOverYear = lazyRetry(() => import('./pages/YearOverYear'));
const RateMonitor = lazyRetry(() => import('./pages/RateMonitor'));
const Tasks = lazyRetry(() => import('./pages/Tasks'));
const Calendar = lazyRetry(() => import('./pages/Calendar'));
const CalendarSettings = lazyRetry(() => import('./pages/CalendarSettings'));
const CalendarSetupWizard = lazyRetry(() => import('./components/calendar/setup/CalendarSetupWizard'));
const TeamCalendar = lazyRetry(() => import('./pages/TeamCalendar'));
const Scorecard = lazyRetry(() => import('./pages/Scorecard'));
const Assistant = lazyRetry(() => import('./pages/Assistant'));
const ClientProfile = lazyRetry(() => import('./pages/ClientProfile'));
const ReferralPartners = lazyRetry(() => import('./pages/ReferralPartners'));
const ReferralPartnerDetail = lazyRetry(() => import('./pages/ReferralPartnerDetail'));
const PartnerDashboardPortal = lazyRetry(() => import('./pages/PartnerDashboardPortal'));
const PartnerClientDetail = lazyRetry(() => import('./pages/PartnerClientDetail'));
const AIUnderwriter = lazyRetry(() => import('./pages/AIUnderwriter'));
const GoalTracker = lazyRetry(() => import('./pages/GoalTracker'));
const Coach = lazyRetry(() => import('./pages/Coach'));
const ReconciliationCenter = lazyRetry(() => import('./pages/ReconciliationCenter'));
const MergeCenter = lazyRetry(() => import('./pages/MergeCenter'));
const Settings = lazyRetry(() => import('./pages/Settings'));
const TeamMembers = lazyRetry(() => import('./pages/TeamMembers'));
const TeamMemberProfile = lazyRetry(() => import('./pages/TeamMemberProfile'));
const MyProfile = lazyRetry(() => import('./pages/MyProfile'));
const MyPermissions = lazyRetry(() => import('./pages/MyPermissions'));
const ComplianceDashboard = lazyRetry(() => import('./pages/ComplianceDashboard'));
const OpsManagerDashboard = lazyRetry(() => import('./pages/OpsManagerDashboard'));
const AdminSettings = lazyRetry(() => import('./pages/AdminSettings'));
const PermissionsPage = lazyRetry(() => import('./pages/PermissionsPage'));
const AdminCustomDomains = lazyRetry(() => import('./pages/AdminCustomDomains'));
const DataUpload = lazyRetry(() => import('./pages/DataUpload'));
const EstimateComparison = lazyRetry(() => import('./pages/EstimateComparison'));
const Users = lazyRetry(() => import('./pages/Users'));
const UserProfile = lazyRetry(() => import('./pages/UserProfile'));
const ProcessTemplates = lazyRetry(() => import('./pages/ProcessTemplates'));
const BuyerIntake = lazyRetry(() => import('./pages/BuyerIntake'));
const ApplicationPreview = lazyRetry(() => import('./pages/ApplicationPreview'));
const VerizonTest = lazyRetry(() => import('./pages/VerizonTest'));
const PipelineEfficiency = lazyRetry(() => import('./pages/PipelineEfficiency'));
const StageEmployees = lazyRetry(() => import('./pages/StageEmployees'));
const EmployeeLoans = lazyRetry(() => import('./pages/EmployeeLoans'));
const TeamRoleEmployees = lazyRetry(() => import('./pages/TeamRoleEmployees'));
const BottleneckLoans = lazyRetry(() => import('./pages/BottleneckLoans'));
const AIReceptionistDashboard = lazyRetry(() => import('./pages/AIReceptionistDashboard'));
const CallRoutingConfig = lazyRetry(() => import('./pages/CallRoutingConfig'));
const VoiceOSDashboard = lazyRetry(() => import('./pages/VoiceOSDashboard'));
const VideoOS = lazyRetry(() => import('./pages/VideoOS'));
const VoiceAgentStudio = lazyRetry(() => import('./components/voice/AgentStudio'));
const VoiceLiveCallsMonitor = lazyRetry(() => import('./components/voice/LiveCallsMonitor'));
const VoiceAgentBuilder = lazyRetry(() => import('./components/voice/AgentBuilder'));
const VoiceCallQueueDashboard = lazyRetry(() => import('./components/voice/CallQueueDashboard'));
const VoiceConferenceRoomDashboard = lazyRetry(() => import('./components/voice/ConferenceRoomDashboard'));
const VoiceIVRMenuDashboard = lazyRetry(() => import('./components/voice/IVRMenuDashboard'));
const VoiceHoldMusicDashboard = lazyRetry(() => import('./components/voice/HoldMusicDashboard'));
const VoiceTalkToAgentPage = lazyRetry(() => import('./components/voice/TalkToAgentPage'));
const VoiceCallAnalyticsDashboard = lazyRetry(() => import('./components/voice/CallAnalyticsDashboard'));
const CallIntelligencePage = lazyRetry(() => import('./pages/CallIntelligencePage'));
const MobileCallIntelligencePage = lazyRetry(() => import('./pages/MobileCallIntelligencePage'));
const AILandingPage = lazyRetry(() => import('./pages/AILandingPage'));
const WorkflowDashboard = lazyRetry(() => import('./pages/WorkflowDashboard'));
const WorkflowStagePage = lazyRetry(() => import('./pages/WorkflowStagePage'));
const MarketDashboard = lazyRetry(() => import('./pages/MarketDashboard'));
const MorningCheckin = lazyRetry(() => import('./pages/MorningCheckin'));
const PartnerROIDashboard = lazyRetry(() => import('./pages/PartnerROIDashboard'));
const ProfitabilityDashboard = lazyRetry(() => import('./pages/ProfitabilityDashboard'));
const UsageIntelligenceDashboard = lazyRetry(() => import('./pages/UsageIntelligenceDashboard'));
const ScenarioModeling = lazyRetry(() => import('./pages/ScenarioModeling'));
// const DecisionLab = lazyRetry(() => import('./pages/DecisionLab')); // DEPRECATED: Experimental feature deregistered
const MortgageCalculator = lazyRetry(() => import('./pages/MortgageCalculator'));
const AllInOneLoan = lazyRetry(() => import('./pages/AllInOneLoan'));
const PipelineProbability = lazyRetry(() => import('./pages/PipelineProbability'));
const SLASettings = lazyRetry(() => import('./pages/SLASettings'));
const EmployeeOnboardingAdmin = lazyRetry(() => import('./pages/EmployeeOnboardingAdmin'));
const AcceptInvite = lazyRetry(() => import('./pages/AcceptInvite'));
const MortgagePlannerQuestionnaire = lazyRetry(() => import('./pages/MortgagePlannerQuestionnaire'));
const KnowledgeBase = lazyRetry(() => import('./pages/KnowledgeBase'));
const Support = lazyRetry(() => import('./pages/Support'));
const AriaVoiceApp = lazyRetry(() => import('./pages/AriaVoiceApp'));
const AriaCalendarPage = lazyRetry(() => import('./pages/aria/AriaCalendarPage'));
const AriaMortgageCalculator = lazyRetry(() => import('./pages/aria/AriaMortgageCalculator'));
const MobileAriaChat = lazyRetry(() => import('./pages/MobileAriaChat'));
const MobileHomeDashboard = lazyRetry(() => import('./pages/MobileHomeDashboard'));
const MobileLeadsList = lazyRetry(() => import('./pages/MobileLeadsList'));
const MobilePipelineView = lazyRetry(() => import('./pages/MobilePipelineView'));
const MobileNotificationCenter = lazyRetry(() => import('./pages/MobileNotificationCenter'));
import MobileErrorBoundary from './components/mobile/MobileErrorBoundary';
const AriaVoiceHome = lazyRetry(() => import('./pages/aria-mobile/AriaVoiceHome'));
const MobileCalendar = lazyRetry(() => import('./pages/aria-mobile/MobileCalendar'));
const MobileTasks = lazyRetry(() => import('./pages/aria-mobile/MobileTasks'));
const MobileAppointmentDetail = lazyRetry(() => import('./pages/aria-mobile/MobileAppointmentDetail'));
const MobileCallIntel = lazyRetry(() => import('./pages/aria-mobile/MobileCallIntel'));
const AriaVoiceOnboarding = lazyRetry(() => import('./pages/aria-mobile/AriaVoiceOnboarding'));
const AriaChatScreen = lazyRetry(() => import('./pages/aria-mobile/AriaChatScreen'));
const AriaTestPage = lazyRetry(() => import('./pages/AriaTestPage'));
const BriefingPage = lazyRetry(() => import('./pages/BriefingPage'));
const PowerDialer = lazyRetry(() => import('./pages/PowerDialer'));
const UserCreationWizard = lazyRetry(() => import('./pages/UserCreationWizard'));
const UserBulkUpload = lazyRetry(() => import('./pages/UserBulkUpload'));
const ActivateAccount = lazyRetry(() => import('./pages/ActivateAccount'));
const MeetingRoom = lazyRetry(() => import('./pages/MeetingRoom'));
const OAuthCallback = lazyRetry(() => import('./pages/OAuthCallback'));
const WorkflowStatusDetail = lazyRetry(() => import('./pages/WorkflowStatusDetail'));
const CommunicationIntelligence = lazyRetry(() => import('./pages/CommunicationIntelligence'));
const AIOutreach = lazyRetry(() => import('./pages/AIOutreach'));
const ConversationIntelligence = lazyRetry(() => import('./pages/ConversationIntelligence'));
const ConversationIntelligenceRecordingDetail = lazyRetry(() => import('./pages/ConversationIntelligenceRecordingDetail'));
const SmartDocs = lazyRetry(() => import('./pages/SmartDocs'));
const SmartDocsClientDetail = lazyRetry(() => import('./pages/SmartDocsClientDetail'));
const SmartDocsDashboard = lazyRetry(() => import('./pages/SmartDocsDashboard'));
const SmartDocsAnalytics = lazyRetry(() => import('./pages/SmartDocsAnalytics'));
const SmartDocsReviewQueue = lazyRetry(() => import('./pages/SmartDocsReviewQueue'));
const SmartDocsSecurity = lazyRetry(() => import('./pages/SmartDocsSecurity'));
const SmartDocsBankAnalysis = lazyRetry(() => import('./pages/SmartDocsBankAnalysis'));
const SmartDocsIncome = lazyRetry(() => import('./pages/SmartDocsIncome'));
const SmartDocsAdmin = lazyRetry(() => import('./pages/SmartDocsAdmin'));
const AIDailyBlog = lazyRetry(() => import('./pages/AIDailyBlog'));
// DEPRECATED: Experimental feature deregistered
// const AvatarStudio = lazyRetry(() => import('./pages/AvatarStudio'));
const PublicBooking = lazyRetry(() => import('./pages/PublicBooking'));
const BookingConfirmationPage = lazyRetry(() => import('./pages/BookingConfirmationPage'));
const EmbedBooking = lazyRetry(() => import('./pages/EmbedBooking'));
const BorrowerApplication = lazyRetry(() => import('./pages/BorrowerApplication'));
const AdaptiveURLA = lazyRetry(() => import('./pages/AdaptiveURLA'));
const PurchaseApplication = lazyRetry(() => import('./pages/PurchaseApplication'));
const RefinanceApplication = lazyRetry(() => import('./pages/RefinanceApplication'));
const PurchasePreQualForm = lazyRetry(() => import('./pages/PurchasePreQualForm'));

// New enhanced applications (v2)
const NewPurchaseApplication = lazyRetry(() => import('./pages/applications/NewPurchaseApplication'));
const NewRefinanceApplication = lazyRetry(() => import('./pages/applications/NewRefinanceApplication'));
const ApplicationDemo = lazyRetry(() => import('./pages/applications/ApplicationDemo'));
const CoborrowerApplication = lazyRetry(() => import('./pages/CoborrowerApplication'));
const BorrowerLogin = lazyRetry(() => import('./pages/BorrowerLogin'));
const ApplyVerify = lazyRetry(() => import('./pages/ApplyVerify'));
const BorrowerOAuthCallback = lazyRetry(() => import('./pages/BorrowerOAuthCallback'));
const ApplicationAnalytics = lazyRetry(() => import('./pages/ApplicationAnalytics'));
const BorrowerPortal = lazyRetry(() => import('./pages/BorrowerPortal'));
const SharedCalculator = lazyRetry(() => import('./pages/SharedCalculator'));
const CalculatorDashboard = lazyRetry(() => import('./pages/CalculatorDashboard'));
const PortalTest = lazyRetry(() => import('./pages/PortalTest'));
const ThemeRenderer = lazyRetry(() => import('./pages/microsites/ThemeRenderer'));
const ThemePreview = lazyRetry(() => import('./pages/microsites/ThemePreview'));
const MicrositePreview = lazyRetry(() => import('./pages/microsites/MicrositePreview'));
const MicrositeWizard = lazyRetry(() => import('./components/microsites/MicrositeWizard'));
const MicrositeEditor = lazyRetry(() => import('./pages/MicrositeEditor'));
const LODashboard = lazyRetry(() => import('./pages/LODashboard'));
const RealtorDashboard = lazyRetry(() => import('./pages/RealtorDashboard'));
const RealtorPortal = lazyRetry(() => import('./pages/RealtorPortal'));
const AdminPanel = lazyRetry(() => import('./pages/AdminPanel'));
const AgentDashboard = lazyRetry(() => import('./pages/AgentDashboard'));
const AgentProfile = lazyRetry(() => import('./pages/AgentProfile'));
const AcquisitionDashboard = lazyRetry(() => import('./pages/AcquisitionDashboard'));
const EngagementDashboard = lazyRetry(() => import('./pages/EngagementDashboard'));
const Marketing = lazyRetry(() => import('./pages/Marketing'));
const CarouselBuilder = lazyRetry(() => import('./pages/CarouselBuilder/CarouselBuilderPage'));
const MasterManagerCapacity = lazyRetry(() => import('./pages/MasterManager/CapacityCommandCenter'));
// DEPRECATED: Premium feature deregistered — not yet launched
// const MasterManagerRecruiting = lazyRetry(() => import('./pages/MasterManager/RecruitingDashboard'));
// const RecruitDetail = lazyRetry(() => import('./pages/MasterManager/RecruitDetail'));
// const PartnerRecruitingDashboard = lazyRetry(() => import('./pages/PartnerRecruiting/PartnerRecruitingDashboard'));
// const PartnerRecruitDetail = lazyRetry(() => import('./pages/PartnerRecruiting/PartnerRecruitDetail'));
const AgentGym = lazyRetry(() => import('./pages/AgentGym'));
const AgentGovernanceSettings = lazyRetry(() => import('./pages/AgentGovernanceSettings'));
const EmailIntegrationSettings = lazyRetry(() => import('./pages/EmailIntegrationSettings'));
const UserProfileSettings = lazyRetry(() => import('./pages/UserProfileSettings'));
const DocumentUploadSettings = lazyRetry(() => import('./pages/DocumentUploadSettings'));
const LeadCaptureSettings = lazyRetry(() => import('./pages/LeadCaptureSettings'));
const ClientPortalSettings = lazyRetry(() => import('./pages/ClientPortalSettings'));
const CommunicationPreferences = lazyRetry(() => import('./pages/CommunicationPreferences'));
const IntegrationSettings = lazyRetry(() => import('./pages/IntegrationSettings'));
const SalesforceIntegrationPage = lazyRetry(() => import('./pages/SalesforceIntegrationPage'));
const FollowUpBossIntegrationPage = lazyRetry(() => import('./pages/FollowUpBossIntegrationPage'));
const StateRecordingRules = lazyRetry(() => import('./pages/settings/StateRecordingRules'));
const QuoteLanguagePresets = lazyRetry(() => import('./pages/settings/QuoteLanguagePresets'));
const CalculatorSettings = lazyRetry(() => import('./pages/settings/CalculatorSettings'));
const BillingSettings = lazyRetry(() => import('./pages/settings/BillingSettings'));
const APIKeysSettings = lazyRetry(() => import('./pages/APIKeysSettings'));
const CompanyBrandingSettings = lazyRetry(() => import('./pages/CompanyBrandingSettings'));
const AccountManagement = lazyRetry(() => import('./pages/AccountManagement'));
const PURLDashboard = lazyRetry(() => import('./pages/PURLDashboard'));
const PURLApplication = lazyRetry(() => import('./pages/PURLApplication'));
const PortalContainer = lazyRetry(() => import('./pages/portal/PortalContainer'));
const LoanPortalRedirect = lazyRetry(() => import('./components/Portal/LoanPortalRedirect'));
const AdminDocumentReviewQueue = lazyRetry(() => import('./pages/AdminDocumentReviewQueue'));
const LeadAssignmentConfig = lazyRetry(() => import('./pages/LeadAssignmentConfig'));
const IncomeCalculatorPopout = lazyRetry(() => import('./pages/IncomeCalculatorPopout'));
const IntakeEngine = lazyRetry(() => import('./components/intake/IntakeEngine'));
const ListingPortalTransactions = lazyRetry(() => import('./pages/ListingPortalTransactions'));
const ListingPortalTransactionDetail = lazyRetry(() => import('./pages/ListingPortalTransactionDetail'));
const ListingAgentPortal = lazyRetry(() => import('./pages/ListingAgentPortal'));
// DEPRECATED: Premium feature deregistered — not yet launched
// const RecruitPortal = lazyRetry(() => import('./pages/RecruitPortal/RecruitPortal'));
// const DISCAssessment = lazyRetry(() => import('./pages/DISCAssessment'));
const PrivacyPolicy = lazyRetry(() => import('./pages/PrivacyPolicy'));
const TermsOfService = lazyRetry(() => import('./pages/TermsOfService'));
const LiveCallWhisper = lazyRetry(() => import('./pages/LiveCallWhisper'));
const ProductionPredictor = lazyRetry(() => import('./pages/ProductionPredictor'));
const ProductionPredictorDetail = lazyRetry(() => import('./pages/ProductionPredictorDetail'));
const DealAlerts = lazyRetry(() => import('./pages/DealAlerts'));

// Accounting System
const AccountingDashboard = lazyRetry(() => import('./pages/accounting/AccountingDashboard'));
const ChartOfAccounts = lazyRetry(() => import('./pages/accounting/ChartOfAccounts'));
const JournalEntries = lazyRetry(() => import('./pages/accounting/JournalEntries'));
// AR (Accounts Receivable)
const ARCustomerList = lazyRetry(() => import('./pages/accounting/ar/CustomerList'));
const ARInvoiceList = lazyRetry(() => import('./pages/accounting/ar/InvoiceList'));
const ARPaymentList = lazyRetry(() => import('./pages/accounting/ar/PaymentList'));
const ARAgingReport = lazyRetry(() => import('./pages/accounting/ar/AgingReport'));
// AP (Accounts Payable)
const APVendorList = lazyRetry(() => import('./pages/accounting/ap/VendorList'));
const APBillList = lazyRetry(() => import('./pages/accounting/ap/BillList'));
const APPayBills = lazyRetry(() => import('./pages/accounting/ap/PayBills'));
const APAgingReport = lazyRetry(() => import('./pages/accounting/ap/AgingReport'));
// Banking
const BankAccounts = lazyRetry(() => import('./pages/accounting/banking/BankAccounts'));
const PlaidConnect = lazyRetry(() => import('./pages/accounting/banking/PlaidConnect'));
const BankTransactions = lazyRetry(() => import('./pages/accounting/banking/BankTransactions'));
const BankReconciliation = lazyRetry(() => import('./pages/accounting/banking/BankReconciliation'));
// Financial Reports
const ProfitLoss = lazyRetry(() => import('./pages/accounting/reports/ProfitLoss'));
const BalanceSheet = lazyRetry(() => import('./pages/accounting/reports/BalanceSheet'));
const CashFlow = lazyRetry(() => import('./pages/accounting/reports/CashFlow'));
const TrialBalance = lazyRetry(() => import('./pages/accounting/reports/TrialBalance'));
// Budgeting
const BudgetList = lazyRetry(() => import('./pages/accounting/budgets/BudgetList'));
const BudgetVariance = lazyRetry(() => import('./pages/accounting/budgets/BudgetVariance'));

// Portal Components - Real-time borrower and partner portals
const ActiveLoanPortalComplete = lazyRetry(() => import('./components/Portal/ActiveLoanPortalComplete'));
const PartnerPortalView = lazyRetry(() => import('./components/Portal/PartnerPortalView'));
const PerenniaClientPortalUltimate = lazyRetry(() => import('./components/Portal/PerenniaClientPortalUltimate'));
const TotalCostAnalysis = lazyRetry(() => import('./components/Portal/TotalCostAnalysis'));

// E-Signature Components - Field placement builder and signing session
const FieldPlacementBuilder = lazyRetry(() => import('./components/esign/FieldPlacementBuilder'));
const SigningSession = lazyRetry(() => import('./pages/esign/SigningSession'));

// Calendar sub-pages & LO Today command center
const CalendarAnalyticsPage = lazyRetry(() => import('./pages/CalendarAnalyticsPage'));
const SurveyResultsPage = lazyRetry(() => import('./pages/SurveyResultsPage'));
const BufferSettingsPage = lazyRetry(() => import('./pages/BufferSettingsPage'));
const WaitlistPage = lazyRetry(() => import('./pages/WaitlistPage'));
const LOTodayView = lazyRetry(() => import('./pages/LOTodayView'));

// Create a client with optimized defaults for instant navigation
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // Data is fresh for 5 minutes
      gcTime: 1000 * 60 * 30, // Cache persists for 30 minutes (formerly cacheTime)
      refetchOnWindowFocus: false, // Don't refetch on tab focus
      refetchOnMount: true, // Refetch stale/failed data on mount (staleTime still prevents unnecessary refetches)
      retry: 1, // Only retry once on failure
    },
  },
});

// Loading fallback component with spinner for Suspense boundaries
function PageLoadingFallback() {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center',
      alignItems: 'center',
      height: '100vh',
      gap: '12px',
    }}>
      <div style={{
        width: '32px',
        height: '32px',
        border: '3px solid #e5e7eb',
        borderTopColor: '#3b82f6',
        borderRadius: '50%',
        animation: 'page-loader-spin 0.7s linear infinite',
      }} />
      <p style={{ fontSize: '14px', color: '#666', margin: 0 }}>Loading...</p>
      <style>{`@keyframes page-loader-spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

// Keep backward-compatible alias
const PageLoader = PageLoadingFallback;

function PrivateRoute({ children }) {
  const { loading: permissionsLoading } = usePermissions();
  const { loading: modulesLoading } = useModules();

  if (!isAuthenticated()) {
    return <Navigate to="/login" />;
  }

  // Block rendering until permissions and modules are loaded to prevent partial-load flicker
  if (permissionsLoading || modulesLoading) {
    return <PageLoader />;
  }

  return children;
}

// Role-based redirect component for authenticated users
function RoleBasedRedirect() {
  // Get user data from localStorage to determine role
  try {
    const userStr = localStorage.getItem('user');
    if (userStr) {
      const user = JSON.parse(userStr);
      const permissionRole = user.permission_role || 'sales';
      const legacyRole = user.role || null;
      const effectiveRole = getUserEffectiveRole(permissionRole, legacyRole);
      const defaultRoute = getDefaultRouteForRole(effectiveRole);
      return <Navigate to={defaultRoute} replace />;
    }
  } catch (error) {
    console.error('Error determining role-based redirect:', error);
  }
  // Default to dashboard if something goes wrong
  return <Navigate to="/dashboard" replace />;
}

// Wrapper to handle lazy-loaded pages with suspense
function LazyPage({ children }) {
  return (
    <Suspense fallback={<PageLoader />}>
      {children}
    </Suspense>
  );
}

// Floating action button for Aria — only on native (iOS) authenticated screens
function AriaFAB() {
  const location = useLocation();
  const navigate = useNavigate();

  if (!Capacitor.isNativePlatform()) return null;
  if (!isAuthenticated()) return null;

  // Hide on public/auth pages and when already on Aria
  const hiddenPaths = ['/login', '/register', '/forgot-password', '/reset-password',
    '/verify-account', '/verify-email-sent', '/aria-voice', '/aria',
    '/mobile-aria', '/apply', '/aria-test'];
  if (hiddenPaths.some(p => location.pathname === p || location.pathname.startsWith(p + '/'))) {
    return null;
  }

  return (
    <button
      onClick={() => navigate('/aria-voice')}
      aria-label="Open Aria voice assistant"
      style={{
        position: 'fixed',
        bottom: 'calc(24px + env(safe-area-inset-bottom, 0px))',
        right: '20px',
        width: '56px',
        height: '56px',
        borderRadius: '50%',
        background: 'linear-gradient(135deg, #1a2744 0%, #2a4a7f 100%)',
        border: 'none',
        boxShadow: '0 4px 12px rgba(26, 39, 68, 0.4)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'pointer',
        zIndex: 9998,
        transition: 'transform 0.2s ease, box-shadow 0.2s ease',
        WebkitTapHighlightColor: 'transparent',
      }}
      onTouchStart={(e) => { e.currentTarget.style.transform = 'scale(0.92)'; }}
      onTouchEnd={(e) => { e.currentTarget.style.transform = 'scale(1)'; }}
    >
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 1C11.2044 1 10.4413 1.31607 9.87868 1.87868C9.31607 2.44129 9 3.20435 9 4V12C9 12.7956 9.31607 13.5587 9.87868 14.1213C10.4413 14.6839 11.2044 15 12 15C12.7956 15 13.5587 14.6839 14.1213 14.1213C14.6839 13.5587 15 12.7956 15 12V4C15 3.20435 14.6839 2.44129 14.1213 1.87868C13.5587 1.31607 12.7956 1 12 1Z" fill="white"/>
        <path d="M19 10V12C19 13.8565 18.2625 15.637 16.9497 16.9497C15.637 18.2625 13.8565 19 12 19C10.1435 19 8.36301 18.2625 7.05025 16.9497C5.7375 15.637 5 13.8565 5 12V10" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        <path d="M12 19V23" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
        <path d="M8 23H16" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    </button>
  );
}

function App() {
  // --- App version check state ---
  const [versionStatus, setVersionStatus] = useState(null);
  const [updateBannerDismissed, setUpdateBannerDismissed] = useState(false);

  // Hide Capacitor splash screen on mount and migrate auth tokens
  useEffect(() => {
    // Migrate any localStorage-only auth tokens to Capacitor Preferences
    // before the app makes its first authenticated API call. No-op on web.
    migrateAuthTokens().catch(() => {});
    SplashScreen.hide().catch(() => {});
  }, []);

  // Check app version on launch (native only)
  useEffect(() => {
    if (!Capacitor.isNativePlatform()) return;

    checkForUpdate().then(setVersionStatus).catch(() => {});

    // Re-check when the app returns to the foreground
    const listener = CapApp.addListener('appStateChange', ({ isActive }) => {
      if (isActive) {
        clearVersionCache();
        checkForUpdate({ force: true }).then(setVersionStatus).catch(() => {});
      }
    });

    return () => { listener.then(l => l.remove()); };
  }, []);

  // Deep link handling is managed by initDeepLinkRouter() in PushNotificationInitializer.
  // It handles appUrlOpen, custom scheme (perenniaai://), and cold launch URLs.

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
    unifiedTasks: 0,  // New unified task count
    reconciliation: 0,  // Pending reconciliation items
    smartDocs: 0  // Documents pending review
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

  // Clear React Query cache on login/logout to prevent stale data
  useEffect(() => {
    const handleAuthChange = (event) => {
      const { type } = event.detail || {};

      // Clear all cached queries on login or logout
      queryClient.clear();

      // Reset task counts on logout
      if (type === 'logout') {
        setTaskCounts({
          leads: 0,
          loans: 0,
          portfolio: 0,
          tasks: 0,
          urgentTasks: 0,
          partners: 0,
          unifiedTasks: 0,
          reconciliation: 0,
          smartDocs: 0
        });
        // Clean up push notification registration on logout
        teardownPushNotifications();
      }

      // Initialize push notifications on login
      if (type === 'login') {
        // Delay slightly so auth token is fully persisted
        setTimeout(() => {
          initializePushNotifications().catch((err) =>
            console.warn('Push notification init failed after login:', err)
          );
        }, 2000);
      }
    };

    window.addEventListener('authChange', handleAuthChange);
    return () => window.removeEventListener('authChange', handleAuthChange);
  }, []);

  // Fetch task counts for navigation badges
  useEffect(() => {
    const fetchTaskCounts = async () => {
      if (!isAuthenticated()) return;

      const headers = {
        'Authorization': `Bearer ${localStorage.getItem('token')}`
      };

      try {
        // Fetch all counts in parallel
        const [tasksResponse, reconciliationResponse, smartDocsResponse] = await Promise.all([
          fetch(`${API_BASE_URL}/api/v1/tasks`, { headers }).catch(() => null),
          fetch(`${API_BASE_URL}/api/v1/reconciliation/pending`, { headers }).catch(() => null),
          fetch(`${API_BASE_URL}/api/v1/smart-docs/applicants/pending-review`, { headers }).catch(() => null)
        ]);

        let updates = {};

        // Process tasks
        if (tasksResponse && tasksResponse.ok) {
          const tasks = await tasksResponse.json();
          // Check both 'type' and 'status' fields — backend returns 'type' (TaskType enum)
          const isTaskCompleted = (t) => {
            const s = (t.status || t.type || '').toLowerCase();
            return s === 'completed' || s === 'done';
          };
          const outstandingTasks = tasks.filter(t => !isTaskCompleted(t)).length;
          const urgentTasks = tasks.filter(t => t.priority === 'high' && !isTaskCompleted(t)).length;
          updates.tasks = outstandingTasks;
          updates.urgentTasks = urgentTasks;
        }

        // Process reconciliation count
        if (reconciliationResponse && reconciliationResponse.ok) {
          const reconciliationData = await reconciliationResponse.json();
          // Handle both array response and object with items array
          const items = Array.isArray(reconciliationData) ? reconciliationData : (reconciliationData.items || []);
          updates.reconciliation = items.length;
        }

        // Process smart docs count
        if (smartDocsResponse && smartDocsResponse.ok) {
          const smartDocsData = await smartDocsResponse.json();
          // Sum up pending counts from all loans
          const totalPending = Array.isArray(smartDocsData)
            ? smartDocsData.reduce((sum, loan) => sum + (loan.pending_count || 0), 0)
            : 0;
          updates.smartDocs = totalPending;
        }

        setTaskCounts(prev => ({ ...prev, ...updates }));
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

  // Block the entire app when a forced update or maintenance is required
  if (versionStatus?.needsForceUpdate || versionStatus?.maintenanceMode) {
    return (
      <UpdateRequiredModal
        forceUpdate={versionStatus.needsForceUpdate}
        maintenanceMode={versionStatus.maintenanceMode}
        maintenanceMessage={versionStatus.maintenanceMessage}
        updateUrl={versionStatus.updateUrl}
        recommendedVersion={versionStatus.recommendedVersion}
        changelog={versionStatus.changelog}
      />
    );
  }

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
      <ErrorBoundary>
        <OfflineIndicator />
        {/* GLBA-compliant session timeout — warns at 13min, locks at 15min of inactivity */}
        <SessionTimeoutModal />
        {/* Optional update banner (dismissible) */}
        {versionStatus?.updateAvailable && !updateBannerDismissed && (
          <UpdateRequiredModal
            updateAvailable
            updateUrl={versionStatus.updateUrl}
            recommendedVersion={versionStatus.recommendedVersion}
            onDismiss={() => setUpdateBannerDismissed(true)}
          />
        )}
        <ImpersonationProvider>
        <PermissionProvider>
        <ModuleProvider>
        <BrandingProvider>
          <Router>
            <PushNotificationInitializer />
            <GlobalLayoutFix />
            <ImpersonationBanner />
            <div className="app">
        <Routes>
          {/* Public routes - Mobile app launches Aria voice assistant */}
          {/* Check for native platform OR loading from local IP (dev mode on device) */}
          <Route path="/" element={
            Capacitor.isNativePlatform() || window.location.hostname.startsWith('192.168.')
              ? <Navigate to="/aria-voice" />
              : <ExternalRedirect to="https://www.perenniaai.com" />
          } />
          <Route path="/aria-test" element={<LazyPage><AriaTestPage /></LazyPage>} />
          <Route path="/apply" element={<BuyerIntake />} />
          <Route path="/apply/preview" element={<LazyPage><ApplicationPreview /></LazyPage>} />
          <Route path="/mortgage-planner" element={<LazyPage><MortgagePlannerQuestionnaire /></LazyPage>} />
          <Route path="/questionnaire" element={<LazyPage><MortgagePlannerQuestionnaire /></LazyPage>} />
          {/* <Route path="/decision-lab" element={<LazyPage><DecisionLab /></LazyPage>} /> */}{/* DEPRECATED: Experimental feature deregistered */}
          <Route path="/mortgage-calculator" element={<LazyPage><MortgageCalculator /></LazyPage>} />
          <Route path="/estimate-comparison" element={<LazyPage><EstimateComparison /></LazyPage>} />
          <Route path="/register" element={<Registration />} />
          <Route path="/verify-account" element={<AccountVerification />} />
          <Route path="/verify-email-sent" element={<EmailVerificationSent />} />
          <Route path="/login" element={<Login />} />
          <Route
            path="/briefing"
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
                    <LazyPage><BriefingPage /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route path="/aria" element={<PrivateRoute><LazyPage><AriaVoiceApp /></LazyPage></PrivateRoute>} />
          <Route path="/aria/calendar" element={<PrivateRoute><LazyPage><AriaCalendarPage /></LazyPage></PrivateRoute>} />
          <Route path="/aria/calculator" element={<PrivateRoute><LazyPage><AriaMortgageCalculator /></LazyPage></PrivateRoute>} />
          {/* Mobile-native routes (no Navigation wrapper, no app-layout) */}
          <Route path="/mobile-aria" element={<MobileErrorBoundary><PrivateRoute><LazyPage><MobileAriaChat /></LazyPage></PrivateRoute></MobileErrorBoundary>} />
          <Route path="/mobile-home" element={<MobileErrorBoundary><PrivateRoute><LazyPage><MobileHomeDashboard /></LazyPage></PrivateRoute></MobileErrorBoundary>} />
          <Route path="/mobile/leads" element={<MobileErrorBoundary><PrivateRoute><LazyPage><MobileLeadsList /></LazyPage></PrivateRoute></MobileErrorBoundary>} />
          <Route path="/mobile/pipeline" element={<MobileErrorBoundary><PrivateRoute><LazyPage><MobilePipelineView /></LazyPage></PrivateRoute></MobileErrorBoundary>} />
          <Route path="/aria/notifications" element={<MobileErrorBoundary><PrivateRoute><LazyPage><MobileNotificationCenter /></LazyPage></PrivateRoute></MobileErrorBoundary>} />
          {/* Aria Mobile Redesign — voice-first 5-screen app */}
          <Route path="/aria-voice" element={<MobileErrorBoundary><PrivateRoute><LazyPage><AriaVoiceHome /></LazyPage></PrivateRoute></MobileErrorBoundary>} />
          <Route path="/mobile-calendar" element={<MobileErrorBoundary><PrivateRoute><LazyPage><MobileCalendar /></LazyPage></PrivateRoute></MobileErrorBoundary>} />
          <Route path="/mobile-tasks" element={<MobileErrorBoundary><PrivateRoute><LazyPage><MobileTasks /></LazyPage></PrivateRoute></MobileErrorBoundary>} />
          <Route path="/mobile-appointment/:id" element={<MobileErrorBoundary><PrivateRoute><LazyPage><MobileAppointmentDetail /></LazyPage></PrivateRoute></MobileErrorBoundary>} />
          <Route path="/mobile-ci" element={<MobileErrorBoundary><PrivateRoute><LazyPage><MobileCallIntel /></LazyPage></PrivateRoute></MobileErrorBoundary>} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/signup" element={<AdminOnboarding />} />
          <Route path="/application-submitted" element={<ApplicationSubmitted />} />
          <Route path="/privacy-policy" element={<LazyPage><PrivacyPolicy /></LazyPage>} />
          <Route path="/terms-of-service" element={<LazyPage><TermsOfService /></LazyPage>} />

          {/* Realtor Portal (public - token-based auth) */}
          <Route path="/realtor-portal" element={<LazyPage><RealtorPortal /></LazyPage>} />

          {/* Listing Agent Portal (public - magic link auth) */}
          <Route path="/listing-agent-portal" element={<LazyPage><ListingAgentPortal /></LazyPage>} />

          {/* DEPRECATED: Premium feature deregistered — not yet launched */}
          {/* <Route path="/recruit-portal/:slug" element={<LazyPage><RecruitPortal /></LazyPage>} /> */}
          {/* <Route path="/join/:slug" element={<LazyPage><RecruitPortal /></LazyPage>} /> */}

          {/* DEPRECATED: Premium feature deregistered — not yet launched */}
          {/* <Route path="/disc-assessment/:token" element={<LazyPage><DISCAssessment /></LazyPage>} /> */}
          {/* <Route path="/assessment/disc" element={<LazyPage><DISCAssessment /></LazyPage>} /> */}

          {/* Employee Invite Accept (public) */}
          <Route path="/invite/accept/:token" element={<LazyPage><AcceptInvite /></LazyPage>} />
          <Route path="/accept-invite" element={<LazyPage><AcceptInvite /></LazyPage>} />

          {/* User Activation (public) */}
          <Route path="/activate" element={<LazyPage><ActivateAccount /></LazyPage>} />

          {/* Video Meeting Room (public/private) */}
          <Route path="/meeting/:roomCode" element={<LazyPage><MeetingRoom /></LazyPage>} />

          {/* Public Booking Page */}
          <Route path="/book/:slug" element={<LazyPage><PublicBooking /></LazyPage>} />

          {/* Embeddable Booking Widget (standalone page for iframe embedding) */}
          <Route path="/embed/book/:slug" element={<LazyPage><EmbedBooking /></LazyPage>} />

          {/* Public Booking Confirmation (standalone, token-based) */}
          <Route path="/booking/confirmation/:appointmentId" element={<LazyPage><BookingConfirmationPage /></LazyPage>} />

          {/* Portal Components Test Page */}
          <Route path="/portal-test" element={<LazyPage><PortalTest /></LazyPage>} />

          {/* Loan Officer Microsite (public) - Uses ThemeRenderer for dynamic themes */}
          <Route path="/lo/:slug" element={<LazyPage><ThemeRenderer /></LazyPage>} />
          <Route path="/lo/:slug/:pageSlug" element={<LazyPage><ThemeRenderer /></LazyPage>} />
          <Route path="/microsite/loan-officer/:userId" element={<LazyPage><ThemeRenderer /></LazyPage>} />
          <Route path="/microsite/preview" element={<LazyPage><MicrositePreview /></LazyPage>} />

          {/* Theme Preview (public) - Preview themes with sample data */}
          <Route path="/preview/theme/:themeSlug" element={<LazyPage><ThemePreview /></LazyPage>} />

          {/* Borrower Login (public - social login for applicants) */}
          <Route path="/apply/login" element={<LazyPage><BorrowerLogin /></LazyPage>} />

          {/* Magic link verification - redirects to backend API */}
          <Route path="/apply/verify" element={<LazyPage><ApplyVerify /></LazyPage>} />

          {/* Borrower Application Start - Demo mode of PurchaseApplication */}
          <Route path="/apply/start" element={<LazyPage><PurchaseApplication /></LazyPage>} />

          {/* Purpose-specific applications */}
          <Route path="/apply/purchase" element={<LazyPage><PurchaseApplication /></LazyPage>} />
          <Route path="/apply/refinance" element={<LazyPage><RefinanceApplication /></LazyPage>} />

          {/* Pre-Qualification Forms (public, embeddable) */}
          <Route path="/prequal/purchase" element={<LazyPage><PurchasePreQualForm embedded={new URLSearchParams(window.location.search).get('embedded') === 'true'} /></LazyPage>} />

          {/* Enhanced applications (v2) */}
          <Route path="/apply/v2/purchase" element={<LazyPage><NewPurchaseApplication /></LazyPage>} />
          <Route path="/apply/v2/refinance" element={<LazyPage><NewRefinanceApplication /></LazyPage>} />
          <Route path="/apply/demo" element={<LazyPage><ApplicationDemo /></LazyPage>} />

          {/* Borrower OAuth Callbacks */}
          <Route path="/apply/oauth/:provider/callback" element={<LazyPage><BorrowerOAuthCallback /></LazyPage>} />

          {/* Borrower Application (public - token-based access) */}
          <Route path="/apply/:token" element={<LazyPage><BorrowerApplication /></LazyPage>} />

          {/* Co-borrower Application (public - token-based access) */}
          <Route path="/coborrower/:token" element={<LazyPage><CoborrowerApplication /></LazyPage>} />

          {/* Legacy Borrower Portal - moved to /borrower-portal to avoid conflict with PURL /portal/:slug route */}
          <Route path="/borrower-portal/:token" element={<LazyPage><BorrowerPortal /></LazyPage>} />
          <Route path="/borrower-portal" element={<LazyPage><BorrowerPortal /></LazyPage>} />

          {/* Shared Calculator Result (public - token-based access) */}
          <Route path="/shared/calculator/:shareToken" element={<LazyPage><SharedCalculator /></LazyPage>} />

          {/* Calculator Dashboard - All calculators on one page with sidebar navigation */}
          <Route path="/calculators" element={<LazyPage><CalculatorDashboard /></LazyPage>} />
          <Route path="/calculator-dashboard" element={<LazyPage><CalculatorDashboard /></LazyPage>} />
          <Route path="/all-in-one-loan" element={<LazyPage><AllInOneLoan /></LazyPage>} />

          {/* Active Loan Portal - Real-time borrower dashboard with WebSocket updates */}
          <Route path="/portal/loan/:loanId" element={<LazyPage><ActiveLoanPortalComplete /></LazyPage>} />
          <Route path="/portal/active/:token" element={<LazyPage><ActiveLoanPortalComplete /></LazyPage>} />

          {/* Perennia Client Portal Ultimate - Production-ready lifecycle portal */}
          <Route path="/portal/ultimate/:loanId" element={<LazyPage><PerenniaClientPortalUltimate /></LazyPage>} />
          <Route path="/portal/ultimate/token/:token" element={<LazyPage><PerenniaClientPortalUltimate /></LazyPage>} />

          {/* Loan to Portal Redirect - Maps loan IDs to borrower portal access */}
          <Route path="/portal/redirect/:loanId" element={<LazyPage><LoanPortalRedirect /></LazyPage>} />
          <Route path="/client-portal/:loanId" element={<LazyPage><LoanPortalRedirect /></LazyPage>} />

          {/* Total Cost Analysis - Mortgage Coach style comparison tool */}
          <Route path="/portal/tca/:loanId" element={<LazyPage><TotalCostAnalysis /></LazyPage>} />
          <Route path="/analysis/:token" element={<LazyPage><TotalCostAnalysis /></LazyPage>} />

          {/* Income Calculator Popout - Opens in separate window for multi-monitor viewing */}
          <Route path="/income-calculator-popout" element={<LazyPage><IncomeCalculatorPopout /></LazyPage>} />

          {/* Partner Portal - Realtor/Partner view with magic link access */}
          <Route path="/partner/:token" element={<LazyPage><PartnerPortalView /></LazyPage>} />

          {/* OAuth Callback (public) */}
          <Route path="/oauth/callback" element={<LazyPage><OAuthCallback /></LazyPage>} />

          {/* E-Signature Signing Session (public - token-based auth) */}
          <Route path="/sign/:token" element={<LazyPage><SigningSession /></LazyPage>} />

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

          {/* Usage Intelligence Dashboard - Owner cost tracking & pricing */}
          <Route
            path="/usage-intelligence"
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
                    <LazyPage><UsageIntelligenceDashboard /></LazyPage>
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

          {/* Pipeline Probability - AI-powered closing predictions */}
          <Route
            path="/pipeline-probability"
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
                    <LazyPage><PipelineProbability /></LazyPage>
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
            path="/leads/:leadId/intake"
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
                    <LazyPage><IntakeEngine /></LazyPage>
                  </main>
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
            path="/loans/:loanId/intake"
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
                    <LazyPage><IntakeEngine /></LazyPage>
                  </main>
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
            path="/rate-monitor"
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
                    <LazyPage><RateMonitor /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/closed-loans"
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
                    <LazyPage><ClosedLoans /></LazyPage>
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
            path="/calendar-settings"
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
                    <LazyPage><CalendarSettings /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/calendar/setup"
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
                    <LazyPage><CalendarSetupWizard /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/calendar/analytics"
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
                    <LazyPage><CalendarAnalyticsPage /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/calendar/surveys"
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
                    <LazyPage><SurveyResultsPage /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/calendar/buffer-settings"
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
                    <LazyPage><BufferSettingsPage /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/calendar/waitlist"
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
                    <LazyPage><WaitlistPage /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/today"
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
                    <LazyPage><LOTodayView /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/team-calendar"
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
                    <LazyPage><TeamCalendar /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/marketing"
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
                    <LazyPage><Marketing /></LazyPage>
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
            path="/call-routing-config"
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
                    <LazyPage><CallRoutingConfig /></LazyPage>
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
            path="/video-os"
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
                    <LazyPage><VideoOS /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/voice/agents"
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
                    <LazyPage><VoiceAgentStudio /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/voice/agents/new"
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
                    <LazyPage><VoiceAgentBuilder /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/voice/live"
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
                    <LazyPage><VoiceLiveCallsMonitor /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/voice/queues"
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
                    <LazyPage><VoiceCallQueueDashboard /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/voice/conferences"
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
                    <LazyPage><VoiceConferenceRoomDashboard /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/voice/ivr"
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
                    <LazyPage><VoiceIVRMenuDashboard /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/voice/hold-music"
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
                    <LazyPage><VoiceHoldMusicDashboard /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/voice/talk"
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
                    <LazyPage><VoiceTalkToAgentPage /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/voice/analytics"
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
                    <LazyPage><VoiceCallAnalyticsDashboard /></LazyPage>
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
            path="/acquisition"
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
                    <LazyPage><AcquisitionDashboard /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          {/* Engagement Dashboard */}
          <Route
            path="/engagement"
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
                    <LazyPage><EngagementDashboard /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          {/* Accounting System Routes */}
          <Route
            path="/accounting/accounts"
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
                    <LazyPage><ChartOfAccounts /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/accounting/journal-entries"
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
                    <LazyPage><JournalEntries /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          {/* AR (Accounts Receivable) Routes */}
          <Route
            path="/accounting/ar/customers"
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
                    <LazyPage><ARCustomerList /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/accounting/ar/invoices"
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
                    <LazyPage><ARInvoiceList /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/accounting/ar/payments"
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
                    <LazyPage><ARPaymentList /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/accounting/ar/aging"
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
                    <LazyPage><ARAgingReport /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/accounting/ap/vendors"
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
                    <LazyPage><APVendorList /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/accounting/ap/bills"
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
                    <LazyPage><APBillList /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/accounting/ap/payments"
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
                    <LazyPage><APPayBills /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/accounting/ap/aging"
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
                    <LazyPage><APAgingReport /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/accounting/banking/accounts"
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
                    <LazyPage><BankAccounts /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/accounting/banking/connect"
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
                    <LazyPage><PlaidConnect /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/accounting/banking/transactions"
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
                    <LazyPage><BankTransactions /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/accounting/banking/reconcile"
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
                    <LazyPage><BankReconciliation /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/accounting/reports/profit-loss"
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
                    <LazyPage><ProfitLoss /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/accounting/reports/balance-sheet"
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
                    <LazyPage><BalanceSheet /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/accounting/reports/cash-flow"
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
                    <LazyPage><CashFlow /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/accounting/reports/trial-balance"
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
                    <LazyPage><TrialBalance /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/accounting/budgets"
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
                    <LazyPage><BudgetList /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/accounting/budgets/variance"
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
                    <LazyPage><BudgetVariance /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/accounting/*"
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
                    <LazyPage><AccountingDashboard /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/master-manager"
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
                    <LazyPage><MasterManagerCapacity /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          {/* DEPRECATED: Premium feature deregistered — not yet launched */}
          {/*
          <Route
            path="/master-manager/recruiting"
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
                    <LazyPage><MasterManagerRecruiting /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/master-manager/recruiting/:candidateId"
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
                    <LazyPage><RecruitDetail /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/partner-recruiting"
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
                    <LazyPage><PartnerRecruitingDashboard /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/partner-recruiting/:partnerId"
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
                    <LazyPage><PartnerRecruitDetail /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          */}
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
          {/* Smart Scheduler merged into Calendar Settings */}
          <Route
            path="/settings/smart-scheduler"
            element={<Navigate to="/calendar-settings" replace />}
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
            path="/settings/integrations/salesforce"
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
                    <LazyPage><SalesforceIntegrationPage /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/settings/integrations/followupboss"
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
                    <LazyPage><FollowUpBossIntegrationPage /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/integrations"
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
            path="/settings/state-recording-rules"
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
                    <LazyPage><StateRecordingRules /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/settings/quote-language-presets"
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
                    <LazyPage><QuoteLanguagePresets /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/settings/calculator-types"
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
                    <LazyPage><CalculatorSettings /></LazyPage>
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
            path="/settings/account-management"
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
                    <LazyPage><AccountManagement /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/settings/billing"
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
                    <LazyPage><BillingSettings /></LazyPage>
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
          {/* DEPRECATED: Experimental feature deregistered
          <Route
            path="/avatar-studio"
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
                    <LazyPage><AvatarStudio /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          */}
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
            path="/call-intelligence"
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
                    <LazyPage><CallIntelligencePage /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/mobile/call-intelligence"
            element={
              <PrivateRoute>
                <LazyPage><MobileCallIntelligencePage /></LazyPage>
              </PrivateRoute>
            }
          />
          <Route
            path="/voice-onboarding"
            element={
              <PrivateRoute>
                <LazyPage><AriaVoiceOnboarding /></LazyPage>
              </PrivateRoute>
            }
          />
          <Route
            path="/aria-chat"
            element={
              <PrivateRoute>
                <LazyPage><AriaChatScreen /></LazyPage>
              </PrivateRoute>
            }
          />
          <Route
            path="/live-call-whisper"
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
                    <LazyPage><LiveCallWhisper /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/production-predictor"
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
                    <LazyPage><ProductionPredictor /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/production-predictor/detail"
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
                    <LazyPage><ProductionPredictorDetail /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/deal-alerts"
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
                    <LazyPage><DealAlerts /></LazyPage>
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

          {/* Smart Docs Enterprise Pages */}
          <Route
            path="/smart-docs/analytics"
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
                    <LazyPage><SmartDocsAnalytics /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/smart-docs/review-queue"
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
                    <LazyPage><SmartDocsReviewQueue /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/smart-docs/security"
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
                    <LazyPage><SmartDocsSecurity /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/smart-docs/bank-analysis"
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
                    <LazyPage><SmartDocsBankAnalysis /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/smart-docs/income"
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
                    <LazyPage><SmartDocsIncome /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/smart-docs/admin"
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
                    <LazyPage><SmartDocsAdmin /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />

          {/* E-Signature Field Placement Builder (staff - envelope management) */}
          <Route
            path="/esign/envelope/:envelopeId"
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
                    <LazyPage><FieldPlacementBuilder /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />

          {/* Listing Agent Portal Admin (transactions management) */}
          <Route
            path="/listing-portal"
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
                    <LazyPage><ListingPortalTransactions /></LazyPage>
                  </main>
                  <CoachCorner isOpen={coachOpen} onClose={() => setCoachOpen(false)} />
                </div>
              </PrivateRoute>
            }
          />
          <Route
            path="/listing-portal/transactions/:transactionId"
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
                    <LazyPage><ListingPortalTransactionDetail /></LazyPage>
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
            path="/carousel-builder"
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
                    <LazyPage><CarouselBuilder /></LazyPage>
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
            path="/ops-manager"
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
                    <LazyPage><OpsManagerDashboard /></LazyPage>
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
            path="/admin/permissions"
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
                    <LazyPage><PermissionsPage /></LazyPage>
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
            path="/admin/lead-assignment"
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
                    <LazyPage><LeadAssignmentConfig /></LazyPage>
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
            path="/support"
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
                    <LazyPage><Support /></LazyPage>
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
        {/* Aria FAB - floating mic button on native mobile */}
        <AriaFAB />
        </div>
      </Router>
        </BrandingProvider>
        </ModuleProvider>
        </PermissionProvider>
        </ImpersonationProvider>
      </ErrorBoundary>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

export default App;
