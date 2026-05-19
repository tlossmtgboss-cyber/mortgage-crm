import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import AddressAutocomplete from '../components/AddressAutocomplete';
import EmployerAutocomplete from '../components/EmployerAutocomplete';
import MortgageStatementUpload from '../components/MortgageStatementUpload';
import './AdaptiveURLA.css';

import {
  STAGES,
  DECLARATION_QUESTIONS,
  getRequiredDocuments,
  // Shared components
  Icon,
  ProgressHeader,
  DocumentsSidebar,
  SaveProgressModal,
  SubmissionSuccess,
  MicroWinToast,
  AccountStage,
  DeclarationsStage,
  ScheduleStage,
  US_STATES,
  getApiUrl,
  shouldShowQuestion,
  getVisibleQuestions,
  calculateProgress,
  getStageMicroWin,
  getEnabledStages,
  getEnabledQuestions,
  buildRedirectUrl,
  buildNeedsList,
  // Stage components
  ProfileStage,
  IncomeStage,
  PropertyStage,
  GoalsStage,
  ReviewStage,
  PlanningStage,
} from './refinance-application';

/**
 * RefinanceApplication - Thin orchestrator for the refinance application flow.
 * Owns all state and handlers; delegates rendering to extracted stage components.
 *
 * 9-Stage Flow: Account -> Declarations -> Profile -> Income -> Property ->
 *               Goals -> Review -> Planning -> Schedule
 */
