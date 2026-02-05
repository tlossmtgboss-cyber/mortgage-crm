import { lazy, Suspense } from 'react';
import { Route, Navigate } from 'react-router-dom';
import { Capacitor } from '@capacitor/core';
import { isAuthenticatedSync as isAuthenticated } from '../utils/auth';
import { getUserEffectiveRole, getDefaultRouteForRole } from '../config/roleConfig';
import MainLayout from '../layouts/MainLayout';

// Landing/Auth pages (keep these as regular imports for faster initial load)
import LandingPage from '../pages/LandingPage';
import Registration from '../pages/Registration';
import AccountVerification from '../pages/AccountVerification';
import EmailVerificationSent from '../pages/EmailVerificationSent';
import Login from '../pages/Login';
import ForgotPassword from '../pages/ForgotPassword';
import ResetPassword from '../pages/ResetPassword';
import AdminOnboarding from '../pages/AdminOnboarding';
import ApplicationSubmitted from '../pages/ApplicationSubmitted';
import BuyerIntake from '../pages/BuyerIntake';

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

// Wrapper to handle lazy-loaded pages with suspense
function LazyPage({ children }) {
  return (
    <Suspense fallback={<PageLoader />}>
      {children}
    </Suspense>
  );
}

// Private route wrapper
function PrivateRoute({ children }) {
  if (!isAuthenticated()) {
    return <Navigate to="/login" />;
  }
  return children;
}

// Role-based redirect component for authenticated users
function RoleBasedRedirect() {
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
  return <Navigate to="/dashboard" replace />;
}

// =============================================================================
// LAZY LOADED PAGE COMPONENTS
// =============================================================================

// Core pages
const Dashboard = lazy(() => import('../pages/Dashboard'));
const CommandCenter = lazy(() => import('../pages/CommandCenter'));
const OnboardingWizard = lazy(() => import('../components/onboarding/OnboardingWizard'));
const Leads = lazy(() => import('../pages/Leads'));
const LeadDetail = lazy(() => import('../pages/LeadDetail'));
const Loans = lazy(() => import('../pages/Loans'));
const LoanDetail = lazy(() => import('../pages/LoanDetail'));
const Portfolio = lazy(() => import('../pages/Portfolio'));
const ClosedLoans = lazy(() => import('../pages/ClosedLoans'));
const PortfolioDetail = lazy(() => import('../pages/PortfolioDetail'));
const MumClientDetail = lazy(() => import('../pages/MumClientDetail'));
const YearOverYear = lazy(() => import('../pages/YearOverYear'));
const RateMonitor = lazy(() => import('../pages/RateMonitor'));
const Tasks = lazy(() => import('../pages/Tasks'));
const Calendar = lazy(() => import('../pages/Calendar'));
const Scorecard = lazy(() => import('../pages/Scorecard'));
const Assistant = lazy(() => import('../pages/Assistant'));
const ClientProfile = lazy(() => import('../pages/ClientProfile'));
const ReferralPartners = lazy(() => import('../pages/ReferralPartners'));
const ReferralPartnerDetail = lazy(() => import('../pages/ReferralPartnerDetail'));
const PartnerDashboardPortal = lazy(() => import('../pages/PartnerDashboardPortal'));
const PartnerClientDetail = lazy(() => import('../pages/PartnerClientDetail'));
const AIUnderwriter = lazy(() => import('../pages/AIUnderwriter'));
const GoalTracker = lazy(() => import('../pages/GoalTracker'));
const Coach = lazy(() => import('../pages/Coach'));
const ReconciliationCenter = lazy(() => import('../pages/ReconciliationCenter'));
const MergeCenter = lazy(() => import('../pages/MergeCenter'));
const Settings = lazy(() => import('../pages/Settings'));
const TeamMembers = lazy(() => import('../pages/TeamMembers'));
const TeamMemberProfile = lazy(() => import('../pages/TeamMemberProfile'));
const MyProfile = lazy(() => import('../pages/MyProfile'));
const MyPermissions = lazy(() => import('../pages/MyPermissions'));
const ComplianceDashboard = lazy(() => import('../pages/ComplianceDashboard'));
const AdminSettings = lazy(() => import('../pages/AdminSettings'));
const PermissionsPage = lazy(() => import('../pages/PermissionsPage'));
const AdminCustomDomains = lazy(() => import('../pages/AdminCustomDomains'));
const DataUpload = lazy(() => import('../pages/DataUpload'));
const EstimateComparison = lazy(() => import('../pages/EstimateComparison'));
const Users = lazy(() => import('../pages/Users'));
const UserProfile = lazy(() => import('../pages/UserProfile'));
const ProcessTemplates = lazy(() => import('../pages/ProcessTemplates'));
const ApplicationPreview = lazy(() => import('../pages/ApplicationPreview'));
const VerizonTest = lazy(() => import('../pages/VerizonTest'));

