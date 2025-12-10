import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import './AdaptiveURLA.css';

/**
 * RefinanceApplication - Streamlined Refinance Application
 *
 * Tailored 6-Stage Flow for Refinancing:
 * 1. Declarations - Key questions for personalization
 * 2. Profile - Personal information
 * 3. Income - Employment and income details
 * 4. Current Property - Existing home details
 * 5. Refinance Goals - Cash-out, rate/term, loan program
 * 6. Review - Summary and submit
 */

const STAGES = [
  { id: 'declarations', label: 'Your Story', icon: '🧩', description: 'Quick questions' },
  { id: 'profile', label: 'About You', icon: '👤', description: 'The basics' },
  { id: 'income', label: 'Your Income', icon: '💼', description: 'How you earn' },
  { id: 'property', label: 'Current Home', icon: '🏠', description: 'Property details' },
  { id: 'goals', label: 'Refi Goals', icon: '🎯', description: 'Refinance options' },
  { id: 'review', label: 'Review', icon: '✅', description: 'Review your info' },
  { id: 'planning', label: 'Planning', icon: '📊', description: 'Your preferences' },
  { id: 'schedule', label: 'Schedule', icon: '📅', description: 'Book a call' },
];

// Refinance-specific declaration questions
const DECLARATION_QUESTIONS = [
  {
    id: 'borrower_count',
    question: 'How many people will be on this loan application?',
    type: 'choice',
    options: [
      { value: '1', label: 'Just me', icon: '👤' },
      { value: '2', label: 'Two of us', icon: '👥' },
      { value: '3', label: 'Three people', icon: '👨‍👩‍👦' },
      { value: '4+', label: 'Four or more', icon: '👨‍👩‍👧‍👦' },
    ],
    hint: 'This helps us know how many borrowers to include in the application.',
  },
  {
    id: 'refi_goal',
    question: 'What\'s your main goal for refinancing?',
    type: 'choice',
    options: [
      { value: 'lower_rate', label: 'Lower my interest rate', icon: '📉' },
      { value: 'lower_payment', label: 'Lower my monthly payment', icon: '💵' },
      { value: 'cash_out', label: 'Get cash from my equity', icon: '💰' },
      { value: 'shorter_term', label: 'Pay off faster', icon: '⏱️' },
    ],
  },
  {
    id: 'marital_status',
    question: 'Are you married?',
    type: 'choice',
    options: [
      { value: 'married', label: 'Yes, married', icon: '💑' },
      { value: 'single', label: 'Single', icon: '👤' },
      { value: 'divorced', label: 'Divorced', icon: '📝' },
    ],
    unlocks: ['spouse_section'],
  },
  {
    id: 'veteran',
    question: 'Have you or your spouse served in the military?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, I\'m a Veteran', icon: '🎖️' },
      { value: 'active', label: 'Currently Active Duty', icon: '⭐' },
      { value: 'spouse', label: 'My spouse served', icon: '💑' },
      { value: 'no', label: 'No military service', icon: '➡️' },
    ],
    hint: 'VA streamline refinance options available!',
  },
  {
    id: 'self_employed',
    question: 'Are you self-employed or own a business?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, self-employed', icon: '🏢' },
      { value: 'side_business', label: 'I have a side business', icon: '💼' },
      { value: 'no', label: 'No, I\'m an employee', icon: '👔' },
    ],
    hint: 'This helps us know what income documents you\'ll need.',
  },
  {
    id: 'write_off_expenses',
    question: 'Do you write off most expenses to minimize taxable income?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, I maximize deductions', icon: '📉' },
      { value: 'some', label: 'Some, but I show decent income', icon: '⚖️' },
      { value: 'no', label: 'No, I show most of my income', icon: '📈' },
    ],
    hint: 'Self-employed income is based on your adjusted gross income after expenses. If you write off heavily, we may need 12 months of business bank statements.',
    showIf: { field: 'self_employed', values: ['yes', 'side_business'] },
  },
  {
    id: 'irs_balance_owed',
    question: 'Do you have an outstanding balance owed to the IRS?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, I owe the IRS', icon: '⚠️' },
      { value: 'payment_plan', label: 'Yes, but on a payment plan', icon: '📋' },
      { value: 'no', label: 'No outstanding balance', icon: '✅' },
    ],
    hint: 'Having a balance doesn\'t disqualify you - we just need to know.',
  },
  {
    id: 'recent_credit_applications',
    question: 'Have you applied for any credit in the past 3 months?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, I applied recently', icon: '💳' },
      { value: 'no', label: 'No recent applications', icon: '✅' },
    ],
    hint: 'Car loans, credit cards, personal loans, etc. Recent inquiries can affect your score.',
  },
  {
    id: 'current_loan_type',
    question: 'What type of loan do you currently have?',
    type: 'choice',
    options: [
      { value: 'conventional', label: 'Conventional', icon: '🏦' },
      { value: 'fha', label: 'FHA', icon: '🏛️' },
      { value: 'va', label: 'VA', icon: '🎖️' },
      { value: 'usda', label: 'USDA', icon: '🌾' },
      { value: 'not_sure', label: 'Not sure', icon: '❓' },
    ],
  },
  {
    id: 'property_type',
    question: 'What type of property is it?',
    type: 'choice',
    options: [
      { value: 'single_family', label: 'Single Family', icon: '🏠' },
      { value: 'condo', label: 'Condo', icon: '🏢' },
      { value: 'townhouse', label: 'Townhouse', icon: '🏘️' },
      { value: 'multi_family', label: 'Multi-Family (2-4 units)', icon: '🏗️' },
    ],
  },
  {
    id: 'credit_estimate',
    question: 'What\'s your estimated credit score?',
    type: 'choice',
    options: [
      { value: 'excellent', label: '740+', icon: '🌟', description: 'Excellent' },
      { value: 'good', label: '700-739', icon: '👍', description: 'Good' },
      { value: 'fair', label: '640-699', icon: '📊', description: 'Fair' },
      { value: 'building', label: 'Below 640', icon: '📈', description: 'Building' },
    ],
    hint: 'Better credit often means better rates!',
  },
];

