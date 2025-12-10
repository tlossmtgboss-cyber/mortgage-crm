import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import './AdaptiveURLA.css';

/**
 * AdaptiveURLA - The Reimagined URLA: Intelligent, Adaptive, Fun
 *
 * 7-Stage Adaptive Flow:
 * 1. Declarations First - Unlock conditional logic, eliminate redundant questions
 * 2. Fun Profile - TurboTax-style basics with micro-interactions
 * 3. Smart Income Engine - Conditional branching based on declarations
 * 4. Smart Asset Engine - Plaid, gift funds module
 * 5. Real Estate Section - Only if declared
 * 6. Loan Details - Purchase vs refi, program selection
 * 7. Final Declarations & Legal - Summary review
 */

// Stage configuration with icons and fun names
const STAGES = [
  { id: 'declarations', label: 'Your Story', icon: '🧩', description: 'Quick questions to personalize your journey' },
  { id: 'profile', label: 'About You', icon: '👤', description: 'The basics about you' },
  { id: 'income', label: 'Your Income', icon: '💼', description: 'How you earn' },
  { id: 'assets', label: 'Your Assets', icon: '💰', description: 'What you have saved' },
  { id: 'realestate', label: 'Your Homes', icon: '🏡', description: 'Properties you own' },
  { id: 'loan', label: 'Your Loan', icon: '🎯', description: 'What you need' },
  { id: 'review', label: 'Final Review', icon: '✅', description: 'Confirm and submit' },
];

// Declaration questions that unlock conditional logic
const DECLARATION_QUESTIONS = [
  {
    id: 'marital_status',
    question: 'Are you married?',
    type: 'choice',
    options: [
      { value: 'married', label: 'Yes, married', icon: '💑' },
      { value: 'single', label: 'Single', icon: '👤' },
      { value: 'divorced', label: 'Divorced', icon: '📝' },
      { value: 'widowed', label: 'Widowed', icon: '🕊️' },
    ],
    unlocks: ['spouse_section'],
  },
  {
    id: 'citizenship',
    question: 'What is your citizenship status?',
    type: 'choice',
    options: [
      { value: 'us_citizen', label: 'U.S. Citizen', icon: '🇺🇸' },
      { value: 'permanent_resident', label: 'Permanent Resident', icon: '🪪' },
      { value: 'non_permanent', label: 'Non-Permanent Resident', icon: '📋' },
    ],
    unlocks: ['visa_section'],
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
    unlocks: ['va_section'],
    hint: 'Veterans may qualify for VA loans with $0 down payment!',
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
    unlocks: ['business_section'],
    hint: 'This helps us know what income documents you\'ll need.',
  },
  {
    id: 'owns_real_estate',
    question: 'Do you currently own any real estate?',
    type: 'choice',
    options: [
      { value: 'primary', label: 'Yes, my primary home', icon: '🏠' },
      { value: 'multiple', label: 'Yes, multiple properties', icon: '🏘️' },
      { value: 'investment', label: 'Yes, investment property', icon: '📈' },
      { value: 'no', label: 'No, I\'m a first-time buyer', icon: '🎉' },
    ],
    unlocks: ['reo_section'],
  },
  {
    id: 'gift_funds',
    question: 'Will you use gift funds for your down payment?',
    type: 'choice',
    options: [
      { value: 'yes', label: 'Yes, receiving a gift', icon: '🎁' },
      { value: 'maybe', label: 'Maybe, not sure yet', icon: '🤔' },
      { value: 'no', label: 'No, using my own funds', icon: '💵' },
    ],
    unlocks: ['gift_section'],
    hint: 'Gift funds from family are totally okay!',
  },
  {
    id: 'bankruptcy_history',
    question: 'Have you had a bankruptcy or foreclosure in the past 7 years?',
    type: 'choice',
    options: [
      { value: 'bankruptcy', label: 'Yes, bankruptcy', icon: '📋' },
      { value: 'foreclosure', label: 'Yes, foreclosure', icon: '🏚️' },
      { value: 'both', label: 'Both', icon: '📑' },
      { value: 'no', label: 'No', icon: '✅' },
    ],
    unlocks: ['bankruptcy_section'],
    hint: 'Don\'t worry - many people qualify even with past events.',
  },
  {
    id: 'alimony_obligations',
    question: 'Do you pay alimony or child support?',
    type: 'choice',
    options: [
      { value: 'alimony', label: 'Yes, alimony', icon: '💳' },
      { value: 'child_support', label: 'Yes, child support', icon: '👶' },
      { value: 'both', label: 'Both', icon: '📝' },
      { value: 'no', label: 'No', icon: '➡️' },
    ],
    unlocks: ['obligations_section'],
  },
  {
    id: 'occupancy_intent',
    question: 'How will you use this property?',
    type: 'choice',
    options: [
      { value: 'primary', label: 'Primary Residence', icon: '🏠', description: 'I\'ll live here' },
      { value: 'secondary', label: 'Second Home', icon: '🏖️', description: 'Vacation property' },
      { value: 'investment', label: 'Investment', icon: '📈', description: 'Rental income' },
    ],
    unlocks: ['investment_section'],
  },
];