// Efficiency & Pipeline pages
const PipelineEfficiency = lazy(() => import('../pages/PipelineEfficiency'));
const StageEmployees = lazy(() => import('../pages/StageEmployees'));
const EmployeeLoans = lazy(() => import('../pages/EmployeeLoans'));
const TeamRoleEmployees = lazy(() => import('../pages/TeamRoleEmployees'));
const BottleneckLoans = lazy(() => import('../pages/BottleneckLoans'));

// AI & Voice pages
const AIReceptionistDashboard = lazy(() => import('../pages/AIReceptionistDashboard'));
const CallRoutingConfig = lazy(() => import('../pages/CallRoutingConfig'));
const VoiceOSDashboard = lazy(() => import('../pages/VoiceOSDashboard'));
const VideoOS = lazy(() => import('../pages/VideoOS'));
const VoiceAgentStudio = lazy(() => import('../components/voice/AgentStudio'));
const VoiceLiveCallsMonitor = lazy(() => import('../components/voice/LiveCallsMonitor'));
const VoiceAgentBuilder = lazy(() => import('../components/voice/AgentBuilder'));
const VoiceCallQueueDashboard = lazy(() => import('../components/voice/CallQueueDashboard'));
const VoiceConferenceRoomDashboard = lazy(() => import('../components/voice/ConferenceRoomDashboard'));
const VoiceIVRMenuDashboard = lazy(() => import('../components/voice/IVRMenuDashboard'));
const VoiceHoldMusicDashboard = lazy(() => import('../components/voice/HoldMusicDashboard'));
const VoiceTalkToAgentPage = lazy(() => import('../components/voice/TalkToAgentPage'));
const VoiceCallAnalyticsDashboard = lazy(() => import('../components/voice/CallAnalyticsDashboard'));
const CallIntelligencePage = lazy(() => import('../pages/CallIntelligencePage'));
const MobileCallIntelligencePage = lazy(() => import('../pages/MobileCallIntelligencePage'));
const AILandingPage = lazy(() => import('../pages/AILandingPage'));