// Common employers for autocomplete
const COMMON_EMPLOYERS = [
  'CMG Home Loans', 'CMG Financial', 'Wells Fargo', 'Bank of America', 'JPMorgan Chase',
  'Citibank', 'US Bank', 'PNC Bank', 'Capital One', 'TD Bank',
  'Amazon', 'Apple', 'Google', 'Microsoft', 'Meta', 'Netflix', 'Tesla',
  'Walmart', 'Target', 'Costco', 'Home Depot', 'Lowes',
  'UnitedHealth Group', 'CVS Health', 'Cigna', 'Anthem', 'Kaiser Permanente',
  'AT&T', 'Verizon', 'T-Mobile', 'Comcast', 'Charter Communications',
  'FedEx', 'UPS', 'USPS', 'DHL',
  'Boeing', 'Lockheed Martin', 'Raytheon', 'Northrop Grumman',
  'General Motors', 'Ford', 'Toyota', 'Honda', 'BMW',
  'Starbucks', 'McDonalds', 'Chipotle', 'Subway',
  'United Airlines', 'Delta Airlines', 'American Airlines', 'Southwest Airlines',
  'Marriott', 'Hilton', 'Hyatt',
  'Disney', 'Warner Bros', 'NBC Universal', 'Paramount',
  'Deloitte', 'PwC', 'EY', 'KPMG', 'Accenture', 'McKinsey',
  'IBM', 'Oracle', 'Salesforce', 'Adobe', 'SAP', 'Intuit',
];

// Planning questions - mortgage priorities and goals (excludes questions already asked in declarations)
const PLANNING_QUESTIONS = {
  mortgagePriorities: {
    question: 'What matters most to you in your new mortgage?',
    hint: 'Select all that apply - this helps us find the best loan structure for you.',
    options: [
      { value: 'lowest_payment', label: 'Lowest Monthly Payment', icon: '💵' },
      { value: 'lowest_rate', label: 'Lowest Interest Rate', icon: '📉' },
      { value: 'fastest_payoff', label: 'Pay Off Fastest', icon: '⚡' },
      { value: 'lowest_total', label: 'Lowest Total Cost', icon: '🎯' },
      { value: 'flexibility', label: 'Maximum Flexibility', icon: '🔄' },
      { value: 'tax_benefits', label: 'Tax Benefits', icon: '📋' },
      { value: 'build_equity', label: 'Build Equity Faster', icon: '📈' },
      { value: 'predictable', label: 'Predictable Payments', icon: '📊' },
    ],
  },
  personalGoals: {
    question: 'What are your personal financial goals?',
    hint: 'Select all that apply - helps us align your refinance with your life plans.',
    options: [
      { value: 'net_worth', label: 'Building Net Worth', icon: '💰' },
      { value: 'larger_home', label: 'Moving to Larger Home', icon: '🏡' },
      { value: 'financial_freedom', label: 'Financial Freedom', icon: '🦅' },
      { value: 'pay_debt', label: 'Paying Off Debt', icon: '✂️' },
      { value: 'retirement', label: 'Saving for Retirement', icon: '🏖️' },
      { value: 'education', label: 'Children\'s Education', icon: '🎓' },
      { value: 'investments', label: 'Investment Portfolio', icon: '📊' },
      { value: 'business', label: 'Starting a Business', icon: '🚀' },
    ],
  },
  financialPhilosophy: {
    question: 'How would you describe your financial approach?',
    options: [
      { value: 'conservative', label: 'Conservative', icon: '🛡️', description: 'Prefer stability and lower risk' },
      { value: 'moderate', label: 'Moderate', icon: '⚖️', description: 'Balance between safety and growth' },
      { value: 'aggressive', label: 'Aggressive', icon: '🚀', description: 'Willing to take risks for higher returns' },
    ],
  },
  professionalNetwork: {
    question: 'Do you currently work with any of these professionals?',
    hint: 'We can coordinate with your existing team for a comprehensive financial plan.',
    options: [
      { value: 'financial_planner', label: 'Financial Planner', icon: '📈' },
      { value: 'accountant', label: 'CPA / Accountant', icon: '🧮' },
      { value: 'insurance_agent', label: 'Life Insurance Agent', icon: '🛡️' },
      { value: 'estate_planner', label: 'Estate Planner', icon: '📜' },
    ],
  },
  taxDeferredRetirement: {
    question: 'Are you currently contributing to a tax-deferred retirement account?',
    hint: '401(k), IRA, or similar retirement savings',
    options: [
      { value: 'yes', label: 'Yes, I contribute regularly', icon: '✅' },
      { value: 'some', label: 'Sometimes / Not maxing out', icon: '🔄' },
      { value: 'no', label: 'Not currently', icon: '❌' },
      { value: 'not_sure', label: 'Not sure', icon: '🤔' },
    ],
  },
};