function RefinanceApplication() {
  const { token } = useParams();
  const navigate = useNavigate();
  const isDemoMode = token === 'start';

  const API_URL = getApiUrl();

  // ─── Core state ───
  const [currentStage, setCurrentStage] = useState('account');
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const [declarations, setDeclarations] = useState({});
  const [profileData, setProfileData] = useState({});
  const [incomeData, setIncomeData] = useState({});
  const [incomeStep, setIncomeStep] = useState(1);
  const [propertyData, setPropertyData] = useState({});
  const [statementParsed, setStatementParsed] = useState(false);
  const [goalsData, setGoalsData] = useState({});
  const [planningData, setPlanningData] = useState({
    mortgagePriorities: [], personalGoals: [], financialPhilosophy: '',
    professionalNetwork: [], taxDeferredRetirement: '',
  });
  const [needsList, setNeedsList] = useState([]);
  const [showMicroWin, setShowMicroWin] = useState(false);
  const [microWinMessage, setMicroWinMessage] = useState('');
  const [isAnimating, setIsAnimating] = useState(false);
  const [selectedTimeSlot, setSelectedTimeSlot] = useState(null);


  // ─── Consent & schedule state ───
  const [eConsentAgreed, setEConsentAgreed] = useState(false);
  const [creditAuthAgreed, setCreditAuthAgreed] = useState(false);
  const [scheduleStep, setScheduleStep] = useState(1);
  const [calendarAssignment, setCalendarAssignment] = useState(null);
  const [bookingSlots, setBookingSlots] = useState([]);
  const [bookingSelectedDate, setBookingSelectedDate] = useState(null);
  const [bookingSelectedTime, setBookingSelectedTime] = useState('');
  const [bookingWeekStart, setBookingWeekStart] = useState(() => { const d = new Date(); d.setHours(0,0,0,0); return d; });
  const [bookingLoading, setBookingLoading] = useState(false);
  const [bookingConfirmed, setBookingConfirmed] = useState(false);
  const [bookingError, setBookingError] = useState(null);

  // ─── Submission state ───
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [showSubmissionSuccess, setShowSubmissionSuccess] = useState(false);
  const [portalUrlForRedirect, setPortalUrlForRedirect] = useState(null);
  const portalUrlRef = useRef(null);

  // ─── Account & save state ───
  const [userAccount, setUserAccount] = useState({ email: '', authMethod: null, isLoggedIn: false });
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [saveEmail, setSaveEmail] = useState('');
  const [lastSavedAt, setLastSavedAt] = useState(null);

  // ─── Co-borrower state ───
  const [coBorrowerData, setCoBorrowerData] = useState({});
  const [coBorrowerIncomeData, setCoBorrowerIncomeData] = useState({});
  const [currentIncomeBorrower, setCurrentIncomeBorrower] = useState(1);
  const [emailSending, setEmailSending] = useState(false);
  const [emailSent, setEmailSent] = useState(false);

  // ─── Config state ───
  const [applicationConfig, setApplicationConfig] = useState(null);
  const [configLoaded, setConfigLoaded] = useState(false);

  // ─── Follow-up state (disabled) ───
  const [followupAnswers, setFollowupAnswers] = useState({});
  const [activeFollowup, setActiveFollowup] = useState(null);
  const clearFollowup = () => {};
  const checkForFollowup = async () => null;

  // ═══════════════════════════════════════
  // Effects
  // ═══════════════════════════════════════

  useEffect(() => { portalUrlRef.current = portalUrlForRedirect; }, [portalUrlForRedirect]);

  // Load application config
  useEffect(() => {
    const loadConfig = async () => {
      try {
        const response = await fetch(`${API_URL}/api/v1/settings/application-slides`);
        if (response.ok) setApplicationConfig(await response.json());
      } catch (e) { console.log('Using default application configuration'); }
      finally { setConfigLoaded(true); }
    };
    loadConfig();
  }, [API_URL]);

  // Derived values
  const enabledStages = getEnabledStages(applicationConfig, STAGES);
  const enabledQuestions = getEnabledQuestions(applicationConfig, DECLARATION_QUESTIONS);
  const visibleStages = enabledStages.filter(s => !s.hideFromProgress);

  // Auto-redirect after submission
  useEffect(() => {
    if (showSubmissionSuccess) {
      const timer = setTimeout(() => {
        let redirectUrl = portalUrlRef.current || buildRedirectUrl(token);
        if (window.parent !== window) window.parent.postMessage({ type: 'APPLICATION_SUBMITTED', portalUrl: redirectUrl }, window.location.origin);
        window.location.href = redirectUrl;
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [showSubmissionSuccess]);

  // Fetch calendar assignment
  useEffect(() => {
    const fetchCal = async () => {
      try {
        const r = await fetch(`${API_URL}/api/v1/calendar-assignments/refinance_application`);
        if (r.ok) setCalendarAssignment(await r.json());
      } catch (e) { console.error('Error fetching calendar assignment:', e); }
    };
    fetchCal();
  }, [API_URL]);

  // localStorage auto-save
  const STORAGE_KEY = `refinance_application_${token || 'anonymous'}`;

  useEffect(() => {
    if (currentStage === 'account') return;
    const sanitizedProfile = { ...profileData }; delete sanitizedProfile.ssn;
    const sanitizedCo = { ...coBorrowerData }; delete sanitizedCo.ssn;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        declarations, profileData: sanitizedProfile, incomeData, propertyData, goalsData,
        planningData, coBorrowerData: sanitizedCo, coBorrowerIncomeData, currentStage, userAccount,
        savedAt: new Date().toISOString(),
      }));
      setLastSavedAt(new Date());
    } catch (e) { console.error('Error saving to localStorage:', e); }
  }, [declarations, profileData, incomeData, propertyData, goalsData, planningData, coBorrowerData, coBorrowerIncomeData, currentStage, userAccount, STORAGE_KEY]);

  // Load saved progress
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const data = JSON.parse(saved);
        if (data.userAccount?.isLoggedIn) {
          setDeclarations(data.declarations || {}); setProfileData(data.profileData || {});
          setIncomeData(data.incomeData || {}); setPropertyData(data.propertyData || {});
          setGoalsData(data.goalsData || {}); setPlanningData(data.planningData || {});
          setCoBorrowerData(data.coBorrowerData || {}); setCoBorrowerIncomeData(data.coBorrowerIncomeData || {});
          setUserAccount(data.userAccount || {}); setCurrentStage(data.currentStage || 'declarations');
        }
      }
    } catch (e) { console.error('Error loading saved progress:', e); }
  }, [STORAGE_KEY]);

  // Update needs list from declarations
  useEffect(() => {
    setNeedsList(buildNeedsList(declarations, 'refinance'));
  }, [declarations]);

  // ═══════════════════════════════════════
  // Handlers
  // ═══════════════════════════════════════

  const showMicroWinAnimation = (message) => {
    setMicroWinMessage(message); setShowMicroWin(true);
    setTimeout(() => setShowMicroWin(false), 2500);
  };

  const getProgress = useCallback(() => {
    if (currentStage === 'account') return 0;
    return calculateProgress(currentStage, currentQuestionIndex, visibleStages, enabledQuestions);
  }, [currentStage, currentQuestionIndex, visibleStages, enabledQuestions]);

  const handleMortgageStatementData = useCallback((formData) => {
    setPropertyData(prev => ({
      ...prev,
      address: formData.address || prev.address, street: formData.street || prev.street,
      city: formData.city || prev.city, state: formData.state || prev.state, zip: formData.zip || prev.zip,
      mortgageBalance: formData.mortgageBalance || prev.mortgageBalance,
      monthlyPayment: formData.monthlyPayment || prev.monthlyPayment,
      currentRate: formData.currentRate || prev.currentRate,
      loanDate: formData.loanDate || prev.loanDate,
      currentTerm: formData.currentTerm ? String(formData.currentTerm) : prev.currentTerm,
      lenderName: formData.lenderName || prev.lenderName, loanNumber: formData.loanNumber || prev.loanNumber,
      principalAndInterest: formData.principalAndInterest || prev.principalAndInterest,
      propertyTaxes: formData.propertyTaxes || prev.propertyTaxes,
      insurance: formData.insurance || prev.insurance, pmi: formData.pmi || prev.pmi,
      hoa: formData.hoa || prev.hoa, escrowPayment: formData.escrowPayment || prev.escrowPayment,
    }));
    setStatementParsed(true);
  }, []);

  const handleSaveProgressEmail = async () => {
    if (!saveEmail || !saveEmail.includes('@')) return;
    try {
      setUserAccount(prev => ({ ...prev, email: saveEmail }));
      setShowSaveModal(false); setSaveEmail('');
      showMicroWinAnimation('Progress saved! Check your email for a link to continue later.');
    } catch (e) { console.error('Error saving progress:', e); }
  };

  const handleSubmitApplication = async () => {
    setIsSubmitting(true); setSubmitError(null);
    try {
      let loId = null;
      if (token && token !== 'start') { const stored = localStorage.getItem('lo_id'); if (stored) loId = stored; }
      const response = await fetch(`${API_URL}/api/v1/borrower-auth/submit-application`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profileData, incomeData, assetData: {}, propertyData, declarations, goalsData, eConsentAgreed, creditAuthAgreed, loId, applicationType: 'refinance' }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || 'Submission failed');
      localStorage.removeItem(STORAGE_KEY); localStorage.removeItem('borrower_email');
      if (result.data?.portal_url) { setPortalUrlForRedirect(result.data.portal_url); portalUrlRef.current = result.data.portal_url; }
      setShowSubmissionSuccess(true);
    } catch (error) {
      console.error('Application submission error:', error);
      setSubmitError(error.message || 'Failed to submit application. Please try again.');
    } finally { setIsSubmitting(false); }
  };

  // ─── Declaration navigation ───

  const proceedToNextQuestion = () => {
    let nextIndex = currentQuestionIndex + 1;
    while (nextIndex < enabledQuestions.length) {
      if (shouldShowQuestion(enabledQuestions[nextIndex], declarations)) { setCurrentQuestionIndex(nextIndex); return; }
      nextIndex++;
    }
    showMicroWinAnimation('Great! Your checklist is ready!');
    setTimeout(() => setCurrentStage('profile'), 1500);
  };

  const handleDeclarationAnswer = async (questionId, value) => {
    setIsAnimating(true);
    const newDecl = { ...declarations, [questionId]: value };
    setDeclarations(newDecl);
    const triggerFields = ['self_employed', 'gift_funds', 'bankruptcy', 'credit_issues', 'investment_property', 'coborrower'];
    if (triggerFields.some(f => questionId.includes(f))) {
      const result = await checkForFollowup(questionId, value, 'refinance', newDecl);
      if (result?.needs_followup) { setActiveFollowup(result); setIsAnimating(false); return; }
    }
    setTimeout(() => {
      setIsAnimating(false);
      let nextIndex = currentQuestionIndex + 1;
      while (nextIndex < enabledQuestions.length) {
        if (shouldShowQuestion(enabledQuestions[nextIndex], newDecl)) { setCurrentQuestionIndex(nextIndex); return; }
        nextIndex++;
      }
      showMicroWinAnimation('Great! Your checklist is ready!');
      setTimeout(() => setCurrentStage('profile'), 1500);
    }, 300);
  };

  const handleInputAnswer = (questionId, value) => setDeclarations(prev => ({ ...prev, [questionId]: value }));

  const submitInputAnswer = (questionId) => {
    if (declarations[questionId]) {
      setIsAnimating(true);
      setTimeout(() => {
        setIsAnimating(false);
        let nextIndex = currentQuestionIndex + 1;
        while (nextIndex < enabledQuestions.length) {
          if (shouldShowQuestion(enabledQuestions[nextIndex], declarations)) { setCurrentQuestionIndex(nextIndex); return; }
          nextIndex++;
        }
        showMicroWinAnimation('Great! Your checklist is ready!');
        setTimeout(() => setCurrentStage('profile'), 1500);
      }, 300);
    }
  };

  const goToPrevQuestion = () => {
    let prevIndex = currentQuestionIndex - 1;
    while (prevIndex >= 0) {
      if (shouldShowQuestion(enabledQuestions[prevIndex], declarations)) { setCurrentQuestionIndex(prevIndex); return; }
      prevIndex--;
    }
  };

  const getVisibleQuestionNumber = () => {
    const visible = getVisibleQuestions(enabledQuestions, declarations);
    return visible.findIndex(q => q.id === enabledQuestions[currentQuestionIndex].id) + 1;
  };

  // ─── Stage navigation ───

  const goToNextStage = () => {
    const idx = enabledStages.findIndex(s => s.id === currentStage);
    if (idx < enabledStages.length - 1) {
      setCurrentStage(enabledStages[idx + 1].id);
      showMicroWinAnimation(getStageMicroWin(enabledStages[idx].id));
    }
  };

  const goToPrevStage = () => {
    const idx = enabledStages.findIndex(s => s.id === currentStage);
    if (idx > 0) setCurrentStage(enabledStages[idx - 1].id);
  };

  // ─── Follow-up handlers ───

  const handleFollowupSubmit = (answers, trigger) => {
    setFollowupAnswers(prev => ({ ...prev, [trigger]: answers }));
    setDeclarations(prev => ({
      ...prev, ...Object.entries(answers).reduce((acc, [k, v]) => { acc[`${trigger}_${k}`] = v; return acc; }, {})
    }));
    setActiveFollowup(null); clearFollowup(); proceedToNextQuestion();
  };
  const handleFollowupSkip = () => { setActiveFollowup(null); clearFollowup(); proceedToNextQuestion(); };
  // ─── Income/goals field change handlers with follow-up checks ───

  const handleIncomeFieldChange = async (fieldName, value, setter) => {
    setter(prev => ({ ...prev, [fieldName]: value }));
    const triggerFields = ['businessType', 'ownershipPercent', 'rentalIncome', 'otherIncome'];
    if (triggerFields.includes(fieldName) && value) {
      const result = await checkForFollowup(`income_${fieldName}`, value, 'refinance', { ...declarations, ...incomeData, [fieldName]: value });
      if (result?.needs_followup) setActiveFollowup(result);
    }
  };

  const handleGoalsFieldChange = async (fieldName, value, setter) => {
    setter(prev => ({ ...prev, [fieldName]: value }));
    const triggerFields = ['cashOutAmount', 'cashOutPurpose'];
    if (triggerFields.includes(fieldName) && value) {
      const result = await checkForFollowup(`goals_${fieldName}`, value, 'refinance', { ...declarations, ...goalsData, [fieldName]: value });
      if (result?.needs_followup) setActiveFollowup(result);
    }
  };

  // ═══════════════════════════════════════
  // Stage renderer
  // ═══════════════════════════════════════

  const renderStage = () => {
    switch (currentStage) {
      case 'account':
        return (
          <AccountStage
            userAccount={userAccount} setUserAccount={setUserAccount}
            API_URL={API_URL} token={token}
            goToNextStage={() => setCurrentStage('declarations')}
          />
        );
      case 'declarations':
      default:
        return (
          <DeclarationsStage
            enabledQuestions={enabledQuestions} currentQuestionIndex={currentQuestionIndex}
            declarations={declarations} isAnimating={isAnimating}
            handleDeclarationAnswer={handleDeclarationAnswer} handleInputAnswer={handleInputAnswer}
            submitInputAnswer={submitInputAnswer} goToPrevQuestion={goToPrevQuestion}
            getVisibleQuestionNumber={getVisibleQuestionNumber}
            getVisibleQuestions={() => getVisibleQuestions(enabledQuestions, declarations)}
            activeFollowup={activeFollowup} handleFollowupSubmit={handleFollowupSubmit}
            handleFollowupSkip={handleFollowupSkip}
            AddressAutocomplete={AddressAutocomplete} US_STATES={US_STATES}
          />
        );
      case 'profile':
        return (
          <ProfileStage
            profileData={profileData} setProfileData={setProfileData}
            declarations={declarations} coBorrowerData={coBorrowerData}
            setCoBorrowerData={setCoBorrowerData}
            goToPrevStage={goToPrevStage} goToNextStage={goToNextStage}
          />
        );
      case 'income':
        return (
          <IncomeStage
            incomeData={incomeData} setIncomeData={setIncomeData}
            incomeStep={incomeStep} setIncomeStep={setIncomeStep}
            handleIncomeFieldChange={handleIncomeFieldChange}
            EmployerAutocomplete={EmployerAutocomplete}
            goToPrevStage={goToPrevStage} goToNextStage={goToNextStage}
          />
        );
      case 'property':
        return (
          <PropertyStage
            propertyData={propertyData} setPropertyData={setPropertyData}
            statementParsed={statementParsed} setStatementParsed={setStatementParsed}
            handleMortgageStatementData={handleMortgageStatementData}
            MortgageStatementUpload={MortgageStatementUpload}
            AddressAutocomplete={AddressAutocomplete}
            API_URL={API_URL}
            goToPrevStage={goToPrevStage} goToNextStage={goToNextStage}
          />
        );
      case 'goals':
        return (
          <GoalsStage
            declarations={declarations} propertyData={propertyData}
            goalsData={goalsData} setGoalsData={setGoalsData}
            handleGoalsFieldChange={handleGoalsFieldChange}
            goToPrevStage={goToPrevStage} goToNextStage={goToNextStage}
          />
        );
      case 'review':
        return (
          <ReviewStage
            profileData={profileData} incomeData={incomeData}
            propertyData={propertyData} goalsData={goalsData}
            setCurrentStage={setCurrentStage}
            goToPrevStage={goToPrevStage} goToNextStage={goToNextStage}
          />
        );
      case 'planning':
        return (
          <PlanningStage
            planningData={planningData} setPlanningData={setPlanningData}
            goToPrevStage={goToPrevStage} goToNextStage={goToNextStage}
          />
        );
      case 'schedule':
        return (
          <ScheduleStage
            API_URL={API_URL} calendarAssignment={calendarAssignment}
            scheduleStep={scheduleStep} setScheduleStep={setScheduleStep}
            bookingSlots={bookingSlots} setBookingSlots={setBookingSlots}
            bookingSelectedDate={bookingSelectedDate} setBookingSelectedDate={setBookingSelectedDate}
            bookingSelectedTime={bookingSelectedTime} setBookingSelectedTime={setBookingSelectedTime}
            bookingWeekStart={bookingWeekStart} setBookingWeekStart={setBookingWeekStart}
            bookingLoading={bookingLoading} setBookingLoading={setBookingLoading}
            bookingConfirmed={bookingConfirmed} setBookingConfirmed={setBookingConfirmed}
            bookingError={bookingError} setBookingError={setBookingError}
            eConsentAgreed={eConsentAgreed} setEConsentAgreed={setEConsentAgreed}
            creditAuthAgreed={creditAuthAgreed} setCreditAuthAgreed={setCreditAuthAgreed}
            profileData={profileData}
            isSubmitting={isSubmitting} submitError={submitError}
            handleSubmitApplication={handleSubmitApplication}
            goToPrevStage={goToPrevStage}
          />
        );
    }
  };

  // ═══════════════════════════════════════
  // Render
  // ═══════════════════════════════════════

  return (
    <div className="adaptive-urla">
      {isDemoMode && (
        <div className="demo-banner" style={{ background: 'linear-gradient(135deg, #1F3D2E 0%, #2A4F3D 100%)' }}>
          <span className="demo-badge">DEMO</span>
          Refinance Application
        </div>
      )}

      {currentStage !== 'account' && (
        <ProgressHeader
          visibleStages={visibleStages} currentStage={currentStage}
          setCurrentStage={setCurrentStage} getProgress={getProgress}
          onSave={() => setShowSaveModal(true)}
        />
      )}

      <MicroWinToast show={showMicroWin} message={microWinMessage} />

      <div className="urla-main-layout">
        <main className="urla-content">
          {renderStage()}
        </main>

        {currentStage !== 'account' && (
          <DocumentsSidebar
            currentStage={currentStage} enabledStages={enabledStages}
            declarations={declarations} profileData={profileData}
            incomeData={incomeData} coBorrowerData={coBorrowerData}
            coBorrowerIncomeData={coBorrowerIncomeData}
            getRequiredDocuments={getRequiredDocuments}
            categoryUnlockStage={{ identity: 'declarations', income: 'income', assets: 'income', property: 'property' }}
          />
        )}
      </div>

      {currentStage !== 'declarations' && needsList.length > 0 && (
        <aside className="needs-sidebar">
          <h4><Icon name="clipboard" size={16} /> Your Checklist</h4>
          <ul>{needsList.slice(0, 5).map(item => <li key={item.id}>{item.label}</li>)}</ul>
          {needsList.length > 5 && <span className="more-items">+{needsList.length - 5} more</span>}
        </aside>
      )}

      {showSubmissionSuccess && <SubmissionSuccess show={true} applicationType="refinance" />}

      {showSaveModal && (
        <SaveProgressModal
          showSaveModal={showSaveModal} setShowSaveModal={setShowSaveModal}
          saveEmail={saveEmail} setSaveEmail={setSaveEmail}
          userAccount={userAccount} setUserAccount={setUserAccount}
          lastSavedAt={lastSavedAt} onSaveEmail={handleSaveProgressEmail}
        />
      )}
    </div>
  );
}

export default RefinanceApplication;