// Workflow & Analytics pages
const WorkflowDashboard = lazy(() => import('../pages/WorkflowDashboard'));
const WorkflowStagePage = lazy(() => import('../pages/WorkflowStagePage'));
const MarketDashboard = lazy(() => import('../pages/MarketDashboard'));
const MorningCheckin = lazy(() => import('../pages/MorningCheckin'));
const PartnerROIDashboard = lazy(() => import('../pages/PartnerROIDashboard'));
const ProfitabilityDashboard = lazy(() => import('../pages/ProfitabilityDashboard'));
const UsageIntelligenceDashboard = lazy(() => import('../pages/UsageIntelligenceDashboard'));
const ScenarioModeling = lazy(() => import('../pages/ScenarioModeling'));
const DecisionLab = lazy(() => import('../pages/DecisionLab'));
const MortgageCalculator = lazy(() => import('../pages/MortgageCalculator'));
const AllInOneLoan = lazy(() => import('../pages/AllInOneLoan'));
const PipelineProbability = lazy(() => import('../pages/PipelineProbability'));
const SLASettings = lazy(() => import('../pages/SLASettings'));
const EmployeeOnboardingAdmin = lazy(() => import('../pages/EmployeeOnboardingAdmin'));
const AcceptInvite = lazy(() => import('../pages/AcceptInvite'));
const MortgagePlannerQuestionnaire = lazy(() => import('../pages/MortgagePlannerQuestionnaire'));
const KnowledgeBase = lazy(() => import('../pages/KnowledgeBase'));
const Support = lazy(() => import('../pages/Support'));
const AriaVoiceApp = lazy(() => import('../pages/AriaVoiceApp'));
const PowerDialer = lazy(() => import('../pages/PowerDialer'));
const UserCreationWizard = lazy(() => import('../pages/UserCreationWizard'));
const UserBulkUpload = lazy(() => import('../pages/UserBulkUpload'));
const ActivateAccount = lazy(() => import('../pages/ActivateAccount'));
const MeetingRoom = lazy(() => import('../pages/MeetingRoom'));
const OAuthCallback = lazy(() => import('../pages/OAuthCallback'));
const WorkflowStatusDetail = lazy(() => import('../pages/WorkflowStatusDetail'));
const CommunicationIntelligence = lazy(() => import('../pages/CommunicationIntelligence'));
const AIOutreach = lazy(() => import('../pages/AIOutreach'));
const ConversationIntelligence = lazy(() => import('../pages/ConversationIntelligence'));
const ConversationIntelligenceRecordingDetail = lazy(() => import('../pages/ConversationIntelligenceRecordingDetail'));
const SmartDocs = lazy(() => import('../pages/SmartDocs'));
const SmartDocsClientDetail = lazy(() => import('../pages/SmartDocsClientDetail'));
const SmartDocsDashboard = lazy(() => import('../pages/SmartDocsDashboard'));
const AIDailyBlog = lazy(() => import('../pages/AIDailyBlog'));
const AvatarStudio = lazy(() => import('../pages/AvatarStudio'));
const PublicBooking = lazy(() => import('../pages/PublicBooking'));
const ApplicationAnalytics = lazy(() => import('../pages/ApplicationAnalytics'));

// Application pages
const BorrowerApplication = lazy(() => import('../pages/BorrowerApplication'));
// AdaptiveURLA is available but not currently routed
// const AdaptiveURLA = lazy(() => import('../pages/AdaptiveURLA'));
const PurchaseApplication = lazy(() => import('../pages/PurchaseApplication'));
const RefinanceApplication = lazy(() => import('../pages/RefinanceApplication'));
const PurchasePreQualForm = lazy(() => import('../pages/PurchasePreQualForm'));
const NewPurchaseApplication = lazy(() => import('../pages/applications/NewPurchaseApplication'));
const NewRefinanceApplication = lazy(() => import('../pages/applications/NewRefinanceApplication'));
const ApplicationDemo = lazy(() => import('../pages/applications/ApplicationDemo'));
const CoborrowerApplication = lazy(() => import('../pages/CoborrowerApplication'));
const BorrowerLogin = lazy(() => import('../pages/BorrowerLogin'));
const ApplyVerify = lazy(() => import('../pages/ApplyVerify'));
const BorrowerOAuthCallback = lazy(() => import('../pages/BorrowerOAuthCallback'));
const BorrowerPortal = lazy(() => import('../pages/BorrowerPortal'));
const SharedCalculator = lazy(() => import('../pages/SharedCalculator'));
const CalculatorDashboard = lazy(() => import('../pages/CalculatorDashboard'));
const PortalTest = lazy(() => import('../pages/PortalTest'));

// Microsite pages
const ThemeRenderer = lazy(() => import('../pages/microsites/ThemeRenderer'));
const ThemePreview = lazy(() => import('../pages/microsites/ThemePreview'));
const MicrositePreview = lazy(() => import('../pages/microsites/MicrositePreview'));
const MicrositeWizard = lazy(() => import('../components/microsites/MicrositeWizard'));
const MicrositeEditor = lazy(() => import('../pages/MicrositeEditor'));

// Dashboard pages
const LODashboard = lazy(() => import('../pages/LODashboard'));
const RealtorDashboard = lazy(() => import('../pages/RealtorDashboard'));
const RealtorPortal = lazy(() => import('../pages/RealtorPortal'));
const AdminPanel = lazy(() => import('../pages/AdminPanel'));
const AgentDashboard = lazy(() => import('../pages/AgentDashboard'));
const AgentProfile = lazy(() => import('../pages/AgentProfile'));
const AcquisitionDashboard = lazy(() => import('../pages/AcquisitionDashboard'));
const Marketing = lazy(() => import('../pages/Marketing'));
const CarouselBuilder = lazy(() => import('../pages/CarouselBuilder/CarouselBuilderPage'));

