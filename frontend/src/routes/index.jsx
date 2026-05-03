import { lazy, Suspense } from 'react';
import { Route, Navigate } from 'react-router-dom';
import { Capacitor } from '@capacitor/core';
import MainLayout from '../layouts/MainLayout';
import RouteErrorBoundary from '../components/RouteErrorBoundary';
import MobileErrorBoundary from '../components/mobile/MobileErrorBoundary';
// eslint-disable-next-line no-unused-vars
import ProtectedRoute from '../components/ProtectedRoute';

// Landing/Auth pages (keep these as regular imports for faster initial load)
import Registration from '../pages/Registration';
import AccountVerification from '../pages/AccountVerification';
import EmailVerificationSent from '../pages/EmailVerificationSent';
import Login from '../pages/Login';
import ForgotPassword from '../pages/ForgotPassword';
import ResetPassword from '../pages/ResetPassword';
import AdminOnboarding from '../pages/AdminOnboarding';
import ApplicationSubmitted from '../pages/ApplicationSubmitted';
import BuyerIntake from '../pages/BuyerIntake';

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

const PageLoader = PageLoadingFallback;

// Retry dynamic imports on failure (handles stale chunks after deploys)
function lazyRetry(importFn) {
  return lazy(() =>
    importFn().catch(() => {
      const hasReloaded = sessionStorage.getItem('chunk_reload');
      if (!hasReloaded) {
        sessionStorage.setItem('chunk_reload', '1');
        window.location.reload();
        return new Promise(() => {}); // never resolves, page is reloading
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

// Wrapper to handle lazy-loaded pages with suspense and route-level error isolation
function LazyPage({ children, fallback }) {
  return (
    <RouteErrorBoundary fallback={fallback}>
      <Suspense fallback={<PageLoader />}>
        {children}
      </Suspense>
    </RouteErrorBoundary>
  );
}

// Clear chunk reload flag on successful load
sessionStorage.removeItem('chunk_reload');

// Error pages
const NotFound = lazyRetry(() => import('../pages/NotFound'));
const Forbidden = lazyRetry(() => import('../pages/Forbidden'));

// =============================================================================
// LAZY LOADED PAGE COMPONENTS
// =============================================================================

// Core pages
const Dashboard = lazyRetry(() => import('../pages/Dashboard'));
const CommandCenter = lazyRetry(() => import('../pages/CommandCenter'));
const OnboardingWizard = lazyRetry(() => import('../components/onboarding/OnboardingWizard'));
const Leads = lazyRetry(() => import('../pages/Leads'));
const LeadDetail = lazyRetry(() => import('../pages/LeadDetail'));
const Loans = lazyRetry(() => import('../pages/Loans'));
const LoanDetail = lazyRetry(() => import('../pages/LoanDetail'));
const Portfolio = lazyRetry(() => import('../pages/Portfolio'));
const ClosedLoans = lazyRetry(() => import('../pages/ClosedLoans'));
const PortfolioDetail = lazyRetry(() => import('../pages/PortfolioDetail'));
const MumClientDetail = lazyRetry(() => import('../pages/MumClientDetail'));
const YearOverYear = lazyRetry(() => import('../pages/YearOverYear'));
const RateMonitor = lazyRetry(() => import('../pages/RateMonitor'));
const Tasks = lazyRetry(() => import('../pages/Tasks'));
const SMSTasks = lazyRetry(() => import('../pages/SMSTasks'));
const Calendar = lazyRetry(() => import('../pages/Calendar'));
const CalendarSettings = lazyRetry(() => import('../pages/CalendarSettings'));
const CalendarSetupWizard = lazyRetry(() => import('../components/calendar/setup/CalendarSetupWizard'));
const CalendarAnalyticsPage = lazyRetry(() => import('../pages/CalendarAnalyticsPage'));
const SurveyResultsPage = lazyRetry(() => import('../pages/SurveyResultsPage'));
const BufferSettingsPage = lazyRetry(() => import('../pages/BufferSettingsPage'));
const WaitlistPage = lazyRetry(() => import('../pages/WaitlistPage'));
const LOTodayView = lazyRetry(() => import('../pages/LOTodayView'));
const TeamCalendar = lazyRetry(() => import('../pages/TeamCalendar'));
const Scorecard = lazyRetry(() => import('../pages/Scorecard'));
const Assistant = lazyRetry(() => import('../pages/Assistant'));
const ClientProfile = lazyRetry(() => import('../pages/ClientProfile'));
const ReferralPartners = lazyRetry(() => import('../pages/ReferralPartners'));
const ReferralPartnerDetail = lazyRetry(() => import('../pages/ReferralPartnerDetail'));
const PartnerDashboardPortal = lazyRetry(() => import('../pages/PartnerDashboardPortal'));
const PartnerClientDetail = lazyRetry(() => import('../pages/PartnerClientDetail'));
const AIUnderwriter = lazyRetry(() => import('../pages/AIUnderwriter'));
const GoalTracker = lazyRetry(() => import('../pages/GoalTracker'));
const Coach = lazyRetry(() => import('../pages/Coach'));
const ReconciliationCenter = lazyRetry(() => import('../pages/ReconciliationCenter'));
const MergeCenter = lazyRetry(() => import('../pages/MergeCenter'));
const Settings = lazyRetry(() => import('../pages/Settings'));
const TeamMembers = lazyRetry(() => import('../pages/TeamMembers'));
const TeamMemberProfile = lazyRetry(() => import('../pages/TeamMemberProfile'));
const MyProfile = lazyRetry(() => import('../pages/MyProfile'));
const MyPermissions = lazyRetry(() => import('../pages/MyPermissions'));
const ComplianceDashboard = lazyRetry(() => import('../pages/ComplianceDashboard'));
const OpsManagerDashboard = lazyRetry(() => import('../pages/OpsManagerDashboard'));
const AdminSettings = lazyRetry(() => import('../pages/AdminSettings'));
const PermissionsPage = lazyRetry(() => import('../pages/PermissionsPage'));
const AdminCustomDomains = lazyRetry(() => import('../pages/AdminCustomDomains'));
const DataUpload = lazyRetry(() => import('../pages/DataUpload'));
const EstimateComparison = lazyRetry(() => import('../pages/EstimateComparison'));
const Users = lazyRetry(() => import('../pages/Users'));
const UserProfile = lazyRetry(() => import('../pages/UserProfile'));
const ProcessTemplates = lazyRetry(() => import('../pages/ProcessTemplates'));
const ApplicationPreview = lazyRetry(() => import('../pages/ApplicationPreview'));
const VerizonTest = lazyRetry(() => import('../pages/VerizonTest'));

// Mobile-first pages
const MobileHomeDashboard = lazyRetry(() => import('../pages/MobileHomeDashboard'));
const MobileAriaChat = lazyRetry(() => import('../pages/MobileAriaChat'));
const MobileLeadsList = lazyRetry(() => import('../pages/MobileLeadsList'));
const MobileNotificationCenter = lazyRetry(() => import('../pages/MobileNotificationCenter'));
const MobilePipelineView = lazyRetry(() => import('../pages/MobilePipelineView'));

// Aria Mobile Redesign
const AriaVoiceHome = lazyRetry(() => import('../pages/aria-mobile/AriaVoiceHome'));
const AriaVoiceHistory = lazyRetry(() => import('../pages/aria-mobile/AriaVoiceHistory'));
const MobileCalendar = lazyRetry(() => import('../pages/aria-mobile/MobileCalendar'));
const MobileTasks = lazyRetry(() => import('../pages/aria-mobile/MobileTasks'));
const MobileAppointmentDetail = lazyRetry(() => import('../pages/aria-mobile/MobileAppointmentDetail'));
const MobileCallIntel = lazyRetry(() => import('../pages/aria-mobile/MobileCallIntel'));
const AriaVoiceOnboarding = lazyRetry(() => import('../pages/aria-mobile/AriaVoiceOnboarding'));
const AriaChatScreen = lazyRetry(() => import('../pages/aria-mobile/AriaChatScreen'));

// Efficiency & Pipeline pages
const PipelineEfficiency = lazyRetry(() => import('../pages/PipelineEfficiency'));
const StageEmployees = lazyRetry(() => import('../pages/StageEmployees'));
const EmployeeLoans = lazyRetry(() => import('../pages/EmployeeLoans'));
const TeamRoleEmployees = lazyRetry(() => import('../pages/TeamRoleEmployees'));
const BottleneckLoans = lazyRetry(() => import('../pages/BottleneckLoans'));

// AI & Voice pages
const AIReceptionistDashboard = lazyRetry(() => import('../pages/AIReceptionistDashboard'));
const CallRoutingConfig = lazyRetry(() => import('../pages/CallRoutingConfig'));
const VoiceOSDashboard = lazyRetry(() => import('../pages/VoiceOSDashboard'));
const VideoOS = lazyRetry(() => import('../pages/VideoOS'));
const VoiceAgentStudio = lazyRetry(() => import('../components/voice/AgentStudio'));
const VoiceLiveCallsMonitor = lazyRetry(() => import('../components/voice/LiveCallsMonitor'));
const VoiceAgentBuilder = lazyRetry(() => import('../components/voice/AgentBuilder'));
const VoiceCallQueueDashboard = lazyRetry(() => import('../components/voice/CallQueueDashboard'));
const VoiceConferenceRoomDashboard = lazyRetry(() => import('../components/voice/ConferenceRoomDashboard'));
const VoiceIVRMenuDashboard = lazyRetry(() => import('../components/voice/IVRMenuDashboard'));
const VoiceHoldMusicDashboard = lazyRetry(() => import('../components/voice/HoldMusicDashboard'));
const VoiceTalkToAgentPage = lazyRetry(() => import('../components/voice/TalkToAgentPage'));
const VoiceCallAnalyticsDashboard = lazyRetry(() => import('../components/voice/CallAnalyticsDashboard'));
const CallIntelligencePage = lazyRetry(() => import('../pages/CallIntelligencePage'));
const MobileCallIntelligencePage = lazyRetry(() => import('../pages/MobileCallIntelligencePage'));
const URLACallIntelligencePage = lazyRetry(() => import('../pages/URLACallIntelligencePage'));
const AILandingPage = lazyRetry(() => import('../pages/AILandingPage'));
const AriaVoiceApp = lazyRetry(() => import('../pages/AriaVoiceApp'));
const AriaCalendarPage = lazyRetry(() => import('../pages/aria/AriaCalendarPage'));
const AriaMortgageCalculator = lazyRetry(() => import('../pages/aria/AriaMortgageCalculator'));
const AriaTestPage = lazyRetry(() => import('../pages/AriaTestPage'));

// Workflow & Analytics pages
const WorkflowDashboard = lazyRetry(() => import('../pages/WorkflowDashboard'));
const WorkflowStagePage = lazyRetry(() => import('../pages/WorkflowStagePage'));
const WorkflowStatusDetail = lazyRetry(() => import('../pages/WorkflowStatusDetail'));
const MarketDashboard = lazyRetry(() => import('../pages/MarketDashboard'));
const MorningCheckin = lazyRetry(() => import('../pages/MorningCheckin'));
const PartnerROIDashboard = lazyRetry(() => import('../pages/PartnerROIDashboard'));
const ProfitabilityDashboard = lazyRetry(() => import('../pages/ProfitabilityDashboard'));
const UsageIntelligenceDashboard = lazyRetry(() => import('../pages/UsageIntelligenceDashboard'));
const ScenarioModeling = lazyRetry(() => import('../pages/ScenarioModeling'));
const MortgageCalculator = lazyRetry(() => import('../pages/MortgageCalculator'));
const AllInOneLoan = lazyRetry(() => import('../pages/AllInOneLoan'));
const PipelineProbability = lazyRetry(() => import('../pages/PipelineProbability'));
const SLASettings = lazyRetry(() => import('../pages/SLASettings'));
const EmployeeOnboardingAdmin = lazyRetry(() => import('../pages/EmployeeOnboardingAdmin'));
const AcceptInvite = lazyRetry(() => import('../pages/AcceptInvite'));
const MortgagePlannerQuestionnaire = lazyRetry(() => import('../pages/MortgagePlannerQuestionnaire'));
const KnowledgeBase = lazyRetry(() => import('../pages/KnowledgeBase'));
const Support = lazyRetry(() => import('../pages/Support'));
const PowerDialer = lazyRetry(() => import('../pages/PowerDialer'));
const UserCreationWizard = lazyRetry(() => import('../pages/UserCreationWizard'));
const UserBulkUpload = lazyRetry(() => import('../pages/UserBulkUpload'));
const ActivateAccount = lazyRetry(() => import('../pages/ActivateAccount'));
const MeetingRoom = lazyRetry(() => import('../pages/MeetingRoom'));
const OAuthCallback = lazyRetry(() => import('../pages/OAuthCallback'));
const CommunicationIntelligence = lazyRetry(() => import('../pages/CommunicationIntelligence'));
const AIOutreach = lazyRetry(() => import('../pages/AIOutreach'));
const ConversationIntelligence = lazyRetry(() => import('../pages/ConversationIntelligence'));
const ConversationIntelligenceRecordingDetail = lazyRetry(() => import('../pages/ConversationIntelligenceRecordingDetail'));
const BriefingPage = lazyRetry(() => import('../pages/BriefingPage'));
const ApplicationAnalytics = lazyRetry(() => import('../pages/ApplicationAnalytics'));

// Smart Docs pages
const SmartDocs = lazyRetry(() => import('../pages/SmartDocs'));
const SmartDocsClientDetail = lazyRetry(() => import('../pages/SmartDocsClientDetail'));
const SmartDocsDashboard = lazyRetry(() => import('../pages/SmartDocsDashboard'));
const SmartDocsAnalytics = lazyRetry(() => import('../pages/SmartDocsAnalytics'));
const SmartDocsReviewQueue = lazyRetry(() => import('../pages/SmartDocsReviewQueue'));
const SmartDocsSecurity = lazyRetry(() => import('../pages/SmartDocsSecurity'));
const SmartDocsBankAnalysis = lazyRetry(() => import('../pages/SmartDocsBankAnalysis'));
const SmartDocsIncome = lazyRetry(() => import('../pages/SmartDocsIncome'));
const SmartDocsAdmin = lazyRetry(() => import('../pages/SmartDocsAdmin'));
const SmartDocsCadence = lazyRetry(() => import('../pages/SmartDocsCadence'));
const EnterpriseDocumentationPortal = lazyRetry(() => import('../pages/EnterpriseDocumentationPortal'));
const AppCompletionScoring = lazyRetry(() => import('../pages/AppCompletionScoring'));

// Content & Blog
const AIDailyBlog = lazyRetry(() => import('../pages/AIDailyBlog'));
const PublicBooking = lazyRetry(() => import('../pages/PublicBooking'));
const BookingConfirmationPage = lazyRetry(() => import('../pages/BookingConfirmationPage'));
const EmbedBooking = lazyRetry(() => import('../pages/EmbedBooking'));

// Application pages
const BorrowerApplication = lazyRetry(() => import('../pages/BorrowerApplication'));
const AdaptiveURLA = lazyRetry(() => import('../pages/AdaptiveURLA'));
const PurchaseApplication = lazyRetry(() => import('../pages/PurchaseApplication'));
const RefinanceApplication = lazyRetry(() => import('../pages/RefinanceApplication'));
const PurchasePreQualForm = lazyRetry(() => import('../pages/PurchasePreQualForm'));
const NewPurchaseApplication = lazyRetry(() => import('../pages/applications/NewPurchaseApplication'));
const NewRefinanceApplication = lazyRetry(() => import('../pages/applications/NewRefinanceApplication'));
const ApplicationDemo = lazyRetry(() => import('../pages/applications/ApplicationDemo'));
const VoiceReviewPage = lazyRetry(() => import('../pages/VoiceReviewPage'));
const CoborrowerApplication = lazyRetry(() => import('../pages/CoborrowerApplication'));
const BorrowerLogin = lazyRetry(() => import('../pages/BorrowerLogin'));
const ApplyVerify = lazyRetry(() => import('../pages/ApplyVerify'));
const BorrowerOAuthCallback = lazyRetry(() => import('../pages/BorrowerOAuthCallback'));
const BorrowerPortal = lazyRetry(() => import('../pages/BorrowerPortal'));
const SharedCalculator = lazyRetry(() => import('../pages/SharedCalculator'));
const CalculatorDashboard = lazyRetry(() => import('../pages/CalculatorDashboard'));
const PortalTest = lazyRetry(() => import('../pages/PortalTest'));

// Microsite pages
const ThemeRenderer = lazyRetry(() => import('../pages/microsites/ThemeRenderer'));
const ThemePreview = lazyRetry(() => import('../pages/microsites/ThemePreview'));
const MicrositePreview = lazyRetry(() => import('../pages/microsites/MicrositePreview'));
const MicrositeWizard = lazyRetry(() => import('../components/microsites/MicrositeWizard'));
const MicrositeEditor = lazyRetry(() => import('../pages/MicrositeEditor'));

// Dashboard pages
const LODashboard = lazyRetry(() => import('../pages/LODashboard'));
const RealtorDashboard = lazyRetry(() => import('../pages/RealtorDashboard'));
const RealtorPortal = lazyRetry(() => import('../pages/RealtorPortal'));
const AdminPanel = lazyRetry(() => import('../pages/AdminPanel'));
const LeadAssignmentConfig = lazyRetry(() => import('../pages/LeadAssignmentConfig'));
const AgentDashboard = lazyRetry(() => import('../pages/AgentDashboard'));
const AgentProfile = lazyRetry(() => import('../pages/AgentProfile'));
const AcquisitionDashboard = lazyRetry(() => import('../pages/AcquisitionDashboard'));
const EngagementDashboard = lazyRetry(() => import('../pages/EngagementDashboard'));
const Marketing = lazyRetry(() => import('../pages/Marketing'));
const CarouselBuilder = lazyRetry(() => import('../pages/CarouselBuilder/CarouselBuilderPage'));

// Master Manager pages
const MasterManagerCapacity = lazyRetry(() => import('../pages/MasterManager/CapacityCommandCenter'));
const AgentGym = lazyRetry(() => import('../pages/AgentGym'));
const AgentGovernanceSettings = lazyRetry(() => import('../pages/AgentGovernanceSettings'));
const MemoryStaging = lazyRetry(() => import('../pages/MemoryStaging'));

// Settings pages
const EmailIntegrationSettings = lazyRetry(() => import('../pages/EmailIntegrationSettings'));
const UserProfileSettings = lazyRetry(() => import('../pages/UserProfileSettings'));
const DocumentUploadSettings = lazyRetry(() => import('../pages/DocumentUploadSettings'));
const LeadCaptureSettings = lazyRetry(() => import('../pages/LeadCaptureSettings'));
const ClientPortalSettings = lazyRetry(() => import('../pages/ClientPortalSettings'));
const CommunicationPreferences = lazyRetry(() => import('../pages/CommunicationPreferences'));
const IntegrationSettings = lazyRetry(() => import('../pages/IntegrationSettings'));
const SalesforceIntegrationPage = lazyRetry(() => import('../pages/SalesforceIntegrationPage'));
const FollowUpBossIntegrationPage = lazyRetry(() => import('../pages/FollowUpBossIntegrationPage'));
const Microsoft365IntegrationPage = lazyRetry(() => import('../pages/Microsoft365IntegrationPage'));
const StateRecordingRules = lazyRetry(() => import('../pages/settings/StateRecordingRules'));
const QuoteLanguagePresets = lazyRetry(() => import('../pages/settings/QuoteLanguagePresets'));
const CalculatorSettings = lazyRetry(() => import('../pages/settings/CalculatorSettings'));
const BillingSettings = lazyRetry(() => import('../pages/settings/BillingSettings'));
const APIKeysSettings = lazyRetry(() => import('../pages/APIKeysSettings'));
const CompanyBrandingSettings = lazyRetry(() => import('../pages/CompanyBrandingSettings'));
const AccountManagement = lazyRetry(() => import('../pages/AccountManagement'));

// Portal pages
const PURLDashboard = lazyRetry(() => import('../pages/PURLDashboard'));
const PURLApplication = lazyRetry(() => import('../pages/PURLApplication'));
const PortalContainer = lazyRetry(() => import('../pages/portal/PortalContainer'));
const POSApplication = lazyRetry(() => import('../pages/portal/POSApplication'));
const POSTestPage = lazyRetry(() => import('../pages/portal/POSTestPage'));
const POSEntryPage = lazyRetry(() => import('../pages/pos/POSEntryPage'));
const LoanPortalRedirect = lazyRetry(() => import('../components/Portal/LoanPortalRedirect'));
const AdminDocumentReviewQueue = lazyRetry(() => import('../pages/AdminDocumentReviewQueue'));
const IncomeCalculatorPopout = lazyRetry(() => import('../pages/IncomeCalculatorPopout'));
const IntakeEngine = lazyRetry(() => import('../components/intake/IntakeEngine'));
const ListingPortalTransactions = lazyRetry(() => import('../pages/ListingPortalTransactions'));
const ListingPortalTransactionDetail = lazyRetry(() => import('../pages/ListingPortalTransactionDetail'));
const ListingAgentPortal = lazyRetry(() => import('../pages/ListingAgentPortal'));
const PrivacyPolicy = lazyRetry(() => import('../pages/PrivacyPolicy'));
const TermsOfService = lazyRetry(() => import('../pages/TermsOfService'));
const LiveCallWhisper = lazyRetry(() => import('../pages/LiveCallWhisper'));
const ProductionPredictor = lazyRetry(() => import('../pages/ProductionPredictor'));
const ProductionPredictorDetail = lazyRetry(() => import('../pages/ProductionPredictorDetail'));
const DealAlerts = lazyRetry(() => import('../pages/DealAlerts'));
const ClientFilePage = lazyRetry(() => import('../pages/ClientFilePage'));

// Accounting System
const AccountingDashboard = lazyRetry(() => import('../pages/accounting/AccountingDashboard'));
const ChartOfAccounts = lazyRetry(() => import('../pages/accounting/ChartOfAccounts'));
const JournalEntries = lazyRetry(() => import('../pages/accounting/JournalEntries'));
const ARCustomerList = lazyRetry(() => import('../pages/accounting/ar/CustomerList'));
const ARInvoiceList = lazyRetry(() => import('../pages/accounting/ar/InvoiceList'));
const ARPaymentList = lazyRetry(() => import('../pages/accounting/ar/PaymentList'));
const ARAgingReport = lazyRetry(() => import('../pages/accounting/ar/AgingReport'));
const APVendorList = lazyRetry(() => import('../pages/accounting/ap/VendorList'));
const APBillList = lazyRetry(() => import('../pages/accounting/ap/BillList'));
const APPayBills = lazyRetry(() => import('../pages/accounting/ap/PayBills'));
const APAgingReport = lazyRetry(() => import('../pages/accounting/ap/AgingReport'));
const BankAccounts = lazyRetry(() => import('../pages/accounting/banking/BankAccounts'));
const PlaidConnect = lazyRetry(() => import('../pages/accounting/banking/PlaidConnect'));
const BankTransactions = lazyRetry(() => import('../pages/accounting/banking/BankTransactions'));
const BankReconciliation = lazyRetry(() => import('../pages/accounting/banking/BankReconciliation'));
const ProfitLoss = lazyRetry(() => import('../pages/accounting/reports/ProfitLoss'));
const BalanceSheet = lazyRetry(() => import('../pages/accounting/reports/BalanceSheet'));
const CashFlow = lazyRetry(() => import('../pages/accounting/reports/CashFlow'));
const TrialBalance = lazyRetry(() => import('../pages/accounting/reports/TrialBalance'));
const BudgetList = lazyRetry(() => import('../pages/accounting/budgets/BudgetList'));
const BudgetVariance = lazyRetry(() => import('../pages/accounting/budgets/BudgetVariance'));

// Portal Components
const ActiveLoanPortalComplete = lazyRetry(() => import('../components/Portal/ActiveLoanPortalComplete'));
const PartnerPortalView = lazyRetry(() => import('../components/Portal/PartnerPortalView'));
const PerenniaClientPortalUltimate = lazyRetry(() => import('../components/Portal/PerenniaClientPortalUltimate'));
const TotalCostAnalysis = lazyRetry(() => import('../components/Portal/TotalCostAnalysis'));

// E-Signature Components
const FieldPlacementBuilder = lazyRetry(() => import('../components/esign/FieldPlacementBuilder'));
const SigningSession = lazyRetry(() => import('../pages/esign/SigningSession'));

// =============================================================================
// ROUTE CONFIGURATION
// =============================================================================

/**
 * Generates all application routes.
 *
 * @param {Object} layoutProps - Props to pass to MainLayout (toggle functions, open states, task counts)
 * @param {Object} options - Additional options
 * @param {React.ComponentType} options.PrivateRoute - PrivateRoute wrapper component from App.jsx
 * @param {React.ReactElement} options.rootElement - Element for the "/" route (handles platform detection in App.jsx)
 * @returns {JSX.Element[]} Array of Route elements
 */
export function getRoutes(layoutProps, options = {}) {
  const {
    toggleAssistant,
    toggleCoach,
    toggleTaskSidebar,
    assistantOpen,
    coachOpen,
    taskSidebarOpen,
    taskCounts,
  } = layoutProps;

  const { PrivateRoute, rootElement } = options;

  // Helper to create a private route with MainLayout
  const withMainLayout = (Component, showCoach = true) => (
    <PrivateRoute>
      <MainLayout
        onToggleAssistant={toggleAssistant}
        onToggleCoach={toggleCoach}
        onToggleTaskSidebar={toggleTaskSidebar}
        assistantOpen={assistantOpen}
        coachOpen={coachOpen}
        taskSidebarOpen={taskSidebarOpen}
        taskCounts={taskCounts}
        showCoach={showCoach}
      >
        <Component />
      </MainLayout>
    </PrivateRoute>
  );

  // Helper for private route without MainLayout (mobile, standalone pages)
  const privateOnly = (Component) => (
    <PrivateRoute>
      <LazyPage><Component /></LazyPage>
    </PrivateRoute>
  );

  // Helper for role-protected route with MainLayout
  const withProtectedMainLayout = (Component, requiredRoles, showCoach = true) => (
    <ProtectedRoute requiredRoles={requiredRoles}>
      <MainLayout
        onToggleAssistant={toggleAssistant}
        onToggleCoach={toggleCoach}
        onToggleTaskSidebar={toggleTaskSidebar}
        assistantOpen={assistantOpen}
        coachOpen={coachOpen}
        taskSidebarOpen={taskSidebarOpen}
        taskCounts={taskCounts}
        showCoach={showCoach}
      >
        <Component />
      </MainLayout>
    </ProtectedRoute>
  );

  // Helper for mobile routes with error boundary
  const mobilePrivate = (Component) => (
    <MobileErrorBoundary>
      <PrivateRoute>
        <LazyPage><Component /></LazyPage>
      </PrivateRoute>
    </MobileErrorBoundary>
  );

  return [
    // =============================================================================
    // PUBLIC ROUTES
    // =============================================================================

    // Root route — platform-dependent, provided by App.jsx
    <Route key="/" path="/" element={rootElement} />,

    // Auth routes
    <Route key="/register" path="/register" element={<Registration />} />,
    <Route key="/verify-account" path="/verify-account" element={<AccountVerification />} />,
    <Route key="/verify-email-sent" path="/verify-email-sent" element={<EmailVerificationSent />} />,
    <Route key="/login" path="/login" element={<Login />} />,
    <Route key="/forgot-password" path="/forgot-password" element={<ForgotPassword />} />,
    <Route key="/reset-password" path="/reset-password" element={<ResetPassword />} />,
    <Route key="/signup" path="/signup" element={<AdminOnboarding />} />,
    <Route key="/application-submitted" path="/application-submitted" element={<ApplicationSubmitted />} />,

    // Public pages
    <Route key="/apply" path="/apply" element={<BuyerIntake />} />,
    <Route key="/apply/preview" path="/apply/preview" element={<LazyPage><ApplicationPreview /></LazyPage>} />,
    <Route key="/mortgage-planner" path="/mortgage-planner" element={<LazyPage><MortgagePlannerQuestionnaire /></LazyPage>} />,
    <Route key="/questionnaire" path="/questionnaire" element={<LazyPage><MortgagePlannerQuestionnaire /></LazyPage>} />,
    <Route key="/mortgage-calculator" path="/mortgage-calculator" element={<LazyPage><MortgageCalculator /></LazyPage>} />,
    <Route key="/estimate-comparison" path="/estimate-comparison" element={<LazyPage><EstimateComparison /></LazyPage>} />,
    <Route key="/privacy-policy" path="/privacy-policy" element={<LazyPage><PrivacyPolicy /></LazyPage>} />,
    <Route key="/terms-of-service" path="/terms-of-service" element={<LazyPage><TermsOfService /></LazyPage>} />,
    <Route key="/terms" path="/terms" element={<LazyPage><TermsOfService /></LazyPage>} />,
    <Route key="/aria-test" path="/aria-test" element={<LazyPage><AriaTestPage /></LazyPage>} />,
    <Route key="/pos" path="/pos" element={<LazyPage><POSEntryPage /></LazyPage>} />,
    <Route key="/pos-test" path="/pos-test" element={<LazyPage><POSTestPage /></LazyPage>} />,

    // Public portals
    <Route key="/realtor-portal" path="/realtor-portal" element={<LazyPage><RealtorPortal /></LazyPage>} />,
    <Route key="/listing-agent-portal" path="/listing-agent-portal" element={<LazyPage><ListingAgentPortal /></LazyPage>} />,
    <Route key="/invite/accept/:token" path="/invite/accept/:token" element={<LazyPage><AcceptInvite /></LazyPage>} />,
    <Route key="/accept-invite" path="/accept-invite" element={<LazyPage><AcceptInvite /></LazyPage>} />,
    <Route key="/activate" path="/activate" element={<LazyPage><ActivateAccount /></LazyPage>} />,
    <Route key="/meeting/:roomCode" path="/meeting/:roomCode" element={<LazyPage><MeetingRoom /></LazyPage>} />,
    <Route key="/book/org/:orgSlug/lo/:loSlug" path="/book/org/:orgSlug/lo/:loSlug" element={<LazyPage><PublicBooking /></LazyPage>} />,
    <Route key="/book/org/:orgSlug" path="/book/org/:orgSlug" element={<LazyPage><PublicBooking /></LazyPage>} />,
    <Route key="/book/:slug" path="/book/:slug" element={<LazyPage><PublicBooking /></LazyPage>} />,
    <Route key="/embed/book/:slug" path="/embed/book/:slug" element={<LazyPage><EmbedBooking /></LazyPage>} />,
    <Route key="/booking/confirmation/:appointmentId" path="/booking/confirmation/:appointmentId" element={<LazyPage><BookingConfirmationPage /></LazyPage>} />,
    <Route key="/portal-test" path="/portal-test" element={<LazyPage><PortalTest /></LazyPage>} />,

    // Microsite routes (public)
    <Route key="/lo/:slug" path="/lo/:slug" element={<LazyPage><ThemeRenderer /></LazyPage>} />,
    <Route key="/lo/:slug/:pageSlug" path="/lo/:slug/:pageSlug" element={<LazyPage><ThemeRenderer /></LazyPage>} />,
    <Route key="/microsite/loan-officer/:userId" path="/microsite/loan-officer/:userId" element={<LazyPage><ThemeRenderer /></LazyPage>} />,
    <Route key="/microsite/preview" path="/microsite/preview" element={<LazyPage><MicrositePreview /></LazyPage>} />,
    <Route key="/preview/theme/:themeSlug" path="/preview/theme/:themeSlug" element={<LazyPage><ThemePreview /></LazyPage>} />,

    // Borrower application routes (public)
    <Route key="/apply/login" path="/apply/login" element={<LazyPage><BorrowerLogin /></LazyPage>} />,
    <Route key="/apply/verify" path="/apply/verify" element={<LazyPage><ApplyVerify /></LazyPage>} />,
    <Route key="/apply/start" path="/apply/start" element={<LazyPage><PurchaseApplication /></LazyPage>} />,
    <Route key="/apply/purchase" path="/apply/purchase" element={<LazyPage><PurchaseApplication /></LazyPage>} />,
    <Route key="/apply/refinance" path="/apply/refinance" element={<LazyPage><RefinanceApplication /></LazyPage>} />,
    <Route key="/prequal/purchase" path="/prequal/purchase" element={<LazyPage><PurchasePreQualForm embedded={new URLSearchParams(window.location.search).get('embedded') === 'true'} /></LazyPage>} />,
    <Route key="/apply/v2/purchase" path="/apply/v2/purchase" element={<LazyPage><NewPurchaseApplication /></LazyPage>} />,
    <Route key="/apply/v2/refinance" path="/apply/v2/refinance" element={<LazyPage><NewRefinanceApplication /></LazyPage>} />,
    <Route key="/apply/demo" path="/apply/demo" element={<LazyPage><ApplicationDemo /></LazyPage>} />,
    <Route key="/apply/oauth/:provider/callback" path="/apply/oauth/:provider/callback" element={<LazyPage><BorrowerOAuthCallback /></LazyPage>} />,
    <Route key="/apply/voice-review/:token" path="/apply/voice-review/:token" element={<LazyPage><VoiceReviewPage /></LazyPage>} />,
    <Route key="/apply/:token" path="/apply/:token" element={<LazyPage><BorrowerApplication /></LazyPage>} />,
    <Route key="/coborrower/:token" path="/coborrower/:token" element={<LazyPage><CoborrowerApplication /></LazyPage>} />,
    <Route key="/borrower-portal/:token" path="/borrower-portal/:token" element={<LazyPage><BorrowerPortal /></LazyPage>} />,
    <Route key="/borrower-portal" path="/borrower-portal" element={<LazyPage><BorrowerPortal /></LazyPage>} />,
    <Route key="/shared/calculator/:shareToken" path="/shared/calculator/:shareToken" element={<LazyPage><SharedCalculator /></LazyPage>} />,
    <Route key="/calculators" path="/calculators" element={<LazyPage><CalculatorDashboard /></LazyPage>} />,
    <Route key="/calculator-dashboard" path="/calculator-dashboard" element={<LazyPage><CalculatorDashboard /></LazyPage>} />,
    <Route key="/all-in-one-loan" path="/all-in-one-loan" element={<LazyPage><AllInOneLoan /></LazyPage>} />,

    // Portal routes (public)
    <Route key="/portal/loan/:loanId" path="/portal/loan/:loanId" element={<LazyPage><ActiveLoanPortalComplete /></LazyPage>} />,
    <Route key="/portal/active/:token" path="/portal/active/:token" element={<LazyPage><ActiveLoanPortalComplete /></LazyPage>} />,
    <Route key="/portal/ultimate/:loanId" path="/portal/ultimate/:loanId" element={<LazyPage><PerenniaClientPortalUltimate /></LazyPage>} />,
    <Route key="/portal/ultimate/token/:token" path="/portal/ultimate/token/:token" element={<LazyPage><PerenniaClientPortalUltimate /></LazyPage>} />,
    <Route key="/portal/redirect/:loanId" path="/portal/redirect/:loanId" element={<LazyPage><LoanPortalRedirect /></LazyPage>} />,
    <Route key="/client-portal/:loanId" path="/client-portal/:loanId" element={<LazyPage><LoanPortalRedirect /></LazyPage>} />,
    <Route key="/portal/tca/:loanId" path="/portal/tca/:loanId" element={<LazyPage><TotalCostAnalysis /></LazyPage>} />,
    <Route key="/analysis/:token" path="/analysis/:token" element={<LazyPage><TotalCostAnalysis /></LazyPage>} />,
    <Route key="/income-calculator-popout" path="/income-calculator-popout" element={<LazyPage><IncomeCalculatorPopout /></LazyPage>} />,
    <Route key="/partner/:token" path="/partner/:token" element={<LazyPage><PartnerPortalView /></LazyPage>} />,
    <Route key="/oauth/callback" path="/oauth/callback" element={<LazyPage><OAuthCallback /></LazyPage>} />,
    <Route key="/sign/:token" path="/sign/:token" element={<LazyPage><SigningSession /></LazyPage>} />,
    <Route key="/portal/:slug" path="/portal/:slug" element={<LazyPage><PortalContainer /></LazyPage>} />,
    <Route key="/portal/:slug/apply" path="/portal/:slug/apply" element={<LazyPage><PURLApplication /></LazyPage>} />,
    <Route key="/portal/:slug/application" path="/portal/:slug/application" element={<LazyPage><POSApplication /></LazyPage>} />,

    // =============================================================================
    // PRIVATE ROUTES — NO MAIN LAYOUT (standalone / mobile / aria)
    // =============================================================================

    // Onboarding
    <Route key="/onboarding" path="/onboarding" element={<PrivateRoute><Navigate to="/onboarding/welcome" replace /></PrivateRoute>} />,
    <Route key="/onboarding/:step" path="/onboarding/:step" element={withMainLayout(OnboardingWizard)} />,

    // AI Landing (standalone)
    <Route key="/ai" path="/ai" element={privateOnly(AILandingPage)} />,

    // Aria standalone routes (no nav wrapper)
    <Route key="/aria" path="/aria" element={<PrivateRoute><LazyPage><AriaVoiceApp /></LazyPage></PrivateRoute>} />,
    <Route key="/aria/calendar" path="/aria/calendar" element={<PrivateRoute><LazyPage><AriaCalendarPage /></LazyPage></PrivateRoute>} />,
    <Route key="/aria/calculator" path="/aria/calculator" element={<PrivateRoute><LazyPage><AriaMortgageCalculator /></LazyPage></PrivateRoute>} />,

    // Mobile-native routes (no Navigation wrapper, no app-layout)
    <Route key="/mobile-aria" path="/mobile-aria" element={mobilePrivate(MobileAriaChat)} />,
    <Route key="/mobile-home" path="/mobile-home" element={mobilePrivate(MobileHomeDashboard)} />,
    <Route key="/mobile/leads" path="/mobile/leads" element={mobilePrivate(MobileLeadsList)} />,
    <Route key="/mobile/pipeline" path="/mobile/pipeline" element={mobilePrivate(MobilePipelineView)} />,
    <Route key="/aria/notifications" path="/aria/notifications" element={mobilePrivate(MobileNotificationCenter)} />,
    <Route key="/mobile/call-intelligence" path="/mobile/call-intelligence" element={<PrivateRoute><LazyPage><MobileCallIntelligencePage /></LazyPage></PrivateRoute>} />,

    // Aria Mobile Redesign — voice-first 5-screen app
    <Route key="/aria-mobile" path="/aria-mobile" element={mobilePrivate(AriaVoiceHome)} />,
    <Route key="/aria-voice" path="/aria-voice" element={mobilePrivate(AriaVoiceHome)} />,
    <Route key="/aria-history" path="/aria-history" element={mobilePrivate(AriaVoiceHistory)} />,
    <Route key="/mobile-calendar" path="/mobile-calendar" element={mobilePrivate(MobileCalendar)} />,
    <Route key="/mobile-tasks" path="/mobile-tasks" element={mobilePrivate(MobileTasks)} />,
    <Route key="/mobile-appointment/:id" path="/mobile-appointment/:id" element={mobilePrivate(MobileAppointmentDetail)} />,
    <Route key="/mobile-ci" path="/mobile-ci" element={mobilePrivate(MobileCallIntel)} />,
    <Route key="/voice-onboarding" path="/voice-onboarding" element={privateOnly(AriaVoiceOnboarding)} />,
    <Route key="/aria-chat" path="/aria-chat" element={privateOnly(AriaChatScreen)} />,

    // Partner portal (standalone, no nav)
    <Route key="/partner-portal/:id" path="/partner-portal/:id" element={privateOnly(PartnerDashboardPortal)} />,
    <Route key="/partner-portal/:partnerId/client/:clientId" path="/partner-portal/:partnerId/client/:clientId" element={privateOnly(PartnerClientDetail)} />,

    // =============================================================================
    // PROTECTED ROUTES WITH MAIN LAYOUT
    // =============================================================================

    // Dashboard & Command Center
    <Route key="/dashboard" path="/dashboard" element={withMainLayout(Dashboard)} />,
    <Route key="/command-center" path="/command-center" element={withMainLayout(CommandCenter)} />,
    <Route key="/briefing" path="/briefing" element={withMainLayout(BriefingPage)} />,
    <Route key="/dashboard/efficiency" path="/dashboard/efficiency" element={withMainLayout(PipelineEfficiency)} />,
    <Route key="/efficiency" path="/efficiency" element={withMainLayout(PipelineEfficiency)} />,
    <Route key="/efficiency/stage/:stageSlug" path="/efficiency/stage/:stageSlug" element={withMainLayout(StageEmployees)} />,
    <Route key="/efficiency/stage/:stageSlug/employee/:employeeId" path="/efficiency/stage/:stageSlug/employee/:employeeId" element={withMainLayout(EmployeeLoans)} />,
    <Route key="/efficiency/team/:roleSlug" path="/efficiency/team/:roleSlug" element={withMainLayout(TeamRoleEmployees)} />,
    <Route key="/efficiency/team/:roleSlug/employee/:employeeId" path="/efficiency/team/:roleSlug/employee/:employeeId" element={withMainLayout(EmployeeLoans)} />,
    <Route key="/efficiency/bottleneck/:bottleneckId" path="/efficiency/bottleneck/:bottleneckId" element={withMainLayout(BottleneckLoans)} />,

    // Workflow
    <Route key="/workflow" path="/workflow" element={withMainLayout(WorkflowDashboard)} />,
    <Route key="/workflow/:stage" path="/workflow/:stage" element={withMainLayout(WorkflowStagePage)} />,
    <Route key="/workflow/status/:statusId" path="/workflow/status/:statusId" element={withMainLayout(WorkflowStatusDetail)} />,

    // Analytics & Intelligence
    <Route key="/market" path="/market" element={withMainLayout(MarketDashboard)} />,
    <Route key="/checkin" path="/checkin" element={withMainLayout(MorningCheckin)} />,
    <Route key="/partner-roi" path="/partner-roi" element={withMainLayout(PartnerROIDashboard)} />,
    <Route key="/analytics/applications" path="/analytics/applications" element={withMainLayout(ApplicationAnalytics)} />,
    <Route key="/profitability" path="/profitability" element={withMainLayout(ProfitabilityDashboard)} />,
    <Route key="/usage-intelligence" path="/usage-intelligence" element={withProtectedMainLayout(UsageIntelligenceDashboard, ['admin', 'site_admin'])} />,
    <Route key="/profitability/scenarios" path="/profitability/scenarios" element={withMainLayout(ScenarioModeling)} />,
    <Route key="/pipeline-probability" path="/pipeline-probability" element={withMainLayout(PipelineProbability)} />,
    <Route key="/sla-tracking" path="/sla-tracking" element={withMainLayout(SLASettings)} />,

    // Leads & Loans
    <Route key="/leads" path="/leads" element={withMainLayout(Leads)} />,
    <Route key="/leads/:id" path="/leads/:id" element={withMainLayout(LeadDetail)} />,
    <Route key="/clients/:uuid" path="/clients/:uuid" element={withMainLayout(ClientFilePage)} />,
    <Route key="/leads/:leadId/intake" path="/leads/:leadId/intake" element={withMainLayout(IntakeEngine, false)} />,
    <Route key="/loans" path="/loans" element={withMainLayout(Loans)} />,
    <Route key="/loans/:id" path="/loans/:id" element={withMainLayout(LoanDetail)} />,
    <Route key="/loans/:loanId/intake" path="/loans/:loanId/intake" element={withMainLayout(IntakeEngine, false)} />,

    // Portfolio
    <Route key="/portfolio" path="/portfolio" element={withMainLayout(Portfolio)} />,
    <Route key="/rate-monitor" path="/rate-monitor" element={withMainLayout(RateMonitor)} />,
    <Route key="/closed-loans" path="/closed-loans" element={withMainLayout(ClosedLoans)} />,
    <Route key="/portfolio/detail" path="/portfolio/detail" element={withMainLayout(PortfolioDetail)} />,
    <Route key="/portfolio/year-over-year" path="/portfolio/year-over-year" element={withMainLayout(YearOverYear)} />,
    <Route key="/portfolio/:id" path="/portfolio/:id" element={withMainLayout(MumClientDetail)} />,

    // Tasks & Calendar
    <Route key="/tasks" path="/tasks" element={withMainLayout(Tasks)} />,
    <Route key="/sms-tasks" path="/sms-tasks" element={withMainLayout(SMSTasks)} />,
    <Route key="/calendar" path="/calendar" element={withMainLayout(Calendar)} />,
    <Route key="/calendar-settings" path="/calendar-settings" element={withMainLayout(CalendarSettings)} />,
    <Route key="/calendar/setup" path="/calendar/setup" element={withMainLayout(CalendarSetupWizard)} />,
    <Route key="/calendar/analytics" path="/calendar/analytics" element={withMainLayout(CalendarAnalyticsPage)} />,
    <Route key="/calendar/surveys" path="/calendar/surveys" element={withMainLayout(SurveyResultsPage)} />,
    <Route key="/calendar/buffer-settings" path="/calendar/buffer-settings" element={withMainLayout(BufferSettingsPage)} />,
    <Route key="/calendar/waitlist" path="/calendar/waitlist" element={withMainLayout(WaitlistPage)} />,
    <Route key="/today" path="/today" element={withMainLayout(LOTodayView)} />,
    <Route key="/team-calendar" path="/team-calendar" element={withMainLayout(TeamCalendar)} />,

    // Marketing
    <Route key="/marketing" path="/marketing" element={withMainLayout(Marketing)} />,
    <Route key="/scorecard" path="/scorecard" element={withMainLayout(Scorecard)} />,
    <Route key="/assistant" path="/assistant" element={withMainLayout(Assistant)} />,

    // Voice & AI
    <Route key="/ai-receptionist-dashboard" path="/ai-receptionist-dashboard" element={withMainLayout(AIReceptionistDashboard)} />,
    <Route key="/call-routing-config" path="/call-routing-config" element={withMainLayout(CallRoutingConfig)} />,
    <Route key="/voice-os-dashboard" path="/voice-os-dashboard" element={withMainLayout(VoiceOSDashboard)} />,
    <Route key="/video-os" path="/video-os" element={withMainLayout(VideoOS)} />,
    <Route key="/voice/agents" path="/voice/agents" element={withMainLayout(VoiceAgentStudio)} />,
    <Route key="/voice/agents/new" path="/voice/agents/new" element={withMainLayout(VoiceAgentBuilder)} />,
    <Route key="/voice/live" path="/voice/live" element={withMainLayout(VoiceLiveCallsMonitor)} />,
    <Route key="/voice/queues" path="/voice/queues" element={withMainLayout(VoiceCallQueueDashboard)} />,
    <Route key="/voice/conferences" path="/voice/conferences" element={withMainLayout(VoiceConferenceRoomDashboard)} />,
    <Route key="/voice/ivr" path="/voice/ivr" element={withMainLayout(VoiceIVRMenuDashboard)} />,
    <Route key="/voice/hold-music" path="/voice/hold-music" element={withMainLayout(VoiceHoldMusicDashboard)} />,
    <Route key="/voice/talk" path="/voice/talk" element={withMainLayout(VoiceTalkToAgentPage)} />,
    <Route key="/voice/analytics" path="/voice/analytics" element={withMainLayout(VoiceCallAnalyticsDashboard)} />,

    // Agents
    <Route key="/agents" path="/agents" element={withMainLayout(AgentDashboard)} />,
    <Route key="/acquisition" path="/acquisition" element={withMainLayout(AcquisitionDashboard)} />,
    <Route key="/engagement" path="/engagement" element={withMainLayout(EngagementDashboard)} />,
    <Route key="/agent/:id" path="/agent/:id" element={withMainLayout(AgentProfile)} />,
    <Route key="/agent/:agentId/settings" path="/agent/:agentId/settings" element={withMainLayout(AgentGovernanceSettings)} />,
    <Route key="/agent-gym" path="/agent-gym" element={withMainLayout(AgentGym)} />,

    // Accounting
    <Route key="/accounting/accounts" path="/accounting/accounts" element={withMainLayout(ChartOfAccounts)} />,
    <Route key="/accounting/journal-entries" path="/accounting/journal-entries" element={withMainLayout(JournalEntries)} />,
    <Route key="/accounting/ar/customers" path="/accounting/ar/customers" element={withMainLayout(ARCustomerList)} />,
    <Route key="/accounting/ar/invoices" path="/accounting/ar/invoices" element={withMainLayout(ARInvoiceList)} />,
    <Route key="/accounting/ar/payments" path="/accounting/ar/payments" element={withMainLayout(ARPaymentList)} />,
    <Route key="/accounting/ar/aging" path="/accounting/ar/aging" element={withMainLayout(ARAgingReport)} />,
    <Route key="/accounting/ap/vendors" path="/accounting/ap/vendors" element={withMainLayout(APVendorList)} />,
    <Route key="/accounting/ap/bills" path="/accounting/ap/bills" element={withMainLayout(APBillList)} />,
    <Route key="/accounting/ap/payments" path="/accounting/ap/payments" element={withMainLayout(APPayBills)} />,
    <Route key="/accounting/ap/aging" path="/accounting/ap/aging" element={withMainLayout(APAgingReport)} />,
    <Route key="/accounting/banking/accounts" path="/accounting/banking/accounts" element={withMainLayout(BankAccounts)} />,
    <Route key="/accounting/banking/connect" path="/accounting/banking/connect" element={withMainLayout(PlaidConnect)} />,
    <Route key="/accounting/banking/transactions" path="/accounting/banking/transactions" element={withMainLayout(BankTransactions)} />,
    <Route key="/accounting/banking/reconcile" path="/accounting/banking/reconcile" element={withMainLayout(BankReconciliation)} />,
    <Route key="/accounting/reports/profit-loss" path="/accounting/reports/profit-loss" element={withMainLayout(ProfitLoss)} />,
    <Route key="/accounting/reports/balance-sheet" path="/accounting/reports/balance-sheet" element={withMainLayout(BalanceSheet)} />,
    <Route key="/accounting/reports/cash-flow" path="/accounting/reports/cash-flow" element={withMainLayout(CashFlow)} />,
    <Route key="/accounting/reports/trial-balance" path="/accounting/reports/trial-balance" element={withMainLayout(TrialBalance)} />,
    <Route key="/accounting/budgets" path="/accounting/budgets" element={withMainLayout(BudgetList)} />,
    <Route key="/accounting/budgets/variance" path="/accounting/budgets/variance" element={withMainLayout(BudgetVariance)} />,
    <Route key="/accounting/*" path="/accounting/*" element={withMainLayout(AccountingDashboard)} />,

    // Master Manager
    <Route key="/master-manager" path="/master-manager" element={withMainLayout(MasterManagerCapacity)} />,

    // Settings
    <Route key="/settings" path="/settings" element={withMainLayout(Settings)} />,
    <Route key="/settings/smart-scheduler" path="/settings/smart-scheduler" element={<Navigate to="/calendar-settings" replace />} />,
    <Route key="/settings/email-integration" path="/settings/email-integration" element={withMainLayout(EmailIntegrationSettings)} />,
    <Route key="/settings/user-profile" path="/settings/user-profile" element={withMainLayout(UserProfileSettings)} />,
    <Route key="/settings/document-upload" path="/settings/document-upload" element={withMainLayout(DocumentUploadSettings)} />,
    <Route key="/settings/lead-capture" path="/settings/lead-capture" element={withMainLayout(LeadCaptureSettings)} />,
    <Route key="/settings/client-portal" path="/settings/client-portal" element={withMainLayout(ClientPortalSettings)} />,
    <Route key="/settings/communication" path="/settings/communication" element={withMainLayout(CommunicationPreferences)} />,
    <Route key="/settings/integrations" path="/settings/integrations" element={withMainLayout(IntegrationSettings)} />,
    <Route key="/settings/integrations/salesforce" path="/settings/integrations/salesforce" element={withMainLayout(SalesforceIntegrationPage)} />,
    <Route key="/settings/integrations/followupboss" path="/settings/integrations/followupboss" element={withMainLayout(FollowUpBossIntegrationPage)} />,
    <Route key="/settings/integrations/microsoft365" path="/settings/integrations/microsoft365" element={withMainLayout(Microsoft365IntegrationPage)} />,
    <Route key="/integrations" path="/integrations" element={withMainLayout(IntegrationSettings)} />,
    <Route key="/settings/state-recording-rules" path="/settings/state-recording-rules" element={withMainLayout(StateRecordingRules)} />,
    <Route key="/settings/quote-language-presets" path="/settings/quote-language-presets" element={withMainLayout(QuoteLanguagePresets)} />,
    <Route key="/settings/calculator-types" path="/settings/calculator-types" element={withMainLayout(CalculatorSettings)} />,
    <Route key="/settings/api-keys" path="/settings/api-keys" element={withMainLayout(APIKeysSettings)} />,
    <Route key="/settings/company-branding" path="/settings/company-branding" element={withMainLayout(CompanyBrandingSettings)} />,
    <Route key="/settings/account-management" path="/settings/account-management" element={withMainLayout(AccountManagement)} />,
    <Route key="/settings/billing" path="/settings/billing" element={withMainLayout(BillingSettings)} />,

    // Client & Partner management
    <Route key="/client-portals" path="/client-portals" element={withMainLayout(PURLDashboard)} />,
    <Route key="/client/:type/:id" path="/client/:type/:id" element={withMainLayout(ClientProfile)} />,
    <Route key="/referral-partners" path="/referral-partners" element={withMainLayout(ReferralPartners)} />,
    <Route key="/referral-partners/:id" path="/referral-partners/:id" element={withMainLayout(ReferralPartnerDetail)} />,

    // AI & Tools
    <Route key="/ai-underwriter" path="/ai-underwriter" element={withMainLayout(AIUnderwriter)} />,
    <Route key="/goal-tracker" path="/goal-tracker" element={withMainLayout(GoalTracker)} />,
    <Route key="/coach" path="/coach" element={withMainLayout(Coach)} />,
    <Route key="/reconciliation" path="/reconciliation" element={withMainLayout(ReconciliationCenter)} />,
    <Route key="/merge" path="/merge" element={withMainLayout(MergeCenter)} />,

    // Communication Intelligence
    <Route key="/communication-intelligence" path="/communication-intelligence" element={withMainLayout(CommunicationIntelligence)} />,
    <Route key="/email-intelligence" path="/email-intelligence" element={withMainLayout(CommunicationIntelligence)} />,
    <Route key="/ai-outreach" path="/ai-outreach" element={withMainLayout(AIOutreach)} />,
    <Route key="/conversation-intelligence" path="/conversation-intelligence" element={withMainLayout(ConversationIntelligence)} />,
    <Route key="/call-intelligence" path="/call-intelligence" element={withMainLayout(CallIntelligencePage)} />,
    <Route key="/urla-call-intelligence" path="/urla-call-intelligence" element={withMainLayout(URLACallIntelligencePage)} />,
    <Route key="/live-call-whisper" path="/live-call-whisper" element={withMainLayout(LiveCallWhisper)} />,
    <Route key="/production-predictor" path="/production-predictor" element={withMainLayout(ProductionPredictor)} />,
    <Route key="/production-predictor/detail" path="/production-predictor/detail" element={withMainLayout(ProductionPredictorDetail)} />,
    <Route key="/deal-alerts" path="/deal-alerts" element={withMainLayout(DealAlerts)} />,

    // Smart Docs
    <Route key="/smart-docs" path="/smart-docs" element={withMainLayout(SmartDocs)} />,
    <Route key="/smart-docs/dashboard" path="/smart-docs/dashboard" element={withMainLayout(SmartDocsDashboard)} />,
    <Route key="/smart-docs/client/:loanId" path="/smart-docs/client/:loanId" element={withMainLayout(SmartDocsClientDetail)} />,
    <Route key="/smart-docs/analytics" path="/smart-docs/analytics" element={withMainLayout(SmartDocsAnalytics)} />,
    <Route key="/smart-docs/review-queue" path="/smart-docs/review-queue" element={withMainLayout(SmartDocsReviewQueue)} />,
    <Route key="/smart-docs/security" path="/smart-docs/security" element={withMainLayout(SmartDocsSecurity)} />,
    <Route key="/smart-docs/bank-analysis" path="/smart-docs/bank-analysis" element={withMainLayout(SmartDocsBankAnalysis)} />,
    <Route key="/smart-docs/income" path="/smart-docs/income" element={withMainLayout(SmartDocsIncome)} />,
    <Route key="/smart-docs/admin" path="/smart-docs/admin" element={withMainLayout(SmartDocsAdmin)} />,
    <Route key="/smart-docs/cadence" path="/smart-docs/cadence" element={withMainLayout(SmartDocsCadence)} />,
    <Route key="/smart-docs/app-scoring" path="/smart-docs/app-scoring" element={withMainLayout(AppCompletionScoring)} />,
    <Route key="/smart-docs/app-scoring/:loanId" path="/smart-docs/app-scoring/:loanId" element={withMainLayout(AppCompletionScoring)} />,

    // Enterprise Documentation Portal
    <Route key="/enterprise-docs" path="/enterprise-docs" element={withMainLayout(EnterpriseDocumentationPortal)} />,

    // E-Signature
    <Route key="/esign/envelope/:envelopeId" path="/esign/envelope/:envelopeId" element={withMainLayout(FieldPlacementBuilder)} />,

    // Listing Portal Admin
    <Route key="/listing-portal" path="/listing-portal" element={withMainLayout(ListingPortalTransactions)} />,
    <Route key="/listing-portal/transactions/:transactionId" path="/listing-portal/transactions/:transactionId" element={withMainLayout(ListingPortalTransactionDetail)} />,

    // Blog & Content
    <Route key="/ai-blog" path="/ai-blog" element={withMainLayout(AIDailyBlog)} />,
    <Route key="/conversation-intelligence/recording/:id" path="/conversation-intelligence/recording/:id" element={withMainLayout(ConversationIntelligenceRecordingDetail)} />,

    // Microsite management
    <Route key="/microsite/wizard" path="/microsite/wizard" element={withMainLayout(MicrositeWizard)} />,
    <Route key="/microsite/editor" path="/microsite/editor" element={withMainLayout(MicrositeEditor)} />,
    <Route key="/carousel-builder" path="/carousel-builder" element={withMainLayout(CarouselBuilder)} />,

    // Team management
    <Route key="/team-members" path="/team-members" element={withMainLayout(TeamMembers)} />,
    <Route key="/team-members/:id" path="/team-members/:id" element={withMainLayout(TeamMemberProfile)} />,
    <Route key="/my-profile" path="/my-profile" element={withMainLayout(MyProfile)} />,
    <Route key="/my-permissions" path="/my-permissions" element={withMainLayout(MyPermissions)} />,

    // Admin (role-guarded)
    <Route key="/compliance" path="/compliance" element={withProtectedMainLayout(ComplianceDashboard, ['admin', 'site_admin', 'management'])} />,
    <Route key="/ops-manager" path="/ops-manager" element={withProtectedMainLayout(OpsManagerDashboard, ['admin', 'site_admin'])} />,
    <Route key="/admin/settings" path="/admin/settings" element={withProtectedMainLayout(AdminSettings, ['admin', 'site_admin'])} />,
    <Route key="/admin/permissions" path="/admin/permissions" element={withProtectedMainLayout(PermissionsPage, ['admin', 'site_admin'])} />,
    <Route key="/admin/domains" path="/admin/domains" element={withProtectedMainLayout(AdminCustomDomains, ['admin', 'site_admin'])} />,
    <Route key="/admin/employee-onboarding" path="/admin/employee-onboarding" element={withProtectedMainLayout(EmployeeOnboardingAdmin, ['admin', 'site_admin'])} />,
    <Route key="/admin/documents" path="/admin/documents" element={withProtectedMainLayout(AdminDocumentReviewQueue, ['admin', 'site_admin'])} />,
    <Route key="/admin/lead-assignment" path="/admin/lead-assignment" element={withProtectedMainLayout(LeadAssignmentConfig, ['admin', 'site_admin'])} />,
    <Route key="/admin/memory-staging" path="/admin/memory-staging" element={withProtectedMainLayout(MemoryStaging, ['admin', 'site_admin'])} />,
    <Route key="/admin" path="/admin" element={withProtectedMainLayout(AdminPanel, ['admin', 'site_admin'])} />,

    // Knowledge & Support
    <Route key="/knowledge-base" path="/knowledge-base" element={withMainLayout(KnowledgeBase)} />,
    <Route key="/support" path="/support" element={withMainLayout(Support)} />,

    // Dialer & Tools
    <Route key="/dialer" path="/dialer" element={withMainLayout(PowerDialer)} />,
    <Route key="/data-upload" path="/data-upload" element={withMainLayout(DataUpload)} />,
    <Route key="/compare-estimates" path="/compare-estimates" element={withMainLayout(EstimateComparison)} />,
    <Route key="/verizon-test" path="/verizon-test" element={withMainLayout(VerizonTest)} />,

    // Users (role-guarded)
    <Route key="/team/:userId" path="/team/:userId" element={withMainLayout(UserProfile)} />,
    <Route key="/users" path="/users" element={withProtectedMainLayout(Users, ['admin', 'site_admin', 'management'])} />,
    <Route key="/users/create" path="/users/create" element={withProtectedMainLayout(UserCreationWizard, ['admin', 'site_admin'])} />,
    <Route key="/users/bulk-upload" path="/users/bulk-upload" element={withProtectedMainLayout(UserBulkUpload, ['admin', 'site_admin'])} />,
    <Route key="/users/:id" path="/users/:id" element={withMainLayout(UserProfile)} />,

    // Process templates
    <Route key="/process-templates" path="/process-templates" element={withMainLayout(ProcessTemplates)} />,

    // Role-specific dashboards
    <Route key="/dashboard/loan-officer" path="/dashboard/loan-officer" element={withMainLayout(LODashboard)} />,
    <Route key="/dashboard/realtor" path="/dashboard/realtor" element={withMainLayout(RealtorDashboard)} />,

    // 403 Forbidden
    <Route key="forbidden" path="/forbidden" element={<LazyPage><Forbidden /></LazyPage>} />,

    // 404 catch-all — must be last
    <Route key="404" path="*" element={<LazyPage><NotFound /></LazyPage>} />,
  ];
}

// Export components for external use
export { LazyPage, PageLoader };