export default function AdaptiveURLA() {
  const { token } = useParams();
  const navigate = useNavigate();

  // Demo mode detection
  const isDemoMode = !token || token === 'start';

  // Core state
  const [currentStage, setCurrentStage] = useState('declarations');
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const [declarations, setDeclarations] = useState({});
  const [profileData, setProfileData] = useState({});
  const [incomeData, setIncomeData] = useState({});
  const [assetData, setAssetData] = useState({});
  const [realEstateData, setRealEstateData] = useState({});
  const [loanData, setLoanData] = useState({});
  const [needsList, setNeedsList] = useState([]);
  const [showMicroWin, setShowMicroWin] = useState(false);
  const [microWinMessage, setMicroWinMessage] = useState('');
  const [isAnimating, setIsAnimating] = useState(false);

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

  // Update needs list based on declarations
  useEffect(() => {
    const newNeeds = [];

    // Base documents everyone needs
    newNeeds.push({ id: 'id', label: 'Government-issued ID', category: 'identity' });

    // Conditional documents based on declarations
    if (declarations.self_employed === 'yes' || declarations.self_employed === 'side_business') {
      newNeeds.push({ id: 'tax_returns', label: '2 years tax returns', category: 'income' });
      newNeeds.push({ id: 'profit_loss', label: 'Year-to-date P&L statement', category: 'income' });
      newNeeds.push({ id: 'business_license', label: 'Business license', category: 'income' });
    } else if (declarations.self_employed === 'no') {
      newNeeds.push({ id: 'paystubs', label: 'Recent pay stubs (30 days)', category: 'income' });
      newNeeds.push({ id: 'w2', label: 'W-2s (last 2 years)', category: 'income' });
    }

    if (declarations.gift_funds === 'yes') {
      newNeeds.push({ id: 'gift_letter', label: 'Gift letter from donor', category: 'assets' });
      newNeeds.push({ id: 'gift_source', label: 'Donor bank statements', category: 'assets' });
    }

    if (declarations.owns_real_estate && declarations.owns_real_estate !== 'no') {
      newNeeds.push({ id: 'mortgage_statement', label: 'Current mortgage statement(s)', category: 'property' });
      newNeeds.push({ id: 'hoa', label: 'HOA statement (if applicable)', category: 'property' });
    }

    if (declarations.bankruptcy_history && declarations.bankruptcy_history !== 'no') {
      newNeeds.push({ id: 'bk_discharge', label: 'Bankruptcy discharge papers', category: 'legal' });
    }

    if (declarations.veteran && declarations.veteran !== 'no') {
      newNeeds.push({ id: 'dd214', label: 'DD-214 or Certificate of Eligibility', category: 'military' });
    }

    if (declarations.alimony_obligations && declarations.alimony_obligations !== 'no') {
      newNeeds.push({ id: 'divorce_decree', label: 'Divorce decree / court order', category: 'legal' });
    }

    // Always need bank statements
    newNeeds.push({ id: 'bank_statements', label: 'Bank statements (2 months)', category: 'assets' });

    setNeedsList(newNeeds);
  }, [declarations]);

  // Show micro-win animation
  const showMicroWinAnimation = (message) => {
    setMicroWinMessage(message);
    setShowMicroWin(true);
    setTimeout(() => setShowMicroWin(false), 2500);
  };

  // Handle declaration answer
  const handleDeclarationAnswer = (questionId, value) => {
    setIsAnimating(true);

    setDeclarations(prev => ({
      ...prev,
      [questionId]: value,
    }));

    setTimeout(() => {
      setIsAnimating(false);

      if (currentQuestionIndex < DECLARATION_QUESTIONS.length - 1) {
        setCurrentQuestionIndex(prev => prev + 1);
      } else {
        // Completed declarations - show micro-win and move to profile
        showMicroWinAnimation('Your personalized checklist is ready!');
        setTimeout(() => {
          setCurrentStage('profile');
        }, 1500);
      }
    }, 300);
  };

  // Navigate between stages
  const goToNextStage = () => {
    const currentIndex = STAGES.findIndex(s => s.id === currentStage);
    if (currentIndex < STAGES.length - 1) {
      // Skip real estate section if they don't own property
      if (STAGES[currentIndex + 1].id === 'realestate' && declarations.owns_real_estate === 'no') {
        setCurrentStage(STAGES[currentIndex + 2].id);
        showMicroWinAnimation('Skipped! You don\'t own other properties.');
      } else {
        setCurrentStage(STAGES[currentIndex + 1].id);
        showMicroWinAnimation(getStageMicroWin(STAGES[currentIndex].id));
      }
    }
  };

  const goToPrevStage = () => {
    const currentIndex = STAGES.findIndex(s => s.id === currentStage);
    if (currentIndex > 0) {
      // Skip real estate section if they don't own property
      if (STAGES[currentIndex - 1].id === 'realestate' && declarations.owns_real_estate === 'no') {
        setCurrentStage(STAGES[currentIndex - 2].id);
      } else {
        setCurrentStage(STAGES[currentIndex - 1].id);
      }
    }
  };

  const getStageMicroWin = (stageId) => {
    const wins = {
      declarations: 'Great start! Your journey is personalized.',
      profile: 'Profile complete! You\'re making great progress.',
      income: 'Income captured! Almost there.',
      assets: 'Assets recorded! You\'re doing amazing.',
      realestate: 'Properties logged! Nearly done.',
      loan: 'Loan details set! Just review and submit.',
    };
    return wins[stageId] || 'Section complete!';
  };

  // Render the declarations stage (one question per screen)
  const renderDeclarationsStage = () => {
    const question = DECLARATION_QUESTIONS[currentQuestionIndex];

    return (
      <div className={`declaration-screen ${isAnimating ? 'animating-out' : 'animating-in'}`}>
        <div className="question-number">
          Question {currentQuestionIndex + 1} of {DECLARATION_QUESTIONS.length}
        </div>

        <h2 className="declaration-question">{question.question}</h2>

        {question.hint && (
          <p className="declaration-hint">💡 {question.hint}</p>
        )}

        <div className="declaration-options">
          {question.options.map(option => (
            <button
              key={option.value}
              className={`declaration-option ${declarations[question.id] === option.value ? 'selected' : ''}`}
              onClick={() => handleDeclarationAnswer(question.id, option.value)}
            >
              <span className="option-icon">{option.icon}</span>
              <span className="option-label">{option.label}</span>
              {option.description && (
                <span className="option-description">{option.description}</span>
              )}
            </button>
          ))}
        </div>

        {currentQuestionIndex > 0 && (
          <button
            className="back-link"
            onClick={() => setCurrentQuestionIndex(prev => prev - 1)}
          >
            ← Go back
          </button>
        )}
      </div>
    );
  };

  // Render profile stage
  const renderProfileStage = () => {
    return (
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

          <div className="form-group">
            <label>Current Address</label>
            <input
              type="text"
              value={profileData.address || ''}
              onChange={(e) => setProfileData(prev => ({ ...prev, address: e.target.value }))}
              placeholder="Start typing your address..."
              className="fun-input"
            />
            <span className="input-hint">🔍 We'll auto-complete as you type</span>
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
  };

  // Render income stage with conditional sections
  const renderIncomeStage = () => {
    const isSelfEmployed = declarations.self_employed === 'yes' || declarations.self_employed === 'side_business';

    return (
      <div className="stage-content">
        <div className="stage-header">
          <h2>Tell us about your income</h2>
          <p>This helps us find the best loan for you</p>
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
            <div
              className={`income-card ${incomeData.primaryType === 'other' ? 'selected' : ''}`}
              onClick={() => setIncomeData(prev => ({ ...prev, primaryType: 'other' }))}
            >
              <span className="card-icon">💰</span>
              <span className="card-label">Other</span>
              <span className="card-desc">Rental, investments</span>
            </div>
          </div>
        </div>

        {incomeData.primaryType === 'employed' && (
          <div className="form-card">
            <h3>Employment Details</h3>
            <div className="form-group">
              <label>Employer Name</label>
              <input
                type="text"
                value={incomeData.employerName || ''}
                onChange={(e) => setIncomeData(prev => ({ ...prev, employerName: e.target.value }))}
                placeholder="Start typing company name..."
                className="fun-input"
              />
              <span className="input-hint">🔍 AI will help find your employer</span>
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

            <div className="bonus-section">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={incomeData.hasBonus || false}
                  onChange={(e) => setIncomeData(prev => ({ ...prev, hasBonus: e.target.checked }))}
                />
                I receive bonuses, overtime, or commissions
              </label>

              {incomeData.hasBonus && (
                <div className="form-row">
                  <div className="form-group">
                    <label>Average Monthly Bonus</label>
                    <div className="input-with-prefix">
                      <span className="input-prefix">$</span>
                      <input
                        type="number"
                        value={incomeData.monthlyBonus || ''}
                        onChange={(e) => setIncomeData(prev => ({ ...prev, monthlyBonus: e.target.value }))}
                        className="fun-input"
                      />
                    </div>
                  </div>
                </div>
              )}
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
                  <option value="partnership">Partnership</option>
                </select>
              </div>
              <div className="form-group">
                <label>Ownership %</label>
                <input
                  type="number"
                  value={incomeData.ownershipPercent || ''}
                  onChange={(e) => setIncomeData(prev => ({ ...prev, ownershipPercent: e.target.value }))}
                  className="fun-input"
                  min="0"
                  max="100"
                />
              </div>
            </div>

            <div className="form-group">
              <label>Annual Net Income (from business)</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={incomeData.businessIncome || ''}
                  onChange={(e) => setIncomeData(prev => ({ ...prev, businessIncome: e.target.value }))}
                  className="fun-input"
                />
              </div>
              <span className="input-hint">Use your net income from Schedule C or K-1</span>
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

  // Render assets stage
  const renderAssetsStage = () => {
    const hasGiftFunds = declarations.gift_funds === 'yes';

    return (
      <div className="stage-content">
        <div className="stage-header">
          <h2>Let's talk about your savings</h2>
          <p>We'll use this to determine your down payment options</p>
        </div>

        <div className="form-card">
          <div className="connect-bank-section">
            <div className="connect-bank-card">
              <span className="bank-icon">🏦</span>
              <h3>Connect Your Bank</h3>
              <p>Securely link your accounts to auto-fill your balances</p>
              <button className="btn-connect-bank">
                Connect with Plaid
              </button>
              <span className="security-note">🔒 Bank-level encryption</span>
            </div>

            <div className="or-divider">
              <span>or enter manually</span>
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Checking Accounts</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={assetData.checking || ''}
                  onChange={(e) => setAssetData(prev => ({ ...prev, checking: e.target.value }))}
                  className="fun-input"
                  placeholder="0"
                />
              </div>
            </div>
            <div className="form-group">
              <label>Savings Accounts</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={assetData.savings || ''}
                  onChange={(e) => setAssetData(prev => ({ ...prev, savings: e.target.value }))}
                  className="fun-input"
                  placeholder="0"
                />
              </div>
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Investment Accounts</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={assetData.investments || ''}
                  onChange={(e) => setAssetData(prev => ({ ...prev, investments: e.target.value }))}
                  className="fun-input"
                  placeholder="0"
                />
              </div>
            </div>
            <div className="form-group">
              <label>Retirement (401k, IRA)</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input
                  type="number"
                  value={assetData.retirement || ''}
                  onChange={(e) => setAssetData(prev => ({ ...prev, retirement: e.target.value }))}
                  className="fun-input"
                  placeholder="0"
                />
              </div>
            </div>
          </div>

          {/* Gift Funds Section - Only shown if declared */}
          {hasGiftFunds && (
            <div className="gift-funds-section">
              <h3>🎁 Gift Funds Details</h3>
              <p className="section-hint">Great news! Gift funds can help with your down payment.</p>

              <div className="form-group">
                <label>Gift Amount</label>
                <div className="input-with-prefix">
                  <span className="input-prefix">$</span>
                  <input
                    type="number"
                    value={assetData.giftAmount || ''}
                    onChange={(e) => setAssetData(prev => ({ ...prev, giftAmount: e.target.value }))}
                    className="fun-input"
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Donor Name</label>
                  <input
                    type="text"
                    value={assetData.donorName || ''}
                    onChange={(e) => setAssetData(prev => ({ ...prev, donorName: e.target.value }))}
                    className="fun-input"
                    placeholder="Who is giving the gift?"
                  />
                </div>
                <div className="form-group">
                  <label>Relationship</label>
                  <select
                    value={assetData.donorRelationship || ''}
                    onChange={(e) => setAssetData(prev => ({ ...prev, donorRelationship: e.target.value }))}
                    className="fun-input"
                  >
                    <option value="">Select...</option>
                    <option value="parent">Parent</option>
                    <option value="grandparent">Grandparent</option>
                    <option value="sibling">Sibling</option>
                    <option value="other_family">Other Family</option>
                  </select>
                </div>
              </div>

              <div className="gift-letter-generator">
                <button className="btn-generate-letter">
                  ✨ Generate Gift Letter
                </button>
                <span className="hint">We'll create a compliant gift letter for your donor to sign</span>
              </div>
            </div>
          )}
        </div>

        <div className="total-assets-display">
          <span>Total Verified Assets:</span>
          <strong>
            ${(
              (parseFloat(assetData.checking) || 0) +
              (parseFloat(assetData.savings) || 0) +
              (parseFloat(assetData.investments) || 0) +
              (parseFloat(assetData.retirement) || 0) +
              (parseFloat(assetData.giftAmount) || 0)
            ).toLocaleString()}
          </strong>
        </div>

        <div className="stage-navigation">
          <button className="btn-back" onClick={goToPrevStage}>← Back</button>
          <button className="btn-continue" onClick={goToNextStage}>Continue →</button>
        </div>
      </div>
    );
  };

  // Render real estate stage (only if they own property)
  const renderRealEstateStage = () => {
    return (
      <div className="stage-content">
        <div className="stage-header">
          <h2>Your Current Properties</h2>
          <p>Tell us about the real estate you own</p>
        </div>

        <div className="form-card">
          <div className="property-card">
            <h3>🏠 Primary Residence</h3>

            <div className="form-group">
              <label>Property Address</label>
              <input
                type="text"
                value={realEstateData.currentAddress || ''}
                onChange={(e) => setRealEstateData(prev => ({ ...prev, currentAddress: e.target.value }))}
                className="fun-input"
                placeholder="Start typing address..."
              />
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>Estimated Value</label>
                <div className="input-with-prefix">
                  <span className="input-prefix">$</span>
                  <input
                    type="number"
                    value={realEstateData.currentValue || ''}
                    onChange={(e) => setRealEstateData(prev => ({ ...prev, currentValue: e.target.value }))}
                    className="fun-input"
                  />
                </div>
                <span className="input-hint">🏠 We'll verify with market data</span>
              </div>
              <div className="form-group">
                <label>Mortgage Balance</label>
                <div className="input-with-prefix">
                  <span className="input-prefix">$</span>
                  <input
                    type="number"
                    value={realEstateData.currentMortgage || ''}
                    onChange={(e) => setRealEstateData(prev => ({ ...prev, currentMortgage: e.target.value }))}
                    className="fun-input"
                  />
                </div>
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>Monthly Payment</label>
                <div className="input-with-prefix">
                  <span className="input-prefix">$</span>
                  <input
                    type="number"
                    value={realEstateData.monthlyPayment || ''}
                    onChange={(e) => setRealEstateData(prev => ({ ...prev, monthlyPayment: e.target.value }))}
                    className="fun-input"
                  />
                </div>
              </div>
              <div className="form-group">
                <label>What will you do with this property?</label>
                <select
                  value={realEstateData.propertyIntent || ''}
                  onChange={(e) => setRealEstateData(prev => ({ ...prev, propertyIntent: e.target.value }))}
                  className="fun-input"
                >
                  <option value="">Select...</option>
                  <option value="keep">Keep as primary home</option>
                  <option value="sell">Sell it</option>
                  <option value="rent">Convert to rental</option>
                  <option value="second_home">Keep as second home</option>
                </select>
              </div>
            </div>
          </div>

          {declarations.owns_real_estate === 'multiple' && (
            <button className="btn-add-property">
              + Add Another Property
            </button>
          )}
        </div>

        <div className="stage-navigation">
          <button className="btn-back" onClick={goToPrevStage}>← Back</button>
          <button className="btn-continue" onClick={goToNextStage}>Continue →</button>
        </div>
      </div>
    );
  };

  // Render loan details stage
  const renderLoanStage = () => {
    return (
      <div className="stage-content">
        <div className="stage-header">
          <h2>Your New Loan</h2>
          <p>Let's find the perfect loan for you</p>
        </div>

        <div className="loan-purpose-selector">
          <h3>What are you looking to do?</h3>
          <div className="purpose-cards">
            <div
              className={`purpose-card ${loanData.purpose === 'purchase' ? 'selected' : ''}`}
              onClick={() => setLoanData(prev => ({ ...prev, purpose: 'purchase' }))}
            >
              <span className="card-icon">🏠</span>
              <span className="card-label">Buy a Home</span>
            </div>
            <div
              className={`purpose-card ${loanData.purpose === 'refinance' ? 'selected' : ''}`}
              onClick={() => setLoanData(prev => ({ ...prev, purpose: 'refinance' }))}
            >
              <span className="card-icon">🔄</span>
              <span className="card-label">Refinance</span>
            </div>
            <div
              className={`purpose-card ${loanData.purpose === 'cashout' ? 'selected' : ''}`}
              onClick={() => setLoanData(prev => ({ ...prev, purpose: 'cashout' }))}
            >
              <span className="card-icon">💵</span>
              <span className="card-label">Cash-Out Refi</span>
            </div>
          </div>
        </div>

        {loanData.purpose === 'purchase' && (
          <div className="form-card">
            <h3>Property Details</h3>

            <div className="property-type-selector">
              <label>Property Type</label>
              <div className="type-pills">
                {['Single Family', 'Condo', 'Townhouse', 'Multi-Family'].map(type => (
                  <button
                    key={type}
                    className={`type-pill ${loanData.propertyType === type ? 'selected' : ''}`}
                    onClick={() => setLoanData(prev => ({ ...prev, propertyType: type }))}
                  >
                    {type}
                  </button>
                ))}
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>Purchase Price</label>
                <div className="input-with-prefix">
                  <span className="input-prefix">$</span>
                  <input
                    type="number"
                    value={loanData.purchasePrice || ''}
                    onChange={(e) => setLoanData(prev => ({ ...prev, purchasePrice: e.target.value }))}
                    className="fun-input"
                    placeholder="0"
                  />
                </div>
              </div>
              <div className="form-group">
                <label>Down Payment</label>
                <div className="input-with-prefix">
                  <span className="input-prefix">$</span>
                  <input
                    type="number"
                    value={loanData.downPayment || ''}
                    onChange={(e) => setLoanData(prev => ({ ...prev, downPayment: e.target.value }))}
                    className="fun-input"
                    placeholder="0"
                  />
                </div>
                {loanData.purchasePrice && loanData.downPayment && (
                  <span className="calculated-hint">
                    {((loanData.downPayment / loanData.purchasePrice) * 100).toFixed(1)}% down
                  </span>
                )}
              </div>
            </div>

            {/* VA Section - Only if veteran */}
            {(declarations.veteran === 'yes' || declarations.veteran === 'active') && (
              <div className="va-section">
                <h4>🎖️ VA Loan Options</h4>
                <p>As a veteran, you may qualify for a VA loan with:</p>
                <ul className="va-benefits">
                  <li>✓ No down payment required</li>
                  <li>✓ No PMI</li>
                  <li>✓ Competitive rates</li>
                </ul>
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={loanData.useVA || false}
                    onChange={(e) => setLoanData(prev => ({ ...prev, useVA: e.target.checked }))}
                  />
                  I want to use my VA benefit
                </label>
              </div>
            )}

            <div className="loan-programs">
              <h4>Recommended Programs</h4>
              <div className="program-cards">
                <div
                  className={`program-card ${loanData.program === 'conventional' ? 'selected' : ''}`}
                  onClick={() => setLoanData(prev => ({ ...prev, program: 'conventional' }))}
                >
                  <span className="program-name">Conventional</span>
                  <span className="program-rate">~6.5% APR</span>
                  <span className="program-note">Best for 20%+ down</span>
                </div>
                <div
                  className={`program-card ${loanData.program === 'fha' ? 'selected' : ''}`}
                  onClick={() => setLoanData(prev => ({ ...prev, program: 'fha' }))}
                >
                  <span className="program-name">FHA</span>
                  <span className="program-rate">~6.25% APR</span>
                  <span className="program-note">3.5% down, flexible credit</span>
                </div>
                {(declarations.veteran === 'yes' || declarations.veteran === 'active') && (
                  <div
                    className={`program-card va ${loanData.program === 'va' ? 'selected' : ''}`}
                    onClick={() => setLoanData(prev => ({ ...prev, program: 'va' }))}
                  >
                    <span className="program-badge">🎖️ FOR YOU</span>
                    <span className="program-name">VA</span>
                    <span className="program-rate">~6.0% APR</span>
                    <span className="program-note">$0 down, no PMI</span>
                  </div>
                )}
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

  // Render review stage
  const renderReviewStage = () => {
    return (
      <div className="stage-content">
        <div className="stage-header">
          <h2>Review & Submit</h2>
          <p>Almost there! Let's make sure everything looks good.</p>
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
              <h3>💰 Assets</h3>
              <button className="edit-link" onClick={() => setCurrentStage('assets')}>Edit</button>
            </div>
            <div className="section-content">
              <p><strong>Total Assets:</strong> ${(
                (parseFloat(assetData.checking) || 0) +
                (parseFloat(assetData.savings) || 0) +
                (parseFloat(assetData.investments) || 0) +
                (parseFloat(assetData.retirement) || 0)
              ).toLocaleString()}</p>
              {declarations.gift_funds === 'yes' && (
                <p><strong>Gift Funds:</strong> ${parseFloat(assetData.giftAmount || 0).toLocaleString()}</p>
              )}
            </div>
          </div>

          <div className="review-section">
            <div className="section-header">
              <h3>🎯 Loan Details</h3>
              <button className="edit-link" onClick={() => setCurrentStage('loan')}>Edit</button>
            </div>
            <div className="section-content">
              <p><strong>Purpose:</strong> {loanData.purpose}</p>
              {loanData.purchasePrice && <p><strong>Purchase Price:</strong> ${parseFloat(loanData.purchasePrice).toLocaleString()}</p>}
              {loanData.downPayment && <p><strong>Down Payment:</strong> ${parseFloat(loanData.downPayment).toLocaleString()}</p>}
              {loanData.program && <p><strong>Program:</strong> {loanData.program}</p>}
            </div>
          </div>
        </div>

        {/* Needs List */}
        <div className="needs-list-section">
          <h3>📋 Your Document Checklist</h3>
          <p>Based on your answers, here's what we'll need:</p>
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

        <div className="submit-section">
          {isDemoMode && (
            <div className="demo-notice">
              <span>🎮 Demo Mode</span> - In a real application, this would submit to your loan officer.
            </div>
          )}

          <button className="btn-submit" onClick={() => showMicroWinAnimation('Application Submitted! 🎉')}>
            Submit Application
          </button>
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
      case 'declarations':
        return renderDeclarationsStage();
      case 'profile':
        return renderProfileStage();
      case 'income':
        return renderIncomeStage();
      case 'assets':
        return renderAssetsStage();
      case 'realestate':
        return renderRealEstateStage();
      case 'loan':
        return renderLoanStage();
      case 'review':
        return renderReviewStage();
      default:
        return renderDeclarationsStage();
    }
  };

  return (
    <div className="adaptive-urla">
      {/* Demo Mode Banner */}
      {isDemoMode && (
        <div className="demo-banner">
          <span className="demo-badge">DEMO</span>
          Exploring the application experience
        </div>
      )}

      {/* Gamified Progress Bar */}
      <div className="progress-header">
        <div className="progress-chapters">
          {STAGES.map((stage, index) => {
            const currentIndex = STAGES.findIndex(s => s.id === currentStage);
            const isComplete = index < currentIndex;
            const isCurrent = index === currentIndex;
            const isSkipped = stage.id === 'realestate' && declarations.owns_real_estate === 'no';

            return (
              <div
                key={stage.id}
                className={`progress-chapter ${isComplete ? 'complete' : ''} ${isCurrent ? 'current' : ''} ${isSkipped ? 'skipped' : ''}`}
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

      {/* Micro-Win Toast */}
      {showMicroWin && (
        <div className="micro-win-toast">
          <span className="micro-win-icon">🎉</span>
          <span className="micro-win-message">{microWinMessage}</span>
        </div>
      )}

      {/* Main Content */}
      <main className="urla-content">
        {renderStage()}
      </main>

      {/* Real-time Needs List Sidebar (shown after declarations) */}
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