export default function RefinanceApplication() {
  const { token } = useParams();
  const navigate = useNavigate();
  const isDemoMode = !token || token === 'start';

  // State
  const [currentStage, setCurrentStage] = useState('declarations');
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const [declarations, setDeclarations] = useState({});
  const [profileData, setProfileData] = useState({});
  const [incomeData, setIncomeData] = useState({});
  const [propertyData, setPropertyData] = useState({});
  const [goalsData, setGoalsData] = useState({});
  const [planningData, setPlanningData] = useState({
    mortgagePriorities: [],
    personalGoals: [],
    financialPhilosophy: '',
    professionalNetwork: [],
    taxDeferredRetirement: '',
  });
  const [needsList, setNeedsList] = useState([]);
  const [showMicroWin, setShowMicroWin] = useState(false);
  const [microWinMessage, setMicroWinMessage] = useState('');
  const [isAnimating, setIsAnimating] = useState(false);
  const [selectedTimeSlot, setSelectedTimeSlot] = useState(null);
  const [employerSuggestions, setEmployerSuggestions] = useState([]);
  const [showEmployerDropdown, setShowEmployerDropdown] = useState(false);

  // Filter employers
  const filterEmployers = (input) => {
    if (!input || input.length < 2) {
      setEmployerSuggestions([]);
      setShowEmployerDropdown(false);
      return;
    }
    const filtered = COMMON_EMPLOYERS.filter(emp =>
      emp.toLowerCase().includes(input.toLowerCase())
    ).slice(0, 8);
    setEmployerSuggestions(filtered);
    setShowEmployerDropdown(filtered.length > 0);
  };

  // Calculate progress
  const getProgress = useCallback(() => {
    const stageIndex = STAGES.findIndex(s => s.id === currentStage);
    const stageProgress = (stageIndex / STAGES.length) * 100;
    if (currentStage === 'declarations') {
      const questionProgress = (currentQuestionIndex / DECLARATION_QUESTIONS.length) * (100 / STAGES.length);
      return Math.round(stageProgress + questionProgress);
    }
    return Math.round(stageProgress);
  }, [currentStage, currentQuestionIndex]);

  // Helper to check if a question should be shown based on conditions
  const shouldShowQuestion = useCallback((question, currentDeclarations) => {
    if (!question.showIf) return true;
    const { field, values } = question.showIf;
    return values.includes(currentDeclarations[field]);
  }, []);

  // Get filtered questions based on current declarations
  const getVisibleQuestions = useCallback(() => {
    return DECLARATION_QUESTIONS.filter(q => shouldShowQuestion(q, declarations));
  }, [declarations, shouldShowQuestion]);

  // Update needs list
  useEffect(() => {
    const newNeeds = [];
    newNeeds.push({ id: 'id', label: 'Government-issued ID', category: 'identity' });

    if (declarations.self_employed === 'yes' || declarations.self_employed === 'side_business') {
      newNeeds.push({ id: 'tax_returns', label: '2 years tax returns', category: 'income' });
      newNeeds.push({ id: 'profit_loss', label: 'Year-to-date P&L statement', category: 'income' });

      // If they write off heavily, need 12 months business bank statements
      if (declarations.write_off_expenses === 'yes') {
        newNeeds.push({ id: 'business_bank_statements', label: '12 months business bank statements', category: 'income' });
      }
    } else {
      newNeeds.push({ id: 'paystubs', label: 'Recent pay stubs (30 days)', category: 'income' });
      newNeeds.push({ id: 'w2', label: 'W-2s (last 2 years)', category: 'income' });
    }

    if (declarations.veteran && declarations.veteran !== 'no') {
      newNeeds.push({ id: 'dd214', label: 'DD-214 or Certificate of Eligibility', category: 'military' });
    }

    // IRS payment plan documentation
    if (declarations.irs_balance_owed === 'yes' || declarations.irs_balance_owed === 'payment_plan') {
      newNeeds.push({ id: 'irs_docs', label: 'IRS payment arrangement documentation', category: 'legal' });
    }

    newNeeds.push({ id: 'mortgage_statement', label: 'Current mortgage statement', category: 'property' });
    newNeeds.push({ id: 'hoi', label: 'Homeowners insurance declaration', category: 'property' });
    newNeeds.push({ id: 'bank_statements', label: 'Bank statements (2 months)', category: 'assets' });

    if (declarations.refi_goal === 'cash_out') {
      newNeeds.push({ id: 'home_value', label: 'Recent appraisal or home value estimate', category: 'property' });
    }

    setNeedsList(newNeeds);
  }, [declarations]);

  // Micro-win animation
  const showMicroWinAnimation = (message) => {
    setMicroWinMessage(message);
    setShowMicroWin(true);
    setTimeout(() => setShowMicroWin(false), 2500);
  };

  // Handle declaration answer
  const handleDeclarationAnswer = (questionId, value) => {
    setIsAnimating(true);
    const newDeclarations = { ...declarations, [questionId]: value };
    setDeclarations(newDeclarations);

    setTimeout(() => {
      setIsAnimating(false);

      // Find next visible question
      let nextIndex = currentQuestionIndex + 1;
      while (nextIndex < DECLARATION_QUESTIONS.length) {
        const nextQuestion = DECLARATION_QUESTIONS[nextIndex];
        if (shouldShowQuestion(nextQuestion, newDeclarations)) {
          setCurrentQuestionIndex(nextIndex);
          return;
        }
        nextIndex++;
      }

      // No more visible questions - move to next stage
      showMicroWinAnimation('Great! Your checklist is ready!');
      setTimeout(() => setCurrentStage('profile'), 1500);
    }, 300);
  };

  // Go back to previous visible question
  const goToPrevQuestion = () => {
    let prevIndex = currentQuestionIndex - 1;
    while (prevIndex >= 0) {
      const prevQuestion = DECLARATION_QUESTIONS[prevIndex];
      if (shouldShowQuestion(prevQuestion, declarations)) {
        setCurrentQuestionIndex(prevIndex);
        return;
      }
      prevIndex--;
    }
  };

  // Get current visible question number for display
  const getVisibleQuestionNumber = () => {
    const visibleQuestions = getVisibleQuestions();
    const currentQuestion = DECLARATION_QUESTIONS[currentQuestionIndex];
    return visibleQuestions.findIndex(q => q.id === currentQuestion.id) + 1;
  };

  // Navigation
  const goToNextStage = () => {
    const currentIndex = STAGES.findIndex(s => s.id === currentStage);
    if (currentIndex < STAGES.length - 1) {
      setCurrentStage(STAGES[currentIndex + 1].id);
      showMicroWinAnimation(getStageMicroWin(STAGES[currentIndex].id));
    }
  };

  const goToPrevStage = () => {
    const currentIndex = STAGES.findIndex(s => s.id === currentStage);
    if (currentIndex > 0) {
      setCurrentStage(STAGES[currentIndex - 1].id);
    }
  };

  const getStageMicroWin = (stageId) => {
    const wins = {
      declarations: 'Great start!',
      profile: 'Profile complete!',
      income: 'Income captured!',
      property: 'Property details saved!',
      goals: 'Almost done!',
    };
    return wins[stageId] || 'Section complete!';
  };

  // Render declarations
  const renderDeclarationsStage = () => {
    const question = DECLARATION_QUESTIONS[currentQuestionIndex];
    const visibleQuestions = getVisibleQuestions();
    const visibleQuestionNum = getVisibleQuestionNumber();

    return (
      <div className={`declaration-screen ${isAnimating ? 'animating-out' : 'animating-in'}`}>
        <div className="question-number">
          Question {visibleQuestionNum} of {visibleQuestions.length}
        </div>
        <h2 className="declaration-question">{question.question}</h2>
        {question.hint && <p className="declaration-hint">💡 {question.hint}</p>}
        <div className="declaration-options">
          {question.options.map(option => (
            <button
              key={option.value}
              className={`declaration-option ${declarations[question.id] === option.value ? 'selected' : ''}`}
              onClick={() => handleDeclarationAnswer(question.id, option.value)}
            >
              <span className="option-icon">{option.icon}</span>
              <span className="option-label">{option.label}</span>
              {option.description && <span className="option-description">{option.description}</span>}
            </button>
          ))}
        </div>
        {currentQuestionIndex > 0 && (
          <button className="back-link" onClick={goToPrevQuestion}>
            ← Go back
          </button>
        )}
      </div>
    );
  };

  // Render profile
  const renderProfileStage = () => (
    <div className="stage-content">
      <div className="stage-header">
        <h2>Let's get to know you</h2>
        <p>This should take about 2 minutes</p>
      </div>
      <div className="form-card">
        <div className="form-row">
          <div className="form-group">
            <label>First Name</label>
            <input
              type="text"
              value={profileData.firstName || ''}
              onChange={(e) => setProfileData(prev => ({ ...prev, firstName: e.target.value }))}
              placeholder="Your first name"
              className="fun-input"
            />
          </div>
          <div className="form-group">
            <label>Last Name</label>
            <input
              type="text"
              value={profileData.lastName || ''}
              onChange={(e) => setProfileData(prev => ({ ...prev, lastName: e.target.value }))}
              placeholder="Your last name"
              className="fun-input"
            />
          </div>
        </div>
        <div className="form-row">
          <div className="form-group">
            <label>Email</label>
            <input
              type="email"
              value={profileData.email || ''}
              onChange={(e) => setProfileData(prev => ({ ...prev, email: e.target.value }))}
              placeholder="you@example.com"
              className="fun-input"
            />
          </div>
          <div className="form-group">
            <label>Phone</label>
            <input
              type="tel"
              value={profileData.phone || ''}
              onChange={(e) => setProfileData(prev => ({ ...prev, phone: e.target.value }))}
              placeholder="(555) 123-4567"
              className="fun-input"
            />
          </div>
        </div>
        <div className="form-group">
          <label>Date of Birth</label>
          <input
            type="date"
            value={profileData.dob || ''}
            onChange={(e) => setProfileData(prev => ({ ...prev, dob: e.target.value }))}
            className="fun-input"
          />
        </div>
        {declarations.marital_status === 'married' && (
          <div className="spouse-section">
            <h3>👥 Spouse Information</h3>
            <div className="form-row">
              <div className="form-group">
                <label>Spouse's First Name</label>
                <input
                  type="text"
                  value={profileData.spouseFirstName || ''}
                  onChange={(e) => setProfileData(prev => ({ ...prev, spouseFirstName: e.target.value }))}
                  className="fun-input"
                />
              </div>
              <div className="form-group">
                <label>Spouse's Last Name</label>
                <input
                  type="text"
                  value={profileData.spouseLastName || ''}
                  onChange={(e) => setProfileData(prev => ({ ...prev, spouseLastName: e.target.value }))}
                  className="fun-input"
                />
              </div>
            </div>
          </div>
        )}
      </div>
      <div className="stage-navigation">
        <button className="btn-back" onClick={goToPrevStage}>← Back</button>
        <button className="btn-continue" onClick={goToNextStage}>Continue →</button>
      </div>
    </div>
  );

  // Render income
  const renderIncomeStage = () => {
    const isSelfEmployed = declarations.self_employed === 'yes' || declarations.self_employed === 'side_business';

    return (
      <div className="stage-content">
        <div className="stage-header">
          <h2>Tell us about your income</h2>
          <p>This helps determine your refinance options</p>
        </div>
        <div className="income-type-selector">
          <h3>How do you earn income?</h3>
          <div className="income-cards">
            <div
              className={`income-card ${incomeData.primaryType === 'employed' ? 'selected' : ''}`}
              onClick={() => setIncomeData(prev => ({ ...prev, primaryType: 'employed' }))}
            >
              <span className="card-icon">👔</span>
              <span className="card-label">Employed</span>
              <span className="card-desc">W-2 employee</span>
            </div>
            <div
              className={`income-card ${incomeData.primaryType === 'self_employed' ? 'selected' : ''}`}
              onClick={() => setIncomeData(prev => ({ ...prev, primaryType: 'self_employed' }))}
            >
              <span className="card-icon">🏢</span>
              <span className="card-label">Self-Employed</span>
              <span className="card-desc">Business owner</span>
            </div>
            <div
              className={`income-card ${incomeData.primaryType === 'retired' ? 'selected' : ''}`}
              onClick={() => setIncomeData(prev => ({ ...prev, primaryType: 'retired' }))}
            >
              <span className="card-icon">🏖️</span>
              <span className="card-label">Retired</span>
              <span className="card-desc">Pension/SS</span>
            </div>
          </div>
        </div>

        {incomeData.primaryType === 'employed' && (
          <div className="form-card">
            <h3>Employment Details</h3>
            <div className="form-group employer-autocomplete">
              <label>Employer Name</label>
              <input
                type="text"
                value={incomeData.employerName || ''}
                onChange={(e) => {
                  setIncomeData(prev => ({ ...prev, employerName: e.target.value }));
                  filterEmployers(e.target.value);
                }}
                onFocus={() => incomeData.employerName?.length >= 2 && filterEmployers(incomeData.employerName)}
                onBlur={() => setTimeout(() => setShowEmployerDropdown(false), 200)}
                placeholder="Start typing company name..."
                className="fun-input"
                autoComplete="off"
              />
              {showEmployerDropdown && employerSuggestions.length > 0 && (
                <div className="employer-dropdown">
                  {employerSuggestions.map((emp, idx) => (
                    <div
                      key={idx}
                      className="employer-option"
                      onMouseDown={() => {
                        setIncomeData(prev => ({ ...prev, employerName: emp }));
                        setShowEmployerDropdown(false);
                      }}
                    >
                      <span className="employer-icon">🏢</span>
                      {emp}
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>Job Title</label>
                <input
                  type="text"
                  value={incomeData.jobTitle || ''}
                  onChange={(e) => setIncomeData(prev => ({ ...prev, jobTitle: e.target.value }))}
                  className="fun-input"
                />
              </div>
              <div className="form-group">
                <label>Years There</label>
                <input
                  type="number"
                  value={incomeData.yearsAtJob || ''}
                  onChange={(e) => setIncomeData(prev => ({ ...prev, yearsAtJob: e.target.value }))}
                  className="fun-input"
                  min="0"
                />
              </div>
            </div>
            <div className="form-group">
              <label>Annual Base Salary</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={incomeData.annualSalary || ''}
                  onChange={(e) => setIncomeData(prev => ({ ...prev, annualSalary: e.target.value }))}
                  className="fun-input"
                  placeholder="0"
                />
              </div>
            </div>
          </div>
        )}

        {(incomeData.primaryType === 'self_employed' || isSelfEmployed) && (
          <div className="form-card">
            <h3>🏢 Business Details</h3>
            <div className="form-group">
              <label>Business Name</label>
              <input
                type="text"
                value={incomeData.businessName || ''}
                onChange={(e) => setIncomeData(prev => ({ ...prev, businessName: e.target.value }))}
                className="fun-input"
              />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>Business Type</label>
                <select
                  value={incomeData.businessType || ''}
                  onChange={(e) => setIncomeData(prev => ({ ...prev, businessType: e.target.value }))}
                  className="fun-input"
                >
                  <option value="">Select...</option>
                  <option value="sole_prop">Sole Proprietorship</option>
                  <option value="llc">LLC</option>
                  <option value="s_corp">S-Corporation</option>
                  <option value="c_corp">C-Corporation</option>
                </select>
              </div>
              <div className="form-group">
                <label>Years in Business</label>
                <input
                  type="number"
                  value={incomeData.yearsInBusiness || ''}
                  onChange={(e) => setIncomeData(prev => ({ ...prev, yearsInBusiness: e.target.value }))}
                  className="fun-input"
                  min="0"
                />
              </div>
            </div>
            <div className="form-group">
              <label>Annual Net Income</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={incomeData.businessIncome || ''}
                  onChange={(e) => setIncomeData(prev => ({ ...prev, businessIncome: e.target.value }))}
                  className="fun-input"
                />
              </div>
            </div>
          </div>
        )}

        <div className="stage-navigation">
          <button className="btn-back" onClick={goToPrevStage}>← Back</button>
          <button className="btn-continue" onClick={goToNextStage}>Continue →</button>
        </div>
      </div>
    );
  };

  // Render property (refinance-specific - current home)
  const renderPropertyStage = () => (
    <div className="stage-content">
      <div className="stage-header">
        <h2>Your Current Home</h2>
        <p>Tell us about the property you want to refinance</p>
      </div>

      <div className="form-card">
        <div className="form-group">
          <label>Property Address</label>
          <input
            type="text"
            value={propertyData.address || ''}
            onChange={(e) => setPropertyData(prev => ({ ...prev, address: e.target.value }))}
            placeholder="Enter your home address..."
            className="fun-input"
          />
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Estimated Home Value</label>
            <div className="input-with-prefix">
              <span className="input-prefix">$</span>
              <input
                type="number"
                value={propertyData.homeValue || ''}
                onChange={(e) => setPropertyData(prev => ({ ...prev, homeValue: e.target.value }))}
                className="fun-input"
                placeholder="0"
              />
            </div>
            <span className="input-hint">🏠 Based on recent comparable sales</span>
          </div>
          <div className="form-group">
            <label>Current Mortgage Balance</label>
            <div className="input-with-prefix">
              <span className="input-prefix">$</span>
              <input
                type="number"
                value={propertyData.mortgageBalance || ''}
                onChange={(e) => setPropertyData(prev => ({ ...prev, mortgageBalance: e.target.value }))}
                className="fun-input"
                placeholder="0"
              />
            </div>
          </div>
        </div>

        {/* Equity Calculator */}
        {propertyData.homeValue && propertyData.mortgageBalance && (
          <div className="equity-display">
            <div className="equity-item">
              <span className="equity-label">Your Equity</span>
              <strong className="equity-value">
                ${(parseFloat(propertyData.homeValue) - parseFloat(propertyData.mortgageBalance)).toLocaleString()}
              </strong>
            </div>
            <div className="equity-item">
              <span className="equity-label">Loan-to-Value (LTV)</span>
              <strong className="equity-value">
                {((parseFloat(propertyData.mortgageBalance) / parseFloat(propertyData.homeValue)) * 100).toFixed(1)}%
              </strong>
            </div>
          </div>
        )}

        <div className="form-row">
          <div className="form-group">
            <label>Current Monthly Payment</label>
            <div className="input-with-prefix">
              <span className="input-prefix">$</span>
              <input
                type="number"
                value={propertyData.monthlyPayment || ''}
                onChange={(e) => setPropertyData(prev => ({ ...prev, monthlyPayment: e.target.value }))}
                className="fun-input"
                placeholder="0"
              />
            </div>
          </div>
          <div className="form-group">
            <label>Current Interest Rate</label>
            <div className="input-with-prefix">
              <input
                type="number"
                step="0.125"
                value={propertyData.currentRate || ''}
                onChange={(e) => setPropertyData(prev => ({ ...prev, currentRate: e.target.value }))}
                className="fun-input"
                placeholder="0.000"
              />
              <span className="input-suffix">%</span>
            </div>
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Original Loan Date</label>
            <input
              type="month"
              value={propertyData.loanDate || ''}
              onChange={(e) => setPropertyData(prev => ({ ...prev, loanDate: e.target.value }))}
              className="fun-input"
            />
          </div>
          <div className="form-group">
            <label>Current Loan Term</label>
            <select
              value={propertyData.currentTerm || ''}
              onChange={(e) => setPropertyData(prev => ({ ...prev, currentTerm: e.target.value }))}
              className="fun-input"
            >
              <option value="">Select...</option>
              <option value="30">30 Year</option>
              <option value="25">25 Year</option>
              <option value="20">20 Year</option>
              <option value="15">15 Year</option>
              <option value="10">10 Year</option>
            </select>
          </div>
        </div>

        <div className="form-group">
          <label>Is there a second mortgage or HELOC?</label>
          <div className="income-cards" style={{ gridTemplateColumns: '1fr 1fr' }}>
            <div
              className={`income-card ${propertyData.hasSecondLien === 'yes' ? 'selected' : ''}`}
              onClick={() => setPropertyData(prev => ({ ...prev, hasSecondLien: 'yes' }))}
            >
              <span className="card-icon">📋</span>
              <span className="card-label">Yes</span>
            </div>
            <div
              className={`income-card ${propertyData.hasSecondLien === 'no' ? 'selected' : ''}`}
              onClick={() => setPropertyData(prev => ({ ...prev, hasSecondLien: 'no' }))}
            >
              <span className="card-icon">✓</span>
              <span className="card-label">No</span>
            </div>
          </div>
        </div>

        {propertyData.hasSecondLien === 'yes' && (
          <div className="form-group">
            <label>Second Mortgage/HELOC Balance</label>
            <div className="input-with-prefix">
              <span className="input-prefix">$</span>
              <input
                type="number"
                value={propertyData.secondLienBalance || ''}
                onChange={(e) => setPropertyData(prev => ({ ...prev, secondLienBalance: e.target.value }))}
                className="fun-input"
                placeholder="0"
              />
            </div>
          </div>
        )}
      </div>

      <div className="stage-navigation">
        <button className="btn-back" onClick={goToPrevStage}>← Back</button>
        <button className="btn-continue" onClick={goToNextStage}>Continue →</button>
      </div>
    </div>
  );

  // Render goals (refinance-specific)
  const renderGoalsStage = () => {
    const isVeteran = declarations.veteran === 'yes' || declarations.veteran === 'active';
    const currentLoanIsVA = declarations.current_loan_type === 'va';
    const currentLoanIsFHA = declarations.current_loan_type === 'fha';
    const wantsCashOut = declarations.refi_goal === 'cash_out';

    // Calculate potential cash out
    const equity = (parseFloat(propertyData.homeValue) || 0) - (parseFloat(propertyData.mortgageBalance) || 0);
    const maxCashOut = Math.max(0, equity * 0.8); // Assume 80% LTV max

    return (
      <div className="stage-content">
        <div className="stage-header">
          <h2>Your Refinance Goals</h2>
          <p>Let's find the best option for you</p>
        </div>

        {/* Refinance Type Selection */}
        <div className="form-card">
          <h3>What type of refinance?</h3>
          <div className="income-cards">
            <div
              className={`income-card ${goalsData.refiType === 'rate_term' ? 'selected' : ''}`}
              onClick={() => setGoalsData(prev => ({ ...prev, refiType: 'rate_term' }))}
            >
              <span className="card-icon">📉</span>
              <span className="card-label">Rate & Term</span>
              <span className="card-desc">Lower rate or change term</span>
            </div>
            <div
              className={`income-card ${goalsData.refiType === 'cash_out' ? 'selected' : ''}`}
              onClick={() => setGoalsData(prev => ({ ...prev, refiType: 'cash_out' }))}
            >
              <span className="card-icon">💰</span>
              <span className="card-label">Cash-Out</span>
              <span className="card-desc">Get cash from equity</span>
            </div>
            {(isVeteran || currentLoanIsVA) && (
              <div
                className={`income-card ${goalsData.refiType === 'va_irrrl' ? 'selected' : ''}`}
                onClick={() => setGoalsData(prev => ({ ...prev, refiType: 'va_irrrl' }))}
              >
                <span className="card-icon">🎖️</span>
                <span className="card-label">VA Streamline</span>
                <span className="card-desc">Fast, limited docs</span>
              </div>
            )}
            {currentLoanIsFHA && (
              <div
                className={`income-card ${goalsData.refiType === 'fha_streamline' ? 'selected' : ''}`}
                onClick={() => setGoalsData(prev => ({ ...prev, refiType: 'fha_streamline' }))}
              >
                <span className="card-icon">🏛️</span>
                <span className="card-label">FHA Streamline</span>
                <span className="card-desc">No appraisal needed</span>
              </div>
            )}
          </div>
        </div>

        {/* Cash-Out Amount */}
        {goalsData.refiType === 'cash_out' && (
          <div className="form-card">
            <h3>💵 Cash-Out Amount</h3>
            <p className="section-hint">
              Based on your equity, you may be able to access up to <strong>${maxCashOut.toLocaleString()}</strong>
            </p>
            <div className="form-group">
              <label>How much cash do you need?</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={goalsData.cashOutAmount || ''}
                  onChange={(e) => setGoalsData(prev => ({ ...prev, cashOutAmount: e.target.value }))}
                  className="fun-input"
                  placeholder="0"
                  max={maxCashOut}
                />
              </div>
            </div>
            <div className="form-group">
              <label>What will you use the cash for?</label>
              <select
                value={goalsData.cashOutPurpose || ''}
                onChange={(e) => setGoalsData(prev => ({ ...prev, cashOutPurpose: e.target.value }))}
                className="fun-input"
              >
                <option value="">Select...</option>
                <option value="home_improvement">Home Improvements</option>
                <option value="debt_consolidation">Debt Consolidation</option>
                <option value="education">Education</option>
                <option value="investment">Investment</option>
                <option value="emergency_fund">Emergency Fund</option>
                <option value="other">Other</option>
              </select>
            </div>
          </div>
        )}

        {/* New Loan Term */}
        <div className="form-card">
          <h3>New Loan Term</h3>
          <div className="income-cards">
            <div
              className={`income-card ${goalsData.newTerm === '30' ? 'selected' : ''}`}
              onClick={() => setGoalsData(prev => ({ ...prev, newTerm: '30' }))}
            >
              <span className="card-icon">📅</span>
              <span className="card-label">30 Year</span>
              <span className="card-desc">Lowest payment</span>
            </div>
            <div
              className={`income-card ${goalsData.newTerm === '20' ? 'selected' : ''}`}
              onClick={() => setGoalsData(prev => ({ ...prev, newTerm: '20' }))}
            >
              <span className="card-icon">⏱️</span>
              <span className="card-label">20 Year</span>
              <span className="card-desc">Balance</span>
            </div>
            <div
              className={`income-card ${goalsData.newTerm === '15' ? 'selected' : ''}`}
              onClick={() => setGoalsData(prev => ({ ...prev, newTerm: '15' }))}
            >
              <span className="card-icon">🚀</span>
              <span className="card-label">15 Year</span>
              <span className="card-desc">Pay off faster</span>
            </div>
          </div>
        </div>

        {/* Loan Program Selection */}
        <div className="form-card">
          <h3>Recommended Programs</h3>
          <div className="program-cards">
            {isVeteran && (
              <div
                className={`program-card va ${goalsData.program === 'va' ? 'selected' : ''}`}
                onClick={() => setGoalsData(prev => ({ ...prev, program: 'va' }))}
              >
                <span className="program-badge">🎖️ FOR YOU</span>
                <span className="program-name">VA</span>
                <span className="program-rate">~6.0% APR</span>
                <span className="program-note">No PMI, great rates</span>
              </div>
            )}
            <div
              className={`program-card ${goalsData.program === 'conventional' ? 'selected' : ''}`}
              onClick={() => setGoalsData(prev => ({ ...prev, program: 'conventional' }))}
            >
              <span className="program-name">Conventional</span>
              <span className="program-rate">~6.5% APR</span>
              <span className="program-note">Best for good credit</span>
            </div>
            <div
              className={`program-card ${goalsData.program === 'fha' ? 'selected' : ''}`}
              onClick={() => setGoalsData(prev => ({ ...prev, program: 'fha' }))}
            >
              <span className="program-name">FHA</span>
              <span className="program-rate">~6.25% APR</span>
              <span className="program-note">Flexible requirements</span>
            </div>
          </div>
        </div>

        <div className="stage-navigation">
          <button className="btn-back" onClick={goToPrevStage}>← Back</button>
          <button className="btn-continue" onClick={goToNextStage}>Continue →</button>
        </div>
      </div>
    );
  };

  // Render review
  const renderReviewStage = () => {
    const newLoanAmount = goalsData.refiType === 'cash_out'
      ? (parseFloat(propertyData.mortgageBalance) || 0) + (parseFloat(goalsData.cashOutAmount) || 0)
      : (parseFloat(propertyData.mortgageBalance) || 0);

    return (
      <div className="stage-content">
        <div className="stage-header">
          <h2>Review Your Application</h2>
          <p>Let's make sure everything looks good!</p>
        </div>

        <div className="review-sections">
          <div className="review-section">
            <div className="section-header">
              <h3>👤 Your Profile</h3>
              <button className="edit-link" onClick={() => setCurrentStage('profile')}>Edit</button>
            </div>
            <div className="section-content">
              <p><strong>Name:</strong> {profileData.firstName} {profileData.lastName}</p>
              <p><strong>Email:</strong> {profileData.email}</p>
              <p><strong>Phone:</strong> {profileData.phone}</p>
            </div>
          </div>

          <div className="review-section">
            <div className="section-header">
              <h3>💼 Income</h3>
              <button className="edit-link" onClick={() => setCurrentStage('income')}>Edit</button>
            </div>
            <div className="section-content">
              <p><strong>Type:</strong> {incomeData.primaryType}</p>
              {incomeData.employerName && <p><strong>Employer:</strong> {incomeData.employerName}</p>}
              {incomeData.annualSalary && <p><strong>Annual Income:</strong> ${parseFloat(incomeData.annualSalary).toLocaleString()}</p>}
            </div>
          </div>

          <div className="review-section">
            <div className="section-header">
              <h3>🏠 Current Home</h3>
              <button className="edit-link" onClick={() => setCurrentStage('property')}>Edit</button>
            </div>
            <div className="section-content">
              <p><strong>Address:</strong> {propertyData.address}</p>
              <p><strong>Home Value:</strong> ${parseFloat(propertyData.homeValue || 0).toLocaleString()}</p>
              <p><strong>Current Balance:</strong> ${parseFloat(propertyData.mortgageBalance || 0).toLocaleString()}</p>
              <p><strong>Current Rate:</strong> {propertyData.currentRate}%</p>
            </div>
          </div>

          <div className="review-section">
            <div className="section-header">
              <h3>🎯 Refinance Details</h3>
              <button className="edit-link" onClick={() => setCurrentStage('goals')}>Edit</button>
            </div>
            <div className="section-content">
              <p><strong>Type:</strong> {goalsData.refiType === 'cash_out' ? 'Cash-Out Refinance' : 'Rate & Term'}</p>
              <p><strong>New Loan Amount:</strong> ${newLoanAmount.toLocaleString()}</p>
              {goalsData.cashOutAmount && <p><strong>Cash Out:</strong> ${parseFloat(goalsData.cashOutAmount).toLocaleString()}</p>}
              <p><strong>New Term:</strong> {goalsData.newTerm} Years</p>
              <p><strong>Program:</strong> {goalsData.program?.toUpperCase()}</p>
            </div>
          </div>
        </div>

        <div className="needs-list-section">
          <h3>📋 Your Document Checklist</h3>
          <p>We'll need these documents to process your refinance:</p>
          <ul className="needs-list">
            {needsList.map(item => (
              <li key={item.id} className="needs-item">
                <span className="needs-icon">📄</span>
                <span className="needs-label">{item.label}</span>
                <span className={`needs-category ${item.category}`}>{item.category}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="stage-navigation">
          <button className="btn-back" onClick={goToPrevStage}>← Back</button>
          <button className="btn-continue" onClick={goToNextStage}>Continue →</button>
        </div>
      </div>
    );
  };

  // Toggle multi-select options for planning
  const togglePlanningOption = (field, value) => {
    setPlanningData(prev => {
      const current = prev[field] || [];
      if (current.includes(value)) {
        return { ...prev, [field]: current.filter(v => v !== value) };
      } else {
        return { ...prev, [field]: [...current, value] };
      }
    });
  };

  // Render planning stage with mortgage questionnaire
  const renderPlanningStage = () => (
    <div className="stage-content planning-stage">
      <div className="stage-header">
        <h2>Let's Plan Your Refinance</h2>
        <p>A few quick questions to help us find the perfect loan for your situation</p>
      </div>

      {/* Mortgage Priorities - Multi-select */}
      <div className="form-card planning-section">
        <h3>{PLANNING_QUESTIONS.mortgagePriorities.question}</h3>
        <p className="section-hint">{PLANNING_QUESTIONS.mortgagePriorities.hint}</p>
        <div className="multi-select-grid">
          {PLANNING_QUESTIONS.mortgagePriorities.options.map(option => (
            <button
              key={option.value}
              className={`multi-select-option ${planningData.mortgagePriorities.includes(option.value) ? 'selected' : ''}`}
              onClick={() => togglePlanningOption('mortgagePriorities', option.value)}
            >
              <span className="option-icon">{option.icon}</span>
              <span className="option-label">{option.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Personal Goals - Multi-select */}
      <div className="form-card planning-section">
        <h3>{PLANNING_QUESTIONS.personalGoals.question}</h3>
        <p className="section-hint">{PLANNING_QUESTIONS.personalGoals.hint}</p>
        <div className="multi-select-grid">
          {PLANNING_QUESTIONS.personalGoals.options.map(option => (
            <button
              key={option.value}
              className={`multi-select-option ${planningData.personalGoals.includes(option.value) ? 'selected' : ''}`}
              onClick={() => togglePlanningOption('personalGoals', option.value)}
            >
              <span className="option-icon">{option.icon}</span>
              <span className="option-label">{option.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Financial Philosophy - Single select */}
      <div className="form-card planning-section">
        <h3>{PLANNING_QUESTIONS.financialPhilosophy.question}</h3>
        <div className="philosophy-options">
          {PLANNING_QUESTIONS.financialPhilosophy.options.map(option => (
            <button
              key={option.value}
              className={`philosophy-option ${planningData.financialPhilosophy === option.value ? 'selected' : ''}`}
              onClick={() => setPlanningData(prev => ({ ...prev, financialPhilosophy: option.value }))}
            >
              <span className="option-icon">{option.icon}</span>
              <span className="option-label">{option.label}</span>
              <span className="option-description">{option.description}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Tax-Deferred Retirement - Single select */}
      <div className="form-card planning-section">
        <h3>{PLANNING_QUESTIONS.taxDeferredRetirement.question}</h3>
        <p className="section-hint">{PLANNING_QUESTIONS.taxDeferredRetirement.hint}</p>
        <div className="single-select-options">
          {PLANNING_QUESTIONS.taxDeferredRetirement.options.map(option => (
            <button
              key={option.value}
              className={`single-select-option ${planningData.taxDeferredRetirement === option.value ? 'selected' : ''}`}
              onClick={() => setPlanningData(prev => ({ ...prev, taxDeferredRetirement: option.value }))}
            >
              <span className="option-icon">{option.icon}</span>
              <span className="option-label">{option.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Professional Network - Multi-select */}
      <div className="form-card planning-section">
        <h3>{PLANNING_QUESTIONS.professionalNetwork.question}</h3>
        <p className="section-hint">{PLANNING_QUESTIONS.professionalNetwork.hint}</p>
        <div className="multi-select-grid compact">
          {PLANNING_QUESTIONS.professionalNetwork.options.map(option => (
            <button
              key={option.value}
              className={`multi-select-option ${planningData.professionalNetwork.includes(option.value) ? 'selected' : ''}`}
              onClick={() => togglePlanningOption('professionalNetwork', option.value)}
            >
              <span className="option-icon">{option.icon}</span>
              <span className="option-label">{option.label}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="stage-navigation">
        <button className="btn-back" onClick={goToPrevStage}>← Back</button>
        <button className="btn-continue" onClick={goToNextStage}>Continue →</button>
      </div>
    </div>
  );

  // Generate available time slots
  const generateTimeSlots = () => {
    const slots = [];
    const today = new Date();
    for (let d = 1; d <= 5; d++) {
      const date = new Date(today);
      date.setDate(today.getDate() + d);
      if (date.getDay() === 0 || date.getDay() === 6) continue; // Skip weekends

      ['9:00 AM', '10:30 AM', '1:00 PM', '2:30 PM', '4:00 PM'].forEach(time => {
        slots.push({
          id: `${date.toISOString().split('T')[0]}-${time}`,
          date: date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }),
          time: time,
        });
      });
    }
    return slots.slice(0, 12);
  };

  // Render schedule stage with video and calendar
  const renderScheduleStage = () => {
    const timeSlots = generateTimeSlots();

    return (
      <div className="stage-content scheduling-page">
        <div className="scheduling-header">
          <h2>You're Almost Done!</h2>
          <p>Watch this quick video to learn what happens next, then schedule your consultation.</p>
        </div>

        <div className="video-section">
          <div className="video-container">
            <div className="video-placeholder">
              <span className="play-icon">▶️</span>
              <p>What to Expect: Your Refinance Journey</p>
            </div>
          </div>

          <div className="next-steps-list">
            <h3>📋 What Happens Next</h3>
            <ol>
              <li><strong>Consultation Call</strong> - We'll review your refinance goals and answer questions</li>
              <li><strong>Rate Lock</strong> - Lock in your new rate once you're ready</li>
              <li><strong>Document Collection</strong> - Upload your documents through our secure portal</li>
              <li><strong>Appraisal</strong> - We'll order and coordinate your home appraisal</li>
              <li><strong>Closing</strong> - Sign your new loan docs and start saving!</li>
            </ol>
          </div>
        </div>

        <div className="calendar-section">
          <h3>Schedule Your Consultation</h3>

          <div className="calendar-placeholder">
            <span className="cal-icon">📅</span>
            <h4>Pick a Time That Works For You</h4>
            <p>Select an available time slot below for your 15-minute consultation call</p>

            <div className="time-slots">
              {timeSlots.map(slot => (
                <div
                  key={slot.id}
                  className={`time-slot ${selectedTimeSlot === slot.id ? 'selected' : ''}`}
                  onClick={() => setSelectedTimeSlot(slot.id)}
                >
                  <div className="time-slot-time">{slot.time}</div>
                  <div className="time-slot-date">{slot.date}</div>
                </div>
              ))}
            </div>

            <button
              className="btn-schedule"
              disabled={!selectedTimeSlot}
              onClick={() => showMicroWinAnimation('Consultation Scheduled! 🎉 Check your email for confirmation.')}
            >
              {selectedTimeSlot ? 'Confirm Appointment' : 'Select a Time Slot'}
            </button>
          </div>
        </div>

        <div className="stage-navigation">
          <button className="btn-back" onClick={goToPrevStage}>← Back</button>
        </div>
      </div>
    );
  };

  // Render current stage
  const renderStage = () => {
    switch (currentStage) {
      case 'declarations': return renderDeclarationsStage();
      case 'profile': return renderProfileStage();
      case 'income': return renderIncomeStage();
      case 'property': return renderPropertyStage();
      case 'goals': return renderGoalsStage();
      case 'review': return renderReviewStage();
      case 'planning': return renderPlanningStage();
      case 'schedule': return renderScheduleStage();
      default: return renderDeclarationsStage();
    }
  };

  return (
    <div className="adaptive-urla">
      {isDemoMode && (
        <div className="demo-banner" style={{ background: 'linear-gradient(135deg, #218D8D 0%, #1a7070 100%)' }}>
          <span className="demo-badge">DEMO</span>
          Refinance Application
        </div>
      )}

      <div className="progress-header">
        <div className="progress-chapters">
          {STAGES.map((stage, index) => {
            const currentIndex = STAGES.findIndex(s => s.id === currentStage);
            const isComplete = index < currentIndex;
            const isCurrent = index === currentIndex;
            return (
              <div
                key={stage.id}
                className={`progress-chapter ${isComplete ? 'complete' : ''} ${isCurrent ? 'current' : ''}`}
                onClick={() => isComplete && setCurrentStage(stage.id)}
              >
                <span className="chapter-icon">{isComplete ? '✓' : stage.icon}</span>
                <span className="chapter-label">{stage.label}</span>
              </div>
            );
          })}
        </div>
        <div className="progress-bar-container">
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${getProgress()}%` }}></div>
          </div>
          <span className="progress-text">{getProgress()}% Complete</span>
        </div>
      </div>

      {showMicroWin && (
        <div className="micro-win-toast">
          <span className="micro-win-icon">🎉</span>
          <span className="micro-win-message">{microWinMessage}</span>
        </div>
      )}

      <main className="urla-content">
        {renderStage()}
      </main>

      {currentStage !== 'declarations' && needsList.length > 0 && (
        <aside className="needs-sidebar">
          <h4>📋 Your Checklist</h4>
          <ul>
            {needsList.slice(0, 5).map(item => (
              <li key={item.id}>{item.label}</li>
            ))}
          </ul>
          {needsList.length > 5 && (
            <span className="more-items">+{needsList.length - 5} more</span>
          )}
        </aside>
      )}
    </div>
  );
}
