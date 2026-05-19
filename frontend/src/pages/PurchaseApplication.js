import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import './AdaptiveURLA.css';

// Configuration data and shared components (extracted to sub-modules)
import {
  STAGES,
  DECLARATION_QUESTIONS,
  getRequiredDocuments,
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
  shouldShowQuestion,
  getVisibleQuestions,
  getStageMicroWin,
  getEnabledStages,
  getEnabledQuestions,
  buildRedirectUrl,
  buildNeedsList,
} from './purchase-application';

// Stage components (extracted)
import ProfileStage from './purchase-application/ProfileStage';
import IncomeStage from './purchase-application/IncomeStage';
import AssetsStage from './purchase-application/AssetsStage';
import PropertyStage from './purchase-application/PropertyStage';
import ReviewStage from './purchase-application/ReviewStage';
import PlanningStage from './purchase-application/PlanningStage';

/**
 * PurchaseApplication - Streamlined Home Purchase Application
 *
 * Thin orchestrator: owns all state, delegates rendering to extracted stage components.
 */

export default function PurchaseApplication() {
  const { token } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const isDemoMode = token === 'start' || searchParams.get('demo') === 'true';

  // API Configuration
  const isProduction = window.location.hostname !== 'localhost';
  const API_URL = isProduction
    ? 'https://api.perenniaai.com'
    : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

  const STORAGE_KEY = `purchase_application_${token || 'draft'}`;

  // --- State declarations ---
  const [userAccount, setUserAccount] = useState({ email: '', authMethod: null, isLoggedIn: false });
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [saveEmail, setSaveEmail] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState(null);
  const [currentStage, setCurrentStage] = useState(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const isDemo = urlParams.get('demo') === 'true' || window.location.pathname.includes('/apply/start');
    return isDemo ? 'declarations' : 'account';
  });
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const [declarations, setDeclarations] = useState({});
  const [profileData, setProfileData] = useState({});
  const [residenceHistory, setResidenceHistory] = useState([{ street: '', city: '', state: '', zip: '', years: '', months: '', housingStatus: '' }]);
  const [coBorrowerResidenceHistory, setCoBorrowerResidenceHistory] = useState([{ street: '', city: '', state: '', zip: '', years: '', months: '', housingStatus: '' }]);
  const [incomeData, setIncomeData] = useState({});
  const [incomeStep, setIncomeStep] = useState(1);
  const [followupAnswers, setFollowupAnswers] = useState({});
  const [activeFollowup, setActiveFollowup] = useState(null);
  const [agentSearch, setAgentSearch] = useState('');
  const [agentSuggestions, setAgentSuggestions] = useState([]);
  const [agentLoading, setAgentLoading] = useState(false);
  const [showAgentDropdown, setShowAgentDropdown] = useState(false);
  const [agentInfo, setAgentInfo] = useState({ name: '', phone: '', email: '', company: '', partnerId: null });
  const [propertyStep, setPropertyStep] = useState(1);
  const [assetData, setAssetData] = useState({});
  const [propertyData, setPropertyData] = useState({});
  const [planningData, setPlanningData] = useState({ mortgagePriorities: [], personalGoals: [], financialPhilosophy: '', professionalNetwork: [], taxDeferredRetirement: '' });
  const [needsList, setNeedsList] = useState([]);
  const [showMicroWin, setShowMicroWin] = useState(false);
  const [microWinMessage, setMicroWinMessage] = useState('');
  const [isAnimating, setIsAnimating] = useState(false);
  const [selectedTimeSlot, setSelectedTimeSlot] = useState(null);
  const [scheduleStep, setScheduleStep] = useState(1);
  const [calendarAssignment, setCalendarAssignment] = useState(null);
  const [bookingSlots, setBookingSlots] = useState([]);
  const [bookingSelectedDate, setBookingSelectedDate] = useState(null);
  const [bookingSelectedTime, setBookingSelectedTime] = useState('');
  const [bookingWeekStart, setBookingWeekStart] = useState(() => { const today = new Date(); today.setHours(0, 0, 0, 0); return today; });
  const [bookingLoading, setBookingLoading] = useState(false);
  const [bookingConfirmed, setBookingConfirmed] = useState(false);
  const [bookingError, setBookingError] = useState(null);
  const [planningStep, setPlanningStep] = useState(1);
  const [professionalSubStep, setProfessionalSubStep] = useState(1);
  const [wantProfessionalsInvolved, setWantProfessionalsInvolved] = useState(null);
  const [professionalContacts, setProfessionalContacts] = useState({});
  const [wantIntroductions, setWantIntroductions] = useState(null);
  const [introductionRequests, setIntroductionRequests] = useState([]);
  const [ssnRaw, setSsnRaw] = useState('');
  const [ssnDisplay, setSsnDisplay] = useState('');
  const [emailSending, setEmailSending] = useState(false);
  const [emailSent, setEmailSent] = useState(false);
  const [currentBorrower, setCurrentBorrower] = useState(1);
  const [coBorrowerData, setCoBorrowerData] = useState({});
  const [coBorrowerIncomeData, setCoBorrowerIncomeData] = useState({});
  const [currentIncomeBorrower, setCurrentIncomeBorrower] = useState(1);
  const [coBorrowerSsnRaw, setCoBorrowerSsnRaw] = useState('');
  const [coBorrowerSsnDisplay, setCoBorrowerSsnDisplay] = useState('');
  const [paymentEstimate, setPaymentEstimate] = useState(null);
  const [eConsentAgreed, setEConsentAgreed] = useState(false);
  const [creditAuthAgreed, setCreditAuthAgreed] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [showSubmissionSuccess, setShowSubmissionSuccess] = useState(false);
  const [portalUrlForRedirect, setPortalUrlForRedirect] = useState(null);
  const portalUrlRef = useRef(null);
  const [employerSuggestions, setEmployerSuggestions] = useState([]);
  const [showEmployerDropdown, setShowEmployerDropdown] = useState(false);
  const [applicationConfig, setApplicationConfig] = useState(null);
  const [configLoaded, setConfigLoaded] = useState(false);

  // Stubs for disabled followup feature
  const clearFollowup = () => {};
  const checkForFollowup = async () => null;

  // --- Config & enabled stages ---
  useEffect(() => {
    const loadApplicationConfig = async () => {
      try {
        const response = await fetch(`${API_URL}/api/v1/settings/application-slides`);
        if (response.ok) { const config = await response.json(); setApplicationConfig(config); }
      } catch (error) { console.warn('[PurchaseApplication] Failed to load config:', error); }
      finally { setConfigLoaded(true); }
    };
    loadApplicationConfig();
  }, [API_URL]);

  const enabledStages = getEnabledStages(applicationConfig, STAGES);
  const enabledQuestions = getEnabledQuestions(applicationConfig, DECLARATION_QUESTIONS);
  const visibleStages = enabledStages.filter(s => !s.hideFromProgress);

  // --- Load/save/auth effects ---
  useEffect(() => {
    const isFreshStart = searchParams.get('fresh') === 'true';
    if (isFreshStart) {
      localStorage.removeItem(STORAGE_KEY);
      const newUrl = new URL(window.location.href); newUrl.searchParams.delete('fresh');
      window.history.replaceState({}, '', newUrl.toString());
      return;
    }
    const savedData = localStorage.getItem(STORAGE_KEY);
    if (savedData) {
      try {
        const parsed = JSON.parse(savedData);
        if (parsed.declarations) setDeclarations(parsed.declarations);
        if (parsed.profileData) setProfileData(parsed.profileData);
        if (parsed.incomeData) setIncomeData(parsed.incomeData);
        if (parsed.assetData) setAssetData(parsed.assetData);
        if (parsed.propertyData) setPropertyData(parsed.propertyData);
        if (parsed.coBorrowerData) setCoBorrowerData(parsed.coBorrowerData);
        if (parsed.coBorrowerIncomeData) setCoBorrowerIncomeData(parsed.coBorrowerIncomeData);
        if (parsed.currentStage && parsed.currentStage !== 'account') setCurrentStage(parsed.currentStage);
        if (parsed.userAccount?.email) setUserAccount(parsed.userAccount);
        setLastSavedAt(parsed.savedAt ? new Date(parsed.savedAt) : null);
      } catch (e) { console.error('Failed to load saved progress:', e); }
    }
  }, [STORAGE_KEY, searchParams]);

  useEffect(() => {
    const authToken = searchParams.get('auth');
    if (authToken) {
      try {
        const parts = authToken.split('.');
        if (parts.length === 3) {
          const payload = JSON.parse(atob(parts[1]));
          const email = payload.sub || payload.email;
          if (email) {
            localStorage.removeItem(STORAGE_KEY);
            setDeclarations({}); setProfileData({ firstName: '', lastName: '', email, phone: '', dateOfBirth: '' });
            setIncomeData({}); setAssetData({ checking: '', savings: '', investments: '', retirement: '', other: '' });
            setPropertyData({}); setCoBorrowerData({}); setCoBorrowerIncomeData({});
            setUserAccount({ email, authMethod: 'email', isLoggedIn: true, authToken });
            setCurrentStage('declarations');
            const newUrl = new URL(window.location.href); newUrl.searchParams.delete('auth');
            window.history.replaceState({}, '', newUrl.toString());
          }
        }
      } catch (e) { console.error('Failed to parse auth token:', e); }
    }
  }, [searchParams, STORAGE_KEY]);

  useEffect(() => { if (isDemoMode && currentStage === 'account') setCurrentStage('declarations'); }, [isDemoMode, currentStage]);

  useEffect(() => {
    if (currentStage === 'account') return;
    const sanitizedProfileData = { ...profileData }; delete sanitizedProfileData.ssn;
    const sanitizedCoBorrowerData = { ...coBorrowerData }; delete sanitizedCoBorrowerData.ssn;
    const dataToSave = { declarations, profileData: sanitizedProfileData, propertyData, coBorrowerData: sanitizedCoBorrowerData, currentStage, userAccount, savedAt: new Date().toISOString() };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(dataToSave));
    setLastSavedAt(new Date());
  }, [declarations, profileData, incomeData, assetData, propertyData, coBorrowerData, coBorrowerIncomeData, currentStage, userAccount, STORAGE_KEY]);

  useEffect(() => {
    const stageParam = searchParams.get('stage');
    if (stageParam === 'calculator') { setCurrentStage('planning'); setPlanningStep(1); }
  }, [searchParams]);

  useEffect(() => {
    const fetchCalendarAssignment = async () => {
      try {
        const response = await fetch(`${API_URL}/api/v1/calendar-assignments/purchase_application`);
        if (response.ok) { const data = await response.json(); setCalendarAssignment(data); }
      } catch (err) { console.error('Error fetching calendar assignment:', err); }
    };
    fetchCalendarAssignment();
  }, [API_URL]);

  useEffect(() => { portalUrlRef.current = portalUrlForRedirect; }, [portalUrlForRedirect]);

  useEffect(() => {
    if (showSubmissionSuccess) {
      const redirectTimer = setTimeout(() => {
        let redirectUrl = portalUrlRef.current || buildRedirectUrl(token);
        if (window.parent !== window) window.parent.postMessage({ type: 'APPLICATION_SUBMITTED', portalUrl: redirectUrl }, window.location.origin);
        window.location.href = redirectUrl;
      }, 3000);
      return () => clearTimeout(redirectTimer);
    }
  }, [showSubmissionSuccess]);

  // --- Needs list ---
  useEffect(() => {
    setNeedsList(buildNeedsList(declarations, 'purchase'));
  }, [declarations]);

  // --- Handlers ---
  const hasMultipleBorrowers = ['2', '3', '4+'].includes(declarations.borrower_count);
  const getBorrowerCount = () => { if (declarations.borrower_count === '2') return 2; if (declarations.borrower_count === '3') return 3; if (declarations.borrower_count === '4+') return 4; return 1; };

  const calculateTotalResidenceMonths = (history) => history.reduce((total, addr) => { const years = parseInt(addr.years) || 0; const months = parseInt(addr.months) || 0; return total + (years * 12) + months; }, 0);

  const addResidenceAddress = (isCoBorrower = false) => {
    const newAddr = { street: '', city: '', state: '', zip: '', years: '', months: '', housingStatus: '' };
    if (isCoBorrower) setCoBorrowerResidenceHistory(prev => [...prev, newAddr]);
    else setResidenceHistory(prev => [...prev, newAddr]);
  };

  const removeResidenceAddress = (index, isCoBorrower = false) => {
    if (isCoBorrower) setCoBorrowerResidenceHistory(prev => prev.filter((_, i) => i !== index));
    else setResidenceHistory(prev => prev.filter((_, i) => i !== index));
  };

  const updateResidenceAddress = (index, field, value, isCoBorrower = false) => {
    if (isCoBorrower) setCoBorrowerResidenceHistory(prev => prev.map((addr, i) => i === index ? { ...addr, [field]: value } : addr));
    else setResidenceHistory(prev => prev.map((addr, i) => i === index ? { ...addr, [field]: value } : addr));
  };

  const handleSsnChange = (input, isCoBorrower = false) => {
    const digits = input.replace(/\D/g, '').slice(0, 9);
    let display = '';
    if (digits.length === 0) display = '';
    else if (digits.length <= 3) display = 'X'.repeat(digits.length);
    else if (digits.length <= 5) display = 'XXX-' + 'X'.repeat(digits.length - 3);
    else display = 'XXX-XX-' + digits.slice(5);
    if (isCoBorrower) { setCoBorrowerSsnRaw(digits); setCoBorrowerSsnDisplay(display); setCoBorrowerData(prev => ({ ...prev, ssn: digits })); }
    else { setSsnRaw(digits); setSsnDisplay(display); setProfileData(prev => ({ ...prev, ssn: digits })); }
  };

  const showMicroWinAnimation = (message) => { setMicroWinMessage(message); setShowMicroWin(true); setTimeout(() => setShowMicroWin(false), 2500); };

  const getProgress = useCallback(() => {
    if (currentStage === 'account') return 0;
    const stageIndex = visibleStages.findIndex(s => s.id === currentStage);
    if (stageIndex === -1) return 0;
    const stageProgress = (stageIndex / visibleStages.length) * 100;
    if (currentStage === 'declarations') {
      const questionProgress = (currentQuestionIndex / enabledQuestions.length) * (100 / visibleStages.length);
      return Math.round(stageProgress + questionProgress);
    }
    return Math.round(stageProgress);
  }, [currentStage, currentQuestionIndex, visibleStages, enabledQuestions]);

  const goToNextStage = () => {
    const currentIndex = enabledStages.findIndex(s => s.id === currentStage);
    if (currentIndex < enabledStages.length - 1) { setCurrentStage(enabledStages[currentIndex + 1].id); showMicroWinAnimation(getStageMicroWin(enabledStages[currentIndex].id)); }
  };

  const goToPrevStage = () => {
    const currentIndex = enabledStages.findIndex(s => s.id === currentStage);
    if (currentIndex > 0) setCurrentStage(enabledStages[currentIndex - 1].id);
  };

  const proceedToNextQuestion = () => {
    let nextIndex = currentQuestionIndex + 1;
    while (nextIndex < enabledQuestions.length) {
      if (shouldShowQuestion(enabledQuestions[nextIndex], declarations)) { setCurrentQuestionIndex(nextIndex); return; }
      nextIndex++;
    }
    goToNextStage();
  };

  const handleDeclarationAnswer = async (questionId, value) => {
    setIsAnimating(true);
    const newDeclarations = { ...declarations, [questionId]: value };
    setDeclarations(newDeclarations);
    const triggerFields = ['self_employed', 'gift_funds', 'bankruptcy', 'credit_issues', 'investment_property', 'coborrower'];
    if (triggerFields.some(f => questionId.includes(f))) {
      const result = await checkForFollowup(questionId, value, 'purchase', newDeclarations);
      if (result && result.needs_followup) { setActiveFollowup(result); setIsAnimating(false); return; }
    }
    setTimeout(() => {
      setIsAnimating(false);
      let nextIndex = currentQuestionIndex + 1;
      while (nextIndex < enabledQuestions.length) {
        if (shouldShowQuestion(enabledQuestions[nextIndex], newDeclarations)) { setCurrentQuestionIndex(nextIndex); return; }
        nextIndex++;
      }
      showMicroWinAnimation('Great! Your checklist is ready!');
      setTimeout(() => goToNextStage(), 1500);
    }, 300);
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
    const current = enabledQuestions[currentQuestionIndex];
    return visible.findIndex(q => q.id === current?.id) + 1;
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
        setTimeout(() => goToNextStage(), 1500);
      }, 300);
    }
  };

  const searchRealtors = async (searchTerm) => {
    if (!searchTerm || searchTerm.length < 2) { setAgentSuggestions([]); setShowAgentDropdown(false); return; }
    setAgentLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/v1/public/partners/realtors?q=${encodeURIComponent(searchTerm)}&limit=8`);
      if (response.ok) { const data = await response.json(); setAgentSuggestions(data); setShowAgentDropdown(data.length > 0); }
    } catch (error) { console.error('Error searching realtors:', error); }
    finally { setAgentLoading(false); }
  };

  const handleSelectAgent = (agent) => {
    setAgentInfo({ name: agent.name || '', phone: agent.phone || '', email: agent.email || '', company: agent.company || '', partnerId: agent.id || null });
    setAgentSearch(agent.name || ''); setShowAgentDropdown(false);
    setDeclarations(prev => ({ ...prev, agent_name: agent.name || '', agent_phone: agent.phone || '', agent_email: agent.email || '', agent_company: agent.company || '', agent_partner_id: agent.id || null }));
  };

  const handleAgentInfoChange = (field, value) => {
    setAgentInfo(prev => ({ ...prev, [field]: value }));
    setDeclarations(prev => ({ ...prev, [`agent_${field}`]: value }));
  };

  const handleIncomeFieldChange = async (fieldName, value, setter) => {
    setter(prev => ({ ...prev, [fieldName]: value }));
    const triggerFields = ['businessType', 'ownershipPercent', 'rentalIncome', 'otherIncome'];
    if (triggerFields.includes(fieldName) && value) {
      const result = await checkForFollowup(`income_${fieldName}`, value, 'purchase', { ...declarations, ...incomeData, [fieldName]: value });
      if (result && result.needs_followup) setActiveFollowup(result);
    }
  };

  const handleAssetFieldChange = async (fieldName, value, setter) => {
    setter(prev => ({ ...prev, [fieldName]: value }));
    const triggerFields = ['largeDeposits', 'giftAmount', 'donorName', 'otherAssets'];
    if (triggerFields.includes(fieldName) && value) {
      const result = await checkForFollowup(`asset_${fieldName}`, value, 'purchase', { ...declarations, ...assetData, [fieldName]: value });
      if (result && result.needs_followup) setActiveFollowup(result);
    }
  };

  const handleSubmitApplication = async () => {
    setIsSubmitting(true); setSubmitError(null);
    try {
      let loId = null;
      if (token && token !== 'start') { const storedLoId = localStorage.getItem('lo_id'); if (storedLoId) loId = storedLoId; }
      const submissionData = { profileData, incomeData, assetData, propertyData, declarations, paymentEstimate, eConsentAgreed, creditAuthAgreed, loId };
      const response = await fetch(`${API_URL}/api/v1/borrower-auth/submit-application`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(submissionData) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || 'Submission failed');
      if (profileData?.email) localStorage.setItem('borrower_email', profileData.email);
      // Sync document requirements to Smart Docs
      if (result.data?.loan_id) {
        try {
          const coBorrowerInfo = declarations.borrower_count && ['2', '3', '4+'].includes(declarations.borrower_count) ? { firstName: declarations.co_borrower_first_name } : {};
          const coBorrowerIncomeInfo = { employerName: declarations.co_borrower_employer_name };
          const requiredDocs = getRequiredDocuments(declarations, assetData, profileData, incomeData, coBorrowerInfo, coBorrowerIncomeInfo);
          await fetch(`${API_URL}/api/v1/smart-docs/needs-list/sync-from-application`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ loan_id: result.data.loan_id, workspace_slug: result.data.workspace_slug, borrower_first_name: profileData.firstName || 'Borrower', co_borrower_first_name: coBorrowerInfo.firstName || null, documents: requiredDocs.map(doc => ({ id: doc.id, name: doc.name, description: doc.description, category: doc.category, stage: doc.stage })) })
          });
        } catch (syncError) { console.warn('[PurchaseApplication] Failed to sync documents:', syncError); }
      }
      localStorage.removeItem(STORAGE_KEY); localStorage.removeItem('borrower_email');
      if (result.data?.portal_url) { setPortalUrlForRedirect(result.data.portal_url); portalUrlRef.current = result.data.portal_url; }
      setShowSubmissionSuccess(true);
    } catch (error) { console.error('Application submission error:', error); setSubmitError(error.message || 'Failed to submit application. Please try again.'); }
    finally { setIsSubmitting(false); }
  };

  // --- Stage dispatcher ---
  const renderStage = () => {
    switch (currentStage) {
      case 'account':
        return <AccountStage API_URL={API_URL} userAccount={userAccount} setUserAccount={setUserAccount} emailSending={emailSending} setEmailSending={setEmailSending} emailSent={emailSent} setEmailSent={setEmailSent} setCurrentStage={setCurrentStage} isDemoMode={isDemoMode} navigate={navigate} />;
      case 'declarations':
        return <DeclarationsStage enabledQuestions={enabledQuestions} currentQuestionIndex={currentQuestionIndex} setCurrentQuestionIndex={setCurrentQuestionIndex} declarations={declarations} isAnimating={isAnimating} handleDeclarationAnswer={handleDeclarationAnswer} handleInputAnswer={handleInputAnswer} submitInputAnswer={submitInputAnswer} goToPrevQuestion={goToPrevQuestion} getVisibleQuestions={() => getVisibleQuestions(enabledQuestions, declarations)} getVisibleQuestionNumber={getVisibleQuestionNumber} shouldShowQuestion={(q) => shouldShowQuestion(q, declarations)} Icon={Icon} US_STATES={US_STATES} agentSearch={agentSearch} setAgentSearch={setAgentSearch} agentSuggestions={agentSuggestions} agentLoading={agentLoading} showAgentDropdown={showAgentDropdown} setShowAgentDropdown={setShowAgentDropdown} agentInfo={agentInfo} handleSelectAgent={handleSelectAgent} handleAgentInfoChange={handleAgentInfoChange} searchRealtors={searchRealtors} />;
      case 'profile':
        return <ProfileStage currentBorrower={currentBorrower} setCurrentBorrower={setCurrentBorrower} profileData={profileData} setProfileData={setProfileData} coBorrowerData={coBorrowerData} setCoBorrowerData={setCoBorrowerData} ssnDisplay={ssnDisplay} ssnRaw={ssnRaw} coBorrowerSsnDisplay={coBorrowerSsnDisplay} coBorrowerSsnRaw={coBorrowerSsnRaw} handleSsnChange={handleSsnChange} declarations={declarations} hasMultipleBorrowers={hasMultipleBorrowers} getBorrowerCount={getBorrowerCount} residenceHistory={residenceHistory} coBorrowerResidenceHistory={coBorrowerResidenceHistory} addResidenceAddress={addResidenceAddress} removeResidenceAddress={removeResidenceAddress} updateResidenceAddress={updateResidenceAddress} calculateTotalResidenceMonths={calculateTotalResidenceMonths} goToPrevStage={goToPrevStage} goToNextStage={goToNextStage} />;
      case 'income':
        return <IncomeStage declarations={declarations} profileData={profileData} coBorrowerData={coBorrowerData} incomeData={incomeData} setIncomeData={setIncomeData} coBorrowerIncomeData={coBorrowerIncomeData} setCoBorrowerIncomeData={setCoBorrowerIncomeData} currentIncomeBorrower={currentIncomeBorrower} setCurrentIncomeBorrower={setCurrentIncomeBorrower} hasMultipleBorrowers={hasMultipleBorrowers} getBorrowerCount={getBorrowerCount} handleIncomeFieldChange={handleIncomeFieldChange} goToPrevStage={goToPrevStage} goToNextStage={goToNextStage} />;
      case 'assets':
        return <AssetsStage declarations={declarations} assetData={assetData} setAssetData={setAssetData} handleAssetFieldChange={handleAssetFieldChange} goToPrevStage={goToPrevStage} goToNextStage={goToNextStage} />;
      case 'property':
        return <PropertyStage declarations={declarations} propertyData={propertyData} setPropertyData={setPropertyData} propertyStep={propertyStep} setPropertyStep={setPropertyStep} paymentEstimate={paymentEstimate} setPaymentEstimate={setPaymentEstimate} setCurrentStage={setCurrentStage} goToPrevStage={goToPrevStage} goToNextStage={goToNextStage} />;
      case 'review':
        return <ReviewStage profileData={profileData} incomeData={incomeData} assetData={assetData} propertyData={propertyData} declarations={declarations} coBorrowerData={coBorrowerData} ssnDisplay={ssnDisplay} coBorrowerSsnDisplay={coBorrowerSsnDisplay} paymentEstimate={paymentEstimate} hasMultipleBorrowers={hasMultipleBorrowers} setCurrentStage={setCurrentStage} goToPrevStage={goToPrevStage} goToNextStage={goToNextStage} />;
      case 'planning':
        return <PlanningStage propertyData={propertyData} planningData={planningData} setPlanningData={setPlanningData} planningStep={planningStep} setPlanningStep={setPlanningStep} professionalSubStep={professionalSubStep} setProfessionalSubStep={setProfessionalSubStep} wantProfessionalsInvolved={wantProfessionalsInvolved} setWantProfessionalsInvolved={setWantProfessionalsInvolved} professionalContacts={professionalContacts} setProfessionalContacts={setProfessionalContacts} wantIntroductions={wantIntroductions} setWantIntroductions={setWantIntroductions} introductionRequests={introductionRequests} setIntroductionRequests={setIntroductionRequests} paymentEstimate={paymentEstimate} setPaymentEstimate={setPaymentEstimate} goToPrevStage={goToPrevStage} goToNextStage={goToNextStage} />;
      case 'schedule':
        return <ScheduleStage applicationType="purchase" API_URL={API_URL} profileData={profileData} calendarAssignment={calendarAssignment} scheduleStep={scheduleStep} setScheduleStep={setScheduleStep} selectedTimeSlot={selectedTimeSlot} setSelectedTimeSlot={setSelectedTimeSlot} bookingWeekStart={bookingWeekStart} setBookingWeekStart={setBookingWeekStart} bookingSelectedDate={bookingSelectedDate} setBookingSelectedDate={setBookingSelectedDate} bookingSelectedTime={bookingSelectedTime} setBookingSelectedTime={setBookingSelectedTime} bookingSlots={bookingSlots} setBookingSlots={setBookingSlots} bookingLoading={bookingLoading} setBookingLoading={setBookingLoading} bookingConfirmed={bookingConfirmed} setBookingConfirmed={setBookingConfirmed} bookingError={bookingError} setBookingError={setBookingError} eConsentAgreed={eConsentAgreed} setEConsentAgreed={setEConsentAgreed} creditAuthAgreed={creditAuthAgreed} setCreditAuthAgreed={setCreditAuthAgreed} isSubmitting={isSubmitting} submitError={submitError} handleSubmitApplication={handleSubmitApplication} goToPrevStage={goToPrevStage} goToNextStage={goToNextStage} />;
      default:
        return <AccountStage API_URL={API_URL} userAccount={userAccount} setUserAccount={setUserAccount} emailSending={emailSending} setEmailSending={setEmailSending} emailSent={emailSent} setEmailSent={setEmailSent} setCurrentStage={setCurrentStage} isDemoMode={isDemoMode} navigate={navigate} />;
    }
  };

  // --- Main render ---
  return (
    <div className="adaptive-urla">
      {isDemoMode && (<div className="demo-banner"><span className="demo-badge">DEMO</span> Home Purchase Application</div>)}

      {currentStage !== 'account' && (
        <ProgressHeader
          visibleStages={visibleStages} currentStage={currentStage}
          setCurrentStage={setCurrentStage} getProgress={getProgress}
          onSave={() => setShowSaveModal(true)} allowClickAny={true}
        />
      )}

      <MicroWinToast show={showMicroWin} message={microWinMessage} />

      <div className="urla-main-layout">
        <main className="urla-content">{renderStage()}</main>
        {currentStage !== 'account' && (
          <DocumentsSidebar
            currentStage={currentStage} enabledStages={enabledStages}
            declarations={declarations} assetData={assetData}
            profileData={profileData} incomeData={incomeData}
            coBorrowerData={coBorrowerData} coBorrowerIncomeData={coBorrowerIncomeData}
            getRequiredDocuments={getRequiredDocuments}
          />
        )}
      </div>

      {showSubmissionSuccess && <SubmissionSuccess show={true} applicationType="mortgage" />}

      {showSaveModal && (
        <SaveProgressModal
          showSaveModal={showSaveModal} setShowSaveModal={setShowSaveModal}
          saveEmail={saveEmail} setSaveEmail={setSaveEmail}
          userAccount={userAccount} setUserAccount={setUserAccount}
          lastSavedAt={lastSavedAt}
        />
      )}
    </div>
  );
}