// Master Manager pages
const MasterManagerCapacity = lazy(() => import('../pages/MasterManager/CapacityCommandCenter'));
const MasterManagerRecruiting = lazy(() => import('../pages/MasterManager/RecruitingDashboard'));
const RecruitDetail = lazy(() => import('../pages/MasterManager/RecruitDetail'));
const PartnerRecruitingDashboard = lazy(() => import('../pages/PartnerRecruiting/PartnerRecruitingDashboard'));
const PartnerRecruitDetail = lazy(() => import('../pages/PartnerRecruiting/PartnerRecruitDetail'));
const AgentGym = lazy(() => import('../pages/AgentGym'));
const AgentGovernanceSettings = lazy(() => import('../pages/AgentGovernanceSettings'));

// Settings pages
const SmartSchedulerSettings = lazy(() => import('../pages/SmartSchedulerSettings'));
const EmailIntegrationSettings = lazy(() => import('../pages/EmailIntegrationSettings'));
const UserProfileSettings = lazy(() => import('../pages/UserProfileSettings'));
const DocumentUploadSettings = lazy(() => import('../pages/DocumentUploadSettings'));
const LeadCaptureSettings = lazy(() => import('../pages/LeadCaptureSettings'));
const ClientPortalSettings = lazy(() => import('../pages/ClientPortalSettings'));
const CommunicationPreferences = lazy(() => import('../pages/CommunicationPreferences'));
const IntegrationSettings = lazy(() => import('../pages/IntegrationSettings'));
const SalesforceIntegrationPage = lazy(() => import('../pages/SalesforceIntegrationPage'));
const TwilioSetup = lazy(() => import('../pages/settings/TwilioSetup'));
const StateRecordingRules = lazy(() => import('../pages/settings/StateRecordingRules'));
const TwilioStatusCallbacks = lazy(() => import('../pages/settings/TwilioStatusCallbacks'));
const QuoteLanguagePresets = lazy(() => import('../pages/settings/QuoteLanguagePresets'));
const APIKeysSettings = lazy(() => import('../pages/APIKeysSettings'));
const CompanyBrandingSettings = lazy(() => import('../pages/CompanyBrandingSettings'));
const AccountManagement = lazy(() => import('../pages/AccountManagement'));

// Portal pages
const PURLDashboard = lazy(() => import('../pages/PURLDashboard'));
const PURLApplication = lazy(() => import('../pages/PURLApplication'));
const PortalContainer = lazy(() => import('../pages/portal/PortalContainer'));
const LoanPortalRedirect = lazy(() => import('../components/Portal/LoanPortalRedirect'));
const AdminDocumentReviewQueue = lazy(() => import('../pages/AdminDocumentReviewQueue'));
const IncomeCalculatorPopout = lazy(() => import('../pages/IncomeCalculatorPopout'));
const IntakeEngine = lazy(() => import('../components/intake/IntakeEngine'));
const ListingPortalTransactions = lazy(() => import('../pages/ListingPortalTransactions'));
const ListingPortalTransactionDetail = lazy(() => import('../pages/ListingPortalTransactionDetail'));
const ListingAgentPortal = lazy(() => import('../pages/ListingAgentPortal'));
const RecruitPortal = lazy(() => import('../pages/RecruitPortal/RecruitPortal'));
const DISCAssessment = lazy(() => import('../pages/DISCAssessment'));
const PrivacyPolicy = lazy(() => import('../pages/PrivacyPolicy'));
const TermsOfService = lazy(() => import('../pages/TermsOfService'));
const LiveCallWhisper = lazy(() => import('../pages/LiveCallWhisper'));
const ProductionPredictor = lazy(() => import('../pages/ProductionPredictor'));
const ProductionPredictorDetail = lazy(() => import('../pages/ProductionPredictorDetail'));
const DealAlerts = lazy(() => import('../pages/DealAlerts'));

// Accounting System
const AccountingDashboard = lazy(() => import('../pages/accounting/AccountingDashboard'));
const ChartOfAccounts = lazy(() => import('../pages/accounting/ChartOfAccounts'));
const JournalEntries = lazy(() => import('../pages/accounting/JournalEntries'));
const ARCustomerList = lazy(() => import('../pages/accounting/ar/CustomerList'));
const ARInvoiceList = lazy(() => import('../pages/accounting/ar/InvoiceList'));
const ARPaymentList = lazy(() => import('../pages/accounting/ar/PaymentList'));
const ARAgingReport = lazy(() => import('../pages/accounting/ar/AgingReport'));
const APVendorList = lazy(() => import('../pages/accounting/ap/VendorList'));
const APBillList = lazy(() => import('../pages/accounting/ap/BillList'));
const APPayBills = lazy(() => import('../pages/accounting/ap/PayBills'));
const APAgingReport = lazy(() => import('../pages/accounting/ap/AgingReport'));
const BankAccounts = lazy(() => import('../pages/accounting/banking/BankAccounts'));
const PlaidConnect = lazy(() => import('../pages/accounting/banking/PlaidConnect'));
const BankTransactions = lazy(() => import('../pages/accounting/banking/BankTransactions'));
const BankReconciliation = lazy(() => import('../pages/accounting/banking/BankReconciliation'));
const ProfitLoss = lazy(() => import('../pages/accounting/reports/ProfitLoss'));
const BalanceSheet = lazy(() => import('../pages/accounting/reports/BalanceSheet'));
const CashFlow = lazy(() => import('../pages/accounting/reports/CashFlow'));
const TrialBalance = lazy(() => import('../pages/accounting/reports/TrialBalance'));
const BudgetList = lazy(() => import('../pages/accounting/budgets/BudgetList'));
const BudgetVariance = lazy(() => import('../pages/accounting/budgets/BudgetVariance'));

// Portal Components
const ActiveLoanPortalComplete = lazy(() => import('../components/Portal/ActiveLoanPortalComplete'));
const PartnerPortalView = lazy(() => import('../components/Portal/PartnerPortalView'));
const PerenniaClientPortalUltimate = lazy(() => import('../components/Portal/PerenniaClientPortalUltimate'));
const TotalCostAnalysis = lazy(() => import('../components/Portal/TotalCostAnalysis'));

// E-Signature Components
const FieldPlacementBuilder = lazy(() => import('../components/esign/FieldPlacementBuilder'));
const SigningSession = lazy(() => import('../pages/esign/SigningSession'));

// =============================================================================
// ROUTE CONFIGURATION
// =============================================================================

/**
 * Generates all application routes
 * @param {Object} layoutProps - Props to pass to MainLayout (toggle functions, open states, task counts)
 * @returns {JSX.Element[]} Array of Route elements
 */
export function getRoutes(layoutProps) {
  const {
    toggleAssistant,
    toggleCoach,
    toggleTaskSidebar,
    assistantOpen,
    coachOpen,
    taskSidebarOpen,
    taskCounts,
    // setCoachOpen is available but not currently used in route generation
  } = layoutProps;

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

  // Helper for private route without MainLayout
  const privateOnly = (Component) => (
    <PrivateRoute>
      <LazyPage><Component /></LazyPage>
    </PrivateRoute>
  );

  return [
    // =============================================================================
    // PUBLIC ROUTES
    // =============================================================================

    // Landing page (redirects to Aria on mobile)
    <Route
      key="/"
      path="/"
      element={
        (Capacitor.isNativePlatform() || window.location.hostname.startsWith('192.168.'))
          ? <Navigate to="/aria" />
          : <LandingPage />
      }
    />,

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
    <Route key="/decision-lab" path="/decision-lab" element={<LazyPage><DecisionLab /></LazyPage>} />,
    <Route key="/mortgage-calculator" path="/mortgage-calculator" element={<LazyPage><MortgageCalculator /></LazyPage>} />,
    <Route key="/estimate-comparison" path="/estimate-comparison" element={<LazyPage><EstimateComparison /></LazyPage>} />,
    <Route key="/aria" path="/aria" element={<LazyPage><AriaVoiceApp /></LazyPage>} />,
    <Route key="/privacy-policy" path="/privacy-policy" element={<LazyPage><PrivacyPolicy /></LazyPage>} />,
    <Route key="/terms-of-service" path="/terms-of-service" element={<LazyPage><TermsOfService /></LazyPage>} />,

    // Public portals
    <Route key="/realtor-portal" path="/realtor-portal" element={<LazyPage><RealtorPortal /></LazyPage>} />,
    <Route key="/listing-agent-portal" path="/listing-agent-portal" element={<LazyPage><ListingAgentPortal /></LazyPage>} />,
    <Route key="/recruit-portal/:slug" path="/recruit-portal/:slug" element={<LazyPage><RecruitPortal /></LazyPage>} />,
    <Route key="/join/:slug" path="/join/:slug" element={<LazyPage><RecruitPortal /></LazyPage>} />,
    <Route key="/disc-assessment/:token" path="/disc-assessment/:token" element={<LazyPage><DISCAssessment /></LazyPage>} />,
    <Route key="/assessment/disc" path="/assessment/disc" element={<LazyPage><DISCAssessment /></LazyPage>} />,
    <Route key="/invite/accept/:token" path="/invite/accept/:token" element={<LazyPage><AcceptInvite /></LazyPage>} />,
    <Route key="/accept-invite" path="/accept-invite" element={<LazyPage><AcceptInvite /></LazyPage>} />,
    <Route key="/activate" path="/activate" element={<LazyPage><ActivateAccount /></LazyPage>} />,
    <Route key="/meeting/:roomCode" path="/meeting/:roomCode" element={<LazyPage><MeetingRoom /></LazyPage>} />,
    <Route key="/book/:slug" path="/book/:slug" element={<LazyPage><PublicBooking /></LazyPage>} />,
    <Route key="/portal-test" path="/portal-test" element={<LazyPage><PortalTest /></LazyPage>} />,

    // Microsite routes
    <Route key="/lo/:slug" path="/lo/:slug" element={<LazyPage><ThemeRenderer /></LazyPage>} />,
    <Route key="/lo/:slug/:pageSlug" path="/lo/:slug/:pageSlug" element={<LazyPage><ThemeRenderer /></LazyPage>} />,
    <Route key="/microsite/loan-officer/:userId" path="/microsite/loan-officer/:userId" element={<LazyPage><ThemeRenderer /></LazyPage>} />,
    <Route key="/microsite/preview" path="/microsite/preview" element={<LazyPage><MicrositePreview /></LazyPage>} />,
    <Route key="/preview/theme/:themeSlug" path="/preview/theme/:themeSlug" element={<LazyPage><ThemePreview /></LazyPage>} />,

    // Borrower application routes
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
    <Route key="/apply/:token" path="/apply/:token" element={<LazyPage><BorrowerApplication /></LazyPage>} />,
    <Route key="/coborrower/:token" path="/coborrower/:token" element={<LazyPage><CoborrowerApplication /></LazyPage>} />,
    <Route key="/borrower-portal/:token" path="/borrower-portal/:token" element={<LazyPage><BorrowerPortal /></LazyPage>} />,
    <Route key="/borrower-portal" path="/borrower-portal" element={<LazyPage><BorrowerPortal /></LazyPage>} />,
    <Route key="/shared/calculator/:shareToken" path="/shared/calculator/:shareToken" element={<LazyPage><SharedCalculator /></LazyPage>} />,
    <Route key="/calculators" path="/calculators" element={<LazyPage><CalculatorDashboard /></LazyPage>} />,
    <Route key="/calculator-dashboard" path="/calculator-dashboard" element={<LazyPage><CalculatorDashboard /></LazyPage>} />,
    <Route key="/all-in-one-loan" path="/all-in-one-loan" element={<LazyPage><AllInOneLoan /></LazyPage>} />,

    // Portal routes
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

    // =============================================================================
    // PROTECTED ROUTES WITH MAIN LAYOUT
    // =============================================================================

    // Onboarding
    <Route key="/onboarding" path="/onboarding" element={<PrivateRoute><Navigate to="/onboarding/welcome" replace /></PrivateRoute>} />,
    <Route key="/onboarding/:step" path="/onboarding/:step" element={withMainLayout(OnboardingWizard)} />,

    // AI Landing
    <Route key="/ai" path="/ai" element={privateOnly(AILandingPage)} />,

    // Dashboard & Command Center
    <Route key="/dashboard" path="/dashboard" element={withMainLayout(Dashboard)} />,
    <Route key="/command-center" path="/command-center" element={withMainLayout(CommandCenter)} />,
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
    <Route key="/usage-intelligence" path="/usage-intelligence" element={withMainLayout(UsageIntelligenceDashboard)} />,
    <Route key="/profitability/scenarios" path="/profitability/scenarios" element={withMainLayout(ScenarioModeling)} />,
    <Route key="/pipeline-probability" path="/pipeline-probability" element={withMainLayout(PipelineProbability)} />,
    <Route key="/sla-tracking" path="/sla-tracking" element={withMainLayout(SLASettings)} />,

    // Leads & Loans
    <Route key="/leads" path="/leads" element={withMainLayout(Leads)} />,
    <Route key="/leads/:id" path="/leads/:id" element={withMainLayout(LeadDetail)} />,
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
    <Route key="/calendar" path="/calendar" element={withMainLayout(Calendar)} />,

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
    <Route key="/master-manager/recruiting" path="/master-manager/recruiting" element={withMainLayout(MasterManagerRecruiting)} />,
    <Route key="/master-manager/recruiting/:candidateId" path="/master-manager/recruiting/:candidateId" element={withMainLayout(RecruitDetail)} />,
    <Route key="/partner-recruiting" path="/partner-recruiting" element={withMainLayout(PartnerRecruitingDashboard)} />,
    <Route key="/partner-recruiting/:partnerId" path="/partner-recruiting/:partnerId" element={withMainLayout(PartnerRecruitDetail)} />,

    // Settings
    <Route key="/settings" path="/settings" element={withMainLayout(Settings)} />,
    <Route key="/settings/smart-scheduler" path="/settings/smart-scheduler" element={withMainLayout(SmartSchedulerSettings)} />,
    <Route key="/settings/email-integration" path="/settings/email-integration" element={withMainLayout(EmailIntegrationSettings)} />,
    <Route key="/settings/user-profile" path="/settings/user-profile" element={withMainLayout(UserProfileSettings)} />,
    <Route key="/settings/document-upload" path="/settings/document-upload" element={withMainLayout(DocumentUploadSettings)} />,
    <Route key="/settings/lead-capture" path="/settings/lead-capture" element={withMainLayout(LeadCaptureSettings)} />,
    <Route key="/settings/client-portal" path="/settings/client-portal" element={withMainLayout(ClientPortalSettings)} />,
    <Route key="/settings/communication" path="/settings/communication" element={withMainLayout(CommunicationPreferences)} />,
    <Route key="/settings/integrations" path="/settings/integrations" element={withMainLayout(IntegrationSettings)} />,
    <Route key="/settings/integrations/salesforce" path="/settings/integrations/salesforce" element={withMainLayout(SalesforceIntegrationPage)} />,
    <Route key="/integrations" path="/integrations" element={withMainLayout(IntegrationSettings)} />,
    <Route key="/settings/twilio" path="/settings/twilio" element={withMainLayout(TwilioSetup)} />,
    <Route key="/settings/state-recording-rules" path="/settings/state-recording-rules" element={withMainLayout(StateRecordingRules)} />,
    <Route key="/settings/twilio-status-callbacks" path="/settings/twilio-status-callbacks" element={withMainLayout(TwilioStatusCallbacks)} />,
    <Route key="/settings/quote-language-presets" path="/settings/quote-language-presets" element={withMainLayout(QuoteLanguagePresets)} />,
    <Route key="/settings/api-keys" path="/settings/api-keys" element={withMainLayout(APIKeysSettings)} />,
    <Route key="/settings/company-branding" path="/settings/company-branding" element={withMainLayout(CompanyBrandingSettings)} />,
    <Route key="/settings/account-management" path="/settings/account-management" element={withMainLayout(AccountManagement)} />,

    // Client & Partner management
    <Route key="/client-portals" path="/client-portals" element={withMainLayout(PURLDashboard)} />,
    <Route key="/client/:type/:id" path="/client/:type/:id" element={withMainLayout(ClientProfile)} />,
    <Route key="/referral-partners" path="/referral-partners" element={withMainLayout(ReferralPartners)} />,
    <Route key="/referral-partners/:id" path="/referral-partners/:id" element={withMainLayout(ReferralPartnerDetail)} />,
    <Route key="/partner-portal/:id" path="/partner-portal/:id" element={privateOnly(PartnerDashboardPortal)} />,
    <Route key="/partner-portal/:partnerId/client/:clientId" path="/partner-portal/:partnerId/client/:clientId" element={privateOnly(PartnerClientDetail)} />,

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
    <Route key="/avatar-studio" path="/avatar-studio" element={withMainLayout(AvatarStudio)} />,
    <Route key="/conversation-intelligence" path="/conversation-intelligence" element={withMainLayout(ConversationIntelligence)} />,
    <Route key="/call-intelligence" path="/call-intelligence" element={withMainLayout(CallIntelligencePage)} />,
    <Route key="/mobile/call-intelligence" path="/mobile/call-intelligence" element={privateOnly(MobileCallIntelligencePage)} />,
    <Route key="/live-call-whisper" path="/live-call-whisper" element={withMainLayout(LiveCallWhisper)} />,
    <Route key="/production-predictor" path="/production-predictor" element={withMainLayout(ProductionPredictor)} />,
    <Route key="/production-predictor/detail" path="/production-predictor/detail" element={withMainLayout(ProductionPredictorDetail)} />,
    <Route key="/deal-alerts" path="/deal-alerts" element={withMainLayout(DealAlerts)} />,

    // Smart Docs
    <Route key="/smart-docs" path="/smart-docs" element={withMainLayout(SmartDocs)} />,
    <Route key="/smart-docs/dashboard" path="/smart-docs/dashboard" element={withMainLayout(SmartDocsDashboard)} />,
    <Route key="/smart-docs/client/:loanId" path="/smart-docs/client/:loanId" element={withMainLayout(SmartDocsClientDetail)} />,

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

    // Admin
    <Route key="/compliance" path="/compliance" element={withMainLayout(ComplianceDashboard)} />,
    <Route key="/admin/settings" path="/admin/settings" element={withMainLayout(AdminSettings)} />,
    <Route key="/admin/permissions" path="/admin/permissions" element={withMainLayout(PermissionsPage)} />,
    <Route key="/admin/domains" path="/admin/domains" element={withMainLayout(AdminCustomDomains)} />,
    <Route key="/admin/employee-onboarding" path="/admin/employee-onboarding" element={withMainLayout(EmployeeOnboardingAdmin)} />,
    <Route key="/admin/documents" path="/admin/documents" element={withMainLayout(AdminDocumentReviewQueue)} />,
    <Route key="/admin" path="/admin" element={withMainLayout(AdminPanel)} />,

    // Knowledge & Support
    <Route key="/knowledge-base" path="/knowledge-base" element={withMainLayout(KnowledgeBase)} />,
    <Route key="/support" path="/support" element={withMainLayout(Support)} />,

    // Dialer & Tools
    <Route key="/dialer" path="/dialer" element={withMainLayout(PowerDialer)} />,
    <Route key="/data-upload" path="/data-upload" element={withMainLayout(DataUpload)} />,
    <Route key="/compare-estimates" path="/compare-estimates" element={withMainLayout(EstimateComparison)} />,
    <Route key="/verizon-test" path="/verizon-test" element={withMainLayout(VerizonTest)} />,

    // Users
    <Route key="/team/:userId" path="/team/:userId" element={withMainLayout(UserProfile)} />,
    <Route key="/users" path="/users" element={withMainLayout(Users)} />,
    <Route key="/users/create" path="/users/create" element={withMainLayout(UserCreationWizard)} />,
    <Route key="/users/bulk-upload" path="/users/bulk-upload" element={withMainLayout(UserBulkUpload)} />,
    <Route key="/users/:id" path="/users/:id" element={withMainLayout(UserProfile)} />,

    // Process templates
    <Route key="/process-templates" path="/process-templates" element={withMainLayout(ProcessTemplates)} />,

    // Role-specific dashboards
    <Route key="/dashboard/loan-officer" path="/dashboard/loan-officer" element={withMainLayout(LODashboard)} />,
    <Route key="/dashboard/realtor" path="/dashboard/realtor" element={withMainLayout(RealtorDashboard)} />,
  ];
}

// Export components for external use
export { PrivateRoute, RoleBasedRedirect, LazyPage, PageLoader };
